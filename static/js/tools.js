/**
 * Hardware Diagnostic NOC Console - Real-Time Telemetry Engine
 * Features:
 * - 60 Hz Live ECG Heartbeat Oscilloscope
 * - Live MS Graph (Multi-Subsystem Latency Timeline with Bézier curves & crosshair HUD)
 * - Individual Node Sparklines, Jitter, Packet Drop & On-Demand Packet Probes
 * - Gate-01 & Main Gate (Club Road) Antenna Transponder Stream
 */

// Device Meta Definitions & Visual Palette
const DEVICE_CONFIG = {
    'Gate01_Entry': {
        name: 'Gate-01 Entry Reader',
        short: 'G01 Entry',
        color: '#06B6D4', // Cyan
        bg: 'rgba(6, 182, 212, 0.1)',
        border: 'rgba(6, 182, 212, 0.4)',
        type: 'RFID'
    },
    'Gate01_Exit': {
        name: 'Gate-01 Exit Reader',
        short: 'G01 Exit',
        color: '#38BDF8', // Sky
        bg: 'rgba(56, 189, 248, 0.1)',
        border: 'rgba(56, 189, 248, 0.4)',
        type: 'RFID'
    },
    'ClubRoad_Entry': {
        name: 'Club Road Entry Reader',
        short: 'Club Rd Entry',
        color: '#A855F7', // Purple
        bg: 'rgba(168, 85, 247, 0.1)',
        border: 'rgba(168, 85, 247, 0.4)',
        type: 'RFID'
    },
    'ClubRoad_Exit': {
        name: 'Club Road Exit Reader',
        short: 'Club Rd Exit',
        color: '#F59E0B', // Amber
        bg: 'rgba(245, 158, 11, 0.1)',
        border: 'rgba(245, 158, 11, 0.4)',
        type: 'RFID'
    },
    'Hikvision': {
        name: 'Hikvision AI Camera',
        short: 'Hikvision Cam',
        color: '#F43F5E', // Rose
        bg: 'rgba(244, 63, 94, 0.1)',
        border: 'rgba(244, 63, 94, 0.4)',
        type: 'CAMERA'
    },
    'Database': {
        name: 'SQLite Core Storage',
        short: 'SQLite Engine',
        color: '#10B981', // Emerald
        bg: 'rgba(16, 185, 129, 0.1)',
        border: 'rgba(16, 185, 129, 0.4)',
        type: 'DATABASE'
    }
};

// Global State
let pollIntervalMs = 2000;
let pollTimer = null;
let isStreamPaused = false;
let audioEnabled = false;
let audioCtx = null;

// Time-Series Graph Data (Max 45 points)
const MAX_GRAPH_POINTS = 45;
let timeLabels = [];
let seriesData = {
    'Gate01_Entry': [],
    'Gate01_Exit': [],
    'ClubRoad_Entry': [],
    'ClubRoad_Exit': [],
    'Hikvision': [],
    'Database': []
};
let seriesVisible = {
    'Gate01_Entry': true,
    'Gate01_Exit': true,
    'ClubRoad_Entry': true,
    'ClubRoad_Exit': true,
    'Hikvision': true,
    'Database': true
};

// Sparkline Cache per Device
let deviceSparklines = {};

// Hover Crosshair State
let mousePos = { x: -1, y: -1, active: false };

/* ==========================================================================
   1. Live ECG Heartbeat Oscilloscope (60 Hz Canvas)
   ========================================================================== */
let ecgCanvas, ecgCtx;
let ecgPoints = [];
let ecgScanX = 0;
let ecgAnimId = null;
let lastBeatTimestamp = 0;

function initECG() {
    ecgCanvas = document.getElementById('ecgCanvas');
    if (!ecgCanvas) return;
    ecgCtx = ecgCanvas.getContext('2d');

    resizeECG();
    window.addEventListener('resize', resizeECG);

    // Fill initial flat baseline
    const width = ecgCanvas.width;
    const midY = ecgCanvas.height / 2;
    for (let i = 0; i < width; i++) {
        ecgPoints[i] = midY;
    }

    animateECG();
}

function resizeECG() {
    if (!ecgCanvas) return;
    const rect = ecgCanvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    ecgCanvas.width = rect.width * dpr;
    ecgCanvas.height = rect.height * dpr;
    ecgCtx.scale(dpr, dpr);
}

function triggerECGBeat() {
    lastBeatTimestamp = performance.now();
    playHeartbeatSound();

    const badge = document.getElementById('ecgBeatBadge');
    if (badge) {
        badge.classList.remove('bg-emerald-500/20', 'text-emerald-300');
        badge.classList.add('bg-emerald-400', 'text-slate-950', 'scale-110');
        setTimeout(() => {
            badge.classList.remove('bg-emerald-400', 'text-slate-950', 'scale-110');
            badge.classList.add('bg-emerald-500/20', 'text-emerald-300');
        }, 150);
    }
}

function animateECG() {
    if (!ecgCanvas || !ecgCtx) return;

    const rect = ecgCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const midY = h / 2;

    // Advance scan head
    const speed = 2.4;
    ecgScanX = (ecgScanX + speed) % w;

    // Generate heartbeat pulse waveform
    const now = performance.now();
    const timeSinceBeat = (now - lastBeatTimestamp) / 1000; // seconds
    let newY = midY;

    if (timeSinceBeat >= 0 && timeSinceBeat <= 0.6) {
        const t = timeSinceBeat / 0.6; // normalized 0..1
        if (t < 0.15) {
            // P wave
            newY = midY - Math.sin((t / 0.15) * Math.PI) * 7;
        } else if (t < 0.25) {
            // Flat PR
            newY = midY;
        } else if (t < 0.32) {
            // Q dip
            newY = midY + 8;
        } else if (t < 0.42) {
            // R tall spike
            newY = midY - 38;
        } else if (t < 0.50) {
            // S dip
            newY = midY + 16;
        } else if (t < 0.75) {
            // T wave
            const tw = (t - 0.50) / 0.25;
            newY = midY - Math.sin(tw * Math.PI) * 12;
        }
    } else {
        // Minor natural baseline noise
        newY = midY + (Math.random() - 0.5) * 1.5;
    }

    const idx = Math.floor(ecgScanX);
    ecgPoints[idx] = newY;

    // Render Oscilloscope
    ecgCtx.clearRect(0, 0, w, h);

    // Draw Gridlines
    ecgCtx.strokeStyle = 'rgba(51, 65, 85, 0.25)';
    ecgCtx.lineWidth = 1;
    ecgCtx.beginPath();
    for (let x = 0; x < w; x += 30) {
        ecgCtx.moveTo(x, 0);
        ecgCtx.lineTo(x, h);
    }
    for (let y = 0; y < h; y += 20) {
        ecgCtx.moveTo(0, y);
        ecgCtx.lineTo(w, y);
    }
    ecgCtx.stroke();

    // Draw Glowing ECG Line
    ecgCtx.save();
    ecgCtx.strokeStyle = '#10B981';
    ecgCtx.lineWidth = 2;
    ecgCtx.shadowColor = '#10B981';
    ecgCtx.shadowBlur = 10;
    ecgCtx.beginPath();

    let started = false;
    for (let x = 0; x < w; x++) {
        // Skip current sweep head to give radar erase effect
        if (Math.abs(x - ecgScanX) < 14) continue;
        const py = ecgPoints[x] || midY;
        if (!started) {
            ecgCtx.moveTo(x, py);
            started = true;
        } else {
            ecgCtx.lineTo(x, py);
        }
    }
    ecgCtx.stroke();

    // Glowing Lead Dot
    ecgCtx.fillStyle = '#6EE7B7';
    ecgCtx.shadowBlur = 15;
    ecgCtx.shadowColor = '#6EE7B7';
    ecgCtx.beginPath();
    ecgCtx.arc(ecgScanX, newY, 3.5, 0, Math.PI * 2);
    ecgCtx.fill();
    ecgCtx.restore();

    ecgAnimId = requestAnimationFrame(animateECG);
}

/* ==========================================================================
   2. Web Audio Synthesizer (Heartbeat Sound Pulse)
   ========================================================================== */
function toggleAudioHeartbeat() {
    audioEnabled = !audioEnabled;
    const iconOff = document.getElementById('audioIconOff');
    const iconOn = document.getElementById('audioIconOn');
    if (audioEnabled) {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        if (iconOff) iconOff.classList.add('hidden');
        if (iconOn) iconOn.classList.remove('hidden');
    } else {
        if (iconOff) iconOff.classList.remove('hidden');
        if (iconOn) iconOn.classList.add('hidden');
    }
}

function playHeartbeatSound() {
    if (!audioEnabled || !audioCtx) return;
    try {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(650, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(180, audioCtx.currentTime + 0.05);

        gain.gain.setValueAtTime(0.04, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.06);

        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.07);
    } catch (e) {}
}

/* ==========================================================================
   3. Live MS Latency Graph (Canvas Time-Series)
   ========================================================================== */
let latCanvas, latCtx;

function initLatencyChart() {
    latCanvas = document.getElementById('latencyCanvas');
    if (!latCanvas) return;
    latCtx = latCanvas.getContext('2d');

    resizeLatencyChart();
    window.addEventListener('resize', resizeLatencyChart);

    // Mouse Interaction for Floating Crosshair
    latCanvas.addEventListener('mousemove', (e) => {
        const rect = latCanvas.getBoundingClientRect();
        mousePos.x = e.clientX - rect.left;
        mousePos.y = e.clientY - rect.top;
        mousePos.active = true;
        renderLatencyChart();
    });

    latCanvas.addEventListener('mouseleave', () => {
        mousePos.active = false;
        const tt = document.getElementById('chartTooltip');
        if (tt) tt.classList.add('hidden');
        renderLatencyChart();
    });

    buildLegendPills();
}

function resizeLatencyChart() {
    if (!latCanvas) return;
    const rect = latCanvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    latCanvas.width = rect.width * dpr;
    latCanvas.height = rect.height * dpr;
    latCtx.scale(dpr, dpr);
    renderLatencyChart();
}

function buildLegendPills() {
    const container = document.getElementById('graphLegend');
    if (!container) return;

    container.innerHTML = Object.keys(DEVICE_CONFIG).map(key => {
        const cfg = DEVICE_CONFIG[key];
        const isVis = seriesVisible[key];
        return `
        <button type="button" onclick="toggleSeries('${key}')" id="legendBtn_${key}"
                class="flex items-center gap-2 px-3 py-1.5 rounded-xl border transition text-xs font-bold ${isVis ? 'bg-slate-900 border-slate-700 text-white' : 'bg-slate-950/60 border-slate-800/80 text-slate-500 opacity-60'}">
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cfg.color};"></span>
            <span>${cfg.short}</span>
            <span id="legendVal_${key}" class="font-mono text-[11px] text-slate-400">-- ms</span>
        </button>`;
    }).join('');
}

function toggleSeries(key) {
    seriesVisible[key] = !seriesVisible[key];
    buildLegendPills();
    renderLatencyChart();
}

function renderLatencyChart() {
    if (!latCanvas || !latCtx) return;

    const rect = latCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    latCtx.clearRect(0, 0, w, h);

    const padLeft = 46;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 26;
    const chartW = w - padLeft - padRight;
    const chartH = h - padTop - padBottom;

    // 1. Calculate Dynamic Max Y in Milliseconds
    let maxVal = 30; // default minimum ceiling
    Object.keys(seriesData).forEach(key => {
        if (!seriesVisible[key]) return;
        seriesData[key].forEach(v => {
            if (v !== null && v !== undefined && v > maxVal) maxVal = v;
        });
    });
    // Round ceiling to neat step (e.g. 50, 100, 150)
    maxVal = Math.ceil((maxVal * 1.2) / 10) * 10;

    // 2. Draw Horizontal Gridlines & Y-Axis Labels
    latCtx.strokeStyle = 'rgba(51, 65, 85, 0.3)';
    latCtx.lineWidth = 1;
    latCtx.fillStyle = '#64748B';
    latCtx.font = '10px "JetBrains Mono", monospace';
    latCtx.textAlign = 'right';

    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
        const val = Math.round((maxVal / ySteps) * i);
        const y = padTop + chartH - (i / ySteps) * chartH;

        latCtx.beginPath();
        latCtx.moveTo(padLeft, y);
        latCtx.lineTo(w - padRight, y);
        latCtx.stroke();

        latCtx.fillText(`${val}ms`, padLeft - 8, y + 3);
    }

    // 3. Draw Vertical Gridlines & X Labels
    const numPoints = timeLabels.length;
    if (numPoints > 1) {
        const xStep = chartW / (numPoints - 1);
        latCtx.textAlign = 'center';
        for (let i = 0; i < numPoints; i += Math.max(1, Math.floor(numPoints / 5))) {
            const x = padLeft + i * xStep;
            latCtx.beginPath();
            latCtx.strokeStyle = 'rgba(51, 65, 85, 0.15)';
            latCtx.moveTo(x, padTop);
            latCtx.lineTo(x, padTop + chartH);
            latCtx.stroke();

            latCtx.fillText(timeLabels[i] || '', x, h - 8);
        }
    }

    if (numPoints < 2) {
        latCtx.fillStyle = '#64748B';
        latCtx.textAlign = 'center';
        latCtx.fillText('Gathering real-time telemetry packets...', w / 2, h / 2);
        return;
    }

    // 4. Render Curves for Each Active Subsystem
    const xStep = chartW / (numPoints - 1);

    Object.keys(seriesData).forEach(key => {
        if (!seriesVisible[key]) return;
        const pts = seriesData[key];
        const cfg = DEVICE_CONFIG[key];
        if (!pts || pts.length < 2) return;

        // Create Canvas Point Array
        const coords = [];
        for (let i = 0; i < pts.length; i++) {
            const v = pts[i];
            if (v === null || v === undefined) continue;
            const x = padLeft + i * xStep;
            const y = padTop + chartH - (v / maxVal) * chartH;
            coords.push({ x, y, v, idx: i });
        }

        if (coords.length < 2) return;

        // Draw Line with Glowing Stroke
        latCtx.save();
        latCtx.strokeStyle = cfg.color;
        latCtx.lineWidth = 2.2;
        latCtx.shadowColor = cfg.color;
        latCtx.shadowBlur = 8;
        latCtx.beginPath();

        latCtx.moveTo(coords[0].x, coords[0].y);
        for (let i = 1; i < coords.length; i++) {
            // Smooth Bézier curve interpolation
            const prev = coords[i - 1];
            const curr = coords[i];
            const cpx = (prev.x + curr.x) / 2;
            latCtx.bezierCurveTo(cpx, prev.y, cpx, curr.y, curr.x, curr.y);
        }
        latCtx.stroke();

        // Optional Semi-Transparent Gradient Fill Underneath
        latCtx.lineTo(coords[coords.length - 1].x, padTop + chartH);
        latCtx.lineTo(coords[0].x, padTop + chartH);
        latCtx.closePath();
        const grad = latCtx.createLinearGradient(0, padTop, 0, padTop + chartH);
        grad.addColorStop(0, cfg.color.replace(')', ', 0.12)').replace('rgb', 'rgba').replace('#', 'rgba('));
        // Fallback transparent fill
        latCtx.fillStyle = cfg.bg;
        latCtx.globalAlpha = 0.35;
        latCtx.fill();

        // Small indicator circle at the latest point
        const latest = coords[coords.length - 1];
        latCtx.globalAlpha = 1.0;
        latCtx.fillStyle = cfg.color;
        latCtx.beginPath();
        latCtx.arc(latest.x, latest.y, 3, 0, Math.PI * 2);
        latCtx.fill();
        latCtx.restore();
    });

    // 5. Render Interactive Mouse Crosshair Tracker
    if (mousePos.active && mousePos.x >= padLeft && mousePos.x <= w - padRight) {
        const hoverIdx = Math.round((mousePos.x - padLeft) / xStep);
        if (hoverIdx >= 0 && hoverIdx < numPoints) {
            const snapX = padLeft + hoverIdx * xStep;

            latCtx.save();
            latCtx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
            latCtx.setLineDash([4, 4]);
            latCtx.lineWidth = 1;
            latCtx.beginPath();
            latCtx.moveTo(snapX, padTop);
            latCtx.lineTo(snapX, padTop + chartH);
            latCtx.stroke();
            latCtx.restore();

            // Populate and position floating HTML tooltip
            updateChartTooltip(hoverIdx, snapX, mousePos.y);
        }
    }
}

function updateChartTooltip(idx, screenX, screenY) {
    const tooltip = document.getElementById('chartTooltip');
    const timeEl = document.getElementById('tooltipTime');
    const rowsEl = document.getElementById('tooltipRows');
    if (!tooltip || !timeEl || !rowsEl) return;

    timeEl.innerText = `Timestamp: ${timeLabels[idx] || '--'}`;

    let rowsHtml = '';
    Object.keys(seriesData).forEach(key => {
        if (!seriesVisible[key]) return;
        const cfg = DEVICE_CONFIG[key];
        const val = seriesData[key][idx];
        const displayVal = (val !== null && val !== undefined) ? `${val.toFixed(1)} ms` : 'Offline / No Packet';

        rowsHtml += `
        <div class="flex items-center justify-between gap-4">
            <span class="flex items-center gap-1.5 font-bold" style="color: ${cfg.color};">
                <span class="w-2 h-2 rounded-full" style="background-color: ${cfg.color};"></span>
                <span>${cfg.short}:</span>
            </span>
            <span class="font-mono font-bold text-white">${displayVal}</span>
        </div>`;
    });

    rowsEl.innerHTML = rowsHtml;
    tooltip.classList.remove('hidden');

    // Bounds checking inside canvas viewport
    const ttWidth = 190;
    let leftPos = screenX + 15;
    if (leftPos + ttWidth > latCanvas.parentElement.clientWidth) {
        leftPos = screenX - ttWidth - 15;
    }
    tooltip.style.left = `${Math.max(10, leftPos)}px`;
    tooltip.style.top = `${Math.max(10, Math.min(screenY - 20, 160))}px`;
}

/* ==========================================================================
   4. Telemetry Polling Engine & HUD Updaters
   ========================================================================== */
async function fetchTelemetry() {
    if (isStreamPaused) return;

    try {
        const res = await fetch('/api/tools/telemetry?synthetic=true');
        if (!res.ok) return;
        const data = await res.json();

        // 1. Sync Heartbeat Oscilloscope
        triggerECGBeat();

        const ts = data.timestamp || new Date().toTimeString().split(' ')[0];
        document.getElementById('ecgTimeDisplay').innerText = ts;
        document.getElementById('lastSyncTime').innerText = `Updated: ${ts}`;

        // 2. Update Top Vitals
        const cluster = data.cluster || {};
        const avgRtt = cluster.avg_latency_ms || 0;
        document.getElementById('topClusterLatency').innerText = `${avgRtt.toFixed(1)} ms`;
        document.getElementById('statAvgLatency').innerText = `${avgRtt.toFixed(1)} ms`;
        document.getElementById('statNodes').innerText = `${cluster.active_nodes || 0} / ${cluster.total_nodes || 6}`;

        const statusEl = document.getElementById('clusterStatusText');
        const subTextEl = document.getElementById('clusterSubText');
        if (cluster.status === 'OPTIMAL') {
            statusEl.innerText = 'All Subsystems Operational';
            statusEl.className = 'text-2xl font-black text-white';
            subTextEl.innerText = 'Multi-gate RFID antennas, AI cameras, and storage engines synchronizing with zero packet drop.';
        } else if (cluster.status === 'DEGRADED') {
            statusEl.innerText = 'Partial Telemetry Alert';
            statusEl.className = 'text-2xl font-black text-amber-400';
            subTextEl.innerText = `${cluster.total_nodes - cluster.active_nodes} hardware node(s) unreachable or unconfigured. Verify LAN IP addresses.`;
        } else {
            statusEl.innerText = 'Hardware Nodes Offline';
            statusEl.className = 'text-2xl font-black text-rose-500';
            subTextEl.innerText = 'Zero hardware responses received. Check LAN switches and antenna controllers.';
        }

        // Calculate average cluster jitter across devices
        const devices = data.devices || {};
        let jitterSum = 0;
        let jitterCount = 0;
        Object.values(devices).forEach(d => {
            if (d.stats && d.stats.jitter_ms !== undefined) {
                jitterSum += d.stats.jitter_ms;
                jitterCount++;
            }
        });
        const clusterJitter = jitterCount ? (jitterSum / jitterCount).toFixed(1) : '0.0';
        document.getElementById('statJitter').innerText = `\u00B1 ${clusterJitter} ms`;

        // 3. Append to Graph Series
        timeLabels.push(ts);
        if (timeLabels.length > MAX_GRAPH_POINTS) timeLabels.shift();

        Object.keys(seriesData).forEach(key => {
            const dev = devices[key];
            const lat = (dev && dev.latency_ms !== null && dev.latency_ms !== undefined) ? dev.latency_ms : null;
            seriesData[key].push(lat);
            if (seriesData[key].length > MAX_GRAPH_POINTS) seriesData[key].shift();

            // Update legend ms badges
            const legEl = document.getElementById(`legendVal_${key}`);
            if (legEl) {
                legEl.innerText = lat !== null ? `${lat.toFixed(1)} ms` : 'OFFLINE';
                legEl.className = `font-mono text-[11px] font-bold ${lat !== null ? 'text-white' : 'text-rose-500'}`;
            }
        });

        // Re-render Graph
        renderLatencyChart();

        // 4. Render Hardware Node Cards
        renderDeviceCards(devices);

        // 5. Render Live Tag Stream
        renderRecentTags(data.recent_tags);

    } catch (err) {
        console.error('Telemetry query error:', err);
    }
}

/* ==========================================================================
   5. Device Telemetry Cards & Sparklines
   ========================================================================== */
function renderDeviceCards(devices) {
    const grid = document.getElementById('devicesGrid');
    if (!grid) return;

    grid.innerHTML = Object.keys(devices).map(key => {
        const d = devices[key];
        const cfg = DEVICE_CONFIG[key] || { name: key, color: '#38BDF8', bg: 'rgba(56,189,248,0.1)' };
        const isOnline = d.status === 'CONNECTED' || d.status === 'ONLINE';
        const isUnconf = d.status === 'UNCONFIGURED';

        // Badge styling
        const statusBadgeClass = isOnline
            ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
            : isUnconf
                ? 'bg-slate-900 text-slate-400 border-slate-800'
                : 'bg-rose-950/80 text-rose-300 border-rose-800';

        // Latency color
        const lat = d.latency_ms;
        const latColor = !isOnline
            ? 'text-slate-500'
            : lat < 25
                ? 'text-emerald-400'
                : lat < 70
                    ? 'text-amber-400'
                    : 'text-rose-400';

        const latText = lat !== null && lat !== undefined ? lat.toFixed(1) : '--';
        const stats = d.stats || {};
        const minMs = stats.min_ms !== undefined && stats.min_ms !== null ? `${stats.min_ms}ms` : '--';
        const avgMs = stats.avg_ms !== undefined && stats.avg_ms !== null ? `${stats.avg_ms}ms` : '--';
        const maxMs = stats.max_ms !== undefined && stats.max_ms !== null ? `${stats.max_ms}ms` : '--';
        const jitterMs = stats.jitter_ms !== undefined ? `\u00B1${stats.jitter_ms}ms` : '--';
        const lossPct = stats.loss_pct !== undefined ? `${stats.loss_pct}%` : '0.0%';

        return `
        <div id="card_${key}" class="glass-panel rounded-2xl p-5 border-slate-800 hover:border-slate-700 transition relative overflow-hidden flex flex-col justify-between group">
            <div>
                <!-- Top Device Header -->
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div>
                        <div class="flex items-center gap-2 mb-0.5">
                            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cfg.color};"></span>
                            <span class="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">${d.role || cfg.type}</span>
                        </div>
                        <h3 class="text-sm font-extrabold text-white truncate" title="${d.label}">${d.label}</h3>
                    </div>
                    <span class="text-[10px] font-mono font-extrabold px-2.5 py-1 rounded-full border ${statusBadgeClass}">
                        ${d.status}
                    </span>
                </div>

                <!-- Big MS Readout & Sparkline -->
                <div class="flex items-baseline justify-between my-2">
                    <div class="flex items-baseline gap-1">
                        <span class="text-3xl font-black font-mono ${latColor}">${latText}</span>
                        <span class="text-xs font-mono font-bold text-slate-500">ms</span>
                    </div>
                    <div class="w-28 h-8 rounded-lg overflow-hidden bg-slate-950/80 border border-slate-800/80">
                        <canvas id="spark_${key}" class="w-full h-full block"></canvas>
                    </div>
                </div>

                <!-- Technical Specs & Network Metrics Grid -->
                <div class="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-800/80 text-[11px] font-mono">
                    <div>
                        <span class="text-slate-500 block text-[9px] uppercase tracking-wider">Min / Max</span>
                        <span class="text-slate-300 font-bold">${minMs} / ${maxMs}</span>
                    </div>
                    <div>
                        <span class="text-slate-500 block text-[9px] uppercase tracking-wider">Jitter</span>
                        <span class="text-slate-300 font-bold">${jitterMs}</span>
                    </div>
                    <div>
                        <span class="text-slate-500 block text-[9px] uppercase tracking-wider">Drop Rate</span>
                        <span class="text-emerald-400 font-bold">${lossPct}</span>
                    </div>
                </div>

                <!-- IP Address & Protocol -->
                <div class="mt-3 bg-slate-950/60 rounded-xl p-2.5 border border-slate-800/80 text-[10px] font-mono text-slate-400 flex items-center justify-between">
                    <span class="truncate" title="${d.ip}:${d.port}">📍 ${d.ip}:${d.port}</span>
                    <span class="text-slate-500">${d.protocol}</span>
                </div>
            </div>

            <!-- Single Node Ping Action Button -->
            <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between">
                <span id="pingResult_${key}" class="text-[10px] font-mono text-slate-500">Ready for probe</span>
                <button type="button" onclick="pingDevice('${key}', this)"
                        class="text-[11px] font-bold px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-white transition flex items-center gap-1.5 shadow">
                    <span>Ping Node</span>
                </button>
            </div>
        </div>`;
    }).join('');

    // Render individual sparklines for each device
    Object.keys(devices).forEach(key => {
        drawSparkline(key, devices[key].history || []);
    });
}

function drawSparkline(key, history) {
    const canvas = document.getElementById(`spark_${key}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.parentElement.clientWidth;
    const h = canvas.parentElement.clientHeight;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, w, h);
    if (!history || history.length < 2) return;

    const valid = history.filter(v => v !== null && v !== undefined);
    if (valid.length < 2) return;

    const maxVal = Math.max(...valid, 20);
    const step = w / (history.length - 1);
    const cfg = DEVICE_CONFIG[key] || { color: '#38BDF8' };

    ctx.strokeStyle = cfg.color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();

    let started = false;
    for (let i = 0; i < history.length; i++) {
        const v = history[i];
        if (v === null || v === undefined) continue;
        const x = i * step;
        const y = h - (v / maxVal) * (h - 4) - 2;
        if (!started) {
            ctx.moveTo(x, y);
            started = true;
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.stroke();
}

/* ==========================================================================
   6. Interactive Actions: On-Demand Ping, Frame Capture, Intervals
   ========================================================================== */
async function pingDevice(deviceId, btn) {
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Probing...';
        btn.disabled = true;
    }

    const resEl = document.getElementById(`pingResult_${deviceId}`);
    const cardEl = document.getElementById(`card_${deviceId}`);

    if (resEl) resEl.innerText = 'Transmitting packet...';
    if (cardEl) cardEl.classList.add('ring-2', 'ring-cyan-500');

    try {
        const res = await fetch(`/api/tools/ping/${deviceId}`, { method: 'POST' });
        const data = await res.json();
        const r = data.result || {};

        if (cardEl) {
            cardEl.classList.remove('ring-cyan-500');
            cardEl.classList.add('ring-2', 'ring-emerald-500');
            setTimeout(() => cardEl.classList.remove('ring-2', 'ring-emerald-500'), 1000);
        }

        if (resEl) {
            if (r.latency_ms !== null && r.latency_ms !== undefined) {
                resEl.innerText = `RTT: ${r.latency_ms.toFixed(1)} ms (${r.status})`;
                resEl.className = 'text-[10px] font-mono font-bold text-emerald-400';
            } else {
                resEl.innerText = `Probe timeout (${r.status})`;
                resEl.className = 'text-[10px] font-mono font-bold text-rose-400';
            }
        }
    } catch (e) {
        if (resEl) resEl.innerText = 'Probe network error';
    } finally {
        if (btn) {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }
}

async function probeAllDevicesNow(btn) {
    const orig = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Probing Cluster...';
        btn.disabled = true;
    }
    await fetchTelemetry();
    if (btn) {
        btn.innerHTML = orig;
        btn.disabled = false;
    }
}

async function resetTelemetryData() {
    if (!confirm('Reset rolling latency time-series and telemetry buffers?')) return;
    try {
        await fetch('/api/tools/telemetry/reset', { method: 'POST' });
        timeLabels = [];
        Object.keys(seriesData).forEach(k => seriesData[k] = []);
        renderLatencyChart();
        fetchTelemetry();
    } catch (e) {
        alert('Reset error: ' + e.message);
    }
}

function setPollInterval(ms) {
    pollIntervalMs = ms;
    ['rateBtn1', 'rateBtn2', 'rateBtn5'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.className = 'px-2.5 py-1 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition';
        }
    });

    const activeId = ms === 1000 ? 'rateBtn1' : ms === 2000 ? 'rateBtn2' : 'rateBtn5';
    const activeEl = document.getElementById(activeId);
    if (activeEl) {
        activeEl.className = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-600 text-white shadow';
    }

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(fetchTelemetry, pollIntervalMs);
}

function togglePauseStream() {
    isStreamPaused = !isStreamPaused;
    const btn = document.getElementById('pauseResumeBtn');
    if (btn) {
        if (isStreamPaused) {
            btn.innerText = 'Resume Stream';
            btn.className = 'text-xs font-bold px-3 py-1.5 rounded-xl border border-amber-600 bg-amber-950/60 text-amber-300';
        } else {
            btn.innerText = 'Pause Stream';
            btn.className = 'text-xs font-bold px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 transition';
            fetchTelemetry();
        }
    }
}

/* ==========================================================================
   7. RFID Antenna Tag Stream & Camera Viewport
   ========================================================================== */
function renderRecentTags(tags) {
    const countBadge = document.getElementById('rfidCountBadge');
    const container = document.getElementById('rfidFeedContainer');
    if (!tags || !tags.length) return;

    if (countBadge) countBadge.innerText = `${tags.length} tags captured`;
    if (!container) return;

    container.innerHTML = tags.slice().reverse().map(t => {
        const isEntry = t.direction === 'Entry';
        const dirBadge = isEntry
            ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
            : 'bg-amber-950/80 text-amber-300 border-amber-800';

        const gateName = t.gate || 'Gate-01';

        return `
        <div class="flex items-center justify-between bg-slate-900/80 border border-slate-800/80 rounded-xl px-4 py-2.5 hover:border-slate-700 transition">
            <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full ${isEntry ? 'bg-emerald-400' : 'bg-amber-400'} animate-ping"></span>
                <span class="font-mono text-xs font-bold text-slate-200">${t.tag}</span>
            </div>
            <div class="flex items-center gap-2.5">
                <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">${gateName}</span>
                <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${dirBadge}">${t.direction}</span>
                <span class="text-[10px] text-slate-500 font-mono">${t.time || ''}</span>
            </div>
        </div>`;
    }).join('');
}

async function captureFrame(cam, btn) {
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Capturing...';
        btn.disabled = true;
    }

    try {
        const t0 = performance.now();
        const res = await fetch('/api/tools/capture/' + cam, { method: 'POST' });
        const latency = Math.round(performance.now() - t0);
        const data = await res.json();

        if (!res.ok) {
            alert(`Frame capture error: ${data.detail || 'Service error'}`);
            return;
        }

        const imgEl = document.getElementById('snapHik');
        const placeEl = document.getElementById('snapPlaceholder');
        const metaEl = document.getElementById('hikMeta');

        if (imgEl) {
            imgEl.src = '/' + data.path + '?t=' + Date.now();
            imgEl.classList.remove('hidden');
        }
        if (placeEl) placeEl.classList.add('hidden');
        if (metaEl) metaEl.innerText = `${data.width} \u00D7 ${data.height} px (${latency}ms)`;

    } catch (err) {
        alert('Network error during frame grab: ' + err.message);
    } finally {
        if (btn) {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }
}

/* ==========================================================================
   8. Bootloader
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    initECG();
    initLatencyChart();
    fetchTelemetry();
    pollTimer = setInterval(fetchTelemetry, pollIntervalMs);
});
