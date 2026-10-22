"""
Restore Database Script for Karachi Gymkhana RFID VAMS
Restores the complete kgc_vams database from kgc_vams_backup.sql on any server or workstation.
"""

import os
import sys
import subprocess
import glob

# Load .env if present
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k = _k.strip()
                    _v = _v.strip().strip('"').strip("'")
                    if _k not in os.environ:
                        os.environ[_k] = _v
    except Exception:
        pass

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DBNAME = os.environ.get("PG_DBNAME", "kgc_vams")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kgc_vams_backup.sql")

def find_psql() -> str | None:
    # 1. Check PATH
    import shutil
    p = shutil.which("psql")
    if p:
        return p
    # 2. Check standard Windows locations
    search_patterns = [
        r"C:\PostgreSQL\pgsql\bin\psql.exe",
        r"C:\Program Files\PostgreSQL\*\bin\psql.exe",
        r"C:\Program Files (x86)\PostgreSQL\*\bin\psql.exe",
    ]
    for pat in search_patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[-1]
    return None

def main():
    print("=" * 76)
    print("  KARACHI GYMKHANA CLUB - RFID VAMS DATABASE RESTORE TOOL")
    print("=" * 76)
    print(f"Target Host    : {PG_HOST}:{PG_PORT}")
    print(f"Target Database: {PG_DBNAME}")
    print(f"Database User  : {PG_USER}")
    print(f"Backup File    : {BACKUP_FILE}")
    print("=" * 76)

    if not os.path.exists(BACKUP_FILE):
        print(f"[ERROR] Backup file not found: {BACKUP_FILE}")
        sys.exit(1)

    import psycopg2
    # Step 1: Ensure database exists
    print("\n[1/3] Connecting to PostgreSQL maintenance server...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            dbname="postgres",
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DBNAME,))
        if not cur.fetchone():
            print(f"[INFO] Creating database '{PG_DBNAME}'...")
            cur.execute(f'CREATE DATABASE "{PG_DBNAME}"')
        else:
            print(f"[INFO] Target database '{PG_DBNAME}' already exists.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Could not connect to PostgreSQL on {PG_HOST}:{PG_PORT}: {e}")
        print("\nTroubleshooting tips:")
        print("  1. Verify PostgreSQL service is running in Windows Services (services.msc).")
        print("  2. If PostgreSQL requires a password, create a .env file with PG_PASSWORD=your_password.")
        sys.exit(1)

    # Step 2: Restore backup
    print("\n[2/3] Restoring complete schema, tables, and data...")
    psql_exe = find_psql()
    if psql_exe:
        print(f"[INFO] Using psql engine: {psql_exe}")
        env = os.environ.copy()
        if PG_PASSWORD:
            env["PGPASSWORD"] = PG_PASSWORD
        cmd = [
            psql_exe,
            "-h", PG_HOST,
            "-p", PG_PORT,
            "-U", PG_USER,
            "-d", PG_DBNAME,
            "-f", BACKUP_FILE,
            "-q"
        ]
        res = subprocess.run(cmd, env=env)
        if res.returncode != 0:
            print(f"[WARNING] psql exited with code {res.returncode}. Checking restored counts...")
    else:
        print("[INFO] psql executable not found in PATH; restoring directly via psycopg2...")
        try:
            target_conn = psycopg2.connect(
                host=PG_HOST,
                port=int(PG_PORT),
                dbname=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
                connect_timeout=5
            )
            target_conn.autocommit = True
            cur = target_conn.cursor()
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                sql_content = f.read()
            # Split and execute or execute as block
            cur.execute(sql_content)
            cur.close()
            target_conn.close()
        except Exception as e:
            print(f"[ERROR] Failed to execute backup script: {e}")
            sys.exit(1)

    # Step 3: Verify restored tables and counts
    print("\n[3/3] Verifying restored tables and record counts...")
    try:
        v_conn = psycopg2.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            dbname=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=5
        )
        v_cur = v_conn.cursor()
        for tbl in ["daily_logs", "members", "users", "settings", "raw_reader_logs"]:
            try:
                v_cur.execute(f"SELECT count(*) FROM {tbl}")
                cnt = v_cur.fetchone()[0]
                print(f"  - {tbl:<18}: {cnt:>6} records")
            except Exception as e:
                print(f"  - {tbl:<18}: error ({e})")
        v_cur.close()
        v_conn.close()
        print("\n" + "=" * 76)
        print(" [SUCCESS] PostgreSQL Database 'kgc_vams' is fully restored and ready!")
        print(" You can now run 'start_server.bat' to launch RFID VAMS.")
        print("=" * 76)
    except Exception as e:
        print(f"[WARNING] Verification encountered an error: {e}")

if __name__ == "__main__":
    main()
