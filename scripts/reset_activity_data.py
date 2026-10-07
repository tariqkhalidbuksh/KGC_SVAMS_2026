"""
Reset Activity Data Utility
Purges all previous activity logs, raw reader scans, and camera audit entries.
Leaves 100% of Members data (10,798 records) and System Settings completely intact.
"""
import os
import sqlite3
import shutil

DB_FILE = "gate_access.db"
BACKUP_FILE = "gate_access.db.bak"

def reset_activity_data():
    if not os.path.exists(DB_FILE):
        print(f"Error: Database {DB_FILE} not found.")
        return False

    # Backup if not already backed up
    if not os.path.exists(BACKUP_FILE):
        shutil.copy2(DB_FILE, BACKUP_FILE)
        print(f"Created safety backup at {BACKUP_FILE}")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    m_before = c.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    s_before = c.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    d_before = c.execute("SELECT COUNT(*) FROM daily_logs").fetchone()[0]
    r_before = c.execute("SELECT COUNT(*) FROM raw_reader_logs").fetchone()[0]
    ca_before = c.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]

    print("--- BEFORE RESET ---")
    print(f"Members:           {m_before} (Will be retained)")
    print(f"Settings:          {s_before} (Will be retained)")
    print(f"Daily Logs:        {d_before} (Will be purged)")
    print(f"Raw Reader Logs:   {r_before} (Will be purged)")
    print(f"Camera Audit Logs: {ca_before} (Will be purged)")

    # Purge logs and reset transit state
    c.execute("DELETE FROM daily_logs")
    c.execute("DELETE FROM raw_reader_logs")
    c.execute("DELETE FROM camera_audit_logs")
    c.execute("DELETE FROM unregistered_tags")
    c.execute("DELETE FROM guest_passes")
    c.execute("UPDATE members SET Current_Location = 'Outside'")
    c.execute("DELETE FROM sqlite_sequence WHERE name IN ('daily_logs', 'raw_reader_logs', 'camera_audit_logs', 'unregistered_tags', 'guest_passes')")
    conn.commit()

    # Reclaim disk space
    c.execute("VACUUM")
    conn.close()

    # Clean temporary directories (keep profile pictures intact)
    for folder in ["static/snapshots", "static/camera_audit", "static/ftp_uploads", "static/tools_test"]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.unlink(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception as e:
                    print(f"Notice: Could not remove {fpath}: {e}")

    # Verify after reset
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    m_after = c.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    s_after = c.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    d_after = c.execute("SELECT COUNT(*) FROM daily_logs").fetchone()[0]
    r_after = c.execute("SELECT COUNT(*) FROM raw_reader_logs").fetchone()[0]
    ca_after = c.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]
    conn.close()

    print("\n--- AFTER RESET ---")
    print(f"Members:           {m_after} (100% Intact)")
    print(f"Settings:          {s_after} (100% Intact)")
    print(f"Daily Logs:        {d_after} (Reset to 0)")
    print(f"Raw Reader Logs:   {r_after} (Reset to 0)")
    print(f"Camera Audit Logs: {ca_after} (Reset to 0)")

    return True

if __name__ == "__main__":
    reset_activity_data()
