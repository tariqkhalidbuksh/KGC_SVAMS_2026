import os
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
from routers import logs, members, stats, settings, tools, simulate

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
    threading.Thread(target=preview_stream_worker, args=("Hikvision", "hikvision_cam_url"), daemon=True, name="CamStreamWorker").start()
    threading.Thread(target=buffer_cleaner_worker, daemon=True, name="BufferCleaner").start()
    yield

app = FastAPI(title="Karachi Gymkhana Club - Smart Vehicle Access", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(logs.router)
app.include_router(members.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(tools.router)
app.include_router(simulate.router)

def render_template(template_name: str) -> str:
    path = os.path.join("templates", template_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    return HTMLResponse(content=render_template("dashboard.html"))

@app.get("/kiosk", response_class=HTMLResponse)
async def kiosk_view(request: Request):
    return HTMLResponse(content=render_template("kiosk.html"))

@app.get("/tools", response_class=HTMLResponse)
async def tools_view(request: Request):
    return HTMLResponse(content=render_template("tools.html"))

@app.get("/camera-audit")
async def camera_audit_view():
    return RedirectResponse(url="/?tab=camera_audit")

@app.get("/simulate", response_class=HTMLResponse)
async def simulate_view(request: Request):
    return HTMLResponse(content=render_template("simulate.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)