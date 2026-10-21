"""
Database Connection & Management Module for Karachi Gymkhana RFID VAMS
Enterprise PostgreSQL 14.15 Engine with High-Performance Threaded Connection Pooling,
Dynamic Parameter Adaptation, Case-Insensitive DictRow mapping, and High-Speed RAM Caching.
SQLite is 100% eliminated from this application.
"""

import os
import sys
import re
import time
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

_POOLS: dict[str, ThreadedConnectionPool] = {}
_POOL_LOCK = threading.Lock()

# Ultra-fast in-memory settings cache to eliminate DB lock contention across reader/camera loops
_SETTINGS_CACHE: dict[str, tuple[str, float]] = {}
_SETTINGS_LOCK = threading.Lock()
SETTINGS_CACHE_TTL = 15.0  # 15 seconds cache

def is_pg_service_responsive() -> bool:
    """Fast non-blocking 50ms socket probe to verify PostgreSQL is listening."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        res = s.connect_ex((PG_HOST, PG_PORT))
        s.close()
        return res == 0
    except Exception:
        return False

def ensure_pg_database_exists(dbname: str = None):
    """Ensures the target PostgreSQL database exists; creates it via 'postgres' maintenance DB if missing."""
    target_db = dbname or PG_DBNAME
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname="postgres",
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=3
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{target_db}"')
        cur.close()
        conn.close()
    except Exception:
        pass

def get_pg_pool(dbname: str = None) -> ThreadedConnectionPool:
    global _POOLS
    target_db = dbname or os.environ.get("PG_DBNAME", PG_DBNAME)

    if target_db in _POOLS:
        return _POOLS[target_db]

    with _POOL_LOCK:
        if target_db in _POOLS:
            return _POOLS[target_db]

        if not is_pg_service_responsive():
            raise RuntimeError(
                f"PostgreSQL service is not responding on {PG_HOST}:{PG_PORT}. "
                f"Please ensure PostgreSQL server is running and listening on port {PG_PORT}."
            )

        try:
            pool = ThreadedConnectionPool(
                minconn=4,
                maxconn=100,
                host=PG_HOST,
                port=PG_PORT,
                dbname=target_db,
                user=PG_USER,
                password=PG_PASSWORD,
                connect_timeout=3
            )
            _POOLS[target_db] = pool
            return pool
        except psycopg2.OperationalError as op_err:
            err_str = str(op_err).lower()
            if "does not exist" in err_str:
                ensure_pg_database_exists(target_db)
                pool = ThreadedConnectionPool(
                    minconn=4,
                    maxconn=100,
                    host=PG_HOST,
                    port=PG_PORT,
                    dbname=target_db,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    connect_timeout=3
                )
                _POOLS[target_db] = pool
                return pool
            raise RuntimeError(f"PostgreSQL connection failed to {PG_HOST}:{PG_PORT}/{target_db}: {op_err}")
        except Exception as e:
            raise RuntimeError(f"PostgreSQL connection failed to {PG_HOST}:{PG_PORT}/{target_db}: {e}")

class CaseInsensitiveRow(dict):
    """
    Case-Insensitive DictRow for PostgreSQL queries:
    Supports column access by case-insensitive name (row['Mem_id'], row['mem_id']),
    positional integer index (row[0]), and dict methods (.get()).
    """
    __slots__ = ('_items',)

    _CANONICAL_KEYS = {
        'mem_id': 'Mem_id',
        'name': 'Name',
        'car_number': 'Car_number',
        'make_model': 'Make_Model',
        'e_tag_id': 'E_tag_id',
        'status': 'Status',
        'profile_pic': 'Profile_pic',
        'current_location': 'Current_Location',
    }

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
                canonical = self._CANONICAL_KEYS.get(low_name)
                if canonical:
                    self[canonical] = val

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        if isinstance(key, str):
            val = super().get(key.lower())
            if val is not None or key.lower() in self:
                return val
            return super().__getitem__(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, int):
            if 0 <= key < len(self._items):
                return self._items[key]
            return default
        if isinstance(key, str):
            val = super().get(key.lower())
            if val is not None or key.lower() in self:
                return val
            return super().get(key, default)
        return super().get(key, default)

    def keys(self):
        return super().keys()

    def values(self):
        return self._items

    def items(self):
        return super().items()

class PostgresCursorWrapper:
    """Wraps psycopg2 cursor with row_factory, lastrowid, fetchone, fetchall, and execute semantics."""
    def __init__(self, raw_cursor, lastrowid=None, conn_wrapper=None):
        self._cursor = raw_cursor
        self.lastrowid = lastrowid
        self._conn_wrapper = conn_wrapper
        self.rowcount = raw_cursor.rowcount if raw_cursor else 0
        self.description = raw_cursor.description if raw_cursor else None

    def execute(self, sql: str, parameters=None):
        if self._conn_wrapper:
            res = self._conn_wrapper.execute(sql, parameters)
            self._cursor = res._cursor
            self.lastrowid = res.lastrowid
            self.rowcount = res.rowcount
            self.description = res.description
            return self
        pg_sql, _ = PostgresConnectionWrapper._translate_query(sql)
        if parameters:
            self._cursor.execute(pg_sql, parameters)
        else:
            self._cursor.execute(pg_sql)
        self.rowcount = self._cursor.rowcount
        self.description = self._cursor.description
        return self

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
    High-Performance Connection Adapter for PostgreSQL.
    Provides automatic parameter translation (? -> %s, datetime/strftime translation),
    transaction management, and connection pool integration.
    """
    def __init__(self, raw_conn, pool=None):
        self._conn = raw_conn
        self._pool = pool
        self._in_transaction = False

    @staticmethod
    def _translate_query(sql: str) -> tuple[str, bool]:
        """Translates query parameters (? -> %s) and dialect expressions into PostgreSQL."""
        q = sql.strip()
        needs_returning = False

        # 1. Skip sqlite_sequence and PRAGMA table resets
        if "sqlite_sequence" in q.lower() or q.lower().startswith("pragma"):
            return "SELECT 1", False

        # 2. Translate INSERT OR REPLACE INTO settings
        if re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+settings", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+settings\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO settings (\1) VALUES (\2) ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value",
                q,
                flags=re.IGNORECASE
            )
        elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+unregistered_tags", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+unregistered_tags\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO unregistered_tags (\1) VALUES (\2) ON CONFLICT (tag) DO UPDATE SET last_seen = EXCLUDED.last_seen, read_count = unregistered_tags.read_count + 1",
                q,
                flags=re.IGNORECASE
            )
        elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+members", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+members\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO members (\1) VALUES (\2) ON CONFLICT (e_tag_id) DO UPDATE SET mem_id = EXCLUDED.mem_id, name = EXCLUDED.name, car_number = EXCLUDED.car_number, make_model = EXCLUDED.make_model, status = EXCLUDED.status, profile_pic = EXCLUDED.profile_pic, current_location = EXCLUDED.current_location",
                q,
                flags=re.IGNORECASE
            )
        elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+users", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+users\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO users (\1) VALUES (\2) ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, full_name = EXCLUDED.full_name, role = EXCLUDED.role",
                q,
                flags=re.IGNORECASE
            )
        elif re.search(r"INSERT\s+OR\s+IGNORE\s+INTO\s+([a-zA-Z0-9_]+)", q, re.IGNORECASE):
            q = re.sub(
                r"INSERT\s+OR\s+IGNORE\s+INTO\s+([a-zA-Z0-9_]+)",
                r"INSERT INTO \1",
                q,
                flags=re.IGNORECASE
            ) + " ON CONFLICT DO NOTHING"

        # 3. Translate SQLite date/time functions
        def _replace_date(m):
            args_str = m.group(1) or ""
            interval_match = re.search(r"'-(\d+)\s+([a-zA-Z]+)'", args_str)
            if interval_match:
                num, unit = interval_match.groups()
                return f"(CURRENT_DATE - INTERVAL '{num} {unit}')"
            return "CURRENT_DATE"

        def _replace_datetime(m):
            args_str = m.group(1) or ""
            interval_match = re.search(r"'-(\d+)\s+([a-zA-Z]+)'", args_str)
            if interval_match:
                num, unit = interval_match.groups()
                return f"(CURRENT_TIMESTAMP - INTERVAL '{num} {unit}')"
            return "CURRENT_TIMESTAMP"

        q = re.sub(r"date\(\s*'now'\s*([^)]*)\)", _replace_date, q, flags=re.IGNORECASE)
        q = re.sub(r"datetime\(\s*'now'\s*([^)]*)\)", _replace_datetime, q, flags=re.IGNORECASE)

        # 3b. Translate timestamp LIKE -> CAST(timestamp AS TEXT) LIKE
        q = re.sub(r"([a-zA-Z0-9_.]*timestamp)\s+LIKE", r"CAST(\1 AS TEXT) LIKE", q, flags=re.IGNORECASE)

        # 3c. Translate string concatenation used as timestamp: (? || ' 10:00:00') -> CAST(? || ' 10:00:00' AS TIMESTAMP)
        q = re.sub(r"(\?\s*\|\|\s*'[^']*')", r"CAST(\1 AS TIMESTAMP)", q)

        # 4. If query is INSERT on table with auto-id, append RETURNING id
        is_insert = bool(re.match(r"^\s*INSERT\s+INTO\s+(daily_logs|raw_reader_logs|camera_audit_logs|members|users)", q, re.IGNORECASE))
        if is_insert and "RETURNING" not in q.upper():
            q = q.rstrip(";") + " RETURNING id"
            needs_returning = True

        # 5. Convert ? parameter placeholders to %s and escape literal % to %% for psycopg2
        parts = []
        in_str = False
        str_char = ''
        i = 0
        while i < len(q):
            char = q[i]
            if char in ("'", '"'):
                if not in_str:
                    in_str = True
                    str_char = char
                elif char == str_char:
                    in_str = False
                parts.append(char)
            elif char == '%':
                if i + 1 < len(q) and q[i + 1] == '%':
                    parts.append('%%')
                    i += 1
                else:
                    parts.append('%%')
            elif char == '?' and not in_str:
                parts.append('%s')
            else:
                parts.append(char)
            i += 1

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

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor(), conn_wrapper=self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        return False

def get_db_connection(dbname: str = None):
    """
    Returns an active database connection exclusively from PostgreSQL ThreadedConnectionPool.
    SQLite is completely eliminated from the architecture.
    """
    import sys
    app_module = sys.modules.get('app')
    custom_db = getattr(app_module, 'DB_FILE', getattr(config, 'DB_FILE', ''))

    if not dbname:
        if custom_db and ("test" in str(custom_db).lower() or "qa" in str(custom_db).lower()):
            target_db = "kgc_vams_test"
        else:
            target_db = os.environ.get("PG_DBNAME", PG_DBNAME)
    else:
        target_db = dbname

    pool = get_pg_pool(target_db)
    raw_conn = pool.getconn()
    raw_conn.autocommit = False
    return PostgresConnectionWrapper(raw_conn, pool=pool)

def init_db(dbname: str = None):
    """
    Initializes PostgreSQL tables, schema constraints, indices, and compatibility functions.
    Pure PostgreSQL 14.15 enterprise architecture.
    """
    with config.DB_LOCK:
        conn = get_db_connection(dbname=dbname)
        try:
            with conn:
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
                conn.execute("""
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
                    'bulk_exit_exceptions': '[]'
                }
                for key, val in default_settings.items():
                    conn.execute("INSERT INTO settings (config_key, config_value) VALUES (?, ?) ON CONFLICT (config_key) DO NOTHING", (key, val))

                # 4. Unregistered Tags Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS unregistered_tags (
                    id SERIAL PRIMARY KEY,
                    tag VARCHAR(100) UNIQUE NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    direction VARCHAR(50) DEFAULT 'Unknown',
                    current_location VARCHAR(50) DEFAULT 'Outside',
                    read_count INTEGER DEFAULT 1,
                    tag_type VARCHAR(100) DEFAULT 'Unregistered Visitor'
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_tag ON unregistered_tags(tag)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_last_seen ON unregistered_tags(last_seen)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_loc ON unregistered_tags(current_location)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_unreg_tag_type ON unregistered_tags(tag_type)")

                # 5. Daily Activity Logs Table
                conn.execute("""
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
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON daily_logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tag ON daily_logs(scanned_tag)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_memid ON daily_logs(mem_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_direction ON daily_logs(direction)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_veh ON daily_logs(vehicle_number)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_dir_ts ON daily_logs(direction, timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tag_ts ON daily_logs(scanned_tag, timestamp)")

                # 6. Raw Reader Logs Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_reader_logs (
                    id SERIAL PRIMARY KEY,
                    tag_scanned VARCHAR(100),
                    system_response TEXT,
                    direction VARCHAR(50) DEFAULT 'Unknown',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")

                # 7. Camera Audit Logs Table
                conn.execute("""
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
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cam_audit_plate ON camera_audit_logs(detected_plate)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cam_audit_date ON camera_audit_logs(date_str)")
        finally:
            conn.close()

    # Initialize authentication & user accounts tables
    from services.auth_service import init_auth_tables
    init_auth_tables()

def get_setting(key: str, default: str = "") -> str:
    now = time.time()
    with _SETTINGS_LOCK:
        cached = _SETTINGS_CACHE.get(key)
        if cached and now < cached[1]:
            return cached[0]

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT config_value FROM settings WHERE config_key = ?", (key,)).fetchone()
            val = row['config_value'] if row else default
            with _SETTINGS_LOCK:
                _SETTINGS_CACHE[key] = (val, now + SETTINGS_CACHE_TTL)
            return val
        finally:
            conn.close()

def set_setting(key: str, value: str):
    now = time.time()
    with _SETTINGS_LOCK:
        _SETTINGS_CACHE[key] = (value, now + SETTINGS_CACHE_TTL)
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
