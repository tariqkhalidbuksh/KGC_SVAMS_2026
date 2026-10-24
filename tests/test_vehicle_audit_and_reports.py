import os
import time
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import pypdfium2 as pdfium

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

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_audit_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_audit_bugs.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()
    return test_db


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Helper to extract text from generated PDF bytes using pypdfium2."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    full_text = []
    for page in pdf:
        textpage = page.get_textpage()
        full_text.append(textpage.get_text_range())
    return " ".join(full_text)


class TestBug1VehicleAuditFilters:
    """
    Bug #1: Vehicle Audit filters not applied to displayed data.
    Verifies that all filters (date presets, date ranges, camera/gate, status, search)
    and their combinations strictly filter returned records, totals, and pagination.
    """

    @pytest.fixture
    def seed_test_data(self):
        """Seed diverse records across dates, gates, members, and statuses."""
        today_str = config.get_pkt_today()
        today_dt = datetime.strptime(today_str, "%Y-%m-%d")
        yesterday_str = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        four_days_ago = (today_dt - timedelta(days=4)).strftime("%Y-%m-%d")
        ten_days_ago = (today_dt - timedelta(days=10)).strftime("%Y-%m-%d")

        with get_db_connection() as conn:
            with conn:
                # 1. Register test members
                conn.execute("""
                    INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status)
                    VALUES 
                    ('MEM-001', 'Dr. Farhan Ahmed', 'KGC-111', 'Toyota Corolla', 'TAG-001', 'Active'),
                    ('MEM-002', 'Capt. Sara Malik', 'KGC-222', 'Honda Civic', 'TAG-002', 'Active'),
                    ('MEM-003', 'Zubair Qureshi', 'KGC-333', 'Kia Sportage', 'TAG-003', 'Active')
                """)

                # 2. Today:
                # Member 1: Entered via Gate-01, Exited via Gate-02 (Status: Exited)
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-001', 'Dr. Farhan Ahmed', 'KGC-111', 'RFID Verified Member', 'Entry', 'Gate-01', 'TAG-001', ?)
                """, (f"{today_str} 09:00:00",))
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-001', 'Dr. Farhan Ahmed', 'KGC-111', 'RFID Verified Member', 'Exit', 'Gate-02', 'TAG-001', ?)
                """, (f"{today_str} 10:30:00",))

                # Member 2: Entered via Gate-01, still inside (Status: Inside Facility)
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-002', 'Capt. Sara Malik', 'KGC-222', 'RFID Verified Member', 'Entry', 'Gate-01', 'TAG-002', ?)
                """, (f"{today_str} 11:00:00",))

                # Unregistered / Alert: Entered via Hikvision camera, still inside (Status: Alert / Inside)
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('GUEST-LOG', 'Unregistered Visitor', 'UNKNOWN-999', 'Security Alert - Unknown', 'Entry', 'Hikvision', 'NO_TAG', ?)
                """, (f"{today_str} 11:30:00",))

                # 3. Yesterday:
                # Member 3: Entered via Gate-02, Exited via Gate-02
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-003', 'Zubair Qureshi', 'KGC-333', 'RFID Verified Member', 'Entry', 'Gate-02', 'TAG-003', ?)
                """, (f"{yesterday_str} 14:00:00",))
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-003', 'Zubair Qureshi', 'KGC-333', 'RFID Verified Member', 'Exit', 'Gate-02', 'TAG-003', ?)
                """, (f"{yesterday_str} 16:00:00",))

                # 4. 4 days ago (in "week"):
                # Member 1 entered and exited
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-001', 'Dr. Farhan Ahmed', 'KGC-111', 'RFID Verified Member', 'Entry', 'Gate-01', 'TAG-001', ?)
                """, (f"{four_days_ago} 08:00:00",))
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-001', 'Dr. Farhan Ahmed', 'KGC-111', 'RFID Verified Member', 'Exit', 'Gate-01', 'TAG-001', ?)
                """, (f"{four_days_ago} 09:00:00",))

                # 5. 10 days ago (outside "week", inside "all"):
                # Member 2 entered and exited
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-002', 'Capt. Sara Malik', 'KGC-222', 'RFID Verified Member', 'Entry', 'Gate-01', 'TAG-002', ?)
                """, (f"{ten_days_ago} 12:00:00",))
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-002', 'Capt. Sara Malik', 'KGC-222', 'RFID Verified Member', 'Exit', 'Gate-01', 'TAG-002', ?)
                """, (f"{ten_days_ago} 13:00:00",))

        return {
            "today": today_str,
            "yesterday": yesterday_str,
            "four_days_ago": four_days_ago,
            "ten_days_ago": ten_days_ago
        }

    def test_date_filter_presets(self, seed_test_data):
        """Test 'today', 'yesterday', 'week', 'all' presets."""
        # Today: 3 paired audits (MEM-001, MEM-002, UNKNOWN-999)
        res_today = client.get("/api/audit?date=today")
        assert res_today.status_code == 200
        d_today = res_today.json()
        assert d_today["total"] == 3
        assert len(d_today["audits"]) == 3
        assert d_today["currently_inside"] == 2  # MEM-002 and UNKNOWN-999
        assert d_today["exited_count"] == 1      # MEM-001
        assert d_today["alert_count"] == 1       # UNKNOWN-999

        # Yesterday: 1 paired audit (MEM-003)
        res_yest = client.get("/api/audit?date=yesterday")
        assert res_yest.status_code == 200
        d_yest = res_yest.json()
        assert d_yest["total"] == 1
        assert len(d_yest["audits"]) == 1
        assert d_yest["audits"][0]["entry"]["mem_id"] == "MEM-003"
        assert d_yest["currently_inside"] == 0
        assert d_yest["exited_count"] == 1

        # Week: today (3) + yesterday (1) + 4 days ago (1) = 5
        res_week = client.get("/api/audit?date=week")
        assert res_week.status_code == 200
        d_week = res_week.json()
        assert d_week["total"] == 5

        # All: today (3) + yesterday (1) + 4 days ago (1) + 10 days ago (1) = 6
        res_all = client.get("/api/audit?date=all")
        assert res_all.status_code == 200
        d_all = res_all.json()
        assert d_all["total"] == 6

    def test_custom_date_range_filter(self, seed_test_data):
        """Test custom date range from start_date to end_date."""
        dates = seed_test_data
        # Range covering four_days_ago to yesterday
        res_range = client.get(f"/api/audit?start_date={dates['four_days_ago']}&end_date={dates['yesterday']}")
        assert res_range.status_code == 200
        d_range = res_range.json()
        assert d_range["total"] == 2
        mem_ids = {a["entry"]["mem_id"] for a in d_range["audits"]}
        assert mem_ids == {"MEM-001", "MEM-003"}

    def test_camera_filter(self, seed_test_data):
        """Test camera/gate filter individually."""
        # Gate-02 on today: only MEM-001 had Gate-02 exit
        res_gate2 = client.get("/api/audit?date=today&camera=Gate-02")
        assert res_gate2.status_code == 200
        d_gate2 = res_gate2.json()
        assert d_gate2["total"] == 1
        assert d_gate2["audits"][0]["entry"]["mem_id"] == "MEM-001"

        # Hikvision on today: only UNKNOWN-999
        res_hik = client.get("/api/audit?date=today&camera=Hikvision")
        assert res_hik.status_code == 200
        d_hik = res_hik.json()
        assert d_hik["total"] == 1
        assert d_hik["audits"][0]["entry"]["vehicle_number"] == "UNKNOWN-999"

    def test_status_filter(self, seed_test_data):
        """Test status filter (inside, exited, alert)."""
        # Inside
        res_inside = client.get("/api/audit?date=today&status=inside")
        assert res_inside.status_code == 200
        d_inside = res_inside.json()
        assert d_inside["total"] == 2
        assert d_inside["currently_inside"] == 2
        assert d_inside["exited_count"] == 0

        # Exited
        res_exited = client.get("/api/audit?date=today&status=exited")
        assert res_exited.status_code == 200
        d_exited = res_exited.json()
        assert d_exited["total"] == 1
        assert d_exited["exited_count"] == 1
        assert d_exited["currently_inside"] == 0

        # Alert
        res_alert = client.get("/api/audit?date=today&status=alert")
        assert res_alert.status_code == 200
        d_alert = res_alert.json()
        assert d_alert["total"] == 1
        assert d_alert["alert_count"] == 1
        assert d_alert["audits"][0]["entry"]["name"] == "Unregistered Visitor"

    def test_search_filter(self, seed_test_data):
        """Test search by member name, vehicle plate, or mem_id."""
        # Search by name
        res_name = client.get("/api/audit?date=all&search=Farhan")
        assert res_name.status_code == 200
        d_name = res_name.json()
        assert d_name["total"] == 2  # 2 visits by Dr. Farhan Ahmed
        assert all("Farhan" in a["entry"]["name"] for a in d_name["audits"])

        # Search by plate
        res_plate = client.get("/api/audit?date=all&search=KGC-222")
        assert res_plate.status_code == 200
        d_plate = res_plate.json()
        assert d_plate["total"] == 2  # 2 visits by Sara Malik in KGC-222

    def test_combined_filters_and_pagination(self, seed_test_data):
        """
        Test combined filters: Date + Camera + Status + Search,
        and ensure total, total_filtered, total_unfiltered, counts, and pagination update accurately.
        """
        # Combination: date=today, camera=Gate-01, status=inside, search=Sara
        res = client.get("/api/audit?date=today&camera=Gate-01&status=inside&search=Sara&page=1&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["total_filtered"] == 1
        assert data["total_unfiltered"] == 3  # Raw today has 3 audits
        assert data["currently_inside"] == 1
        assert data["exited_count"] == 0
        assert data["alert_count"] == 0
        assert data["total_pages"] == 1
        assert len(data["audits"]) == 1
        assert data["audits"][0]["entry"]["mem_id"] == "MEM-002"

        # Pagination test on date=all with limit=5
        res_page1 = client.get("/api/audit?date=all&page=1&limit=5")
        assert res_page1.status_code == 200
        d1 = res_page1.json()
        assert d1["total"] == 6
        assert d1["limit"] == 5
        assert d1["total_pages"] == 2
        assert len(d1["audits"]) == 5

        res_page2 = client.get("/api/audit?date=all&page=2&limit=5")
        assert res_page2.status_code == 200
        d2 = res_page2.json()
        assert len(d2["audits"]) == 1
        # Ensure page 1 and page 2 items are different
        p1_ids = [a["entry"]["id"] for a in d1["audits"]]
        p2_ids = [a["entry"]["id"] for a in d2["audits"]]
        assert set(p1_ids).isdisjoint(set(p2_ids))

    def test_audit_export_respects_filters(self, seed_test_data):
        """Verify /api/audit/export endpoint exports strictly filtered results."""
        # 1. Export CSV: today + status=inside
        res_csv = client.get(f"/api/audit/export?start_date={seed_test_data['today']}&end_date={seed_test_data['today']}&status=inside&format=csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]
        csv_text = res_csv.text
        # Must contain MEM-002 and UNKNOWN-999, but NOT MEM-001 (exited)
        assert "KGC-222" in csv_text
        assert "UNKNOWN-999" in csv_text
        assert "KGC-111" not in csv_text

        # 2. Export Excel (default format=xlsx)
        res_xlsx = client.get(f"/api/audit/export?start_date={seed_test_data['today']}&end_date={seed_test_data['today']}&status=inside")
        assert res_xlsx.status_code == 200
        assert "spreadsheetml.sheet" in res_xlsx.headers["content-type"]
        assert len(res_xlsx.content) > 1000


class TestBug2ReportsMemberInfoEnrichment:
    """
    Bug #2: Reports show 'Unknown Member' instead of actual member info.
    Verifies that report generation fetches and displays exact member details,
    replaces 'Unknown Member' / 'N/A' via database fallback, and marks RFID Verified badge.
    """

    @pytest.fixture
    def seed_member_record(self):
        """Insert a verified member with distinctive details."""
        mem_id = "MEM-VIP-99"
        name = "Commodore Tariq Mansoor"
        car_number = "KGC-9900"
        etag = "TAG-VIP-9900"
        make_model = "Mercedes-Benz E200"

        with get_db_connection() as conn:
            with conn:
                conn.execute("""
                    INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status)
                    VALUES (?, ?, ?, ?, ?, 'Active')
                """, (mem_id, name, car_number, make_model, etag))

                cursor = conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES (?, ?, ?, 'RFID Verified Member', 'Entry', 'Gate-01', ?, '2026-10-08 09:30:00')
                """, (mem_id, name, car_number, etag))
                log_id = cursor.lastrowid

        return {
            "mem_id": mem_id,
            "name": name,
            "car_number": car_number,
            "etag": etag,
            "make_model": make_model,
            "log_id": log_id
        }

    def test_single_log_pdf_displays_member_info(self, seed_member_record):
        """Test GET /api/audit/{log_id}/pdf generates valid PDF with member details."""
        log_id = seed_member_record["log_id"]
        res = client.get(f"/api/audit/{log_id}/pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF-")

        pdf_text = _extract_pdf_text(res.content)
        assert "Unknown Member" not in pdf_text
        assert seed_member_record["name"] in pdf_text
        assert seed_member_record["mem_id"] in pdf_text
        assert seed_member_record["car_number"] in pdf_text
        assert "RFID VERIFIED MEMBER" in pdf_text

    def test_custom_report_pdf_with_frontend_nested_incident_payload(self, seed_member_record):
        """
        Test POST /api/audit/custom-report/pdf with the exact nested structure
        sent by dashboard.js (incident: { entry: {...}, exit: {...} }).
        """
        payload = {
            "incident": {
                "entry": {
                    "id": seed_member_record["log_id"],
                    "mem_id": seed_member_record["mem_id"],
                    "name": seed_member_record["name"],
                    "vehicle_number": seed_member_record["car_number"],
                    "access_type": "RFID Verified Member",
                    "gate_no": "Gate-01",
                    "direction": "Entry",
                    "scanned_tag": seed_member_record["etag"],
                    "timestamp": "2026-10-08 09:30:00"
                },
                "exit": None,
                "status": "Inside Facility",
                "duration": "1h 15m"
            },
            "duration": "1h 15m",
            "status": "Inside Facility"
        }

        res = client.post("/api/audit/custom-report/pdf", json=payload)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"

        pdf_text = _extract_pdf_text(res.content)
        assert "Unknown Member" not in pdf_text
        assert "Unregistered Visitor" not in pdf_text
        assert seed_member_record["name"] in pdf_text
        assert seed_member_record["mem_id"] in pdf_text
        assert seed_member_record["car_number"] in pdf_text
        assert "RFID VERIFIED MEMBER" in pdf_text

    def test_custom_report_pdf_fallback_enrichment_when_name_unknown(self, seed_member_record):
        """
        Crucial test: When the incident payload has 'Unknown Member' or sparse data,
        the backend safety net MUST query the members database and populate
        the actual member name, member ID, make/model, and verified badge.
        """
        sparse_payload = {
            "incident": {
                "entry": {
                    "id": seed_member_record["log_id"],
                    "mem_id": "GUEST-LOG",  # Sparse/unregistered placeholder
                    "name": "Unknown Member",  # Previously buggy display
                    "vehicle_number": seed_member_record["car_number"],  # Known vehicle plate
                    "scanned_tag": seed_member_record["etag"],          # Known RFID tag
                    "access_type": "RFID Verified",
                    "gate_no": "Gate-01",
                    "direction": "Entry",
                    "timestamp": "2026-10-08 09:30:00"
                }
            }
        }

        res = client.post("/api/audit/custom-report/pdf", json=sparse_payload)
        assert res.status_code == 200

        pdf_text = _extract_pdf_text(res.content)
        # Verify the fallback resolved the real member
        assert "Commodore Tariq Mansoor" in pdf_text
        assert seed_member_record["mem_id"] in pdf_text
        assert "Mercedes-Benz E200" in pdf_text
        assert "Unknown Member" not in pdf_text
        assert "Unregistered Visitor" not in pdf_text
        assert "RFID VERIFIED MEMBER" in pdf_text


class TestCameraAuditFilters:
    """
    Verifies that the Camera Vehicle Audit filters (date presets, ranges,
    directions, searches, and pagination) operate strictly and accurately.
    """

    @pytest.fixture
    def seed_cam_data(self):
        today_str = config.get_pkt_today()
        today_dt = datetime.strptime(today_str, "%Y-%m-%d")
        yesterday_str = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        four_days_ago = (today_dt - timedelta(days=4)).strftime("%Y-%m-%d")

        with get_db_connection() as conn:
            with conn:
                # Today: 1 Entry, 1 Exit
                conn.execute("""
                    INSERT INTO camera_audit_logs (timestamp, date_str, event_type, direction, image_path, detected_plate)
                    VALUES (?, ?, 'Line Crossing', 'Entry', 'static/camera_audit/today_entry.jpg', 'KGC-777')
                """, (f"{today_str} 09:15:00", today_str))

                conn.execute("""
                    INSERT INTO camera_audit_logs (timestamp, date_str, event_type, direction, image_path, detected_plate)
                    VALUES (?, ?, 'Line Crossing', 'Exit', 'static/camera_audit/today_exit.jpg', 'KGC-888')
                """, (f"{today_str} 10:15:00", today_str))

                # Yesterday: 1 Entry
                conn.execute("""
                    INSERT INTO camera_audit_logs (timestamp, date_str, event_type, direction, image_path, detected_plate)
                    VALUES (?, ?, 'Line Crossing', 'Entry', 'static/camera_audit/yest_entry.jpg', 'KGC-999')
                """, (f"{yesterday_str} 15:30:00", yesterday_str))

                # 4 Days Ago: 1 Line Crossing
                conn.execute("""
                    INSERT INTO camera_audit_logs (timestamp, date_str, event_type, direction, image_path, detected_plate)
                    VALUES (?, ?, 'Line Crossing', 'Line Crossing', 'static/camera_audit/past_cross.jpg', 'NO_PLATE')
                """, (f"{four_days_ago} 11:00:00", four_days_ago))

        return {
            "today": today_str,
            "yesterday": yesterday_str,
            "four_days_ago": four_days_ago
        }

    def test_camera_audit_date_presets_and_ranges(self, seed_cam_data):
        dates = seed_cam_data

        # Today: 2 logs
        res_today = client.get("/api/camera-audit-logs?date=today")
        assert res_today.status_code == 200
        d_today = res_today.json()
        assert d_today["total"] == 2
        assert len(d_today["logs"]) == 2

        # Yesterday: 1 log
        res_yest = client.get("/api/camera-audit-logs?date=yesterday")
        assert res_yest.status_code == 200
        assert res_yest.json()["total"] == 1

        # Week: 4 logs
        res_week = client.get("/api/camera-audit-logs?date=week")
        assert res_week.status_code == 200
        assert res_week.json()["total"] == 4

        # Custom date range: four_days_ago to yesterday (2 logs)
        res_range = client.get(f"/api/camera-audit-logs?start_date={dates['four_days_ago']}&end_date={dates['yesterday']}")
        assert res_range.status_code == 200
        assert res_range.json()["total"] == 2

    def test_camera_audit_direction_and_search(self, seed_cam_data):
        # Direction filter: Entry on today (1 log)
        res_entry = client.get("/api/camera-audit-logs?date=today&direction=Entry")
        assert res_entry.status_code == 200
        d_entry = res_entry.json()
        assert d_entry["total"] == 1
        assert d_entry["logs"][0]["direction"] == "Entry"

        # Direction filter: Exit on today (1 log)
        res_exit = client.get("/api/camera-audit-logs?date=today&direction=Exit")
        assert res_exit.status_code == 200
        assert res_exit.json()["total"] == 1
        assert res_exit.json()["logs"][0]["direction"] == "Exit"

        # Search filter by plate or image
        res_search = client.get("/api/camera-audit-logs?date=all&search=today_entry")
        assert res_search.status_code == 200
        d_search = res_search.json()
        assert d_search["total"] == 1
        assert "today_entry.jpg" in d_search["logs"][0]["image_path"]


class TestApproachBCrossDayAndOccupancy:
    """
    Validates Approach B: Multi-Day Lookback for cross-day vehicle visits
    and authoritative state-based facility occupancy synchronization.
    """
    def test_overnight_cross_day_pairing_and_duration(self, setup_audit_test_db):
        pkt_today = config.get_pkt_today()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with get_db_connection() as conn:
            with conn:
                conn.execute("""
                    INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status)
                    VALUES ('MEM-NIGHT', 'Overnight Visitor', 'KGC-NIGHT', 'Sedan', 'TAG-NIGHT', 'Active')
                """)
                # Car entered yesterday at 22:00:00
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-NIGHT', 'Overnight Visitor', 'KGC-NIGHT', 'RFID Verified', 'Entry', 'Gate-01', 'TAG-NIGHT', ?)
                """, (f"{yesterday} 22:00:00",))
                # Car exited today at 07:30:00
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-NIGHT', 'Overnight Visitor', 'KGC-NIGHT', 'RFID Verified', 'Exit', 'Gate-01', 'TAG-NIGHT', ?)
                """, (f"{pkt_today} 07:30:00",))
                # Car entered today and is still inside
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('MEM-INSIDE', 'Inside Visitor', 'KGC-INSIDE', 'RFID Verified', 'Entry', 'Gate-01', 'TAG-INSIDE', ?)
                """, (f"{pkt_today} 09:00:00",))

        # 1. Audit log for today should pair the overnight car
        res_audit = client.get("/api/audit?date=today")
        assert res_audit.status_code == 200
        audit_data = res_audit.json()

        # Find overnight visit
        night_visit = next((a for a in audit_data["audits"] if a["exit"] and a["exit"]["scanned_tag"] == "TAG-NIGHT"), None)
        assert night_visit is not None
        assert night_visit["status"] == "Exited"
        assert night_visit["entry"] is not None
        assert "Overnight" in night_visit["duration"]
        assert "9h 30m" in night_visit["duration"]

        # 2. Stats and Audit occupancy must be 100% synchronized
        res_stats = client.get("/api/stats")
        assert res_stats.status_code == 200
        stats_data = res_stats.json()

        assert stats_data["currently_in_club"] == audit_data["facility_currently_inside"]
        assert stats_data["currently_in_club"] == 1  # Only MEM-INSIDE is inside

    def test_orphan_exit_retains_truthful_exit_only(self, setup_audit_test_db):
        pkt_today = config.get_pkt_today()
        with get_db_connection() as conn:
            with conn:
                conn.execute("""
                    INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                    VALUES ('GUEST-ORPHAN', 'Orphan Exit', 'KGC-ORPHAN', 'RFID Verified', 'Exit', 'Gate-01', 'TAG-ORPHAN', ?)
                """, (f"{pkt_today} 14:00:00",))

        res = client.get("/api/audit?date=today")
        assert res.status_code == 200
        audits = res.json()["audits"]

        orphan = next((a for a in audits if a["exit"] and a["exit"]["scanned_tag"] == "TAG-ORPHAN"), None)
        assert orphan is not None
        assert orphan["status"] == "Exit Only"
        assert orphan["entry"] is None


