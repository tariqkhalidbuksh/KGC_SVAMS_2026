from fastapi import APIRouter, HTTPException, Request
import config
from services.camera_service import grab_hikvision_snapshot, save_snapshot

router = APIRouter(prefix="/api/tools", tags=["Hardware Diagnostics"])

@router.get("/status")
async def get_hardware_status():
    return {
        "readers": config.READER_STATUS,
        "cameras": config.CAM_STATUS,
        "ftp_events": config.FTP_EVENT_COUNT["count"],
        "recent_tags": list(config.RECENT_TAGS),
        "enroll_mode": config.ENROLL_MODE["active"]
    }

@router.post("/capture/{cam}")
async def capture_diagnostic_frame(cam: str):
    img = grab_hikvision_snapshot()
    if img is None:
        raise HTTPException(502, "Camera HD snapshot failed - verify IP and credentials in Settings")
    path = save_snapshot(img, "test_diagnostic")
    if not path:
        raise HTTPException(500, "Failed to persist captured frame to disk")
    return {
        "ok": True,
        "path": path.replace("\\", "/"),
        "width": img.shape[1],
        "height": img.shape[0]
    }

@router.api_route("/event/hikvision", methods=["GET", "POST", "PUT"])
@router.api_route("/camera/trigger", methods=["GET", "POST"])
async def receive_camera_trigger(request: Request):
    """
    Sub-100ms ultra-low latency HTTP event receiver for Hikvision Alarm Center / HTTP Listening.
    Instantly triggers dual synchronized Dahua plate and Hikvision overview captures.
    """
    import os
    import time
    import cv2
    from services.access_service import process_camera_line_crossing
    from services.camera_service import grab_verified_snapshot, is_valid_image

    direction = "Line Crossing"
    temp_path = None

    try:
        content_type = request.headers.get("content-type", "").lower()
        if "multipart/form-data" in content_type:
            form = await request.form()
            for field in form:
                val = form[field]
                if hasattr(val, "filename") and hasattr(val, "read"):
                    data = await val.read()
                    if len(data) > 1000:
                        temp_path = os.path.join(config.FTP_UPLOAD_DIR, f"http_hook_{int(time.time()*1000)}.jpg")
                        with open(temp_path, "wb") as f:
                            f.write(data)
                        break
        else:
            body = await request.body()
            body_str = body.decode(errors="ignore").lower()
            if any(k in body_str for k in ["rule2", "rule02", "b-a", "exit", "leaving"]):
                direction = "Exit"
            elif any(k in body_str for k in ["rule1", "rule01", "a-b", "entry", "entering"]):
                direction = "Entry"
    except Exception:
        pass

    if not temp_path:
        hik_frame = grab_verified_snapshot("Hikvision", max_timeout_sec=1.5)
        if is_valid_image(hik_frame):
            temp_path = os.path.join(config.FTP_UPLOAD_DIR, f"http_hook_{int(time.time()*1000)}.jpg")
            cv2.imwrite(temp_path, hik_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

    if temp_path and os.path.exists(temp_path):
        import threading
        threading.Thread(target=process_camera_line_crossing, args=(temp_path, direction), daemon=True).start()
        return {"ok": True, "status": "triggered", "mode": "instant_http"}

    return {"ok": False, "status": "no_frame_available"}

