import os
import time
import pytest
from fastapi.testclient import TestClient

from app import app
import config
from database import get_db_connection, init_db
from services.access_service import execute_access_decision, process_camera_line_crossing
import httpx
_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

import app as app_module
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_gate_access.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    init_db()
    return test_db

def test_camera_audit_stats_and_logs():
    res = client.get("/api/camera-audit-stats")
    assert res.status_code == 200
    data = res.json()
    assert "today_total" in data
    assert "week_total" in data
    assert "month_total" in data

    res = client.get("/api/camera-audit-logs?date=all")
    assert res.status_code == 200
    logs_data = res.json()
    assert "logs" in logs_data
    assert "total" in logs_data
    assert "pages" in logs_data

def test_camera_audit_redirect():
    res = client.get("/camera-audit", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "/?tab=camera_audit"

def test_fifo_rfid_sequence():
    test_tag = "FIFO_TEST_TAG_999"

    # Clean existing logs for test_tag
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (test_tag,))

    # 1st scan -> Entry
    log_id1 = execute_access_decision(test_tag)
    with get_db_connection() as conn:
        row1 = conn.execute("SELECT direction, scanned_tag FROM daily_logs WHERE id=?", (log_id1,)).fetchone()
        assert row1["direction"] == "Entry"
        assert row1["scanned_tag"] == test_tag

    # Immediate scan within 20s should deduplicate and return same log_id1
    duplicate_id = execute_access_decision(test_tag)
    assert duplicate_id == log_id1

    # Simulate 50s passing by updating log1 timestamp in database
    with get_db_connection() as conn:
        with conn:
            conn.execute("UPDATE daily_logs SET timestamp = datetime('now', '-50 seconds') WHERE id=?", (log_id1,))

    # 2nd scan after cooldown -> Exit
    log_id2 = execute_access_decision(test_tag)
    assert log_id2 != log_id1
    with get_db_connection() as conn:
        row2 = conn.execute("SELECT direction FROM daily_logs WHERE id=?", (log_id2,)).fetchone()
        assert row2["direction"] == "Exit"

    # Simulate 50s passing by updating log2 timestamp in database
    with get_db_connection() as conn:
        with conn:
            conn.execute("UPDATE daily_logs SET timestamp = datetime('now', '-50 seconds') WHERE id=?", (log_id2,))

    # 3rd scan after cooldown -> Entry
    log_id3 = execute_access_decision(test_tag)
    assert log_id3 != log_id2
    with get_db_connection() as conn:
        row3 = conn.execute("SELECT direction FROM daily_logs WHERE id=?", (log_id3,)).fetchone()
        assert row3["direction"] == "Entry"

def test_kiosk_html_light_theme_and_no_camera_box():
    res = client.get("/kiosk")
    assert res.status_code == 200
    html = res.text
    assert "#F8FAFC" in html
    assert "Gate Access Terminal" in html
    assert "CAM LIVE PROOF" not in html
    assert "VEHICLE SNAPSHOT" not in html

    # Verify kiosk.js contains UNREGISTERED CAR DETECTED
    js_res = client.get("/static/js/kiosk.js")
    assert js_res.status_code == 200
    assert "UNREGISTERED CAR DETECTED" in js_res.text

def test_dashboard_camera_audit_tab():
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "tab-camera_audit" in html
    assert "camAuditGrid" in html
    assert "camStatToday" in html
    assert "camProofModal" in html

def test_prevent_simultaneous_dual_entry_exit():
    tag = "SIMUL_DUAL_TEST_777"
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (tag,))

    # First detection at gate in FIFO Auto mode
    id_entry = execute_access_decision(tag, direction="Auto")
    
    # Near-simultaneous detection from second reader (within 45s cooldown)
    id_exit = execute_access_decision(tag, direction="Auto")

    # Both must resolve to the same passage ID
    assert id_exit == id_entry

    # Database must have exactly ONE record, strictly as Entry
    with get_db_connection() as conn:
        rows = conn.execute("SELECT id, direction FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["direction"] == "Entry"

def test_multithreaded_simultaneous_cross_read():
    import concurrent.futures
    tag = "CONCURRENT_TAG_888"
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (tag,))

    # 10 threads trying to scan at the exact same millisecond in FIFO mode
    def worker():
        return execute_access_decision(tag, direction="Auto")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker) for _ in range(10)]
        results = [f.result() for f in futures]

    # All threads must receive the same single log ID
    assert len(set(results)) == 1

    # Database must contain exactly 1 log
    with get_db_connection() as conn:
        rows = conn.execute("SELECT id, direction FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchall()
        assert len(rows) == 1

def test_universal_cross_reader_cooldown_entry_then_exit():
    tag = "CROSS_READER_BOUNCE_TAG_101"
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (tag,))

    # Reader 1 reports Entry
    id1 = execute_access_decision(tag, direction="Entry")
    assert id1 is not None

    # 1-2 seconds later, Reader 2 catches same tag and reports Exit
    id2 = execute_access_decision(tag, direction="Exit")

    # Universal 45s cooldown must suppress Reader 2 and return same log ID
    assert id2 == id1

    with get_db_connection() as conn:
        rows = conn.execute("SELECT id, direction FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["direction"] == "Entry"

def test_camera_audit_deduplication_preserves_dahua_plate():
    from services.access_service import deduplicate_camera_audit_logs, log_camera_audit_event
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM camera_audit_logs WHERE image_path LIKE '%test_dedup%'")

    # Create dummy images for testing
    import os
    os.makedirs("static/camera_audits", exist_ok=True)
    img1 = "static/camera_audits/test_dedup_overview_1.jpg"
    img2 = "static/camera_audits/test_dedup_overview_2.jpg"
    plate_img = "static/camera_audits/test_dedup_dahua_plate.jpg"
    with open(img1, "wb") as f: f.write(b"overview_bytes_1")
    with open(img2, "wb") as f: f.write(b"overview_bytes_2")
    with open(plate_img, "wb") as f: f.write(b"plate_bytes")

    # Trigger 1: overview without plate
    log_camera_audit_event(img1, plate_image_path=None, direction="Entry")
    # Trigger 2 (immediate repeat within 1s): overview with Dahua plate
    log_camera_audit_event(img2, plate_image_path=plate_img, direction="Entry")

    removed = deduplicate_camera_audit_logs()
    assert removed >= 1

    # Verify Dahua plate was preserved in the retained record
    with get_db_connection() as conn:
        remaining = conn.execute("SELECT * FROM camera_audit_logs WHERE image_path LIKE '%test_dedup%'").fetchall()
        assert len(remaining) == 1
        assert remaining[0]["plate_image_path"] == plate_img

    # Cleanup test files
    for p in (img1, img2, plate_img):
        if os.path.exists(p): os.remove(p)

