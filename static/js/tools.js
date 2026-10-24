/**
 * Hardware Diagnostic NOC Console - Real-Time Telemetry Engine (Light Mode Theme)
 * Features:
 * - 60 Hz Live ECG Heartbeat Oscilloscope (Logo Blue pulse on crisp light grid)
 * - Live MS Graph (Multi-Subsystem Latency Timeline with Bézier curves & crosshair HUD)
 * - Individual Node Sparklines, Jitter, Packet Drop & On-Demand Packet Probes
 * - Gate-01 & Main Gate (Club Road) Antenna Transponder Stream
 */

// Device Meta Definitions & Visual Palette (Light Theme High-Contrast)
const DEVICE_CONFIG = {
    'Gate01_Entry': {
        name: 'Gate-01 Entry Reader',
        short: 'G01 Entry',
        color: '#2563EB', // Logo Royal Blue
        bg: 'rgba(37, 99, 235, 0.08)',
        border: 'rgba(37, 99, 235, 0.4)',
        type: 'RFID'
    },
    'Gate01_Exit': {
        name: 'Gate-01 Exit Reader',
        short: 'G01 Exit',
        color: '#0284C7', // Sky Blue
        bg: 'rgba(2, 132, 199, 0.08)',
        border: 'rgba(2, 132, 199, 0.4)',
        type: 'RFID'
    },
    'ClubRoad_Entry': {
        name: 'Club Road Entry Reader',
        short: 'Club Rd Entry',
        color: '#7C3AED', // Purple
        bg: 'rgba(124, 58, 237, 0.08)',
        border: 'rgba(124, 58, 237, 0.4)',
        type: 'RFID'
    },
    'ClubRoad_Exit': {
        name: 'Club Road Exit Reader',
        short: 'Club Rd Exit',
        color: '#D97706', // Amber
        bg: 'rgba(217, 119, 6, 0.08)',
        border: 'rgba(217, 119, 6, 0.4)',
        type: 'RFID'
    },
    'Hikvision': {
        name: 'Hikvision AI Camera',
        short: 'Hikvision Cam',
        color: '#DC2626', // Red
        bg: 'rgba(220, 38, 38, 0.08)',
        border: 'rgba(220, 38, 38, 0.4)',
        type: 'CAMERA'
    },
    'Database': {
        name: 'Database Engine',
        short: 'PostgreSQL Engine',
        color: '#059669', // Emerald
        bg: 'rgba(5, 150, 105, 0.08)',
        border: 'rgba(5, 150, 105, 0.4)',
        type: 'DATABASE'
    }
};

// Global State
let pollIntervalMs = 2000;
let pollTimer = null;
let isStreamPaused = false;
let audioEnabled = false;
let audioCtx = null;
let useSyntheticMode = false;

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

// Hover Crosshair State
let mousePos = { x: -1, y: -1, active: false };

/* ==========================================================================
   1. Live ECG Heartbeat Oscilloscope (60 Hz Canvas Light Mode)
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
        badge.classList.remove('bg-blue-50', 'text-blue-700');
        badge.classList.add('bg-blue-600', 'text-white', 'scale-105');
        setTimeout(() => {
            badge.classList.remove('bg-blue-600', 'text-white', 'scale-105');
            badge.classList.add('bg-blue-50', 'text-blue-700');
        }, 150);
    }
}

function animateECG() {
    if (!ecgCanvas || !ecgCtx) return;

    const rect = ecgCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const midY = h / 2;

    const speed = 2.4;
    ecgScanX = (ecgScanX + speed) % w;

    const now = performance.now();
    const timeSinceBeat = (now - lastBeatTimestamp) / 1000;
    let newY = midY;

    if (timeSinceBeat >= 0 && timeSinceBeat <= 0.6) {
        const t = timeSinceBeat / 0.6;
        if (t < 0.15) {
            newY = midY - Math.sin((t / 0.15) * Math.PI) * 7;
        } else if (t < 0.25) {
            newY = midY;
        } else if (t < 0.32) {
            newY = midY + 8;
        } else if (t < 0.42) {
            newY = midY - 38;
        } else if (t < 0.50) {
            newY = midY + 16;
        } else if (t < 0.75) {
            const tw = (t - 0.50) / 0.25;
            newY = midY - Math.sin(tw * Math.PI) * 12;
        }
    } else {
        newY = midY + (Math.random() - 0.5) * 1.5;
    }

    const idx = Math.floor(ecgScanX);
    ecgPoints[idx] = newY;

    ecgCtx.clearRect(0, 0, w, h);

    // Light Theme Gridlines
    ecgCtx.strokeStyle = 'rgba(226, 232, 240, 0.85)';
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

    // Glowing Logo Blue ECG Line
    ecgCtx.save();
    ecgCtx.strokeStyle = '#2563EB'; // Logo Blue
    ecgCtx.lineWidth = 2.2;
    ecgCtx.shadowColor = 'rgba(37, 99, 235, 0.35)';
    ecgCtx.shadowBlur = 6;
    ecgCtx.beginPath();

    let started = false;
    for (let x = 0; x < w; x++) {
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

    // Lead Pulse Dot
    ecgCtx.fillStyle = '#1D4ED8';
    ecgCtx.shadowBlur = 8;
    ecgCtx.shadowColor = '#2563EB';
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
   3. Live MS Latency Graph (Canvas Time-Series in Light Mode)
   ========================================================================== */
let latCanvas, latCtx;

function initLatencyChart() {
    latCanvas = document.getElementById('latencyCanvas');
    if (!latCanvas) return;
    latCtx = latCanvas.getContext('2d');

    resizeLatencyChart();
    window.addEventListener('resize', resizeLatencyChart);

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
                class="flex items-center gap-2 px-3 py-1.5 rounded-xl border transition text-xs font-bold ${isVis ? 'bg-white border-slate-300 text-slate-800 shadow-2xs' : 'bg-slate-100 border-slate-200 text-slate-400 opacity-60'}">
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cfg.color};"></span>
            <span>${cfg.short}</span>
            <span id="legendVal_${key}" class="font-mono text-[11px] text-slate-500">-- ms</span>
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

    const padLeft = 48;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 26;
    const chartW = w - padLeft - padRight;
    const chartH = h - padTop - padBottom;

    let maxVal = 30;
    Object.keys(seriesData).forEach(key => {
        if (!seriesVisible[key]) return;
        seriesData[key].forEach(v => {
            if (v !== null && v !== undefined && v > maxVal) maxVal = v;
        });
    });
    maxVal = Math.ceil((maxVal * 1.2) / 10) * 10;

    // Light Theme Gridlines & Y-Axis Labels
    latCtx.strokeStyle = 'rgba(226, 232, 240, 0.9)';
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

    const numPoints = timeLabels.length;
    if (numPoints > 1) {
        const xStep = chartW / (numPoints - 1);
        latCtx.textAlign = 'center';
        for (let i = 0; i < numPoints; i += Math.max(1, Math.floor(numPoints / 5))) {
            const x = padLeft + i * xStep;
            latCtx.beginPath();
            latCtx.strokeStyle = 'rgba(226, 232, 240, 0.7)';
            latCtx.moveTo(x, padTop);
            latCtx.lineTo(x, padTop + chartH);
            latCtx.stroke();

            latCtx.fillText(timeLabels[i] || '', x, h - 8);
        }
    }

    if (numPoints < 2) {
        latCtx.fillStyle = '#94A3B8';
        latCtx.textAlign = 'center';
        latCtx.fillText('Gathering real-time telemetry packets...', w / 2, h / 2);
        return;
    }

    const xStep = chartW / (numPoints - 1);

    Object.keys(seriesData).forEach(key => {
        if (!seriesVisible[key]) return;
        const pts = seriesData[key];
        const cfg = DEVICE_CONFIG[key];
        if (!pts || pts.length < 2) return;

        const coords = [];
        for (let i = 0; i < pts.length; i++) {
            const v = pts[i];
            if (v === null || v === undefined) continue;
            const x = padLeft + i * xStep;
            const y = padTop + chartH - (v / maxVal) * chartH;
            coords.push({ x, y, v, idx: i });
        }

        if (coords.length < 2) return;

        latCtx.save();
        latCtx.strokeStyle = cfg.color;
        latCtx.lineWidth = 2.2;
        latCtx.beginPath();

        latCtx.moveTo(coords[0].x, coords[0].y);
        for (let i = 1; i < coords.length; i++) {
            const prev = coords[i - 1];
            const curr = coords[i];
            const cpx = (prev.x + curr.x) / 2;
            latCtx.bezierCurveTo(cpx, prev.y, cpx, curr.y, curr.x, curr.y);
        }
        latCtx.stroke();

        latCtx.lineTo(coords[coords.length - 1].x, padTop + chartH);
        latCtx.lineTo(coords[0].x, padTop + chartH);
        latCtx.closePath();
        latCtx.fillStyle = cfg.bg;
        latCtx.fill();

        const latest = coords[coords.length - 1];
        latCtx.fillStyle = cfg.color;
        latCtx.beginPath();
        latCtx.arc(latest.x, latest.y, 3, 0, Math.PI * 2);
        latCtx.fill();
        latCtx.restore();
    });

    if (mousePos.active && mousePos.x >= padLeft && mousePos.x <= w - padRight) {
        const hoverIdx = Math.round((mousePos.x - padLeft) / xStep);
        if (hoverIdx >= 0 && hoverIdx < numPoints) {
            const snapX = padLeft + hoverIdx * xStep;

            latCtx.save();
            latCtx.strokeStyle = 'rgba(15, 23, 42, 0.4)';
            latCtx.setLineDash([4, 4]);
            latCtx.lineWidth = 1;
            latCtx.beginPath();
            latCtx.moveTo(snapX, padTop);
            latCtx.lineTo(snapX, padTop + chartH);
            latCtx.stroke();
            latCtx.restore();

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
            <span class="font-mono font-bold text-slate-900">${displayVal}</span>
        </div>`;
    });

    rowsEl.innerHTML = rowsHtml;
    tooltip.classList.remove('hidden');

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
        const res = await fetch(`/api/tools/telemetry?synthetic=${useSyntheticMode}`);
        if (!res.ok) return;
        const data = await res.json();

        triggerECGBeat();

        const ts = data.timestamp || new Date().toTimeString().split(' ')[0];
        document.getElementById('ecgTimeDisplay').innerText = ts;
        document.getElementById('lastSyncTime').innerText = `Updated: ${ts}`;

        const cluster = data.cluster || {};
        const avgRtt = cluster.avg_latency_ms || 0;
        document.getElementById('topClusterLatency').innerText = `${avgRtt.toFixed(1)} ms`;
        document.getElementById('statAvgLatency').innerText = `${avgRtt.toFixed(1)} ms`;
        document.getElementById('statNodes').innerText = `${cluster.active_nodes || 0} / ${cluster.total_nodes || 6}`;

        const statusEl = document.getElementById('clusterStatusText');
        const subTextEl = document.getElementById('clusterSubText');
        if (cluster.status === 'OPTIMAL') {
            statusEl.innerText = 'All Subsystems Operational';
            statusEl.className = 'text-2xl font-black text-slate-900';
            subTextEl.innerText = 'Multi-gate RFID antennas, AI cameras, and storage engines synchronizing with zero packet drop.';
        } else if (cluster.status === 'DEGRADED') {
            statusEl.innerText = 'Partial Telemetry Alert';
            statusEl.className = 'text-2xl font-black text-amber-600';
            subTextEl.innerText = `${cluster.total_nodes - cluster.active_nodes} hardware node(s) unreachable or unconfigured. Verify LAN IP addresses.`;
        } else {
            statusEl.innerText = 'Hardware Nodes Offline';
            statusEl.className = 'text-2xl font-black text-rose-600';
            subTextEl.innerText = 'Zero hardware responses received. Check LAN switches and antenna controllers.';
        }

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

        timeLabels.push(ts);
        if (timeLabels.length > MAX_GRAPH_POINTS) timeLabels.shift();

        Object.keys(seriesData).forEach(key => {
            const dev = devices[key];
            const lat = (dev && dev.latency_ms !== null && dev.latency_ms !== undefined) ? dev.latency_ms : null;
            seriesData[key].push(lat);
            if (seriesData[key].length > MAX_GRAPH_POINTS) seriesData[key].shift();

            const legEl = document.getElementById(`legendVal_${key}`);
            if (legEl) {
                legEl.innerText = lat !== null ? `${lat.toFixed(1)} ms` : 'OFFLINE';
                legEl.className = `font-mono text-[11px] font-bold ${lat !== null ? 'text-slate-800' : 'text-rose-500'}`;
            }
        });

        renderLatencyChart();
        renderDeviceCards(devices);
        renderRecentTags(data.recent_tags);

    } catch (err) {
        console.error('Telemetry query error:', err);
    }
}

/* ==========================================================================
   5. Device Telemetry Cards & Sparklines (Light Theme)
   ========================================================================== */
function renderDeviceCards(devices) {
    const grid = document.getElementById('devicesGrid');
    if (!grid) return;

    grid.innerHTML = Object.keys(devices).map(key => {
        const d = devices[key];
        const cfg = DEVICE_CONFIG[key] || { name: key, color: '#2563EB', bg: 'rgba(37,99,235,0.08)' };
        const isOnline = d.status === 'CONNECTED' || d.status === 'ONLINE';
        const isUnconf = d.status === 'UNCONFIGURED';

        const statusBadgeClass = isOnline
            ? 'bg-blue-50 text-blue-700 border-blue-200'
            : isUnconf
                ? 'bg-slate-100 text-slate-500 border-slate-200'
                : 'bg-rose-50 text-rose-700 border-rose-200';

        const lat = d.latency_ms;
        const latColor = !isOnline
            ? 'text-slate-400'
            : lat < 25
                ? 'text-blue-700'
                : lat < 70
                    ? 'text-amber-600'
                    : 'text-rose-600';

        const latText = lat !== null && lat !== undefined ? lat.toFixed(1) : '--';
        const stats = d.stats || {};
        const minMs = stats.min_ms !== undefined && stats.min_ms !== null ? `${stats.min_ms}ms` : '--';
        const avgMs = stats.avg_ms !== undefined && stats.avg_ms !== null ? `${stats.avg_ms}ms` : '--';
        const maxMs = stats.max_ms !== undefined && stats.max_ms !== null ? `${stats.max_ms}ms` : '--';
        const jitterMs = stats.jitter_ms !== undefined ? `\u00B1${stats.jitter_ms}ms` : '--';
        const lossPct = stats.loss_pct !== undefined ? `${stats.loss_pct}%` : '0.0%';

        return `
        <div id="card_${key}" class="glass-panel rounded-2xl p-5 border border-slate-200 hover:border-slate-300 shadow-xs hover:shadow-sm transition relative overflow-hidden flex flex-col justify-between group">
            <div>
                <!-- Top Device Header -->
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div>
                        <div class="flex items-center gap-2 mb-0.5">
                            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cfg.color};"></span>
                            <span class="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">${d.role || cfg.type}</span>
                        </div>
                        <h3 class="text-sm font-extrabold text-slate-900 truncate" title="${d.label}">${d.label}</h3>
                    </div>
                    <span class="text-[10px] font-mono font-extrabold px-2.5 py-1 rounded-full border ${statusBadgeClass}">
                        ${d.status}
                    </span>
                </div>

                <!-- Big MS Readout & Sparkline -->
                <div class="flex items-baseline justify-between my-2">
                    <div class="flex items-baseline gap-1">
                        <span class="text-3xl font-black font-mono ${latColor}">${latText}</span>
                        <span class="text-xs font-mono font-bold text-slate-400">ms</span>
                    </div>
                    <div class="w-28 h-8 rounded-lg overflow-hidden bg-slate-50 border border-slate-200 shadow-inner">
                        <canvas id="spark_${key}" class="w-full h-full block"></canvas>
                    </div>
                </div>

                <!-- Technical Specs & Network Metrics Grid -->
                <div class="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-100 text-[11px] font-mono">
                    <div>
                        <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Min / Max</span>
                        <span class="text-slate-700 font-bold">${minMs} / ${maxMs}</span>
                    </div>
                    <div>
                        <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Jitter</span>
                        <span class="text-slate-700 font-bold">${jitterMs}</span>
                    </div>
                    <div>
                        <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Drop Rate</span>
                        <span class="text-blue-700 font-bold">${lossPct}</span>
                    </div>
                </div>

                <!-- IP Address & Protocol -->
                <div class="mt-3 bg-slate-50 rounded-xl p-2.5 border border-slate-200 text-[10px] font-mono text-slate-600 flex items-center justify-between">
                    <span class="truncate" title="${d.ip}:${d.port}">📍 ${d.ip}:${d.port}</span>
                    <span class="text-slate-400 font-semibold">${d.protocol}</span>
                </div>

                ${d.last_error ? `
                <div class="mt-2.5 bg-rose-50 border border-rose-200 text-rose-800 text-[10px] font-mono p-2.5 rounded-xl flex items-start gap-2 break-all">
                    <span class="text-rose-500 font-bold shrink-0 mt-0.5">⚠️</span>
                    <div class="flex-1">
                        <div class="font-bold text-rose-900">${d.last_error}</div>
                        ${d.reconnects ? `<div class="text-[9px] text-rose-600 font-medium mt-0.5">Reconnect attempts: ${d.reconnects}</div>` : ''}
                    </div>
                </div>` : ''}
            </div>

            <!-- Single Node Ping Action Button & Socket Re-sync -->
            <div class="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2">
                <span id="pingResult_${key}" class="text-[10px] font-mono text-slate-400 truncate max-w-[130px]">Ready for probe</span>
                <div class="flex items-center gap-1.5 shrink-0">
                    ${key.includes('Gate') || key.includes('ClubRoad') ? `
                    <button type="button" onclick="diagnoseReader('${key}', this)" title="Run Deep Diagnostic Audit (Ping, MAC check, Port scan, Conflict detector)"
                            class="text-[11px] font-bold px-2.5 py-1.5 rounded-lg border border-purple-200 bg-purple-50 hover:bg-purple-100 text-purple-700 transition flex items-center gap-1 shadow-2xs">
                        <span>🔍 Diagnose</span>
                    </button>
                    <button type="button" onclick="reconnectReaderSocket('${key}', this)" title="Cycle TCP Socket & Reconnect"
                            class="text-[11px] font-bold px-2 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 transition flex items-center gap-1 shadow-2xs">
                        <span>Re-sync</span>
                    </button>
                    ` : ''}
                    <button type="button" onclick="pingDevice('${key}', this)"
                            class="text-[11px] font-bold px-2.5 py-1.5 rounded-lg border border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-700 transition flex items-center gap-1 shadow-2xs">
                        <span>Ping</span>
                    </button>
                </div>
            </div>
        </div>`;
    }).join('');

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
    const cfg = DEVICE_CONFIG[key] || { color: '#2563EB' };

    ctx.strokeStyle = cfg.color;
    ctx.lineWidth = 1.8;
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
    if (cardEl) cardEl.classList.add('ring-2', 'ring-blue-400');

    try {
        const res = await fetch(`/api/tools/ping/${deviceId}?synthetic=${useSyntheticMode}`, { method: 'POST' });
        const data = await res.json();
        const r = data.result || {};

        if (cardEl) {
            cardEl.classList.remove('ring-blue-400');
            cardEl.classList.add('ring-2', 'ring-blue-600');
            setTimeout(() => cardEl.classList.remove('ring-2', 'ring-blue-600'), 1000);
        }

        if (resEl) {
            if (r.latency_ms !== null && r.latency_ms !== undefined) {
                resEl.innerText = `RTT: ${r.latency_ms.toFixed(1)} ms (${r.status})`;
                resEl.className = 'text-[10px] font-mono font-bold text-blue-700';
            } else {
                resEl.innerText = `Probe timeout (${r.status})`;
                resEl.className = 'text-[10px] font-mono font-bold text-rose-600';
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

async function reconnectReaderSocket(readerId, btn) {
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Cycling...';
        btn.disabled = true;
    }
    const resEl = document.getElementById(`pingResult_${readerId}`);
    if (resEl) {
        resEl.innerText = 'Resetting TCP socket...';
        resEl.className = 'text-[10px] font-mono font-bold text-amber-600';
    }

    try {
        const res = await fetch(`/api/tools/reconnect-reader/${readerId}`, { method: 'POST' });
        const data = await res.json();
        if (resEl) {
            resEl.innerText = data.reset_triggered ? 'Socket cycled - reconnecting' : 'Reconnecting worker...';
            resEl.className = 'text-[10px] font-mono font-bold text-blue-700';
            setTimeout(() => {
                if (resEl) {
                    resEl.innerText = 'Ready for probe';
                    resEl.className = 'text-[10px] font-mono text-slate-400';
                }
            }, 3500);
        }
    } catch (e) {
        if (resEl) {
            resEl.innerText = 'Reset failed';
            resEl.className = 'text-[10px] font-mono font-bold text-rose-600';
        }
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
            el.className = 'px-2.5 py-1 rounded-lg text-xs font-bold text-slate-600 hover:text-slate-900 transition';
        }
    });

    const activeId = ms === 1000 ? 'rateBtn1' : ms === 2000 ? 'rateBtn2' : 'rateBtn5';
    const activeEl = document.getElementById(activeId);
    if (activeEl) {
        activeEl.className = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white shadow-xs';
    }

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(fetchTelemetry, pollIntervalMs);
}

function setTelemetryMode(useSynthetic) {
    useSyntheticMode = !!useSynthetic;
    const physBtn = document.getElementById('modePhysicalBtn');
    const synthBtn = document.getElementById('modeSyntheticBtn');

    if (physBtn && synthBtn) {
        if (!useSyntheticMode) {
            physBtn.className = 'px-3 py-1 rounded-lg text-xs font-black transition flex items-center gap-1.5 bg-white text-slate-900 shadow-2xs border border-slate-200';
            synthBtn.className = 'px-3 py-1 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-800 transition flex items-center gap-1.5';
        } else {
            synthBtn.className = 'px-3 py-1 rounded-lg text-xs font-black transition flex items-center gap-1.5 bg-white text-blue-700 shadow-2xs border border-blue-200';
            physBtn.className = 'px-3 py-1 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-800 transition flex items-center gap-1.5';
        }
    }
    fetchTelemetry();
}

function togglePauseStream() {
    isStreamPaused = !isStreamPaused;
    const btn = document.getElementById('pauseResumeBtn');
    if (btn) {
        if (isStreamPaused) {
            btn.innerText = 'Resume Stream';
            btn.className = 'text-xs font-bold px-3 py-1.5 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 shadow-2xs';
        } else {
            btn.innerText = 'Pause Stream';
            btn.className = 'text-xs font-bold px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition shadow-2xs';
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
            ? 'bg-blue-50 text-blue-700 border-blue-200'
            : 'bg-amber-50 text-amber-700 border-amber-200';

        const gateName = t.gate || 'Gate-01';

        return `
        <div class="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 hover:bg-white hover:border-slate-300 transition shadow-2xs">
            <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full ${isEntry ? 'bg-blue-600' : 'bg-amber-500'} animate-ping"></span>
                <span class="font-mono text-xs font-bold text-slate-800">${t.tag}</span>
            </div>
            <div class="flex items-center gap-2.5">
                <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-white text-slate-700 border border-slate-200">${gateName}</span>
                <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${dirBadge}">${t.direction}</span>
                <span class="text-[10px] text-slate-400 font-mono">${t.time || ''}</span>
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

/* ==========================================================================
   9. Deep Hardware Reader Diagnostic Auditor
   ========================================================================== */
let currentDiagReaderId = null;
let lastDiagReportData = null;

async function diagnoseReader(readerId, btn) {
    currentDiagReaderId = readerId;
    const modal = document.getElementById('diagnoseModal');
    if (!modal) return;

    modal.classList.remove('hidden');

    const loadingEl = document.getElementById('diagLoading');
    const resultsEl = document.getElementById('diagResults');
    const rerunBtn = document.getElementById('diagRerunBtn');
    if (rerunBtn) rerunBtn.onclick = () => diagnoseReader(currentDiagReaderId);

    if (loadingEl) loadingEl.classList.remove('hidden');
    if (resultsEl) resultsEl.classList.add('hidden');

    const cfg = DEVICE_CONFIG[readerId] || { name: readerId };
    const titleEl = document.getElementById('diagModalTitle');
    const subEl = document.getElementById('diagModalSubtitle');
    const badgeEl = document.getElementById('diagBadge');

    if (titleEl) titleEl.innerText = `${cfg.name} Deep Hardware Audit`;
    if (subEl) subEl.innerText = 'Transmitting ICMP ping & scanning reader socket layer...';
    if (badgeEl) {
        badgeEl.innerText = 'AUDITING';
        badgeEl.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 animate-pulse';
    }

    try {
        const res = await fetch(`/api/tools/diagnose-reader/${readerId}`);
        const data = await res.json();
        lastDiagReportData = data;
        renderDiagResults(data);
    } catch (e) {
        if (loadingEl) loadingEl.classList.add('hidden');
        if (resultsEl) resultsEl.classList.remove('hidden');
        const alertCard = document.getElementById('diagRootCauseCard');
        if (alertCard) {
            alertCard.className = 'rounded-2xl p-4.5 border border-rose-200 bg-rose-50 text-rose-800';
            document.getElementById('diagAlertHeading').innerText = 'Diagnostic Execution Failed';
            document.getElementById('diagRootCauseText').innerText = 'Could not communicate with local diagnostic auditor: ' + e.message;
            document.getElementById('diagActionList').innerHTML = '<li>Check server process health.</li>';
        }
    }
}

function renderDiagResults(data) {
    const loadingEl = document.getElementById('diagLoading');
    const resultsEl = document.getElementById('diagResults');
    const subEl = document.getElementById('diagModalSubtitle');
    const badgeEl = document.getElementById('diagBadge');

    if (loadingEl) loadingEl.classList.add('hidden');
    if (resultsEl) resultsEl.classList.remove('hidden');

    if (!data.ok) {
        if (subEl) subEl.innerText = `Target: ${data.reader_id} (${data.error})`;
        if (badgeEl) {
            badgeEl.innerText = 'ERROR';
            badgeEl.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200';
        }
        const card = document.getElementById('diagRootCauseCard');
        card.className = 'rounded-2xl p-4.5 border border-rose-200 bg-rose-50';
        document.getElementById('diagAlertHeading').innerText = 'Configuration Error';
        document.getElementById('diagRootCauseText').innerText = data.message || 'Reader unconfigured';
        document.getElementById('diagActionList').innerHTML = '<li>Set IP address in Settings.</li>';
        return;
    }

    if (subEl) subEl.innerText = `Target: ${data.host}:${data.configured_port} (${data.label})`;
    if (badgeEl) {
        badgeEl.innerText = 'AUDIT COMPLETE';
        badgeEl.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200';
    }

    // 1. Root Cause Alert Banner
    const diag = data.diagnosis || {};
    const rootCause = diag.root_cause || '';
    const actions = diag.action_items || [];
    const rootCard = document.getElementById('diagRootCauseCard');
    const heading = document.getElementById('diagAlertHeading');
    const textEl = document.getElementById('diagRootCauseText');
    const iconEl = document.getElementById('diagAlertIcon');

    textEl.innerText = rootCause;
    if (rootCause.includes('PORT CONFLICT')) {
        rootCard.className = 'rounded-2xl p-4.5 border border-amber-300 bg-amber-50';
        heading.className = 'text-sm font-black text-amber-900';
        iconEl.innerText = '⚡';
    } else if (rootCause.includes('OPEN and reachable')) {
        rootCard.className = 'rounded-2xl p-4.5 border border-emerald-300 bg-emerald-50';
        heading.className = 'text-sm font-black text-emerald-900';
        iconEl.innerText = '✅';
    } else if (rootCause.includes('PORT MISMATCH') || rootCause.includes('WEB GUI ACTIVE')) {
        rootCard.className = 'rounded-2xl p-4.5 border border-blue-300 bg-blue-50';
        heading.className = 'text-sm font-black text-blue-900';
        iconEl.innerText = '💡';
    } else {
        rootCard.className = 'rounded-2xl p-4.5 border border-rose-300 bg-rose-50';
        heading.className = 'text-sm font-black text-rose-900';
        iconEl.innerText = '⚠️';
    }

    const actionList = document.getElementById('diagActionList');
    if (actionList) {
        actionList.innerHTML = actions.map(act => `<li class="font-medium text-slate-800">${act}</li>`).join('');
    }

    // 2. Ping Echo Box
    const ping = data.ping || {};
    const pingBadge = document.getElementById('diagPingBadge');
    if (pingBadge) {
        const isOnline = ping.status === 'ONLINE';
        pingBadge.innerText = isOnline ? 'ONLINE' : 'UNREACHABLE';
        pingBadge.className = `text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${isOnline ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}`;
    }
    document.getElementById('diagPingRtt').innerText = ping.latency_ms !== null && ping.latency_ms !== undefined ? `${ping.latency_ms.toFixed(1)} ms` : 'No Echo';
    document.getElementById('diagPingHost').innerText = data.host;

    // 3. Physical MAC Address Box
    const hw = data.hardware || {};
    const macBadge = document.getElementById('diagMacBadge');
    if (macBadge) {
        const hasMac = hw.mac_address && hw.mac_address !== 'NOT_IN_ARP_CACHE';
        macBadge.innerText = hasMac ? 'RESOLVED' : 'UNKNOWN';
        macBadge.className = `text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${hasMac ? 'bg-blue-50 text-blue-700 border border-blue-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`;
    }
    document.getElementById('diagMacAddress').innerText = hw.mac_address || 'Not in cache';
    const vendorEl = document.getElementById('diagVendorMatch');
    if (vendorEl) {
        if (hw.vendor_matched) {
            vendorEl.innerHTML = '<span class="text-emerald-700 font-bold">Verified &bull; Matches Club Readers</span>';
        } else if (hw.mac_address && hw.mac_address !== 'NOT_IN_ARP_CACHE') {
            vendorEl.innerHTML = '<span class="text-amber-600 font-bold">Unverified &bull; Possible IP Conflict</span>';
        } else {
            vendorEl.innerHTML = '<span class="text-slate-400">Cannot inspect OUI</span>';
        }
    }

    // 4. Port Scan Grid
    const portGrid = document.getElementById('diagPortGrid');
    if (portGrid) {
        const portScan = data.port_scan || {};
        portGrid.innerHTML = Object.keys(portScan).map(p => {
            const status = portScan[p];
            const isOpen = status === 'OPEN';
            const isRefused = status === 'CONNECTION_REFUSED';
            const isTimedOut = status === 'TIMED_OUT';

            const chipClass = isOpen
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : isRefused
                    ? 'bg-rose-50 border-rose-200 text-rose-800'
                    : 'bg-slate-100 border-slate-200 text-slate-500';

            const portDesc = p === '49152' ? 'RFID Default' : (p === '6000' || p === '4001' || p === '5000') ? 'Alt RFID' : (p === '80' || p === '8080') ? 'Web GUI' : 'Port';

            return `
            <div class="p-2.5 rounded-xl border ${chipClass} flex flex-col justify-between">
                <div class="flex items-center justify-between">
                    <span class="font-mono text-xs font-black">${p}</span>
                    <span class="text-[9px] font-mono font-bold uppercase">${status}</span>
                </div>
                <div class="flex items-center justify-between mt-1 text-[10px]">
                    <span class="opacity-75">${portDesc}</span>
                    ${isOpen && p !== String(data.configured_port) && (p === '6000' || p === '4001' || p === '5000' || p === '49152') ? `
                    <button type="button" onclick="applyDiscoveredIp('${data.reader_id}', '${data.host}:${p}')" class="underline font-bold text-blue-700 hover:text-blue-900">
                        Use Port
                    </button>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    // 5. Conflicting Processes
    const conflictBox = document.getElementById('diagConflictBox');
    const conflictList = document.getElementById('diagConflictList');
    const procs = data.conflicting_processes || [];
    if (procs.length > 0) {
        conflictBox.classList.remove('hidden');
        conflictList.innerHTML = procs.map(pr => `
        <div class="flex items-center justify-between bg-white/80 p-2 rounded-lg border border-amber-200">
            <span>Process: <strong>${pr.process_name}</strong> (PID ${pr.pid})</span>
            <span class="text-[10px] text-amber-700">${pr.state} &bull; Socket Held</span>
        </div>`).join('');
    } else {
        conflictBox.classList.add('hidden');
    }

    // 6. Subnet Discovery
    const subnetBox = document.getElementById('diagSubnetBox');
    const subnetText = document.getElementById('diagSubnetText');
    const discovered = data.discovered_readers_on_subnet || [];
    if (discovered.length > 0) {
        subnetBox.classList.remove('hidden');
        const dReader = discovered[0];
        subnetText.innerText = `Active RFID listener detected at ${dReader.ip}:${dReader.port}`;
        const applyBtn = document.getElementById('diagApplyDiscoveredBtn');
        if (applyBtn) {
            applyBtn.onclick = () => applyDiscoveredIp(data.reader_id, `${dReader.ip}:${dReader.port}`);
        }
    } else {
        subnetBox.classList.add('hidden');
    }
}

function closeDiagModal() {
    const modal = document.getElementById('diagnoseModal');
    if (modal) modal.classList.add('hidden');
}

async function applyDiscoveredIp(readerId, newIp) {
    if (!confirm(`Update ${readerId} IP to '${newIp}' and reconnect?`)) return;
    try {
        const res = await fetch(`/api/tools/update-reader-ip/${readerId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip: newIp })
        });
        const data = await res.json();
        alert(data.message || 'IP updated successfully.');
        diagnoseReader(readerId);
        fetchTelemetry();
    } catch (e) {
        alert('Failed to update reader IP: ' + e.message);
    }
}

function copyDiagReport() {
    if (!lastDiagReportData) {
        alert('No diagnostic data to copy.');
        return;
    }
    const d = lastDiagReportData;
    const diag = d.diagnosis || {};
    const lines = [
        `=== KGC VAMS Hardware Diagnostic Report ===`,
        `Reader: ${d.label} (${d.reader_id})`,
        `Target Host: ${d.host}`,
        `Configured Port: ${d.configured_port}`,
        `Ping Status: ${d.ping?.status} (${d.ping?.latency_ms} ms)`,
        `MAC Address: ${d.hardware?.mac_address} (Vendor Match: ${d.hardware?.vendor_matched})`,
        `Open Ports: ${(d.open_ports || []).join(', ') || 'None'}`,
        `Conflicting Local Processes: ${(d.conflicting_processes || []).map(p => `${p.process_name} (PID ${p.pid})`).join(', ') || 'None'}`,
        `Root Cause: ${diag.root_cause}`,
        `Recommended Fixes:`,
        ...(diag.action_items || []).map(a => ` - ${a}`),
        `Generated: ${new Date().toISOString()}`
    ];

    navigator.clipboard.writeText(lines.join('\n')).then(() => {
        alert('Diagnostic report copied to clipboard!');
    }).catch(() => {
        alert('Failed to copy to clipboard.');
    });
}

