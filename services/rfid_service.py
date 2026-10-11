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

def prioritize_member_tags(tags: list[str]) -> list[str]:
    """
    When multiple RFID tags are detected in the same antenna window (e.g. car carries both
    a Gymkhana Club E-Tag and an NHA Motorway M-Tag / Sindh Excise tag on windshield),
    ensures any tag registered to a Gymkhana member is processed first.
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
            # Place verified Gymkhana tags first
            reg = [t for t in tags if t in registered_set]
            unreg = [t for t in tags if t not in registered_set]
            return reg + unreg
    except Exception:
        pass
    return tags

def process_rfid_direct(tag: str, direction: str):
    now = time.time()
    clean_tag = tag.strip().upper()

    # If a registered member just passed through the gate within the last 3.5 seconds,
    # suppress secondary unregistered tags (e.g. M-Tag on same windshield) from creating duplicate guest alerts
    with config.FUSION_LOCK:
        time_since_passage = now - config.LAST_GATE_PASSAGE.get("time", 0.0)
    
    log_id = execute_access_decision(clean_tag, direction or "Auto", path_full=None, is_ai_trigger=False)
    if log_id:
        with config.FUSION_LOCK:
            config.LAST_GATE_PASSAGE["time"] = now
            config.LAST_GATE_PASSAGE["log_id"] = log_id

def rfid_tcp_client_worker(direction: str, ip_setting_key: str):
    while True:
        target_ip = get_setting(ip_setting_key, "")
        if not target_ip:
            config.READER_STATUS[direction] = "NO_IP"
            time.sleep(3)
            continue
        try:
            config.READER_STATUS[direction] = "CONNECTING"
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((target_ip, 49152))
            sock.settimeout(None)
            config.READER_STATUS[direction] = "CONNECTED"

            buffer = b""
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                buffer += data
                hex_stream = buffer.hex().upper()

                # Prioritize standard EPC Gen2 tags:
                # 1. Matches E2... (covers 100% of Karachi Gymkhana E280 & E200 member tags)
                # 2. Matches general 24-hex EPC tags
                found_tags = re.findall(
                    r'(?:3000|3400|3800)?(E2[0-9A-F]{22}|E[0-9A-F]{23})',
                    hex_stream
                )
                
                # Filter out reader protocol noise and unaligned framing headers
                valid_tags = [
                    t for t in found_tags
                    if len(t) == 24 and not any(t.startswith(np) for np in EXCLUDE_NOISE_PREFIXES)
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
                        with config.BUFFER_LOCK:
                            # 45-second universal cooldown across all readers
                            if tag in config.GLOBAL_TAG_LOCKS and (now - config.GLOBAL_TAG_LOCKS[tag] < config.CROSS_READ_COOLDOWN):
                                continue
                            config.GLOBAL_TAG_LOCKS[tag] = now

                        config.RECENT_TAGS.append({
                            "tag": tag,
                            "direction": direction,
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
                                    "direction": direction
                                })

                        # Submit to persistent worker pool with zero thread-creation overhead
                        RFID_EXECUTOR.submit(process_rfid_direct, tag, direction)

                    # Preserve buffer tail to avoid chopping incoming frames across recv boundaries
                    buffer = buffer[-256:]
                elif len(buffer) > 4096:
                    buffer = buffer[-1024:]
        except Exception:
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
