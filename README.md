# Karachi Gymkhana Club — Smart Vehicle Access Management System (KGC-SVAMS)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![UHF RFID](https://img.shields.io/badge/RFID-EPC%20Gen2%20UHF-blue.svg)](https://en.wikipedia.org/wiki/Radio-frequency_identification)
[![Computer Vision](https://img.shields.io/badge/Vision-YOLOv8%20%2B%20OpenCV-green.svg)](https://ultralytics.com)

---

## 📌 Executive Summary

**KGC-SVAMS** is an enterprise-grade, high-throughput vehicle gate access management platform engineered specifically for the **Karachi Gymkhana Club (KGC)**. The platform integrates long-range UHF RFID hardware, multi-angle RTSP IP security cameras (Hikvision & Dahua ANPR), AI vehicle detection, and low-latency asynchronous processing to automate vehicle authentication, prevent unauthorized access, and ensure smooth traffic flow at security gates.

---

## 🏗️ System Architecture

```
                                 [ HARDWARE LAYER ]
  +--------------------------+                      +--------------------------+
  |  UHF RFID Long-Range     |                      |  Dual RTSP IP Cameras    |
  |  Antenna (Entry / Exit)  |                      |  Hikvision (Wide Scene)  |
  |  TCP/IP Sockets          |                      |  Dahua (Close-Up Plate)  |
  +------------+-------------+                      +------------+-------------+
               |                                                 |
               | TCP Raw Read                                    | RTSP Frames /
               | Stream (Port 6000)                              | FTP Push (Port 2121)
               v                                                 v
  +----------------------------------------------------------------------------+
  |                          KGC-SVAMS FASTAPI BACKEND                         |
  |                                                                            |
  |  +---------------------+  +----------------------+  +-------------------+  |
  |  | RFID Ingestion &    |  | Smart Deduplication  |  | Anti-Passback &   |  |
  |  | EPC Filter Service  |  | & Image Fusion Engine|  | 45s Cross-Cooldown|  |
  |  +----------+----------+  +----------+-----------+  +---------+---------+  |
  |             |                        |                        |            |
  |             +------------------------+------------------------+            |
  |                                      |                                     |
  |                                      v                                     |
  |                        [ ATOMIC ACCESS DECISION ]                          |
  |                                      |                                     |
  |             +------------------------+------------------------+            |
  |             v                                                 v            |
  |  +--------------------+                             +-------------------+  |
  |  | SQLite ACID Store  |                             | Zero-Lag Memory   |  |
  |  | (10,798+ Members,  |                             | Cache (L1/L2)     |  |
  |  |  Audit Logs)       |                             +---------+---------+  |
  |  +--------------------+                                       |            |
  +---------------------------------------------------------------|------------+
                                                                  | WebSockets / SSE
                                                                  v
  +----------------------------------------------------------------------------+
  |                          FRONTEND PRESENTATION                             |
  |                                                                            |
  |   +---------------------------------+   +-------------------------------+  |
  |   | Modern Luxury Kiosk Display     |   | Operations Executive Portal   |  |
  |   | - High-contrast Member Cards    |   | - Live Traffic Logs & Stats   |  |
  |   | - Real-time Plate Rendering     |   | - Camera Vehicle Audits       |  |
  |   | - Unregistered Warning State    |   | - Member Directory & Reports  |  |
  |   +---------------------------------+   +-------------------------------+  |
  +----------------------------------------------------------------------------+
```

---

## ⚡ Key Capabilities & Security Mechanisms

### 1. Dual-Reader UHF RFID Processing
- **Direct TCP Socket Client**: Asynchronously reads incoming tag streams from long-range reader hardware (`192.168.0.217` Entry, `192.168.0.216` Exit).
- **Strict EPC Tag Filtering**: Automatically filters out corrupted reads, short scans, and non-EPC payloads, restricting processing strictly to genuine EPC Gen2 tags (starting with `E...`).

### 2. Multi-Tier Anti-Passback & Collision Prevention
- **45-Second Cross-Reader Cooldown**: If a vehicle sits between entry and exit antennas, dual-entry or rapid flip-flopping is strictly rejected. Once scanned, any opposite-gate trigger for the same tag within 45 seconds is throttled.
- **3.5-Second Gate Passage Debounce**: Prevents burst reads from logging duplicate access events when a car passes slowly under the antenna.

### 3. Dual-Camera Scene Fusion & Smart Deduplication
- **Hikvision (Wide Angle)**: Triggers on line-crossing events, capturing wide-angle scene contexts and vehicle positioning.
- **Dahua (ANPR Close-Up)**: Simultaneously grabs close-range frame crops targeted at the vehicle's license plate.
- **Smart Image Deduplication**: Redundant identical scene frames captured within rapid trigger intervals are automatically discarded, while close-up license plate captures are preserved without degradation.

### 4. Zero-Lag Real-Time Kiosk UI
- Glassmorphic luxury visual theme optimized for outdoor/indoor gate display monitors.
- **Registered Members**: Displays member photo, name, membership ID, formatted vehicle registration plate, car make/brand in high contrast.
- **Unregistered / Unknown Tags**: Suppresses plate styling and triggers an attention-grabbing caution state displaying the raw Tag ID for security guard intervention.
- **Automatic Fallback to Standby**: Transitions to a clean, branded standby screen when gates are idle.

### 5. Production Reliability & Crash Recovery
- **Automatic Watchdog**: Includes a batch watchdog daemon (`start_server.bat`) that monitors the Python process and automatically restarts the system within 5 seconds if an unexpected exception occurs.
- **One-Click Boot Autostart**: Scripts to register the application into Windows Startup and Windows Task Scheduler, ensuring automatic recovery after power outages or server reboots.

---

## 📂 Project Structure

```
RFID_VAMS/
├── app.py                      # FastAPI application entry point & lifespan manager
├── config.py                   # Centralized configuration, IPs, locks, and cache states
├── database.py                 # SQLite schema initialization, indexes, and connection pool
├── gate_access.db              # SQLite ACID database (10,790+ member records & logs)
├── etag tariq.xls              # Master membership Excel dataset
├── yolov8n.pt                  # YOLOv8 nano model for vehicle visual verification
├── requirements.txt            # Python dependencies
├── start_server.bat            # Production launcher with auto-restart watchdog
├── install_autostart.bat       # Auto-start registration on Windows reboot
├── uninstall_autostart.bat     # Disable auto-start registration
├── start_server_background.vbs # Silent background runner (no CMD window)
├── routers/                    # Modular FastAPI APIRouters
│   ├── logs.py                 # Daily gate pass logs & CSV exports
│   ├── members.py              # Member CRUD, search, photo alignment, Excel import
│   ├── settings.py             # Hardware IP, capacity, and traffic alert configuration
│   ├── stats.py                # Parking occupancy and entry/exit analytics
│   ├── tools.py                # Diagnostics, ping tests, reader resets
│   └── simulate.py             # Virtual RFID & camera hardware simulation suite
├── services/                   # Background daemons & business logic
│   ├── access_service.py       # Gate decision engine, cooldowns, image attachment
│   ├── camera_service.py       # RTSP capture, image integrity, stream workers
│   ├── rfid_service.py         # Asynchronous TCP client for UHF RFID readers
│   ├── member_service.py       # Membership synchronization and image matching
│   └── event_daemons.py        # Embedded FTP (2121) & SMTP (2525) event listeners
├── scripts/
│   └── manage_autostart.ps1    # PowerShell automation helper for Windows Startup
├── static/                     # Web assets & media storage
│   ├── club_logo.png           # KGC official emblem
│   ├── kiosk_bg.png            # Luxury kiosk background branding
│   ├── js/                     # Vanilla ES6 client modules (dashboard, kiosk, tools)
│   ├── camera_audits/          # Captured vehicle audit images
│   └── member_profile_img/     # Member directory portrait photos
├── templates/                  # Server-rendered HTML5 templates
│   ├── dashboard.html          # Operational dashboard & management console
│   ├── kiosk.html              # High-visibility luxury gate display
│   ├── tools.html              # Hardware diagnostics utility
│   └── simulate.html           # Full end-to-end simulation environment
└── test_app.py                 # Automated unit and integration test suite
```

---

## 🛠️ Hardware Requirements & Network Topology

| Component | Default IP / Port | Protocol | Purpose |
| :--- | :--- | :--- | :--- |
| **Entry RFID Reader** | `192.168.0.217:6000` | TCP Socket | UHF Long-range entry vehicle tag detection |
| **Exit RFID Reader** | `192.168.0.216:6000` | TCP Socket | UHF Long-range exit vehicle tag detection |
| **Hikvision IP Camera** | `192.168.0.220:554` | RTSP / FTP (2121) | Wide scene context & line-crossing snapshots |
| **Dahua ANPR Camera** | `192.168.0.218:554` | RTSP | High-resolution close-up license plate crop |
| **VAMS Core Server** | `0.0.0.0:8000` | HTTP / WebSocket | Web dashboard, kiosk display, and REST APIs |

---

## 🚀 Installation & Deployment Guide

### Prerequisites
- **Operating System**: Windows 10, Windows 11, or Windows Server 2019/2022.
- **Python**: Version 3.10 to 3.13 (64-bit recommended).
- **Network**: Direct Ethernet connection to the gate hardware VLAN (`192.168.0.0/24`).

### 1. Clone the Repository
```bash
git clone https://github.com/tariqkhalidbuksh/KGC_SVAMS_2026.git
cd KGC_SVAMS_2026
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launching the Server

#### Method A: Production Watchdog (Recommended)
Double-click **`start_server.bat`** or run in terminal:
```cmd
start_server.bat
```
*This launches the application with the auto-recovery watchdog enabled.*

#### Method B: Developer Mode
```bash
python app.py
```

### 4. Enable Automatic Startup on Server Reboot
To ensure the server starts automatically when the computer boots up:
1. Double-click **`install_autostart.bat`**.
2. *(Optional)* Right-click and choose **"Run as Administrator"** to also register a pre-logon Windows Task Scheduler job.

---

## 🌐 Web Interface Endpoints

Once the application is running, navigate to:

- **Executive Operations Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Gate Kiosk Display**: [http://localhost:8000/kiosk](http://localhost:8000/kiosk)
- **Hardware Diagnostics & Tools**: [http://localhost:8000/tools](http://localhost:8000/tools)
- **End-to-End Simulation Center**: [http://localhost:8000/simulate](http://localhost:8000/simulate)
- **Interactive REST API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Testing & Quality Assurance

The codebase includes comprehensive integration and stress tests covering atomic transactions, anti-passback locks, and deduplication logic:

```bash
pytest -v
```

All 28 automated test specifications execute in an isolated temporary sandbox (`tmp_path`) to ensure zero side-effects to the production `gate_access.db`.

---

## 🔒 License & Confidentiality

**Proprietary and Confidential.**  
Developed exclusively for **Karachi Gymkhana Club (KGC)**. Unauthorized distribution, reverse engineering, or reproduction of this codebase is strictly prohibited.
