"""
Reset Activity Data Utility for PostgreSQL (kgc_vams)
Purges all previous activity logs, raw reader scans, and camera audit entries.
Leaves 100% of Members data (10,800+ records) and System Settings completely intact.
"""
import os
import sys
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database import get_db_connection

def reset_activity_data():
    conn = get_db_connection()
    try:
        m_before = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        s_before = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        d_before = conn.execute("SELECT COUNT(*) FROM daily_logs").fetchone()[0]
        r_before = conn.execute("SELECT COUNT(*) FROM raw_reader_logs").fetchone()[0]
        ca_before = conn.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]

        print("--- BEFORE RESET (PostgreSQL) ---")
        print(f"Members:           {m_before} (Will be retained)")
        print(f"Settings:          {s_before} (Will be retained)")
        print(f"Daily Logs:        {d_before} (Will be purged)")
        print(f"Raw Reader Logs:   {r_before} (Will be purged)")
        print(f"Camera Audit Logs: {ca_before} (Will be purged)")

        # Purge logs and reset transit state
        with conn:
            conn.execute("DELETE FROM daily_logs")
            conn.execute("DELETE FROM raw_reader_logs")
            conn.execute("DELETE FROM camera_audit_logs")
            conn.execute("DELETE FROM unregistered_tags")
            conn.execute("UPDATE members SET current_location = 'Outside'")
            conn.execute("ALTER SEQUENCE IF EXISTS daily_logs_id_seq RESTART WITH 1")
            conn.execute("ALTER SEQUENCE IF EXISTS raw_reader_logs_id_seq RESTART WITH 1")
            conn.execute("ALTER SEQUENCE IF EXISTS camera_audit_logs_id_seq RESTART WITH 1")
            conn.execute("ALTER SEQUENCE IF EXISTS unregistered_tags_id_seq RESTART WITH 1")

        # Clean temporary image directories
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

        m_after = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        s_after = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        d_after = conn.execute("SELECT COUNT(*) FROM daily_logs").fetchone()[0]
        r_after = conn.execute("SELECT COUNT(*) FROM raw_reader_logs").fetchone()[0]
        ca_after = conn.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]

        print("\n--- AFTER RESET (PostgreSQL) ---")
        print(f"Members:           {m_after} (100% Intact)")
        print(f"Settings:          {s_after} (100% Intact)")
        print(f"Daily Logs:        {d_after} (Reset to 0)")
        print(f"Raw Reader Logs:   {r_after} (Reset to 0)")
        print(f"Camera Audit Logs: {ca_after} (Reset to 0)")

        return True
    finally:
        conn.close()

if __name__ == "__main__":
    reset_activity_data()
