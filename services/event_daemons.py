import os
import time
import threading
import tempfile
import email
from email.header import decode_header
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import config
from services.access_service import process_camera_line_crossing

class HikvisionFTPHandler(FTPHandler):
    def on_file_received(self, file):
        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
            fname = os.path.basename(file).lower()
            forced_dir = "Line Crossing"
            if any(k in fname for k in ["rule2", "rule02", "rule_2", "b-a", "b_a", "_exit_"]):
                forced_dir = "Exit"
            elif any(k in fname for k in ["rule1", "rule01", "rule_1", "a-b", "a_b", "_entry_"]):
                forced_dir = "Entry"
            threading.Thread(target=process_camera_line_crossing, args=(file, forced_dir), daemon=True).start()

def start_ftp_server():
    authorizer = DummyAuthorizer()
    authorizer.add_user("admin", "admin123", config.FTP_UPLOAD_DIR, perm="elradfmw")
    handler = HikvisionFTPHandler
    handler.authorizer = authorizer
    handler.passive_ports = range(2122, 2130)
    server = FTPServer(("0.0.0.0", 2121), handler)
    server.serve_forever()

def folder_watcher_worker():
    while True:
        try:
            if os.path.exists(config.FTP_UPLOAD_DIR):
                for fname in os.listdir(config.FTP_UPLOAD_DIR):
                    if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                        fpath = os.path.join(config.FTP_UPLOAD_DIR, fname)
                        if not os.path.isfile(fpath):
                            continue
                        try:
                            if os.path.getsize(fpath) == 0:
                                continue
                        except Exception:
                            continue

                        # Atomically claim the file to avoid duplicate thread triggers while writing/processing
                        proc_path = fpath + ".processing"
                        try:
                            os.rename(fpath, proc_path)
                        except OSError:
                            # File is currently being written or locked by camera; retry on next tick
                            continue

                        forced_dir = "Line Crossing"
                        lower_name = fname.lower()
                        if any(k in lower_name for k in ["exit", "rule2", "b-a"]):
                            forced_dir = "Exit"
                        elif any(k in lower_name for k in ["entry", "rule1", "a-b"]):
                            forced_dir = "Entry"

                        # Dispatch immediately in a background daemon thread
                        threading.Thread(target=process_camera_line_crossing, args=(proc_path, forced_dir), daemon=True).start()
        except Exception:
            pass
        time.sleep(0.08)

class HikvisionEmailHandler:
    async def handle_DATA(self, server, session, envelope):
        msg = email.message_from_bytes(envelope.content)
        raw_subject = msg.get('Subject', '')
        decoded_list = decode_header(raw_subject)
        subject = ""
        for part, encoding in decoded_list:
            if isinstance(part, bytes):
                try:
                    subject += part.decode(encoding or 'utf-8')
                except Exception:
                    subject += str(part)
            else:
                subject += str(part)

        body_text = ""
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    body_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except Exception:
                    pass

        forced_direction = "Line Crossing"
        s_lower = subject.lower()
        b_lower = body_text.lower()

        if any(k in s_lower for k in ["rule 2", "rule2", "rule02", "b-a", "b->a", "b to a", "leaving"]) or \
           any(k in b_lower for k in ["rule 2", "rule2", "rule02", "b-a", "b->a", "b to a", "leaving"]):
            forced_direction = "Exit"
        elif any(k in s_lower for k in ["rule 1", "rule1", "rule01", "a-b", "a->b", "a to b", "entering"]) or \
             any(k in b_lower for k in ["rule 1", "rule1", "rule01", "a-b", "a->b", "a to b", "entering"]):
            forced_direction = "Entry"

        img_data = None
        for part in msg.walk():
            if part.get_content_maintype() == 'image':
                img_data = part.get_payload(decode=True)
                break

        if img_data:
            fd, temp_path = tempfile.mkstemp(suffix='.jpg', dir=config.FTP_UPLOAD_DIR)
            with os.fdopen(fd, 'wb') as f:
                f.write(img_data)
            threading.Thread(target=process_camera_line_crossing, args=(temp_path, forced_direction), daemon=True).start()

        return '250 Message accepted for delivery'

def start_smtp_server():
    from aiosmtpd.controller import Controller
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        handler = HikvisionEmailHandler()
        controller = Controller(handler, hostname='', port=2525)
        controller.start()
        while True:
            time.sleep(3600)
    except Exception:
        pass
