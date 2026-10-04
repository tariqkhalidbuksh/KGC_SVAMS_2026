from fastapi import APIRouter, HTTPException
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
