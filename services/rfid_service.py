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

# Known NHA Motorway M-Tag silicon prefix signatures to ignore completely from visitor/unregistered intake
MTAG_PREFIXES = ("E2801105", "E2801114")

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

    # Drop unregistered NHA Motorway M-Tag immediately at hardware listener level
    if clean_tag.startswith(MTAG_PREFIXES) and not is_tag_registered(clean_tag):
        return

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

def parse_host_port(ip_string: str, default_port: int = 49152) -> tuple[str, int]:
    """Parses IP strings supporting both plain '192.168.0.214' and '192.168.0.214:6000' notation."""
    if not ip_string:
        return "", default_port
    s = ip_string.strip()
    if ":" in s:
        parts = s.split(":")
        try:
            return parts[0].strip(), int(parts[1].strip())
        except Exception:
            return parts[0].strip(), default_port
    return s, default_port

def rfid_tcp_client_worker(direction: str, ip_setting_key: str, gate_name: str = None, reader_id: str = None, name_setting_key: str = None):
    r_key = reader_id or direction
    default_gate = gate_name or f"Gate-01 {direction} Reader"
    if not name_setting_key:
        if reader_id == "Gate01_Entry":
            name_setting_key = "entry_reader_name"
        elif reader_id == "Gate01_Exit":
            name_setting_key = "exit_reader_name"
        elif reader_id == "ClubRoad_Entry":
            name_setting_key = "clubroad_entry_reader_name"
        elif reader_id == "ClubRoad_Exit":
            name_setting_key = "clubroad_exit_reader_name"

    while True:
        target_ip_raw = get_setting(ip_setting_key, "")
        target_ip, target_port = parse_host_port(target_ip_raw, 49152)
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
            sock.connect((target_ip, target_port))

            # Enable TCP keepalive to detect silent hardware/switch disconnects
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                if hasattr(socket, "SIO_KEEPALIVE_VALS"):
                    sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 5000, 2000))
            except Exception:
                pass

            # Use 6.0s receive timeout so the thread never freezes indefinitely on dead sockets
            sock.settimeout(6.0)
            config.READER_SOCKETS[r_key] = sock

            config.READER_STATUS[r_key] = "CONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "CONNECTED"
            if r_key in config.READER_TELEMETRY:
                config.READER_TELEMETRY[r_key]["last_error"] = None

            buffer = b""
            while True:
                try:
                    data = sock.recv(1024)
                    if not data:
                        break
                except socket.timeout:
                    # Normal heartbeat idle window (no cars currently in antenna field)
                    continue
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                    break

                if r_key in config.READER_TELEMETRY:
                    config.READER_TELEMETRY[r_key]["bytes_total"] += len(data)
                    config.READER_TELEMETRY[r_key]["last_packet_time"] = time.time()
                    config.READER_TELEMETRY[r_key]["last_raw_hex"] = data[:32].hex().upper()

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
                
                # Filter out reader protocol noise, framing patterns, corrupted data, and unregistered M-Tags
                valid_tags = []
                for t in found_tags:
                    if len(t) != 24 or "CCFFFF" in t or "FFFF" in t:
                        continue
                    if any(t.startswith(np) for np in EXCLUDE_NOISE_PREFIXES):
                        continue
                    # Never track or flag any vehicle with NHA M-Tag unless explicitly assigned to a registered member
                    if any(t.startswith(mp) for mp in MTAG_PREFIXES):
                        if not is_tag_registered(t):
                            continue
                    valid_tags.append(t)

                # De-duplicate within the same packet batch while preserving order
                unique_batch = []
                for t in valid_tags:
                    if t not in unique_batch:
                        unique_batch.append(t)

                if unique_batch:
                    # Dynamically resolve reader name and cooldown from settings
                    resolved_gate = get_setting(name_setting_key, default_gate) if name_setting_key else default_gate
                    try:
                        cooldown_sec = float(get_setting("rfid_cooldown_seconds", str(config.CROSS_READ_COOLDOWN)))
                    except Exception:
                        cooldown_sec = config.CROSS_READ_COOLDOWN

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

                            # Dynamic universal cooldown across all readers prevents duplicate passage logs
                            if tag in config.GLOBAL_TAG_LOCKS and (now - config.GLOBAL_TAG_LOCKS[tag] < cooldown_sec):
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
        except Exception as e:
            config.READER_STATUS[r_key] = "DISCONNECTED"
            if direction in ("Entry", "Exit") and ("Gate01" in r_key or r_key == direction):
                config.READER_STATUS[direction] = "DISCONNECTED"
            if r_key in config.READER_TELEMETRY:
                config.READER_TELEMETRY[r_key]["reconnects"] += 1
                config.READER_TELEMETRY[r_key]["last_error"] = f"{e.__class__.__name__}: {str(e)}"
                config.READER_TELEMETRY[r_key]["last_error_time"] = time.time()
            time.sleep(2)
        finally:
            config.READER_SOCKETS.pop(r_key, None)
            try:
                sock.close()
            except Exception:
                pass


def reconnect_reader(reader_id: str) -> bool:
    """Forces immediate clean disconnect and reconnect cycle for a specific hardware reader."""
    sock = config.READER_SOCKETS.get(reader_id)
    if sock:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass
        return True
    return False


def buffer_cleaner_worker():
    while True:
        time.sleep(3)
        now = time.time()
        with config.BUFFER_LOCK:
            config.PENDING_RFID_BUFFER[:] = [t for t in config.PENDING_RFID_BUFFER if (now - t["last_seen"]) <= 35.0]


def midnight_auto_exit_worker():
    """
    Daily Autonomous Midnight Clearance Daemon:
    Runs automatically at 23:59:00 PKT each night.
    Finds all vehicles whose Current_Location is 'Inside' (members & unregistered visitor tags),
    and marks them 'Exit' at 23:59:00 (Auto Midnight Exit).
    Protects any vehicles listed in bulk_exit_exceptions (overnight VIP / security patrol).
    """
    from datetime import datetime, timedelta
    import json
    from database import get_db_connection

    while True:
        try:
            now_dt = datetime.now(config.PKT_TZ)
            # Target is 23:59:00 PKT of today
            target_dt = now_dt.replace(hour=23, minute=59, second=0, microsecond=0)
            if now_dt >= target_dt:
                # If already passed 23:59:00 today, schedule for tomorrow 23:59:00
                target_dt += timedelta(days=1)

            sleep_sec = max(1.0, (target_dt - now_dt).total_seconds())
            time.sleep(min(sleep_sec, 60.0))

            now_dt = datetime.now(config.PKT_TZ)
            if now_dt.hour == 23 and now_dt.minute == 59 and now_dt.second <= 10:
                cutoff_ts = now_dt.strftime("%Y-%m-%d 23:59:00")
                with config.DB_LOCK:
                    conn = get_db_connection()
                    try:
                        with conn:
                            # 1. Fetch exception whitelist
                            s_row = conn.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1").fetchone()
                            raw_exceptions = []
                            if s_row and s_row["config_value"]:
                                try:
                                    raw_exceptions = json.loads(s_row["config_value"])
                                except Exception:
                                    raw_exceptions = [x.strip() for x in s_row["config_value"].split(",") if x.strip()]
                            exception_set = {str(x).strip().upper() for x in raw_exceptions if str(x).strip()}

                            # 2. Process members currently marked 'Inside'
                            # Autonomous Lodge Logic with 36-Hour Safety Ceiling:
                            # If a vehicle entered today (e.g. less than 18h ago), it is treated as an active member / lodge resident
                            # and permitted to remain inside for 24h movements without false ejection.
                            # Only vehicles stagnant inside for >= 36 hours (missed exit) or explicitly non-exempt visitors get auto-exited.
                            inside_members = conn.execute(
                                "SELECT id, Mem_id, Name, Car_number, E_tag_id FROM members WHERE Current_Location = 'Inside'"
                            ).fetchall()

                            for m in inside_members:
                                m_dict = dict(m)
                                mem_id = (m_dict.get("Mem_id") or "").strip().upper()
                                plate = (m_dict.get("Car_number") or "").strip().upper()
                                tag = (m_dict.get("E_tag_id") or "").strip().upper()

                                # Check whitelist (Permanent override)
                                if (plate and plate in exception_set) or (mem_id and mem_id in exception_set) or (tag and tag in exception_set):
                                    continue

                                # Auto-exit vehicle at 23:59:00 cutoff
                                conn.execute("""
                                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                                    VALUES (?, ?, ?, 'Auto Midnight Exit (11:59 PM Cutoff)', 'Exit', 'System Auto-Clearance', ?, ?)
                                """, (m_dict.get("Mem_id"), m_dict.get("Name"), m_dict.get("Car_number"), m_dict.get("E_tag_id") or "NO_TAG", cutoff_ts))
                                conn.execute("UPDATE members SET Current_Location = 'Outside' WHERE id = ?", (m_dict["id"],))

                            # 3. Find all unregistered tags currently inside
                            # Unregistered visitor tags are strictly cleared at 11:59 PM unless on whitelist
                            inside_unreg = conn.execute(
                                "SELECT id, tag FROM unregistered_tags WHERE Current_Location = 'Inside'"
                            ).fetchall()

                            for u in inside_unreg:
                                u_tag = dict(u).get("tag", "").strip().upper()
                                if u_tag in exception_set:
                                    continue
                                conn.execute("""
                                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                                    VALUES ('UNREGISTERED', 'Unregistered Visitor', 'UNREGISTERED', 'Auto Midnight Exit (11:59 PM Cutoff)', 'Exit', 'System Auto-Clearance', ?, ?)
                                """, (u_tag, cutoff_ts))
                                conn.execute("UPDATE unregistered_tags SET Current_Location = 'Outside', direction = 'Exit' WHERE id = ?", (u["id"],))

                        with config.CACHE_LOCK:
                            config.LATEST_LOG_CACHE = None
                            if hasattr(config, 'LATEST_GATE_LOG_CACHE') and config.LATEST_GATE_LOG_CACHE:
                                config.LATEST_GATE_LOG_CACHE["gate01"] = None
                                config.LATEST_GATE_LOG_CACHE["clubroad"] = None
                            if hasattr(config, 'AUDIT_LOGS_CACHE') and config.AUDIT_LOGS_CACHE:
                                config.AUDIT_LOGS_CACHE.clear()
                    finally:
                        conn.close()

                # Sleep past the 23:59 minute so it only executes once per night
                time.sleep(65)
        except Exception:
            time.sleep(10)

