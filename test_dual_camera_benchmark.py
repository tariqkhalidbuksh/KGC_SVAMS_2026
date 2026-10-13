import os
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
from database import init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_benchmark_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_benchmark.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()
    return test_db

def test_dahua_config_endpoint():
    res = client.get("/api/simulate/dahua-config")
    assert res.status_code == 200
    data = res.json()
    assert "dahua_url" in data
    assert "hikvision_url" in data
    assert "192.168.0.221" in data["dahua_url"]

def test_dual_camera_trigger_simulated():
    payload = {
        "dahua_url": "rtsp://admin:admin123@192.168.0.221:554/cam/realmonitor?channel=1&subtype=0",
        "save_dahua_url": True,
        "direction": "Entry",
        "timeout_sec": 0.5,
        "simulate_fallback": True
    }
    res = client.post("/api/simulate/test-dual-camera-trigger", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "trigger_time" in data
    
    # Hikvision validation
    hik = data["hikvision"]
    assert "status" in hik
    assert "timestamp" in hik
    assert "latency_ms" in hik
    assert hik["latency_ms"] >= 0
    assert hik["image_path"] is not None
    
    # Dahua validation
    dahua = data["dahua"]
    assert "status" in dahua
    assert "timestamp" in dahua
    assert "latency_ms" in dahua
    assert dahua["latency_ms"] >= 0
    assert dahua["image_path"] is not None
    
    # Timing and Physics validation
    assert "time_delta_ms" in data
    disp = data["displacement_cm"]
    assert "speed_5kmh" in disp
    assert "speed_10kmh" in disp
    assert "speed_15kmh" in disp
    assert "analysis_notes" in data
    assert "Dahua HTTP Snapshot took" in data["analysis_notes"]

def test_simulate_page_contains_benchmark_ui():
    res = client.get("/simulate")
    assert res.status_code == 200
    html = res.text
    assert "Dual Camera Trigger &amp; Shutter Latency Benchmark" in html
    assert "simDahuaUrl" in html
    assert "dualTriggerBtn" in html
    assert "dualInspectModal" in html
    assert "Vehicle Displacement Estimation" in html

def test_get_event_hikvision_does_not_trigger_snapshot():
    from database import get_db_connection
    conn = get_db_connection()
    count_before = conn.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]
    conn.close()

    # GET request probe must be safe and idempotent
    res = client.get("/api/event/hikvision")
    assert res.status_code == 200
    assert res.json().get("status") == "listening"

    # Verify audit count has NOT increased
    conn = get_db_connection()
    count_after = conn.execute("SELECT COUNT(*) FROM camera_audit_logs").fetchone()[0]
    conn.close()

    assert count_after == count_before
