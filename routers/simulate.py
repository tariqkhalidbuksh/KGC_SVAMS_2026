import os
import time
from fastapi import APIRouter, Request, HTTPException, File, UploadFile, Form
import config
from database import get_db_connection
from services.access_service import execute_access_decision, log_camera_audit_event
from services.camera_service import analyze_vehicle_direction

router = APIRouter(prefix="/api", tags=["Simulation & QA Testing"])

@router.post("/simulate-rfid-full")
async def simulate_rfid_full(request: Request):
    body = await request.json()
    tag = body.get("tag", "").strip()
    direction = body.get("direction", "Auto")
    path_full = body.get("path_full") or None
    path_plate = body.get("path_plate") or None
    buffer_tag = body.get("buffer", False)
    dry_run = body.get("dry_run", False) or (tag == "PING_TEST")

    if not tag:
        raise HTTPException(400, "Tag parameter is required")

    if dry_run:
        return {"ok": True, "dry_run": True, "status": "active"}

    if buffer_tag:
        now = time.time()
        with config.BUFFER_LOCK:
            config.PENDING_RFID_BUFFER.append({
                "tag": tag,
                "first_seen": now,
                "last_seen": now,
                "direction": direction
            })
        return {"ok": True, "buffered": True, "queue_len": len(config.PENDING_RFID_BUFFER)}
    else:
        bypass = bool(body.get("bypass_cooldown", False))
        log_id = execute_access_decision(tag, direction, path_full, path_plate, is_ai_trigger=False, bypass_cooldown=bypass)
        return {"ok": True, "log_id": log_id, "mode": "direct"}

@router.post("/simulate-linecross")
async def simulate_linecross(file: UploadFile = File(...), direction: str = Form("Line Crossing")):
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
        raise HTTPException(400, "Only image files (JPG, PNG, WEBP, BMP) are allowed")
    ext = os.path.splitext(file.filename)[1]
    stamp = int(time.time() * 1000)
    target_dir = os.path.join(config.STATIC_DIR, "camera_audits")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, f"cam_audit_{stamp}{ext}")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image file exceeds 10MB limit")
    with open(target_path, "wb") as f_out:
        f_out.write(contents)
    
    rel_path = f"static/camera_audits/cam_audit_{stamp}{ext}"
    log_camera_audit_event(rel_path, direction=direction, event_type="Hikvision Line Crossing")
    config.FTP_EVENT_COUNT["count"] += 1
    return {"ok": True, "path": rel_path.replace("\\", "/"), "direction": direction}

@router.post("/simulate-notag-full")
async def simulate_notag_full(request: Request):
    body = await request.json()
    if body.get("dry_run", False):
        return {"ok": True, "dry_run": True, "status": "active"}

    direction = body.get("direction", "Auto")
    path_full = body.get("path_full") or None
    path_plate = body.get("path_plate") or None

    if direction in ("Auto", "Detect", None, "") and path_full:
        direction = analyze_vehicle_direction(path_full)
    elif direction not in ("Entry", "Exit"):
        direction = "Entry"

    log_id = execute_access_decision("NO_TAG", direction, path_full, path_plate, is_ai_trigger=True)
    return {"ok": True, "log_id": log_id, "direction": direction}

@router.post("/simulate/upload-evidence")
async def simulate_upload_evidence(file: UploadFile = File(...), cam: str = Form("hikvision")):
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
        raise HTTPException(400, "Only image files (JPG, PNG, WEBP, BMP) are allowed")
    ext = os.path.splitext(file.filename)[1]
    stamp = int(time.time() * 1000)
    target_path = f"static/snapshots/manual_hikvision_{stamp}{ext}"
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image file exceeds 10MB limit")
    with open(target_path, "wb") as f_out:
        f_out.write(contents)
    return {"ok": True, "path": target_path.replace("\\", "/"), "cam": cam}

@router.get("/simulate/recent")
async def simulate_recent_logs(limit: int = 15):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                ORDER BY d.id DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

@router.delete("/simulate/clear-logs")
async def simulate_clear_logs():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM daily_logs")
                conn.execute("DELETE FROM raw_reader_logs")
                conn.execute("DELETE FROM camera_audit_logs")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='daily_logs'")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='camera_audit_logs'")
            return {"ok": True, "message": "All gate access and camera audit logs cleared"}
        finally:
            conn.close()
