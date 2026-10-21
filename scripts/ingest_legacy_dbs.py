"""
Production Ingestion Script for Karachi Gymkhana RFID VAMS
Choice B Implementation:
1. Purges existing legacy M-Tag noise from active PostgreSQL (kgc_vams).
2. Ingests all 6 legacy SQLite databases, strictly skipping all NHA M-Tag records.
3. Dynamically adapts to schema differences across older SQLite database backups.
4. Automatically deduplicates against existing records (zero duplicates).
5. Updates all PostgreSQL auto-increment sequence counters.
"""

import os
import sys
import sqlite3
import psycopg2
from datetime import datetime

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DBNAME = os.environ.get("PG_DBNAME", "kgc_vams")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

LEGACY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legacy_dbs")

def is_mtag(tag_epc: str, access_type: str = "", tag_type: str = "") -> bool:
    tag = (tag_epc or "").strip().upper()
    acc = (access_type or "").strip().upper()
    tt = (tag_type or "").strip().upper()
    if tag.startswith(("E2801105", "E2801114")):
        return True
    if "M-TAG" in acc or "MTAG" in acc or "MOTORWAY" in acc:
        return True
    if "M-TAG" in tt or "MTAG" in tt or "MOTORWAY" in tt:
        return True
    return False

def execute_ingestion():
    print("=" * 80)
    print("KARACHI GYMKHANA - CHOICE B INGESTION & PURGE EXECUTION")
    print("=" * 80)

    pg_conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DBNAME)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()

    try:
        # STEP 1: Purge existing M-Tag records in active PostgreSQL database
        print("\n[STEP 1] Cleaning existing M-Tag clutter from PostgreSQL (kgc_vams)...")
        pg_cur.execute("""
            DELETE FROM daily_logs 
            WHERE UPPER(access_type) LIKE '%M-TAG%' 
               OR scanned_tag LIKE 'E2801105%' 
               OR scanned_tag LIKE 'E2801114%'
        """)
        purged_logs = pg_cur.rowcount

        pg_cur.execute("""
            DELETE FROM unregistered_tags 
            WHERE UPPER(tag_type) LIKE '%M-TAG%' 
               OR tag LIKE 'E2801105%' 
               OR tag LIKE 'E2801114%'
        """)
        purged_unreg = pg_cur.rowcount
        print(f"  [-] Purged {purged_logs} existing M-Tag records from daily_logs.")
        print(f"  [-] Purged {purged_unreg} existing M-Tag records from unregistered_tags.")

        # Load active signatures to prevent duplicates
        print("\n[STEP 2] Loading current PostgreSQL signatures for 100% duplicate protection...")
        pg_cur.execute("SELECT scanned_tag, to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS'), direction FROM daily_logs")
        existing_logs = {(row[0].strip().upper() if row[0] else '', str(row[1])[:19], (row[2] or '').strip().title()) for row in pg_cur.fetchall()}

        pg_cur.execute("SELECT e_tag_id FROM members WHERE e_tag_id IS NOT NULL AND e_tag_id != ''")
        existing_etags = {row[0].strip().upper() for row in pg_cur.fetchall()}

        pg_cur.execute("SELECT image_path, to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') FROM camera_audit_logs")
        existing_cam = {(os.path.basename(row[0] or ''), str(row[1])[:19]) for row in pg_cur.fetchall()}

        pg_cur.execute("SELECT tag FROM unregistered_tags")
        existing_unreg = {row[0].strip().upper() for row in pg_cur.fetchall() if row[0]}

        print(f"  Baseline unique signatures: {len(existing_logs):,} daily logs, {len(existing_etags):,} members, {len(existing_cam):,} cam audits, {len(existing_unreg):,} unreg tags.")

        # STEP 3: Iterate through all 6 SQLite databases and ingest
        db_files = sorted([f for f in os.listdir(LEGACY_DIR) if f.lower().endswith(".db")])
        print(f"\n[STEP 3] Ingesting {len(db_files)} SQLite databases (Strictly skipping M-Tags)...")

        total_ingested_logs = 0
        total_skipped_mtag_logs = 0
        total_skipped_dup_logs = 0

        total_ingested_members = 0
        total_ingested_cam = 0
        total_skipped_dup_cam = 0

        total_ingested_unreg = 0
        total_skipped_mtag_unreg = 0

        for idx, fname in enumerate(db_files, 1):
            fpath = os.path.join(LEGACY_DIR, fname)
            print(f"  [{idx}/{len(db_files)}] Processing {fname}...")
            s_conn = sqlite3.connect(fpath)
            s_conn.row_factory = sqlite3.Row
            s_cur = s_conn.cursor()

            s_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in s_cur.fetchall()]

            # 3a. Ingest Members
            if "members" in tables:
                s_cur.execute("PRAGMA table_info(members)")
                m_cols = {r[1].lower() for r in s_cur.fetchall()}
                s_cur.execute("SELECT * FROM members")
                for m in s_cur.fetchall():
                    etag = (m["E_tag_id"] if "e_tag_id" in m_cols else m["e_tag_id"]) or ""
                    etag = etag.strip().upper()
                    if etag and etag not in existing_etags:
                        mem_id = m["Mem_id"] if "mem_id" in m_cols else m["mem_id"]
                        name = m["Name"] if "name" in m_cols else m["name"]
                        car = m["Car_number"] if "car_number" in m_cols else m["car_number"]
                        make = m["Make_Model"] if "make_model" in m_cols else (m["make_model"] if "make_model" in m_cols else "")
                        status = m["Status"] if "status" in m_cols else (m["status"] if "status" in m_cols else "Active")
                        pic = m["Profile_pic"] if "profile_pic" in m_cols else (m["profile_pic"] if "profile_pic" in m_cols else "")
                        loc = m["Current_Location"] if "current_location" in m_cols else (m["current_location"] if "current_location" in m_cols else "Outside")

                        pg_cur.execute("""
                            INSERT INTO members (mem_id, name, car_number, make_model, e_tag_id, status, profile_pic, current_location)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (e_tag_id) DO NOTHING
                        """, (
                            mem_id or "N/A",
                            name or "Club Member",
                            car or "N/A",
                            make or "",
                            etag,
                            status or "Active",
                            pic or "",
                            loc or "Outside"
                        ))
                        if pg_cur.rowcount > 0:
                            existing_etags.add(etag)
                            total_ingested_members += 1

            # 3b. Ingest Daily Access Logs
            if "daily_logs" in tables:
                s_cur.execute("PRAGMA table_info(daily_logs)")
                d_cols = {r[1].lower() for r in s_cur.fetchall()}
                s_cur.execute("SELECT * FROM daily_logs ORDER BY id ASC")
                batch_logs = []
                for log in s_cur.fetchall():
                    tag = (log["scanned_tag"] if "scanned_tag" in d_cols else "") or ""
                    tag = tag.strip().upper()
                    acc = (log["access_type"] if "access_type" in d_cols else "") or ""
                    ts_str = str(log["timestamp"])[:19] if log["timestamp"] else ""
                    dir_val = ((log["direction"] if "direction" in d_cols else "Entry") or "Entry").strip().title()

                    # Filter out M-Tags
                    if is_mtag(tag, access_type=acc):
                        total_skipped_mtag_logs += 1
                        continue

                    sig = (tag, ts_str, dir_val)
                    if sig in existing_logs:
                        total_skipped_dup_logs += 1
                        continue

                    existing_logs.add(sig)
                    batch_logs.append((
                        (log["mem_id"] if "mem_id" in d_cols else "") or "",
                        (log["name"] if "name" in d_cols else "") or "",
                        (log["vehicle_number"] if "vehicle_number" in d_cols else "") or "",
                        (log["access_type"] if "access_type" in d_cols else "RFID Verified") or "RFID Verified",
                        dir_val,
                        (log["gate_no"] if "gate_no" in d_cols else "Gate-01") or "Gate-01",
                        (log["image_path"] if "image_path" in d_cols else "") or "",
                        (log["plate_image_path"] if "plate_image_path" in d_cols else "") or "",
                        (log["detected_plate"] if "detected_plate" in d_cols else "") or "",
                        tag,
                        ts_str
                    ))

                if batch_logs:
                    pg_cur.executemany("""
                        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, detected_plate, scanned_tag, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, batch_logs)
                    total_ingested_logs += len(batch_logs)

            # 3c. Ingest Camera Audit Logs
            if "camera_audit_logs" in tables:
                s_cur.execute("PRAGMA table_info(camera_audit_logs)")
                ca_cols = {r[1].lower() for r in s_cur.fetchall()}
                s_cur.execute("SELECT * FROM camera_audit_logs ORDER BY id ASC")
                batch_cam = []
                for c in s_cur.fetchall():
                    img = os.path.basename((c["image_path"] if "image_path" in ca_cols else "") or "")
                    ts_str = str(c["timestamp"])[:19] if c["timestamp"] else ""
                    sig = (img, ts_str)
                    if sig in existing_cam:
                        total_skipped_dup_cam += 1
                        continue

                    existing_cam.add(sig)
                    batch_cam.append((
                        (c["image_path"] if "image_path" in ca_cols else "") or "",
                        (c["plate_image_path"] if "plate_image_path" in ca_cols else "") or "",
                        (c["detected_plate"] if "detected_plate" in ca_cols else "") or "",
                        (c["direction"] if "direction" in ca_cols else "Unknown") or "Unknown",
                        (c["event_type"] if "event_type" in ca_cols else "Line Crossing") or "Line Crossing",
                        (c["ocr_status"] if "ocr_status" in ca_cols else "") or "",
                        (c["matched_mem_id"] if "matched_mem_id" in ca_cols else "") or "",
                        (c["matched_name"] if "matched_name" in ca_cols else "") or "",
                        (c["matched_make_model"] if "matched_make_model" in ca_cols else "") or "",
                        (c["matched_profile_pic"] if "matched_profile_pic" in ca_cols else "") or "",
                        ts_str,
                        (c["date_str"] if "date_str" in ca_cols else ts_str[:10]) or ts_str[:10],
                        (c["hour_str"] if "hour_str" in ca_cols else ts_str[11:13] + ":00") or ts_str[11:13] + ":00"
                    ))

                if batch_cam:
                    pg_cur.executemany("""
                        INSERT INTO camera_audit_logs (image_path, plate_image_path, detected_plate, direction, event_type, ocr_status, matched_mem_id, matched_name, matched_make_model, matched_profile_pic, timestamp, date_str, hour_str)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, batch_cam)
                    total_ingested_cam += len(batch_cam)

            # 3d. Ingest Unregistered Tags (Excluding M-Tags)
            if "unregistered_tags" in tables:
                s_cur.execute("PRAGMA table_info(unregistered_tags)")
                u_cols = {r[1].lower() for r in s_cur.fetchall()}
                s_cur.execute("SELECT * FROM unregistered_tags")

                for u in s_cur.fetchall():
                    u_tag = (u["tag"] or "").strip().upper()
                    ttype = (u["tag_type"] if "tag_type" in u_cols else "Unregistered Visitor") or "Unregistered Visitor"

                    if is_mtag(u_tag, tag_type=ttype):
                        total_skipped_mtag_unreg += 1
                        continue

                    if u_tag and u_tag not in existing_unreg:
                        fseen = str(u["first_seen"])[:19] if "first_seen" in u_cols and u["first_seen"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        lseen = str(u["last_seen"])[:19] if "last_seen" in u_cols and u["last_seen"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        udir = (u["direction"] if "direction" in u_cols else "Unknown") or "Unknown"
                        cloc = (u["current_location"] if "current_location" in u_cols else "Outside") or "Outside"
                        rcnt = int(u["read_count"] if "read_count" in u_cols and u["read_count"] else 1)

                        pg_cur.execute("""
                            INSERT INTO unregistered_tags (tag, first_seen, last_seen, direction, current_location, read_count, tag_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (tag) DO UPDATE SET 
                                read_count = unregistered_tags.read_count + EXCLUDED.read_count,
                                last_seen = GREATEST(unregistered_tags.last_seen, EXCLUDED.last_seen)
                        """, (u_tag, fseen, lseen, udir, cloc, rcnt, ttype))
                        existing_unreg.add(u_tag)
                        total_ingested_unreg += 1

            s_conn.close()

        # STEP 4: Reset all PostgreSQL sequences to MAX(id)
        print("\n[STEP 4] Synchronizing PostgreSQL sequence generators...")
        for seq, tbl in [
            ("daily_logs_id_seq", "daily_logs"),
            ("camera_audit_logs_id_seq", "camera_audit_logs"),
            ("unregistered_tags_id_seq", "unregistered_tags"),
            ("members_id_seq", "members")
        ]:
            pg_cur.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {tbl}), 1))")

        pg_conn.commit()
        print("[SUCCESS] All transactions committed cleanly to PostgreSQL!")

        # STEP 5: Final Counts
        print("\n" + "=" * 80)
        print("FINAL POSTGRESQL (kgc_vams) INGESTION REPORT (CHOICE B)")
        print("=" * 80)
        pg_cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM daily_logs")
        final_logs, min_d, max_d = pg_cur.fetchone()
        pg_cur.execute("SELECT COUNT(*) FROM members")
        final_members = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM camera_audit_logs")
        final_cam = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM unregistered_tags")
        final_unreg = pg_cur.fetchone()[0]

        print(f"1. Daily Activity Logs:")
        print(f"   - Added New Genuine Logs : +{total_ingested_logs:,}")
        print(f"   - M-Tag Logs Skipped     : {total_skipped_mtag_logs:,} (Skipped)")
        print(f"   - Duplicate Logs Skipped : {total_skipped_dup_logs:,} (Skipped)")
        print(f"   - Final Total in DB      : {final_logs:,} (Date span: {min_d} to {max_d})")

        print(f"\n2. Camera Audit Logs:")
        print(f"   - Added New Audits       : +{total_ingested_cam:,}")
        print(f"   - Duplicate Audits Skip  : {total_skipped_dup_cam:,} (Skipped)")
        print(f"   - Final Total in DB      : {final_cam:,}")

        print(f"\n3. Unregistered Visitor Tags:")
        print(f"   - Added New Tags         : +{total_ingested_unreg:,}")
        print(f"   - M-Tags Skipped         : {total_skipped_mtag_unreg:,} (Skipped)")
        print(f"   - Final Total in DB      : {final_unreg:,}")

        print(f"\n4. Registered Club Members:")
        print(f"   - Added New Members      : +{total_ingested_members:,}")
        print(f"   - Final Total in DB      : {final_members:,}")
        print("=" * 80)

    except Exception as exc:
        pg_conn.rollback()
        print(f"\n[FATAL ERROR] Ingestion failed. Transaction rolled back completely: {exc}")
        raise
    finally:
        pg_cur.close()
        pg_conn.close()

if __name__ == "__main__":
    execute_ingestion()
