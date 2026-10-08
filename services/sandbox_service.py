import os
import re
import time
import uuid
import threading
from collections import deque
from datetime import datetime
import cv2
import numpy as np
import requests
import config
from database import get_db_connection, get_setting, set_setting

# Thread lock completely isolated from main gate production locks
SANDBOX_LOCK = threading.Lock()

# In-memory storage for sandbox session
SANDBOX_UNREGISTERED_TAGS = deque(maxlen=100)
SANDBOX_MATCHED_RECORDS = deque(maxlen=50)
SANDBOX_DAHUA_STATUS = {"status": "STANDBY", "last_capture": None, "ip": None, "last_error": None}

def notify_sandbox_rfid(tag: str, direction: str = "Entry", is_unregistered: bool = True):
    """
    Non-blocking shadow hook called when an RFID tag is detected.
    Does not hold any production locks.
    """
    if not tag or tag in ("NO_TAG", ""):
        return

    now = time.time()
    clean_tag = tag.strip().upper()

    with SANDBOX_LOCK:
        # Check if tag already exists in recent pending queue within last 8 seconds
        existing = next((item for item in SANDBOX_UNREGISTERED_TAGS if item["tag"] == clean_tag and (now - item["last_seen"] < 10.0)), None)
        if existing:
            existing["last_seen"] = now
            existing["read_count"] += 1
            existing["direction"] = direction or existing["direction"]
        else:
            SANDBOX_UNREGISTERED_TAGS.append({
                "id": str(uuid.uuid4())[:8],
                "tag": clean_tag,
                "direction": direction or "Entry",
                "first_seen": now,
                "last_seen": now,
                "read_count": 1,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "pending_match"
            })

def search_car_in_members(car_plate: str) -> dict | None:
    """
    Searches the members database to check if a car license plate already exists.
    Ignores whitespace and hyphens for fuzzy matching (e.g., 'BDB-686' matches 'BDB 686' and 'BDB686').
    """
    if not car_plate or not car_plate.strip():
        return None

    cleaned_query = re.sub(r'[^A-Za-z0-9]', '', car_plate).upper()
    if not cleaned_query:
        return None

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("""
                SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic
                FROM members
                WHERE UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) = ?
                   OR UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) LIKE ?
                LIMIT 1
            """, (cleaned_query, f"%{cleaned_query}%")).fetchone()

            if row:
                res = dict(row)
                res["has_tag"] = bool(res.get("E_tag_id") and res["E_tag_id"] not in ("NO_TAG", ""))
                return res
            return None
        finally:
            conn.close()

def link_tag_to_car(tag: str, car_number: str, mem_id: str = None) -> dict:
    """
    1-Click Action: Assigns the unregistered RFID tag to a member's vehicle profile.
    Also links any prior daily_logs with this tag so past visits link to the member.
    """
    clean_tag = tag.strip().upper()
    clean_car = car_number.strip().upper()
    cleaned_query = re.sub(r'[^A-Za-z0-9]', '', clean_car).upper()

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                # Find target member
                if mem_id:
                    member_row = conn.execute("SELECT * FROM members WHERE Mem_id = ? LIMIT 1", (mem_id,)).fetchone()
                else:
                    member_row = conn.execute("""
                        SELECT * FROM members 
                        WHERE UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) = ? LIMIT 1
                    """, (cleaned_query,)).fetchone()

                if not member_row:
                    return {"ok": False, "error": f"No member found for Car Number '{car_number}'"}

                member = dict(member_row)

                # Update member with new RFID tag
                conn.execute("UPDATE members SET E_tag_id = ? WHERE id = ?", (clean_tag, member["id"]))

                # Update past guest logs for this tag
                conn.execute("""
                    UPDATE daily_logs 
                    SET mem_id = ?, name = ?, vehicle_number = ?
                    WHERE scanned_tag = ? AND (mem_id = 'GUEST-LOG' OR mem_id IS NULL OR mem_id = '')
                """, (member["Mem_id"], member["Name"], member["Car_number"], clean_tag))

                # Remove from unregistered_tags table
                conn.execute("DELETE FROM unregistered_tags WHERE tag = ?", (clean_tag,))

            # Mark matched record in sandbox memory
            with SANDBOX_LOCK:
                for rec in SANDBOX_MATCHED_RECORDS:
                    if rec.get("tag") == clean_tag:
                        rec["status"] = "ASSIGNED"
                        rec["assigned_to"] = member["Name"]
                        rec["assigned_car"] = member["Car_number"]

            return {
                "ok": True,
                "message": f"Successfully linked Tag {clean_tag} to {member['Name']} ({member['Car_number']})",
                "member": member
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()

def search_members_list(query: str, limit: int = 8) -> list[dict]:
    """
    Returns a list of matching members for live autocomplete by plate, name, or mem_id.
    """
    if not query or not query.strip():
        return []
    cleaned_query = re.sub(r'[^A-Za-z0-9]', '', query).upper()
    if not cleaned_query:
        return []
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""
                SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic
                FROM members
                WHERE UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) LIKE ?
                   OR UPPER(Name) LIKE ?
                   OR Mem_id LIKE ?
                LIMIT ?
            """, (f"%{cleaned_query}%", f"%{query.strip().upper()}%", f"%{query.strip()}%", limit)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["has_tag"] = bool(item.get("E_tag_id") and item["E_tag_id"] not in ("NO_TAG", ""))
                results.append(item)
            return results
        finally:
            conn.close()

def register_new_car_member(name: str, car_number: str, tag: str, mem_id: str = None, make_model: str = "Unspecified") -> dict:
    """
    Registers a brand-new vehicle & member directly from the Sandbox.
    """
    clean_tag = tag.strip().upper()
    clean_car = car_number.strip().upper()
    clean_name = name.strip().upper()
    clean_mem_id = (mem_id or f"MEM-{str(uuid.uuid4())[:6].upper()}").strip()

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status)
                    VALUES (?, ?, ?, ?, ?, 'Active')
                """, (clean_mem_id, clean_name, clean_car, make_model or "Standard", clean_tag))

                # Update any previous daily logs
                conn.execute("""
                    UPDATE daily_logs 
                    SET mem_id = ?, name = ?, vehicle_number = ?
                    WHERE scanned_tag = ? AND (mem_id = 'GUEST-LOG' OR mem_id IS NULL OR mem_id = '')
                """, (clean_mem_id, clean_name, clean_car, clean_tag))

                conn.execute("DELETE FROM unregistered_tags WHERE tag = ?", (clean_tag,))

            with SANDBOX_LOCK:
                for rec in SANDBOX_MATCHED_RECORDS:
                    if rec.get("tag") == clean_tag:
                        rec["status"] = "ASSIGNED"
                        rec["assigned_to"] = clean_name
                        rec["assigned_car"] = clean_car

            return {
                "ok": True,
                "message": f"Successfully registered new vehicle {clean_car} for {clean_name} with Tag {clean_tag}",
                "member": {
                    "Mem_id": clean_mem_id,
                    "Name": clean_name,
                    "Car_number": clean_car,
                    "Make_Model": make_model,
                    "E_tag_id": clean_tag
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()

def clear_sandbox_state() -> dict:
    """Resets the pending and matched ring buffers."""
    with SANDBOX_LOCK:
        SANDBOX_UNREGISTERED_TAGS.clear()
        SANDBOX_MATCHED_RECORDS.clear()
    return {"ok": True, "message": "Sandbox session queues cleared successfully"}

_EASYOCR_READER = None

def run_ocr_plate(image_path: str) -> list[str]:
    """Runs lightweight plate text recognition if easyocr is available."""
    global _EASYOCR_READER
    if not image_path or not os.path.isfile(image_path):
        return []
    try:
        if _EASYOCR_READER is None:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
        if _EASYOCR_READER:
            results = _EASYOCR_READER.readtext(image_path)
            plates = []
            for bbox, text, prob in results:
                t = re.sub(r'[^A-Za-z0-9]', '', text).upper()
                if 2 <= len(t) <= 10 and prob > 0.25:
                    plates.append(t)
            return plates
    except Exception:
        pass
    return []

def _capture_dahua_frame(cam_url: str = None) -> tuple[np.ndarray | None, str | None]:
    """
    Captures a frame from Dahua camera using RTSP or HTTP snapshot API with a strict 1.5s timeout.
    """
    url = cam_url or get_setting("dahua_cam_url", "")
    if not url:
        return None, "No Dahua camera URL configured"

    # Option 1: Dahua HTTP CGI snapshot API (e.g. http://ip/cgi-bin/snapshot.cgi)
    if url.lower().startswith("http://") or url.lower().startswith("https://"):
        try:
            # Parse user:password if embedded in URL
            creds = None
            clean_url = url
            m = re.search(r'https?://([^:]+):([^@]+)@(.+)', url)
            if m:
                creds = requests.auth.HTTPDigestAuth(m.group(1), m.group(2))
                clean_url = "http://" + m.group(3)
            
            res = requests.get(clean_url, auth=creds, timeout=1.5)
            if res.status_code == 200:
                arr = np.frombuffer(res.content, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None and img.size > 0:
                    return img, None
        except Exception as e:
            pass

    # Option 2: Dahua RTSP stream (e.g. rtsp://user:pass@ip:554/cam/realmonitor?channel=1&subtype=0)
    if url.lower().startswith("rtsp://"):
        cap = None
        try:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;100000|probesize;100000"
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                return frame, None
        except Exception as e:
            return None, str(e)
        finally:
            if cap:
                cap.release()

    return None, "Failed to capture frame from Dahua stream"

def correlate_camera_capture(
    image_input: str | np.ndarray,
    direction: str = "Entry",
    manual_plate: str = None
) -> dict:
    """
    Core Alignment Engine:
    Correlates an incoming camera capture (at 0.5m barrier line) with candidate
    unregistered RFID tags detected 4-6m away within the 0.5s - 4.5s lead window.
    """
    now = time.time()
    stamp = int(now * 1000)
    save_dir = os.path.join(config.STATIC_DIR, "sandbox_captures")
    os.makedirs(save_dir, exist_ok=True)

    rel_path = ""
    if isinstance(image_input, np.ndarray):
        rel_path = f"static/sandbox_captures/dahua_cap_{stamp}.jpg"
        cv2.imwrite(rel_path, image_input, [cv2.IMWRITE_JPEG_QUALITY, 90])
    elif isinstance(image_input, str) and os.path.isfile(image_input):
        rel_path = f"static/sandbox_captures/dahua_cap_{stamp}.jpg"
        import shutil
        shutil.copy(image_input, rel_path)
    else:
        # Fallback to test car image if available
        rel_path = "static/img/no-car.svg"

    candidate_tag = None
    time_delta = 0.0
    confidence = 0

    with SANDBOX_LOCK:
        # Search candidate tags whose first read occurred 0.3s to 5.0s ago (FIFO lead)
        candidates = []
        for item in list(SANDBOX_UNREGISTERED_TAGS):
            if item.get("status") == "pending_match":
                dt = now - item["last_seen"]
                # Car was 4-6m away when first seen, and 0.5m when last seen / camera triggers
                if 0.1 <= dt <= 6.0:
                    candidates.append((dt, item))

        if candidates:
            # Sort by closest time delta to camera snapshot
            candidates.sort(key=lambda x: x[0])
            best_dt, best_item = candidates[0]
            candidate_tag = best_item["tag"]
            time_delta = round(best_dt, 2)
            # Confidence score calculation
            confidence = max(60, min(99, int(100 - (abs(best_dt - 1.2) * 12))))
            best_item["status"] = "matched"
        elif SANDBOX_UNREGISTERED_TAGS:
            # Fallback to most recent unregistered tag
            most_recent = SANDBOX_UNREGISTERED_TAGS[-1]
            candidate_tag = most_recent["tag"]
            time_delta = round(now - most_recent["last_seen"], 2)
            confidence = 75
            most_recent["status"] = "matched"
        else:
            candidate_tag = "UNREGISTERED_PENDING"
            time_delta = 0.0
            confidence = 50

    # Auto Plate Search in Database
    detected_plate = manual_plate or ""
    matched_member = None
    if detected_plate:
        matched_member = search_car_in_members(detected_plate)

    record = {
        "id": f"MATCH-{str(uuid.uuid4())[:6].upper()}",
        "tag": candidate_tag,
        "direction": direction or "Entry",
        "image_path": rel_path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": now,
        "time_delta": time_delta,
        "confidence": confidence,
        "detected_plate": detected_plate,
        "member": matched_member,
        "status": "PENDING"
    }

    with SANDBOX_LOCK:
        SANDBOX_MATCHED_RECORDS.appendleft(record)

    return record

def get_sandbox_state() -> dict:
    """Returns the full real-time state of the Sandbox Lab."""
    with SANDBOX_LOCK:
        pending_tags = list(SANDBOX_UNREGISTERED_TAGS)
        matches = list(SANDBOX_MATCHED_RECORDS)
        dahua_status = dict(SANDBOX_DAHUA_STATUS)

    dahua_url = get_setting("dahua_cam_url", "rtsp://admin:admin123@192.168.0.221:554/cam/realmonitor?channel=1&subtype=0")

    return {
        "pending_tags": pending_tags,
        "matches": matches,
        "dahua_status": dahua_status,
        "dahua_url": dahua_url,
        "stats": {
            "pending_count": len([t for t in pending_tags if t.get("status") == "pending_match"]),
            "matched_count": len(matches),
            "assigned_count": len([m for m in matches if m.get("status") == "ASSIGNED"])
        }
    }
