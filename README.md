# Karachi Gymkhana Club — Smart Vehicle Access Management System (KGC-SVAMS)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![UHF RFID](https://img.shields.io/badge/RFID-EPC%20Gen2%20UHF-blue.svg)](https://en.wikipedia.org/wiki/Radio-frequency_identification)
[![Computer Vision](https://img.shields.io/badge/Vision-YOLOv8%20%2B%20OpenCV-green.svg)](https://ultralytics.com)

---

## 📌 Executive Summary

**KGC-SVAMS** is an enterprise-grade, high-throughput vehicle gate access management platform engineered specifically for the **Karachi Gymkhana Club (KGC)**. The platform integrates long-range UHF RFID hardware, Hikvision IP security cameras (Line-Crossing & Vehicle Overview), AI vehicle detection, and low-latency asynchronous processing to automate vehicle authentication, prevent unauthorized access, and ensure smooth traffic flow at security gates.

---

## 🏗️ System Architecture

```
                                 [ HARDWARE LAYER ]
  +--------------------------+                      +--------------------------+
  |  UHF RFID Long-Range     |                      |  Hikvision IP Camera     |
  |  Antenna (Entry / Exit)  |                      |  (Wide Scene Overview)   |
  |  TCP/IP Sockets          |                      |  Line-Crossing Detection |
  +------------+-------------+                      +------------+-------------+
               |                                                 |
               | TCP Raw Read                                    | RTSP Frames /
               | Stream (Port 6000)                              | HTTP Push / FTP (Port 2121)
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
  |  | PostgreSQL DB      |                             | Zero-Lag Memory   |  |
  |  | (10,800+ Members,  |                             | Cache (L1/L2)     |  |
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

### 3. Hikvision Optical Line-Crossing & Vehicle Overview
- **Hikvision (Wide Angle)**: Triggers on line-crossing events, capturing wide-angle scene contexts and vehicle positioning.
- **Smart Image Deduplication**: Redundant identical scene frames captured within rapid trigger intervals are automatically discarded to keep storage lean and responsive.

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
├── config.py                   # Central environment, network, and hardware configurations
├── database.py                 # PostgreSQL connection pooling, schema init, and migrations
├── requirements.txt            # Python production dependencies
├── pytest.ini                  # Pytest configuration & test path registry
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules for bytecode, caches, logs, and artifacts
├── README.md                   # Comprehensive system documentation
│
├── startup.bat                 # One-click setup, PostgreSQL check, and launcher
├── start_server.bat            # Production launcher with auto-restart watchdog
├── start_server_background.vbs # Silent background runner (no terminal window)
├── install_autostart.bat       # Windows autostart installer (Task Scheduler & Startup)
├── uninstall_autostart.bat     # Windows autostart uninstaller
├── restore_db.bat              # One-click database restoration helper
├── restore_db.py               # Database restore script for PostgreSQL
├── kgc_vams_backup.sql         # Canonical base database dump
├── yolov8n.pt                  # YOLOv8 nano model for vehicle verification
│
├── routers/                    # Modular FastAPI APIRouters
│   ├── auth.py                 # User authentication, RBAC, session management
│   ├── logs.py                 # Daily gate pass logs, pairing, and CSV exports
│   ├── members.py              # Member directory, photo alignment, spreadsheet import
│   ├── settings.py             # Hardware IP, capacity, traffic alert configurations
│   ├── stats.py                # Live parking occupancy and analytical reporting
│   ├── tools.py                # Hardware diagnostics, socket monitors, reader resets
│   ├── simulate.py             # Virtual RFID & camera hardware simulation suite
│   └── etag.py                 # E-tag verification and audit endpoints
│
├── services/                   # Background daemons & business logic engines
│   ├── access_service.py       # Gate decision engine, cooldowns, image attachment
│   ├── camera_service.py       # RTSP capture, image integrity, stream workers
│   ├── rfid_service.py         # Asynchronous TCP socket client for UHF RFID readers
│   ├── member_service.py       # Membership synchronization and image matching
│   ├── event_daemons.py        # Embedded FTP (2121) & SMTP (2525) event listeners
│   └── pdf_service.py          # Professional executive PDF export generator
│
├── static/                     # Web assets, styles, client scripts & media
│   ├── js/                     # Modular client-side JavaScript controllers
│   │   ├── dashboard.js        # Executive dashboard UI logic & real-time updates
│   │   ├── kiosk.js            # Dual-gate kiosk terminal controller & Sindh plate renderer
│   │   ├── tools.js            # Hardware diagnostic and ping monitor controller
│   │   └── simulate.js         # Virtual hardware simulation controller
│   ├── club_logo.png           # Karachi Gymkhana Club official crest
│   ├── kiosk_bg.png            # Luxury architectural terminal backdrop
│   ├── camera_audits/          # Captured vehicle audit scene images
│   ├── member_profile_img/     # Member directory portrait photographs
│   └── snapshots/              # Real-time camera snapshots
│
├── templates/                  # Server-rendered HTML5 templates
│   ├── dashboard.html          # Operational dashboard & management console
│   ├── kiosk.html              # High-visibility luxury gate access display
│   ├── tools.html              # Hardware diagnostics and socket monitoring utility
│   ├── simulate.html           # Full end-to-end hardware simulation environment
│   └── login.html              # Secure administrative authentication portal
│
├── tests/                      # Automated Test Suite (144+ Specifications)
│   ├── __init__.py
│   ├── conftest.py             # Test isolation fixtures & temporary DB configuration
│   ├── test_app.py             # Core routes, middleware, and lifecycle tests
│   ├── test_auth_and_user_mgmt.py # User authentication and RBAC permission tests
│   ├── test_dahua_linecross_alignment.py # Dual-camera synchronization & alignment
│   ├── test_deep_production_verification.py # 15-point deep production integrity verification
│   ├── test_dual_camera_benchmark.py # Camera capture and latency benchmarks
│   ├── test_etag_audit.py      # E-tag audit, history, and status filtering tests
│   ├── test_manual_and_bulk_exit.py # Manual pass, bulk midnight clearance tests
│   ├── test_multi_gate_kiosk_qa.py # Dual-gate kiosk isolation and switcher tests
│   ├── test_multi_gate_tracking.py # Gate 01 vs Club Road multi-gate tracking tests
│   ├── test_new_features.py    # Recent features, photo modal, and PDF tests
│   ├── test_reader_diagnostic_qa.py # Hardware diagnostics and port scanner tests
│   ├── test_reader_rename_and_cooldown_qa.py # Reader cooldown & anti-passback tests
│   ├── test_rfid_gate_qa.py    # Tag stream processing & antenna event tests
│   ├── test_unregistered_and_enrollment.py # Unregistered vehicle holding & alert tests
│   └── test_vehicle_audit_and_reports.py # Vehicle reporting, date range & filter tests
│
├── scripts/                    # Maintenance, migration, and automation utilities
│   ├── analyze_legacy_dbs.py   # Legacy SQLite database schema analyzer
│   ├── clear_legacy_inside.py  # Reset and cleanup stale inside vehicle states
│   ├── ensure_pg.py            # PostgreSQL service availability and auto-start
│   ├── ingest_legacy_dbs.py    # Ingest legacy SQLite records into PostgreSQL
│   ├── inspect_schema.py       # Database schema and index validation helper
│   ├── manage_autostart.ps1    # PowerShell automation helper for Windows Startup
│   ├── migrate_sqlite_to_pg.py # One-time SQLite to PostgreSQL migration script
│   ├── process_system_outside.py # System auto-clearance processing script
│   ├── reset_activity_data.py  # Factory reset for activity logs
│   └── setup_pg_compat.py      # PostgreSQL compatibility layer setup
│
├── data/                       # Datasets, templates, and spreadsheets
│   └── imports/                # Raw membership spreadsheets for import
│       ├── etag tariq.xls      # Master membership Excel dataset
│       └── my_tags.xlsx        # Reference RFID tag assignment workbook
│
├── backups/                    # Database snapshot archives
│   └── kgc_vams_backup_20261022_131153_full.sql # Historical database snapshot
│
├── legacy_dbs/                 # Archived SQLite databases from historical deployments
│
└── .agents/                    # Workspace agent customizations and skills
    └── skills/                 # High-performance design & UI engineering skills
```

---

## 🛠️ Hardware Requirements & Network Topology

| Component | Default IP / Port | Protocol | Purpose |
| :--- | :--- | :--- | :--- |
| **Entry RFID Reader** | `192.168.0.217:6000` | TCP Socket | UHF Long-range entry vehicle tag detection |
| **Exit RFID Reader** | `192.168.0.216:6000` | TCP Socket | UHF Long-range exit vehicle tag detection |
| **Hikvision IP Camera** | `192.168.0.220:554` | RTSP / FTP (2121) | Wide scene context & line-crossing snapshots |
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

The codebase includes an enterprise-grade automated test suite with 144+ comprehensive specifications covering atomic access decisions, dual-camera synchronization, multi-gate tracking, anti-passback locks, and deep production verification:

```bash
pytest
```

All 144 automated test specifications execute in an isolated test database sandbox (`kgc_vams_test` & `tmp_path`) with automatic rollback and sequence resets, guaranteeing zero side-effects to the production database.

---

## 🔒 License & Confidentiality

**Proprietary and Confidential.**  
Developed exclusively for **Karachi Gymkhana Club (KGC)**. Unauthorized distribution, reverse engineering, or reproduction of this codebase is strictly prohibited.
