import os
import pytest
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

TODAY_STR = datetime.now().strftime("%Y-%m-%d")
PAST_STR = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

@pytest.fixture(autouse=True)
def setup_etag_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_etag_audit.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()

    conn = get_db_connection()
    # Insert test member
    conn.execute("""
        INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'Toyota Prado 2024', 'E280116060000204', 'Active')
    """)

    # Insert multi-day scans for this member
    # Day 1: PAST_STR (Entry + Exit = 45m stay)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-01-In', 'E280116060000204', '{PAST_STR} 09:00:00')
    """)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-01-Out', 'E280116060000204', '{PAST_STR} 09:45:00')
    """)

    # Day 2: TODAY_STR (Two visits: 08:00-08:15 = 15m, 14:00-14:30 = 30m => total 45m)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-02-In', 'E280116060000204', '{TODAY_STR} 08:00:00')
    """)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-02-Out', 'E280116060000204', '{TODAY_STR} 08:15:00')
    """)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-01-In', 'E280116060000204', '{TODAY_STR} 14:00:00')
    """)
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-01-Out', 'E280116060000204', '{TODAY_STR} 14:30:00')
    """)

    # Unregistered tag scanned at gate
    conn.execute(f"""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('GUEST-LOG', 'Guest / Unregistered', 'UNREGISTERED', 'RFID', 'Entry', 'Gate-01-In', 'E280999900000111', '{TODAY_STR} 16:00:00')
    """)

    conn.commit()
    conn.close()
    return test_db

def test_etag_audit_redirects():
    """Verify clean URL redirects to the E-TAG Audit tab."""
    for path in ["/etag-audit", "/tag-audit", "/tag-activity"]:
        res = client.get(path, follow_redirects=False)
        assert res.status_code in (302, 307)
        assert res.headers["location"] == "/?tab=etag_audit"

def test_etag_recent_tags_endpoint():
    """Verify /api/etag/recent-tags returns valid list with required fields."""
    res = client.get("/api/etag/recent-tags?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    tags = [t["scanned_tag"] for t in data["tags"]]
    assert "E280116060000204" in tags
    assert "E280999900000111" in tags

def test_etag_audit_registered_member_multi_day():
    """Verify full audit breakdown for registered member across multiple days."""
    res = client.get("/api/etag/audit?tag_id=E280116060000204")
    assert res.status_code == 200
    data = res.json()

    assert data["found"] is True
    assert data["is_registered"] is True
    assert data["tag_id"] == "E280116060000204"

    # Member verification
    member = data["member"]
    assert member["is_registered"] is True
    assert member["name"] == "Tariq Al-Rashid"
    assert member["mem_id"] == "M-7788"
    assert member["vehicle_number"] == "KGC-9900"
    assert member["make_model"] == "Toyota Prado 2024"

    # Summary verification
    summary = data["summary"]
    assert summary["total_detections"] == 6
    assert summary["days_active"] == 2
    assert summary["first_detected"] == f"{PAST_STR} 09:00:00"
    assert summary["latest_detected"] == f"{TODAY_STR} 14:30:00"
    assert "Gate-01-In" in summary["readers_breakdown"]
    assert "Gate-02-In" in summary["readers_breakdown"]

    # Daily breakdown verification
    daily = data["daily_breakdown"]
    assert len(daily) == 2

    # Newest day first: TODAY_STR
    day_today = daily[0]
    assert day_today["date"] == TODAY_STR
    assert day_today["total_detections"] == 4
    assert day_today["entries"] == 2
    assert day_today["exits"] == 2
    assert day_today["first_scan_time"] == "08:00:00"
    assert day_today["last_scan_time"] == "14:30:00"
    assert day_today["visits_count"] == 2
    assert day_today["stay_duration"] == "45m"
    assert day_today["readers"]["Gate-02-In"] == 1
    assert day_today["readers"]["Gate-01-In"] == 1

    # Day 2: PAST_STR
    day_past = daily[1]
    assert day_past["date"] == PAST_STR
    assert day_past["total_detections"] == 2
    assert day_past["entries"] == 1
    assert day_past["exits"] == 1
    assert day_past["first_scan_time"] == "09:00:00"
    assert day_past["last_scan_time"] == "09:45:00"
    assert day_past["visits_count"] == 1
    assert day_past["stay_duration"] == "45m"

    # Full scans chronological verification
    scans = data["scans"]
    assert len(scans) == 6

def test_etag_audit_unregistered_tag():
    """Verify audit handles standalone unregistered tag cleanly."""
    res = client.get("/api/etag/audit?tag_id=E280999900000111")
    assert res.status_code == 200
    data = res.json()

    assert data["found"] is True
    assert data["is_registered"] is False
    assert data["member"]["is_registered"] is False
    assert data["summary"]["total_detections"] == 1
    assert data["daily_breakdown"][0]["date"] == TODAY_STR

def test_etag_audit_unknown_tag():
    """Verify audit handles non-existent tag gracefully."""
    res = client.get("/api/etag/audit?tag_id=E280000000000000")
    assert res.status_code == 200
    data = res.json()

    assert data["found"] is False
    assert data["summary"]["total_detections"] == 0
    assert len(data["daily_breakdown"]) == 0
    assert len(data["scans"]) == 0

def test_etag_audit_empty_or_whitespace():
    """Verify validation when tag_id is empty or blank."""
    res = client.get("/api/etag/audit?tag_id=")
    assert res.status_code == 400
    res2 = client.get("/api/etag/audit?tag_id=   ")
    assert res2.status_code == 400


def test_etag_audit_date_filters():
    """Verify that E-TAG audit date filtering (today, yesterday, week, month, all) works accurately."""
    tag = "E280116060000204"

    # All time
    res_all = client.get(f"/api/etag/audit?tag_id={tag}&date_filter=all")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["summary"]["total_detections"] == 6

    # Today
    res_today = client.get(f"/api/etag/audit?tag_id={tag}&date_filter=today")
    assert res_today.status_code == 200
    data_today = res_today.json()
    assert data_today["date_filter"] == "today"
    # Should only return detections for TODAY_STR (4 detections)
    assert data_today["summary"]["total_detections"] == 4
    assert len(data_today["daily_breakdown"]) == 1
    assert data_today["daily_breakdown"][0]["date"] == TODAY_STR

    # Week (past 7 days covers both PAST_STR and TODAY_STR)
    res_week = client.get(f"/api/etag/audit?tag_id={tag}&date_filter=week")
    assert res_week.status_code == 200
    data_week = res_week.json()
    assert data_week["summary"]["total_detections"] == 6


def test_recent_tags_deduplication_and_search():
    """Verify that recent-tags returns strictly unique tags and supports search."""
    res = client.get("/api/etag/recent-tags?limit=50")
    assert res.status_code == 200
    data = res.json()
    tags = data["tags"]
    assert len(tags) > 0

    # Ensure uniqueness: every tag appears at most once
    tag_ids = [t["scanned_tag"] for t in tags]
    assert len(tag_ids) == len(set(tag_ids))

    # Test search by member name or plate
    search_res = client.get("/api/etag/recent-tags?search=Tariq")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert any(t["scanned_tag"] == "E280116060000204" for t in search_data["tags"])


def test_etag_recent_tags_pagination():
    """Verify pagination support (page, limit, pages, offset) on /api/etag/recent-tags."""
    # Page 1 with limit 1
    p1 = client.get("/api/etag/recent-tags?page=1&limit=1")
    assert p1.status_code == 200
    d1 = p1.json()
    assert d1["page"] == 1
    assert d1["limit"] == 1
    assert d1["total"] >= 2
    assert d1["pages"] >= 2
    assert len(d1["tags"]) == 1
    tag_p1 = d1["tags"][0]["scanned_tag"]

    # Page 2 with limit 1
    p2 = client.get("/api/etag/recent-tags?page=2&limit=1")
    assert p2.status_code == 200
    d2 = p2.json()
    assert d2["page"] == 2
    assert d2["limit"] == 1
    assert len(d2["tags"]) == 1
    tag_p2 = d2["tags"][0]["scanned_tag"]

    # Tags on different pages should not be the same
    assert tag_p1 != tag_p2


