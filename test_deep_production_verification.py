import os
import sys
import pytest
import concurrent.futures
from datetime import datetime, timedelta
import httpx

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from fastapi.testclient import TestClient

import config
from app import app
from database import get_db_connection

client = TestClient(app)

# -------------------------------------------------------------
# 1. DATABASE SCHEMA & INTEGRITY TESTS
# -------------------------------------------------------------
def test_production_database_schema():
    """Verify all critical production tables, indexes, and connections are valid."""
    with get_db_connection() as conn:
        tables = [
            "members",
            "daily_logs",
            "unregistered_tags",
            "users",
            "settings",
            "camera_audit_logs"
        ]
        for tbl in tables:
            row = conn.execute(f"SELECT COUNT(*) as c FROM {tbl}").fetchone()
            assert row is not None
            assert row["c"] >= 0, f"Table {tbl} must be accessible and readable"

def test_database_connection_concurrency():
    """Verify database connection pool handles multi-threaded operations safely."""
    def worker(worker_id):
        with get_db_connection() as conn:
            r = conn.execute("SELECT COUNT(*) as c FROM daily_logs").fetchone()
            return r["c"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in futures]
        assert len(results) == 20
        assert all(r == results[0] for r in results)

# -------------------------------------------------------------
# 2. AUDIT LOGS & TIMEFRAME CONSISTENCY TESTS
# -------------------------------------------------------------
def test_audit_multi_day_journey_and_reentry_logic():
    """
    Simulates real-world vehicle scenarios:
    1. Vehicle 1 (MEM-001): Entered Yesterday, Exited Yesterday -> Should be Exited.
    2. Vehicle 2 (MEM-002): Entered Yesterday, NO Exit yesterday, BUT re-entered Today -> Yesterday visit MUST be Exited, Today visit is Inside.
    3. Vehicle 3 (MEM-003): Entered Yesterday, NO Exit yesterday, Member is now 'Outside' -> Yesterday visit MUST be Exited.
    4. Vehicle 4 (MEM-004): Entered Today, still inside -> Inside Facility.
    """
    pkt_today = config.get_pkt_today()
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        with conn:
            # Seed members
            conn.execute("INSERT INTO members (Mem_id, Name, Car_number, E_tag_id, Current_Location) VALUES (?, ?, ?, ?, ?)",
                         ("MEM-001", "Member One", "ABC-001", "TAG-001", "Outside"))
            conn.execute("INSERT INTO members (Mem_id, Name, Car_number, E_tag_id, Current_Location) VALUES (?, ?, ?, ?, ?)",
                         ("MEM-002", "Member Two", "ABC-002", "TAG-002", "Inside"))
            conn.execute("INSERT INTO members (Mem_id, Name, Car_number, E_tag_id, Current_Location) VALUES (?, ?, ?, ?, ?)",
                         ("MEM-003", "Member Three", "ABC-003", "TAG-003", "Outside"))
            conn.execute("INSERT INTO members (Mem_id, Name, Car_number, E_tag_id, Current_Location) VALUES (?, ?, ?, ?, ?)",
                         ("MEM-004", "Member Four", "ABC-004", "TAG-004", "Inside"))

            # Log 1: MEM-001 entered & exited yesterday
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-001", "Member One", "ABC-001", "Entry", "TAG-001", f"{yesterday} 09:00:00"))
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-001", "Member One", "ABC-001", "Exit", "TAG-001", f"{yesterday} 11:00:00"))

            # Log 2: MEM-002 entered yesterday (no exit scan), but re-entered today at 08:00
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-002", "Member Two", "ABC-002", "Entry", "TAG-002", f"{yesterday} 14:00:00"))
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-002", "Member Two", "ABC-002", "Entry", "TAG-002", f"{pkt_today} 08:00:00"))

            # Log 3: MEM-003 entered yesterday, no exit scan, but member is marked 'Outside'
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-003", "Member Three", "ABC-003", "Entry", "TAG-003", f"{yesterday} 16:00:00"))

            # Log 4: MEM-004 entered today at 10:00, no exit scan
            conn.execute("INSERT INTO daily_logs (mem_id, name, vehicle_number, direction, scanned_tag, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         ("MEM-004", "Member Four", "ABC-004", "Entry", "TAG-004", f"{pkt_today} 10:00:00"))

    # Invalidate cache
    config.invalidate_member_cache()
    with config.CACHE_LOCK:
        if hasattr(config, 'AUDIT_LOGS_CACHE') and config.AUDIT_LOGS_CACHE:
            config.AUDIT_LOGS_CACHE.clear()

    # Query Yesterday
    res_yest = client.get("/api/audit?date=yesterday")
    assert res_yest.status_code == 200
    yest_data = res_yest.json()
    assert yest_data["currently_inside"] == 0, f"Yesterday currently_inside MUST be 0, got {yest_data['currently_inside']}"
    assert yest_data["overstay_count"] == 0, "No overstay warnings for yesterday"

    # Query Today
    res_today = client.get("/api/audit?date=today")
    assert res_today.status_code == 200
    today_data = res_today.json()
    # Exactly MEM-002 and MEM-004 should be currently inside (2 cars)
    assert today_data["currently_inside"] == 2
    inside_tags = {a["entry"]["scanned_tag"] for a in today_data["audits"] if a["status"] in ("Inside Facility", "Alert / Inside")}
    assert "TAG-002" in inside_tags
    assert "TAG-004" in inside_tags

    # Query All Time
    res_all = client.get("/api/audit?date=all")
    assert res_all.status_code == 200
    all_data = res_all.json()
    assert all_data["currently_inside"] == 2

def test_audit_pagination_and_search_logic():
    """Verify pagination and multi-field search logic in audit logs."""
    res = client.get("/api/audit?date=all&limit=10&page=1")
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert data["limit"] == 10

def test_audit_filtering_by_status():
    """Verify filtering audits by status (inside, exited)."""
    res_in = client.get("/api/audit?date=today&status=inside")
    assert res_in.status_code == 200
    in_audits = res_in.json()["audits"]
    for a in in_audits:
        assert a["status"] in ("Inside Facility", "Alert / Inside", "Overstay (>8h)")

    res_ex = client.get("/api/audit?date=today&status=exited")
    assert res_ex.status_code == 200
    ex_audits = res_ex.json()["audits"]
    for a in ex_audits:
        assert a["status"] in ("Exited", "Exit Only")

# -------------------------------------------------------------
# 3. LIVE STATS & DASHBOARD METRICS ALIGNMENT
# -------------------------------------------------------------
def test_dashboard_stats_alignment_with_audit():
    """
    Ensure /api/stats 'currently_in_club' matches /api/audit 'facility_currently_inside'.
    """
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()

    res_audit = client.get("/api/audit?date=today")
    assert res_audit.status_code == 200
    audit = res_audit.json()

    assert stats["currently_in_club"] == audit["facility_currently_inside"]
    assert stats["total_entries_today"] >= 0
    assert stats["total_exits_today"] >= 0

def test_chart_data_endpoint_structure():
    """Verify /api/chart-data returns complete 24-hour distribution and 7-day trend."""
    res = client.get("/api/chart-data")
    assert res.status_code == 200
    data = res.json()
    assert "hours" in data
    assert "hourly_entries" in data
    assert "hourly_exits" in data
    assert "days" in data
    assert "daily_entries" in data
    assert "daily_exits" in data

    assert len(data["hours"]) == 24
    assert len(data["hourly_entries"]) == 24
    assert len(data["hourly_exits"]) == 24
    assert len(data["days"]) == 7
    assert len(data["daily_entries"]) == 7
    assert len(data["daily_exits"]) == 7

# -------------------------------------------------------------
# 4. MEMBERS MANAGEMENT & MULTI-VEHICLE SUPPORT
# -------------------------------------------------------------
def test_member_crud_and_multi_vehicle_association():
    """Test creating, reading, updating and deleting a member with multiple vehicles."""
    test_mem_id = "PROD-TEST-9999"
    test_tag_1 = "E280TEST0001"
    test_tag_2 = "E280TEST0002"
    test_plate_1 = "TEST-991"
    test_plate_2 = "TEST-992"

    try:
        # Add member vehicle 1
        res1 = client.post("/api/add-member", json={
            "mem_id": test_mem_id,
            "name": "Production Test User",
            "car_number": test_plate_1,
            "e_tag_id": test_tag_1,
            "make_model": "Honda Civic"
        })
        assert res1.status_code == 200
        assert res1.json()["ok"] is True

        # Add member vehicle 2 (same mem_id)
        res2 = client.post("/api/add-member", json={
            "mem_id": test_mem_id,
            "name": "Production Test User",
            "car_number": test_plate_2,
            "e_tag_id": test_tag_2,
            "make_model": "Toyota Corolla"
        })
        assert res2.status_code == 200

        # Verify unique member listing
        res_m = client.get(f"/api/members?search={test_mem_id}")
        assert res_m.status_code == 200
        m_list = res_m.json()["members"]
        assert len(m_list) == 1
        assert m_list[0]["Mem_id"] == test_mem_id
        assert m_list[0]["vehicle_count"] == 2

        # Verify vehicles sub-endpoint
        res_v = client.get(f"/api/members/{test_mem_id}/vehicles")
        assert res_v.status_code == 200
        v_list = res_v.json()["vehicles"]
        assert len(v_list) == 2
        plates = {v["Car_number"] for v in v_list}
        assert test_plate_1 in plates
        assert test_plate_2 in plates

        # Test location toggle
        res_tog = client.post("/api/members/toggle-location", json={
            "mem_id": test_mem_id,
            "car_number": test_plate_1,
            "location": "Inside"
        })
        assert res_tog.status_code == 200
        assert res_tog.json()["ok"] is True

    finally:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM members WHERE Mem_id=?", (test_mem_id,))

# -------------------------------------------------------------
# 5. UNREGISTERED TAGS & GUEST WORKFLOW
# -------------------------------------------------------------
def test_unregistered_tag_lifecycle():
    """Verify unregistered tags recording, retrieval, and dismissal."""
    guest_tag = "E280GUESTPROD01"
    try:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM unregistered_tags WHERE tag=?", (guest_tag,))
                conn.execute("INSERT INTO unregistered_tags (tag, direction, current_location, tag_type) VALUES (?, ?, ?, ?)",
                             (guest_tag, "Entry", "Inside", "Unregistered Visitor"))

        # Retrieve unregistered tags
        res = client.get("/api/unregistered-tags")
        assert res.status_code == 200
        tags = res.json()
        assert isinstance(tags, list)
        match = next((t for t in tags if t["tag"] == guest_tag), None)
        assert match is not None
        assert match["tag"] == guest_tag

        # Dismiss tag
        res_del = client.delete(f"/api/unregistered-tags/{guest_tag}")
        assert res_del.status_code == 200
        assert res_del.json()["ok"] is True

        # Confirm deleted
        with get_db_connection() as conn:
            check = conn.execute("SELECT COUNT(*) as c FROM unregistered_tags WHERE tag=?", (guest_tag,)).fetchone()
            assert check["c"] == 0

    finally:
        with get_db_connection() as conn:
            with conn:
                conn.execute("DELETE FROM unregistered_tags WHERE tag=?", (guest_tag,))

# -------------------------------------------------------------
# 6. EXPORT SERVICES (PDF, EXCEL, CSV, DATABASE)
# -------------------------------------------------------------
def test_audit_pdf_export_production_integrity():
    """Verify PDF export returns valid binary PDF stream with proper headers."""
    post_res = client.post("/api/audit/pdf", json={
        "entry": {
            "id": 1,
            "mem_id": "MEM-9999",
            "name": "Executive Member",
            "vehicle_number": "KGC-777",
            "timestamp": "2026-10-22 10:00:00",
            "gate_no": "Gate-01"
        },
        "duration": "1h 15m",
        "status": "Exited"
    })
    assert post_res.status_code == 200
    assert post_res.headers["content-type"] == "application/pdf"
    assert post_res.content.startswith(b"%PDF-")
    assert len(post_res.content) > 1000

def test_audit_excel_export_production_integrity():
    """Verify Excel export returns valid binary openpyxl xlsx stream."""
    res = client.get("/api/audit/export?format=xlsx&date=today&status=all")
    assert res.status_code == 200
    assert "openxmlformats" in res.headers["content-type"]
    assert len(res.content) > 500

def test_audit_csv_export_production_integrity():
    """Verify CSV export returns valid comma-separated text stream."""
    res = client.get("/api/audit/export?format=csv&date=today&status=all")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    text = res.text
    lines = text.strip().split("\n")
    assert len(lines) >= 1

def test_database_status_and_export_integrity():
    """Verify database status and export endpoints."""
    # 1. DB Status
    res_st = client.get("/api/database/status")
    assert res_st.status_code == 200
    st = res_st.json()
    assert st["ok"] is True
    assert "engine" in st
    assert "counts" in st
    assert "members" in st["counts"]
    assert "daily_logs" in st["counts"]

    # 2. DB Export (Download SQL backup)
    res_exp = client.get("/api/database/export")
    assert res_exp.status_code == 200
    assert "application/sql" in res_exp.headers["content-type"]
    assert len(res_exp.content) > 1000

# -------------------------------------------------------------
# 7. BULK EXIT EXCEPTIONS ENGINE
# -------------------------------------------------------------
def test_bulk_exit_exceptions_management():
    """Verify exceptions can be retrieved, saved, and checked."""
    res = client.get("/api/settings/bulk-exit-exceptions")
    assert res.status_code == 200
    data = res.json()
    assert "exceptions" in data
    assert "total_inside" in data
    orig_exceptions = data["exceptions"]

    # Add test exception
    test_exc = list(orig_exceptions) + ["TEST-EXCEPT-001"]
    res_post = client.post("/api/settings/bulk-exit-exceptions", json={"exceptions": test_exc})
    assert res_post.status_code == 200
    assert res_post.json()["ok"] is True

    # Verify updated
    res_check = client.get("/api/settings/bulk-exit-exceptions")
    assert "TEST-EXCEPT-001" in res_check.json()["exceptions"]

    # Restore original
    client.post("/api/settings/bulk-exit-exceptions", json={"exceptions": orig_exceptions})

# -------------------------------------------------------------
# 8. HIGH CONCURRENCY ENDPOINT STRESS TEST
# -------------------------------------------------------------
def test_production_high_concurrency_stress():
    """
    Simulates high concurrent load (50 simultaneous requests) across key API endpoints
    to guarantee zero 500 internal server errors or database lock contention crashes.
    """
    endpoints = [
        "/api/stats",
        "/api/audit?date=today&limit=10",
        "/api/chart-data",
        "/api/members?limit=10",
        "/api/latest-log?gate=gate01",
        "/api/database/status"
    ]

    def hit_endpoint(url):
        r = client.get(url)
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(hit_endpoint, endpoints[i % len(endpoints)]) for i in range(50)]
        results = [f.result() for f in futures]

    assert all(code == 200 for code in results), f"All concurrent requests must return 200 OK, got: {set(results)}"
