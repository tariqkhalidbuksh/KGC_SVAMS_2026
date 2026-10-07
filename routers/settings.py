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
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('daily_logs', 'raw_reader_logs', 'camera_audit_logs', 'guest_passes')")
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

