import math
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Response, Request
import config
from database import get_db_connection

router = APIRouter(prefix="/api", tags=["Logs & Audit"])

def _fmt_duration(entry_ts, exit_ts):
    try:
        time_format = "%Y-%m-%d %H:%M:%S"
        dt_entry = datetime.strptime(str(entry_ts)[:19], time_format)
        dt_exit = datetime.strptime(str(exit_ts)[:19], time_format)
        diff_seconds = abs(int((dt_exit - dt_entry).total_seconds()))
        hours = diff_seconds // 3600
        minutes = (diff_seconds % 3600) // 60
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
    except Exception:
        return None

def _fmt_active_duration(entry_ts):
    try:
        time_format = "%Y-%m-%d %H:%M:%S"
        dt_entry = datetime.strptime(str(entry_ts)[:19], time_format)
        diff_seconds = max(0, int((datetime.now() - dt_entry).total_seconds()))
        hours = diff_seconds // 3600
        minutes = (diff_seconds % 3600) // 60
        dur_str = f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
        return f"{dur_str} (Active)"
    except Exception:
        return None

def _identity_key(log_row):
    if log_row['mem_id'] and log_row['mem_id'] not in ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED'):
        return ('member', log_row['mem_id'])
    if log_row.get('scanned_tag') and log_row['scanned_tag'] not in ('NO_TAG', ''):
        return ('tag', log_row['scanned_tag'])
    return None

@router.get("/latest-log")
async def get_latest_log(direction: str = None):
    # Zero-lag fast path: serve directly from memory cache (< 0.05ms) without acquiring DB_LOCK
    with config.CACHE_LOCK:
        cached = config.LATEST_LOG_CACHE
        if cached:
            if not direction or cached.get("direction", "").lower() == direction.lower():
                return cached

    # Fallback to database query if cache is empty
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            query = """SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                WHERE (d.scanned_tag != 'NO_TAG' AND d.scanned_tag IS NOT NULL AND d.scanned_tag != '')"""
            params = []
            if direction:
                query += " AND LOWER(d.direction) = LOWER(?)"
                params.append(direction)
            query += " ORDER BY d.id DESC LIMIT 1"

            row = conn.execute(query, params).fetchone()
            res = dict(row) if row else {}
            if res and not direction:
                with config.CACHE_LOCK:
                    config.LATEST_LOG_CACHE = res
            return res
        finally:
            conn.close()

@router.get("/recent-entries")
async def get_recent_entries(limit: int = 4):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                WHERE (d.scanned_tag != 'NO_TAG' AND d.scanned_tag IS NOT NULL AND d.scanned_tag != '')
                ORDER BY d.id DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

@router.get("/logs")
async def get_logs(limit: int = 100):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                ORDER BY d.id DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

@router.get("/audit")
async def get_audit(date: str = "", page: int = 1, limit: int = 25, search: str = "", status: str = "all"):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            target_date = date or pkt_today
            base_query = """SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number"""
            if target_date == "all":
                rows = conn.execute(base_query + " ORDER BY d.id ASC").fetchall()
            else:
                rows = conn.execute(
                    base_query + " WHERE date(d.timestamp)=? OR date(d.timestamp, '+5 hours')=? ORDER BY d.id ASC",
                    (target_date, target_date)
                ).fetchall()
            logs = [dict(r) for r in rows]
        finally:
            conn.close()

    entries = [l for l in logs if l['direction'] == 'Entry']
    exits = [l for l in logs if l['direction'] == 'Exit']
    matched_exit_ids = set()
    paired_audits = []

    for entry_event in entries:
        exit_event = None
        key = _identity_key(entry_event)
        if key:
            # 1. Search for candidate exit occurring AFTER the entry
            for candidate_exit in exits:
                if candidate_exit['id'] in matched_exit_ids:
                    continue
                if _identity_key(candidate_exit) == key:
                    if str(candidate_exit['timestamp']) >= str(entry_event['timestamp']):
                        exit_event = candidate_exit
                        matched_exit_ids.add(candidate_exit['id'])
                        break

            # 2. Fallback: if no exit found AFTER entry, but an unmatched exit exists with same key (e.g. inverted logs)
            if not exit_event:
                for candidate_exit in exits:
                    if candidate_exit['id'] in matched_exit_ids:
                        continue
                    if _identity_key(candidate_exit) == key:
                        exit_event = candidate_exit
                        matched_exit_ids.add(candidate_exit['id'])
                        break

        # If entry and exit timestamps are reversed, align chronologically so entry is earlier and exit is later
        actual_entry = entry_event
        actual_exit = exit_event
        if actual_entry and actual_exit:
            if str(actual_entry['timestamp']) > str(actual_exit['timestamp']):
                actual_entry, actual_exit = actual_exit, actual_entry

        is_unregistered = bool(
            (actual_entry or actual_exit) and (
                'Unknown' in ((actual_entry or actual_exit).get('access_type') or '') or
                'No RFID' in ((actual_entry or actual_exit).get('access_type') or '') or
                'Unregistered' in ((actual_entry or actual_exit).get('name') or '')
            )
        )
        audit_status = "Exited" if actual_exit else "Inside Facility"
        if is_unregistered and not actual_exit:
            audit_status = "Alert / Inside"

        if actual_exit:
            duration = _fmt_duration(actual_entry['timestamp'], actual_exit['timestamp'])
        elif actual_entry:
            duration = _fmt_active_duration(actual_entry['timestamp'])
        else:
            duration = None

        paired_audits.append({
            "entry": actual_entry,
            "exit": actual_exit,
            "duration": duration,
            "status": audit_status,
            "is_alert": is_unregistered
        })

    for orphan_exit in exits:
        if orphan_exit['id'] not in matched_exit_ids:
            is_unregistered = bool(
                'Unknown' in (orphan_exit.get('access_type') or '') or
                'No RFID' in (orphan_exit.get('access_type') or '') or
                'Unregistered' in (orphan_exit.get('name') or '')
            )
            paired_audits.append({
                "entry": None,
                "exit": orphan_exit,
                "duration": None,
                "status": "Exit Only",
                "is_alert": is_unregistered
            })

    total_transits = len(paired_audits)
    currently_inside = sum(1 for a in paired_audits if a['status'] in ("Inside Facility", "Alert / Inside"))
    exited_count = sum(1 for a in paired_audits if a['status'] == "Exited")
    alert_count = sum(1 for a in paired_audits if a['is_alert'])

    filtered = paired_audits
    search_term = search.strip().lower()
    if search_term:
        filtered = []
        for audit in paired_audits:
            record = audit['entry'] or audit['exit'] or {}
            combined_text = f"{record.get('name', '')} {record.get('mem_id', '')} {record.get('vehicle_number', '')} {record.get('scanned_tag', '')} {record.get('make_model', '')}".lower()
            if search_term in combined_text:
                filtered.append(audit)

    status_filter = status.strip().lower()
    if status_filter != "all":
        if status_filter == "inside":
            filtered = [a for a in filtered if a['status'] in ("Inside Facility", "Alert / Inside")]
        elif status_filter == "exited":
            filtered = [a for a in filtered if a['status'] == "Exited"]
        elif status_filter == "alert":
            filtered = [a for a in filtered if a['is_alert']]

    filtered.sort(key=lambda a: (a['entry'] or a['exit'])['id'], reverse=True)

    page = max(1, page)
    limit = min(max(5, limit), 200)
    offset = (page - 1) * limit
    total_filtered = len(filtered)
    total_pages = math.ceil(total_filtered / limit) if total_filtered > 0 else 1
    paginated_items = filtered[offset:offset + limit]

    return {
        "date": target_date,
        "total": total_transits,
        "total_filtered": total_filtered,
        "currently_inside": currently_inside,
        "exited_count": exited_count,
        "alert_count": alert_count,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "audits": paginated_items
    }

@router.get("/camera-audit-logs")
async def get_camera_audit_logs(date: str = "", page: int = 1, limit: int = 24, search: str = ""):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            target_date = date or pkt_today

            page = max(1, page)
            limit = min(max(4, limit), 100)
            offset = (page - 1) * limit

            where_clauses = []
            params = []

            if target_date != "all":
                where_clauses.append("date_str = ?")
                params.append(target_date)

            if search and search.strip():
                clean_s = search.strip()
                where_clauses.append("(detected_plate LIKE ? OR matched_name LIKE ? OR matched_mem_id LIKE ? OR image_path LIKE ?)")
                params.extend([f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%"])

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            total = conn.execute(f"SELECT COUNT(*) as c FROM camera_audit_logs {where_str}", params).fetchone()['c']
            
            query = f"SELECT * FROM camera_audit_logs {where_str} ORDER BY id DESC LIMIT ? OFFSET ?"
            query_params = list(params) + [limit, offset]
            rows = conn.execute(query, query_params).fetchall()

            return {
                "date": target_date,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": max(1, math.ceil(total / limit)),
                "logs": [dict(r) for r in rows]
            }
        finally:
            conn.close()

@router.post("/camera-audit/reprocess-ocr")
async def reprocess_ocr():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT id, image_path FROM camera_audit_logs WHERE detected_plate IS NULL OR detected_plate = '' ORDER BY id DESC LIMIT 50").fetchall()
            from services.ocr_service import submit_image_to_ocr
            count = 0
            for r in rows:
                submit_image_to_ocr(r['id'], r['image_path'])
                count += 1
            return {"ok": True, "queued": count}
        finally:
            conn.close()

@router.post("/camera-audit/{log_id}/extract-ocr")
async def extract_single_audit_ocr(log_id: int):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT id, image_path FROM camera_audit_logs WHERE id = ?", (log_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Audit log not found")
            image_path = row["image_path"]
        finally:
            conn.close()

    from services.ocr_service import process_single_ocr_job
    process_single_ocr_job(log_id, image_path)

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            updated = conn.execute("SELECT * FROM camera_audit_logs WHERE id = ?", (log_id,)).fetchone()
            return {"ok": True, "log": dict(updated) if updated else {}}
        finally:
            conn.close()

@router.post("/deduplicate-camera-audits")
@router.get("/deduplicate-camera-audits")
async def api_deduplicate_camera_audits():
    from services.access_service import deduplicate_camera_audit_logs
    removed = deduplicate_camera_audit_logs()
    return {"ok": True, "removed_duplicates": removed}

@router.get("/audit/{log_id}/pdf")
async def get_audit_log_pdf(log_id: int):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            target = conn.execute("""SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                WHERE d.id = ?""", (log_id,)).fetchone()
            if not target:
                raise HTTPException(404, f"Audit log #{log_id} not found")
            target_dict = dict(target)

            target_date = str(target_dict["timestamp"])[:10]
            same_day_rows = conn.execute("""SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                    d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
                    m.Make_Model as make_model, m.Profile_pic as profile_pic
                FROM daily_logs d LEFT JOIN members m ON d.mem_id = m.Mem_id AND d.vehicle_number = m.Car_number
                WHERE d.timestamp LIKE ? ORDER BY d.id ASC""", (f"{target_date}%",)).fetchall()
            logs = [dict(r) for r in same_day_rows]
        finally:
            conn.close()

    entry_rec = None
    exit_rec = None
    if target_dict["direction"] == "Entry":
        entry_rec = target_dict
        key = _identity_key(entry_rec)
        if key:
            for l in logs:
                if l["direction"] == "Exit" and _identity_key(l) == key:
                    exit_rec = l
                    break
    else:
        exit_rec = target_dict
        key = _identity_key(exit_rec)
        if key:
            for l in logs:
                if l["direction"] == "Entry" and _identity_key(l) == key:
                    entry_rec = l
                    break

    if entry_rec and exit_rec and str(entry_rec["timestamp"]) > str(exit_rec["timestamp"]):
        entry_rec, exit_rec = exit_rec, entry_rec

    is_unregistered = bool(
        (entry_rec or exit_rec) and (
            'Unknown' in ((entry_rec or exit_rec).get('access_type') or '') or
            'No RFID' in ((entry_rec or exit_rec).get('access_type') or '') or
            'Unregistered' in ((entry_rec or exit_rec).get('name') or '')
        )
    )
    audit_status = "Exited" if exit_rec else "Inside Facility"
    if is_unregistered and not exit_rec:
        audit_status = "Alert / Inside"

    duration = None
    if entry_rec and exit_rec:
        duration = _fmt_duration(entry_rec['timestamp'], exit_rec['timestamp'])
    elif entry_rec:
        duration = _fmt_active_duration(entry_rec['timestamp'])

    audit_payload = {
        "entry": entry_rec,
        "exit": exit_rec,
        "duration": duration,
        "status": audit_status,
        "is_alert": is_unregistered
    }

    try:
        from services.pdf_service import generate_audit_pdf
        pdf_bytes = generate_audit_pdf(audit_payload)
    except ModuleNotFoundError as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"ReportLab PDF library missing on server ({err}). Run 'pip install reportlab' to enable PDF generation."
        )
    except Exception as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate audit PDF: {str(err)}"
        )

    filename = f"Audit_Report_AUD_{str(log_id).zfill(6)}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )

@router.post("/audit/pdf")
async def post_audit_pdf(request: Request):
    body = await request.json()
    if not body:
        raise HTTPException(400, "Audit record data is required")
    try:
        from services.pdf_service import generate_audit_pdf
        pdf_bytes = generate_audit_pdf(body)
    except ModuleNotFoundError as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"ReportLab PDF library missing on server ({err}). Run 'pip install reportlab' to enable PDF generation."
        )
    except Exception as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate audit PDF: {str(err)}"
        )

    ref = ((body.get("entry") or body.get("exit") or {}).get("id")) or int(time.time())
    filename = f"Audit_Report_AUD_{str(ref).zfill(6)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )

