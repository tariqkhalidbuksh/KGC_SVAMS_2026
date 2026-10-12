import time
import socket
import re
from concurrent.futures import ThreadPoolExecutor
import config
from database import get_setting
from services.access_service import execute_access_decision

# Persistent thread pool for zero-overhead background tag processing
RFID_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rfid_worker")

# Protocol framing bytes and reader noise that should never be treated as vehicle EPC tags
EXCLUDE_NOISE_PREFIXES = (
    "EF55", "ECCF", "EC4C", "EB0C", "E5DC", "E53C", "EE01", "E1CC", "E09C", "E32C", "E388", "E00000000"
)

def is_tag_registered(tag: str) -> bool:
    """Fast check whether an EPC tag belongs to a registered club member."""
    clean_tag = tag.strip().upper()
    try:
        from database import get_db_connection
        with config.DB_LOCK:
            conn = get_db_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM members WHERE UPPER(E_tag_id) = ? LIMIT 1",
                    (clean_tag,)
                ).fetchone()
                if not row and len(clean_tag) == 24:
                    row = conn.execute(
                        "SELECT 1 FROM members WHERE LENGTH(E_tag_id)=23 AND ? LIKE (UPPER(E_tag_id) || '%') LIMIT 1",
                        (clean_tag,)
                    ).fetchone()
                return bool(row)
            finally:
                conn.close()
    except Exception:
        return False

def prioritize_member_tags(tags: list[str]) -> list[str]:
    """
    When multiple RFID tags are detected in the same antenna window (e.g. car carries both
    a Gymkhana Club E-Tag and an NHA Motorway M-Tag / Sindh Excise tag on windshield):
    If ANY tag belongs to a verified Gymkhana member, ONLY return the member tag(s).
    Secondary windshield tags (such as NHA M-Tag) are completely dropped so they never
    create phantom guest logs.
    """
    if len(tags) <= 1:
        return tags
    try:
        from database import get_db_connection
        with config.DB_LOCK:
            conn = get_db_connection()
            try:
                placeholders = ','.join(['?'] * len(tags))
                rows = conn.execute(
                    f"SELECT UPPER(E_tag_id) FROM members WHERE UPPER(E_tag_id) IN ({placeholders})",
                    [t.upper() for t in tags]
                ).fetchall()
                registered_set = {r[0] for r in rows}
            finally:
                conn.close()

        if registered_set:
            # If a verified Gymkhana member tag is detected in this burst,
            # ONLY return the member tag(s). Completely drop secondary windshield tags!
            return [t for t in tags if t in registered_set]
    except Exception:
        pass
    return tags

def process_rfid_direct(tag: str, direction: str, gate_name: str = None):
    now = time.time()
    clean_tag = tag.strip().upper()

    with config.FUSION_LOCK:
        time_since_passage = now - config.LAST_GATE_PASSAGE.get("time", 0.0)

    # If a registered member just passed through the gate within the last 4.0 seconds:
    # Any secondary transponder on that vehicle (such as an NHA M-Tag or Sindh Excise)
    # arriving in a subsequent packet burst must NOT trigger a duplicate GUEST-LOG!
    if time_since_passage < 4.0:
        if not is_tag_registered(clean_tag):
            return  # Suppress secondary windshield transponder on passing member car

    log_id = execute_access_decision(clean_tag, direction or "Auto", path_full=None, is_ai_trigger=False, gate_name=gate_name)
    if log_id:
        with config.FUSION_LOCK:
            config.LAST_GATE_PASSAGE["time"] = now
            config.LAST_GATE_PASSAGE["log_id"] = log_id

def rfid_tcp_client_worker(direction: str, ip_setting_key: str, gate_name: str = None, reader_id: str = None):
    r_key = reader_id or direction
    resolved_gate = gate_name or f"Gate-01 {direction} Reader"

    while True:
        target_ip = get_setting(ip_setting_key, "")
        if not target_ip:
            config.READER_STATUS[r_key] = "NO_IP"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "NO_IP"
            time.sleep(3)
            continue
        try:
            config.READER_STATUS[r_key] = "CONNECTING"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "CONNECTING"

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((target_ip, 49152))
            sock.settimeout(None)

            config.READER_STATUS[r_key] = "CONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "CONNECTED"

            buffer = b""
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                buffer += data
                hex_stream = buffer.hex().upper()

                # Strictly match standard EPC Gen2 tags:
                # 1. 100% of legitimate Karachi Gymkhana tags start with E2 (E280... and E200...)
                # 2. Rejects reader protocol framing bytes (EE..., EC..., E3..., CCFFFF...)
                matches = list(re.finditer(
                    r'(?:3000|3400|3800)?(E2[0-9A-F]{22})',
                    hex_stream
                ))
                found_tags = [m.group(1) for m in matches]
                
                # Filter out reader protocol noise, framing patterns, and corrupted data
                valid_tags = [
                    t for t in found_tags
                    if len(t) == 24 
                    and "CCFFFF" not in t 
                    and "FFFF" not in t
                    and not any(t.startswith(np) for np in EXCLUDE_NOISE_PREFIXES)
                ]

                # De-duplicate within the same packet batch while preserving order
                unique_batch = []
                for t in valid_tags:
                    if t not in unique_batch:
                        unique_batch.append(t)

                if unique_batch:
                    # Dual-tag resolution: prioritize registered Gymkhana member tags
                    prioritized_tags = prioritize_member_tags(unique_batch)
                    now = time.time()
                    for tag in prioritized_tags:
                        config.RECENT_TAGS.append({
                            "tag": tag,
                            "direction": direction,
                            "gate": resolved_gate,
                            "time": time.strftime("%H:%M:%S"),
                            "epoch": now
                        })

                        if config.ENROLL_MODE["active"]:
                            continue

                        with config.BUFFER_LOCK:
                            existing = next((item for item in config.PENDING_RFID_BUFFER if item["tag"] == tag), None)
                            if existing:
                                existing["last_seen"] = now
                            else:
                                config.PENDING_RFID_BUFFER.append({
                                    "tag": tag,
                                    "first_seen": now,
                                    "last_seen": now,
                                    "direction": direction,
                                    "gate": resolved_gate
                                })

                            # 45-second universal cooldown across all readers prevents duplicate passage logs
                            if tag in config.GLOBAL_TAG_LOCKS and (now - config.GLOBAL_TAG_LOCKS[tag] < config.CROSS_READ_COOLDOWN):
                                continue
                            config.GLOBAL_TAG_LOCKS[tag] = now

                        # Submit to persistent worker pool with zero thread-creation overhead
                        RFID_EXECUTOR.submit(process_rfid_direct, tag, direction, resolved_gate)

                # CRITICAL BUFFER MANAGEMENT:
                # Discard all bytes up to the end of the last matched tag so processed tags
                # are NEVER re-parsed from memory. Retain only incomplete trailing bytes.
                if matches:
                    consumed_bytes = (matches[-1].end() + 1) // 2
                    buffer = buffer[consumed_bytes:]
                elif len(buffer) > 512:
                    buffer = buffer[-64:]
        except Exception:
            config.READER_STATUS[r_key] = "DISCONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "DISCONNECTED"
            time.sleep(3)
        finally:
            try:
                sock.close()
            except Exception:
                pass


def buffer_cleaner_worker():
    while True:
        time.sleep(3)
        now = time.time()
        with config.BUFFER_LOCK:
            config.PENDING_RFID_BUFFER[:] = [t for t in config.PENDING_RFID_BUFFER if (now - t["last_seen"]) <= 35.0]
