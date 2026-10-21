"""
Script to process System Outside / Auto Midnight Clearance for all vehicles marked 'Inside'
exclusively on PostgreSQL (kgc_vams). Pure PostgreSQL architecture.
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database import get_db_connection

def process_system_outside():
    print("[*] Processing System Outside clearance on PostgreSQL (kgc_vams)...")
    conn = get_db_connection()
    try:
        # 1. Check exception whitelist
        s_row = conn.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1").fetchone()
        raw_exceptions = []
        if s_row and s_row["config_value"]:
            try:
                raw_exceptions = json.loads(s_row["config_value"])
            except Exception:
                raw_exceptions = [x.strip() for x in s_row["config_value"].split(",") if x.strip()]
        exception_set = {str(x).strip().upper() for x in raw_exceptions if str(x).strip()}
        print(f"[+] Exception whitelist count: {len(exception_set)}")

        # 2. Process Members marked 'Inside'
        inside_members = conn.execute("SELECT id, mem_id, name, car_number, e_tag_id FROM members WHERE current_location = 'Inside'").fetchall()
        print(f"[+] Found {len(inside_members)} members currently marked Inside.")

        exited_members_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with conn:
            for m in inside_members:
                mem_id = (m["mem_id"] or "").strip().upper()
                plate = (m["car_number"] or "").strip().upper()
                tag = (m["e_tag_id"] or "").strip().upper()

                if (plate and plate in exception_set) or (mem_id and mem_id in exception_set) or (tag and tag in exception_set):
                    print(f"    [SKIP] Member {mem_id} ({plate}) is on exception whitelist.")
                    continue

                # Find last entry timestamp
                last_entry = conn.execute("""
                    SELECT timestamp FROM daily_logs 
                    WHERE (UPPER(scanned_tag) = ? OR UPPER(mem_id) = ?) AND direction = 'Entry' 
                    ORDER BY id DESC LIMIT 1
                """, (tag, mem_id)).fetchone()
                
                entry_ts = str(last_entry["timestamp"])[:19] if last_entry and last_entry["timestamp"] else now_str

                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES (?, ?, ?, 'Auto Midnight Exit (System Clearance)', 'Exit', 'System Auto-Clearance', ?, CURRENT_TIMESTAMP)
                """, (m["mem_id"], m["name"], m["car_number"], m["e_tag_id"] or "NO_TAG"))

                conn.execute("UPDATE members SET current_location = 'Outside' WHERE id = ?", (m["id"],))
                exited_members_count += 1

        print(f"[+] Successfully marked {exited_members_count} members as 'Outside'.")

        # 3. Process Unregistered Tags marked 'Inside'
        inside_unreg = conn.execute("SELECT id, tag, first_seen, last_seen FROM unregistered_tags WHERE current_location = 'Inside'").fetchall()
        print(f"[+] Found {len(inside_unreg)} unregistered tags currently marked Inside.")

        exited_unreg_count = 0
        with conn:
            for u in inside_unreg:
                u_tag = (u["tag"] or "").strip().upper()
                if u_tag in exception_set:
                    print(f"    [SKIP] Unregistered tag {u_tag} is on exception whitelist.")
                    continue

                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('UNREGISTERED', 'Unregistered Visitor', 'UNREGISTERED', 'Auto Midnight Exit (System Clearance)', 'Exit', 'System Auto-Clearance', ?, CURRENT_TIMESTAMP)
                """, (u["tag"],))

                conn.execute("UPDATE unregistered_tags SET current_location = 'Outside', direction = 'Exit' WHERE id = ?", (u["id"],))
                exited_unreg_count += 1

        print(f"[+] Successfully marked {exited_unreg_count} unregistered tags as 'Outside'.")
        print("[SUCCESS] All Inside vehicles processed to Outside cleanly on PostgreSQL!")
    finally:
        conn.close()

if __name__ == "__main__":
    process_system_outside()
