import os
import time
import pytest
from fastapi.testclient import TestClient
import httpx

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from app import app
import app as app_module
import config
from database import get_db_connection, init_db
from services.access_service import execute_access_decision

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_multi_gate.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    init_db()
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        config.MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
    with config.BUFFER_LOCK:
        config.PENDING_RFID_BUFFER.clear()
        config.GLOBAL_TAG_LOCKS.clear()
    return test_db


def test_hardware_status_includes_all_four_readers():
    """Verify /api/tools/status reports Gate01 and ClubRoad reader statuses."""
    res = client.get("/api/tools/status")
    assert res.status_code == 200
    data = res.json()
    assert "readers" in data
    readers = data["readers"]
    assert "Gate01_Entry" in readers
    assert "Gate01_Exit" in readers
    assert "ClubRoad_Entry" in readers
    assert "ClubRoad_Exit" in readers
    assert "Entry" in readers
    assert "Exit" in readers


def test_save_and_retrieve_club_road_settings():
    """Verify settings can save and retrieve Club Road reader IP addresses."""
    # First get current settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    settings = res.json()

    # Update with Club Road reader IPs
    settings["entry_reader_ip"] = "192.168.1.101"
    settings["exit_reader_ip"] = "192.168.1.102"
    settings["clubroad_entry_reader_ip"] = "192.168.1.103"
    settings["clubroad_exit_reader_ip"] = "192.168.1.104"

    save_res = client.post("/api/settings", json=settings)
    assert save_res.status_code == 200

    # Retrieve and verify
    verify_res = client.get("/api/settings")
    assert verify_res.status_code == 200
    saved = verify_res.json()
    assert saved["entry_reader_ip"] == "192.168.1.101"
    assert saved["exit_reader_ip"] == "192.168.1.102"
    assert saved["clubroad_entry_reader_ip"] == "192.168.1.103"
    assert saved["clubroad_exit_reader_ip"] == "192.168.1.104"


def test_cross_gate_journey_club_road_entry_to_gate01_exit():
    """
    Test scenario:
    A vehicle enters through Main Gate (Club Road) and exits through Gate-01.
    Verify:
    1. Entry transit logged with gate 'Main Gate (Club Road)'.
    2. Member location changes to 'Inside'.
    3. Exit transit logged with gate 'Gate-01'.
    4. Member location changes to 'Outside'.
    5. The paired audit logs show complete journey with entry and exit gates.
    """
    test_epc = "E280_MULTI_GATE_001"
    test_mem = "MG-001"
    test_car = "KHI-9988"

    # Register member
    reg_res = client.post("/api/add-member", json={
        "mem_id": test_mem,
        "name": "Senator Tariq",
        "car_number": test_car,
        "make_model": "Mercedes E200",
        "e_tag_id": test_epc
    })
    assert reg_res.status_code == 200

    # Step 1: Vehicle enters via Main Gate (Club Road)
    entry_log_id = execute_access_decision(
        tag=test_epc,
        direction="Entry",
        gate_name="Main Gate (Club Road)",
        bypass_cooldown=True
    )
    assert entry_log_id is not None

    with get_db_connection() as conn:
        entry_row = conn.execute("SELECT * FROM daily_logs WHERE id=?", (entry_log_id,)).fetchone()
        assert entry_row["direction"] == "Entry"
        assert entry_row["gate_no"] == "Main Gate (Club Road)"

        mem_row = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()
        assert mem_row["Current_Location"] == "Inside"

    # Step 2: Vehicle exits via Gate-01
    exit_log_id = execute_access_decision(
        tag=test_epc,
        direction="Exit",
        gate_name="Gate-01",
        bypass_cooldown=True
    )
    assert exit_log_id is not None

    with get_db_connection() as conn:
        exit_row = conn.execute("SELECT * FROM daily_logs WHERE id=?", (exit_log_id,)).fetchone()
        assert exit_row["direction"] == "Exit"
        assert exit_row["gate_no"] == "Gate-01"

        mem_row = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()
        assert mem_row["Current_Location"] == "Outside"

    # Step 3: Check paired audit logs in /api/audit
    audit_res = client.get("/api/audit?date=today")
    assert audit_res.status_code == 200
    audits = audit_res.json()["audits"]

    # Locate the paired audit for our car
    matched = [a for a in audits if a.get("entry", {}).get("vehicle_number") == test_car or a.get("entry", {}).get("scanned_tag") == test_epc]
    assert len(matched) >= 1
    pair = matched[0]
    assert pair["entry"]["gate_no"] == "Main Gate (Club Road)"
    assert pair["exit"]["gate_no"] == "Gate-01"
    assert pair["exit"]["timestamp"] is not None


def test_cross_gate_journey_gate01_entry_to_club_road_exit():
    """
    Test scenario:
    A vehicle enters through Gate-01 and exits through Main Gate (Club Road).
    Verify pairing links entry and exit gates properly.
    """
    test_epc = "E280_MULTI_GATE_002"
    test_mem = "MG-002"
    test_car = "KHI-1122"

    reg_res = client.post("/api/add-member", json={
        "mem_id": test_mem,
        "name": "Commodore Khalid",
        "car_number": test_car,
        "make_model": "Toyota Prado",
        "e_tag_id": test_epc
    })
    assert reg_res.status_code == 200

    # Enter via Gate-01
    entry_id = execute_access_decision(
        tag=test_epc,
        direction="Entry",
        gate_name="Gate-01",
        bypass_cooldown=True
    )
    assert entry_id is not None

    # Exit via Main Gate (Club Road)
    exit_id = execute_access_decision(
        tag=test_epc,
        direction="Exit",
        gate_name="Main Gate (Club Road)",
        bypass_cooldown=True
    )
    assert exit_id is not None

    with get_db_connection() as conn:
        entry_row = conn.execute("SELECT gate_no FROM daily_logs WHERE id=?", (entry_id,)).fetchone()
        exit_row = conn.execute("SELECT gate_no FROM daily_logs WHERE id=?", (exit_id,)).fetchone()
        assert entry_row["gate_no"] == "Gate-01"
        assert exit_row["gate_no"] == "Main Gate (Club Road)"

    # Check paired audit
    audit_res = client.get("/api/audit?date=today")
    assert audit_res.status_code == 200
    audits = audit_res.json()["audits"]
    matched = [a for a in audits if a.get("entry", {}).get("vehicle_number") == test_car]
    assert len(matched) >= 1
    pair = matched[0]
    assert pair["entry"]["gate_no"] == "Gate-01"
    assert pair["exit"]["gate_no"] == "Main Gate (Club Road)"


def test_simulation_endpoint_with_gate_parameter():
    """Verify /api/simulate-rfid-full accepts gate parameter and records it in daily_logs."""
    test_epc = "E280_SIM_GATE_003"
    test_mem = "SIM-003"
    test_car = "SIM-7777"

    client.post("/api/add-member", json={
        "mem_id": test_mem,
        "name": "Simulated Member",
        "car_number": test_car,
        "make_model": "Audi A6",
        "e_tag_id": test_epc
    })

    sim_res = client.post("/api/simulate-rfid-full", json={
        "tag": test_epc,
        "direction": "Entry",
        "gate": "Main Gate (Club Road)",
        "bypass_cooldown": True
    })
    assert sim_res.status_code == 200
    data = sim_res.json()
    assert data["ok"] is True
    log_id = data["log_id"]

    with get_db_connection() as conn:
        log_row = conn.execute("SELECT gate_no FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        assert log_row["gate_no"] == "Main Gate (Club Road)"


def test_hardware_telemetry_endpoint():
    """Verify /api/tools/telemetry returns full cluster metrics and device latency."""
    res = client.get("/api/tools/telemetry?synthetic=true")
    assert res.status_code == 200
    data = res.json()
    assert "heartbeat" in data
    assert data["heartbeat"]["bpm"] == 60
    assert "cluster" in data
    assert "avg_latency_ms" in data["cluster"]
    assert "devices" in data
    devices = data["devices"]
    expected_devices = ["Gate01_Entry", "Gate01_Exit", "ClubRoad_Entry", "ClubRoad_Exit", "Hikvision", "Database"]
    for dev_id in expected_devices:
        assert dev_id in devices
        dev = devices[dev_id]
        assert "latency_ms" in dev
        assert "status" in dev
        assert "stats" in dev
        assert "history" in dev


def test_single_device_ping_endpoint():
    """Verify POST /api/tools/ping/{device_id} probes target and returns valid RTT."""
    res = client.post("/api/tools/ping/Database")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["result"]["id"] == "Database"
    assert data["result"]["latency_ms"] is not None
    assert data["result"]["status"] == "ONLINE"

    # Ping RFID reader
    res_rfid = client.post("/api/tools/ping/Gate01_Entry")
    assert res_rfid.status_code == 200
    rfid_data = res_rfid.json()
    assert rfid_data["ok"] is True
    assert rfid_data["result"]["id"] == "Gate01_Entry"
    assert rfid_data["result"]["latency_ms"] is not None

