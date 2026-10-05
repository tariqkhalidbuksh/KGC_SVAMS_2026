import os
import time
import pytest
import cv2
import numpy as np
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

def test_dahua_capture_latency_under_two_seconds():
    """
    Verifies that Dahua frame capture executes in less than 2 seconds (in practice < 0.1s).
    """
    import numpy as np
    import cv2
    import time
    from services.camera_service import grab_verified_snapshot
    from services.access_service import process_camera_line_crossing
    import config

    # Simulate live frame in RAM buffer
    dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    cv2.putText(dummy_frame, "DAHUA LIVE TEST", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    with config.FRAME_LOCK:
        config.LATEST_RAW_FRAMES["Dahua"] = dummy_frame
        config.LATEST_FRAME_TIMES["Dahua"] = time.time()
        config.CAM_STATUS["Dahua"] = "ONLINE"

    t0 = time.time()
    captured_img = grab_verified_snapshot("Dahua", max_timeout_sec=1.5)
    t_snap = time.time() - t0

    assert captured_img is not None
    # RAM capture must be under 0.1s (100ms), far below 2 seconds
    assert t_snap < 0.1

    # Now test full process_camera_line_crossing execution speed
    hik_dummy = "static/ftp_uploads/test_latency_hik.jpg"
    cv2.imwrite(hik_dummy, dummy_frame)

    t1 = time.time()
    process_camera_line_crossing(hik_dummy, forced_direction="Entry")
    t_process = time.time() - t1

    # Entire pipeline including Dahua snapshot & DB insert must be well below 2 seconds
    assert t_process < 1.0

    # Verify latest camera audit record contains the plate close-up
    # Clean up test audit record
    with get_db_connection() as conn:
        latest = conn.execute("SELECT * FROM camera_audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        if latest:
            conn.execute("DELETE FROM camera_audit_logs WHERE id=?", (latest["id"],))
            conn.commit()

def test_unregistered_vehicle_stay_duration_always_visible():
    """
    Verifies that an unregistered vehicle with two timestamps (e.g. 12:04:40 and 13:08:21)
    always displays a valid, visible stay duration (e.g. 1h 03m / 1h 04m) and is never None or '--',
    even if directions were recorded in reverse order.
    """
    unreg_tag = "E280110520008341E3C50B69"
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (unreg_tag,))
            # Insert the exact two records from user's screenshot
            conn.execute("""INSERT INTO daily_logs 
                (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("GUEST-LOG", "Unregistered Visitor", unreg_tag, "RFID Unknown", "Exit", "Gate-01", unreg_tag, "2026-10-05 12:04:40"))
            conn.execute("""INSERT INTO daily_logs 
                (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("GUEST-LOG", "Unregistered Visitor", unreg_tag, "RFID Unknown", "Entry", "Gate-01", unreg_tag, "2026-10-05 13:08:21"))

    # Fetch audit report via /api/audit
    res = client.get("/api/audit?date=2026-10-05&status=all")
    assert res.status_code == 200
    data = res.json()
    unreg_audit = next((a for a in data["audits"] if (a["entry"] and a["entry"]["scanned_tag"] == unreg_tag) or (a["exit"] and a["exit"]["scanned_tag"] == unreg_tag)), None)

    assert unreg_audit is not None
    # Stay duration must be visible and properly formatted (not None, not empty, not '--')
    assert unreg_audit["duration"] is not None
    assert "1h" in unreg_audit["duration"]
    assert unreg_audit["status"] == "Exited"
    # Entry timestamp must be chronologically earlier than Exit timestamp
    assert str(unreg_audit["entry"]["timestamp"]) < str(unreg_audit["exit"]["timestamp"])
    assert "12:04:40" in str(unreg_audit["entry"]["timestamp"])
    assert "13:08:21" in str(unreg_audit["exit"]["timestamp"])

    # Clean up test records
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM daily_logs WHERE scanned_tag=?", (unreg_tag,))

def test_unique_members_directory_and_vehicles_modal_api():
    """
    Verifies that the members directory shows unique members (not repeated per vehicle),
    attaches all vehicle details to each member, and provides the /api/members/{mem_id}/vehicles endpoint.
    """
    test_mem_id = "MEM-FLEET-TEST-77"
    cars = [
        {"mem_id": test_mem_id, "name": "Fleet Owner", "car_number": "FLT-111", "e_tag_id": "TAG-FLT-111", "make_model": "Toyota Land Cruiser"},
        {"mem_id": test_mem_id, "name": "Fleet Owner", "car_number": "FLT-222", "e_tag_id": "TAG-FLT-222", "make_model": "BMW 7 Series"},
        {"mem_id": test_mem_id, "name": "Fleet Owner", "car_number": "FLT-333", "e_tag_id": "TAG-FLT-333", "make_model": "Mercedes S500"}
    ]
    for c in cars:
        res = client.post("/api/add-member", json=c)
        assert res.status_code == 200

    try:
        # 1. Query members directory with search
        res = client.get(f"/api/members?search={test_mem_id}")
        assert res.status_code == 200
        data = res.json()
        
        # Must return exactly ONE member row for this member, not 3 rows!
        member_matches = [m for m in data["members"] if m["Mem_id"] == test_mem_id]
        assert len(member_matches) == 1
        
        m = member_matches[0]
        assert m["Name"] == "Fleet Owner"
        assert m["vehicle_count"] == 3
        assert m["tagged_count"] == 3
        assert len(m["vehicles"]) == 3
        car_numbers = [v["Car_number"] for v in m["vehicles"]]
        assert "FLT-111" in car_numbers
        assert "FLT-222" in car_numbers
        assert "FLT-333" in car_numbers

        # 2. Test dedicated fleet modal API endpoint
        fleet_res = client.get(f"/api/members/{test_mem_id}/vehicles")
        assert fleet_res.status_code == 200
        fleet_data = fleet_res.json()
        assert fleet_data["ok"] is True
        assert fleet_data["mem_id"] == test_mem_id
        assert fleet_data["vehicle_count"] == 3
        assert len(fleet_data["vehicles"]) == 3
    finally:
        # Cleanup
        client.delete(f"/api/members/{test_mem_id}")

def test_instant_http_camera_trigger():
    """
    Verifies that the /api/tools/event/hikvision endpoint receives HTTP event alerts
    and processes them instantly without waiting for FTP transfers.
    """
    dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    cv2.putText(dummy_frame, "HTTP TRIGGER TEST", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    with config.FRAME_LOCK:
        config.LATEST_RAW_FRAMES["Hikvision"] = dummy_frame
        config.LATEST_FRAME_TIMES["Hikvision"] = time.time()
        config.CAM_STATUS["Hikvision"] = "ONLINE"
        config.LATEST_RAW_FRAMES["Dahua"] = dummy_frame
        config.LATEST_FRAME_TIMES["Dahua"] = time.time()
        config.CAM_STATUS["Dahua"] = "ONLINE"

    # Test HTTP alert trigger
    res = client.post("/api/tools/event/hikvision", json={"eventType": "linedetection", "rule": "rule1"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["mode"] == "instant_http"





