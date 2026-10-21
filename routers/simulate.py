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
        gate = body.get("gate_name") or body.get("gate_no") or body.get("gate") or None
        log_id = execute_access_decision(tag, direction, path_full, path_plate, is_ai_trigger=False, bypass_cooldown=bypass, gate_name=gate)
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
    
    # Dahua Camera Alignment: capture live or test frame on-demand (no RAM buffer)
    from services.camera_service import grab_dahua_snapshot, create_simulated_anpr_frame, is_valid_image
    import cv2
    dahua_rel_path = None
    try:
        dahua_img, _, _ = grab_dahua_snapshot(timeout=1.0)
        if dahua_img is None or not is_valid_image(dahua_img):
            dahua_img = create_simulated_anpr_frame()
        if dahua_img is not None:
            dahua_target = os.path.join(target_dir, f"dahua_audit_{stamp}.jpg")
            cv2.imwrite(dahua_target, dahua_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            dahua_rel_path = f"static/camera_audits/dahua_audit_{stamp}.jpg"
    except Exception:
        pass

    rel_path = f"static/camera_audits/cam_audit_{stamp}{ext}"
    log_camera_audit_event(rel_path, plate_image_path=dahua_rel_path, direction=direction, event_type="Hikvision Line Crossing")
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
                    d.gate_no, d.gate_no as gate, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
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
                conn.execute("DELETE FROM unregistered_tags")
                conn.execute("UPDATE members SET Current_Location = 'Outside'")
                conn.execute("ALTER SEQUENCE IF EXISTS daily_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS raw_reader_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS camera_audit_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS unregistered_tags_id_seq RESTART WITH 1")
            with config.CACHE_LOCK:
                config.LATEST_LOG_CACHE = None
                config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
                config.FLEET_ADOPTION_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
            config.invalidate_member_cache()
            return {"ok": True, "message": "All gate access, camera audit, and unregistered vehicle logs cleared"}
        finally:
            conn.close()

@router.get("/simulate/dahua-config")
async def get_dahua_sim_config():
    from database import get_setting
    return {
        "hikvision_url": get_setting("hikvision_cam_url", ""),
        "dahua_url": get_setting("dahua_cam_url", "rtsp://admin:admin123@192.168.0.221:554/cam/realmonitor?channel=1&subtype=0")
    }

@router.post("/simulate/test-dual-camera-trigger")
async def test_dual_camera_trigger(request: Request):
    from datetime import datetime
    from database import get_setting, set_setting
    from services.camera_service import (
        grab_verified_snapshot,
        grab_dahua_snapshot,
        create_simulated_anpr_frame,
        create_simulated_hikvision_frame,
        save_snapshot
    )

    body = await request.json()
    dahua_url = (body.get("dahua_url") or "").strip() or get_setting("dahua_cam_url", "")
    if dahua_url and body.get("save_dahua_url", False):
        set_setting("dahua_cam_url", dahua_url)

    direction = body.get("direction", "Entry")
    simulate_fallback = body.get("simulate_fallback", True)
    timeout_sec = float(body.get("timeout_sec", 2.0))

    t_trigger_start = datetime.now()
    trigger_iso = t_trigger_start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # 1. Trigger Hikvision Overview Capture
    t0_hik = time.perf_counter()
    hik_img = grab_verified_snapshot("Hikvision", max_timeout_sec=timeout_sec)
    t1_hik = time.perf_counter()
    hik_latency_ms = round((t1_hik - t0_hik) * 1000, 2)
    hik_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    hik_status = "ONLINE_CAPTURED"
    if hik_img is None:
        if simulate_fallback:
            hik_img = create_simulated_hikvision_frame(direction=direction, timestamp_str=hik_ts)
            hik_status = "SIMULATED_FRAME"
        else:
            hik_status = "OFFLINE"

    hik_path = save_snapshot(hik_img, "sim_hik_wide") if hik_img is not None else None

    # 2. Concurrently Trigger Dahua Snapshot Request
    dahua_img, dahua_latency_ms, dahua_err = grab_dahua_snapshot(dahua_url, timeout=timeout_sec)
    dahua_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    dahua_status = "ONLINE_CAPTURED"
    if dahua_img is None:
        if simulate_fallback:
            dahua_img = create_simulated_anpr_frame(plate_text="EAC-638", timestamp_str=dahua_ts)
            dahua_status = f"SIMULATED_TEST_FRAME ({dahua_err or 'Camera Offline'})"
        else:
            dahua_status = f"OFFLINE ({dahua_err})"

    dahua_path = save_snapshot(dahua_img, "sim_dahua_anpr") if dahua_img is not None else None

    # 3. Time Delta & Velocity Displacement Analysis
    time_delta_ms = round(abs(dahua_latency_ms - hik_latency_ms), 2)
    sec_delay = (dahua_latency_ms / 1000.0)
    disp_5kmh = round(sec_delay * 1.38889 * 100, 1)   # cm
    disp_10kmh = round(sec_delay * 2.77778 * 100, 1)  # cm
    disp_15kmh = round(sec_delay * 4.16667 * 100, 1)  # cm

    return {
        "ok": True,
        "trigger_time": trigger_iso,
        "hikvision": {
            "status": hik_status,
            "timestamp": hik_ts,
            "latency_ms": hik_latency_ms,
            "image_path": hik_path.replace("\\", "/") if hik_path else None
        },
        "dahua": {
            "status": dahua_status,
            "timestamp": dahua_ts,
            "latency_ms": dahua_latency_ms,
            "image_path": dahua_path.replace("\\", "/") if dahua_path else None,
            "error": dahua_err
        },
        "time_delta_ms": time_delta_ms,
        "displacement_cm": {
            "speed_5kmh": disp_5kmh,
            "speed_10kmh": disp_10kmh,
            "speed_15kmh": disp_15kmh
        },
        "analysis_notes": f"Dahua HTTP Snapshot took {dahua_latency_ms} ms. At 10 km/h, the vehicle moves ~{disp_10kmh} cm during camera shutter delay."
    }
