import math
from datetime import datetime
from fastapi import APIRouter
import config
from database import get_db_connection

router = APIRouter(prefix="/api", tags=["Logs & Audit"])

def _fmt_duration(entry_ts, exit_ts):
    try:
        time_format = "%Y-%m-%d %H:%M:%S"
        dt_entry = datetime.strptime(str(entry_ts)[:19], time_format)
        dt_exit = datetime.strptime(str(exit_ts)[:19], time_format)
        diff_seconds = int((dt_exit - dt_entry).total_seconds())
        if diff_seconds < 0:
            return None
        hours = diff_seconds // 3600
        minutes = (diff_seconds % 3600) // 60
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
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
            for candidate_exit in exits:
                if candidate_exit['id'] in matched_exit_ids:
                    continue
                if _identity_key(candidate_exit) == key:
                    exit_event = candidate_exit
                    matched_exit_ids.add(candidate_exit['id'])
                    break

        is_unregistered = bool(
            entry_event and (
                'Unknown' in (entry_event.get('access_type') or '') or
                'No RFID' in (entry_event.get('access_type') or '') or
                'Unregistered' in (entry_event.get('name') or '')
            )
        )
        audit_status = "Exited" if exit_event else "Inside Facility"
        if is_unregistered and not exit_event:
            audit_status = "Alert / Inside"

        paired_audits.append({
            "entry": entry_event,
            "exit": exit_event,
            "duration": _fmt_duration(entry_event['timestamp'], exit_event['timestamp']) if exit_event else None,
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
async def get_camera_audit_logs(date: str = "", page: int = 1, limit: int = 24):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            target_date = date or pkt_today

            page = max(1, page)
            limit = min(max(4, limit), 100)
            offset = (page - 1) * limit

            if target_date == "all":
                total = conn.execute("SELECT COUNT(*) as c FROM camera_audit_logs").fetchone()['c']
                rows = conn.execute(
                    "SELECT * FROM camera_audit_logs ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) as c FROM camera_audit_logs WHERE date_str=?",
                    (target_date,)
                ).fetchone()['c']
                rows = conn.execute(
                    "SELECT * FROM camera_audit_logs WHERE date_str=? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (target_date, limit, offset)
                ).fetchall()

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

@router.post("/deduplicate-camera-audits")
@router.get("/deduplicate-camera-audits")
async def api_deduplicate_camera_audits():
    from services.access_service import deduplicate_camera_audit_logs
    removed = deduplicate_camera_audit_logs()
    return {"ok": True, "removed_duplicates": removed}
