import os
import sys

# Ensure the application directory is always in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from database import init_db, get_db_connection
from services.camera_service import is_valid_image, preview_stream_worker
from services.access_service import execute_access_decision, attach_images_to_log
from services.rfid_service import rfid_tcp_client_worker, buffer_cleaner_worker
from services.event_daemons import start_ftp_server, start_smtp_server, folder_watcher_worker
from routers import logs, members, stats, settings, tools, simulate, auth

from services.member_service import align_member_photos

DB_FILE = config.DB_FILE
PENDING_RFID_BUFFER = config.PENDING_RFID_BUFFER
BUFFER_LOCK = config.BUFFER_LOCK

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    align_member_photos()
    threading.Thread(target=start_ftp_server, daemon=True, name="FTPDaemon").start()
    threading.Thread(target=start_smtp_server, daemon=True, name="SMTPDaemon").start()
    threading.Thread(target=folder_watcher_worker, daemon=True, name="FolderWatcher").start()
    threading.Thread(target=rfid_tcp_client_worker, args=("Entry", "entry_reader_ip"), daemon=True, name="RFIDEntryWorker").start()
    threading.Thread(target=rfid_tcp_client_worker, args=("Exit", "exit_reader_ip"), daemon=True, name="RFIDExitWorker").start()
    threading.Thread(target=preview_stream_worker, args=("Hikvision", "hikvision_cam_url"), daemon=True, name="HikStreamWorker").start()
    threading.Thread(target=buffer_cleaner_worker, daemon=True, name="BufferCleaner").start()
    yield

app = FastAPI(title="Karachi Gymkhana Club - Smart Vehicle Access", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(logs.router)
app.include_router(members.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(tools.router)
app.include_router(simulate.router)

@app.api_route("/api/event/hikvision", methods=["GET", "POST", "PUT"])
@app.api_route("/api/camera/trigger", methods=["GET", "POST"])
@app.api_route("/ISAPI/Event/notification/alertStream", methods=["GET", "POST", "PUT"])
async def direct_camera_trigger(request: Request):
    from routers.tools import receive_camera_trigger
    return await receive_camera_trigger(request)

def render_template(template_name: str) -> str:
    path = os.path.join("templates", template_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
async def login_view(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return HTMLResponse(content=render_template("login.html"))

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if not user:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        return RedirectResponse(url=f"/login?next={next_path}")
    return HTMLResponse(content=render_template("dashboard.html"))

@app.get("/kiosk", response_class=HTMLResponse)
async def kiosk_view(request: Request):
    return HTMLResponse(content=render_template("kiosk.html"))

@app.get("/tools", response_class=HTMLResponse)
async def tools_view(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login?next=/tools")
    return HTMLResponse(content=render_template("tools.html"))

@app.get("/camera-audit")
async def camera_audit_view():
    return RedirectResponse(url="/?tab=camera_audit")

@app.get("/members")
async def members_view():
    return RedirectResponse(url="/?tab=members")

@app.get("/settings")
@app.get("/hardware")
@app.get("/hardware-settings")
@app.get("/hardware-setting")
async def settings_view():
    return RedirectResponse(url="/?tab=settings")

@app.get("/logs")
@app.get("/audit")
@app.get("/reports")
async def logs_view():
    return RedirectResponse(url="/?tab=logs")

@app.get("/overview")
async def overview_view():
    return RedirectResponse(url="/?tab=overview")

@app.get("/simulate", response_class=HTMLResponse)
async def simulate_view(request: Request):
    from routers.auth import get_current_user_optional
    user = get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login?next=/simulate")
    return HTMLResponse(content=render_template("simulate.html"))

def free_port(port: int):
    import subprocess, os
    try:
        output = subprocess.check_output('netstat -ano -p tcp', shell=True).decode()
        current_pid = os.getpid()
        for line in output.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = int(parts[-1])
                if pid != current_pid and pid > 0:
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    for p in (8000, 2121):
        free_port(p)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)