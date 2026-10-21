import os
import pytest
import json
from datetime import datetime, timedelta
import httpx

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from fastapi.testclient import TestClient
from app import app
import app as app_module
import config
from database import get_db_connection, init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_manual_bulk.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()

    conn = get_db_connection()
    # Insert test members
    conn.execute("""
        INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Current_Location, Status)
        VALUES 
        ('M-101', 'Member Alpha', 'ABC-111', 'Civic', 'TAG-A1', 'Inside', 'Active'),
        ('M-102', 'Member Beta', 'XYZ-222', 'Corolla', 'TAG-B2', 'Inside', 'Active'),
        ('M-103', 'Staff Whitelist', 'VIP-999', 'Land Cruiser', 'TAG-VIP', 'Inside', 'Active')
    """)

    # Entry timestamps on today's PKT date (so duration is calculated consistently across midnight)
    today_str = datetime.now().strftime("%Y-%m-%d")
    t_alpha = f"{today_str} 00:05:00"
    t_beta = f"{today_str} 00:07:00"
    t_vip = f"{today_str} 00:09:00"

    # Seed Entry logs: Alpha, Beta, VIP are currently inside
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES 
        ('M-101', 'Member Alpha', 'ABC-111', 'RFID', 'Entry', 'Gate-01-In', 'TAG-A1', ?),
        ('M-102', 'Member Beta', 'XYZ-222', 'RFID', 'Entry', 'Gate-02-In', 'TAG-B2', ?),
        ('M-103', 'Staff Whitelist', 'VIP-999', 'RFID', 'Entry', 'Gate-01-In', 'TAG-VIP', ?)
    """, (t_alpha, t_beta, t_vip))
    conn.commit()
    conn.close()


def test_single_manual_exit():
    # Verify initial status of Alpha is Inside
    res = client.get("/api/audit?search=ABC-111")
    assert res.status_code == 200
    data = res.json()
    assert len(data["audits"]) >= 1
    assert data["audits"][0]["status"] == "Inside Facility"

    today_str = datetime.now().strftime("%Y-%m-%d")
    exit_time = f"{today_str} 02:10:00"

    # Manually exit Member Alpha with custom timestamp and camera image proof
    payload = {
        "vehicle_number": "ABC-111",
        "mem_id": "M-101",
        "name": "Member Alpha",
        "scanned_tag": "TAG-A1",
        "timestamp": exit_time,
        "gate_no": "Gate-01-Out",
        "image_path": "static/camera_audits/hikvision_proof_test.jpg",
        "notes": "Tag read failed at barrier"
    }
    exit_res = client.post("/api/audit/manual-exit", json=payload)
    assert exit_res.status_code == 200
    exit_data = exit_res.json()
    assert exit_data["ok"] is True
    assert exit_data["vehicle_number"] == "ABC-111"
    assert "Manual Exit" in exit_data["access_type"]

    # Verify Member Alpha's Current_Location in database is now 'Outside'
    conn = get_db_connection()
    mem = conn.execute("SELECT Current_Location FROM members WHERE Mem_id = 'M-101'").fetchone()
    assert mem["Current_Location"] == "Outside"
    conn.close()

    # Verify Audit table now shows Member Alpha as 'Exited' with calculated stay duration
    res_after = client.get("/api/audit?search=ABC-111")
    assert res_after.status_code == 200
    data_after = res_after.json()
    assert data_after["audits"][0]["status"] == "Exited"
    assert "2h" in data_after["audits"][0]["duration"]
    assert data_after["audits"][0]["exit"]["image_path"] == "static/camera_audits/hikvision_proof_test.jpg"


def test_bulk_exit_settings_and_exception_whitelist():
    # Test getting default whitelist
    get_res = client.get("/api/settings/bulk-exit-exceptions")
    assert get_res.status_code == 200
    data = get_res.json()
    assert "exceptions" in data
    assert data["total_inside"] >= 3  # Alpha, Beta, VIP

    # Add VIP-999 to whitelist
    save_res = client.post("/api/settings/bulk-exit-exceptions", json={"exceptions": ["VIP-999"]})
    assert save_res.status_code == 200
    assert save_res.json()["ok"] is True
    assert "VIP-999" in save_res.json()["exceptions"]

    # Re-check settings
    get_res2 = client.get("/api/settings/bulk-exit-exceptions")
    assert get_res2.status_code == 200
    data2 = get_res2.json()
    assert data2["exempt_inside_count"] == 1
    assert data2["clearable_count"] == data2["total_inside"] - 1


def test_bulk_manual_exit_execution():
    # Set whitelist to protect VIP-999
    client.post("/api/settings/bulk-exit-exceptions", json={"exceptions": ["VIP-999"]})

    # Execute bulk manual exit
    today_str = datetime.now().strftime("%Y-%m-%d")
    bulk_res = client.post("/api/audit/bulk-manual-exit", json={
        "timestamp": f"{today_str} 02:15:00",
        "gate_no": "Gate-01-Out (Bulk Exit)",
        "notes": "Nightly Clearance"
    })
    assert bulk_res.status_code == 200
    bulk_data = bulk_res.json()
    assert bulk_data["ok"] is True
    assert bulk_data["exited_count"] == 2  # Alpha and Beta
    assert bulk_data["exempted_count"] == 1  # VIP-999 stayed inside

    # Verify database state
    conn = get_db_connection()
    alpha_loc = conn.execute("SELECT Current_Location FROM members WHERE Mem_id = 'M-101'").fetchone()["Current_Location"]
    beta_loc = conn.execute("SELECT Current_Location FROM members WHERE Mem_id = 'M-102'").fetchone()["Current_Location"]
    vip_loc = conn.execute("SELECT Current_Location FROM members WHERE Mem_id = 'M-103'").fetchone()["Current_Location"]
    conn.close()

    assert alpha_loc == "Outside"
    assert beta_loc == "Outside"
    assert vip_loc == "Inside"  # Protected!

    # Verify Audit logs: VIP-999 is still 'Inside Facility', Alpha and Beta are 'Exited'
    res_vip = client.get("/api/audit?search=VIP-999")
    assert res_vip.json()["audits"][0]["status"] == "Inside Facility"

    res_beta = client.get("/api/audit?search=XYZ-222")
    assert res_beta.json()["audits"][0]["status"] == "Exited"


def test_unregistered_car_manual_exit():
    """Verify that unknown/unregistered vehicles can be manually exited cleanly."""
    conn = get_db_connection()
    entry_time = (datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('UNREGISTERED', 'Unregistered Driver', 'UNREGISTERED', 'Optical Capture - No RFID', 'Entry', 'Gate-01-In', 'NO_TAG', ?)
    """, (entry_time,))
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Verify initial status is Alert / Inside
    res = client.get("/api/audit?search=Unregistered")
    assert res.status_code == 200
    audits = res.json()["audits"]
    unreg_item = next((a for a in audits if a.get("entry") and a["entry"]["id"] == entry_id), None)
    assert unreg_item is not None
    assert unreg_item["status"] in ("Alert / Inside", "Inside Facility")

    # Perform manual exit with log_id
    exit_time = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    manual_res = client.post("/api/audit/manual-exit", json={
        "log_id": entry_id,
        "vehicle_number": "UNREGISTERED",
        "name": "Unregistered Driver",
        "timestamp": exit_time,
        "gate_no": "Gate-01-Out",
        "notes": "Guard verified manual departure"
    })
    assert manual_res.status_code == 200
    m_data = manual_res.json()
    assert m_data["ok"] is True
    assert "Manual Exit" in m_data["access_type"]

    # Verify audit table now pairs the unregistered vehicle and marks it Exited
    res_after = client.get("/api/audit?search=Unregistered")
    assert res_after.status_code == 200
    audits_after = res_after.json()["audits"]
    paired_item = next((a for a in audits_after if a.get("entry") and a["entry"]["id"] == entry_id), None)
    assert paired_item is not None
    assert paired_item["status"] == "Exited"
    assert paired_item["exit"] is not None
    assert paired_item["duration"] is not None


def test_bulk_manual_exit_mixed_fleet_members_and_unregistered():
    """
    DEEP TEST: Bulk manual exit with mixed registered members, unregistered RFID tags,
    optical camera captures, and normalized exception whitelist protection.
    """
    conn = get_db_connection()
    t_now = datetime.now()
    t_entry = (t_now - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Registered member inside
    conn.execute("""
        INSERT OR REPLACE INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Current_Location, Status)
        VALUES ('M-DEEP-1', 'Deep Tester 1', 'DEP-101', 'Sedan', 'TAG-DEP-1', 'Inside', 'Active')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-DEEP-1', 'Deep Tester 1', 'DEP-101', 'RFID Verified', 'Entry', 'Gate-01 Entry Reader', 'TAG-DEP-1', ?)
    """, (t_entry,))

    # 2. Unregistered RFID vehicle inside (present in unregistered_tags)
    conn.execute("""
        INSERT OR REPLACE INTO unregistered_tags (tag, first_seen, last_seen, direction, Current_Location, read_count, tag_type)
        VALUES ('TAG-UNREG-99', ?, ?, 'Entry', 'Inside', 3, 'NHA Motorway M-Tag')
    """, (t_entry, t_entry))
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('GUEST-LOG', 'NHA M-Tag Guest', 'GUEST-99', 'NHA Motorway M-Tag (RFID)', 'Entry', 'Gate-01 Entry Reader', 'TAG-UNREG-99', ?)
    """, (t_entry,))

    # 3. Optical AI camera capture (no RFID tag)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('AI-CAM', 'Camera Visitor', 'CAM-777', 'Optical Capture - No RFID', 'Entry', 'Club Road Gate', 'NO_TAG', ?)
    """, (t_entry,))

    # 4. Whitelisted staff vehicle inside (STAFF-888)
    conn.execute("""
        INSERT OR REPLACE INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Current_Location, Status)
        VALUES ('M-STAFF', 'Club Staff', 'STAFF-888', 'SUV', 'TAG-STAFF', 'Inside', 'Active')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-STAFF', 'Club Staff', 'STAFF-888', 'Staff Pass', 'Entry', 'Gate-01 Entry Reader', 'TAG-STAFF', ?)
    """, (t_entry,))

    conn.commit()
    conn.close()

    # Configure whitelist with space formatting to test normalization: 'STAFF 888' protects 'STAFF-888'
    client.post("/api/settings/bulk-exit-exceptions", json={"exceptions": ["STAFF 888", "VIP-999"]})

    # Execute Bulk Manual Exit
    bulk_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bulk_res = client.post("/api/audit/bulk-manual-exit", json={
        "timestamp": bulk_ts,
        "gate_no": "Nightly Bulk Clearance Gate",
        "notes": "Deep Bulk Exit QA"
    })
    assert bulk_res.status_code == 200
    res_data = bulk_res.json()
    assert res_data["ok"] is True

    # STAFF-888 and VIP-999 must be exempted
    exempted_plates = [x.get("vehicle_number") for x in res_data["exempted_vehicles"]]
    assert any("STAFF" in p for p in exempted_plates)

    # Verify database state after bulk exit:
    conn = get_db_connection()
    # 1. Registered member is now Outside
    m1 = conn.execute("SELECT Current_Location FROM members WHERE Mem_id='M-DEEP-1'").fetchone()
    assert m1["Current_Location"] == "Outside"

    # 2. Unregistered tag table is now Outside and direction is Exit
    unreg = conn.execute("SELECT Current_Location, direction FROM unregistered_tags WHERE tag='TAG-UNREG-99'").fetchone()
    assert unreg["Current_Location"] == "Outside"
    assert unreg["direction"] == "Exit"

    # 3. Whitelisted staff vehicle remains Inside
    staff = conn.execute("SELECT Current_Location FROM members WHERE Mem_id='M-STAFF'").fetchone()
    assert staff["Current_Location"] == "Inside"
    conn.close()

    # 4. Audit query shows all cleared vehicles as Exited with duration
    audit_res = client.get("/api/audit?search=DEP-101")
    assert audit_res.status_code == 200
    dep_audit = audit_res.json()["audits"][0]
    assert dep_audit["status"] == "Exited"
    assert dep_audit["duration"] is not None

    audit_cam = client.get("/api/audit?search=CAM-777")
    assert audit_cam.status_code == 200
    cam_audit = audit_cam.json()["audits"][0]
    assert cam_audit["status"] == "Exited"

    audit_unreg = client.get("/api/audit?search=TAG-UNREG-99")
    assert audit_unreg.status_code == 200
    unreg_audit = audit_unreg.json()["audits"][0]
    assert unreg_audit["status"] == "Exited"

    # Idempotency: Re-running bulk exit immediately when only exempt vehicles remain inside
    re_bulk_res = client.post("/api/audit/bulk-manual-exit", json={"notes": "Immediate Second Run"})
    assert re_bulk_res.status_code == 200
    re_data = re_bulk_res.json()
    assert re_data["exited_count"] == 0, "Second run should exit 0 vehicles as non-exempt are already outside"


def test_post_bulk_exit_subsequent_scans_and_cycle():
    """
    DEEP TEST: Full round-trip lifecycle.
    1. Member cleared via bulk exit overnight (Current_Location becomes 'Outside').
    2. Next morning, arrives and enters via Gate-01 Entry Reader -> marked 'Entry'.
    3. Exiting club later, detected by Gate-01 Entry Reader (user's overlap scenario) -> marked 'Exit'.
    4. Confirms paired audit correctly logs 1 complete visit.
    """
    from services.access_service import execute_access_decision

    test_tag = "TAG-CYCLE-001"
    test_car = "CYC-900"
    test_mem = "M-CYC"

    conn = get_db_connection()
    conn.execute("""
        INSERT OR REPLACE INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Current_Location, Status)
        VALUES (?, 'Cycle Tester', ?, 'Civic', ?, 'Inside', 'Active')
    """, (test_mem, test_car, test_tag))
    # Entry yesterday
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES (?, 'Cycle Tester', ?, 'RFID Verified', 'Entry', 'Gate-01 Entry Reader', ?, '2026-10-18 20:00:00')
    """, (test_mem, test_car, test_tag))
    conn.commit()
    conn.close()

    # Overnight bulk manual exit clears the car
    bulk_res = client.post("/api/audit/bulk-manual-exit", json={
        "timestamp": "2026-10-18 23:59:00",
        "gate_no": "Nightly Bulk Clearance Gate",
        "override_exceptions": []
    })
    assert bulk_res.status_code == 200

    conn = get_db_connection()
    m = conn.execute("SELECT Current_Location FROM members WHERE Mem_id=?", (test_mem,)).fetchone()
    assert m["Current_Location"] == "Outside"
    conn.close()

    # Next morning: Car arrives from outside at Gate-01 Entry Reader
    log_entry_id = execute_access_decision(test_tag, direction="Entry", gate_name="Gate-01 Entry Reader", bypass_cooldown=True)
    conn = get_db_connection()
    entry_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (log_entry_id,)).fetchone()
    assert entry_row["direction"] == "Entry"
    assert entry_row["gate_no"] == "Gate-01 Entry Reader"
    m_in = conn.execute("SELECT Current_Location FROM members WHERE Mem_id=?", (test_mem,)).fetchone()
    assert m_in["Current_Location"] == "Inside"
    conn.close()

    # Later: Car exits, detected by Gate-01 Entry Reader (the user's scenario!)
    log_exit_id = execute_access_decision(test_tag, direction="Entry", gate_name="Gate-01 Entry Reader", bypass_cooldown=True)
    conn = get_db_connection()
    exit_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (log_exit_id,)).fetchone()
    assert exit_row["direction"] == "Exit"
    assert exit_row["gate_no"] == "Gate-01 Entry Reader"
    m_out = conn.execute("SELECT Current_Location FROM members WHERE Mem_id=?", (test_mem,)).fetchone()
    assert m_out["Current_Location"] == "Outside"
    conn.close()

    # Verify audit shows the newly completed visit today
    audit_res = client.get(f"/api/audit?search={test_car}")
    assert audit_res.status_code == 200
    audits = audit_res.json()["audits"]
    assert len(audits) >= 1
    today_trip = audits[0]
    assert today_trip["status"] == "Exited"
    assert today_trip["entry"]["gate_no"] == "Gate-01 Entry Reader"
    assert today_trip["exit"]["gate_no"] == "Gate-01 Entry Reader"

    # Verify yesterday's bulk-exited visit is recorded on yesterday's date
    yest_res = client.get(f"/api/audit?date=2026-10-18&search={test_car}")
    assert yest_res.status_code == 200
    yest_audits = yest_res.json()["audits"]
    assert len(yest_audits) >= 1
    assert yest_audits[0]["status"] == "Exited"


