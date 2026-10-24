import pytest
import os
import httpx
from fastapi.testclient import TestClient
import app as app_module
from app import app, init_db, get_db_connection

_orig_client_init = httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):
    kwargs.pop('app', None)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _compat_client_init

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    db_file = os.path.join(tmp_path, "test_gate_access.db")
    monkeypatch.setattr(app_module, "DB_FILE", db_file)
    init_db()
    yield db_file

def test_login_page_renders_with_kiosk_bg():
    res = client.get("/login", headers={"user-agent": "Mozilla/5.0 Chrome/120.0"})
    assert res.status_code == 200
    html = res.text
    assert "kiosk_bg.png" in html
    assert "Karachi Gymkhana Club" in html
    assert "Smart Vehicle Access Management System" in html
    assert "Username" in html
    assert "Password" in html
    assert "admin123" not in html
    assert "submitBtn" in html

def test_login_success_admin():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123", "remember": True})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["user"]["role"] == "Admin"
    assert data["user"]["username"] == "admin"
    assert "kgc_session" in res.cookies

def test_login_success_operator():
    res = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["user"]["role"] == "Editor"
    assert data["user"]["username"] == "operator"

def test_login_success_security_viewer():
    res = client.post("/api/auth/login", json={"username": "security", "password": "security123"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["user"]["role"] == "Viewer"
    assert data["user"]["username"] == "security"

def test_login_invalid_password():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert res.status_code == 401
    data = res.json()
    assert data["ok"] is False
    assert "Invalid username or password" in data["error"]

def test_auth_me_and_logout():
    # Login as security
    login_res = client.post("/api/auth/login", json={"username": "security", "password": "security123"})
    cookie_token = login_res.cookies.get("kgc_session")

    # Verify session via me endpoint
    me_res = client.get("/api/auth/me", cookies={"kgc_session": cookie_token})
    assert me_res.status_code == 200
    assert me_res.json()["authenticated"] is True
    assert me_res.json()["user"]["username"] == "security"

    # Logout
    logout_res = client.post("/api/auth/logout", cookies={"kgc_session": cookie_token})
    assert logout_res.status_code == 200

    # Verify session expired
    me_after = client.get("/api/auth/me", cookies={"kgc_session": cookie_token}, headers={"user-agent": "Mozilla/5.0"})
    assert me_after.json()["authenticated"] is False

def test_viewer_role_cannot_add_or_delete_member():
    # Login as Viewer
    login_res = client.post("/api/auth/login", json={"username": "security", "password": "security123"})
    cookie = {"kgc_session": login_res.cookies.get("kgc_session")}

    # Attempt to add member
    add_res = client.post("/api/add-member", json={
        "mem_id": "KG-9999",
        "name": "Unauthorized Attempt",
        "car_number": "XYZ-999",
        "e_tag_id": "E280999999999999"
    }, cookies=cookie)
    assert add_res.status_code == 403

    # Attempt to delete member
    del_res = client.delete("/api/members/KG-9999", cookies=cookie)
    assert del_res.status_code == 403

    # Attempt to save settings
    set_res = client.post("/api/settings", json={"club_name": "Hacked Name"}, cookies=cookie)
    assert set_res.status_code == 403

def test_editor_can_add_member_but_cannot_save_settings():
    # Login as Editor
    login_res = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    cookie = {"kgc_session": login_res.cookies.get("kgc_session")}

    # Editor can add member
    add_res = client.post("/api/add-member", json={
        "mem_id": "KG-8888",
        "name": "Operator Added Member",
        "car_number": "OPR-888",
        "e_tag_id": "E280888888888888"
    }, cookies=cookie)
    assert add_res.status_code == 200

    # Editor cannot modify hardware settings
    set_res = client.post("/api/settings", json={"club_name": "New Name"}, cookies=cookie)
    assert set_res.status_code == 403

def test_user_management_crud_by_admin():
    # Login as Admin
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    admin_cookie = {"kgc_session": login_res.cookies.get("kgc_session")}

    # 1. List users
    list_res = client.get("/api/users", cookies=admin_cookie)
    assert list_res.status_code == 200
    users = list_res.json()["users"]
    assert len(users) >= 3

    # 2. Create new user
    create_res = client.post("/api/users", json={
        "username": "gatekeeper",
        "password": "gatekeeper123",
        "full_name": "Gatekeeper Officer",
        "role": "Editor",
        "is_active": 1
    }, cookies=admin_cookie)
    assert create_res.status_code == 200
    new_user = create_res.json()["user"]
    new_id = new_user["id"]
    assert new_user["username"] == "gatekeeper"
    assert new_user["role"] == "Editor"

    # 3. Update user (change role to Viewer and update name)
    update_res = client.put(f"/api/users/{new_id}", json={
        "full_name": "Gatekeeper Senior Officer",
        "role": "Viewer",
        "is_active": 1
    }, cookies=admin_cookie)
    assert update_res.status_code == 200
    updated_user = update_res.json()["user"]
    assert updated_user["full_name"] == "Gatekeeper Senior Officer"
    assert updated_user["role"] == "Viewer"

    # 4. Delete user
    del_res = client.delete(f"/api/users/{new_id}", cookies=admin_cookie)
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True

    # 5. Prevent deleting self
    admin_user = [u for u in users if u["username"] == "admin"][0]
    self_del_res = client.delete(f"/api/users/{admin_user['id']}", cookies=admin_cookie)
    assert self_del_res.status_code == 400
    assert "cannot delete your own account" in self_del_res.json()["error"]
