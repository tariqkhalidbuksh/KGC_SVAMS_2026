import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import config
from database import get_db_connection
from services.camera_service import stream_video

router = APIRouter(prefix="/api", tags=["Settings & Streaming"])

@router.get("/logo")
async def get_logo():
    if os.path.exists(config.LOGO_PATH):
        return FileResponse(config.LOGO_PATH)
    return JSONResponse({"error": "No logo configured"}, status_code=404)

@router.get("/settings")
async def get_settings():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT config_key, config_value FROM settings").fetchall()
            return {row['config_key']: row['config_value'] for row in rows}
        finally:
            conn.close()

from fastapi import HTTPException

def check_admin_permission(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if user and user.get("role") != "Admin":
        raise HTTPException(403, "Administrator privileges required. Viewer and Editor accounts cannot modify system configuration.")

@router.post("/settings")
async def save_settings(request: Request):
    check_admin_permission(request)
    body = await request.json()
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                for key, val in body.items():
                    conn.execute("INSERT OR REPLACE INTO settings (config_key, config_value) VALUES (?, ?)", (key, str(val)))
            return {"ok": True}
        finally:
            conn.close()

@router.get("/stream/hikvision")
async def stream_hikvision():
    return StreamingResponse(stream_video("Hikvision"), media_type="multipart/x-mixed-replace; boundary=frame")

@router.post("/settings/reset-activity")
async def reset_activity_data(request: Request = None):
    if request:
        check_admin_permission(request)
    """
    Resets all previous activity logs, raw reader scans, and camera audit entries.
    Retains all Members Directory records and System Settings.
    """
    import shutil
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM daily_logs")
                conn.execute("DELETE FROM raw_reader_logs")
                conn.execute("DELETE FROM camera_audit_logs")
                conn.execute("DELETE FROM guest_passes")
                conn.execute("DELETE FROM unregistered_tags")
                conn.execute("UPDATE members SET Current_Location = 'Outside'")
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('daily_logs', 'raw_reader_logs', 'camera_audit_logs', 'guest_passes', 'unregistered_tags')")
            conn.execute("VACUUM")
            
            # Count retained members and settings
            members_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            settings_count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        finally:
            conn.close()

    # Clear temporary images
    for folder in [config.SNAPSHOT_DIR, config.CAMERA_AUDIT_DIR, config.FTP_UPLOAD_DIR, config.TEST_DIR]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.unlink(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception:
                    pass

    # Clear in-memory state and caches
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
        config.FLEET_ADOPTION_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
    config.invalidate_member_cache()
    with config.BUFFER_LOCK:
        config.RECENT_CAM_TRIGGERS.clear()
        config.RECENT_TAGS.clear()
        config.PENDING_RFID_BUFFER.clear()
    config.FTP_EVENT_COUNT = {"count": 0}
    config.LAST_GATE_PASSAGE = {"time": 0.0, "log_id": None, "md5": None}

    return {
        "ok": True,
        "members_count": members_count,
        "settings_count": settings_count,
        "message": f"Activity logs reset. {members_count:,} members and {settings_count} settings preserved."
    }

@router.get("/settings/bulk-exit-exceptions")
async def get_bulk_exit_exceptions():
    """
    Returns configured exception whitelist for bulk exit and live facility occupancy breakdown.
    """
    import json
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1").fetchone()
            exceptions = []
            if row and row["config_value"]:
                try:
                    exceptions = json.loads(row["config_value"])
                except Exception:
                    exceptions = [x.strip() for x in row["config_value"].split(",") if x.strip()]

            from routers.logs import AUDIT_LOGS_BASE_QUERY, _build_paired_audits
            logs = [dict(r) for r in conn.execute(AUDIT_LOGS_BASE_QUERY + " ORDER BY d.id ASC").fetchall()]
            paired = _build_paired_audits(logs)
            inside = [p for p in paired if p.get("status") in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")]

            exempt_set = {str(x).strip().upper() for x in exceptions if str(x).strip()}
            exempt_count = 0
            for item in inside:
                v = item.get("entry") or item.get("exit") or {}
                p = (v.get("vehicle_number") or "").strip().upper()
                m = (v.get("mem_id") or "").strip().upper()
                t = (v.get("scanned_tag") or "").strip().upper()
                if (p and p in exempt_set) or (m and m in exempt_set) or (t and t in exempt_set):
                    exempt_count += 1

            total_inside = len(inside)
            clearable_count = max(0, total_inside - exempt_count)

            return {
                "exceptions": exceptions,
                "total_inside": total_inside,
                "exempt_inside_count": exempt_count,
                "clearable_count": clearable_count
            }
        finally:
            conn.close()

@router.post("/settings/bulk-exit-exceptions")
async def save_bulk_exit_exceptions(request: Request):
    """
    Updates the list of vehicle plates / IDs exempt from bulk exit.
    """
    import json
    body = await request.json()
    raw_list = body.get("exceptions", [])
    if not isinstance(raw_list, list):
        raise HTTPException(400, "Exceptions must be a list of vehicle plates or member IDs")

    cleaned = []
    seen = set()
    for item in raw_list:
        c = str(item).strip().upper()
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (config_key, config_value) VALUES ('bulk_exit_exceptions', ?)",
                    (json.dumps(cleaned),)
                )
            return {"ok": True, "exceptions": cleaned}
        finally:
            conn.close()

