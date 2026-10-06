import os
import time
import shutil
import hashlib
from datetime import datetime
import cv2
import config
from database import get_db_connection

def log_camera_audit_event(
    image_path: str,
    plate_image_path: str = None,
    direction: str = "Line Crossing",
    event_type: str = "Hikvision Line Crossing"
):
    if not image_path or not os.path.exists(image_path):
        return
    now_dt = datetime.now()
    date_str = now_dt.strftime("%Y-%m-%d")
    hour_str = now_dt.strftime("%H:00")
    timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                cursor = conn.execute("""INSERT INTO camera_audit_logs 
                    (image_path, plate_image_path, direction, event_type, timestamp, date_str, hour_str)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (image_path, plate_image_path, direction, event_type, timestamp_str, date_str, hour_str))
                return cursor.lastrowid
        except Exception as exc:
            print(f"[CAM AUDIT ERROR] {exc}")
            return None
        finally:
            conn.close()

def execute_access_decision(
    tag: str,
    direction: str = None,
    path_full: str = None,
    path_plate: str = None,
    is_ai_trigger: bool = False,
    bypass_cooldown: bool = False
) -> int:
    pkt_now = config.get_pkt_now()
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            clean_tag = tag.strip().upper() if not is_ai_trigger else "NO_TAG"

            if not is_ai_trigger and clean_tag != "NO_TAG":
                member = conn.execute(
                    "SELECT * FROM members WHERE UPPER(E_tag_id)=? OR UPPER(Mem_id)=? OR UPPER(Car_number)=?",
                    (clean_tag, clean_tag, clean_tag)
                ).fetchone()

                if member and (member['Status'] == 'Active' or not member['Status']):
                    name = member['Name']
                    mem_id = member['Mem_id']
                    car = member['Car_number']
                    access_type = "RFID Verified"
                    make_model = member['Make_Model']
                    profile_pic = member['Profile_pic']
                else:
                    name = "Unregistered Visitor"
                    mem_id = "GUEST-LOG"
                    car = clean_tag
                    access_type = "RFID Unknown"
                    make_model = None
                    profile_pic = None

                last_tag_log = conn.execute(
                    "SELECT id, direction, timestamp FROM daily_logs WHERE scanned_tag=? ORDER BY id DESC LIMIT 1",
                    (clean_tag,)
                ).fetchone()

                if last_tag_log:
                    try:
                        last_log_str = last_tag_log['timestamp']
                        try:
                            last_log_dt = datetime.strptime(last_log_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            last_log_dt = datetime.strptime(last_log_str, "%Y-%m-%d %I:%M:%S %p")
                        
                        elapsed_sec = (datetime.now() - last_log_dt).total_seconds()
                        last_dir = last_tag_log['direction']
                        cooldown_window = getattr(config, 'CROSS_READ_COOLDOWN', 45.0)

                        # UNIVERSAL COOLDOWN (45 Seconds):
                        # Suppresses duplicate scans, multi-reads, and cross-reader bounce between Entry & Exit
                        if not bypass_cooldown and elapsed_sec < cooldown_window:
                            return last_tag_log['id']

                        # If the last log was more than 12 hours ago, treat as a fresh visit starting with Entry
                        if elapsed_sec > 43200:
                            resolved_direction = "Entry"
                        elif direction in ("Auto", None, ""):
                            resolved_direction = "Exit" if last_dir == "Entry" else "Entry"
                        elif direction == last_dir:
                            resolved_direction = "Exit" if last_dir == "Entry" else "Entry"
                        else:
                            resolved_direction = direction or ("Exit" if last_dir == "Entry" else "Entry")
                    except Exception:
                        resolved_direction = direction or "Entry"
                else:
                    resolved_direction = "Entry" if direction in ("Auto", None, "", "Entry") else direction

                conn.execute(
                    "INSERT INTO raw_reader_logs (tag_scanned, system_response, direction, timestamp) VALUES (?, ?, ?, ?)",
                    (clean_tag, f"PROCESSED: {resolved_direction}", resolved_direction, pkt_now)
                )

                cursor = conn.execute("""INSERT INTO daily_logs
                    (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, scanned_tag, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mem_id, name, car, access_type, resolved_direction, "Gate-01", path_full, path_plate, clean_tag, pkt_now))
                conn.commit()
                new_id = cursor.lastrowid

                # Update in-memory latest log cache for ZERO-LAG KIOSK POLLING (< 0.05ms response)
                with config.CACHE_LOCK:
                    config.LATEST_LOG_CACHE = {
                        "id": new_id,
                        "mem_id": mem_id,
                        "name": name,
                        "vehicle_number": car,
                        "access_type": access_type,
                        "direction": resolved_direction,
                        "gate_no": "Gate-01",
                        "image_path": path_full,
                        "plate_image_path": path_plate,
                        "scanned_tag": clean_tag,
                        "timestamp": pkt_now,
                        "make_model": make_model,
                        "profile_pic": profile_pic
                    }

                return new_id

            else:
                name = "Unregistered Vehicle"
                mem_id = "AI-CAM"
                car = "UNKNOWN"
                access_type = "No RFID Detected"
                resolved_direction = direction or "Entry"

                cursor = conn.execute("""INSERT INTO daily_logs
                    (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, scanned_tag, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mem_id, name, car, access_type, resolved_direction, "Gate-01", path_full, path_plate, "NO_TAG", pkt_now))
                conn.commit()
                new_id = cursor.lastrowid
                return new_id
        finally:
            conn.close()

def attach_images_to_log(log_id: int, path_full: str, path_plate: str):
    if not log_id or (not path_full and not path_plate):
        return
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""UPDATE daily_logs SET
                    image_path = COALESCE(?, image_path),
                    plate_image_path = COALESCE(?, plate_image_path)
                    WHERE id=?""", (path_full, path_plate, log_id))
        finally:
            conn.close()

    # Keep in-memory cache synchronized with images
    with config.CACHE_LOCK:
        if config.LATEST_LOG_CACHE and config.LATEST_LOG_CACHE.get("id") == log_id:
            if path_full:
                config.LATEST_LOG_CACHE["image_path"] = path_full
            if path_plate:
                config.LATEST_LOG_CACHE["plate_image_path"] = path_plate

def process_camera_line_crossing(hikvision_image_path: str, forced_direction: str = None):
    if not hikvision_image_path or not os.path.exists(hikvision_image_path):
        return

    now = time.time()
    
    # 1. Real-time MD5 trigger de-duplication: prevents duplicate rapid bursts from Hikvision
    try:
        hasher = hashlib.md5()
        with open(hikvision_image_path, 'rb') as f:
            hasher.update(f.read())
        img_md5 = hasher.hexdigest()
    except Exception:
        img_md5 = None

    if img_md5:
        with config.CACHE_LOCK:
            for prev_md5, prev_time in list(config.RECENT_CAM_TRIGGERS):
                # Suppress identical image or burst triggers within 3 seconds
                if prev_md5 == img_md5 or (now - prev_time < 3.0):
                    try:
                        if os.path.exists(hikvision_image_path):
                            os.remove(hikvision_image_path)
                    except Exception:
                        pass
                    return
            config.RECENT_CAM_TRIGGERS.append((img_md5, now))

    stamp = int(now * 1000)
    target_dir = os.path.join(config.STATIC_DIR, "camera_audits")
    os.makedirs(target_dir, exist_ok=True)
    
    # Hikvision Overview Image (Whole Car Overview Shot)
    hik_target_path = os.path.join(target_dir, f"hikvision_full_{stamp}.jpg")
    try:
        shutil.copy(hikvision_image_path, hik_target_path)
    except Exception as exc:
        print(f"[CAM AUDIT HIKVISION COPY ERROR] {exc}")
        return

    # Clean up incoming temporary trigger file
    try:
        if os.path.exists(hikvision_image_path):
            os.remove(hikvision_image_path)
    except Exception:
        pass

    hik_rel_path = f"static/camera_audits/hikvision_full_{stamp}.jpg"
    direction = forced_direction or "Line Crossing"
    event_type = "Hikvision Line Crossing"

    new_audit_id = log_camera_audit_event(
        image_path=hik_rel_path,
        plate_image_path=None,
        direction=direction,
        event_type=event_type
    )
    config.FTP_EVENT_COUNT["count"] += 1

    if new_audit_id:
        from services.ocr_service import submit_image_to_ocr
        submit_image_to_ocr(new_audit_id, hik_target_path)

def deduplicate_camera_audit_logs() -> int:
    """
    Cleans up duplicate overview images in camera_audit_logs.
    If multiple triggers occurred within a tight burst window, keeps the primary record.
    Returns count of removed duplicate rows.
    """
    removed_count = 0
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT id, image_path, plate_image_path, timestamp FROM camera_audit_logs ORDER BY id ASC").fetchall()
            if not rows:
                return 0

            to_delete = []
            prev_row = None

            for r in rows:
                if prev_row is not None:
                    # Check if exact same image path or within 4 seconds of previous capture
                    is_same_path = (r['image_path'] == prev_row['image_path'])
                    is_time_dup = False
                    try:
                        t1 = datetime.strptime(r['timestamp'][:19], "%Y-%m-%d %H:%M:%S")
                        t2 = datetime.strptime(prev_row['timestamp'][:19], "%Y-%m-%d %H:%M:%S")
                        if abs((t1 - t2).total_seconds()) < 4.0:
                            is_time_dup = True
                    except Exception:
                        pass

                    if is_same_path or is_time_dup:
                        to_delete.append(r['id'])
                        continue

                prev_row = r

            if to_delete:
                with conn:
                    for del_id in to_delete:
                        conn.execute("DELETE FROM camera_audit_logs WHERE id=?", (del_id,))
                removed_count = len(to_delete)
        except Exception as exc:
            print(f"[DEDUPLICATE ERROR] {exc}")
        finally:
            conn.close()

    return removed_count

def process_master_trigger(hikvision_image_path: str, forced_direction: str = None):
    return process_camera_line_crossing(hikvision_image_path, forced_direction)
