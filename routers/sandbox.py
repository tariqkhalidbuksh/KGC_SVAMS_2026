import os
import time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
import config
from database import get_setting, set_setting
from services.sandbox_service import (
    notify_sandbox_rfid,
    get_sandbox_state,
    search_car_in_members,
    search_members_list,
    register_new_car_member,
    clear_sandbox_state,
    run_ocr_plate,
    link_tag_to_car,
    correlate_camera_capture,
    _capture_dahua_frame,
    SANDBOX_DAHUA_STATUS
)

router = APIRouter(prefix="/api/sandbox", tags=["RFID Sandbox Lab"])

class AssignTagRequest(BaseModel):
    tag: str
    car_number: str
    mem_id: str = None

class RegisterMemberRequest(BaseModel):
    tag: str
    car_number: str
    name: str
    mem_id: str = None
    make_model: str = "Standard"

class DahuaConfigRequest(BaseModel):
    url: str

class SimulateRfidRequest(BaseModel):
    tag: str
    direction: str = "Entry"

class TriggerDahuaRequest(BaseModel):
    direction: str = "Entry"
    manual_plate: str = None
    use_sample: bool = False

@router.get("/state")
async def get_state():
    """Returns the current real-time state of the Sandbox Lab."""
    return get_sandbox_state()

@router.get("/lookup-car")
async def lookup_car(plate: str):
    """Searches the database to check if a car number exists."""
    if not plate or not plate.strip():
        raise HTTPException(400, "License plate query is required")
    member = search_car_in_members(plate)
    return {
        "found": member is not None,
        "query": plate.strip().upper(),
        "member": member
    }

@router.post("/assign-tag")
async def assign_tag(payload: AssignTagRequest):
    """1-Click Action to assign an unregistered RFID tag to a member vehicle."""
    if not payload.tag or not payload.car_number:
        raise HTTPException(400, "Tag and Car Number are required")
    res = link_tag_to_car(payload.tag, payload.car_number, payload.mem_id)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Failed to assign tag"))
    return res

@router.post("/simulate-rfid")
async def simulate_rfid(payload: SimulateRfidRequest):
    """Simulates an unregistered RFID scan for sandbox testing and calibration."""
    clean_tag = payload.tag.strip().upper()
    notify_sandbox_rfid(clean_tag, direction=payload.direction, is_unregistered=True)
    return {
        "ok": True,
        "message": f"Simulated unregistered scan for Tag {clean_tag} ({payload.direction})",
        "tag": clean_tag
    }

@router.post("/trigger-dahua")
async def trigger_dahua(payload: TriggerDahuaRequest):
    """
    Triggers Dahua camera capture, aligns with pending RFID scans via the 0.5s-4.0s FIFO engine,
    and returns the correlated candidate.
    """
    cam_url = get_setting("dahua_cam_url", "")
    frame = None
    err = None

    if not payload.use_sample and cam_url:
        frame, err = _capture_dahua_frame(cam_url)
        if frame is not None:
            SANDBOX_DAHUA_STATUS["status"] = "ONLINE"
            SANDBOX_DAHUA_STATUS["last_capture"] = time.strftime("%H:%M:%S")
            SANDBOX_DAHUA_STATUS["last_error"] = None
        else:
            SANDBOX_DAHUA_STATUS["status"] = "OFFLINE"
            SANDBOX_DAHUA_STATUS["last_error"] = err

    if frame is None:
        # Fallback to existing sample capture from camera_audits if available, or test car image
        sample_path = None
        target_dir = os.path.join(config.STATIC_DIR, "camera_audits")
        if os.path.exists(target_dir):
            for f in sorted(os.listdir(target_dir), reverse=True):
                if f.endswith(('.jpg', '.jpeg')) and os.path.getsize(os.path.join(target_dir, f)) > 1000:
                    sample_path = os.path.join(target_dir, f)
                    break
        match_record = correlate_camera_capture(
            sample_path or "static/img/no-car.svg",
            direction=payload.direction,
            manual_plate=payload.manual_plate
        )
    else:
        match_record = correlate_camera_capture(
            frame,
            direction=payload.direction,
            manual_plate=payload.manual_plate
        )

    return {
        "ok": True,
        "record": match_record,
        "dahua_status": SANDBOX_DAHUA_STATUS["status"],
        "notice": "Aligned using 4-6m RF lead to 0.5m barrier transit correlation window"
    }

@router.get("/search-members")
async def search_members(q: str):
    """Returns matching members for autocomplete."""
    if not q or not q.strip():
        return {"results": []}
    return {"results": search_members_list(q.strip())}

@router.post("/register-member")
async def register_member(payload: RegisterMemberRequest):
    """Registers a new vehicle/member directly and links the RFID tag."""
    if not payload.tag or not payload.car_number or not payload.name:
        raise HTTPException(400, "Tag, Car Number, and Member Name are required")
    res = register_new_car_member(
        name=payload.name,
        car_number=payload.car_number,
        tag=payload.tag,
        mem_id=payload.mem_id,
        make_model=payload.make_model
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Failed to register member"))
    return res

class OcrRequest(BaseModel):
    image_path: str

@router.post("/ocr")
async def ocr_plate(payload: OcrRequest):
    """Runs OCR on a captured vehicle frame to detect license plate candidates."""
    plates = run_ocr_plate(payload.image_path)
    return {
        "ok": True,
        "plates": plates,
        "detected": plates[0] if plates else None
    }

@router.post("/clear")
async def clear_state():
    """Resets the sandbox session buffer."""
    return clear_sandbox_state()

@router.post("/config")
async def update_config(payload: DahuaConfigRequest):
    """Saves Dahua camera RTSP/HTTP configuration URL."""
    clean_url = payload.url.strip()
    set_setting("dahua_cam_url", clean_url)
    return {"ok": True, "message": "Dahua camera configuration saved successfully", "url": clean_url}
