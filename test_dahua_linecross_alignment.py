import os
import time
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
from database import init_db, get_db_connection
from services.access_service import process_camera_line_crossing
from services.camera_service import create_simulated_hikvision_frame, create_simulated_anpr_frame, is_valid_image, grab_dahua_snapshot

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = os.path.join(tmp_path, "test_align.db")
    monkeypatch.setattr(app_module, "DB_FILE", test_db)
    monkeypatch.setattr(config, "DB_FILE", test_db)
    init_db()
    return test_db

def test_no_dahua_stream_worker_in_app():
    """Verify Dahua is NOT continuously decoded or buffered in RAM."""
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()
    assert "DahuaStreamWorker" not in content, "Dahua continuous streaming worker must not run in RAM"

def test_grab_dahua_snapshot_on_demand():
    """Verify grab_dahua_snapshot runs on-demand with timeout handling."""
    # With dummy offline host or real host, it returns within timeout without exception
    img, latency, err = grab_dahua_snapshot(dahua_url_or_key="http://admin:admin123@127.0.0.1:9999/cgi-bin/snapshot.cgi", timeout=0.2)
    assert latency >= 0
    assert img is None or is_valid_image(img)

def test_process_camera_line_crossing_aligns_dahua(tmp_path, monkeypatch):
    """Verify Hikvision line-crossing event triggers Dahua capture and aligns both frames."""
    import cv2
    
    # Create dummy Hikvision image
    hik_frame = create_simulated_hikvision_frame(direction="Entry")
    hik_path = os.path.join(tmp_path, "hik_incoming.jpg")
    cv2.imwrite(hik_path, hik_frame)

    # Mock grab_dahua_snapshot to return simulated Dahua ANPR frame
    dahua_frame = create_simulated_anpr_frame(plate_text="KGC-777")
    monkeypatch.setattr("services.camera_service.grab_dahua_snapshot", lambda *args, **kwargs: (dahua_frame, 320.0, None))

    # Process line crossing
    audit_id = process_camera_line_crossing(hik_path, forced_direction="Entry")
    assert audit_id is not None

    # Verify database entry
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM camera_audit_logs WHERE id=?", (audit_id,)).fetchone()
        assert row is not None
        assert row["image_path"] is not None
        assert "hikvision_full_" in row["image_path"]
        assert row["plate_image_path"] is not None
        assert "dahua_anpr_" in row["plate_image_path"]
        assert row["direction"] == "Entry"
        
        # Verify both image files actually exist on disk
        assert os.path.exists(row["image_path"])
        assert os.path.exists(row["plate_image_path"])
    finally:
        conn.close()

def test_dashboard_modal_has_dual_camera_controls():
    """Verify the dashboard template contains dual-camera switcher and split view."""
    with open("templates/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert 'id="camProofViewSwitcher"' in html
    assert 'switchCamProofView' in html
    assert 'id="camProofSplitView"' in html
    assert 'id="camProofSplitImgHik"' in html
    assert 'id="camProofSplitImgDahua"' in html

def test_simulate_linecross_captures_aligned_dahua():
    """Verify POST /api/simulate-linecross returns ok and stores aligned Dahua frame."""
    import io
    dummy_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200 + b"\xFF\xD9"
    files = {"file": ("test_hik.jpg", io.BytesIO(dummy_bytes), "image/jpeg")}
    data = {"direction": "Entry"}
    res = client.post("/api/simulate-linecross", files=files, data=data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["ok"] is True
    assert "path" in res_data
    
    # Check that database contains the record
    conn = get_db_connection()
    try:
        latest = conn.execute("SELECT * FROM camera_audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        assert latest is not None
        assert latest["image_path"] is not None
        assert latest["plate_image_path"] is not None
    finally:
        conn.close()
