import pytest
import httpx

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

from starlette.testclient import TestClient
from app import app
import config
from services.rfid_service import parse_host_port

client = TestClient(app)

def test_parse_host_port():
    # Plain IP
    assert parse_host_port("192.168.0.214") == ("192.168.0.214", 49152)
    # Host with custom port
    assert parse_host_port("192.168.0.214:6000") == ("192.168.0.214", 6000)
    assert parse_host_port("  192.168.0.214:4001  ") == ("192.168.0.214", 4001)
    # Hostname with port
    assert parse_host_port("reader.local:5000") == ("reader.local", 5000)
    # Fallback default
    assert parse_host_port("", default_port=49152) == ("", 49152)

def test_diagnose_reader_endpoint():
    res = client.get("/api/tools/diagnose-reader/ClubRoad_Entry")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["reader_id"] == "ClubRoad_Entry"
    assert "host" in data
    assert "ping" in data
    assert "hardware" in data
    assert "port_scan" in data
    assert "diagnosis" in data
    assert "root_cause" in data["diagnosis"]
    assert "action_items" in data["diagnosis"]

def test_update_reader_ip_endpoint():
    # Test valid update
    res = client.post("/api/tools/update-reader-ip/ClubRoad_Entry", json={"ip": "192.168.0.214:49152"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["new_ip"] == "192.168.0.214:49152"

    # Test invalid reader
    res_bad = client.post("/api/tools/update-reader-ip/InvalidReader", json={"ip": "192.168.0.214"})
    assert res_bad.status_code == 400

    # Test empty IP
    res_empty = client.post("/api/tools/update-reader-ip/ClubRoad_Entry", json={"ip": ""})
    assert res_empty.status_code == 400

def test_telemetry_includes_error_info():
    # Artificially set an error in telemetry
    config.READER_TELEMETRY["ClubRoad_Entry"]["last_error"] = "ConnectionRefusedError: [WinError 10061] No connection could be made"
    config.READER_TELEMETRY["ClubRoad_Entry"]["reconnects"] = 42

    res = client.get("/api/tools/telemetry?synthetic=false")
    assert res.status_code == 200
    data = res.json()
    dev = data["devices"]["ClubRoad_Entry"]
    assert dev["last_error"] == "ConnectionRefusedError: [WinError 10061] No connection could be made"
    assert dev["reconnects"] == 42
