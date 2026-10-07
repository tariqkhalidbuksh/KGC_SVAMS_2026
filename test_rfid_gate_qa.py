import os
import time
import pytest
from fastapi.testclient import TestClient

from app import app
import config
from database import get_db_connection, init_db
from services.access_service import execute_access_decision
import httpx

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

import app as app_module
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "qa_test_gate_access.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    init_db()
    return test_db

class TestRFIDGateQAEngineer:
    """
    Comprehensive QA Test Suite for UHF RFID Anti-Bleeding Gate Logic,
    Strict State Machine, First-Reader-Wins Cold Start, Cooldown Lockout,
    Unregistered Tag Pipeline, and Member Fleet Presence Tracking.
    """

    def test_strict_state_machine_happy_path(self):
        """
        Tests normal passage cycle: Outside -> Entry -> Inside -> Exit -> Outside.
        """
        test_epc = "E280_QA_SM_HAPPY_001"
        test_mem = "QA-001"
        test_car = "QA-CAR-1"

        # Register test member
        res = client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester One",
            "car_number": test_car,
            "make_model": "Honda Civic",
            "e_tag_id": test_epc
        })
        assert res.status_code == 200

        # Initial state must be 'Outside'
        with get_db_connection() as conn:
            row = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()
            assert row["Current_Location"] == "Outside"

        # Transit 1: Outside -> Entry
        log_id1 = execute_access_decision(test_epc, direction="Entry")
        with get_db_connection() as conn:
            log1 = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id1,)).fetchone()
            assert log1["direction"] == "Entry"
            assert log1["Current_Location"] == "Inside"

        # Expire cooldown artificially
        with get_db_connection() as conn:
            with conn:
                conn.execute("UPDATE daily_logs SET timestamp = datetime('now', '-50 seconds') WHERE id=?", (log_id1,))

        # Transit 2: Inside -> Exit
        log_id2 = execute_access_decision(test_epc, direction="Exit")
        assert log_id2 != log_id1
        with get_db_connection() as conn:
            log2 = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id2,)).fetchone()
            assert log2["direction"] == "Exit"
            assert log2["Current_Location"] == "Outside"

    def test_tag_bleeding_protection_when_car_is_inside(self):
        """
        SCENARIO: Car is ALREADY INSIDE the club.
        When leaving, the physically adjacent Entry reader catches reflection / bleeds first.
        Strict State Machine MUST resolve direction as 'Exit', ignoring the Entry reader's direction!
        """
        test_epc = "E280_QA_BLEED_INSIDE_002"
        test_mem = "QA-002"
        test_car = "QA-CAR-2"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Inside",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        # Set member location to 'Inside'
        with get_db_connection() as conn:
            with conn:
                conn.execute("UPDATE members SET Current_Location = 'Inside' WHERE UPPER(E_tag_id)=?", (test_epc,))

        # Entry reader falsely reports scan because antennas are close together!
        log_id = execute_access_decision(test_epc, direction="Entry")

        with get_db_connection() as conn:
            log = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id,)).fetchone()
            # Must be forced to EXIT because car is physically inside!
            assert log["direction"] == "Exit"
            assert log["Current_Location"] == "Outside"

    def test_tag_bleeding_protection_when_car_is_outside(self):
        """
        SCENARIO: Car is OUTSIDE the club.
        When approaching the gate, the physically adjacent Exit reader catches reflection first.
        Strict State Machine MUST resolve direction as 'Entry', ignoring the Exit reader!
        """
        test_epc = "E280_QA_BLEED_OUTSIDE_003"
        test_mem = "QA-003"
        test_car = "QA-CAR-3"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Outside",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        # Member location is 'Outside'
        with get_db_connection() as conn:
            row = conn.execute("SELECT Current_Location FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()
            assert row["Current_Location"] == "Outside"

        # Exit reader falsely catches tag reflection first!
        log_id = execute_access_decision(test_epc, direction="Exit")

        with get_db_connection() as conn:
            log = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id,)).fetchone()
            # Must be forced to ENTRY because car is physically outside!
            assert log["direction"] == "Entry"
            assert log["Current_Location"] == "Inside"

    def test_cold_start_first_reader_wins_exit(self):
        """
        SCENARIO: System was reset while a car was already inside the club.
        Prior state is unknown/empty. Car approaches the exit gate, and Exit reader detects it first.
        First-Reader-Wins resolves it as Exit and marks state as 'Outside'.
        """
        test_epc = "E280_QA_COLD_EXIT_004"
        test_mem = "QA-004"
        test_car = "QA-CAR-4"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Cold Exit",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        # Clear Current_Location to simulate cold start without prior state
        with get_db_connection() as conn:
            with conn:
                conn.execute("UPDATE members SET Current_Location = '' WHERE UPPER(E_tag_id)=?", (test_epc,))

        # Exit reader detects tag first
        log_id = execute_access_decision(test_epc, direction="Exit")

        with get_db_connection() as conn:
            log = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id,)).fetchone()
            assert log["direction"] == "Exit"
            assert log["Current_Location"] == "Outside"

    def test_cold_start_first_reader_wins_entry(self):
        """
        SCENARIO: System was reset, car arrives at gate from outside.
        Entry reader detects it first.
        First-Reader-Wins resolves it as Entry and marks state as 'Inside'.
        """
        test_epc = "E280_QA_COLD_ENTRY_005"
        test_mem = "QA-005"
        test_car = "QA-CAR-5"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Cold Entry",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        with get_db_connection() as conn:
            with conn:
                conn.execute("UPDATE members SET Current_Location = '' WHERE UPPER(E_tag_id)=?", (test_epc,))

        # Entry reader detects tag first
        log_id = execute_access_decision(test_epc, direction="Entry")

        with get_db_connection() as conn:
            log = conn.execute("SELECT direction, Current_Location FROM daily_logs d JOIN members m ON d.scanned_tag = m.E_tag_id WHERE d.id=?", (log_id,)).fetchone()
            assert log["direction"] == "Entry"
            assert log["Current_Location"] == "Inside"

    def test_immediate_cooldown_lockout(self):
        """
        SCENARIO: Car is scanned by Reader 1 at t=0, and 100ms later by Reader 2.
        Cooldown lockout MUST drop the second scan and return the first log ID without creating duplicate logs.
        """
        test_epc = "E280_QA_COOLDOWN_LOCK_006"
        test_mem = "QA-006"
        test_car = "QA-CAR-6"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Cooldown",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        # Reader 1 scan
        id1 = execute_access_decision(test_epc, direction="Entry")

        # Reader 2 scan 0.1s later
        id2 = execute_access_decision(test_epc, direction="Exit")

        assert id1 == id2

        with get_db_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM daily_logs WHERE scanned_tag=?", (test_epc,)).fetchone()[0]
            assert count == 1

    def test_unregistered_tag_pipeline_and_one_click_assign(self):
        """
        SCENARIO: Unknown RFID tag detected at gate.
        1. Automatically logged to unregistered_tags table with scan count.
        2. GET /api/unregistered-tags returns the tag.
        3. Assigning the tag to a new member removes it from unregistered_tags.
        """
        unknown_epc = "E280_UNREG_QA_TAG_999"

        # Scan unknown tag
        log_id = execute_access_decision(unknown_epc, direction="Entry")
        assert log_id is not None

        # Check unregistered_tags table
        with get_db_connection() as conn:
            unreg = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (unknown_epc,)).fetchone()
            assert unreg is not None
            assert unreg["direction"] == "Entry"
            assert unreg["read_count"] == 1

        # Check API endpoint
        res = client.get("/api/unregistered-tags")
        assert res.status_code == 200
        tags_list = res.json()
        assert any(t["tag"] == unknown_epc for t in tags_list)

        # 1-Click Assignment: Register member with this tag
        assign_res = client.post("/api/add-member", json={
            "mem_id": "QA-NEW-MEM-999",
            "name": "Assigned Member",
            "car_number": "ASSIGNED-1",
            "e_tag_id": unknown_epc
        })
        assert assign_res.status_code == 200

        # Must be automatically removed from unregistered_tags
        with get_db_connection() as conn:
            remaining = conn.execute("SELECT * FROM unregistered_tags WHERE tag=?", (unknown_epc,)).fetchone()
            assert remaining is None

    def test_manual_toggle_location_api(self):
        """
        SCENARIO: Administrator manually overrides vehicle location in UI fleet view.
        """
        test_epc = "E280_QA_TOGGLE_007"
        test_mem = "QA-007"
        test_car = "QA-CAR-7"

        client.post("/api/add-member", json={
            "mem_id": test_mem,
            "name": "QA Tester Toggle",
            "car_number": test_car,
            "e_tag_id": test_epc
        })

        with get_db_connection() as conn:
            v_id = conn.execute("SELECT id FROM members WHERE UPPER(E_tag_id)=?", (test_epc,)).fetchone()["id"]

        # Toggle to Inside
        res1 = client.post("/api/members/toggle-location", json={"id": v_id, "location": "Inside"})
        assert res1.status_code == 200
        assert res1.json()["location"] == "Inside"

        # Verify in member vehicles API
        res_fleet = client.get(f"/api/members/{test_mem}/vehicles")
        assert res_fleet.status_code == 200
        fleet_data = res_fleet.json()
        assert fleet_data["current_location"] == "Inside"
        assert fleet_data["vehicles"][0]["Current_Location"] == "Inside"

        # Toggle to Outside
        res2 = client.post("/api/members/toggle-location", json={"id": v_id, "location": "Outside"})
        assert res2.status_code == 200
        assert res2.json()["location"] == "Outside"

    def test_kiosk_mode_latency_under_fifty_millis(self):
        """
        SCENARIO: Kiosk polling /api/latest-log must be served in < 50ms (in practice < 5ms).
        """
        test_epc = "E280_QA_LATENCY_008"
        execute_access_decision(test_epc, direction="Entry")

        # Measure 10 consecutive requests
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            res = client.get("/api/latest-log")
            t_elapsed = (time.perf_counter() - t0) * 1000.0  # in milliseconds
            assert res.status_code == 200
            latencies.append(t_elapsed)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 50.0, f"Average latency {avg_latency:.2f}ms exceeds 50ms threshold!"

    def test_day_movements_api(self):
        """
        SCENARIO: /api/audit/day-movements returns all movements for a vehicle on a given day.
        """
        test_car = "QA-MOVE-777"
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, timestamp)
                VALUES ('M-777', 'Tester', ?, 'RFID Verified', 'Entry', 'Gate-01', '2026-10-07 09:00:00')
            """, (test_car,))
            conn.execute("""
                INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, timestamp)
                VALUES ('M-777', 'Tester', ?, 'RFID Verified', 'Exit', 'Gate-01', '2026-10-07 14:00:00')
            """, (test_car,))
            conn.commit()

        res = client.get(f"/api/audit/day-movements?vehicle_number={test_car}&date=2026-10-07")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert len(data["movements"]) == 2
        assert data["movements"][0]["direction"] == "Entry"
        assert data["movements"][1]["direction"] == "Exit"

    def test_available_images_api(self):
        """
        SCENARIO: /api/audit/available-images returns camera captures and gate images for curation.
        """
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO camera_audit_logs (timestamp, date_str, direction, event_type, image_path)
                VALUES ('2026-10-07 10:00:00', '2026-10-07', 'Entry', 'Line Crossing', 'test/img1.jpg')
            """)
            conn.commit()

        res = client.get("/api/audit/available-images?date=2026-10-07")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any("test/img1.jpg" in img["image_path"] for img in data["images"])

    def test_custom_report_pdf_generation(self):
        """
        SCENARIO: POST /api/audit/custom-report/pdf generates an official PDF certificate
        with user-selected proof, all-day movements table, and investigator notes.
        """
        payload = {
            "incident": {
                "id": 999,
                "mem_id": "M-999",
                "name": "CAPT. INVESTIGATOR",
                "vehicle_number": "AUD-999",
                "gate_no": "Gate-01",
                "access_type": "RFID Verified",
                "direction": "Entry",
                "timestamp": "2026-10-07 11:15:00"
            },
            "entry_image_path": "static/img/no-car.svg",
            "exit_image_path": "",
            "daily_movements": [
                {
                    "id": 1,
                    "timestamp": "2026-10-07 08:30:00",
                    "direction": "Entry",
                    "gate_no": "Gate-01",
                    "access_type": "UHF RFID Access"
                },
                {
                    "id": 2,
                    "timestamp": "2026-10-07 12:45:00",
                    "direction": "Exit",
                    "gate_no": "Gate-01",
                    "access_type": "UHF RFID Access"
                }
            ],
            "notes": "Verified by Chief Security Officer. Authorized Club Passage."
        }

        res = client.post("/api/audit/custom-report/pdf", json=payload)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF-")

    def test_stats_avg_duration_and_fleet_adoption(self):
        """
        SCENARIO: /api/stats calculates real vehicle average stay duration,
        paired visits count, and registered vs unregistered adoption metrics.
        """
        pkt_today = config.get_pkt_today()
        test_car = "QA-DUR-888"
        with get_db_connection() as conn:
            # Insert paired Entry and Exit for today with 45 minutes duration
            conn.execute("""
                INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                VALUES ('M-888', 'Duration Test Member', ?, 'RFID Verified', 'Entry', 'Gate-01', 'TAG-DUR-888', ? || ' 10:00:00')
            """, (test_car, pkt_today))
            conn.execute("""
                INSERT INTO daily_logs (mem_id, name, vehicle_number, access_type, direction, gate_no, scanned_tag, timestamp)
                VALUES ('M-888', 'Duration Test Member', ?, 'RFID Verified', 'Exit', 'Gate-01', 'TAG-DUR-888', ? || ' 10:45:00')
            """, (test_car, pkt_today))
            conn.commit()

        res = client.get("/api/stats")
        assert res.status_code == 200
        stats = res.json()
        assert "avg_duration" in stats
        assert stats["avg_duration"] != "--"
        assert "45m" in stats["avg_duration"]
        assert stats["paired_visits_count"] >= 1
        assert "tag_adoption_rate" in stats
        assert "registration_gap_rate" in stats
        assert stats["tag_adoption_rate"] >= 0.0

    def test_chart_data_fleet_adoption_breakdown(self):
        """
        SCENARIO: /api/chart-data includes fleet_adoption breakdown for doughnut visualization.
        """
        res = client.get("/api/chart-data")
        assert res.status_code == 200
        data = res.json()
        assert "fleet_adoption" in data
        fa = data["fleet_adoption"]
        assert "registered_transits" in fa
        assert "unregistered_transits" in fa
        assert "adoption_rate" in fa
        assert "gap_rate" in fa
        assert "unassigned_buffer" in fa


