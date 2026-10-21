"""
Pytest root configuration and test lifecycle fixtures for RFID_VAMS.
Configured for pure PostgreSQL test execution (kgc_vams_test).
"""

import sys
import pytest
import config
from database import get_db_connection, init_db

@pytest.fixture(autouse=True)
def clean_postgres_test_db(monkeypatch):
    """
    Guarantees full test isolation by cleaning PostgreSQL test database
    before each test function runs.
    """
    app_module = sys.modules.get('app')
    if app_module:
        monkeypatch.setattr(app_module, "DB_FILE", "kgc_vams_test")
    monkeypatch.setattr(config, "DB_FILE", "kgc_vams_test")

    # Ensure PostgreSQL test schema is up to date
    init_db(dbname="kgc_vams_test")

    # Clean all mutable tables in kgc_vams_test
    with config.DB_LOCK:
        conn = get_db_connection(dbname="kgc_vams_test")
        try:
            with conn:
                conn.execute("DELETE FROM daily_logs")
                conn.execute("DELETE FROM raw_reader_logs")
                conn.execute("DELETE FROM camera_audit_logs")
                conn.execute("DELETE FROM unregistered_tags")
                conn.execute("DELETE FROM members")
                conn.execute("UPDATE settings SET config_value='Karachi Gymkhana Club' WHERE config_key='club_name'")
                conn.execute("UPDATE settings SET config_value='500' WHERE config_key='parking_capacity'")
                conn.execute("ALTER SEQUENCE IF EXISTS daily_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS raw_reader_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS camera_audit_logs_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS unregistered_tags_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE IF EXISTS members_id_seq RESTART WITH 1")
        finally:
            conn.close()

    # Clear in-memory caches and state
    import database
    with database._SETTINGS_LOCK:
        database._SETTINGS_CACHE.clear()
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        config.LATEST_GATE_LOG_CACHE = {"gate01": None, "clubroad": None}
        config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
        config.STATS_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
        config.FLEET_ADOPTION_CACHE = {"data": None, "timestamp": 0.0, "db_file": None}
        config.GLOBAL_TAG_LOCKS.clear()
        config.PENDING_RFID_BUFFER.clear()
    config.invalidate_member_cache()

    yield

    # Clean after test completes as well
    with config.DB_LOCK:
        conn = get_db_connection(dbname="kgc_vams_test")
        try:
            with conn:
                conn.execute("DELETE FROM daily_logs")
                conn.execute("DELETE FROM raw_reader_logs")
                conn.execute("DELETE FROM camera_audit_logs")
                conn.execute("DELETE FROM unregistered_tags")
                conn.execute("DELETE FROM members")
        finally:
            conn.close()
