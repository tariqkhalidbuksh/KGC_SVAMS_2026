import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
import config
from database import get_db_connection
from routers.logs import analyze_day_movements

router = APIRouter(prefix="/api/etag", tags=["E-TAG Audit"])

@router.get("/recent-tags")
async def get_recent_scanned_tags(limit: int = Query(25, ge=1, le=100)):
    """
    Returns the most recently scanned EPC tags across the facility
    along with their member associations and scan counts for quick 1-click auditing.
    """
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""
                SELECT d.scanned_tag, 
                       MAX(d.timestamp) as last_seen, 
                       COUNT(*) as total_scans,
                       COALESCE(m.Name, MAX(d.name)) as name,
                       COALESCE(m.Car_number, MAX(d.vehicle_number)) as vehicle_number,
                       COALESCE(m.Mem_id, MAX(d.mem_id)) as mem_id,
                       COALESCE(m.Make_Model, '') as make_model,
                       COALESCE(m.Profile_pic, '') as profile_pic,
                       COALESCE(m.Status, 'Unregistered') as status,
                       MAX(d.gate_no) as last_gate
                FROM daily_logs d
                LEFT JOIN members m ON d.scanned_tag = m.E_tag_id
                WHERE d.scanned_tag IS NOT NULL AND d.scanned_tag != 'NO_TAG' AND d.scanned_tag != ''
                GROUP BY d.scanned_tag
                ORDER BY last_seen DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return {
                "total": len(rows),
                "tags": [dict(r) for r in rows]
            }
        finally:
            conn.close()

@router.get("/audit")
async def get_etag_audit(tag_id: str = Query(..., description="RFID E-TAG EPC identifier")):
    """
    Comprehensive E-TAG Activity Audit endpoint.
    Retrieves full chronological detection history, associated member and vehicle particulars,
    multi-day detection counts, reader station distributions, and per-day stay breakdowns.
    """
    clean_tag = (tag_id or "").strip()
    if not clean_tag:
        raise HTTPException(status_code=400, detail="Tag ID (EPC) cannot be empty")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            # 1. Look up member assigned to this E_tag_id
            mem_row = conn.execute(
                "SELECT * FROM members WHERE UPPER(TRIM(E_tag_id)) = UPPER(TRIM(?)) LIMIT 1",
                (clean_tag,)
            ).fetchone()

            # 2. Query all daily logs that scanned this tag
            log_rows = conn.execute("""
                SELECT d.id, d.mem_id, d.name, d.vehicle_number, d.access_type, d.direction,
                       d.gate_no, d.image_path, d.plate_image_path, d.scanned_tag, d.timestamp
                FROM daily_logs d
                WHERE UPPER(TRIM(d.scanned_tag)) = UPPER(TRIM(?))
                ORDER BY d.timestamp DESC, d.id DESC
            """, (clean_tag,)).fetchall()
            logs = [dict(r) for r in log_rows]

            # 3. If member not matched by E_tag_id, try to infer from logs
            if not mem_row and logs:
                for l in logs:
                    m_id = l.get("mem_id")
                    if m_id and m_id not in ("GUEST-LOG", "AI-CAM", "UNREGISTERED", ""):
                        mem_candidate = conn.execute(
                            "SELECT * FROM members WHERE Mem_id = ? LIMIT 1",
                            (m_id,)
                        ).fetchone()
                        if mem_candidate:
                            mem_row = mem_candidate
                            break

            # Format Member Profile Data
            if mem_row:
                m_dict = dict(mem_row)
                is_registered = True
                member_info = {
                    "is_registered": True,
                    "mem_id": m_dict.get("Mem_id") or "N/A",
                    "name": m_dict.get("Name") or "Club Member",
                    "vehicle_number": m_dict.get("Car_number") or (logs[0].get("vehicle_number") if logs else "N/A"),
                    "make_model": m_dict.get("Make_Model") or "Not Specified",
                    "profile_pic": m_dict.get("Profile_pic") or "",
                    "status": m_dict.get("Status") or "Active",
                    "phone": m_dict.get("Phone") or "",
                    "e_tag_id": m_dict.get("E_tag_id") or clean_tag
                }
            else:
                is_registered = False
                fallback_name = logs[0].get("name") if logs else "Unregistered Tag"
                fallback_plate = logs[0].get("vehicle_number") if logs else "NO PLATE"
                member_info = {
                    "is_registered": False,
                    "mem_id": "UNREGISTERED",
                    "name": fallback_name if "Unregister" not in fallback_name else "Unregistered Visitor",
                    "vehicle_number": fallback_plate if fallback_plate != clean_tag else "NO PLATE",
                    "make_model": "Unregistered Tag",
                    "profile_pic": "",
                    "status": "Unregistered / Visitor",
                    "phone": "",
                    "e_tag_id": clean_tag
                }

            # 4. Aggregate Analytics & Telemetry
            total_detections = len(logs)
            if total_detections == 0:
                return {
                    "tag_id": clean_tag,
                    "found": False,
                    "is_registered": is_registered,
                    "member": member_info,
                    "summary": {
                        "total_detections": 0,
                        "days_active": 0,
                        "first_detected": None,
                        "latest_detected": None,
                        "most_active_reader": "--",
                        "readers_breakdown": {}
                    },
                    "daily_breakdown": [],
                    "scans": []
                }

            # Group scans by date
            by_date = {}
            readers_count = {}
            for l in reversed(logs):  # Chronological order for daily stay analysis
                d_str = str(l.get("timestamp", ""))[:10]
                if d_str not in by_date:
                    by_date[d_str] = []
                by_date[d_str].append(l)

                r_gate = l.get("gate_no") or "Gate-01"
                readers_count[r_gate] = readers_count.get(r_gate, 0) + 1

            # Build daily breakdown list (sorted newest date first)
            daily_breakdown = []
            for d_str in sorted(by_date.keys(), reverse=True):
                day_scans = by_date[d_str]
                analysis = analyze_day_movements(day_scans)
                
                day_readers = {}
                entries_cnt = 0
                exits_cnt = 0
                for s in day_scans:
                    g = s.get("gate_no") or "Gate-01"
                    day_readers[g] = day_readers.get(g, 0) + 1
                    direction = (s.get("direction") or "").lower()
                    if direction == "entry":
                        entries_cnt += 1
                    elif direction == "exit":
                        exits_cnt += 1

                timestamps = [str(s.get("timestamp", "")) for s in day_scans if s.get("timestamp")]
                first_ts = min(timestamps) if timestamps else "--"
                last_ts = max(timestamps) if timestamps else "--"

                daily_breakdown.append({
                    "date": d_str,
                    "total_detections": len(day_scans),
                    "entries": entries_cnt,
                    "exits": exits_cnt,
                    "first_scan_time": first_ts[11:19] if len(first_ts) >= 19 else first_ts,
                    "last_scan_time": last_ts[11:19] if len(last_ts) >= 19 else last_ts,
                    "stay_duration": analysis["total_stay_duration"],
                    "visits_count": analysis["visits_count"],
                    "readers": day_readers
                })

            most_active_reader = max(readers_count.items(), key=lambda x: x[1])[0] if readers_count else "Gate-01"
            first_seen = logs[-1].get("timestamp")
            last_seen = logs[0].get("timestamp")

            return {
                "tag_id": clean_tag,
                "found": True,
                "is_registered": is_registered,
                "member": member_info,
                "summary": {
                    "total_detections": total_detections,
                    "days_active": len(by_date),
                    "first_detected": first_seen,
                    "latest_detected": last_seen,
                    "most_active_reader": most_active_reader,
                    "readers_breakdown": readers_count
                },
                "daily_breakdown": daily_breakdown,
                "scans": logs
            }
        finally:
            conn.close()
