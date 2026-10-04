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

            # Cached Member Counts: refresh every 60s instead of scanning 8,000+ rows every 5s
            now_epoch = time.time()
            with config.CACHE_LOCK:
                cached_metrics = config.MEMBERS_METRICS_CACHE.get("data")
                cache_time = config.MEMBERS_METRICS_CACHE.get("timestamp", 0.0)

            if cached_metrics and (now_epoch - cache_time < 60.0):
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
                    config.MEMBERS_METRICS_CACHE["data"] = {
                        "members_count": members_count,
                        "unique_mems": unique_mems,
                        "total_vehicles": total_vehicles
                    }
                    config.MEMBERS_METRICS_CACHE["timestamp"] = now_epoch

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

            return {
                "active_members": members_count,
                "unique_members": unique_mems,
                "total_vehicles": total_vehicles,
                "total_entries_today": entries_today,
                "total_exits_today": exits_today,
                "currently_in_club": max(0, entries_today - exits_today),
                "guests_today": guests_today,
                "peak_hour": peak_hour_str,
                "peak_count": peak_count_val
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

            return {
                "hours": hours,
                "hourly_entries": [entries_h.get(h, 0) for h in hours],
                "hourly_exits": [exits_h.get(h, 0) for h in hours],
                "days": days,
                "daily_entries": entries_d,
                "daily_exits": exits_d
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
