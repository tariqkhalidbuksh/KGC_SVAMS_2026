"""
Clear Legacy Inside Records for Karachi Gymkhana RFID VAMS
Closes 19 historical unclosed visits with proper 'Auto Midnight Exit (11:59 PM Cutoff)'
so that currently_in_club is 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database import get_db_connection
from routers.logs import enrich_daily_log_with_members, _build_paired_audits, RAW_DAILY_LOGS_SELECT
from services.member_service import get_member_directory_lookup

def clear_legacy_inside():
    print("[*] Finding unexited historical journeys...")
    conn = get_db_connection()
    try:
        mem_lookup = get_member_directory_lookup(conn)
        rows = conn.execute(RAW_DAILY_LOGS_SELECT + " ORDER BY d.id ASC").fetchall()
        logs = [enrich_daily_log_with_members(dict(r), mem_lookup) for r in rows]
        paired = _build_paired_audits(logs)
        inside_all = [a for a in paired if a['status'] in ('Inside Facility', 'Alert / Inside', 'Overstay (>8h)')]
        print(f"[+] Found {len(inside_all)} journeys marked Inside.")

        inserted = 0
        for a in inside_all:
            e = a['entry']
            e_date = str(e['timestamp'])[:10]
            exit_ts = f"{e_date} 23:59:00"
            conn.execute(
                """INSERT INTO daily_logs 
                   (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp) 
                   VALUES (?, ?, ?, 'Auto Midnight Exit (11:59 PM Cutoff)', 'Exit', 'System Auto-Clearance', ?, ?)""",
                (
                    e.get('mem_id') or 'UNREGISTERED',
                    e.get('name') or 'Unregistered Visitor',
                    e.get('vehicle_number') or 'UNREGISTERED',
                    e.get('scanned_tag') or 'NO_TAG',
                    exit_ts
                )
            )
            inserted += 1

        conn.commit()
        print(f"[+] Successfully inserted {inserted} Auto Midnight Exit records.")

        conn.execute("UPDATE members SET current_location = 'Outside' WHERE current_location = 'Inside'")
        conn.execute("UPDATE unregistered_tags SET current_location = 'Outside', direction = 'Exit' WHERE current_location = 'Inside'")
        conn.commit()
        print("[+] Reset current_location in members and unregistered_tags to 'Outside'.")

    finally:
        conn.close()

if __name__ == "__main__":
    clear_legacy_inside()
