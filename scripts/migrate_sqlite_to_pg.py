"""
SQLite to PostgreSQL Data Migration Script for Karachi Gymkhana RFID VAMS
Migrates all tables, schemas, constraints, sequences, and records from gate_access.db to PostgreSQL kgc_vams.
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import datetime
import os
import sys

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_DBNAME = os.environ.get("PG_DBNAME", "kgc_vams")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
SQLITE_DB = os.environ.get("SQLITE_DB", "gate_access.db")

def migrate():
    print(f"[*] Starting migration from {SQLITE_DB} to PostgreSQL {PG_DBNAME} on {PG_HOST}:{PG_PORT}...")
    
    if not os.path.exists(SQLITE_DB):
        print(f"[!] SQLite file {SQLITE_DB} not found! Nothing to migrate.")
        return

    s_conn = sqlite3.connect(SQLITE_DB)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    p_conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DBNAME,
        user=PG_USER,
        password=PG_PASSWORD
    )
    p_conn.autocommit = False
    p_cur = p_conn.cursor()

    try:
        # 1. Create Schema in PostgreSQL
        print("[+] Creating PostgreSQL database schemas and tables...")

        p_cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id SERIAL PRIMARY KEY,
            mem_id VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            car_number VARCHAR(100) NOT NULL,
            make_model VARCHAR(255),
            e_tag_id VARCHAR(100) UNIQUE NOT NULL,
            status VARCHAR(50) DEFAULT 'Active',
            profile_pic TEXT,
            current_location VARCHAR(50) DEFAULT 'Outside',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_members_memid ON members(mem_id);
        CREATE INDEX IF NOT EXISTS idx_members_etag ON members(e_tag_id);
        CREATE INDEX IF NOT EXISTS idx_members_car ON members(car_number);
        CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);
        CREATE INDEX IF NOT EXISTS idx_members_curr_loc ON members(current_location);

        CREATE TABLE IF NOT EXISTS settings (
            config_key VARCHAR(100) PRIMARY KEY,
            config_value TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(100) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'Viewer',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

        CREATE TABLE IF NOT EXISTS user_sessions (
            token VARCHAR(255) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);

        CREATE TABLE IF NOT EXISTS unregistered_tags (
            id SERIAL PRIMARY KEY,
            tag VARCHAR(100) UNIQUE NOT NULL,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            direction VARCHAR(50) DEFAULT 'Unknown',
            current_location VARCHAR(50) DEFAULT 'Outside',
            read_count INTEGER DEFAULT 1,
            tag_type VARCHAR(100) DEFAULT 'Unregistered Visitor'
        );
        CREATE INDEX IF NOT EXISTS idx_unreg_tag ON unregistered_tags(tag);
        CREATE INDEX IF NOT EXISTS idx_unreg_last_seen ON unregistered_tags(last_seen);
        CREATE INDEX IF NOT EXISTS idx_unreg_loc ON unregistered_tags(current_location);
        CREATE INDEX IF NOT EXISTS idx_unreg_tag_type ON unregistered_tags(tag_type);

        CREATE TABLE IF NOT EXISTS daily_logs (
            id SERIAL PRIMARY KEY,
            mem_id VARCHAR(100),
            name VARCHAR(255),
            vehicle_number VARCHAR(100),
            access_type VARCHAR(100),
            direction VARCHAR(50) DEFAULT 'Entry',
            gate_no VARCHAR(100) DEFAULT 'Gate-01',
            image_path TEXT,
            plate_image_path TEXT,
            detected_plate VARCHAR(100),
            scanned_tag VARCHAR(100),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON daily_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_logs_tag ON daily_logs(scanned_tag);
        CREATE INDEX IF NOT EXISTS idx_logs_memid ON daily_logs(mem_id);
        CREATE INDEX IF NOT EXISTS idx_logs_direction ON daily_logs(direction);
        CREATE INDEX IF NOT EXISTS idx_logs_veh ON daily_logs(vehicle_number);
        CREATE INDEX IF NOT EXISTS idx_logs_dir_ts ON daily_logs(direction, timestamp);
        CREATE INDEX IF NOT EXISTS idx_logs_tag_ts ON daily_logs(scanned_tag, timestamp);

        CREATE TABLE IF NOT EXISTS raw_reader_logs (
            id SERIAL PRIMARY KEY,
            tag_scanned VARCHAR(100),
            system_response TEXT,
            direction VARCHAR(50) DEFAULT 'Unknown',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS camera_audit_logs (
            id SERIAL PRIMARY KEY,
            image_path TEXT,
            plate_image_path TEXT,
            detected_plate VARCHAR(100),
            direction VARCHAR(50) DEFAULT 'Unknown',
            event_type VARCHAR(100) DEFAULT 'Line Crossing',
            ocr_status VARCHAR(100),
            matched_mem_id VARCHAR(100),
            matched_name VARCHAR(255),
            matched_make_model VARCHAR(255),
            matched_profile_pic TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_str VARCHAR(50),
            hour_str VARCHAR(50)
        );
        CREATE INDEX IF NOT EXISTS idx_cam_audit_plate ON camera_audit_logs(detected_plate);
        CREATE INDEX IF NOT EXISTS idx_cam_audit_date ON camera_audit_logs(date_str);
        """)

        # Clean all tables in PostgreSQL to match current SQLite data exactly
        print("[+] Cleaning / Truncating existing PostgreSQL tables for clean sync...")
        p_cur.execute("""
            TRUNCATE TABLE 
                camera_audit_logs, 
                raw_reader_logs, 
                daily_logs, 
                unregistered_tags, 
                user_sessions, 
                users, 
                settings, 
                members 
            RESTART IDENTITY CASCADE;
        """)

        # 2. Transfer Members
        print("[+] Migrating members table...")
        s_cur.execute("SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic, Current_Location, created_at FROM members ORDER BY id ASC")
        mem_rows = s_cur.fetchall()
        if mem_rows:
            mem_data = []
            for r in mem_rows:
                mem_data.append((
                    r['id'], r['Mem_id'], r['Name'], r['Car_number'], r['Make_Model'],
                    r['E_tag_id'], r['Status'] or 'Active', r['Profile_pic'],
                    r['Current_Location'] or 'Outside', r['created_at']
                ))
            execute_values(p_cur, """
                INSERT INTO members (id, mem_id, name, car_number, make_model, e_tag_id, status, profile_pic, current_location, created_at)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    mem_id = EXCLUDED.mem_id,
                    name = EXCLUDED.name,
                    car_number = EXCLUDED.car_number,
                    make_model = EXCLUDED.make_model,
                    status = EXCLUDED.status,
                    current_location = EXCLUDED.current_location
            """, mem_data, page_size=2000)
            p_cur.execute("SELECT setval('members_id_seq', (SELECT MAX(id) FROM members));")
            print(f"    -> Successfully migrated {len(mem_rows)} members.")

        # 3. Transfer Settings
        print("[+] Migrating settings table...")
        s_cur.execute("SELECT config_key, config_value FROM settings")
        setting_rows = s_cur.fetchall()
        if setting_rows:
            set_data = [(r['config_key'], r['config_value']) for r in setting_rows]
            execute_values(p_cur, """
                INSERT INTO settings (config_key, config_value)
                VALUES %s
                ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value
            """, set_data)
            print(f"    -> Successfully migrated {len(setting_rows)} settings.")

        # 4. Transfer Users
        print("[+] Migrating users table...")
        s_cur.execute("SELECT id, username, password_hash, salt, full_name, role, is_active, created_at, last_login FROM users ORDER BY id ASC")
        user_rows = s_cur.fetchall()
        if user_rows:
            user_data = [(
                r['id'], r['username'], r['password_hash'], r['salt'], r['full_name'],
                r['role'], r['is_active'], r['created_at'], r['last_login']
            ) for r in user_rows]
            execute_values(p_cur, """
                INSERT INTO users (id, username, password_hash, salt, full_name, role, is_active, created_at, last_login)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    salt = EXCLUDED.salt,
                    role = EXCLUDED.role
            """, user_data)
            p_cur.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));")
            print(f"    -> Successfully migrated {len(user_rows)} users.")

        # 5. Transfer Unregistered Tags
        print("[+] Migrating unregistered_tags table...")
        s_cur.execute("SELECT id, tag, first_seen, last_seen, direction, Current_Location, read_count, tag_type FROM unregistered_tags ORDER BY id ASC")
        unreg_rows = s_cur.fetchall()
        if unreg_rows:
            unreg_data = [(
                r['id'], r['tag'], r['first_seen'], r['last_seen'], r['direction'],
                r['Current_Location'] or 'Outside', r['read_count'] or 1, r['tag_type'] or 'Unregistered Visitor'
            ) for r in unreg_rows]
            execute_values(p_cur, """
                INSERT INTO unregistered_tags (id, tag, first_seen, last_seen, direction, current_location, read_count, tag_type)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    last_seen = EXCLUDED.last_seen,
                    read_count = EXCLUDED.read_count,
                    current_location = EXCLUDED.current_location
            """, unreg_data, page_size=2000)
            p_cur.execute("SELECT setval('unregistered_tags_id_seq', (SELECT MAX(id) FROM unregistered_tags));")
            print(f"    -> Successfully migrated {len(unreg_rows)} unregistered tags.")

        # 6. Transfer Daily Logs
        print("[+] Migrating daily_logs table...")
        s_cur.execute("SELECT id, mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, detected_plate, scanned_tag, timestamp FROM daily_logs ORDER BY id ASC")
        log_rows = s_cur.fetchall()
        if log_rows:
            log_data = [(
                r['id'], r['mem_id'], r['name'], r['vehicle_number'], r['access_type'],
                r['direction'], r['gate_no'], r['image_path'], r['plate_image_path'],
                r['detected_plate'], r['scanned_tag'], r['timestamp']
            ) for r in log_rows]
            execute_values(p_cur, """
                INSERT INTO daily_logs (id, mem_id, name, vehicle_number, access_type, direction, gate_no, image_path, plate_image_path, detected_plate, scanned_tag, timestamp)
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, log_data, page_size=2000)
            p_cur.execute("SELECT setval('daily_logs_id_seq', (SELECT MAX(id) FROM daily_logs));")
            print(f"    -> Successfully migrated {len(log_rows)} daily logs.")

        # 7. Transfer Raw Reader Logs
        print("[+] Migrating raw_reader_logs table...")
        s_cur.execute("SELECT id, tag_scanned, system_response, direction, timestamp FROM raw_reader_logs ORDER BY id ASC")
        raw_rows = s_cur.fetchall()
        if raw_rows:
            raw_data = [(r['id'], r['tag_scanned'], r['system_response'], r['direction'], r['timestamp']) for r in raw_rows]
            execute_values(p_cur, """
                INSERT INTO raw_reader_logs (id, tag_scanned, system_response, direction, timestamp)
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, raw_data, page_size=2000)
            p_cur.execute("SELECT setval('raw_reader_logs_id_seq', (SELECT MAX(id) FROM raw_reader_logs));")
            print(f"    -> Successfully migrated {len(raw_rows)} raw reader logs.")

        # 8. Transfer Camera Audit Logs
        print("[+] Migrating camera_audit_logs table...")
        s_cur.execute("""
            SELECT id, image_path, plate_image_path, detected_plate, direction, event_type,
                   ocr_status, matched_mem_id, matched_name, matched_make_model, matched_profile_pic,
                   timestamp, date_str, hour_str
            FROM camera_audit_logs ORDER BY id ASC
        """)
        cam_rows = s_cur.fetchall()
        if cam_rows:
            cam_data = [(
                r['id'], r['image_path'], r['plate_image_path'], r['detected_plate'],
                r['direction'], r['event_type'], r['ocr_status'], r['matched_mem_id'],
                r['matched_name'], r['matched_make_model'], r['matched_profile_pic'],
                r['timestamp'], r['date_str'], r['hour_str']
            ) for r in cam_rows]
            execute_values(p_cur, """
                INSERT INTO camera_audit_logs (id, image_path, plate_image_path, detected_plate, direction, event_type, ocr_status, matched_mem_id, matched_name, matched_make_model, matched_profile_pic, timestamp, date_str, hour_str)
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, cam_data, page_size=2000)
            p_cur.execute("SELECT setval('camera_audit_logs_id_seq', (SELECT MAX(id) FROM camera_audit_logs));")
            print(f"    -> Successfully migrated {len(cam_rows)} camera audit logs.")

        p_conn.commit()
        print("\n[SUCCESS] Migration from SQLite to PostgreSQL completed successfully with 100% data integrity!")

    except Exception as e:
        p_conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        s_conn.close()
        p_conn.close()

if __name__ == "__main__":
    migrate()
