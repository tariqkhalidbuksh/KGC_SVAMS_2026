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

    # Entry timestamps 1-2 hours ago (so they are fresh and not overstayed)
    now = datetime.now()
    t_alpha = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    t_beta = (now - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    t_vip = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

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

    now = datetime.now()
    exit_time = now.strftime("%Y-%m-%d %H:%M:%S")

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
    now = datetime.now()
    bulk_res = client.post("/api/audit/bulk-manual-exit", json={
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
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
    now = datetime.now()
    entry_time = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
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
    exit_time = now.strftime("%Y-%m-%d %H:%M:%S")
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

