import os
import re
import time
import queue
import threading
import cv2
import config
from database import get_db_connection

# Asynchronous producer-consumer queue for background OCR jobs
OCR_QUEUE = queue.Queue(maxsize=300)
_READER_LOCK = threading.Lock()
_EASYOCR_READER = None

def get_easyocr_reader():
    """Lazily initializes the EasyOCR reader in the worker thread."""
    global _EASYOCR_READER
    with _READER_LOCK:
        if _EASYOCR_READER is None:
            try:
                import easyocr
                # Disable GPU if not available, silence logs, prioritize English alphanumeric
                _EASYOCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
            except Exception as exc:
                print(f"[OCR INIT ERROR] Failed to initialize EasyOCR: {exc}")
                _EASYOCR_READER = False
        return _EASYOCR_READER if _EASYOCR_READER is not False else None

def normalize_plate(plate_str: str) -> str:
    """Normalizes plate string by stripping spaces, hyphens, and non-alphanumeric chars."""
    if not plate_str:
        return ""
    cleaned = re.sub(r'[^A-Z0-9]', '', str(plate_str).upper())
    return cleaned

def format_pakistan_plate(raw_plate: str) -> str:
    """Formats normalized alphanumeric text into a clean standard plate format (e.g. BHF-755)."""
    clean = normalize_plate(raw_plate)
    if not clean:
        return ""
    # Standard format: Letters followed by digits (e.g. ABC 123 -> ABC-123)
    match = re.match(r'^([A-Z]{2,4})(\d{2,4})$', clean)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    # 2 digits + letters + digits (e.g. 18-LEE-450)
    match2 = re.match(r'^(\d{2})([A-Z]{2,3})(\d{2,4})$', clean)
    if match2:
        return f"{match2.group(1)}-{match2.group(2)}-{match2.group(3)}"
    return clean

def match_plate_to_member(plate_str: str) -> dict:
    """
    Queries the SQLite members database to check if the detected car plate belongs to a registered member.
    Checks exact matches, normalized matches, and prefix-stripped variants.
    """
    clean = normalize_plate(plate_str)
    if not clean or len(clean) < 3:
        return None

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            # 1. Exact normalized match: remove hyphens, spaces in both
            row = conn.execute("""
                SELECT Mem_id, Name, Car_number, Make_Model, Profile_pic, Status
                FROM members
                WHERE UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) = ?
                LIMIT 1
            """, (clean,)).fetchone()
            if row:
                return dict(row)

            # 2. Province prefix handling (e.g. "SINDH BHF-755" or "KHI BHF-755")
            prefixes = ["SINDH", "KHI", "ICT", "ISB", "PUNJAB", "LHR", "BALOCHISTAN", "KPK"]
            for pfx in prefixes:
                if clean.startswith(pfx) and len(clean) > len(pfx) + 2:
                    sub = clean[len(pfx):]
                    row = conn.execute("""
                        SELECT Mem_id, Name, Car_number, Make_Model, Profile_pic, Status
                        FROM members
                        WHERE UPPER(REPLACE(REPLACE(Car_number, '-', ''), ' ', '')) = ?
                        LIMIT 1
                    """, (sub,)).fetchone()
                    if row:
                        return dict(row)

            return None
        finally:
            conn.close()

def extract_plate_from_image(image_path: str) -> str:
    """
    Uses OpenCV and EasyOCR to locate and read license plate text from the vehicle overview image.
    Optimized for high speed by cropping the bumper/lower vehicle zone first.
    """
    if not image_path:
        return None
    full_path = os.path.normpath(image_path)
    if not os.path.exists(full_path):
        if not full_path.startswith("static"):
            alt = os.path.join(config.STATIC_DIR, image_path)
            if os.path.exists(alt):
                full_path = alt
            else:
                return None
        else:
            return None

    try:
        frame = cv2.imread(full_path)
        if frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]

        # Vehicle plates in gate passage cameras are virtually always located in the lower central section
        # Bounding box crop: y: 30% to 98%, x: 10% to 90%
        crop_y1 = int(h * 0.30)
        crop_y2 = int(h * 0.98)
        crop_x1 = int(w * 0.10)
        crop_x2 = int(w * 0.90)
        cropped = frame[crop_y1:crop_y2, crop_x1:crop_x2]

        # Resize if oversized for sub-100ms CPU inference speed
        ch, cw = cropped.shape[:2]
        if cw > 1200:
            scale = 1200.0 / cw
            cropped = cv2.resize(cropped, (1200, int(ch * scale)), interpolation=cv2.INTER_AREA)

        reader = get_easyocr_reader()
        if not reader:
            return None

        # Run OCR with alphanumeric allowlist (filters out random punctuation)
        results = reader.readtext(
            cropped,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ',
            detail=1,
            paragraph=False
        )

        candidates = []
        for bbox, text, conf in results:
            clean_txt = normalize_plate(text)
            # Pakistani plates generally have between 4 and 8 alphanumeric characters
            if 3 <= len(clean_txt) <= 10 and conf > 0.25:
                # Check if it contains at least one digit and at least one letter (typical car plate)
                has_digit = any(c.isdigit() for c in clean_txt)
                has_alpha = any(c.isalpha() for c in clean_txt)
                score = conf + (0.3 if (has_digit and has_alpha) else 0.0)
                candidates.append((score, text.strip()))

        if candidates:
            # Pick candidate with highest combined confidence
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_raw = candidates[0][1]
            return format_pakistan_plate(best_raw)

        return None
    except Exception as exc:
        print(f"[OCR PROCESS ERROR] Failed to process {image_path}: {exc}")
        return None

def process_single_ocr_job(audit_id: int, image_path: str):
    """Processes a single OCR task and enriches the database record."""
    try:
        detected = extract_plate_from_image(image_path)
        ocr_status = "NO_PLATE_DETECTED"
        matched_mem_id = None
        matched_name = None
        matched_make = None
        matched_pfp = None

        if detected:
            member = match_plate_to_member(detected)
            if member:
                ocr_status = "MATCHED"
                matched_mem_id = member.get("Mem_id")
                matched_name = member.get("Name")
                matched_make = member.get("Make_Model")
                matched_pfp = member.get("Profile_pic")
                print(f"[OCR ENRICHED] Audit #{audit_id}: Plate '{detected}' MATCHED to Member '{matched_name}' (#{matched_mem_id})")
            else:
                ocr_status = "UNREGISTERED"
                matched_mem_id = "AI-GUEST"
                matched_name = "Guest / Unregistered Vehicle"
                print(f"[OCR ENRICHED] Audit #{audit_id}: Plate '{detected}' recorded as UNREGISTERED VISITOR")
        else:
            detected = None

        with config.DB_LOCK:
            conn = get_db_connection()
            try:
                with conn:
                    conn.execute("""
                        UPDATE camera_audit_logs SET
                            detected_plate = ?,
                            ocr_status = ?,
                            matched_mem_id = ?,
                            matched_name = ?,
                            matched_make_model = ?,
                            matched_profile_pic = ?
                        WHERE id = ?
                    """, (detected, ocr_status, matched_mem_id, matched_name, matched_make, matched_pfp, audit_id))
            finally:
                conn.close()

    except Exception as exc:
        print(f"[OCR JOB ERROR] Audit #{audit_id}: {exc}")

def ocr_worker_daemon():
    """Background daemon thread worker that continuously processes the OCR queue sequentially."""
    print("[OCR WORKER] AI License Plate OCR & Member Matching daemon initialized.")
    while True:
        try:
            audit_id, image_path = OCR_QUEUE.get()
            if audit_id is None:
                break
            process_single_ocr_job(audit_id, image_path)
            OCR_QUEUE.task_done()
            time.sleep(0.05)  # Yield CPU to ensure zero interference with gate threads
        except Exception as exc:
            print(f"[OCR WORKER EXCEPTION] {exc}")
            time.sleep(0.5)

def submit_image_to_ocr(audit_id: int, image_path: str):
    """
    Submits a captured vehicle image to the background OCR queue.
    Completely non-blocking (< 0.05ms) so camera event responses remain instantaneous.
    """
    if not audit_id or not image_path:
        return
    try:
        OCR_QUEUE.put_nowait((audit_id, image_path))
    except queue.Full:
        print(f"[OCR WARNING] Queue full. Dropping image {image_path} for OCR.")
