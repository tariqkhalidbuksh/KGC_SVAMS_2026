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
    # Day 1: 2026-10-06 (Entry + Exit = 45m stay)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-01-In', 'E280116060000204', '2026-10-06 09:00:00')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-01-Out', 'E280116060000204', '2026-10-06 09:45:00')
    """)

    # Day 2: 2026-10-08 (Two visits: 08:00-08:15 = 15m, 14:00-14:30 = 30m => total 45m)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-02-In', 'E280116060000204', '2026-10-08 08:00:00')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-02-Out', 'E280116060000204', '2026-10-08 08:15:00')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Entry', 'Gate-01-In', 'E280116060000204', '2026-10-08 14:00:00')
    """)
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('M-7788', 'Tariq Al-Rashid', 'KGC-9900', 'RFID', 'Exit', 'Gate-01-Out', 'E280116060000204', '2026-10-08 14:30:00')
    """)

    # Unregistered tag scanned at gate
    conn.execute("""
        INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
        VALUES ('GUEST-LOG', 'Guest / Unregistered', 'UNREGISTERED', 'RFID', 'Entry', 'Gate-01-In', 'E280999900000111', '2026-10-08 16:00:00')
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
    assert summary["first_detected"] == "2026-10-06 09:00:00"
    assert summary["latest_detected"] == "2026-10-08 14:30:00"
    assert "Gate-01-In" in summary["readers_breakdown"]
    assert "Gate-02-In" in summary["readers_breakdown"]

    # Daily breakdown verification
    daily = data["daily_breakdown"]
    assert len(daily) == 2

    # Newest day first: 2026-10-08
    day_oct8 = daily[0]
    assert day_oct8["date"] == "2026-10-08"
    assert day_oct8["total_detections"] == 4
    assert day_oct8["entries"] == 2
    assert day_oct8["exits"] == 2
    assert day_oct8["first_scan_time"] == "08:00:00"
    assert day_oct8["last_scan_time"] == "14:30:00"
    assert day_oct8["visits_count"] == 2
    assert day_oct8["stay_duration"] == "45m"
    assert day_oct8["readers"]["Gate-02-In"] == 1
    assert day_oct8["readers"]["Gate-01-In"] == 1

    # Day 2: 2026-10-06
    day_oct6 = daily[1]
    assert day_oct6["date"] == "2026-10-06"
    assert day_oct6["total_detections"] == 2
    assert day_oct6["entries"] == 1
    assert day_oct6["exits"] == 1
    assert day_oct6["first_scan_time"] == "09:00:00"
    assert day_oct6["last_scan_time"] == "09:45:00"
    assert day_oct6["visits_count"] == 1
    assert day_oct6["stay_duration"] == "45m"

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
    assert data["daily_breakdown"][0]["date"] == "2026-10-08"

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
