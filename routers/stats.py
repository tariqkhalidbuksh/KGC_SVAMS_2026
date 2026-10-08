from datetime import datetime, timedelta
from fastapi import APIRouter
import config
from database import get_db_connection

router = APIRouter(prefix="/api", tags=["Statistics & Metrics"])

@router.get("/stats")
async def get_stats():
    import time
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            start_today = f"{pkt_today} 00:00:00"
            end_today = f"{pkt_today} 23:59:59"

            # Cached Member Counts: refresh every 30s instead of scanning 8,000+ rows every 5s
            import sys
            app_mod = sys.modules.get('app')
            curr_db_file = getattr(app_mod, 'DB_FILE', getattr(config, 'DB_FILE', 'gate_access.db'))

            now_epoch = time.time()
            with config.CACHE_LOCK:
                cached_metrics = config.MEMBERS_METRICS_CACHE.get("data")
                cache_time = config.MEMBERS_METRICS_CACHE.get("timestamp", 0.0)
                cached_db = config.MEMBERS_METRICS_CACHE.get("db_file")

            if cached_metrics and (cached_db == curr_db_file) and (now_epoch - cache_time < 30.0):
                members_count = cached_metrics["members_count"]
                unique_mems = cached_metrics["unique_mems"]
                total_vehicles = cached_metrics["total_vehicles"]
            else:
                members_count = conn.execute(
                    "SELECT COUNT(*) as c FROM members WHERE Status='Active' OR Status IS NULL OR Status=''"
                ).fetchone()['c']

                unique_mems = conn.execute(
                    "SELECT COUNT(DISTINCT Mem_id) as c FROM members WHERE Mem_id != '' AND Mem_id IS NOT NULL"
                ).fetchone()['c']

                total_vehicles = conn.execute("SELECT COUNT(*) as c FROM members").fetchone()['c']

                with config.CACHE_LOCK:
                    config.MEMBERS_METRICS_CACHE = {
                        "data": {
                            "members_count": members_count,
                            "unique_mems": unique_mems,
                            "total_vehicles": total_vehicles
                        },
                        "timestamp": now_epoch,
                        "db_file": curr_db_file
                    }

            entries_today = conn.execute(
                "SELECT COUNT(*) as c FROM daily_logs WHERE direction='Entry' AND date(timestamp)=?",
                (pkt_today,)
            ).fetchone()['c']

            exits_today = conn.execute(
                "SELECT COUNT(*) as c FROM daily_logs WHERE direction='Exit' AND date(timestamp)=?",
                (pkt_today,)
            ).fetchone()['c']

            guests_today = conn.execute(
                "SELECT COUNT(*) as c FROM daily_logs WHERE date(timestamp)=? "
                "AND (access_type LIKE '%Unknown%' OR access_type LIKE '%No RFID%')",
                (pkt_today,)
            ).fetchone()['c']

            peak_row = conn.execute("""SELECT strftime('%H', timestamp) as h, COUNT(*) as c FROM daily_logs
                WHERE direction='Entry' AND date(timestamp)=?
                GROUP BY h ORDER BY c DESC LIMIT 1""", (pkt_today,)).fetchone()

            peak_hour_str = f"{peak_row['h']}:00" if peak_row else "None"
            peak_count_val = peak_row['c'] if peak_row else 0

            overstay_row = conn.execute("""
                SELECT COUNT(*) as c FROM daily_logs d
                WHERE d.direction = 'Entry'
                  AND d.timestamp <= datetime('now', '-8 hours')
                  AND NOT EXISTS (
                      SELECT 1 FROM daily_logs e
                      WHERE e.direction = 'Exit'
                        AND (
                            (e.mem_id = d.mem_id AND d.mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED'))
                            OR (e.scanned_tag = d.scanned_tag AND d.scanned_tag NOT IN ('NO_TAG', ''))
                        )
                        AND e.timestamp >= d.timestamp
                  )
            """).fetchone()
            overstay_count = overstay_row['c'] if overstay_row else 0

            # Calculate Average Stay Duration from paired visits today
            paired_rows = conn.execute("""
                SELECT d.timestamp as in_time, e.timestamp as out_time
                FROM daily_logs d
                JOIN daily_logs e ON (
                    (d.mem_id = e.mem_id AND d.mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', ''))
                    OR (d.scanned_tag = e.scanned_tag AND d.scanned_tag NOT IN ('NO_TAG', ''))
                    OR (d.vehicle_number = e.vehicle_number AND d.vehicle_number != 'NO PLATE' AND d.vehicle_number != '')
                )
                WHERE d.direction = 'Entry' AND e.direction = 'Exit'
                  AND date(d.timestamp) = ? AND date(e.timestamp) = ?
                  AND e.timestamp >= d.timestamp
            """, (pkt_today, pkt_today)).fetchall()

            avg_duration_str = "--"
            if paired_rows:
                total_diff_sec = 0
                valid_count = 0
                for pr in paired_rows:
                    try:
                        t1 = datetime.strptime(str(pr['in_time'])[:19], "%Y-%m-%d %H:%M:%S")
                        t2 = datetime.strptime(str(pr['out_time'])[:19], "%Y-%m-%d %H:%M:%S")
                        sec = abs(int((t2 - t1).total_seconds()))
                        if 60 <= sec <= 86400:
                            total_diff_sec += sec
                            valid_count += 1
                    except Exception:
                        pass
                if valid_count > 0:
                    avg_sec = total_diff_sec // valid_count
                    h = avg_sec // 3600
                    m = (avg_sec % 3600) // 60
                    avg_duration_str = f"{h}h {m:02d}m" if h else f"{m}m"

            # All-Time Unique Tag Fleet Adoption & Gap Analysis (Unique Scanned Tags: 457+ tags)
            tag_adoption_query = conn.execute("""
                SELECT 
                    COUNT(DISTINCT UPPER(TRIM(d.scanned_tag))) as total_scanned_tags,
                    COUNT(DISTINCT CASE WHEN (m.Mem_id IS NOT NULL AND m.Mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '')) 
                                         OR (d.mem_id IS NOT NULL AND d.mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '') AND d.access_type NOT LIKE '%Unknown%')
                                        THEN UPPER(TRIM(d.scanned_tag)) END) as registered_tags,
                    COUNT(DISTINCT CASE WHEN (m.Mem_id IS NULL OR m.Mem_id IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', ''))
                                         AND (d.mem_id IS NULL OR d.mem_id IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '') OR d.access_type LIKE '%Unknown%')
                                        THEN UPPER(TRIM(d.scanned_tag)) END) as unregistered_tags
                FROM daily_logs d
                LEFT JOIN members m ON UPPER(TRIM(d.scanned_tag)) = UPPER(TRIM(m.E_tag_id))
                WHERE d.scanned_tag IS NOT NULL AND d.scanned_tag != '' AND UPPER(TRIM(d.scanned_tag)) != 'NO_TAG'
            """).fetchone()

            total_unique_tags = tag_adoption_query['total_scanned_tags'] or 0
            reg_unique_tags = tag_adoption_query['registered_tags'] or 0
            unreg_unique_tags = tag_adoption_query['unregistered_tags'] or 0

            adoption_rate = round((reg_unique_tags / total_unique_tags * 100.0), 1) if total_unique_tags > 0 else 100.0
            gap_rate = round((unreg_unique_tags / total_unique_tags * 100.0), 1) if total_unique_tags > 0 else 0.0

            # Today's transits for daily log reporting
            unreg_today = conn.execute("""
                SELECT COUNT(*) as c FROM daily_logs
                WHERE date(timestamp) = ?
                  AND (
                    access_type LIKE '%Unknown%'
                    OR access_type LIKE '%No RFID%'
                    OR mem_id IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '')
                    OR scanned_tag IN ('NO_TAG', '', NULL)
                  )
            """, (pkt_today,)).fetchone()['c']
            total_transits_today = entries_today + exits_today
            reg_today = max(0, total_transits_today - unreg_today)

            try:
                unreg_tags_buffer = conn.execute("SELECT COUNT(*) as c FROM unregistered_tags").fetchone()['c']
            except Exception:
                unreg_tags_buffer = 0

            return {
                "active_members": members_count,
                "unique_members": unique_mems,
                "total_vehicles": total_vehicles,
                "total_entries_today": entries_today,
                "total_exits_today": exits_today,
                "currently_in_club": max(0, entries_today - exits_today),
                "guests_today": guests_today,
                "overstay_count": overstay_count,
                "peak_hour": peak_hour_str,
                "peak_count": peak_count_val,
                "avg_duration": avg_duration_str,
                "paired_visits_count": len(paired_rows) if paired_rows else 0,
                "registered_transits_today": reg_today,
                "unregistered_transits_today": unreg_today,
                "registered_transits_all_time": reg_unique_tags,
                "unregistered_transits_all_time": unreg_unique_tags,
                "total_transits_all_time": total_unique_tags,
                "total_scanned_tags": total_unique_tags,
                "registered_tags_count": reg_unique_tags,
                "unregistered_tags_count": unreg_unique_tags,
                "tag_adoption_rate": adoption_rate,
                "registration_gap_rate": gap_rate,
                "unassigned_tags_buffer": unreg_tags_buffer
            }
        finally:
            conn.close()

@router.get("/chart-data")
async def get_chart_data():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            hours = [f"{h:02d}" for h in range(24)]

            entries_h = {r['h']: r['c'] for r in conn.execute(
                """SELECT strftime('%H', timestamp) as h, COUNT(*) as c FROM daily_logs
                   WHERE direction='Entry' AND date(timestamp)=? GROUP BY h""",
                (pkt_today,)
            ).fetchall()}

            exits_h = {r['h']: r['c'] for r in conn.execute(
                """SELECT strftime('%H', timestamp) as h, COUNT(*) as c FROM daily_logs
                   WHERE direction='Exit' AND date(timestamp)=? GROUP BY h""",
                (pkt_today,)
            ).fetchall()}

            days, entries_d, exits_d = [], [], []
            for row in conn.execute(
                """SELECT date(timestamp) as d,
                       SUM(CASE WHEN direction='Entry' THEN 1 ELSE 0 END) as e,
                       SUM(CASE WHEN direction='Exit' THEN 1 ELSE 0 END) as x
                   FROM daily_logs WHERE date(timestamp) >= date('now', 'localtime', '-6 days')
                   GROUP BY d ORDER BY d"""
            ).fetchall():
                days.append(row['d'][5:])
                entries_d.append(row['e'])
                exits_d.append(row['x'])

            # All-Time Unique Tag Fleet Adoption Breakdown (Unique Scanned Tags: 457+ tags)
            tag_adoption_query = conn.execute("""
                SELECT 
                    COUNT(DISTINCT UPPER(TRIM(d.scanned_tag))) as total_scanned_tags,
                    COUNT(DISTINCT CASE WHEN (m.Mem_id IS NOT NULL AND m.Mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '')) 
                                         OR (d.mem_id IS NOT NULL AND d.mem_id NOT IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '') AND d.access_type NOT LIKE '%Unknown%')
                                        THEN UPPER(TRIM(d.scanned_tag)) END) as registered_tags,
                    COUNT(DISTINCT CASE WHEN (m.Mem_id IS NULL OR m.Mem_id IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', ''))
                                         AND (d.mem_id IS NULL OR d.mem_id IN ('GUEST-LOG', 'AI-CAM', 'UNREGISTERED', '') OR d.access_type LIKE '%Unknown%')
                                        THEN UPPER(TRIM(d.scanned_tag)) END) as unregistered_tags
                FROM daily_logs d
                LEFT JOIN members m ON UPPER(TRIM(d.scanned_tag)) = UPPER(TRIM(m.E_tag_id))
                WHERE d.scanned_tag IS NOT NULL AND d.scanned_tag != '' AND UPPER(TRIM(d.scanned_tag)) != 'NO_TAG'
            """).fetchone()

            total_unique_tags = tag_adoption_query['total_scanned_tags'] or 0
            reg_unique_tags = tag_adoption_query['registered_tags'] or 0
            unreg_unique_tags = tag_adoption_query['unregistered_tags'] or 0

            adoption_rate = round((reg_unique_tags / total_unique_tags * 100.0), 1) if total_unique_tags > 0 else 100.0
            gap_rate = round((unreg_unique_tags / total_unique_tags * 100.0), 1) if total_unique_tags > 0 else 0.0

            try:
                unreg_tags_buffer = conn.execute("SELECT COUNT(*) as c FROM unregistered_tags").fetchone()['c']
            except Exception:
                unreg_tags_buffer = 0

            return {
                "hours": hours,
                "hourly_entries": [entries_h.get(h, 0) for h in hours],
                "hourly_exits": [exits_h.get(h, 0) for h in hours],
                "days": days,
                "daily_entries": entries_d,
                "daily_exits": exits_d,
                "fleet_adoption": {
                    "registered_transits": reg_unique_tags,
                    "unregistered_transits": unreg_unique_tags,
                    "total_transits": total_unique_tags,
                    "total_scanned_tags": total_unique_tags,
                    "registered_tags": reg_unique_tags,
                    "unregistered_tags": unreg_unique_tags,
                    "adoption_rate": adoption_rate,
                    "gap_rate": gap_rate,
                    "unassigned_buffer": unreg_tags_buffer
                }
            }
        finally:
            conn.close()

@router.get("/camera-audit-stats")
async def get_camera_audit_stats():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            pkt_today = config.get_pkt_today()
            today_count = conn.execute(
                "SELECT COUNT(*) as c FROM camera_audit_logs WHERE date_str=?",
                (pkt_today,)
            ).fetchone()['c']

            week_count = conn.execute(
                "SELECT COUNT(*) as c FROM camera_audit_logs WHERE date_str >= date('now', 'localtime', '-6 days')"
            ).fetchone()['c']

            month_count = conn.execute(
                "SELECT COUNT(*) as c FROM camera_audit_logs WHERE date_str >= date('now', 'localtime', '-29 days')"
            ).fetchone()['c']

            return {
                "today_total": today_count,
                "week_total": week_count,
                "month_total": month_count
            }
        finally:
            conn.close()
