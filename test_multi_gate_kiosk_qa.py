import pytest
import httpx
from fastapi.testclient import TestClient

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from app import app
from database import get_db_connection
from services.access_service import execute_access_decision
import config

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_test_environment():
    with config.CACHE_LOCK:
        config.LATEST_LOG_CACHE = None
        if hasattr(config, "LATEST_GATE_LOG_CACHE"):
            config.LATEST_GATE_LOG_CACHE["gate01"] = None
            config.LATEST_GATE_LOG_CACHE["clubroad"] = None
    with config.DB_LOCK:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM daily_logs WHERE scanned_tag LIKE 'TEST_KIOSK_%'")
                conn.execute("DELETE FROM unregistered_tags WHERE tag LIKE 'TEST_KIOSK_%'")
                conn.execute("DELETE FROM members WHERE Mem_id LIKE 'MEM-KIOSK-%' OR E_tag_id LIKE 'TEST_KIOSK_%'")
    yield
    with config.DB_LOCK:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM daily_logs WHERE scanned_tag LIKE 'TEST_KIOSK_%'")
                conn.execute("DELETE FROM unregistered_tags WHERE tag LIKE 'TEST_KIOSK_%'")
                conn.execute("DELETE FROM members WHERE Mem_id LIKE 'MEM-KIOSK-%' OR E_tag_id LIKE 'TEST_KIOSK_%'")


def test_kiosk_routes_and_html_elements():
    """Verify all kiosk endpoints render properly with the gate switcher."""
    for path in ["/kiosk", "/kiosk/gate01", "/kiosk/clubroad", "/kiosk/rear", "/kiosk/main"]:
        res = client.get(path)
        assert res.status_code == 200, f"Failed for path {path}"
        html = res.text
        assert "btnGate01" in html
        assert "btnClubRoad" in html
        assert "Gate 01 (Rear Gate)" in html
        assert "Club Road Gate" in html
        assert "kioskClock" in html
        assert "recentCardsContainer" in html

    # Verify kiosk.js contains multi-gate logic
    js_res = client.get("/static/js/kiosk.js")
    assert js_res.status_code == 200
    js_text = js_res.text
    assert "setKioskGate" in js_text
    assert "initGateSelection" in js_text
    assert "applyGateUI" in js_text
    assert "latest-log?gate=" in js_text
    assert "recent-entries?limit=4&gate=" in js_text


def test_per_gate_latest_log_isolation():
    """
    Verify that Gate 01 scans only trigger Gate 01 kiosk,
    and Club Road scans only trigger Club Road kiosk.
    """
    tag_g01 = "TEST_KIOSK_G01_TAG1"
    tag_club = "TEST_KIOSK_CLUB_TAG2"

    # Step 1: Car passes Gate 01 reader
    g01_log_id = execute_access_decision(
        tag=tag_g01,
        direction="Entry",
        gate_name="Gate-01 Entry Reader",
        bypass_cooldown=True
    )
    assert g01_log_id is not None

    # Gate 01 kiosk poll MUST see the scan
    res_g01 = client.get("/api/latest-log?gate=gate01")
    assert res_g01.status_code == 200
    data_g01 = res_g01.json()
    assert data_g01.get("id") == g01_log_id
    assert data_g01.get("scanned_tag") == tag_g01
    assert "Gate-01" in data_g01.get("gate_no", "")

    # Club Road kiosk poll MUST NOT see the Gate 01 scan
    res_club = client.get("/api/latest-log?gate=clubroad")
    assert res_club.status_code == 200
    data_club = res_club.json()
    # If empty or not matching g01_log_id
    assert data_club.get("id") != g01_log_id

    # Step 2: Car passes Club Road reader
    club_log_id = execute_access_decision(
        tag=tag_club,
        direction="Entry",
        gate_name="Main Gate (Club Road) Entry Reader",
        bypass_cooldown=True
    )
    assert club_log_id is not None

    # Club Road kiosk poll MUST see the Club Road scan
    res_club_after = client.get("/api/latest-log?gate=clubroad")
    assert res_club_after.status_code == 200
    data_club_after = res_club_after.json()
    assert data_club_after.get("id") == club_log_id
    assert data_club_after.get("scanned_tag") == tag_club
    assert "Club" in data_club_after.get("gate_no", "")

    # Gate 01 kiosk poll MUST STILL show its own Gate 01 scan (not overwritten by Club Road)
    res_g01_after = client.get("/api/latest-log?gate=gate01")
    assert res_g01_after.status_code == 200
    data_g01_after = res_g01_after.json()
    assert data_g01_after.get("id") == g01_log_id


def test_per_gate_recent_entries_filtering():
    """Verify that recent entries returns cards specifically for the requested gate."""
    tag_g01_a = "TEST_KIOSK_G01_REC_A"
    tag_club_b = "TEST_KIOSK_CLUB_REC_B"

    execute_access_decision(tag=tag_g01_a, direction="Entry", gate_name="Gate-01 Entry Reader", bypass_cooldown=True)
    execute_access_decision(tag=tag_club_b, direction="Entry", gate_name="Main Gate (Club Road) Entry Reader", bypass_cooldown=True)

    # Check Gate 01 recent entries
    res_g01 = client.get("/api/recent-entries?limit=5&gate=gate01")
    assert res_g01.status_code == 200
    entries_g01 = res_g01.json()
    assert len(entries_g01) > 0
    for e in entries_g01:
        assert "Club" not in e["gate_no"]

    # Check Club Road recent entries
    res_club = client.get("/api/recent-entries?limit=5&gate=clubroad")
    assert res_club.status_code == 200
    entries_club = res_club.json()
    assert len(entries_club) > 0
    for e in entries_club:
        assert "Club" in e["gate_no"] or "Main" in e["gate_no"]


def test_dashboard_gate_kiosks_integration():
    """Verify dashboard navigation links and mini-kiosk widget contain both gate screens."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    # Sidebar links
    assert "/kiosk?gate=gate01" in html
    assert "/kiosk?gate=clubroad" in html
    # Mini widget toggle buttons
    assert "btnMiniGate01" in html
    assert "btnMiniClubRoad" in html
