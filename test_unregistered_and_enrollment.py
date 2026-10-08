import os
import pytest
import json
import time
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
from services.access_service import execute_access_decision

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_unreg_enroll.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()
    # Reset recent tag memory buffers
    config.RECENT_TAGS.clear()
    return test_db


def test_unregistered_state_machine_flow():
    """
    Test the multi-tier state machine for unregistered vehicles:
    1. First scan (cold start) -> sets Current_Location='Inside', resolved_direction='Entry'.
    2. Second scan (vehicle physically Inside) -> resolved_direction='Exit', Current_Location='Outside'.
    3. Third scan (vehicle physically Outside) -> resolved_direction='Entry', Current_Location='Inside'.
    """
    tag = "E280777700000001"

    # 1. Cold start entry
    log_id1 = execute_access_decision(tag=tag, direction="Entry", bypass_cooldown=True)
    assert log_id1 > 0

    conn = get_db_connection()
    log1 = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id1,)).fetchone()
    assert log1["direction"] == "Entry"
    assert log1["access_type"] == "RFID Unknown"

    unreg = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg is not None
    assert unreg["Current_Location"] == "Inside"
    assert unreg["direction"] == "Entry"
    assert unreg["read_count"] == 1
    conn.close()

    # 2. While vehicle is physically inside, next transit MUST be Exit
    # Even if reader trigger is ambiguous or absent, the state machine resolves Exit
    log_id2 = execute_access_decision(tag=tag, direction="Auto", bypass_cooldown=True)
    assert log_id2 > 0

    conn = get_db_connection()
    log2 = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id2,)).fetchone()
    assert log2["direction"] == "Exit"

    unreg2 = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg2["Current_Location"] == "Outside"
    assert unreg2["direction"] == "Exit"
    assert unreg2["read_count"] == 2
    conn.close()

    # 3. While vehicle is physically outside, next transit MUST be Entry
    log_id3 = execute_access_decision(tag=tag, direction="Auto", bypass_cooldown=True)
    assert log_id3 > 0

    conn = get_db_connection()
    log3 = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id3,)).fetchone()
    assert log3["direction"] == "Entry"

    unreg3 = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg3["Current_Location"] == "Inside"
    assert unreg3["direction"] == "Entry"
    assert unreg3["read_count"] == 3
    conn.close()


def test_unregistered_api_returns_current_location():
    """Verify GET /api/unregistered-tags returns Current_Location for each tag."""
    tag = "E280888800000002"
    execute_access_decision(tag=tag, direction="Entry", bypass_cooldown=True)

    res = client.get("/api/unregistered-tags")
    assert res.status_code == 200
    tags = res.json()
    assert len(tags) >= 1

    matched = next((t for t in tags if t["tag"] == tag), None)
    assert matched is not None
    assert matched["Current_Location"] == "Inside"
    assert matched["direction"] == "Entry"
    assert matched["read_count"] >= 1


def test_enroll_unregistered_tag_endpoint_happy_path():
    """
    Verify POST /api/members/enroll-unregistered-tag:
    - Enrolls unregistered tag into members table.
    - Inherits active Current_Location from unregistered_tags.
    - Removes tag from unregistered_tags buffer.
    - Retroactively enriches historical daily_logs for that tag.
    """
    tag = "E280999900000003"
    # Tag scanned at gate as unregistered
    execute_access_decision(tag=tag, direction="Entry", bypass_cooldown=True)

    # Verify log was created as GUEST-LOG
    conn = get_db_connection()
    log_before = conn.execute("SELECT * FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchone()
    assert log_before is not None
    assert log_before["mem_id"] == "GUEST-LOG"
    conn.close()

    payload = {
        "tag": tag,
        "mem_id": "M-8899",
        "name": "Engr. Tariq",
        "car_number": "ABC-9999",
        "make_model": "Mercedes E-Class",
        "status": "Active"
    }

    res = client.post("/api/members/enroll-unregistered-tag", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["current_location"] == "Inside"
    assert data["mem_id"] == "M-8899"

    # Check members table
    conn = get_db_connection()
    mem = conn.execute("SELECT * FROM members WHERE Mem_id='M-8899'").fetchone()
    assert mem is not None
    assert mem["Name"] == "Engr. Tariq"
    assert mem["Car_number"] == "ABC-9999"
    assert mem["E_tag_id"] == tag
    assert mem["Current_Location"] == "Inside"

    # Verify removed from unregistered_tags
    unreg = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg is None

    # Verify retroactive enrichment in daily_logs
    log_after = conn.execute("SELECT * FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchone()
    assert log_after["mem_id"] == "M-8899"
    assert log_after["name"] == "Engr. Tariq"
    assert log_after["vehicle_number"] == "ABC-9999"
    conn.close()


def test_enroll_unregistered_tag_endpoint_validation():
    """Verify input validation for enrollment endpoint."""
    # Missing tag
    res1 = client.post("/api/members/enroll-unregistered-tag", json={"mem_id": "M-1", "car_number": "CAR-1"})
    assert res1.status_code == 400

    # Missing mem_id
    res2 = client.post("/api/members/enroll-unregistered-tag", json={"tag": "TAG-1", "car_number": "CAR-1"})
    assert res2.status_code == 400

    # Missing car_number
    res3 = client.post("/api/members/enroll-unregistered-tag", json={"tag": "TAG-1", "mem_id": "M-1"})
    assert res3.status_code == 400


def test_add_member_inherits_unregistered_location_and_enriches_logs():
    """
    Verify that standard POST /api/add-member:
    - Inherits Current_Location from unregistered_tags when linking a detected tag.
    - Removes the tag from unregistered_tags.
    - Retroactively enriches daily_logs guest transits.
    """
    tag = "E280555500000004"
    # Tag scanned at entry gate
    execute_access_decision(tag=tag, direction="Entry", bypass_cooldown=True)

    add_res = client.post("/api/add-member", json={
        "mem_id": "M-5555",
        "name": "General Member",
        "car_number": "LE-555",
        "make_model": "Civic RS",
        "e_tag_id": tag
    })
    assert add_res.status_code == 200

    conn = get_db_connection()
    # Member has Current_Location = 'Inside'
    mem = conn.execute("SELECT * FROM members WHERE E_tag_id=?", (tag,)).fetchone()
    assert mem["Current_Location"] == "Inside"

    # Tag removed from unregistered_tags
    unreg = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg is None

    # Past transits enriched
    log = conn.execute("SELECT * FROM daily_logs WHERE scanned_tag=?", (tag,)).fetchone()
    assert log["mem_id"] == "M-5555"
    assert log["name"] == "General Member"
    assert log["vehicle_number"] == "LE-555"
    conn.close()


def test_unregistered_dismiss_api():
    """Verify DELETE /api/unregistered-tags/{tag} removes tag cleanly."""
    tag = "E280123400000005"
    execute_access_decision(tag=tag, direction="Entry", bypass_cooldown=True)

    del_res = client.delete(f"/api/unregistered-tags/{tag}")
    assert del_res.status_code == 200

    conn = get_db_connection()
    unreg = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (tag,)).fetchone()
    assert unreg is None
    conn.close()
