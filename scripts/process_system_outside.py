"""
Script to process System Outside / Auto Midnight Clearance for all vehicles marked 'Inside'
prior to or at midnight, and sync the result with PostgreSQL.
"""

import sqlite3
import json
from datetime import datetime

def process_system_outside(sqlite_path="gate_access.db"):
    print(f"[*] Processing System Outside clearance on {sqlite_path}...")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Check exception whitelist
    cur.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1")
    s_row = cur.fetchone()
    raw_exceptions = []
    if s_row and s_row["config_value"]:
        try:
            raw_exceptions = json.loads(s_row["config_value"])
        except Exception:
            raw_exceptions = [x.strip() for x in s_row["config_value"].split(",") if x.strip()]
    exception_set = {str(x).strip().upper() for x in raw_exceptions if str(x).strip()}
    print(f"[+] Exception whitelist count: {len(exception_set)}")

    # 2. Process Members marked 'Inside'
    cur.execute("SELECT id, Mem_id, Name, Car_number, E_tag_id FROM members WHERE Current_Location = 'Inside'")
    inside_members = cur.fetchall()
    print(f"[+] Found {len(inside_members)} members currently marked Inside.")

    exited_members_count = 0
    for m in inside_members:
        mem_id = (m["Mem_id"] or "").strip().upper()
        plate = (m["Car_number"] or "").strip().upper()
        tag = (m["E_tag_id"] or "").strip().upper()

        if (plate and plate in exception_set) or (mem_id and mem_id in exception_set) or (tag and tag in exception_set):
            print(f"    [SKIP] Member {mem_id} ({plate}) is on exception whitelist.")
            continue

        # Find last entry timestamp
        cur.execute("""
            SELECT timestamp FROM daily_logs 
            WHERE (UPPER(scanned_tag) = ? OR UPPER(mem_id) = ?) AND direction = 'Entry' 
            ORDER BY id DESC LIMIT 1
        """, (tag, mem_id))
        last_entry = cur.fetchone()
        entry_ts = str(last_entry["timestamp"])[:19] if last_entry and last_entry["timestamp"] else "2026-10-21 20:00:00"

        if entry_ts < "2026-10-22 00:00:00":
            cutoff_ts = "2026-10-21 23:59:00"
        else:
            cutoff_ts = "2026-10-22 00:20:00"

        cur.execute("""
            INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
            VALUES (?, ?, ?, 'Auto Midnight Exit (11:59 PM Cutoff)', 'Exit', 'System Auto-Clearance', ?, ?)
        """, (m["Mem_id"], m["Name"], m["Car_number"], m["E_tag_id"] or "NO_TAG", cutoff_ts))

        cur.execute("UPDATE members SET Current_Location = 'Outside' WHERE id = ?", (m["id"],))
        exited_members_count += 1

    print(f"[+] Successfully marked {exited_members_count} members as 'Outside'.")

    # 3. Process Unregistered Tags marked 'Inside'
    cur.execute("SELECT id, tag, first_seen, last_seen FROM unregistered_tags WHERE Current_Location = 'Inside'")
    inside_unreg = cur.fetchall()
    print(f"[+] Found {len(inside_unreg)} unregistered tags currently marked Inside.")

    exited_unreg_count = 0
    for u in inside_unreg:
        u_tag = (u["tag"] or "").strip().upper()
        if u_tag in exception_set:
            print(f"    [SKIP] Unregistered tag {u_tag} is on exception whitelist.")
            continue

        last_seen = str(u["last_seen"] or u["first_seen"])[:19]
        if last_seen < "2026-10-22 00:00:00":
            cutoff_ts = "2026-10-21 23:59:00"
        else:
            cutoff_ts = "2026-10-22 00:20:00"

        cur.execute("""
            INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
            VALUES ('UNREGISTERED', 'Unregistered Visitor', 'UNREGISTERED', 'Auto Midnight Exit (11:59 PM Cutoff)', 'Exit', 'System Auto-Clearance', ?, ?)
        """, (u["tag"], cutoff_ts))

        cur.execute("UPDATE unregistered_tags SET Current_Location = 'Outside', direction = 'Exit' WHERE id = ?", (u["id"],))
        exited_unreg_count += 1

    print(f"[+] Successfully marked {exited_unreg_count} unregistered tags as 'Outside'.")

    conn.commit()
    conn.close()
    print("[SUCCESS] All Inside vehicles processed to Outside cleanly!")

if __name__ == "__main__":
    process_system_outside()
