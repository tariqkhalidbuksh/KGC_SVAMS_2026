import os
import threading
from collections import deque
from datetime import datetime, timezone, timedelta

# System Local Timezone (dynamically aligned to host machine's system clock)
LOCAL_TZ = datetime.now().astimezone().tzinfo
PKT_TZ = LOCAL_TZ
TZ_OFFSET_STRING = "localtime"

DB_FILE = "gate_access.db"
STATIC_DIR = "static"
LOGO_PATH = os.path.join(STATIC_DIR, "club_logo.png")
SNAPSHOT_DIR = os.path.join(STATIC_DIR, "snapshots")
FTP_UPLOAD_DIR = os.path.join(STATIC_DIR, "ftp_uploads")
TEST_DIR = os.path.join(STATIC_DIR, "tools_test")
PROFILE_DIR = os.path.join(STATIC_DIR, "profiles")
MEMBER_PROFILE_IMG_DIR = os.path.join(STATIC_DIR, "member_profile_img")
CAMERA_AUDIT_DIR = os.path.join(STATIC_DIR, "camera_audit")

for directory_path in [SNAPSHOT_DIR, FTP_UPLOAD_DIR, TEST_DIR, PROFILE_DIR, MEMBER_PROFILE_IMG_DIR, CAMERA_AUDIT_DIR]:
    os.makedirs(directory_path, exist_ok=True)

DB_LOCK = threading.Lock()
FUSION_LOCK = threading.Lock()
BUFFER_LOCK = threading.Lock()
CACHE_LOCK = threading.Lock()
FRAME_LOCK = threading.Lock()

# 45-second universal cooldown across readers (prevents dual entry/exit and rapid multi-reads)
CROSS_READ_COOLDOWN = 45.0
GATE_COOLDOWN_WINDOW = 3.5

GLOBAL_TAG_LOCKS = {}
PENDING_RFID_BUFFER = []
LAST_GATE_PASSAGE = {"time": 0.0, "log_id": None, "md5": None}

# In-memory zero-lag caches
LATEST_LOG_CACHE = None
MEMBERS_METRICS_CACHE = {"data": None, "timestamp": 0.0}
RECENT_CAM_TRIGGERS = deque(maxlen=30)

READER_STATUS = {"Entry": "DISCONNECTED", "Exit": "DISCONNECTED"}
CAM_STATUS = {"Hikvision": "UNKNOWN", "Dahua": "UNKNOWN"}
LATEST_JPEG_BUFFERS = {"Hikvision": None, "Dahua": None}
LATEST_RAW_FRAMES = {"Hikvision": None, "Dahua": None}
LATEST_FRAME_TIMES = {"Hikvision": 0.0, "Dahua": 0.0}
RECENT_TAGS = deque(maxlen=30)
FTP_EVENT_COUNT = {"count": 0}
ENROLL_MODE = {"active": False}

def get_pkt_now() -> str:
    """Returns the current timestamp exactly matching the host system's clock."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_pkt_today() -> str:
    """Returns today's date exactly matching the host system's clock."""
    return datetime.now().strftime("%Y-%m-%d")

get_local_now = get_pkt_now
get_local_today = get_pkt_today
