import os
import glob
import shutil
import subprocess
from datetime import datetime
import psycopg2
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import config
import database
from database import get_db_connection, set_setting
from services.camera_service import stream_video

router = APIRouter(prefix="/api", tags=["Settings & Streaming"])

@router.get("/logo")
async def get_logo():
    if os.path.exists(config.LOGO_PATH):
        return FileResponse(config.LOGO_PATH)
    return JSONResponse({"error": "No logo configured"}, status_code=404)

@router.get("/settings")
async def get_settings():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT config_key, config_value FROM settings").fetchall()
            return {row['config_key']: row['config_value'] for row in rows}
        finally:
            conn.close()

from fastapi import HTTPException

def check_admin_permission(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")
    if user.get("role") != "Admin":
        raise HTTPException(403, "Administrator privileges required. Viewer and Editor accounts cannot modify system configuration.")

@router.post("/settings")
async def save_settings(request: Request):
    check_admin_permission(request)
    body = await request.json()
    for key, val in body.items():
        set_setting(key, str(val))
    return {"ok": True}

@router.get("/stream/hikvision")
async def stream_hikvision():
    return StreamingResponse(stream_video("Hikvision"), media_type="multipart/x-mixed-replace; boundary=frame")

@router.post("/settings/reset-activity")
async def reset_activity_data(request: Request = None):
    if request:
        check_admin_permission(request)
    """
    Resets all previous activity logs, raw reader scans, and camera audit entries.
    Retains all Members Directory records and System Settings.
    """
    import shutil
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM daily_logs")
                conn.execute("DELETE FROM raw_reader_logs")
                conn.execute("DELETE FROM camera_audit_logs")
                conn.execute("DELETE FROM unregistered_tags")
                conn.execute("UPDATE members SET Current_Location = 'Outside'")
                conn.execute("ALTER SEQUENCE IF EXISTS daily_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS raw_reader_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS camera_audit_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS unregistered_tags_id_seq RESTART WITH 1")
            
            # Count retained members and settings
            members_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            settings_count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        finally:
            conn.close()

    # Clear temporary images
    for folder in [config.SNAPSHOT_DIR, config.CAMERA_AUDIT_DIR, config.FTP_UPLOAD_DIR, config.TEST_DIR]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.unlink(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception:
                    pass

    # Clear in-memory state and caches
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
        config.FLEET_ADOPTION_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
    config.invalidate_member_cache()
    with config.BUFFER_LOCK:
        config.RECENT_CAM_TRIGGERS.clear()
        config.RECENT_TAGS.clear()
        config.PENDING_RFID_BUFFER.clear()
    config.FTP_EVENT_COUNT = {"count": 0}
    config.LAST_GATE_PASSAGE = {"time": 0.0, "log_id": None, "md5": None}

    return {
        "ok": True,
        "members_count": members_count,
        "settings_count": settings_count,
        "message": f"Activity logs reset. {members_count:,} members and {settings_count} settings preserved."
    }

@router.get("/settings/bulk-exit-exceptions")
async def get_bulk_exit_exceptions():
    """
    Returns configured exception whitelist for bulk exit and live facility occupancy breakdown.
    """
    import json
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT config_value FROM settings WHERE config_key = 'bulk_exit_exceptions' LIMIT 1").fetchone()
            exceptions = []
            if row and row["config_value"]:
                try:
                    exceptions = json.loads(row["config_value"])
                except Exception:
                    exceptions = [x.strip() for x in row["config_value"].split(",") if x.strip()]

            from routers.logs import AUDIT_LOGS_BASE_QUERY, _build_paired_audits
            logs = [dict(r) for r in conn.execute(AUDIT_LOGS_BASE_QUERY + " ORDER BY d.id ASC").fetchall()]
            paired = _build_paired_audits(logs)
            inside = [p for p in paired if p.get("status") in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")]

            exempt_set = {str(x).strip().upper() for x in exceptions if str(x).strip()}
            exempt_count = 0
            for item in inside:
                v = item.get("entry") or item.get("exit") or {}
                p = (v.get("vehicle_number") or "").strip().upper()
                m = (v.get("mem_id") or "").strip().upper()
                t = (v.get("scanned_tag") or "").strip().upper()
                if (p and p in exempt_set) or (m and m in exempt_set) or (t and t in exempt_set):
                    exempt_count += 1

            total_inside = len(inside)
            clearable_count = max(0, total_inside - exempt_count)

            return {
                "exceptions": exceptions,
                "total_inside": total_inside,
                "exempt_inside_count": exempt_count,
                "clearable_count": clearable_count
            }
        finally:
            conn.close()

@router.post("/settings/bulk-exit-exceptions")
async def save_bulk_exit_exceptions(request: Request):
    """
    Updates the list of vehicle plates / IDs exempt from bulk exit.
    """
    import json
    body = await request.json()
    raw_list = body.get("exceptions", [])
    if not isinstance(raw_list, list):
        raise HTTPException(400, "Exceptions must be a list of vehicle plates or member IDs")

    cleaned = []
    seen = set()
    for item in raw_list:
        c = str(item).strip().upper()
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)

    import json
    set_setting("bulk_exit_exceptions", json.dumps(cleaned))
    return {"ok": True, "exceptions": cleaned}


def find_pg_tool(tool_name: str) -> str | None:
    """Locates PostgreSQL command-line binaries (pg_dump, psql) across Windows and Linux environments."""
    p = shutil.which(tool_name)
    if p:
        return p
    patterns = [
        rf"C:\PostgreSQL\pgsql\bin\{tool_name}.exe",
        rf"C:\Program Files\PostgreSQL\*\bin\{tool_name}.exe",
        rf"C:\Program Files (x86)\PostgreSQL\*\bin\{tool_name}.exe",
        rf"/usr/bin/{tool_name}",
        rf"/usr/local/bin/{tool_name}",
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[-1]
    return None

@router.get("/database/status")
async def get_database_status(request: Request):
    """
    Returns telemetry for the PostgreSQL database, table record counts,
    disk storage usage, and availability of native backup/restore tools.
    """
    check_admin_permission(request)
    pg_dump_path = find_pg_tool("pg_dump")
    psql_path = find_pg_tool("psql")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            try:
                row = conn.execute(f"SELECT pg_size_pretty(pg_database_size('{database.PG_DBNAME}')), version()").fetchone()
                db_size = row[0]
                pg_version = row[1].split(",")[0]
            except Exception:
                db_size = "Unknown"
                pg_version = "PostgreSQL"

            counts = {}
            for tbl in ["members", "daily_logs", "raw_reader_logs", "camera_audit_logs", "unregistered_tags", "users", "settings"]:
                try:
                    c = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    counts[tbl] = c
                except Exception:
                    counts[tbl] = 0

            try:
                last_log = conn.execute("SELECT MAX(date_time) FROM daily_logs").fetchone()[0]
            except Exception:
                last_log = None
        finally:
            conn.close()

    root_backup = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kgc_vams_backup.sql")
    backup_exists = os.path.exists(root_backup)
    backup_size = os.path.getsize(root_backup) if backup_exists else 0
    backup_mtime = os.path.getmtime(root_backup) if backup_exists else None

    return {
        "ok": True,
        "engine": "Enterprise PostgreSQL",
        "version": pg_version,
        "host": database.PG_HOST,
        "port": database.PG_PORT,
        "database": database.PG_DBNAME,
        "size": db_size,
        "counts": counts,
        "last_log_time": str(last_log) if last_log else "No recent logs",
        "tools": {
            "pg_dump": bool(pg_dump_path),
            "psql": bool(psql_path),
            "pg_dump_path": pg_dump_path,
            "psql_path": psql_path
        },
        "canonical_backup": {
            "path": root_backup,
            "exists": backup_exists,
            "size_bytes": backup_size,
            "size_display": f"{backup_size / (1024*1024):.2f} MB" if backup_size else "0 MB",
            "modified": datetime.fromtimestamp(backup_mtime).strftime("%Y-%m-%d %H:%M:%S") if backup_mtime else None
        }
    }

@router.get("/database/export")
async def export_database_endpoint(request: Request, mode: str = "full"):
    """
    Exports the PostgreSQL database into a standard .sql dump file with DROP/CREATE statements.
    mode='full': Exports complete schema, members, vehicles, users, logs, and settings.
    mode='compact': Exports members, vehicles, users, and settings (omits historical gate logs for fast sync).
    """
    check_admin_permission(request)
    mode = mode.lower() if mode in ("full", "compact") else "full"

    pg_dump_exe = find_pg_tool("pg_dump")
    if not pg_dump_exe:
        raise HTTPException(500, "pg_dump executable not found on host machine.")

    scratch_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"kgc_vams_backup_{ts}_{mode}.sql"
    file_path = os.path.join(scratch_dir, filename)

    cmd = [
        pg_dump_exe,
        "-h", database.PG_HOST,
        "-p", str(database.PG_PORT),
        "-U", database.PG_USER,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
    ]
    if mode == "compact":
        cmd.extend(["-T", "daily_logs", "-T", "raw_reader_logs", "-T", "camera_audit_logs"])

    cmd.extend(["-f", file_path, database.PG_DBNAME])

    env = os.environ.copy()
    if database.PG_PASSWORD:
        env["PGPASSWORD"] = database.PG_PASSWORD

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise HTTPException(500, f"pg_dump export failed: {res.stderr}")

    # Keep the root kgc_vams_backup.sql in sync with full exports
    if mode == "full":
        root_backup = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kgc_vams_backup.sql")
        try:
            shutil.copy2(file_path, root_backup)
        except Exception:
            pass

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/sql"
    )

@router.post("/database/import")
async def import_database_endpoint(request: Request, file: UploadFile = File(...)):
    """
    Restores and synchronizes the PostgreSQL database from an uploaded .sql dump file.
    Recreates tables, restores all member and configuration data, and clears memory caches.
    """
    check_admin_permission(request)

    if not file.filename.lower().endswith(".sql"):
        raise HTTPException(400, "Invalid file format. Please upload a .sql database backup file.")

    scratch_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    import_path = os.path.join(scratch_dir, "uploaded_import.sql")

    # Read and buffer the uploaded SQL file
    content_size = 0
    with open(import_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            content_size += len(chunk)

    if content_size == 0:
        raise HTTPException(400, "The uploaded SQL file is empty.")

    # Sanity check header
    with open(import_path, "r", encoding="utf-8", errors="ignore") as f:
        header_sample = f.read(1024).upper()
        if not any(k in header_sample for k in ["POSTGRESQL", "CREATE", "INSERT", "SET", "DROP", "ALTER"]):
            raise HTTPException(400, "The uploaded file does not appear to be a valid SQL database dump.")

    # 1. Close pool connections
    with database._POOL_LOCK:
        for p in database._POOLS.values():
            try:
                p.closeall()
            except Exception:
                pass
        database._POOLS.clear()

    # 2. Terminate background client locks
    try:
        term_conn = psycopg2.connect(
            host=database.PG_HOST,
            port=database.PG_PORT,
            dbname="postgres",
            user=database.PG_USER,
            password=database.PG_PASSWORD,
            connect_timeout=3
        )
        term_conn.autocommit = True
        term_cur = term_conn.cursor()
        term_cur.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid();
        """, (database.PG_DBNAME,))
        term_cur.close()
        term_conn.close()
    except Exception:
        pass

    # 3. Restore using psql or psycopg2 fallback
    psql_exe = find_pg_tool("psql")
    if psql_exe:
        cmd = [
            psql_exe,
            "-h", database.PG_HOST,
            "-p", str(database.PG_PORT),
            "-U", database.PG_USER,
            "-d", database.PG_DBNAME,
            "-f", import_path,
            "-q"
        ]
        env = os.environ.copy()
        if database.PG_PASSWORD:
            env["PGPASSWORD"] = database.PG_PASSWORD
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if res.returncode != 0 and "FATAL" in (res.stderr or ""):
            raise HTTPException(500, f"psql restore failed: {res.stderr}")
    else:
        try:
            target_conn = psycopg2.connect(
                host=database.PG_HOST,
                port=database.PG_PORT,
                dbname=database.PG_DBNAME,
                user=database.PG_USER,
                password=database.PG_PASSWORD,
                connect_timeout=10
            )
            target_conn.autocommit = True
            cur = target_conn.cursor()
            with open(import_path, "r", encoding="utf-8", errors="ignore") as f:
                cur.execute(f.read())
            cur.close()
            target_conn.close()
        except Exception as e:
            raise HTTPException(500, f"SQL execution failed: {e}")

    # 4. Sync root backup file
    try:
        root_backup = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kgc_vams_backup.sql")
        shutil.copy2(import_path, root_backup)
    except Exception:
        pass

    # 5. Re-run init_db and invalidate caches
    database.init_db()
    config.invalidate_member_cache()
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        config.LATEST_GATE_LOG_CACHE = {"gate01": None, "clubroad": None}
        config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
        config.FLEET_ADOPTION_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
        config.STATS_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
        config.CHARTS_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
        config.AUDIT_LOGS_CACHE.clear()

    # 6. Gather updated table counts
    counts = {}
    with database.get_db_connection() as conn:
        for tbl in ["members", "daily_logs", "raw_reader_logs", "camera_audit_logs", "unregistered_tags", "users", "settings"]:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                counts[tbl] = row[0]
            except Exception:
                counts[tbl] = 0

    return {
        "ok": True,
        "message": f"Database successfully restored! {counts.get('members', 0):,} members, {counts.get('daily_logs', 0):,} access logs, and {counts.get('users', 0)} user accounts are active.",
        "counts": counts,
        "size_bytes": content_size
    }


