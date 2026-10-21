"""
Deep Analysis Tool for Legacy SQLite Databases vs Active PostgreSQL (kgc_vams)
Analyzes all SQLite databases in legacy_dbs/ and prepares a detailed audit report.
Does NOT modify or ingest any data. Read-only inspection.
"""

import os
import sys
import sqlite3
import psycopg2
from datetime import datetime

# PostgreSQL connection settings
PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DBNAME = os.environ.get("PG_DBNAME", "kgc_vams")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

LEGACY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legacy_dbs")

def format_ts(ts):
    if not ts:
        return "N/A"
    return str(ts)[:19]

def analyze_legacy_dbs():
    print("=" * 80)
    print("KARACHI GYMKHANA - LEGACY SQLITE DATABASE AUDIT & INGESTION ANALYSIS")
    print("=" * 80)

    # 1. Inspect Active PostgreSQL Database
    pg_conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DBNAME)
    pg_cur = pg_conn.cursor()

    pg_cur.execute("SELECT COUNT(*) FROM members")
    pg_members_count = pg_cur.fetchone()[0]

    pg_cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM daily_logs")
    pg_logs_count, pg_logs_min, pg_logs_max = pg_cur.fetchone()

    pg_cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM camera_audit_logs")
    pg_cam_count, pg_cam_min, pg_cam_max = pg_cur.fetchone()

    pg_cur.execute("SELECT COUNT(*) FROM unregistered_tags")
    pg_unreg_count = pg_cur.fetchone()[0]

    pg_cur.execute("SELECT COUNT(*) FROM raw_reader_logs")
    pg_raw_count = pg_cur.fetchone()[0]

    # Pre-fetch existing unique keys from PostgreSQL for fast deduplication checking
    print("[*] Loading existing signatures from PostgreSQL...")
    # Daily logs signature: (scanned_tag, timestamp_clean, direction)
    pg_cur.execute("SELECT scanned_tag, to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS'), direction FROM daily_logs")
    existing_pg_logs = set()
    for row in pg_cur.fetchall():
        tag = (row[0] or "").strip().upper()
        ts = str(row[1])[:19]
        d = (row[2] or "").strip().title()
        existing_pg_logs.add((tag, ts, d))

    # Members signature: e_tag_id and mem_id
    pg_cur.execute("SELECT e_tag_id, mem_id FROM members")
    existing_pg_etags = set()
    existing_pg_memids = set()
    for row in pg_cur.fetchall():
        if row[0]: existing_pg_etags.add(row[0].strip().upper())
        if row[1]: existing_pg_memids.add(row[1].strip().upper())

    # Camera audit signature: (image_path, timestamp_clean)
    pg_cur.execute("SELECT image_path, to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') FROM camera_audit_logs")
    existing_pg_cam = set()
    for row in pg_cur.fetchall():
        img = os.path.basename(row[0] or "")
        ts = str(row[1])[:19]
        existing_pg_cam.add((img, ts))

    # Unregistered tags signature
    pg_cur.execute("SELECT tag FROM unregistered_tags")
    existing_pg_unreg = {row[0].strip().upper() for row in pg_cur.fetchall() if row[0]}

    pg_cur.close()
    pg_conn.close()

    print("\n--- CURRENT ACTIVE POSTGRESQL (kgc_vams) BASELINE ---")
    print(f"  Members Registered : {pg_members_count:,}")
    print(f"  Daily Access Logs  : {pg_logs_count:,} (Date span: {format_ts(pg_logs_min)} -> {format_ts(pg_logs_max)})")
    print(f"  Camera Audit Logs  : {pg_cam_count:,} (Date span: {format_ts(pg_cam_min)} -> {format_ts(pg_cam_max)})")
    print(f"  Unregistered Tags  : {pg_unreg_count:,}")
    print(f"  Raw Reader Logs    : {pg_raw_count:,}")

    # 2. Inspect each SQLite file
    db_files = sorted([f for f in os.listdir(LEGACY_DIR) if f.lower().endswith(".db")])
    if not db_files:
        print("\n[!] No .db files found in legacy_dbs directory.")
        return

    print(f"\n[*] Discovered {len(db_files)} SQLite databases in legacy_dbs/:\n")

    file_reports = []
    all_combined_new_logs = set()
    all_combined_duplicate_logs_count = 0
    total_logs_in_sqlite_files = 0

    all_combined_new_members = {}
    all_combined_duplicate_members_count = 0
    total_members_in_sqlite_files = 0

    all_combined_new_cam = set()
    all_combined_dup_cam_count = 0
    total_cam_in_sqlite_files = 0

    all_combined_new_unreg = set()
    total_unreg_in_sqlite_files = 0

    for idx, fname in enumerate(db_files, 1):
        fpath = os.path.join(LEGACY_DIR, fname)
        fsize_mb = os.path.getsize(fpath) / (1024 * 1024)

        try:
            s_conn = sqlite3.connect(fpath)
            s_conn.row_factory = sqlite3.Row
            s_cur = s_conn.cursor()

            # Tables in this SQLite db
            s_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in s_cur.fetchall()]

            # Members stats
            m_count = 0
            new_members_in_file = 0
            if "members" in tables:
                s_cur.execute("SELECT COUNT(*) FROM members")
                m_count = s_cur.fetchone()[0]
                total_members_in_sqlite_files += m_count

                s_cur.execute("SELECT Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic, Current_Location FROM members")
                for m_row in s_cur.fetchall():
                    etag = (m_row["E_tag_id"] or "").strip().upper()
                    memid = (m_row["Mem_id"] or "").strip().upper()
                    if etag and (etag not in existing_pg_etags) and (etag not in all_combined_new_members):
                        new_members_in_file += 1
                        all_combined_new_members[etag] = dict(m_row)
                    else:
                        all_combined_duplicate_members_count += 1

            # Daily logs stats
            d_count = 0
            d_min, d_max = None, None
            new_logs_in_file = 0
            if "daily_logs" in tables:
                s_cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM daily_logs")
                d_row = s_cur.fetchone()
                d_count = d_row[0] or 0
                d_min = d_row[1]
                d_max = d_row[2]
                total_logs_in_sqlite_files += d_count

                s_cur.execute("SELECT scanned_tag, timestamp, direction, mem_id, vehicle_number FROM daily_logs")
                for d in s_cur.fetchall():
                    tag = (d["scanned_tag"] or "").strip().upper()
                    ts = str(d["timestamp"])[:19]
                    dir_val = (d["direction"] or "").strip().title()
                    sig = (tag, ts, dir_val)
                    if sig not in existing_pg_logs and sig not in all_combined_new_logs:
                        all_combined_new_logs.add(sig)
                        new_logs_in_file += 1
                    else:
                        all_combined_duplicate_logs_count += 1

            # Camera audit logs stats
            ca_count = 0
            ca_min, ca_max = None, None
            new_cam_in_file = 0
            if "camera_audit_logs" in tables:
                s_cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM camera_audit_logs")
                ca_row = s_cur.fetchone()
                ca_count = ca_row[0] or 0
                ca_min = ca_row[1]
                ca_max = ca_row[2]
                total_cam_in_sqlite_files += ca_count

                s_cur.execute("SELECT image_path, timestamp FROM camera_audit_logs")
                for c in s_cur.fetchall():
                    img = os.path.basename(c["image_path"] or "")
                    ts = str(c["timestamp"])[:19]
                    sig = (img, ts)
                    if sig not in existing_pg_cam and sig not in all_combined_new_cam:
                        all_combined_new_cam.add(sig)
                        new_cam_in_file += 1
                    else:
                        all_combined_dup_cam_count += 1

            # Unregistered tags stats
            u_count = 0
            new_unreg_in_file = 0
            if "unregistered_tags" in tables:
                s_cur.execute("SELECT COUNT(*) FROM unregistered_tags")
                u_count = s_cur.fetchone()[0] or 0
                total_unreg_in_sqlite_files += u_count

                s_cur.execute("SELECT tag FROM unregistered_tags")
                for u in s_cur.fetchall():
                    tag = (u["tag"] or "").strip().upper()
                    if tag and tag not in existing_pg_unreg and tag not in all_combined_new_unreg:
                        all_combined_new_unreg.add(tag)
                        new_unreg_in_file += 1

            # Raw reader logs stats
            r_count = 0
            if "raw_reader_logs" in tables:
                s_cur.execute("SELECT COUNT(*) FROM raw_reader_logs")
                r_count = s_cur.fetchone()[0] or 0

            s_conn.close()

            report_item = {
                "idx": idx,
                "filename": fname,
                "size_mb": fsize_mb,
                "tables": tables,
                "members_count": m_count,
                "new_members": new_members_in_file,
                "daily_logs_count": d_count,
                "daily_min": format_ts(d_min),
                "daily_max": format_ts(d_max),
                "new_logs": new_logs_in_file,
                "cam_count": ca_count,
                "cam_min": format_ts(ca_min),
                "cam_max": format_ts(ca_max),
                "new_cam": new_cam_in_file,
                "unreg_count": u_count,
                "new_unreg": new_unreg_in_file,
                "raw_count": r_count
            }
            file_reports.append(report_item)

            print(f"[{idx}/6] File: {fname} ({fsize_mb:.2f} MB)")
            print(f"      - Members          : {m_count:,} total ({new_members_in_file:,} new)")
            print(f"      - Daily Logs       : {d_count:,} total ({new_logs_in_file:,} new, Range: {format_ts(d_min)} to {format_ts(d_max)})")
            print(f"      - Camera Audits    : {ca_count:,} total ({new_cam_in_file:,} new, Range: {format_ts(ca_min)} to {format_ts(ca_max)})")
            print(f"      - Unregistered Tags: {u_count:,} total ({new_unreg_in_file:,} new)")
            print(f"      - Raw Reader Logs  : {r_count:,} total")
            print()

        except Exception as e:
            print(f"[!] Error inspecting {fname}: {e}")

    # Summary
    print("=" * 80)
    print("TOTAL AGGREGATE SUMMARY ACROSS ALL 6 LEGACY DATABASES")
    print("=" * 80)
    print(f"1. Daily Activity Logs:")
    print(f"   - Current in PostgreSQL : {pg_logs_count:,}")
    print(f"   - Scanned in 6 files    : {total_logs_in_sqlite_files:,}")
    print(f"   - Already in PostgreSQL : {all_combined_duplicate_logs_count:,} (Identical duplicates safely skipped)")
    print(f"   - NEW Unique Logs Found : +{len(all_combined_new_logs):,} (Will be safely ingested)")
    print(f"   - Expected Final Total  : {pg_logs_count + len(all_combined_new_logs):,} logs")

    print(f"\n2. Registered Members:")
    print(f"   - Current in PostgreSQL : {pg_members_count:,}")
    print(f"   - Scanned in 6 files    : {total_members_in_sqlite_files:,}")
    print(f"   - NEW Unique Members    : +{len(all_combined_new_members):,}")
    print(f"   - Expected Final Total  : {pg_members_count + len(all_combined_new_members):,} members")

    print(f"\n3. Camera Audit Logs:")
    print(f"   - Current in PostgreSQL : {pg_cam_count:,}")
    print(f"   - Scanned in 6 files    : {total_cam_in_sqlite_files:,}")
    print(f"   - NEW Camera Audits     : +{len(all_combined_new_cam):,}")
    print(f"   - Expected Final Total  : {pg_cam_count + len(all_combined_new_cam):,} audit records")

    print(f"\n4. Unregistered Visitor Tags:")
    print(f"   - Current in PostgreSQL : {pg_unreg_count:,}")
    print(f"   - Scanned in 6 files    : {total_unreg_in_sqlite_files:,}")
    print(f"   - NEW Unregistered Tags : +{len(all_combined_new_unreg):,}")
    print(f"   - Expected Final Total  : {pg_unreg_count + len(all_combined_new_unreg):,} tags")
    print("=" * 80)

if __name__ == "__main__":
    analyze_legacy_dbs()
