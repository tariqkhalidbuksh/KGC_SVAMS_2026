"""
Database Connection & Management Module for Karachi Gymkhana RFID VAMS
Supports Enterprise PostgreSQL Engine with High-Performance Threaded Connection Pooling,
Dynamic Query Translation (SQLite-to-PostgreSQL), Case-Insensitive DictRow mapping,
and Auto-Fallback.
"""

import os
import sys
import re
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import config

# PostgreSQL Connection Configuration
PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DBNAME = os.environ.get("PG_DBNAME", "kgc_vams")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

_PG_POOL: ThreadedConnectionPool | None = None
_POOL_LOCK = threading.Lock()

def ensure_pg_database_exists():
    """Ensures the target PostgreSQL database exists; creates it via 'postgres' maintenance DB if missing."""
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname="postgres",
            user=PG_USER,
            password=PG_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DBNAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{PG_DBNAME}"')
        cur.close()
        conn.close()
    except Exception:
        pass

def get_pg_pool() -> ThreadedConnectionPool | None:
    global _PG_POOL
    if _PG_POOL is None:
        with _POOL_LOCK:
            if _PG_POOL is None:
                try:
                    _PG_POOL = ThreadedConnectionPool(
                        minconn=2,
                        maxconn=25,
                        host=PG_HOST,
                        port=PG_PORT,
                        dbname=PG_DBNAME,
                        user=PG_USER,
                        password=PG_PASSWORD
                    )
                except psycopg2.OperationalError as op_err:
                    err_str = str(op_err).lower()
                    if "does not exist" in err_str:
                        ensure_pg_database_exists()
                        try:
                            _PG_POOL = ThreadedConnectionPool(
                                minconn=2,
                                maxconn=25,
                                host=PG_HOST,
                                port=PG_PORT,
                                dbname=PG_DBNAME,
                                user=PG_USER,
                                password=PG_PASSWORD
                            )
                        except Exception:
                            return None
                    else:
                        # Cannot connect to PostgreSQL server (e.g. connection refused)
                        return None
    return _PG_POOL

class CaseInsensitiveRow(dict):
    """
    Emulates sqlite3.Row behavior on PostgreSQL:
    Supports column access by case-insensitive name (row['Mem_id'], row['mem_id']),
    positional integer index (row[0]), and dict methods (.get()).
    """
    __slots__ = ('_items',)

    def __init__(self, data=None, description=None):
        super().__init__()
        self._items = []
        if data is not None and description is not None:
            for idx, col in enumerate(description):
                val = data[idx]
                self._items.append(val)
                raw_name = str(col.name)
                low_name = raw_name.lower()
                self[low_name] = val
                self[raw_name] = val
                # Populate common legacy camel/title casing used across existing endpoints
                self[low_name.title()] = val
                if low_name == 'e_tag_id':
                    self['E_tag_id'] = val
                    self['e_tag_id'] = val
                elif low_name == 'mem_id':
                    self['Mem_id'] = val
                    self['mem_id'] = val
                elif low_name == 'car_number':
                    self['Car_number'] = val
                    self['car_number'] = val
                elif low_name == 'make_model':
                    self['Make_Model'] = val
                    self['make_model'] = val
                elif low_name == 'profile_pic':
                    self['Profile_pic'] = val
                    self['profile_pic'] = val
                elif low_name == 'current_location':
                    self['Current_Location'] = val
                    self['current_location'] = val
                elif low_name == 'name':
                    self['Name'] = val
                    self['name'] = val
                elif low_name == 'status':
                    self['Status'] = val
                    self['status'] = val

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        return super().__getitem__(str(key).lower())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)

    def keys(self):
        return super().keys()

    def values(self):
        return tuple(self._items)

    def items(self):
        return super().items()

class PostgresCursorWrapper:
    """Wraps psycopg2 cursor to mirror sqlite3 cursor semantics (lastrowid, fetchone, etc.)."""
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount if cursor else 0
        self.description = cursor.description if cursor else None

    def fetchone(self):
        if not self._cursor or not self._cursor.description:
            return None
        data = self._cursor.fetchone()
        if data is None:
            return None
        return CaseInsensitiveRow(data, self._cursor.description)

    def fetchall(self):
        if not self._cursor or not self._cursor.description:
            return []
        data = self._cursor.fetchall()
        return [CaseInsensitiveRow(d, self._cursor.description) for d in data]

    def fetchmany(self, size=None):
        if not self._cursor or not self._cursor.description:
            return []
        data = self._cursor.fetchmany(size)
        return [CaseInsensitiveRow(d, self._cursor.description) for d in data]

    def close(self):
        if self._cursor:
            self._cursor.close()

    def __iter__(self):
        if not self._cursor or not self._cursor.description:
            return iter([])
        for row in self._cursor:
            yield CaseInsensitiveRow(row, self._cursor.description)

class PostgresConnectionWrapper:
    """
    Transparent Connection Adapter mapping sqlite3 calls directly into PostgreSQL.
    Provides automatic query translation (? -> %s, date/strftime/now translation),
    transaction management, and pooling.
    """
    def __init__(self, raw_conn, pool=None):
        self._conn = raw_conn
        self._pool = pool
        self._in_transaction = False

    @staticmethod
    def _translate_query(sql: str) -> tuple[str, bool]:
        """Translates SQLite query syntax into PostgreSQL dialect."""
        q = sql.strip()
        needs_returning = False

        # 1. Skip sqlite_sequence table resets
        if "sqlite_sequence" in q.lower():
            return "SELECT 1", False

        # 2. Skip SQLite PRAGMA statements
        if q.lower().startswith("pragma"):
            return "SELECT 1", False

        # 3. Translate INSERT OR REPLACE INTO and INSERT OR IGNORE INTO
        if re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+settings", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+settings\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO settings (\1) VALUES (\2) ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value",
                q,
                flags=re.IGNORECASE
            )
        elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+unregistered_tags", q, re.IGNORECASE):
            m = re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+unregistered_tags\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", q, re.IGNORECASE)
            if m:
                cols = [c.strip() for c in m.group(1).split(',')]
                update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c.lower() not in ('id', 'tag')])
                q = f"INSERT INTO unregistered_tags ({m.group(1)}) VALUES ({m.group(2)}) ON CONFLICT (tag) DO UPDATE SET {update_set}"
        elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+members", q, re.IGNORECASE):
            m = re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+members\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", q, re.IGNORECASE)
            if m:
                cols = [c.strip() for c in m.group(1).split(',')]
                update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c.lower() not in ('id', 'e_tag_id')])
                q = f"INSERT INTO members ({m.group(1)}) VALUES ({m.group(2)}) ON CONFLICT (e_tag_id) DO UPDATE SET {update_set}"
        elif re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", q, re.IGNORECASE):
            q = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", q, flags=re.IGNORECASE).rstrip(";") + " ON CONFLICT DO NOTHING"

        # 4. Translate datetime/date with interval expressions
        q = re.sub(
            r"datetime\('now'(?:,\s*'localtime')?,\s*'-(\d+)\s*([a-zA-Z]+)'\)",
            r"(CURRENT_TIMESTAMP - INTERVAL '\1 \2')",
            q,
            flags=re.IGNORECASE
        )
        q = re.sub(
            r"datetime\('now'(?:,\s*'localtime')?,\s*'\+(\d+)\s*([a-zA-Z]+)'\)",
            r"(CURRENT_TIMESTAMP + INTERVAL '\1 \2')",
            q,
            flags=re.IGNORECASE
        )
        q = re.sub(
            r"date\('now'(?:,\s*'localtime')?,\s*'-(\d+)\s*([a-zA-Z]+)'\)",
            r"(CURRENT_DATE - INTERVAL '\1 \2')::date",
            q,
            flags=re.IGNORECASE
        )
        q = re.sub(
            r"date\('now'(?:,\s*'localtime')?,\s*'\+(\d+)\s*([a-zA-Z]+)'\)",
            r"(CURRENT_DATE + INTERVAL '\1 \2')::date",
            q,
            flags=re.IGNORECASE
        )
        # 5. Translate simple date('now') and datetime('now')
        q = re.sub(r"date\('now'(?:,\s*'localtime')?\)", "CURRENT_DATE", q, flags=re.IGNORECASE)
        q = re.sub(r"datetime\('now'(?:,\s*'localtime')?\)", "CURRENT_TIMESTAMP", q, flags=re.IGNORECASE)
        # 5b. Translate date(timestamp) to timestamp::date
        q = re.sub(r"\bdate\(([a-zA-Z0-9_\.]+)\)", r"(\1::date)", q, flags=re.IGNORECASE)
        # 5c. Translate strftime('%H', timestamp) to TO_CHAR(timestamp, 'HH24')
        q = re.sub(r"strftime\('%H',\s*([a-zA-Z0-9_\.]+)\)", r"TO_CHAR(\1, 'HH24')", q, flags=re.IGNORECASE)
        # 5d. Translate strftime('%Y-%m-%d', timestamp) to TO_CHAR(timestamp, 'YYYY-MM-DD')
        q = re.sub(r"strftime\('%Y-%m-%d',\s*([a-zA-Z0-9_\.]+)\)", r"TO_CHAR(\1, 'YYYY-MM-DD')", q, flags=re.IGNORECASE)

        # 6. Translate VACUUM
        if q.upper() == "VACUUM":
            return "VACUUM", False

        # 7. Convert INSERT queries to RETURNING id if table has auto-increment primary key
        if q.strip().upper().startswith("INSERT INTO") and "RETURNING" not in q.upper():
            tbl_match = re.search(r"INSERT\s+INTO\s+([a-zA-Z0-9_]+)", q, re.IGNORECASE)
            if tbl_match:
                tbl_name = tbl_match.group(1).lower()
                if tbl_name in ("daily_logs", "raw_reader_logs", "camera_audit_logs", "unregistered_tags", "members", "users"):
                    q = q.rstrip(";") + " RETURNING id"
                    needs_returning = True

        # 8. Convert ? parameter placeholders into %s (ignoring literal question marks in strings)
        parts = []
        in_str = False
        quote_char = None
        for char in q:
            if char in ("'", '"'):
                if not in_str:
                    in_str = True
                    quote_char = char
                elif quote_char == char:
                    in_str = False
                    quote_char = None
                if char == '%':
                    parts.append('%%')
                else:
                    parts.append(char)
            elif char == '%':
                # Literal % outside of string
                parts.append('%%')
            elif char == '?' and not in_str:
                parts.append('%s')
            else:
                parts.append(char)

        return "".join(parts), needs_returning

    def execute(self, sql: str, parameters=None):
        pg_sql, needs_returning = self._translate_query(sql)
        cur = self._conn.cursor()
        try:
            if parameters:
                cur.execute(pg_sql, parameters)
            else:
                cur.execute(pg_sql)

            lastrowid = None
            if needs_returning and cur.description:
                row = cur.fetchone()
                if row:
                    lastrowid = row[0]

            return PostgresCursorWrapper(cur, lastrowid=lastrowid)
        except Exception:
            cur.close()
            raise

    def executemany(self, sql: str, seq_of_parameters):
        pg_sql, _ = self._translate_query(sql)
        cur = self._conn.cursor()
        try:
            cur.executemany(pg_sql, seq_of_parameters)
            return PostgresCursorWrapper(cur)
        except Exception:
            cur.close()
            raise

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._pool and self._conn:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._pool.putconn(self._conn)
            self._conn = None
            self._pool = None
        elif self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        return False

def _connect_sqlite(db_file: str):
    """Initializes a case-insensitive SQLite connection matching the PostgreSQL adapter interface."""
    import sqlite3
    conn = sqlite3.connect(db_file, check_same_thread=False, timeout=15.0)
    class SqliteColDesc:
        def __init__(self, name):
            self.name = name
    def sqlite_case_insensitive_factory(cursor, row):
        desc = [SqliteColDesc(col[0]) for col in cursor.description]
        return CaseInsensitiveRow(row, desc)
    conn.row_factory = sqlite_case_insensitive_factory
    return conn

def get_db_connection():
    """
    Returns an active database connection.
    Connects to high-performance PostgreSQL (kgc_vams) via Connection Pool if available.
    If PostgreSQL is unreachable, offline, not installed, or connection refused,
    transparently falls back to SQLite (gate_access.db) with 0 crash and 0 downtime.
    """
    import sys
    app_module = sys.modules.get('app')
    custom_db = getattr(app_module, 'DB_FILE', getattr(config, 'DB_FILE', 'gate_access.db'))

    # If test specifies an explicit non-default sqlite test database path (e.g. pytest tmp_path)
    if custom_db and custom_db != "gate_access.db" and (".db" in custom_db or "test" in custom_db):
        return _connect_sqlite(custom_db)

    # Attempt PostgreSQL Connection
    if getattr(config, 'USE_POSTGRES', True):
        try:
            pool = get_pg_pool()
            if pool is not None:
                raw_conn = pool.getconn()
                raw_conn.autocommit = False
                return PostgresConnectionWrapper(raw_conn, pool=pool)
        except Exception:
            pass

    # Seamless SQLite Fallback
    return _connect_sqlite(custom_db or "gate_access.db")

def init_db():
    """
    Initializes PostgreSQL tables, schema constraints, indices, and compatibility functions.
    """
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                is_pg = getattr(conn, "_conn", None) is not None
                pk_id = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
                ts_type = "TIMESTAMP" if is_pg else "DATETIME"

                if is_pg:
                    # 1. Compatibility function: strftime
                    conn.execute("""
                    CREATE OR REPLACE FUNCTION strftime(fmt text, ts timestamp) RETURNS text AS $$
                    BEGIN
                        IF fmt = '%H' THEN
                            RETURN to_char(ts, 'HH24');
                        ELSIF fmt = '%Y-%m-%d' THEN
                            RETURN to_char(ts, 'YYYY-MM-DD');
                        ELSE
                            RETURN to_char(ts, 'YYYY-MM-DD HH24:MI:SS');
                        END IF;
                    END;
                    $$ LANGUAGE plpgsql IMMUTABLE;
                    """)

                # 2. Members Table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS members (
                    id {pk_id},
                    mem_id VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    car_number VARCHAR(100) NOT NULL,
                    make_model VARCHAR(255),
                    e_tag_id VARCHAR(100) UNIQUE NOT NULL,
                    status VARCHAR(50) DEFAULT 'Active',
                    profile_pic TEXT,
                    current_location VARCHAR(50) DEFAULT 'Outside',
                    created_at {ts_type} DEFAULT CURRENT_TIMESTAMP
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_memid ON members(mem_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_etag ON members(e_tag_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_car ON members(car_number)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_status ON members(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_members_curr_loc ON members(current_location)")

                # 3. Settings Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    config_key VARCHAR(100) PRIMARY KEY,
                    config_value TEXT
                )""")

                # Default Settings
                default_settings = {
                    'traffic_msg': 'SPEED LIMIT 5 KM/H,WELCOME TO KARACHI GYMKHANA CLUB',
                    'club_name': 'Karachi Gymkhana Club',
                    'parking_capacity': '500',
                    'hikvision_cam_url': 'rtsp://admin:TheKG1886@192.168.0.220:554/Streaming/Channels/101',
                    'dahua_cam_url': 'rtsp://admin:admin123@192.168.0.221:554/cam/realmonitor?channel=1&subtype=0',
                    'entry_reader_ip': '192.168.0.217',
                    'exit_reader_ip': '192.168.0.216',
                    'entry_reader_name': 'Gate-01 Entry Reader',
                    'exit_reader_name': 'Gate-01 Exit Reader',
                    'clubroad_entry_reader_ip': '',
                    'clubroad_exit_reader_ip': '',
                    'clubroad_entry_reader_name': 'Main Gate (Club Road) Entry Reader',
                    'clubroad_exit_reader_name': 'Main Gate (Club Road) Exit Reader',
                    'rfid_cooldown_seconds': '60',
                }
                for key, val in default_settings.items():
                    if is_pg:
                        conn.execute("INSERT INTO settings (config_key, config_value) VALUES (?, ?) ON CONFLICT (config_key) DO NOTHING", (key, val))
                    else:
                        conn.execute("INSERT OR IGNORE INTO settings (config_key, config_value) VALUES (?, ?)", (key, val))

                # 4. Unregistered Tags Table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS unregistered_tags (
                    id {pk_id},
                    tag VARCHAR(100) UNIQUE NOT NULL,
                    first_seen {ts_type} DEFAULT CURRENT_TIMESTAMP,
                    last_seen {ts_type} DEFAULT CURRENT_TIMESTAMP,
                    direction VARCHAR(50) DEFAULT 'Unknown',
                    current_location VARCHAR(50) DEFAULT 'Outside',
                    read_count INTEGER DEFAULT 1,
                    tag_type VARCHAR(100) DEFAULT 'Unregistered Visitor'
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_tag ON unregistered_tags(tag)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_last_seen ON unregistered_tags(last_seen)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_loc ON unregistered_tags(current_location)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_tag_type ON unregistered_tags(tag_type)")

                # 5. Daily Logs Table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS daily_logs (
                    id {pk_id},
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
                    timestamp {ts_type} DEFAULT CURRENT_TIMESTAMP
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON daily_logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tag ON daily_logs(scanned_tag)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_memid ON daily_logs(mem_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_direction ON daily_logs(direction)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_veh ON daily_logs(vehicle_number)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_dir_ts ON daily_logs(direction, timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tag_ts ON daily_logs(scanned_tag, timestamp)")

                # 6. Raw Reader Logs Table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS raw_reader_logs (
                    id {pk_id},
                    tag_scanned VARCHAR(100),
                    system_response TEXT,
                    direction VARCHAR(50) DEFAULT 'Unknown',
                    timestamp {ts_type} DEFAULT CURRENT_TIMESTAMP
                )""")

                # 7. Camera Audit Logs Table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS camera_audit_logs (
                    id {pk_id},
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
                    timestamp {ts_type} DEFAULT CURRENT_TIMESTAMP,
                    date_str VARCHAR(50),
                    hour_str VARCHAR(50)
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cam_audit_plate ON camera_audit_logs(detected_plate)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cam_audit_date ON camera_audit_logs(date_str)")
        finally:
            conn.close()

    # Initialize authentication & user accounts tables
    from services.auth_service import init_auth_tables
    init_auth_tables()

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
                conn.execute("""
                INSERT INTO settings (config_key, config_value)
                VALUES (?, ?)
                ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value
                """, (key, value))
        finally:
            conn.close()
