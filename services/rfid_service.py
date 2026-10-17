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

def parse_reader_target(target_setting: str, default_port: int = 49152) -> tuple[str, int]:
    target = (target_setting or "").strip()
    if not target:
        return "", default_port
    if ":" in target:
        parts = target.split(":", 1)
        host = parts[0].strip()
        try:
            port = int(parts[1].strip())
        except ValueError:
            port = default_port
        return host, port
    return target, default_port

def rfid_tcp_client_worker(direction: str, ip_setting_key: str, gate_name: str = None, reader_id: str = None):
    r_key = reader_id or direction
    resolved_gate = gate_name or f"Gate-01 {direction} Reader"

    while True:
        target_setting = get_setting(ip_setting_key, "").strip()
        host, port = parse_reader_target(target_setting, 49152)
        if not host:
            config.READER_STATUS[r_key] = "NO_IP"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "NO_IP"
            time.sleep(3)
            continue

        current_target = target_setting
        sock = None
        try:
            config.READER_STATUS[r_key] = "CONNECTING"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "CONNECTING"

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Connected successfully to {resolved_gate} at {host}:{port}")

            config.READER_STATUS[r_key] = "CONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "CONNECTED"

            buffer = b""
            while True:
                try:
                    sock.settimeout(2.0)
                    data = sock.recv(1024)
                    if not data:
                        print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Remote reader closed connection ({host}:{port})")
                        break
                except socket.timeout:
                    # Dynamically check if IP/port setting changed in Settings page without server restart
                    latest_setting = get_setting(ip_setting_key, "").strip()
                    if latest_setting != current_target:
                        print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Setting changed from '{current_target}' to '{latest_setting}'. Reconnecting...")
                        break
                    continue

                buffer += data
                hex_stream = buffer.hex().upper()
                print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Recv {len(data)}B from {resolved_gate}: {data.hex().upper()[:48]}...")

                # Match standard EPC Gen2 tags:
                # 1. Matches E2... (covers 100% of Karachi Gymkhana E280, E200, E201 member tags)
                # 2. Matches general 24-hex EPC Gen2 tags starting with E
                # 3. Matches 23-hex tags (e.g. database-stored registered members)
                matches = list(re.finditer(
                    r'(?:3000|3400|3800)?(E2[0-9A-F]{22}|E[0-9A-F]{23}|E2[0-9A-F]{21})',
                    hex_stream
                ))
                found_tags = [m.group(1) for m in matches]

                # Frame parser for active UHF reader response frames (0xEE, 0x01, 0x89, 0x18, 0xAA)
                if not found_tags and len(buffer) >= 14:
                    for i in range(len(buffer) - 13):
                        flen = buffer[i]
                        if 12 <= flen <= 36 and (i + flen + 1) <= len(buffer):
                            cmd = buffer[i + 2]
                            if cmd in (0xEE, 0x01, 0x89, 0x18, 0xAA):
                                cand = buffer[i + 4 : i + flen - 1].hex().upper()
                                for cm in re.finditer(r'(E2[0-9A-F]{22}|E[0-9A-F]{23}|E2[0-9A-F]{21})', cand):
                                    tv = cm.group(1)
                                    if tv not in found_tags:
                                        found_tags.append(tv)
                
                # Filter out reader protocol noise, framing patterns, and corrupted data
                valid_tags = [
                    t for t in found_tags
                    if len(t) in (23, 24)
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
                    print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Tag(s) recognized on {resolved_gate}: {prioritized_tags}")
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
        except Exception as exc:
            config.READER_STATUS[r_key] = "DISCONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "DISCONNECTED"
            print(f"[{time.strftime('%H:%M:%S')}] [{r_key}] Connection error on {resolved_gate} ({host}:{port}): {exc}")
            time.sleep(3)
        finally:
            if sock:
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
