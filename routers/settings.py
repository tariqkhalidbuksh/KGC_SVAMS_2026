import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import config
from database import get_db_connection
from services.camera_service import stream_video

router = APIRouter(prefix="/api", tags=["Settings & Streaming"])

@router.get("/logo")
async def get_logo():
    if os.path.exists(config.LOGO_PATH):
        return FileResponse(config.LOGO_PATH)
    return JSONResponse({"error": "No logo configured"}, status_code=404)

@router.get("/settings")
async def get_settings():
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT config_key, config_value FROM settings").fetchall()
            return {row['config_key']: row['config_value'] for row in rows}
        finally:
            conn.close()

@router.post("/settings")
async def save_settings(request: Request):
    body = await request.json()
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                for key, val in body.items():
                    conn.execute("INSERT OR REPLACE INTO settings (config_key, config_value) VALUES (?, ?)", (key, str(val)))
            return {"ok": True}
        finally:
            conn.close()

@router.get("/stream/hikvision")
async def stream_hikvision():
    return StreamingResponse(stream_video("Hikvision"), media_type="multipart/x-mixed-replace; boundary=frame")

@router.get("/stream/dahua")
async def stream_dahua():
    return StreamingResponse(stream_video("Dahua"), media_type="multipart/x-mixed-replace; boundary=frame")
