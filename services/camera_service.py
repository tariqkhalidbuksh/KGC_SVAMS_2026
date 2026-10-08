import os
import re
import time
import threading
import cv2
import numpy as np
import requests
import config
from database import get_setting

# Suppress verbose FFmpeg/OpenCV C-level decoder logs (e.g. HEVC POC jitter warnings)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
try:
    cv2.setLogLevel(0)
except Exception:
    pass

YOLO_MODEL = None
YOLO_LOCK = threading.Lock()

def create_blank_image(text: str = "OFFLINE") -> bytes:
    blank = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.putText(blank, text, (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (150, 150, 150), 2)
    _, buffer = cv2.imencode('.jpg', blank)
    return buffer.tobytes()

def _cam_credentials(url_setting_key: str):
    url = get_setting(url_setting_key, '')
    match = re.search(r'rtsp://([^:]+):([^@]+)@([0-9.]+)', url)
    return match.groups() if match else None

def is_valid_image(img) -> bool:
    if img is None or not isinstance(img, np.ndarray) or img.size == 0:
        return False
    if img.shape[0] < 50 or img.shape[1] < 50:
        return False
    
    mean_val = float(np.mean(img))
    std_val = float(np.std(img))
    if mean_val < 3.0 or std_val < 2.0:
        return False
        
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if laplacian_var < 3.0:
            return False
    except Exception:
        pass
        
    return True

def save_snapshot(img, prefix: str):
    if not is_valid_image(img):
        return None
    stamp = int(time.time() * 1000)
    relative_path = f"static/snapshots/{prefix}_{stamp}.jpg"
    try:
        cv2.imwrite(relative_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return relative_path
    except Exception:
        return None

def grab_hikvision_snapshot(timeout: float = 1.2):
    creds = _cam_credentials('hikvision_cam_url')
    if not creds:
        return None
    user, pwd, ip = creds
    start_t = time.time()
    for channel in ("101", "102"):
        elapsed = time.time() - start_t
        remaining = timeout - elapsed
        if remaining <= 0.15:
            break
        req_timeout = min(remaining, 1.0)
        try:
            res = requests.get(f"http://{ip}/ISAPI/Streaming/channels/{channel}/picture",
                               auth=requests.auth.HTTPDigestAuth(user, pwd), timeout=req_timeout)
            if res.status_code == 200:
                arr = np.frombuffer(res.content, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if is_valid_image(img):
                    with config.FRAME_LOCK:
                        config.CAM_STATUS["Hikvision"] = "ONLINE"
                    return img
        except Exception:
            continue
    with config.FRAME_LOCK:
        config.CAM_STATUS["Hikvision"] = "OFFLINE"
    return None

def grab_verified_snapshot(cam_key: str = "Hikvision", max_timeout_sec: float = 1.5):
    norm_key = cam_key.capitalize() if cam_key else "Hikvision"
    now = time.time()

    # 1. Zero-lag instant capture from live RTSP RAM frame buffer (< 1ms)
    with config.FRAME_LOCK:
        raw_frame = config.LATEST_RAW_FRAMES.get(norm_key)
        frame_time = config.LATEST_FRAME_TIMES.get(norm_key, 0.0)
        if raw_frame is not None and (now - frame_time) <= 2.0:
            if is_valid_image(raw_frame):
                return raw_frame.copy()

    # Fallback to RAM JPEG buffer if raw frame was not ready
    buf = config.LATEST_JPEG_BUFFERS.get(norm_key)
    if buf:
        try:
            arr = np.frombuffer(buf, np.uint8)
            stream_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if is_valid_image(stream_img):
                return stream_img
        except Exception:
            pass

    # 2. Fast HTTP direct snapshot fallback (with strict <= 1.2s timeout)
    img = grab_hikvision_snapshot(timeout=max_timeout_sec)
    if is_valid_image(img):
        return img

    return None

def preview_stream_worker(cam_key: str, url_setting_key: str):
    norm_key = cam_key.capitalize()
    while True:
        cam_url = get_setting(url_setting_key, "")
        if not cam_url:
            time.sleep(2)
            continue
        try:
            # Real-time zero-lag RTSP options: TCP transport, drop buffer queues, minimal delay, quiet logs
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;100000|loglevel;fatal"
            cap = cv2.VideoCapture(cam_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            last_jpeg_time = 0.0
            consecutive_failures = 0

            while cap.isOpened():
                # Grab next frame packet without blocking decompression
                grabbed = cap.grab()
                if not grabbed:
                    consecutive_failures += 1
                    if consecutive_failures > 10:
                        break
                    time.sleep(0.02)
                    continue

                consecutive_failures = 0
                now = time.time()

                # Decode the real-time frame
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    continue

                # Store live raw BGR frame directly in RAM (0ms latency, always current)
                with config.FRAME_LOCK:
                    config.LATEST_RAW_FRAMES[norm_key] = frame
                    config.LATEST_FRAME_TIMES[norm_key] = now
                    config.CAM_STATUS[norm_key] = "ONLINE"

                # Downsample JPEG encoding to ~3 fps for web UI preview to conserve CPU
                if now - last_jpeg_time >= 0.33:
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
                    config.LATEST_JPEG_BUFFERS[norm_key] = buffer.tobytes()
                    last_jpeg_time = now

            cap.release()
        except Exception:
            pass

        with config.FRAME_LOCK:
            config.CAM_STATUS[norm_key] = "RECONNECTING"
        time.sleep(1.5)

def stream_video(cam_key: str):
    while True:
        buffer = config.LATEST_JPEG_BUFFERS.get(cam_key)
        if buffer is None:
            buffer = create_blank_image(f"{cam_key} OFFLINE")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer + b'\r\n')
        time.sleep(0.2)

def get_yolo_model():
    global YOLO_MODEL
    if YOLO_MODEL is None:
        with YOLO_LOCK:
            if YOLO_MODEL is None:
                from ultralytics import YOLO
                YOLO_MODEL = YOLO('yolov8n.pt')
    return YOLO_MODEL

def analyze_vehicle_direction(image_path: str) -> str:
    try:
        model = get_yolo_model()
        img = cv2.imread(image_path)
        if img is None:
            return "Entry"
            
        results = model(img, classes=[2, 3, 5, 7], verbose=False)
        
        car_crop = img
        if len(results) > 0 and len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
            largest_idx = np.argmax(areas)
            x1, y1, x2, y2 = map(int, boxes[largest_idx])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
            if (x2 - x1) > 20 and (y2 - y1) > 20:
                car_crop = img[y1:y2, x1:x2]
            
        hsv = cv2.cvtColor(car_crop, cv2.COLOR_BGR2HSV)
        
        lower_red1 = np.array([0, 70, 50])
        upper_red1 = np.array([12, 255, 255])
        lower_red2 = np.array([165, 70, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red = cv2.bitwise_or(cv2.inRange(hsv, lower_red1, upper_red1), 
                                  cv2.inRange(hsv, lower_red2, upper_red2))
                                  
        red_pixels = cv2.countNonZero(mask_red)
        total_crop_pixels = max(1, car_crop.shape[0] * car_crop.shape[1])
        red_pct = (red_pixels / total_crop_pixels) * 100.0
        
        if red_pixels >= 200 or red_pct >= 0.6:
            return "Exit"
        else:
            return "Entry"
    except Exception:
        return "Entry"
