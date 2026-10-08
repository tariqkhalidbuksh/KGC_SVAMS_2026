import os
import math
import time
import io
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import FileResponse
from PIL import Image as PILImage
import config
from database import get_db_connection

router = APIRouter(prefix="/api", tags=["Logs & Audit"])

AUDIT_LOGS_BASE_QUERY = """SELECT d.id, 
        COALESCE(m_tag.Mem_id, m_car.Mem_id, m_id.Mem_id, d.mem_id) as mem_id,
        COALESCE(m_tag.Name, m_car.Name, m_id.Name, d.name) as name,
        COALESCE(m_tag.Car_number, m_car.Car_number, d.vehicle_number) as vehicle_number,
        d.access_type, d.direction, d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp,
        COALESCE(m_tag.Make_Model, m_car.Make_Model, m_id.Make_Model, '') as make_model,
        COALESCE(m_tag.Profile_pic, m_car.Profile_pic, m_id.Profile_pic, '') as profile_pic
    FROM daily_logs d
    LEFT JOIN members m_tag ON d.scanned_tag IS NOT NULL AND d.scanned_tag != 'NO_TAG' AND d.scanned_tag != '' AND d.scanned_tag = m_tag.E_tag_id
    LEFT JOIN members m_car ON m_tag.id IS NULL AND d.mem_id = m_car.Mem_id AND REPLACE(REPLACE(UPPER(d.vehicle_number), '-', ''), ' ', '') = REPLACE(REPLACE(UPPER(m_car.Car_number), '-', ''), ' ', '')
    LEFT JOIN (SELECT Mem_id, min(Name) as Name, min(Make_Model) as Make_Model, min(Profile_pic) as Profile_pic FROM members GROUP BY Mem_id) m_id 
        ON m_tag.id IS NULL AND m_car.id IS NULL AND d.mem_id = m_id.Mem_id AND d.mem_id NOT IN ('AI-CAM', 'GUEST-LOG', 'UNREGISTERED', '')
"""

def _parse_audit_date_criteria(date: str = "", start_date: str = "", end_date: str = ""):
    pkt_today = config.get_pkt_today()
    s_date = (start_date or "").strip()
    e_date = (end_date or "").strip()
    d_param = (date or "").strip()

    if s_date and e_date:
        if s_date > e_date:
            s_date, e_date = e_date, s_date
        return ("range", s_date, e_date, f"{s_date} to {e_date}")
    elif s_date:
        return ("range", s_date, s_date, s_date)
    elif e_date:
        return ("range", e_date, e_date, e_date)

    if not d_param:
        return ("single", pkt_today, pkt_today, pkt_today)
    if d_param.lower() in ("all", "all_time", "all-time"):
        return ("all", "", "", "All Time")
    if d_param.lower() == "today":
        return ("single", pkt_today, pkt_today, pkt_today)
    if d_param.lower() == "yesterday":
        yest = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return ("single", yest, yest, yest)
    if d_param.lower() in ("week", "last_7_days", "7days"):
        w_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        return ("range", w_start, pkt_today, f"{w_start} to {pkt_today}")
    if " to " in d_param or "," in d_param or "_" in d_param:
        delims = [" to ", ",", "_to_", "_"]
        for delim in delims:
            if delim in d_param:
                parts = d_param.split(delim, 1)
                p0, p1 = parts[0].strip(), parts[1].strip()
                if len(p0) == 10 and len(p1) == 10:
                    if p0 > p1: p0, p1 = p1, p0
                    return ("range", p0, p1, f"{p0} to {p1}")
    return ("single", d_param, d_param, d_param)

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

def format_duration_seconds(diff_seconds: int) -> str:
    if diff_seconds <= 0:
        return "< 1m"
    hours = diff_seconds // 3600
    minutes = (diff_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m" if minutes else f"{hours}h"
    if minutes > 0:
        return f"{minutes}m"
    return "< 1m"

def analyze_day_movements(movements):
    """
    Analyzes all movements for a vehicle/member on a specific date.
    Pairs Entries and Exits chronologically, calculates per-visit stay durations,
    and aggregates cumulative daily stay duration and visit counts.
    """
    if not movements:
        return {
            "trips": [],
            "visits_count": 0,
            "total_stay_seconds": 0,
            "total_stay_duration": "-- --",
            "first_entry_time": "--",
            "last_exit_time": "--",
            "is_currently_inside": False,
            "movements": []
        }

    sorted_movs = sorted(movements, key=lambda x: (str(x.get("timestamp", "")), x.get("id") or 0))
    trips = []
    current_entry = None
    total_stay_seconds = 0
    first_entry_time = None
    last_exit_time = None

    time_format = "%Y-%m-%d %H:%M:%S"

    for m in sorted_movs:
        d = (m.get("direction") or "").strip().lower()
        ts_str = str(m.get("timestamp", ""))
        
        try:
            ts = datetime.strptime(ts_str[:19], time_format)
        except Exception:
            continue

        if d == "entry":
            if not first_entry_time:
                first_entry_time = ts_str[11:19]
            current_entry = (m, ts)
            m["stay_duration"] = None
        elif d == "exit":
            last_exit_time = ts_str[11:19]
            if current_entry:
                entry_m, entry_ts = current_entry
                diff_sec = max(0, int((ts - entry_ts).total_seconds()))
                dur_str = format_duration_seconds(diff_sec)
                
                m["stay_duration"] = dur_str
                m["stay_seconds"] = diff_sec
                m["entry_ref_id"] = entry_m.get("id")
                m["entry_time"] = str(entry_m.get("timestamp", ""))[11:19]
                
                total_stay_seconds += diff_sec
                trips.append({
                    "entry_id": entry_m.get("id"),
                    "exit_id": m.get("id"),
                    "entry_time": str(entry_m.get("timestamp", ""))[11:19],
                    "exit_time": ts_str[11:19],
                    "stay_seconds": diff_sec,
                    "stay_duration": dur_str
                })
                current_entry = None
            else:
                m["stay_duration"] = None

    active_stay = False
    if current_entry:
        active_stay = True
        entry_m, entry_ts = current_entry
        active_sec = max(0, int((datetime.now() - entry_ts).total_seconds()))
        if str(entry_ts)[:10] == config.get_pkt_today():
            total_stay_seconds += active_sec

    visits_count = len(trips) + (1 if active_stay else 0)
    
    if total_stay_seconds > 0:
        total_stay_duration = format_duration_seconds(total_stay_seconds)
        if active_stay:
            total_stay_duration = f"{total_stay_duration} (Active)"
    else:
        total_stay_duration = "< 1m" if visits_count > 0 else "-- --"

    return {
        "trips": trips,
        "visits_count": visits_count,
        "total_stay_seconds": total_stay_seconds,
        "total_stay_duration": total_stay_duration,
        "first_entry_time": first_entry_time or "--",
        "last_exit_time": last_exit_time or "--",
        "is_currently_inside": active_stay,
        "movements": sorted_movs
    }

def _identity_key(log_row):
    mem = (log_row.get('mem_id') or '').strip().upper()
    if mem and mem not in ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', 'NONE', 'N/A', ''):
        return ('member', mem)
    tag = (log_row.get('scanned_tag') or '').strip().upper()
    if tag and tag not in ('NO_TAG', 'NONE', ''):
        return ('tag', tag)
    plate = (log_row.get('vehicle_number') or '').strip().upper()
    if plate and plate not in ('UNKNOWN', 'UNREGISTERED', 'NO PLATE', 'NO_PLATE', 'NONE', '-', 'N/A', ''):
        return ('plate', plate)
    return None

def _audit_sort_key(a):
    """
    Returns (latest_timestamp, latest_log_id) across entry and exit events.
    Ensures that paired audits and individual transits are sorted in true chronological
    order, keeping the most recently active vehicle events at the top of the table.
    """
    ent = a.get('entry') or {}
    ext = a.get('exit') or {}
    ent_ts = str(ent.get('timestamp') or '')
    ext_ts = str(ext.get('timestamp') or '')
    latest_ts = max(ent_ts, ext_ts)
    latest_id = max(ent.get('id') or 0, ext.get('id') or 0)
    return (latest_ts, latest_id)

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
async def get_audit(
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    camera: str = "all",
    page: int = 1,
    limit: int = 25,
    search: str = "",
    status: str = "all"
):
    mode, s_date, e_date, display_label = _parse_audit_date_criteria(date, start_date, end_date)
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            if mode == "all":
                rows = conn.execute(AUDIT_LOGS_BASE_QUERY + " ORDER BY d.id ASC").fetchall()
            elif mode == "range":
                rows = conn.execute(
                    AUDIT_LOGS_BASE_QUERY + " WHERE date(d.timestamp) >= ? AND date(d.timestamp) <= ? ORDER BY d.id ASC",
                    (s_date, e_date)
                ).fetchall()
            else:
                rows = conn.execute(
                    AUDIT_LOGS_BASE_QUERY + " WHERE date(d.timestamp) = ? ORDER BY d.id ASC",
                    (s_date,)
                ).fetchall()
            logs = [dict(r) for r in rows]
        finally:
            conn.close()

    paired_audits = _build_paired_audits(logs)
    filtered = list(paired_audits)

    # 1. Camera / Gate filter
    cam_filter = (camera or "").strip().lower()
    if cam_filter and cam_filter != "all":
        def _match_cam(audit_item):
            e = audit_item.get('entry') or {}
            x = audit_item.get('exit') or {}
            combined_cam = f"{e.get('gate_no', '')} {x.get('gate_no', '')} {e.get('direction', '')} {x.get('direction', '')} {e.get('image_path', '')} {x.get('image_path', '')} {e.get('access_type', '')} {x.get('access_type', '')}".lower()
            return cam_filter in combined_cam
        filtered = [a for a in filtered if _match_cam(a)]

    # 2. Search query filter
    search_term = (search or "").strip().lower()
    if search_term:
        def _match_search(audit_item):
            e = audit_item.get('entry') or {}
            x = audit_item.get('exit') or {}
            combined_text = f"{e.get('name', '')} {x.get('name', '')} {e.get('mem_id', '')} {x.get('mem_id', '')} {e.get('vehicle_number', '')} {x.get('vehicle_number', '')} {e.get('scanned_tag', '')} {x.get('scanned_tag', '')} {e.get('make_model', '')} {x.get('make_model', '')}".lower()
            return search_term in combined_text
        filtered = [a for a in filtered if _match_search(a)]

    # 3. Status filter (ensure both paired exits and exit-only transits are included in "exited")
    status_filter = (status or "").strip().lower()
    if status_filter and status_filter != "all":
        if status_filter == "inside":
            filtered = [a for a in filtered if a['status'] in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")]
        elif status_filter == "exited":
            filtered = [a for a in filtered if a['status'] in ("Exited", "Exit Only")]
        elif status_filter == "alert":
            filtered = [a for a in filtered if a['is_alert']]
        elif status_filter == "overstay":
            filtered = [a for a in filtered if a.get('is_overstay')]

    # Sort strictly by the most recent movement event (newest entry or exit timestamp first)
    filtered.sort(key=_audit_sort_key, reverse=True)

    # Filtered counts reflecting active tab criteria (preserves test contracts)
    total_filtered = len(filtered)
    currently_inside = sum(1 for a in filtered if a['status'] in ("Inside Facility", "Alert / Inside", "Overstay (>8h)"))
    exited_count = sum(1 for a in filtered if a['status'] in ("Exited", "Exit Only"))
    alert_count = sum(1 for a in filtered if a['is_alert'])
    overstay_count = sum(1 for a in filtered if a.get('is_overstay'))

    # Facility-wide summary metrics for selected date criteria
    fac_inside = sum(1 for a in paired_audits if a['status'] in ("Inside Facility", "Alert / Inside", "Overstay (>8h)"))
    fac_exited = sum(1 for a in paired_audits if a['status'] in ("Exited", "Exit Only"))
    fac_alerts = sum(1 for a in paired_audits if a['is_alert'])
    fac_overstay = sum(1 for a in paired_audits if a.get('is_overstay'))

    page = max(1, page)
    limit = min(max(5, limit), 200)
    offset = (page - 1) * limit
    total_pages = math.ceil(total_filtered / limit) if total_filtered > 0 else 1
    paginated_items = filtered[offset:offset + limit]

    return {
        "date": display_label,
        "total": total_filtered,
        "total_filtered": total_filtered,
        "total_unfiltered": len(paired_audits),
        "currently_inside": currently_inside,
        "exited_count": exited_count,
        "alert_count": alert_count,
        "overstay_count": overstay_count,
        "facility_total_transits": len(paired_audits),
        "facility_currently_inside": fac_inside,
        "facility_completed_visits": fac_exited,
        "facility_security_alerts": fac_alerts,
        "facility_overstay_warnings": fac_overstay,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "audits": paginated_items
    }

def _build_paired_audits(logs):
    entries = [l for l in logs if l['direction'] == 'Entry']
    exits = [l for l in logs if l['direction'] == 'Exit']
    matched_exit_ids = set()
    paired_audits = []

    for entry_event in entries:
        exit_event = None
        # 1. Match explicit manual exit reference token (pairs unregistered / unknown visitor entries)
        entry_ref_token = f"[Ref #{entry_event['id']}]"
        for candidate_exit in exits:
            if candidate_exit['id'] in matched_exit_ids:
                continue
            acc = candidate_exit.get('access_type') or ''
            if entry_ref_token in acc:
                exit_event = candidate_exit
                matched_exit_ids.add(candidate_exit['id'])
                break

        # 2. Match by identity key (member account, RFID EPC tag, or vehicle license plate)
        if not exit_event:
            key = _identity_key(entry_event)
            if key:
                for candidate_exit in exits:
                    if candidate_exit['id'] in matched_exit_ids:
                        continue
                    if _identity_key(candidate_exit) == key:
                        if str(candidate_exit['timestamp']) >= str(entry_event['timestamp']):
                            exit_event = candidate_exit
                            matched_exit_ids.add(candidate_exit['id'])
                            break

                if not exit_event:
                    for candidate_exit in exits:
                        if candidate_exit['id'] in matched_exit_ids:
                            continue
                        if _identity_key(candidate_exit) == key:
                            exit_event = candidate_exit
                            matched_exit_ids.add(candidate_exit['id'])
                            break

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

        is_overstay = False
        if not actual_exit and actual_entry:
            try:
                t_entry = datetime.strptime(str(actual_entry['timestamp'])[:19], "%Y-%m-%d %H:%M:%S")
                diff_h = (datetime.now() - t_entry).total_seconds() / 3600.0
                if diff_h >= 8.0:
                    is_overstay = True
            except Exception:
                pass

        audit_status = "Exited" if actual_exit else ("Overstay (>8h)" if is_overstay else "Inside Facility")
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
            "is_alert": is_unregistered,
            "is_overstay": is_overstay
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
                "is_alert": is_unregistered,
                "is_overstay": False
            })

    return paired_audits

@router.get("/audit/export")
async def export_audit(
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    camera: str = "all",
    format: str = "xlsx",
    search: str = "",
    status: str = "all"
):
    mode, s_date, e_date, display_label = _parse_audit_date_criteria(date, start_date, end_date)
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            if mode == "all":
                rows = conn.execute(AUDIT_LOGS_BASE_QUERY + " ORDER BY d.id ASC").fetchall()
            elif mode == "range":
                rows = conn.execute(
                    AUDIT_LOGS_BASE_QUERY + " WHERE date(d.timestamp) >= ? AND date(d.timestamp) <= ? ORDER BY d.id ASC",
                    (s_date, e_date)
                ).fetchall()
            else:
                rows = conn.execute(
                    AUDIT_LOGS_BASE_QUERY + " WHERE date(d.timestamp) = ? ORDER BY d.id ASC",
                    (s_date,)
                ).fetchall()
            logs = [dict(r) for r in rows]
        finally:
            conn.close()

    paired_audits = _build_paired_audits(logs)
    filtered = list(paired_audits)

    cam_filter = (camera or "").strip().lower()
    if cam_filter and cam_filter != "all":
        def _match_cam(audit_item):
            e = audit_item.get('entry') or {}
            x = audit_item.get('exit') or {}
            combined_cam = f"{e.get('gate_no', '')} {x.get('gate_no', '')} {e.get('direction', '')} {x.get('direction', '')} {e.get('image_path', '')} {x.get('image_path', '')} {e.get('access_type', '')} {x.get('access_type', '')}".lower()
            return cam_filter in combined_cam
        filtered = [a for a in filtered if _match_cam(a)]

    search_term = (search or "").strip().lower()
    if search_term:
        def _match_search(audit_item):
            e = audit_item.get('entry') or {}
            x = audit_item.get('exit') or {}
            combined_text = f"{e.get('name', '')} {x.get('name', '')} {e.get('mem_id', '')} {x.get('mem_id', '')} {e.get('vehicle_number', '')} {x.get('vehicle_number', '')} {e.get('scanned_tag', '')} {x.get('scanned_tag', '')} {e.get('make_model', '')} {x.get('make_model', '')}".lower()
            return search_term in combined_text
        filtered = [a for a in filtered if _match_search(a)]

    status_filter = (status or "").strip().lower()
    if status_filter and status_filter != "all":
        if status_filter == "inside":
            filtered = [a for a in filtered if a['status'] in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")]
        elif status_filter == "exited":
            filtered = [a for a in filtered if a['status'] in ("Exited", "Exit Only")]
        elif status_filter == "alert":
            filtered = [a for a in filtered if a['is_alert']]
        elif status_filter == "overstay":
            filtered = [a for a in filtered if a.get('is_overstay')]

    filtered.sort(key=_audit_sort_key, reverse=True)

    records = []
    for a in filtered:
        ent = a['entry'] or {}
        ext = a['exit'] or {}
        records.append({
            "Date": (ent.get('timestamp') or ext.get('timestamp') or '')[:10],
            "Member ID": ent.get('mem_id') or ext.get('mem_id') or 'GUEST',
            "Member Name": ent.get('name') or ext.get('name') or 'Visitor',
            "Vehicle Number": ent.get('vehicle_number') or ext.get('vehicle_number') or 'N/A',
            "Make / Model": ent.get('make_model') or ext.get('make_model') or 'N/A',
            "Entry Time": ent.get('timestamp') or 'N/A',
            "Exit Time": ext.get('timestamp') or 'N/A',
            "Duration": a.get('duration') or 'N/A',
            "Status": a.get('status') or 'N/A',
            "Access Type": ent.get('access_type') or ext.get('access_type') or 'RFID Verified',
            "Scanned RFID Tag": ent.get('scanned_tag') or ext.get('scanned_tag') or 'N/A',
            "Gate": ent.get('gate_no') or ext.get('gate_no') or 'Gate-01'
        })

    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=[
            "Date", "Member ID", "Member Name", "Vehicle Number", "Make / Model",
            "Entry Time", "Exit Time", "Duration", "Status", "Access Type", "Scanned RFID Tag", "Gate"
        ])

    safe_label = display_label.replace(' ', '_').replace(':', '-')
    export_fmt = (format or "xlsx").lower()
    if export_fmt == "csv":
        csv_data = df.to_csv(index=False)
        filename = f"KGC_Vehicle_Audit_{safe_label}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    else:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Vehicle Audit")
        out.seek(0)
        filename = f"KGC_Vehicle_Audit_{safe_label}.xlsx"
        return Response(
            content=out.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

@router.get("/camera-audit-logs")
async def get_camera_audit_logs(
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    direction: str = "all",
    page: int = 1,
    limit: int = 24,
    search: str = ""
):
    mode, s_date, e_date, display_label = _parse_audit_date_criteria(date, start_date, end_date)
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            page = max(1, page)
            limit = min(max(4, limit), 100)
            offset = (page - 1) * limit

            where_clauses = []
            params = []

            if mode == "range":
                where_clauses.append("((date_str >= ? AND date_str <= ?) OR (date(timestamp) >= ? AND date(timestamp) <= ?))")
                params.extend([s_date, e_date, s_date, e_date])
            elif mode == "single":
                where_clauses.append("(date_str = ? OR date(timestamp) = ?)")
                params.extend([s_date, s_date])
            # if mode == "all", no date constraint is added

            dir_filter = (direction or "").strip().lower()
            if dir_filter and dir_filter != "all":
                where_clauses.append("LOWER(direction) = LOWER(?)")
                params.append(direction.strip())

            if search and search.strip():
                clean_s = search.strip()
                where_clauses.append("(event_type LIKE ? OR direction LIKE ? OR image_path LIKE ? OR timestamp LIKE ? OR COALESCE(detected_plate, '') LIKE ? OR COALESCE(matched_name, '') LIKE ? OR COALESCE(matched_mem_id, '') LIKE ?)")
                params.extend([f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%", f"%{clean_s}%"])

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            total = conn.execute(f"SELECT COUNT(*) as c FROM camera_audit_logs {where_str}", params).fetchone()['c']
            
            query = f"SELECT * FROM camera_audit_logs {where_str} ORDER BY id DESC LIMIT ? OFFSET ?"
            query_params = list(params) + [limit, offset]
            rows = conn.execute(query, query_params).fetchall()

            return {
                "date": display_label,
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

THUMB_CACHE_DIR = os.path.join(config.STATIC_DIR, "cache", "thumbs")
os.makedirs(THUMB_CACHE_DIR, exist_ok=True)

@router.get("/thumbnail")
async def get_image_thumbnail(path: str, w: int = 440, q: int = 65):
    """
    High-speed downsampled thumbnail endpoint for Camera Audit grid cards.
    Reduces full-resolution image payloads by ~90% and disk-caches for sub-millisecond serving.
    """
    if not path or not path.strip():
        raise HTTPException(400, "Image path is required")

    clean_path = path.strip().replace("\\", "/").lstrip("/")
    if ".." in clean_path:
        raise HTTPException(400, "Invalid image path")

    candidates = [
        clean_path,
        os.path.join(config.STATIC_DIR, clean_path),
        os.path.join(config.STATIC_DIR, os.path.basename(clean_path))
    ]
    if os.path.isabs(path):
        candidates.insert(0, path)

    target_file = None
    for cand in candidates:
        if os.path.exists(cand) and os.path.isfile(cand):
            target_file = os.path.abspath(cand)
            break

    if not target_file:
        placeholder = os.path.join(config.STATIC_DIR, "img", "no-car.svg")
        if os.path.exists(placeholder):
            return FileResponse(placeholder, media_type="image/svg+xml")
        raise HTTPException(404, "Source image not found")

    w = max(80, min(w, 800))
    q = max(30, min(q, 95))

    try:
        mtime = os.path.getmtime(target_file)
        cache_key = hashlib.md5(f"{clean_path}_{mtime}_{w}_{q}".encode()).hexdigest()
        thumb_file = os.path.join(THUMB_CACHE_DIR, f"{cache_key}.jpg")

        if not os.path.exists(thumb_file):
            with PILImage.open(target_file) as im:
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                orig_w, orig_h = im.size
                if orig_w > w:
                    calc_h = int(orig_h * (w / float(orig_w)))
                    im.thumbnail((w, calc_h), PILImage.Resampling.BILINEAR)
                im.save(thumb_file, "JPEG", quality=q, optimize=True)

        return FileResponse(
            thumb_file,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800, immutable"}
        )
    except Exception:
        return FileResponse(target_file)

@router.get("/audit/{log_id}/pdf")
async def get_audit_log_pdf(log_id: int):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            target = conn.execute(AUDIT_LOGS_BASE_QUERY + " WHERE d.id = ?", (log_id,)).fetchone()
            if not target:
                raise HTTPException(404, f"Audit log #{log_id} not found")
            target_dict = dict(target)

            target_date = str(target_dict["timestamp"])[:10]
            same_day_rows = conn.execute(AUDIT_LOGS_BASE_QUERY + " WHERE d.timestamp LIKE ? ORDER BY d.id ASC", (f"{target_date}%",)).fetchall()
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

    # Fetch all movements for this vehicle on that date to embed in the report
    veh_num = (entry_rec or exit_rec or {}).get("vehicle_number")
    m_id = (entry_rec or exit_rec or {}).get("mem_id")
    daily_movements = []
    if veh_num or m_id:
        with config.DB_LOCK:
            conn = get_db_connection()
            try:
                where_clauses = ["d.timestamp LIKE ?"]
                params = [f"{target_date}%"]
                if veh_num and veh_num != "NO PLATE":
                    where_clauses.append("LOWER(d.vehicle_number) = LOWER(?)")
                    params.append(veh_num.strip())
                elif m_id:
                    where_clauses.append("d.mem_id = ?")
                    params.append(m_id.strip())
                rows = conn.execute(f"""
                    SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                           d.gate_no, d.image_path, d.scanned_tag, d.timestamp
                    FROM daily_logs d
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY d.id ASC
                """, params).fetchall()
                daily_movements = [dict(r) for r in rows]
            finally:
                conn.close()

    movement_analysis = analyze_day_movements(daily_movements or [])

    audit_payload = {
        "entry": entry_rec,
        "exit": exit_rec,
        "duration": duration,
        "single_trip_duration": duration,
        "total_stay_duration": movement_analysis["total_stay_duration"],
        "total_stay_seconds": movement_analysis["total_stay_seconds"],
        "visits_count": movement_analysis["visits_count"],
        "first_entry_time": movement_analysis["first_entry_time"],
        "last_exit_time": movement_analysis["last_exit_time"],
        "status": audit_status,
        "is_alert": is_unregistered,
        "daily_movements": movement_analysis["movements"]
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

@router.get("/audit/day-movements")
async def get_day_movements(vehicle_number: str = "", mem_id: str = "", date: str = ""):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            target_date = date or config.get_pkt_today()
            where_clauses = ["d.timestamp LIKE ?"]
            params = [f"{target_date}%"]

            if vehicle_number and vehicle_number.strip():
                where_clauses.append("LOWER(d.vehicle_number) = LOWER(?)")
                params.append(vehicle_number.strip())
            elif mem_id and mem_id.strip():
                where_clauses.append("d.mem_id = ?")
                params.append(mem_id.strip())

            where_str = f"WHERE {' AND '.join(where_clauses)}"
            rows = conn.execute(f"""
                SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                       d.gate_no, d.image_path, d.scanned_tag, d.timestamp
                FROM daily_logs d
                {where_str}
                ORDER BY d.id ASC
            """, params).fetchall()

            raw_movements = [dict(r) for r in rows]
            analysis = analyze_day_movements(raw_movements)

            return {
                "date": target_date,
                "vehicle_number": vehicle_number,
                "mem_id": mem_id,
                "total": len(raw_movements),
                "visits_count": analysis["visits_count"],
                "total_stay_duration": analysis["total_stay_duration"],
                "total_stay_seconds": analysis["total_stay_seconds"],
                "first_entry_time": analysis["first_entry_time"],
                "last_exit_time": analysis["last_exit_time"],
                "is_currently_inside": analysis["is_currently_inside"],
                "trips": analysis["trips"],
                "movements": analysis["movements"]
            }
        finally:
            conn.close()

@router.get("/audit/available-images")
async def get_available_audit_images(date: str = "", search: str = "", direction: str = "", limit: int = 0):
    """
    Returns available camera captures and gate images for visual evidence curation.
    When limit is 0 (default), all capture events for the target date are returned.
    """
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            target_date = date or config.get_pkt_today()
            where_clauses = []
            params = []

            if target_date != "all":
                where_clauses.append("(c.date_str = ? OR c.timestamp LIKE ?)")
                params.extend([target_date, f"{target_date}%"])

            if direction and direction.strip() and direction.strip().lower() != "all":
                where_clauses.append("c.direction LIKE ?")
                params.append(f"%{direction.strip()}%")

            if search and search.strip():
                clean_s = f"%{search.strip()}%"
                where_clauses.append("(c.direction LIKE ? OR c.event_type LIKE ? OR c.image_path LIKE ? OR c.timestamp LIKE ?)")
                params.extend([clean_s, clean_s, clean_s, clean_s])

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            cam_sql = f"""
                SELECT id, timestamp, direction, event_type, image_path, 'camera' as source
                FROM camera_audit_logs c
                {where_str}
                ORDER BY id DESC
            """
            if limit and limit > 0:
                cam_sql += " LIMIT ?"
                cam_rows = conn.execute(cam_sql, params + [limit]).fetchall()
            else:
                cam_rows = conn.execute(cam_sql, params).fetchall()

            results = [dict(r) for r in cam_rows]

            # Also fetch distinct daily_logs images from that day
            daily_where = ["image_path IS NOT NULL", "image_path != ''"]
            daily_params = []
            if target_date != "all":
                daily_where.append("timestamp LIKE ?")
                daily_params.append(f"{target_date}%")

            if direction and direction.strip() and direction.strip().lower() != "all":
                daily_where.append("direction LIKE ?")
                daily_params.append(f"%{direction.strip()}%")

            daily_where_str = f"WHERE {' AND '.join(daily_where)}"
            daily_sql = f"""
                SELECT id, timestamp, direction, access_type as event_type, image_path, 'gate' as source, vehicle_number
                FROM daily_logs
                {daily_where_str}
                ORDER BY id DESC
            """
            if limit and limit > 0:
                daily_sql += " LIMIT ?"
                daily_rows = conn.execute(daily_sql, daily_params + [limit]).fetchall()
            else:
                daily_rows = conn.execute(daily_sql, daily_params).fetchall()

            seen_paths = set()
            for r in results:
                p = (r.get("image_path") or "").strip().lstrip("/")
                if p:
                    seen_paths.add(p)

            for dr in daily_rows:
                dr_dict = dict(dr)
                raw_p = (dr_dict.get("image_path") or "").strip().lstrip("/")
                if raw_p and raw_p not in seen_paths:
                    seen_paths.add(raw_p)
                    results.append(dr_dict)

            results.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            final_images = results[:limit] if (limit and limit > 0) else results
            return {
                "date": target_date,
                "total": len(results),
                "images": final_images
            }
        finally:
            conn.close()

@router.post("/audit/custom-report/pdf")
async def post_custom_audit_pdf(request: Request):
    payload = await request.json()
    if not payload:
        raise HTTPException(400, "Report payload is required")

    raw_incident = payload.get("incident") or {}
    entry_rec = payload.get("entry") or (raw_incident.get("entry") if isinstance(raw_incident, dict) else None)
    exit_rec = payload.get("exit") or (raw_incident.get("exit") if isinstance(raw_incident, dict) else None)

    if not entry_rec and not exit_rec:
        if isinstance(raw_incident, dict) and ("vehicle_number" in raw_incident or "timestamp" in raw_incident):
            if (raw_incident.get("direction") or "").lower() == "exit":
                exit_rec = raw_incident
            else:
                entry_rec = raw_incident
        elif isinstance(payload, dict) and ("vehicle_number" in payload or "timestamp" in payload):
            entry_rec = payload

    thumb = entry_rec or exit_rec or {}
    v_num = thumb.get("vehicle_number") or ""
    m_id = thumb.get("mem_id") or ""
    tag = thumb.get("scanned_tag") or ""
    target_date = str(thumb.get("timestamp", ""))[:10] or config.get_pkt_today()
    log_id = payload.get("log_id") or thumb.get("id") or int(time.time())

    # Database lookup to ensure member data (name, mem_id, vehicle_number, make_model, profile_pic) is completely enriched
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            mem_row = None
            if tag and tag not in ("NO_TAG", ""):
                mem_row = conn.execute("SELECT * FROM members WHERE E_tag_id = ? LIMIT 1", (tag,)).fetchone()
            if not mem_row and m_id and m_id not in ("AI-CAM", "GUEST-LOG", "UNREGISTERED", ""):
                if v_num and v_num != "NO PLATE":
                    mem_row = conn.execute("SELECT * FROM members WHERE Mem_id = ? AND UPPER(REPLACE(Car_number, '-', '')) = UPPER(REPLACE(?, '-', '')) LIMIT 1", (m_id, v_num)).fetchone()
                if not mem_row:
                    mem_row = conn.execute("SELECT * FROM members WHERE Mem_id = ? LIMIT 1", (m_id,)).fetchone()
            if not mem_row and v_num and v_num != "NO PLATE":
                mem_row = conn.execute("SELECT * FROM members WHERE UPPER(REPLACE(Car_number, '-', '')) = UPPER(REPLACE(?, '-', '')) LIMIT 1", (v_num,)).fetchone()

            if mem_row:
                m_data = dict(mem_row)
                for rec in [entry_rec, exit_rec, thumb]:
                    if rec:
                        if not rec.get("name") or "Unregister" in rec.get("name", ""):
                            rec["name"] = m_data.get("Name") or rec.get("name")
                        if not rec.get("mem_id") or rec.get("mem_id") in ("GUEST-LOG", "AI-CAM", ""):
                            rec["mem_id"] = m_data.get("Mem_id") or rec.get("mem_id")
                        if not rec.get("make_model"):
                            rec["make_model"] = m_data.get("Make_Model") or ""
                        if not rec.get("profile_pic"):
                            rec["profile_pic"] = m_data.get("Profile_pic") or ""
                        if not rec.get("vehicle_number") or rec.get("vehicle_number") == "NO PLATE":
                            rec["vehicle_number"] = m_data.get("Car_number") or rec.get("vehicle_number")

                v_num = thumb.get("vehicle_number") or v_num
                m_id = thumb.get("mem_id") or m_id

            # Fetch daily movements if not provided
            daily_movements = payload.get("daily_movements")
            if daily_movements is None and (v_num or m_id):
                where_clauses = ["d.timestamp LIKE ?"]
                params = [f"{target_date}%"]
                if v_num and v_num != "NO PLATE":
                    where_clauses.append("LOWER(d.vehicle_number) = LOWER(?)")
                    params.append(v_num.strip())
                elif m_id:
                    where_clauses.append("d.mem_id = ?")
                    params.append(m_id.strip())
                rows = conn.execute(f"""
                    SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                           d.gate_no, d.image_path, d.scanned_tag, d.timestamp
                    FROM daily_logs d
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY d.id ASC
                """, params).fetchall()
                daily_movements = [dict(r) for r in rows]
        finally:
            conn.close()

    user_entry_img = payload.get("entry_image_path")
    user_exit_img = payload.get("exit_image_path")

    duration = payload.get("duration") or (raw_incident.get("duration") if isinstance(raw_incident, dict) else None)
    if not duration:
        if entry_rec and exit_rec and entry_rec.get("timestamp") and exit_rec.get("timestamp"):
            duration = _fmt_duration(entry_rec.get("timestamp"), exit_rec.get("timestamp"))
        elif entry_rec and entry_rec.get("timestamp"):
            duration = _fmt_active_duration(entry_rec.get("timestamp"))

    status_str = payload.get("status") or (raw_incident.get("status") if isinstance(raw_incident, dict) else None) or ("Exited" if exit_rec and entry_rec else "Inside Facility")

    movement_analysis = analyze_day_movements(daily_movements or [])

    total_stay_dur = payload.get("total_stay_duration") or movement_analysis["total_stay_duration"]
    visits_cnt = payload.get("visits_count") or movement_analysis["visits_count"]
    first_in = payload.get("first_entry_time") or movement_analysis["first_entry_time"]
    last_out = payload.get("last_exit_time") or movement_analysis["last_exit_time"]

    audit_payload = {
        "entry": entry_rec,
        "exit": exit_rec,
        "duration": duration,
        "single_trip_duration": payload.get("single_trip_duration") or duration,
        "total_stay_duration": total_stay_dur,
        "total_stay_seconds": movement_analysis["total_stay_seconds"],
        "visits_count": visits_cnt,
        "first_entry_time": first_in,
        "last_exit_time": last_out,
        "status": status_str,
        "entry_image_path": user_entry_img,
        "exit_image_path": user_exit_img,
        "daily_movements": movement_analysis["movements"],
        "investigator_notes": payload.get("notes") or payload.get("investigator_notes") or ""
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

    filename = f"Official_Investigation_Report_AUD_{str(log_id).zfill(6)}.pdf"
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
    if "incident" in body and isinstance(body["incident"], dict):
        inc = body["incident"]
        if "entry" in inc and not body.get("entry"): body["entry"] = inc.get("entry")
        if "exit" in inc and not body.get("exit"): body["exit"] = inc.get("exit")
        if "duration" in inc and not body.get("duration"): body["duration"] = inc.get("duration")
        if "status" in inc and not body.get("status"): body["status"] = inc.get("status")
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

@router.get("/thumbnail")
async def get_image_thumbnail(path: str, w: int = 440, q: int = 65):
    """
    Returns a high-performance compressed thumbnail of an image, with disk caching
    and HTTP cache headers. Used for camera audit cards to load ultra-fast without wasting bandwidth.
    """
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Missing path parameter")

    clean_path = path.strip().replace("\\", "/").lstrip("/")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.abspath(os.path.join(base_dir, clean_path))

    # Guard against directory traversal
    if not target_file.startswith(base_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(target_file):
        alt_file = os.path.abspath(os.path.join(base_dir, "static", clean_path))
        if os.path.isfile(alt_file) and alt_file.startswith(base_dir):
            target_file = alt_file
        else:
            raise HTTPException(status_code=404, detail="Image file not found")

    thumb_w = max(60, min(1200, int(w)))
    quality = max(20, min(95, int(q)))

    cache_dir = os.path.join(base_dir, "static", "cache", "thumbs")
    os.makedirs(cache_dir, exist_ok=True)

    try:
        mtime = int(os.path.getmtime(target_file))
        hash_seed = f"{target_file}_{mtime}_{thumb_w}_{quality}".encode("utf-8")
        cache_key = hashlib.md5(hash_seed).hexdigest()
        thumb_path = os.path.join(cache_dir, f"{cache_key}_{thumb_w}.jpg")

        if os.path.isfile(thumb_path) and os.path.getsize(thumb_path) > 0:
            return FileResponse(
                thumb_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=604800, immutable"}
            )

        with PILImage.open(target_file) as img:
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            if img.mode in ("RGBA", "LA", "P"):
                background = PILImage.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            orig_w, orig_h = img.size
            if orig_w > thumb_w:
                new_h = max(1, int(orig_h * (thumb_w / orig_w)))
                resample = getattr(PILImage, "Resampling", PILImage).BILINEAR
                img = img.resize((thumb_w, new_h), resample=resample)

            img.save(thumb_path, format="JPEG", quality=quality, optimize=True)

        return FileResponse(
            thumb_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800, immutable"}
        )
    except Exception:
        # Fallback to original image if compression fails
        return FileResponse(target_file)

@router.post("/audit/manual-exit")
async def post_manual_exit(request: Request):
    """
    Manually clear a vehicle as Exited when not detected by the RFID exit reader.
    Supports optional custom datetime and optional attached camera optical evidence.
    """
    body = await request.json()
    if not body:
        raise HTTPException(400, "Request payload is required")

    vehicle_number = (body.get("vehicle_number") or "").strip()
    mem_id = (body.get("mem_id") or "").strip()
    name = (body.get("name") or "").strip()
    scanned_tag = (body.get("scanned_tag") or "").strip()
    log_id = body.get("log_id")
    gate_no = (body.get("gate_no") or "Gate-01-Out (Manual)").strip()
    image_path = (body.get("image_path") or "").strip()
    custom_ts = (body.get("timestamp") or "").strip()
    notes = (body.get("notes") or "").strip()

    if not vehicle_number and not scanned_tag and not mem_id and not log_id:
        raise HTTPException(400, "Vehicle Number, RFID Tag, Member ID, or Entry Log ID is required")

    exit_timestamp = None
    if custom_ts:
        clean_ts = custom_ts.replace("T", " ")
        if len(clean_ts) == 16:
            clean_ts += ":00"
        try:
            datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S")
            exit_timestamp = clean_ts[:19]
        except Exception:
            exit_timestamp = None

    if not exit_timestamp:
        exit_timestamp = datetime.now(config.PKT_TZ).strftime("%Y-%m-%d %H:%M:%S")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                # If log_id is supplied, look up the target entry record for complete attribution
                if log_id:
                    l_row = conn.execute("SELECT id, mem_id, name, vehicle_number, scanned_tag FROM daily_logs WHERE id = ? LIMIT 1", (log_id,)).fetchone()
                    if l_row:
                        if not vehicle_number or vehicle_number in ("UNREGISTERED", "UNKNOWN", "NO PLATE", ""):
                            vehicle_number = l_row["vehicle_number"] or "UNREGISTERED"
                        if not name or "Unregistered" in name or name == "Visitor / Manual Clearance":
                            name = l_row["name"] or "Visitor / Unregistered"
                        if not mem_id:
                            mem_id = l_row["mem_id"] or "UNREGISTERED"
                        if not scanned_tag or scanned_tag == "NO_TAG":
                            scanned_tag = l_row["scanned_tag"] or "NO_TAG"

                if not name or not vehicle_number:
                    if scanned_tag and scanned_tag != "NO_TAG":
                        m_row = conn.execute("SELECT Mem_id, Name, Car_number FROM members WHERE E_tag_id = ? LIMIT 1", (scanned_tag,)).fetchone()
                        if m_row:
                            name = name or m_row["Name"]
                            vehicle_number = vehicle_number or m_row["Car_number"]
                            mem_id = mem_id or m_row["Mem_id"]
                    if not name and mem_id and mem_id not in ("GUEST-LOG", "AI-CAM", "UNREGISTERED"):
                        m_row = conn.execute("SELECT Mem_id, Name, Car_number, E_tag_id FROM members WHERE Mem_id = ? LIMIT 1", (mem_id,)).fetchone()
                        if m_row:
                            name = name or m_row["Name"]
                            vehicle_number = vehicle_number or m_row["Car_number"]
                            scanned_tag = scanned_tag or m_row["E_tag_id"]

                display_name = name or "Visitor / Manual Clearance"
                display_vehicle = vehicle_number or scanned_tag or "UNREGISTERED"
                ref_suffix = f" [Ref #{log_id}]" if log_id else ""
                access_type_label = f"Manual Exit{ref_suffix} ({notes})" if notes else f"Manual Exit{ref_suffix}"

                cur = conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, scanned_tag, timestamp)
                    VALUES (?, ?, ?, ?, 'Exit', ?, ?, ?, ?)
                """, (
                    mem_id or "MANUAL-EXIT",
                    display_name,
                    display_vehicle,
                    access_type_label,
                    gate_no,
                    image_path or None,
                    scanned_tag or "NO_TAG",
                    exit_timestamp
                ))
                new_exit_id = cur.lastrowid

                if mem_id and mem_id not in ("GUEST-LOG", "AI-CAM", "UNREGISTERED"):
                    conn.execute("UPDATE members SET Current_Location = 'Outside' WHERE Mem_id = ?", (mem_id,))
                elif scanned_tag and scanned_tag != "NO_TAG":
                    conn.execute("UPDATE members SET Current_Location = 'Outside' WHERE E_tag_id = ?", (scanned_tag,))

                config.LATEST_LOG_CACHE = None

                return {
                    "ok": True,
                    "exit_id": new_exit_id,
                    "vehicle_number": display_vehicle,
                    "name": display_name,
                    "timestamp": exit_timestamp,
                    "direction": "Exit",
                    "access_type": access_type_label,
                    "message": f"Vehicle {display_vehicle} successfully cleared and marked as Exited at {exit_timestamp}."
                }
        finally:
            conn.close()

@router.post("/audit/bulk-manual-exit")
async def post_bulk_manual_exit(request: Request):
    """
    One-click bulk clearance of all vehicles currently marked Inside Facility,
    strictly protecting vehicles that belong to the user-defined exception whitelist.
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    custom_ts = (body.get("timestamp") or "").strip()
    gate_no = (body.get("gate_no") or "Gate-01-Out (Bulk Exit)").strip()
    notes = (body.get("notes") or "Bulk Facility Clearance").strip()
    override_exceptions = body.get("exempt_identifiers")

    exit_timestamp = None
    if custom_ts:
        clean_ts = custom_ts.replace("T", " ")
        if len(clean_ts) == 16:
            clean_ts += ":00"
        try:
            datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S")
            exit_timestamp = clean_ts[:19]
        except Exception:
            exit_timestamp = None

    if not exit_timestamp:
        exit_timestamp = datetime.now(config.PKT_TZ).strftime("%Y-%m-%d %H:%M:%S")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                if override_exceptions is not None and isinstance(override_exceptions, list):
                    raw_exceptions = override_exceptions
                else:
                    s_row = conn.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1").fetchone()
                    raw_exceptions = []
                    if s_row and s_row["config_value"]:
                        import json
                        try:
                            raw_exceptions = json.loads(s_row["config_value"])
                        except Exception:
                            raw_exceptions = [x.strip() for x in s_row["config_value"].split(",") if x.strip()]

                exception_set = {str(x).strip().upper() for x in raw_exceptions if str(x).strip()}

                rows = conn.execute(AUDIT_LOGS_BASE_QUERY + " ORDER BY d.id ASC").fetchall()
                paired = _build_paired_audits([dict(r) for r in rows])

                inside_audits = [
                    p for p in paired 
                    if p.get("status") in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")
                ]

                exited_records = []
                exempted_records = []
                seen_keys = set()

                for item in inside_audits:
                    v = item.get("entry") or item.get("exit") or {}
                    plate = (v.get("vehicle_number") or "").strip().upper()
                    mem = (v.get("mem_id") or "").strip().upper()
                    tag = (v.get("scanned_tag") or "").strip().upper()
                    v_name = v.get("name") or "Club Vehicle"

                    key = plate or tag or mem
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)

                    is_exempt = False
                    if plate and plate in exception_set:
                        is_exempt = True
                    elif mem and mem in exception_set:
                        is_exempt = True
                    elif tag and tag in exception_set:
                        is_exempt = True

                    if is_exempt:
                        exempted_records.append({
                            "vehicle_number": v.get("vehicle_number") or plate,
                            "mem_id": v.get("mem_id") or mem,
                            "name": v_name
                        })
                        continue

                    entry_log_id = (item.get("entry") or {}).get("id")
                    ref_suffix = f" [Ref #{entry_log_id}]" if entry_log_id else ""
                    bulk_access_label = f"Bulk Manual Exit{ref_suffix} ({notes})" if notes else f"Bulk Manual Exit{ref_suffix}"

                    conn.execute("""
                        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                        VALUES (?, ?, ?, ?, 'Exit', ?, ?, ?)
                    """, (
                        v.get("mem_id") or "BULK-EXIT",
                        v_name,
                        v.get("vehicle_number") or plate or "UNREGISTERED",
                        bulk_access_label,
                        gate_no,
                        v.get("scanned_tag") or "NO_TAG",
                        exit_timestamp
                    ))

                    if mem and mem not in ("GUEST-LOG", "AI-CAM", "UNREGISTERED"):
                        conn.execute("UPDATE members SET Current_Location = 'Outside' WHERE Mem_id = ?", (v.get("mem_id"),))
                    elif tag and tag != "NO_TAG":
                        conn.execute("UPDATE members SET Current_Location = 'Outside' WHERE E_tag_id = ?", (v.get("scanned_tag"),))

                    exited_records.append({
                        "vehicle_number": v.get("vehicle_number") or plate,
                        "mem_id": v.get("mem_id") or mem,
                        "name": v_name
                    })

                config.LATEST_LOG_CACHE = None

                return {
                    "ok": True,
                    "exited_count": len(exited_records),
                    "exempted_count": len(exempted_records),
                    "timestamp": exit_timestamp,
                    "exited_vehicles": exited_records,
                    "exempted_vehicles": exempted_records,
                    "message": f"Bulk clearance complete: {len(exited_records)} vehicles marked Exited. {len(exempted_records)} vehicles retained inside per Exception Whitelist."
                }
        finally:
            conn.close()



