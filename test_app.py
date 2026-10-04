"""
Unit and Integration Test Suite for RFID_VAMS app.py
 Karachi Gymkhana Club — Smart Vehicle Access & Parking Management
"""
import pytest
import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient

import config
import app as app_module
from app import app, init_db, get_db_connection, execute_access_decision, attach_images_to_log, PENDING_RFID_BUFFER, BUFFER_LOCK, is_valid_image
import numpy as np
import httpx
_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

client = TestClient(app)

def trigger_test_passage(tag="NO_TAG", direction="Entry", path_full=None, path_plate=None, is_ai_trigger=False, bypass_cooldown=False):
    is_ai = is_ai_trigger or (tag == "NO_TAG")
    return execute_access_decision(tag, direction, path_full, path_plate, is_ai_trigger=is_ai, bypass_cooldown=bypass_cooldown)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """
    Fixture to setup an isolated SQLite database for each test.
    """
    db_file = os.path.join(tmp_path, "test_gate_access.db")
    monkeypatch.setattr(app_module, "DB_FILE", db_file)
    
    # Initialize DB schema
    init_db()
    yield db_file


class TestDatabaseAndCoreLogic:
    def test_init_db_tables_created(self, setup_test_db):
        conn = get_db_connection()
        cursor = conn.cursor()
        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        
        assert "members" in tables
        assert "daily_logs" in tables
        assert "raw_reader_logs" in tables
        assert "settings" in tables

    def test_execute_access_decision_registered_member(self, setup_test_db):
        # Register a member directly in DB
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO members (Mem_id, Name, Car_number, Make_Model, E_tag_id) VALUES (?,?,?,?,?)",
            ("KG-101", "Test Member", "ABC-123", "Toyota Corolla", "TAG-E280111")
        )
        conn.commit()
        conn.close()

        log_id = trigger_test_passage("TAG-E280111", "Entry")
        assert log_id is not None

        conn = get_db_connection()
        log = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        conn.close()

        assert log["mem_id"] == "KG-101"
        assert log["name"] == "Test Member"
        assert log["vehicle_number"] == "ABC-123"
        assert log["access_type"] == "RFID Verified"
        assert log["direction"] == "Entry"

    def test_execute_access_decision_unregistered_tag(self, setup_test_db):
        log_id = trigger_test_passage("UNKNOWN-TAG-999", "Entry")
        
        conn = get_db_connection()
        log = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        conn.close()

        assert log["mem_id"] == "GUEST-LOG"
        assert log["name"] == "Unregistered Visitor"
        assert log["vehicle_number"] == "UNKNOWN-TAG-999"
        assert log["access_type"] == "RFID Unknown"

    def test_execute_access_decision_ai_trigger_no_tag(self, setup_test_db):
        log_id = trigger_test_passage("NO_TAG", "Entry", is_ai_trigger=True)
        
        conn = get_db_connection()
        log = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        conn.close()

        assert log["mem_id"] == "AI-CAM"
        assert log["name"] == "Unregistered Vehicle"
        assert log["access_type"] == "No RFID Detected"

    def test_attach_images_to_log(self, setup_test_db):
        log_id = trigger_test_passage("NO_TAG", "Entry", is_ai_trigger=True)
        attach_images_to_log(log_id, "static/snapshots/full_test.jpg", "static/snapshots/plate_test.jpg")

        conn = get_db_connection()
        log = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id,)).fetchone()
        conn.close()

        assert log["image_path"] == "static/snapshots/full_test.jpg"
        assert log["plate_image_path"] == "static/snapshots/plate_test.jpg"

    def test_is_valid_image(self):
        # Blank / black image should be rejected
        black_img = np.zeros((300, 400, 3), dtype=np.uint8)
        assert is_valid_image(black_img) is False

        # None / empty array should be rejected
        assert is_valid_image(None) is False

        # Random high variance noise / real image should be accepted
        real_img = np.random.randint(50, 200, (300, 400, 3), dtype=np.uint8)
        assert is_valid_image(real_img) is True


class TestMemberAPI:
    def test_add_member_success(self, setup_test_db):
        payload = {
            "mem_id": "KG-202",
            "name": "Sarah Connor",
            "car_number": "LE-999",
            "make_model": "Honda Civic",
            "e_tag_id": "EPC-CONNOR-1",
            "profile_pic": ""
        }
        res = client.post("/api/add-member", json=payload)
        assert res.status_code == 200
        assert res.json()["ok"] is True

        res = client.get("/api/members?all=true")
        members = res.json()
        assert len(members) == 1
        assert members[0]["Mem_id"] == "KG-202"

    def test_multiple_cars_per_member(self, setup_test_db):
        # Register 3 cars for the same member KG-1000
        cars = [
            {"mem_id": "KG-1000", "name": "Ali Khan", "car_number": "CAR-1", "e_tag_id": "TAG-KG-1"},
            {"mem_id": "KG-1000", "name": "Ali Khan", "car_number": "CAR-2", "e_tag_id": "TAG-KG-2"},
            {"mem_id": "KG-1000", "name": "Ali Khan", "car_number": "CAR-3", "e_tag_id": "TAG-KG-3"},
        ]
        for car in cars:
            res = client.post("/api/add-member", json=car)
            assert res.status_code == 200

        res = client.get("/api/members?all=true")
        members = res.json()
        assert len(members) == 3

        # Test that scanning any of the 3 tags identifies Ali Khan with the specific car
        for i in range(1, 4):
            log_id = trigger_test_passage(f"TAG-KG-{i}", "Entry")
            conn = get_db_connection()
            log = conn.execute("SELECT * FROM daily_logs WHERE id=?", (log_id,)).fetchone()
            conn.close()

            assert log["mem_id"] == "KG-1000"
            assert log["name"] == "Ali Khan"
            assert log["vehicle_number"] == f"CAR-{i}"
            assert log["access_type"] == "RFID Verified"

    def test_add_member_duplicate_epc_clash(self, setup_test_db):
        payload1 = {
            "mem_id": "KG-001",
            "name": "User One",
            "car_number": "AAA-111",
            "e_tag_id": "EPC-SHARED-001"
        }
        client.post("/api/add-member", json=payload1)

        payload2 = {
            "mem_id": "KG-002",
            "name": "User Two",
            "car_number": "BBB-222",
            "e_tag_id": "EPC-SHARED-001"  # Same tag
        }
        res = client.post("/api/add-member", json=payload2)
        assert res.status_code == 409
        assert "already assigned" in res.json()["detail"]

    def test_update_member(self, setup_test_db):
        client.post("/api/add-member", json={
            "mem_id": "KG-303",
            "name": "Original Name",
            "car_number": "OLD-123",
            "e_tag_id": "EPC-303"
        })

        update_payload = {
            "old_mem_id": "KG-303",
            "mem_id": "KG-303",
            "name": "Updated Name",
            "car_number": "NEW-123",
            "e_tag_id": "EPC-303"
        }
        res = client.put("/api/update-member", json=update_payload)
        assert res.status_code == 200

        res = client.get("/api/members?all=true")
        members = res.json()
        assert members[0]["Name"] == "Updated Name"
        assert members[0]["Car_number"] == "NEW-123"

    def test_delete_member(self, setup_test_db):
        client.post("/api/add-member", json={
            "mem_id": "KG-404",
            "name": "To Delete",
            "car_number": "DEL-404",
            "e_tag_id": "EPC-DEL-404"
        })
        res = client.delete("/api/members/KG-404")
        assert res.status_code == 200

        res = client.get("/api/members?all=true")
        assert len(res.json()) == 0

    def test_import_members_csv(self, setup_test_db, tmp_path):
        csv_content = (
            "Mem_id,Name,Car_number,Make_Model,E_tag_id,Profile_pic\n"
            "KG-8001,User Alpha,CAR-A8001,Toyota,EPC-8001,\n"
            "KG-8002,User Beta,CAR-B8002,Honda,EPC-8002,\n"
            "KG-8002,User Beta,CAR-B8003,Honda,EPC-8003,\n"
        )
        csv_file = tmp_path / "test_import.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        with open(csv_file, "rb") as f:
            res = client.post("/api/import-members", files={"file": ("test_import.csv", f, "text/csv")})

        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["imported"] == 3
        assert len(data["errors"]) == 0

        res = client.get("/api/members?all=true")
        assert len(res.json()) == 3

    def test_align_member_photos_api(self, setup_test_db):
        client.post("/api/add-member", json={
            "mem_id": "TEST-ALIGN-99",
            "name": "Align User",
            "car_number": "ALIGN-99",
            "e_tag_id": "EPC-ALIGN-99"
        })

        img_dir = config.MEMBER_PROFILE_IMG_DIR
        os.makedirs(img_dir, exist_ok=True)
        dummy_img_path = os.path.join(img_dir, "TEST-ALIGN-99.jpg")
        with open(dummy_img_path, "wb") as f:
            f.write(b"dummy_image_bytes")

        try:
            res = client.post("/api/align-member-photos")
            assert res.status_code == 200
            data = res.json()
            assert data["ok"] is True
            assert data["aligned_photos"] >= 1

            res_members = client.get("/api/members?all=true")
            members = res_members.json()
            target_mem = next((m for m in members if m["Mem_id"] == "TEST-ALIGN-99"), None)
            assert target_mem is not None
            assert "TEST-ALIGN-99.jpg" in target_mem["Profile_pic"]
        finally:
            if os.path.exists(dummy_img_path):
                os.remove(dummy_img_path)


class TestSettingsAndStatsAPI:
    def test_settings_get_and_post(self, setup_test_db):
        res = client.get("/api/settings")
        assert res.status_code == 200
        settings = res.json()
        assert settings["club_name"] == "Karachi Gymkhana Club"

        update_payload = {"club_name": "Karachi Gymkhana Club — Main Gate", "parking_capacity": "600"}
        res = client.post("/api/settings", json=update_payload)
        assert res.status_code == 200

        res = client.get("/api/settings")
        assert res.json()["club_name"] == "Karachi Gymkhana Club — Main Gate"
        assert res.json()["parking_capacity"] == "600"

    def test_api_stats(self, setup_test_db):
        # Register a member and create entry/exit logs
        client.post("/api/add-member", json={
            "mem_id": "KG-505", "name": "Stat Test", "car_number": "ST-505", "e_tag_id": "TAG-505"
        })
        trigger_test_passage("TAG-505", "Entry")
        trigger_test_passage("TAG-505", "Exit", bypass_cooldown=True)

        res = client.get("/api/stats")
        assert res.status_code == 200
        stats = res.json()
        assert stats["active_members"] == 1
        assert stats["total_entries_today"] == 1
        assert stats["total_exits_today"] == 1
        assert stats["currently_in_club"] == 0

    def test_api_audit(self, setup_test_db):
        trigger_test_passage("TAG-AUDIT-1", "Entry")
        trigger_test_passage("TAG-AUDIT-1", "Exit", bypass_cooldown=True)

        res = client.get("/api/audit")
        assert res.status_code == 200
        audit = res.json()
        assert audit["total"] == 1
        assert audit["audits"][0]["status"] == "Exited"


class TestSimulationAndViews:
    def test_simulate_rfid_full(self, setup_test_db):
        payload = {
            "tag": "SIM-TAG-001",
            "direction": "Entry",
            "path_full": None,
            "path_plate": None
        }
        res = client.post("/api/simulate-rfid-full", json=payload)
        assert res.status_code == 200
        assert "log_id" in res.json()

    def test_simulate_clear_logs(self, setup_test_db):
        trigger_test_passage("SIM-TAG-001", "Entry")
        res = client.delete("/api/simulate/clear-logs")
        assert res.status_code == 200

        res = client.get("/api/logs")
        assert len(res.json()) == 0

    def test_html_routes(self, setup_test_db):
        for route in ["/", "/kiosk", "/tools", "/simulate"]:
            res = client.get(route)
            assert res.status_code == 200
            assert "text/html" in res.headers["content-type"]
