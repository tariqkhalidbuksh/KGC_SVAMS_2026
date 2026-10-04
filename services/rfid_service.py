import time
import socket
import re
from concurrent.futures import ThreadPoolExecutor
import config
from database import get_setting
from services.access_service import execute_access_decision

# Persistent thread pool for zero-overhead background tag processing
RFID_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rfid_worker")

def process_rfid_direct(tag: str, direction: str):
    now = time.time()
    clean_tag = tag.strip().upper()
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

                # Strictly match standard EPC Gen2 tags starting with 'E' (20 to 24 hex characters)
                # Eliminates non-EPC transponders and built-in vehicle noise starting with '30...'
                found_tags = re.findall(r'(?:3000)?(E[0-9A-F]{23}|E[0-9A-F]{21}|E2[0-9A-F]{22}|E0[0-9A-F]{22})', hex_stream)
                valid_tags = [t for t in found_tags if t.startswith('E') and len(t) >= 20 and not t.startswith('E00000000')]

                if valid_tags:
                    now = time.time()
                    for tag in valid_tags:
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
                    buffer = b""
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
