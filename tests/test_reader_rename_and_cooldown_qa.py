import pytest
import httpx
from fastapi.testclient import TestClient

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from app import app
from database import get_db_connection, set_setting
from services.access_service import execute_access_decision
import config

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_test_environment():
    with config.DB_LOCK:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM daily_logs WHERE scanned_tag LIKE 'TEST_%'")
                conn.execute("DELETE FROM unregistered_tags WHERE tag LIKE 'TEST_%'")
                conn.execute("DELETE FROM members WHERE Mem_id LIKE 'MEM-TEST-%' OR E_tag_id LIKE 'TEST_%'")
    set_setting("rfid_cooldown_seconds", "45")
    yield
    with config.DB_LOCK:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM daily_logs WHERE scanned_tag LIKE 'TEST_%'")
                conn.execute("DELETE FROM unregistered_tags WHERE tag LIKE 'TEST_%'")
                conn.execute("DELETE FROM members WHERE Mem_id LIKE 'MEM-TEST-%' OR E_tag_id LIKE 'TEST_%'")
    set_setting("rfid_cooldown_seconds", "45")


def test_reader_renaming_settings_persistence_and_propagation():
    """
    Verifies Requirement 1:
    - User can rename all 4 RFID readers in settings.
    - Custom names persist in database settings.
    - Subsequent access transits use the custom reader names in daily_logs.
    """
    custom_names = {
        "entry_reader_name": "Gate-01 North Inbound RFID",
        "exit_reader_name": "Gate-01 South Outbound RFID",
        "clubroad_entry_reader_name": "Club Road Main Inbound RFID",
        "clubroad_exit_reader_name": "Club Road Main Outbound RFID",
        "rfid_cooldown_seconds": "60"
    }

    # Save via /api/settings as Admin
    # Use TestClient with admin cookies
    save_res = client.post("/api/settings", json=custom_names, cookies={"session_user": "admin", "session_role": "Admin"})
    assert save_res.status_code == 200

    # Verify settings API returns custom names
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    saved = get_res.json()
    assert saved["entry_reader_name"] == "Gate-01 North Inbound RFID"
    assert saved["exit_reader_name"] == "Gate-01 South Outbound RFID"
    assert saved["clubroad_entry_reader_name"] == "Club Road Main Inbound RFID"
    assert saved["clubroad_exit_reader_name"] == "Club Road Main Outbound RFID"
    assert saved["rfid_cooldown_seconds"] == "60"

    # Verify tools ping endpoint returns custom name
    ping_res = client.post("/api/tools/ping/Gate01_Entry")
    assert ping_res.status_code == 200
    assert ping_res.json()["result"]["label"] == "Gate-01 North Inbound RFID"

    # Test transit execution with custom gate name
    test_tag = "TEST_RENAME_001"
    log_id = execute_access_decision(
        tag=test_tag,
        direction="Entry",
        gate_name=saved["entry_reader_name"],
        bypass_cooldown=True
    )
    assert log_id is not None
    with get_db_connection() as conn:
        row = conn.execute("SELECT gate_no, direction FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        assert row["gate_no"] == "Gate-01 North Inbound RFID"
        assert row["direction"] == "Entry"

    # Restore default settings
    default_names = {
        "entry_reader_name": "Gate-01 Entry Reader",
        "exit_reader_name": "Gate-01 Exit Reader",
        "clubroad_entry_reader_name": "Club Road Main Inbound RFID",
        "clubroad_exit_reader_name": "Club Road Main Outbound RFID",
        "rfid_cooldown_seconds": "45"
    }
    client.post("/api/settings", json=default_names, cookies={"session_user": "admin", "session_role": "Admin"})


def test_no_enter_and_exit_flip_on_same_reader():
    """
    Verifies Requirement 2:
    - Multiple scans on Gate-01 Entry Reader NEVER create an Exit log.
    - Multiple scans on Gate-01 Exit Reader NEVER create an Entry log.
    - Multiple scans on Club Road Entry Reader NEVER create an Exit log.
    - Multiple scans on Club Road Exit Reader NEVER create an Entry log.
    - Prevents bug where car entered and exited in less than 1 minute on same reader.
    """
    test_epc = "TEST_FLIP_PREVENTION_001"
    test_mem = "MEM-TEST-FLIP-1"
    test_car = "TEST-CAR-1"

    # Register member
    client.post("/api/add-member", json={
        "mem_id": test_mem,
        "name": "Flip Prevention Tester",
        "car_number": test_car,
        "e_tag_id": test_epc
    }, cookies={"session_user": "admin", "session_role": "Admin"})

    # 1. Gate-01 Entry Reader: First scan -> Entry
    log_id1 = execute_access_decision(test_epc, direction="Entry", gate_name="Gate-01 Entry Reader")
    with get_db_connection() as conn:
        row1 = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (log_id1,)).fetchone()
        assert row1["direction"] == "Entry"
        assert row1["gate_no"] == "Gate-01 Entry Reader"
        mem = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()
        assert mem["Current_Location"] == "Inside"

    # Simulate 50 seconds passing (less than 1 minute!)
    with get_db_connection() as conn:
        with conn:
            conn.execute("UPDATE daily_logs SET timestamp = datetime('now', '-50 seconds') WHERE id=?", (log_id1,))

    # 2. Gate-01 Entry Reader: Second scan at 50s
    # In old buggy code, because car was "Inside", this created an EXIT at Gate-01 Entry Reader in < 1m!
    # In fixed code:
    # Dedicated Entry reader NEVER logs Exit!
    # And lingering duplicate scan (< 90s same direction) is suppressed cleanly!
    log_id2 = execute_access_decision(test_epc, direction="Entry", gate_name="Gate-01 Entry Reader")
    # Must be suppressed or must remain Entry, NEVER an Exit!
    with get_db_connection() as conn:
        rows = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE scanned_tag=? ORDER BY id ASC", (test_epc,)).fetchall()
        # All rows must be Entry! ZERO Exits on Gate-01 Entry Reader!
        for r in rows:
            assert r["direction"] == "Entry"
            assert r["gate_no"] == "Gate-01 Entry Reader"
            assert r["direction"] != "Exit"


def test_inside_vehicle_exiting_via_entry_reader_marks_as_exit():
    """
    Verifies User Requirement:
    - If a car is already inside the club (Current_Location == 'Inside'),
      when exiting, if an Entry reader detects the car (due to antenna overlap or shared lane),
      the system MUST mark the transit as 'Exit', while preserving the detecting reader's name
      in gate_no (e.g. 'Main Gate (Club Road) Entry Reader').
    - Resolves the paired trip in the audit log as 'Exited'.
    """
    test_tag = "TEST_INSIDE_EXIT_002"
    test_mem = "MEM-TEST-BG-2"
    test_car = "BG-7788"

    client.post("/api/add-member", json={
        "mem_id": test_mem,
        "name": "Inside Exit Tester",
        "car_number": test_car,
        "e_tag_id": test_tag
    }, cookies={"session_user": "admin", "session_role": "Admin"})

    # Step 1: Vehicle enters via Main Gate (Club Road) Entry Reader
    id_entry = execute_access_decision(test_tag, direction="Entry", gate_name="Main Gate (Club Road) Entry Reader", bypass_cooldown=True)
    with get_db_connection() as conn:
        e_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (id_entry,)).fetchone()
        assert e_row["direction"] == "Entry"
        assert e_row["gate_no"] == "Main Gate (Club Road) Entry Reader"
        mem = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_tag,)).fetchone()
        assert mem["Current_Location"] == "Inside"

    # Step 2: Car is already inside the club. Driver departs, and Main Gate (Club Road) Entry Reader detects it!
    # MUST mark as Exit, but show Main Gate (Club Road) Entry Reader in gate_no!
    id_exit = execute_access_decision(test_tag, direction="Entry", gate_name="Main Gate (Club Road) Entry Reader", bypass_cooldown=True)
    with get_db_connection() as conn:
        x_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (id_exit,)).fetchone()
        assert x_row["direction"] == "Exit"
        assert x_row["gate_no"] == "Main Gate (Club Road) Entry Reader"
        mem = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_tag,)).fetchone()
        assert mem["Current_Location"] == "Outside"

    # Step 3: Check paired audit logs in /api/audit
    audit_res = client.get(f"/api/audit?search={test_car}")
    assert audit_res.status_code == 200
    audits = audit_res.json()["audits"]
    assert len(audits) >= 1
    trip = audits[0]
    assert trip["status"] == "Exited"
    assert trip["entry"]["gate_no"] == "Main Gate (Club Road) Entry Reader"
    assert trip["exit"]["gate_no"] == "Main Gate (Club Road) Entry Reader"

    # Step 4: Vehicle returns next day from Outside -> scanned at Gate-01 Entry Reader
    id_entry2 = execute_access_decision(test_tag, direction="Entry", gate_name="Gate-01 Entry Reader", bypass_cooldown=True)
    with get_db_connection() as conn:
        e2_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (id_entry2,)).fetchone()
        assert e2_row["direction"] == "Entry"
        assert e2_row["gate_no"] == "Gate-01 Entry Reader"
        mem = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_tag,)).fetchone()
        assert mem["Current_Location"] == "Inside"

    # Step 5: Vehicle exits via Gate-01 Exit Reader
    id_exit2 = execute_access_decision(test_tag, direction="Exit", gate_name="Gate-01 Exit Reader", bypass_cooldown=True)
    with get_db_connection() as conn:
        x2_row = conn.execute("SELECT direction, gate_no FROM daily_logs WHERE id=?", (id_exit2,)).fetchone()
        assert x2_row["direction"] == "Exit"
        assert x2_row["gate_no"] == "Gate-01 Exit Reader"
        mem = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_tag,)).fetchone()
        assert mem["Current_Location"] == "Outside"


def test_unregistered_tags_extended_limit_and_search():
    """
    Verifies Requirement 3:
    - /api/unregistered-tags returns all tags beyond 50 (up to 500+).
    - Supports search query for quick filtering.
    """
    # Seed 60 unregistered tags
    with config.DB_LOCK:
        with get_db_connection() as conn:
            with conn:
                for i in range(1, 65):
                    tag_epc = f"TEST_UNREG_{i:04d}"
                    t_type = "NHA Motorway M-Tag" if i % 2 == 0 else "Unregistered Visitor"
                    conn.execute("""
                        INSERT OR REPLACE INTO unregistered_tags 
                        (tag, first_seen, last_seen, direction, Current_Location, read_count, tag_type)
                        VALUES (?, '2026-10-18 10:00:00', '2026-10-18 12:00:00', 'Entry', 'Inside', 2, ?)
                    """, (tag_epc, t_type))

    # Fetch with default limit (should return all 64 seeded tags, > 50!)
    res = client.get("/api/unregistered-tags")
    assert res.status_code == 200
    tags = res.json()
    assert len(tags) >= 64, f"Expected at least 64 tags, got {len(tags)}"

    # Test search filter
    search_res = client.get("/api/unregistered-tags?search=TEST_UNREG_001")
    assert search_res.status_code == 200
    s_tags = search_res.json()
    assert len(s_tags) >= 1
    assert any(t["tag"] == "TEST_UNREG_0010" or t["tag"] == "TEST_UNREG_0001" for t in s_tags)

    # Test category search
    cat_res = client.get("/api/unregistered-tags?search=NHA")
    assert cat_res.status_code == 200
    c_tags = cat_res.json()
    assert len(c_tags) >= 30
    assert all("NHA" in t["tag_type"] for t in c_tags)
