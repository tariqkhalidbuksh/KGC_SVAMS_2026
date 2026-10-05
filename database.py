import sqlite3
import config

def get_db_connection() -> sqlite3.Connection:
    import sys
    app_module = sys.modules.get('app')
    db_file = getattr(app_module, 'DB_FILE', getattr(config, 'DB_FILE', 'gate_access.db'))
    conn = sqlite3.connect(db_file, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA temp_store = MEMORY")
    except Exception:
        pass
    return conn

def init_db():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                table_info = conn.execute("PRAGMA table_info(members)").fetchall()
                if table_info:
                    mem_id_pk = any(col['name'] == 'Mem_id' and col['pk'] > 0 for col in table_info)
                    if mem_id_pk:
                        conn.execute("ALTER TABLE members RENAME TO members_old")
                        conn.execute("""CREATE TABLE members (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            Mem_id TEXT NOT NULL,
                            Name TEXT NOT NULL,
                            Car_number TEXT NOT NULL,
                            Make_Model TEXT,
                            E_tag_id TEXT UNIQUE NOT NULL,
                            Status TEXT DEFAULT 'Active',
                            Profile_pic TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
                        conn.execute("""INSERT OR IGNORE INTO members
                            (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic, created_at)
                            SELECT Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic, created_at FROM members_old""")
                        conn.execute("DROP TABLE members_old")

                conn.execute("""CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Mem_id TEXT NOT NULL,
                    Name TEXT NOT NULL,
                    Car_number TEXT NOT NULL,
                    Make_Model TEXT,
                    E_tag_id TEXT UNIQUE NOT NULL,
                    Status TEXT DEFAULT 'Active',
                    Profile_pic TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_memid ON members(Mem_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_etag ON members(E_tag_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_car ON members(Car_number)")

                conn.execute("""CREATE TABLE IF NOT EXISTS daily_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mem_id TEXT,
                    name TEXT,
                    vehicle_number TEXT,
                    access_type TEXT,
                    direction TEXT DEFAULT 'Entry',
                    gate_no TEXT DEFAULT 'Gate-01',
                    image_path TEXT,
                    plate_image_path TEXT,
                    scanned_tag TEXT,
                    timestamp DATETIME DEFAULT (datetime('now', 'localtime')))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON daily_logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tag ON daily_logs(scanned_tag)")

                conn.execute("""CREATE TABLE IF NOT EXISTS raw_reader_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_scanned TEXT,
                    system_response TEXT,
                    direction TEXT DEFAULT 'Unknown',
                    timestamp DATETIME DEFAULT (datetime('now', 'localtime')))""")

                conn.execute("""CREATE TABLE IF NOT EXISTS camera_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_path TEXT,
                    plate_image_path TEXT,
                    direction TEXT DEFAULT 'Unknown',
                    event_type TEXT DEFAULT 'Line Crossing',
                    timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                    date_str TEXT,
                    hour_str TEXT)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cam_audit_date ON camera_audit_logs(date_str)")

                cam_cols = [col['name'] for col in conn.execute("PRAGMA table_info(camera_audit_logs)").fetchall()]
                if 'plate_image_path' not in cam_cols:
                    conn.execute("ALTER TABLE camera_audit_logs ADD COLUMN plate_image_path TEXT")

                conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT)""")
                
                default_settings = {
                    'traffic_msg': 'SPEED LIMIT 5 KM/H,WELCOME TO KARACHI GYMKHANA CLUB',
                    'club_name': 'Karachi Gymkhana Club',
                    'parking_capacity': '500',
                    'dahua_cam_url': 'rtsp://admin:TheKG1886@192.168.0.218:554/cam/realmonitor?channel=1&subtype=0',
                    'hikvision_cam_url': 'rtsp://admin:TheKG1886@192.168.0.220:554/Streaming/Channels/101',
                    'entry_reader_ip': '192.168.0.217',
                    'exit_reader_ip': '192.168.0.216',
                }
                for key, val in default_settings.items():
                    conn.execute("INSERT OR IGNORE INTO settings (config_key, config_value) VALUES (?, ?)", (key, val))

                conn.execute("UPDATE daily_logs SET timestamp = datetime(timestamp, '+5 hours') WHERE timestamp LIKE '2026-10-02 16:%'")
        finally:
            conn.close()

def get_setting(key: str, default: str = "") -> str:
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT config_value FROM settings WHERE config_key = ?", (key,)).fetchone()
            return row['config_value'] if row else default
        finally:
            conn.close()

def set_setting(key: str, value: str):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("INSERT OR REPLACE INTO settings (config_key, config_value) VALUES (?, ?)", (key, value))
        finally:
            conn.close()
