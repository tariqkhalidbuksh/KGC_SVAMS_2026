import os
import time
import shutil
import hashlib
from datetime import datetime
import cv2
import config
from database import get_db_connection, get_setting

def detect_gate_station(gate_name: str, conn = None) -> str:
    """Classifies a reader or gate into 'gate01' (Rear Gate) or 'clubroad' (Main Gate)."""
    if not gate_name:
        return "gate01"
    g_lower = str(gate_name).lower().strip()
    if "club" in g_lower or "main" in g_lower:
        return "clubroad"
    try:
        if conn:
            row_e = conn.execute("SELECT config_value FROM settings WHERE config_key='clubroad_entry_reader_name'").fetchone()
            row_x = conn.execute("SELECT config_value FROM settings WHERE config_key='clubroad_exit_reader_name'").fetchone()
            club_entry = (row_e[0] if row_e and row_e[0] else "").lower().strip()
            club_exit = (row_x[0] if row_x and row_x[0] else "").lower().strip()
        else:
            club_entry = (get_setting("clubroad_entry_reader_name", "") or "").lower().strip()
            club_exit = (get_setting("clubroad_exit_reader_name", "") or "").lower().strip()
        if (club_entry and club_entry in g_lower) or (club_exit and club_exit in g_lower):
            return "clubroad"
    except Exception:
        pass
    return "gate01"

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

def classify_unregistered_tag(clean_tag: str) -> tuple[str, str, str, str, str]:
    """
    Intelligently classifies non-member RFID tags based on their silicon manufacturer & known deployment signatures.
    Returns: (name, mem_id, vehicle_number, access_type, tag_type)
    Always designates non-member vehicles as Unregistered, while preserving the tag category signature.
    """
    clean_upper = clean_tag.upper()
    name = "Unregistered Visitor"
    mem_id = "GUEST-LOG"
    vehicle_number = "UNREGISTERED"

    if clean_upper.startswith(("E2801105", "E2801114")):
        access_type = "Unregistered (NHA M-Tag)"
        tag_type = "NHA Motorway M-Tag"
    elif clean_upper.startswith("E280F336"):
        access_type = "Unregistered (Commercial Tag)"
        tag_type = "Third-Party Fleet Tag"
    elif clean_upper.startswith(("E2803821", "E2003412")):
        access_type = "Unregistered (Society Tag)"
        tag_type = "Society / Resident Tag"
    elif clean_upper.startswith(("E28068940", "E28068900", "E20047")):
        access_type = "Unregistered (Spare Club Tag)"
        tag_type = "Unassigned Gymkhana Tag"
    else:
        access_type = "RFID Unknown"
        tag_type = "Unregistered Visitor"
        vehicle_number = clean_tag

    return (name, mem_id, vehicle_number, access_type, tag_type)

def execute_access_decision(
    tag: str,
    direction: str = None,
    path_full: str = None,
    path_plate: str = None,
    is_ai_trigger: bool = False,
    bypass_cooldown: bool = False,
    gate_name: str = None
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

                # Rescues any registered member tags with human 23-char database typos
                if not member and len(clean_tag) == 24:
                    member = conn.execute(
                        "SELECT * FROM members WHERE LENGTH(E_tag_id)=23 AND ? LIKE (UPPER(E_tag_id) || '%') LIMIT 1",
                        (clean_tag,)
                    ).fetchone()

                if member:
                    raw_status = (member['Status'] or 'Active').strip()
                    name = member['Name']
                    mem_id = member['Mem_id']
                    car = member['Car_number']
                    make_model = member['Make_Model']
                    profile_pic = member['Profile_pic']
                    
                    status_upper = raw_status.upper()
                    if status_upper in ('VIP', 'COMMITTEE', 'PRESIDENT', 'SECRETARY', 'EXECUTIVE'):
                        access_type = "VIP Member"
                        resolved_status = "VIP"
                    elif status_upper in ('SUSPENDED', 'BARRED', 'WATCHLIST', 'BLOCKED'):
                        access_type = f"Security Alert ({raw_status})"
                        resolved_status = "Suspended"
                    else:
                        access_type = "RFID Verified"
                        resolved_status = "Active"
                else:
                    name, mem_id, car, access_type, tag_type = classify_unregistered_tag(clean_tag)
                    make_model = None
                    profile_pic = None
                    resolved_status = "Unregistered"

                member_loc = (member['Current_Location'] or '').strip() if member else ""

                last_tag_log = conn.execute(
                    "SELECT id, direction, gate_no, timestamp FROM daily_logs WHERE scanned_tag=? ORDER BY id DESC LIMIT 1",
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
                        
                        # Load dynamic cooldown window from settings (default: config.CROSS_READ_COOLDOWN)
                        cooldown_window = getattr(config, 'CROSS_READ_COOLDOWN', 45.0)
                        try:
                            setting_row = conn.execute("SELECT config_value FROM settings WHERE config_key='rfid_cooldown_seconds'").fetchone()
                            if setting_row and setting_row[0]:
                                cooldown_window = float(setting_row[0])
                        except Exception:
                            pass

                        # UNIVERSAL COOLDOWN:
                        # Suppresses duplicate scans, multi-reads, and cross-reader bounce between Entry & Exit
                        if not bypass_cooldown and elapsed_sec < cooldown_window:
                            return last_tag_log['id']

                        # SAME-DIRECTION LINGERING SUPPRESSION (90s):
                        # If vehicle was already logged in the same direction recently (e.g. car idling in front of entry barrier)
                        # drop duplicate scan to prevent multi-logging
                        if not bypass_cooldown and direction in ("Entry", "Exit") and direction == last_dir and elapsed_sec < max(cooldown_window, 90.0):
                            return last_tag_log['id']
                    except Exception:
                        pass

                # DIRECTION RESOLUTION:
                # 1. Dedicated Hardware Readers (Entry vs Exit) have fixed, definitive physical directions.
                # An Entry reader ONLY logs 'Entry'. An Exit reader ONLY logs 'Exit'.
                # Dedicated hardware readers must never be inverted to the opposite direction by stale location flags.
                if direction in ("Entry", "Exit"):
                    resolved_direction = direction
                else:
                    # 2. Virtual/Camera/Auto Triggers: resolve direction dynamically via strict state machine
                    active_loc = member_loc if member else ""
                    if not member:
                        unreg_record = conn.execute("SELECT Current_Location FROM unregistered_tags WHERE UPPER(tag)=?", (clean_tag,)).fetchone()
                        active_loc = (unreg_record['Current_Location'] if unreg_record and unreg_record['Current_Location'] else "").strip()
                    
                    if active_loc == "Inside":
                        resolved_direction = "Exit"
                    elif active_loc == "Outside":
                        resolved_direction = "Entry"
                    elif last_tag_log and last_tag_log['direction'] == "Entry":
                        resolved_direction = "Exit"
                    else:
                        resolved_direction = "Entry"

                new_loc = "Outside" if resolved_direction == "Exit" else "Inside"

                if member:
                    conn.execute(
                        "UPDATE members SET Current_Location=? WHERE UPPER(E_tag_id)=? OR (Mem_id=? AND UPPER(Car_number)=?)",
                        (new_loc, clean_tag, mem_id, car.upper())
                    )
                else:
                    # Track into unregistered_tags table with Current_Location and tag_type
                    conn.execute("""
                        INSERT INTO unregistered_tags (tag, first_seen, last_seen, direction, Current_Location, read_count, tag_type)
                        VALUES (?, ?, ?, ?, ?, 1, ?)
                        ON CONFLICT(tag) DO UPDATE SET
                            last_seen = excluded.last_seen,
                            direction = excluded.direction,
                            Current_Location = excluded.Current_Location,
                            read_count = unregistered_tags.read_count + 1,
                            tag_type = excluded.tag_type
                    """, (clean_tag, pkt_now, pkt_now, resolved_direction, new_loc, tag_type))

                conn.execute(
                    "INSERT INTO raw_reader_logs (tag_scanned, system_response, direction, timestamp) VALUES (?, ?, ?, ?)",
                    (clean_tag, f"PROCESSED: {resolved_direction}", resolved_direction, pkt_now)
                )

                if gate_name:
                    resolved_gate = gate_name
                else:
                    resolved_gate = "Gate-01 Entry Reader" if resolved_direction == "Entry" else "Gate-01 Exit Reader"

                cursor = conn.execute("""INSERT INTO daily_logs
                    (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, scanned_tag, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mem_id, name, car, access_type, resolved_direction, resolved_gate, path_full, path_plate, clean_tag, pkt_now))
                conn.commit()
                new_id = cursor.lastrowid

                # Update in-memory latest log cache for ZERO-LAG KIOSK POLLING (< 0.05ms response)
                station = detect_gate_station(resolved_gate, conn=conn)
                log_entry = {
                    "id": new_id,
                    "mem_id": mem_id,
                    "name": name,
                    "vehicle_number": car,
                    "access_type": access_type,
                    "direction": resolved_direction,
                    "gate_no": resolved_gate,
                    "gate_station": station,
                    "image_path": path_full,
                    "plate_image_path": path_plate,
                    "scanned_tag": clean_tag,
                    "timestamp": pkt_now,
                    "make_model": make_model,
                    "profile_pic": profile_pic,
                    "member_status": resolved_status,
                    "current_location": new_loc
                }
                with config.CACHE_LOCK:
                    config.LATEST_LOG_CACHE = log_entry
                    if hasattr(config, "LATEST_GATE_LOG_CACHE"):
                        config.LATEST_GATE_LOG_CACHE[station] = log_entry

                return new_id

            else:
                name = "Unregistered Vehicle"
                mem_id = "AI-CAM"
                car = "UNKNOWN"
                access_type = "No RFID Detected"
                resolved_direction = direction or "Entry"
                resolved_gate = "Gate-01 Entry Reader" if resolved_direction == "Entry" else "Gate-01 Exit Reader"

                cursor = conn.execute("""INSERT INTO daily_logs
                    (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, scanned_tag, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mem_id, name, car, access_type, resolved_direction, resolved_gate, path_full, path_plate, "NO_TAG", pkt_now))
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
        if hasattr(config, "LATEST_GATE_LOG_CACHE"):
            for g_station, g_data in config.LATEST_GATE_LOG_CACHE.items():
                if g_data and g_data.get("id") == log_id:
                    if path_full:
                        g_data["image_path"] = path_full
                    if path_plate:
                        g_data["plate_image_path"] = path_plate

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

    # Dahua Alignment: Trigger Dahua camera to capture current frame on-demand (no RAM buffer)
    dahua_rel_path = None
    try:
        from services.camera_service import grab_dahua_snapshot, is_valid_image
        dahua_frame, dahua_latency, dahua_err = grab_dahua_snapshot(timeout=1.5)
        if dahua_frame is not None and is_valid_image(dahua_frame):
            dahua_target_path = os.path.join(target_dir, f"dahua_anpr_{stamp}.jpg")
            cv2.imwrite(dahua_target_path, dahua_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            dahua_rel_path = f"static/camera_audits/dahua_anpr_{stamp}.jpg"
    except Exception as d_exc:
        print(f"[DAHUA LINE CROSS CAPTURE ERROR] {d_exc}")

    hik_rel_path = f"static/camera_audits/hikvision_full_{stamp}.jpg"
    direction = forced_direction or "Line Crossing"
    event_type = "Hikvision Line Crossing"

    new_audit_id = log_camera_audit_event(
        image_path=hik_rel_path,
        plate_image_path=dahua_rel_path,
        direction=direction,
        event_type=event_type
    )
    config.FTP_EVENT_COUNT["count"] += 1
    return new_audit_id

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
