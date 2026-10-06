function switchTab(name, btn) {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    document.querySelectorAll('[id^="tab-"]').forEach(panel => panel.classList.add('hidden'));
    const target = document.getElementById('tab-' + name);
    if (target) target.classList.remove('hidden');

    const titleEl = document.getElementById('pageTitle');
    if (titleEl) {
        titleEl.innerText = name === 'overview' ? 'Command Overview' :
                            name === 'logs' ? 'Vehicle Audit Reports' :
                            name === 'camera_audit' ? 'Camera Vehicle Audit' :
                            name === 'members' ? 'Member Directory' : 'Hardware Settings';
    }

    if (name === 'logs') {
        const dInput = document.getElementById('auditDate');
        if (dInput && !dInput.value) {
            setAuditDatePreset('today');
        } else {
            loadAudit(1);
        }
    } else if (name === 'camera_audit') {
        const dInput = document.getElementById('camAuditDate');
        if (dInput && !dInput.value && currentCamAuditDate !== 'all') {
            setCamAuditPreset('today');
        } else {
            loadCameraAudit(1);
        }
    }
}

function updateLiveClock() {
    const clockEl = document.getElementById('liveClock');
    if (clockEl) {
        clockEl.innerText = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
}
setInterval(updateLiveClock, 1000);
updateLiveClock();

async function loadStats() {
    try {
        const [statsRes, settingsRes] = await Promise.all([
            fetch('/api/stats'),
            fetch('/api/settings')
        ]);
        const s = await statsRes.json();
        const set = await settingsRes.json();
        const cap = parseInt(set.parking_capacity || '500', 10);

        if (document.getElementById('sMembers')) document.getElementById('sMembers').innerText = (s.active_members || 0).toLocaleString();
        if (document.getElementById('sEntries')) document.getElementById('sEntries').innerText = (s.total_entries_today || 0).toLocaleString();
        if (document.getElementById('sInside')) document.getElementById('sInside').innerText = (s.currently_in_club || 0).toLocaleString();
        if (document.getElementById('sExits')) document.getElementById('sExits').innerText = (s.total_exits_today || 0).toLocaleString();
        if (document.getElementById('sParking')) document.getElementById('sParking').innerText = Math.max(0, cap - (s.currently_in_club || 0)).toLocaleString();
        if (document.getElementById('sCap')) document.getElementById('sCap').innerText = cap.toLocaleString();
        if (document.getElementById('sGuests')) document.getElementById('sGuests').innerText = (s.guests_today || 0).toLocaleString();
        if (document.getElementById('sPeak')) document.getElementById('sPeak').innerText = s.peak_hour ? `${s.peak_hour} (${s.peak_count})` : 'None';
        if (document.getElementById('parkPct')) document.getElementById('parkPct').innerText = Math.round(((s.currently_in_club || 0) / cap) * 100) + '%';
        if (document.getElementById('parkIn')) document.getElementById('parkIn').innerText = (s.currently_in_club || 0).toLocaleString();
        if (document.getElementById('parkFree')) document.getElementById('parkFree').innerText = Math.max(0, cap - (s.currently_in_club || 0)).toLocaleString();

        updateParkingDonut(s.currently_in_club || 0, cap);
    } catch (err) {
        console.error('loadStats error:', err);
    }
}

let hourlyChart = null;
let weeklyChart = null;
let parkingChart = null;

function initCharts() {
    const hourlyEl = document.getElementById('hourlyChart');
    if (!hourlyEl) return;

    Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = '#64748B';

    hourlyChart = new Chart(hourlyEl, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Entries',
                    data: [],
                    borderColor: '#10B981',
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 2
                },
                {
                    label: 'Exits',
                    data: [],
                    borderColor: '#3B82F6',
                    backgroundColor: 'rgba(59, 130, 246, 0.06)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 2
                }
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
    });

    weeklyChart = new Chart(document.getElementById('weeklyChart'), {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                { label: 'Entries', data: [], backgroundColor: '#34D399', borderRadius: 6, barPercentage: 0.55 },
                { label: 'Exits', data: [], backgroundColor: '#93C5FD', borderRadius: 6, barPercentage: 0.55 }
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 10 } } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
    });

    parkingChart = new Chart(document.getElementById('parkingChart'), {
        type: 'doughnut',
        data: {
            labels: ['Occupied', 'Available'],
            datasets: [{ data: [0, 100], backgroundColor: ['#3B82F6', '#E2E8F0'], borderWidth: 0, cutout: '78%' }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });
}

function updateParkingDonut(inside, cap) {
    if (parkingChart) {
        parkingChart.data.datasets[0].data = [inside, Math.max(0, cap - inside)];
        parkingChart.update();
    }
}

async function loadCharts() {
    try {
        const res = await fetch('/api/chart-data');
        if (!res.ok) return;
        const c = await res.json();
        if (hourlyChart) {
            hourlyChart.data.labels = c.hours;
            hourlyChart.data.datasets[0].data = c.hourly_entries;
            hourlyChart.data.datasets[1].data = c.hourly_exits;
            hourlyChart.update();
        }
        if (weeklyChart) {
            weeklyChart.data.labels = c.days;
            weeklyChart.data.datasets[0].data = c.daily_entries;
            weeklyChart.data.datasets[1].data = c.daily_exits;
            weeklyChart.update();
        }
    } catch (err) {
        console.error('loadCharts error:', err);
    }
}

function renderHwRow(label, statusVal, isOk, subtext) {
    return `
    <div class="flex items-center justify-between bg-slate-50 rounded-xl px-4 py-3 border">
        <div class="flex items-center gap-3">
            <span class="w-9 h-9 rounded-lg ${isOk ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-600'} flex items-center justify-center text-xs font-bold font-mono">
                ${isOk ? 'OK' : 'ERR'}
            </span>
            <div>
                <p class="text-xs font-extrabold text-slate-700">${label}</p>
                <p class="text-[10px] ${isOk ? 'text-emerald-600' : 'text-rose-500'} font-bold">${isOk ? 'OPERATIONAL' : 'DISCONNECTED'}</p>
            </div>
        </div>
        <span class="inline-block w-2.5 h-2.5 rounded-full ${isOk ? 'bg-emerald-500 pulse-indicator' : 'bg-rose-500'}"></span>
    </div>`;
}

async function loadHardware() {
    try {
        const res = await fetch('/api/tools/status');
        if (!res.ok) return;
        const s = await res.json();
        const grid = document.getElementById('hwGrid');
        if (!grid) return;

        grid.innerHTML =
            renderHwRow('Entry RFID Reader', s.readers.Entry, s.readers.Entry === 'CONNECTED') +
            renderHwRow('Exit RFID Reader', s.readers.Exit, s.readers.Exit === 'CONNECTED') +
            renderHwRow('Hikvision HD AI Camera', s.cameras.Hikvision, s.cameras.Hikvision === 'ONLINE');

        if (document.getElementById('hwFtp')) document.getElementById('hwFtp').innerText = s.ftp_events || 0;
        const last = s.recent_tags && s.recent_tags.length ? s.recent_tags[s.recent_tags.length - 1] : null;
        if (document.getElementById('hwLastTag')) {
            document.getElementById('hwLastTag').innerText = last ? `${last.tag.substring(0, 16)}... ${last.time}` : 'None';
        }

        const allOk = (s.readers.Entry === 'CONNECTED') && (s.readers.Exit === 'CONNECTED') && (s.cameras.Hikvision === 'ONLINE');
        const badge = document.getElementById('sysBadge');
        if (badge) {
            badge.className = 'inline-flex items-center px-3 py-1.5 rounded-full mb-2 border ' + (allOk ? 'bg-emerald-100 border-emerald-200' : 'bg-amber-100 border-amber-200');
            badge.innerHTML = `<div class="w-2 h-2 rounded-full ${allOk ? 'bg-emerald-500' : 'bg-amber-500'} animate-pulse mr-2"></div><span class="text-xs font-bold ${allOk ? 'text-emerald-700' : 'text-amber-700'}">${allOk ? 'ALL SYSTEMS OPERATIONAL' : 'ATTENTION REQUIRED'}</span>`;
        }
    } catch (err) {
        console.error('loadHardware error:', err);
    }
}

async function loadActivity() {
    try {
        const res = await fetch('/api/logs?limit=10');
        if (!res.ok) return;
        const rows = await res.json();
        const body = document.getElementById('activityBody');
        if (!body) return;

        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="6" class="p-8 text-center text-slate-400 font-bold">No gate transactions recorded yet</td></tr>';
            return;
        }

        body.innerHTML = rows.map(r => {
            const isUnregistered = (r.access_type || '').includes('Unknown') || 
                                   (r.access_type || '').includes('No RFID') || 
                                   (r.name || '').includes('Unregistered');
            const timeStr = String(r.timestamp).replace('T', ' ').substring(11, 19);

            return `
            <tr class="hover:bg-slate-50 transition-colors">
                <td class="p-4 text-xs font-mono font-bold text-slate-500 tabular-nums">${timeStr}</td>
                <td class="p-4">
                    <div class="flex items-center gap-3">
                        ${r.image_path ? 
                            `<img src="/${r.image_path}" class="w-14 h-10 rounded-lg object-cover border cursor-pointer hover:opacity-80" onclick="window.open('/${r.image_path}')">` :
                            `<div class="w-14 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-400 text-[9px] font-bold">NO IMG</div>`
                        }
                        <p class="font-mono font-bold text-indigo-600">${r.vehicle_number || '--'}</p>
                    </div>
                </td>
                <td class="p-4">
                    <p class="font-bold ${isUnregistered ? 'text-rose-600' : 'text-slate-800'}">${r.name}</p>
                    <p class="text-[10px] text-slate-400 font-mono">${r.mem_id || 'N/A'}</p>
                </td>
                <td class="p-4">
                    <span class="text-[10px] font-extrabold px-2.5 py-1 rounded-full ${
                        r.access_type.includes('Verified') ? 'bg-emerald-100 text-emerald-800' :
                        r.access_type.includes('Unknown') ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                    }">${r.access_type}</span>
                </td>
                <td class="p-4">
                    <span class="text-[10px] font-extrabold px-2.5 py-1 rounded-full ${r.direction === 'Entry' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-700'}">${r.direction}</span>
                </td>
                <td class="p-4">
                    ${r.image_path ? 
                        `<button type="button" onclick="window.open('/${r.image_path}')" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 border rounded-lg px-2.5 py-1 bg-indigo-50">View</button>` :
                        '<span class="text-slate-300 text-xs">None</span>'
                    }
                </td>
            </tr>`;
        }).join('');
    } catch (err) {
        console.error('loadActivity error:', err);
    }
}

let auditData = [];
let currentAuditPage = 1;
let currentAuditLimit = 25;
let currentAuditStatus = 'all';
let auditSearchTimer = null;

function onAuditSearchInput() {
    clearTimeout(auditSearchTimer);
    auditSearchTimer = setTimeout(() => {
        currentAuditPage = 1;
        loadAudit(1);
    }, 300);
}

function setAuditDatePreset(preset) {
    const input = document.getElementById('auditDate');
    if (!input) return;
    const now = new Date();
    if (preset === 'yesterday') {
        now.setDate(now.getDate() - 1);
    }
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    input.value = `${year}-${month}-${day}`;
    loadAudit(1);
}

function setAuditStatusFilter(status, el) {
    currentAuditStatus = status;
    document.querySelectorAll('.audit-status-pill').forEach(b => {
        b.className = 'audit-status-pill px-3 py-1 text-xs font-bold rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition';
    });
    if (el) el.className = 'audit-status-pill px-3 py-1 text-xs font-bold rounded-lg bg-indigo-600 text-white shadow-sm transition';
    loadAudit(1);
}

function changeAuditLimit() {
    const sel = document.getElementById('auditLimitSelect');
    if (sel) currentAuditLimit = parseInt(sel.value, 10) || 25;
    loadAudit(1);
}

async function loadAudit(page = currentAuditPage) {
    currentAuditPage = page;
    const d = document.getElementById('auditDate')?.value || '';
    const q = (document.getElementById('auditSearch') || {}).value || '';
    const bodyEl = document.getElementById('auditBody');
    if (!bodyEl) return;

    bodyEl.innerHTML = `<tr><td colspan="8" class="p-10 text-center text-slate-400 font-bold">Loading audit logs...</td></tr>`;

    try {
        const url = `/api/audit?date=${encodeURIComponent(d)}&page=${page}&limit=${currentAuditLimit}&search=${encodeURIComponent(q)}&status=${currentAuditStatus}`;
        const res = await fetch(url);
        const data = await res.json();

        if (document.getElementById('auditStatTotal')) document.getElementById('auditStatTotal').innerText = (data.total || 0).toLocaleString();
        if (document.getElementById('auditStatInside')) document.getElementById('auditStatInside').innerText = (data.currently_inside || 0).toLocaleString();
        if (document.getElementById('auditStatExited')) document.getElementById('auditStatExited').innerText = (data.exited_count || 0).toLocaleString();
        if (document.getElementById('auditStatAlerts')) document.getElementById('auditStatAlerts').innerText = (data.alert_count || 0).toLocaleString();
        if (document.getElementById('auditBadgeDate')) document.getElementById('auditBadgeDate').innerText = data.date || 'Today';

        auditData = data.audits || [];
        const total = data.total_filtered !== undefined ? data.total_filtered : auditData.length;
        const totalPages = data.total_pages || Math.ceil(total / currentAuditLimit) || 1;

        if (!auditData.length) {
            bodyEl.innerHTML = `<tr><td colspan="8" class="p-12 text-center text-slate-400 font-bold">No vehicle audit records matching criteria</td></tr>`;
            renderAuditPagination(0, 1, 1, currentAuditLimit);
            return;
        }

        bodyEl.innerHTML = auditData.map(a => {
            let e = a.entry, x = a.exit;
            if (e && x && e.timestamp && x.timestamp && String(e.timestamp) > String(x.timestamp)) {
                const tmp = e; e = x; x = tmp;
            }
            const thumb = e || x;
            if (!thumb) return '';

            const isMember = e && !['GUEST-LOG', 'AI-CAM'].includes(e.mem_id);
            const isUnreg = (e && (e.access_type || '').includes('Unknown')) || (!e && x && (x.access_type || '').includes('Unknown'));
            const isNoTag = (e && (e.access_type || '').includes('No RFID')) || (!e && x && (x.access_type || '').includes('No RFID'));

            const pfp = thumb.profile_pic;
            const initial = (thumb.name || '?').charAt(0).toUpperCase();

            let rowDur = a.duration;
            if (!rowDur || rowDur === '--') {
                if (e && x && e.timestamp && x.timestamp) {
                    const t1 = new Date(e.timestamp.replace(' ', 'T')).getTime();
                    const t2 = new Date(x.timestamp.replace(' ', 'T')).getTime();
                    if (!isNaN(t1) && !isNaN(t2)) {
                        const diffMin = Math.round(Math.abs(t2 - t1) / 60000);
                        const hrs = Math.floor(diffMin / 60);
                        const mins = diffMin % 60;
                        rowDur = hrs > 0 ? `${hrs}h ${String(mins).padStart(2, '0')}m` : `${mins}m`;
                    }
                } else if (e && !x && e.timestamp) {
                    const t1 = new Date(e.timestamp.replace(' ', 'T')).getTime();
                    if (!isNaN(t1)) {
                        const diffMin = Math.round(Math.max(0, Date.now() - t1) / 60000);
                        const hrs = Math.floor(diffMin / 60);
                        const mins = diffMin % 60;
                        rowDur = `${hrs > 0 ? `${hrs}h ${String(mins).padStart(2, '0')}m` : `${mins}m`} (Active)`;
                    }
                }
            }

            let statusPill = '';
            if (a.status === 'Inside Facility' || a.status === 'Alert / Inside') {
                statusPill = `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>INSIDE FACILITY</span>`;
            } else if (a.status === 'Exited') {
                statusPill = `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black bg-slate-100 text-slate-700 border border-slate-200">
                    <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>EXITED</span>`;
            } else {
                statusPill = `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black bg-amber-100 text-amber-800 border border-amber-200">
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>EXIT ONLY</span>`;
            }

            let methodPill = '';
            if (isMember) {
                methodPill = `<span class="text-[10px] font-black px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/70">Verified Member</span>`;
            } else if (isUnreg) {
                methodPill = `<span class="text-[10px] font-black px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200/70">Unknown RFID</span>`;
            } else {
                methodPill = `<span class="text-[10px] font-black px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200/70">Optical Capture</span>`;
            }

            const imgPath = thumb.image_path || thumb.plate_image_path;

            return `
            <tr class="hover:bg-slate-50 transition-colors cursor-pointer" onclick='openAudit(${JSON.stringify(a).replace(/'/g, "&#39;")})'>
                <td class="p-3.5 pl-5">
                    <div class="flex items-center gap-3">
                        ${imgPath ? `<img src="/${imgPath}" class="w-14 h-10 rounded-xl object-cover border border-slate-200 shadow-sm">` :
                        `<div class="w-14 h-10 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400 text-[9px] font-bold">NO IMG</div>`}
                        <div>
                            <p class="font-mono font-bold text-indigo-600 bg-indigo-50 border border-indigo-200/60 px-2 py-0.5 rounded-md text-xs inline-block">${thumb.vehicle_number || 'UNKNOWN'}</p>
                            ${thumb.make_model ? `<p class="text-[11px] text-slate-500 mt-0.5 truncate max-w-[120px]">${thumb.make_model}</p>` : ''}
                        </div>
                    </div>
                </td>
                <td class="p-3.5">
                    <div class="flex items-center gap-2.5">
                        ${pfp ? `<img src="/${pfp}" class="w-8 h-8 rounded-full object-cover border border-slate-200">` :
                        `<div class="w-8 h-8 rounded-full ${isUnreg || isNoTag ? 'bg-rose-100 text-rose-600' : 'bg-slate-100 text-slate-600'} flex items-center justify-center font-bold text-xs">${initial}</div>`}
                        <div>
                            <p class="font-bold text-slate-900 ${isUnreg || isNoTag ? 'text-rose-600' : ''}">${thumb.name || 'Unregistered'}</p>
                            <p class="text-[10px] text-slate-400 font-mono">${thumb.mem_id || 'N/A'}</p>
                        </div>
                    </div>
                </td>
                <td class="p-3.5">${methodPill}</td>
                <td class="p-3.5">
                    ${e ? `<div>
                        <p class="font-bold text-slate-800 tabular-nums">${String(e.timestamp).split(' ')[1] || e.timestamp}</p>
                        <p class="text-[10px] text-slate-400 font-mono">${e.gate_no || 'Entry Gate'}</p>
                    </div>` : '<span class="text-slate-300">-</span>'}
                </td>
                <td class="p-3.5">
                    ${x ? `<div>
                        <p class="font-bold text-slate-800 tabular-nums">${String(x.timestamp).split(' ')[1] || x.timestamp}</p>
                        <p class="text-[10px] text-slate-400 font-mono">${x.gate_no || 'Exit Gate'}</p>
                    </div>` : '<span class="text-emerald-600 font-bold text-xs">Parked Inside</span>'}
                </td>
                <td class="p-3.5">
                    ${rowDur ? `<span class="font-bold text-xs bg-indigo-50 text-indigo-700 border border-indigo-200/70 px-2.5 py-1 rounded-lg tabular-nums">${rowDur}</span>` :
                    '<span class="text-slate-400 text-xs">-</span>'}
                </td>
                <td class="p-3.5">${statusPill}</td>
                <td class="p-3.5 text-right pr-6" onclick="event.stopPropagation()">
                    <div class="flex items-center justify-end gap-2">
                        <button type="button" onclick='openAudit(${JSON.stringify(a).replace(/'/g, "&#39;")})' class="text-xs font-bold text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded-xl px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 shadow-sm transition">Report</button>
                        <a href="/api/audit/${thumb.id}/pdf" target="_blank" title="Download Executive Gold-Standard PDF Report" class="text-xs font-bold text-amber-800 hover:text-amber-900 border border-amber-300 rounded-xl px-2.5 py-1.5 bg-gradient-to-r from-amber-50 to-yellow-50 hover:from-amber-100 hover:to-yellow-100 shadow-xs transition inline-flex items-center gap-1">
                            <svg class="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                            PDF
                        </a>
                    </div>
                </td>
            </tr>`;
        }).join('');

        renderAuditPagination(total, page, totalPages, currentAuditLimit);
    } catch (err) {
        bodyEl.innerHTML = `<tr><td colspan="8" class="p-10 text-center text-rose-500 font-bold">Error loading audit logs: ${err.message}</td></tr>`;
    }
}

function renderAuditPagination(total, page, totalPages, limit) {
    const pagEl = document.getElementById('auditPagination');
    if (!pagEl) return;
    if (total === 0) {
        pagEl.innerHTML = `<span class="text-xs text-slate-400">No records to display</span>`;
        return;
    }

    const start = (page - 1) * limit + 1;
    const end = Math.min(page * limit, total);
    let btns = [];
    btns.push(`<button onclick="loadAudit(1)" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>First</button>`);
    btns.push(`<button onclick="loadAudit(${page - 1})" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Prev</button>`);

    let startPage = Math.max(1, page - 2);
    let endPage = Math.min(totalPages, page + 2);

    for (let p = startPage; p <= endPage; p++) {
        if (p === page) {
            btns.push(`<button class="px-3 py-1 text-xs border rounded-lg bg-indigo-600 text-white font-bold shadow-sm">${p}</button>`);
        } else {
            btns.push(`<button onclick="loadAudit(${p})" class="px-3 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm">${p}</button>`);
        }
    }

    btns.push(`<button onclick="loadAudit(${page + 1})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Next</button>`);
    btns.push(`<button onclick="loadAudit(${totalPages})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Last</button>`);

    pagEl.innerHTML = `
        <div class="flex justify-between items-center w-full flex-wrap gap-3">
            <div class="text-xs text-slate-500 font-medium">
                Showing <span class="font-bold text-slate-800">${start}</span> to <span class="font-bold text-slate-800">${end}</span> of <span class="font-bold text-slate-800">${total.toLocaleString()}</span> vehicle audit records (Page ${page} of ${totalPages})
            </div>
            <div class="flex gap-1 items-center">
                ${btns.join('')}
            </div>
        </div>
    `;
}

function openAudit(a) {
    let e = a.entry, x = a.exit;
    if (e && x && e.timestamp && x.timestamp && String(e.timestamp) > String(x.timestamp)) {
        const tmp = e; e = x; x = tmp;
    }
    const v = e || x;
    const isUnreg = Boolean((v.access_type || '').includes('Unknown') || (v.name || '').includes('Unregistered'));
    const isNoTag = Boolean((v.access_type || '').includes('No RFID') || !v.scanned_tag || v.scanned_tag === 'NO_TAG');
    const isMember = !isUnreg && !isNoTag && v.mem_id && !['GUEST-LOG', 'AI-CAM'].includes(v.mem_id);
    const epc = (v.scanned_tag && v.scanned_tag !== 'NO_TAG') ? v.scanned_tag : '';

    let modalDur = a.duration;
    if (!modalDur || modalDur === '--') {
        if (e && x && e.timestamp && x.timestamp) {
            const t1 = new Date(e.timestamp.replace(' ', 'T')).getTime();
            const t2 = new Date(x.timestamp.replace(' ', 'T')).getTime();
            if (!isNaN(t1) && !isNaN(t2)) {
                const diffMin = Math.round(Math.abs(t2 - t1) / 60000);
                const hrs = Math.floor(diffMin / 60);
                const mins = diffMin % 60;
                modalDur = hrs > 0 ? `${hrs}h ${String(mins).padStart(2, '0')}m` : `${mins}m`;
            }
        } else if (e && !x && e.timestamp) {
            const t1 = new Date(e.timestamp.replace(' ', 'T')).getTime();
            if (!isNaN(t1)) {
                const diffMin = Math.round(Math.max(0, Date.now() - t1) / 60000);
                const hrs = Math.floor(diffMin / 60);
                const mins = diffMin % 60;
                modalDur = `${hrs > 0 ? `${hrs}h ${String(mins).padStart(2, '0')}m` : `${mins}m`} (Active)`;
            }
        }
    }

    const hasEntryCam = !!(e && e.image_path);
    const hasExitCam = !!(x && x.image_path);
    const photosTotal = (hasEntryCam ? 1 : 0) + (hasExitCam ? 1 : 0);
    const evTotalExpected = (e && x) ? 2 : 1;
    const evScore = Math.round((photosTotal / evTotalExpected) * 100);

    document.getElementById('auditModalContent').innerHTML = `
    <div class="relative">
        <div class="h-2 rounded-t-3xl ${a.status === 'Exited' || a.status === 'Exit Only' ? 'bg-gradient-to-r from-slate-400 to-slate-500' : 'bg-gradient-to-r from-emerald-400 to-green-500'}"></div>
        <div class="p-8">
            <div class="flex justify-between items-start border-b-2 border-slate-200 pb-6 mb-6">
                <div class="flex items-center gap-5">
                    <img src="/api/logo" class="h-16 object-contain" onerror="this.style.display='none'">
                    <div>
                        <h1 class="text-2xl font-extrabold text-slate-800 tracking-wide uppercase">VEHICLE AUDIT REPORT</h1>
                        <p class="text-xs font-bold text-slate-400 tracking-widest uppercase mt-1">Karachi Gymkhana Club &bull; Gate Security Department</p>
                        <div class="flex gap-2 mt-2">
                            <span class="text-[9px] font-black px-2.5 py-1 rounded-full ${isMember ? 'bg-emerald-100 text-emerald-800' : isUnreg ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'}">
                                ${isMember ? 'RFID VERIFIED MEMBER' : isUnreg ? 'UNKNOWN RFID TAG' : 'OPTICAL CAPTURE - NO RFID'}
                            </span>
                            <span class="text-[9px] font-black px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">${(v.direction || 'ENTRY').toUpperCase()}</span>
                        </div>
                </div>
                <div class="text-right text-xs text-slate-500 space-y-1">
                    <div class="flex items-center justify-end gap-2 mb-1.5">
                        <a href="/api/audit/${v.id}/pdf" target="_blank"
                           class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-extrabold bg-gradient-to-r from-amber-100 to-yellow-100 text-amber-900 border border-amber-300 hover:from-amber-200 hover:to-yellow-200 shadow-xs transition">
                            <svg class="w-3.5 h-3.5 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                            Export PDF
                        </a>
                    </div>
                    <p><b>Report Ref:</b> <span class="font-mono font-bold text-slate-700">AUD-${String(v.id).padStart(6, '0')}</span></p>
                    <p><b>Generated:</b> ${new Date().toLocaleString()}</p>
                    <p><b>Visit Date:</b> ${String(v.timestamp).substring(0, 10)}</p>
                    <span class="inline-block mt-1 text-[10px] font-black px-2.5 py-1 rounded-full ${a.status === 'Inside Facility' ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : a.status === 'Exited' || a.status === 'Exit Only' ? 'bg-slate-100 text-slate-700' : 'bg-amber-100 text-amber-800'}">${a.status.toUpperCase()}</span>
                </div>
            </div>

            <div class="grid grid-cols-12 gap-4 mb-6">
                <div class="col-span-5 bg-slate-50 rounded-2xl p-5 border">
                    <p class="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-3">Driver / Member Profile</p>
                    <div class="flex items-center gap-4 mb-4">
                        ${v.Profile_pic ? `<img src="/${v.Profile_pic}" class="w-16 h-16 rounded-2xl object-cover border shadow-sm">` :
                        `<div class="w-16 h-16 rounded-2xl ${isUnreg || isNoTag ? 'bg-rose-100 text-rose-600' : 'bg-slate-200 text-slate-600'} flex items-center justify-center text-2xl font-black">${(v.name || '?').charAt(0)}</div>`}
                        <div>
                            <p class="font-extrabold text-base text-slate-900">${v.name}</p>
                            <p class="text-xs text-slate-400 font-mono mt-0.5">${v.mem_id}</p>
                            <p class="text-[10px] font-bold ${isMember ? 'text-emerald-600' : 'text-rose-500'} mt-1 uppercase tracking-wide">${isMember ? 'Active Member' : 'Unregistered'}</p>
                        </div>
                    </div>
                    <div class="space-y-2 text-xs border-t pt-3">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Member ID</span><span class="font-mono font-bold">${v.mem_id}</span></div>
                        <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">RFID EPC</span><span class="font-mono font-bold text-emerald-600 text-[10px] truncate max-w-[60%]">${epc || 'No RFID Tag'}</span></div>
                    </div>
                </div>

                <div class="col-span-4 bg-slate-50 rounded-2xl p-5 border">
                    <p class="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-3">Vehicle Details</p>
                    <p class="font-mono font-extrabold text-2xl text-indigo-600 tracking-wider">${v.vehicle_number}</p>
                    <p class="text-sm text-slate-600 font-bold mt-1">${v.make_model || 'Make unspecified'}</p>
                    <div class="space-y-2 text-xs border-t pt-3 mt-3">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Gate Station</span><span class="font-bold font-mono">${v.gate_no}</span></div>
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Access Verification</span><span class="font-bold">${v.access_type}</span></div>
                    </div>
                </div>

                <div class="col-span-3 bg-slate-50 rounded-2xl p-5 border text-center">
                    <p class="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest mb-3">Stay Duration</p>
                    <p class="text-3xl font-black ${modalDur ? 'text-indigo-600' : 'text-slate-400'} py-2">${modalDur || '--'}</p>
                    <div class="space-y-2 text-xs border-t pt-3 text-left">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Entry:</span><span class="font-bold">${e ? String(e.timestamp).substring(11, 19) : '--'}</span></div>
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Exit:</span><span class="font-bold">${x ? String(x.timestamp).substring(11, 19) : '--'}</span></div>
                    </div>
                </div>
            </div>

            <!-- Evidence Details -->
            <div class="space-y-4 mb-6">
                ${e && e.image_path ? `
                <div class="border rounded-2xl p-4 bg-slate-50">
                    <p class="text-xs font-bold text-slate-700 mb-2 uppercase">Entry Camera Proof &bull; ${e.timestamp}</p>
                    <div>
                        <span class="text-[10px] font-bold text-slate-500 uppercase block mb-1">Hikvision Full Overview</span>
                        <img src="/${e.image_path}" class="w-full h-72 object-cover rounded-xl border cursor-pointer" onclick="window.open('/${e.image_path}')">
                    </div>
                </div>` : ''}

                ${x && x.image_path ? `
                <div class="border rounded-2xl p-4 bg-slate-50">
                    <p class="text-xs font-bold text-slate-700 mb-2 uppercase">Exit Camera Proof &bull; ${x.timestamp}</p>
                    <div>
                        <span class="text-[10px] font-bold text-slate-500 uppercase block mb-1">Hikvision Full Overview</span>
                        <img src="/${x.image_path}" class="w-full h-72 object-cover rounded-xl border cursor-pointer" onclick="window.open('/${x.image_path}')">
                    </div>
                </div>` : ''}
            </div>

            <div class="flex justify-between items-center pt-5 border-t flex-wrap gap-3">
                <a href="/api/audit/${v.id}/pdf" target="_blank"
                   class="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-bold text-sm text-amber-950 bg-gradient-to-r from-amber-200 via-yellow-100 to-amber-300 hover:from-amber-300 hover:to-yellow-200 border border-amber-400/80 shadow-md transition">
                    <svg class="w-4 h-4 text-amber-800" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    Download Gold-Standard PDF Certificate
                </a>
                <div class="flex items-center gap-3">
                    <button type="button" onclick="closeAudit()" class="px-6 py-2.5 rounded-xl font-bold text-sm border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-xs">Close</button>
                </div>
            </div>
        </div>
    </div>`;

    document.getElementById('auditModal').classList.remove('hidden');
}

function closeAudit() {
    const modal = document.getElementById('auditModal');
    if (modal) modal.classList.add('hidden');
}
const auditModalEl = document.getElementById('auditModal');
if (auditModalEl) {
    auditModalEl.addEventListener('click', function(e) {
        if (e.target === this) closeAudit();
    });
}

let editingMemberRowId = null;
let editingMemberMemId = null;
let currentMemPage = 1;
let currentMemLimit = 25;
let memSearchTimer = null;
let epcPollingInterval = null;

function onMemSearchInput() {
    clearTimeout(memSearchTimer);
    memSearchTimer = setTimeout(() => {
        currentMemPage = 1;
        loadMembers(1);
    }, 300);
}

function changeMemLimit() {
    const sel = document.getElementById('memLimitSelect');
    if (sel) currentMemLimit = parseInt(sel.value, 10) || 25;
    currentMemPage = 1;
    loadMembers(1);
}

async function loadMembers(page = currentMemPage) {
    currentMemPage = page;
    const q = (document.getElementById('memSearch') || {}).value || '';
    const bodyEl = document.getElementById('memBody');
    if (!bodyEl) return;

    bodyEl.innerHTML = `<tr><td colspan="6" class="p-8 text-center text-slate-400 font-bold">Loading members...</td></tr>`;

    try {
        const url = `/api/members?page=${page}&limit=${currentMemLimit}&search=${encodeURIComponent(q)}`;
        const res = await fetch(url);
        const data = await res.json();

        const members = Array.isArray(data) ? data : (data.members || []);
        const total = data.total !== undefined ? data.total : members.length;
        const totalPages = data.total_pages || Math.ceil(total / currentMemLimit) || 1;

        if (document.getElementById('statUniqueMem')) document.getElementById('statUniqueMem').innerText = (data.unique_members || 0).toLocaleString();
        if (document.getElementById('statTotalVehicles')) document.getElementById('statTotalVehicles').innerText = (data.total_vehicles || total).toLocaleString();
        if (document.getElementById('statTaggedMem')) document.getElementById('statTaggedMem').innerText = (data.tagged_count || total).toLocaleString();
        if (document.getElementById('memCount')) document.getElementById('memCount').innerText = `${(data.unique_members || 0).toLocaleString()} Members / ${total.toLocaleString()} Vehicles`;

        if (!members.length) {
            bodyEl.innerHTML = `<tr><td colspan="6" class="p-12 text-center text-slate-400 font-bold">No registered members found matching query</td></tr>`;
            renderMemPagination(0, 1, 1, currentMemLimit);
            return;
        }

        bodyEl.innerHTML = members.map(m => {
            const initial = m.Name ? m.Name.charAt(0).toUpperCase() : '?';
            const vehicles = m.vehicles || [];
            const vCount = m.vehicle_count || vehicles.length || 1;
            const tCount = m.tagged_count !== undefined ? m.tagged_count : vehicles.filter(v => v.E_tag_id && v.E_tag_id.trim()).length;
            
            const platesPreview = vehicles.map(v => v.Car_number).filter(Boolean).slice(0, 3).join(', ') + (vehicles.length > 3 ? ` +${vehicles.length - 3} more` : '');
            const allPlates = vehicles.map(v => `${v.Car_number} (${v.Make_Model || 'No Model'})`).join(' | ');

            let tagBadge = '';
            if (tCount === vCount && vCount > 0) {
                tagBadge = `<span class="font-bold text-xs bg-emerald-50 text-emerald-700 border border-emerald-200/80 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>All ${vCount} Tagged</span>`;
            } else if (tCount > 0) {
                tagBadge = `<span class="font-bold text-xs bg-amber-50 text-amber-700 border border-amber-200/80 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-amber-500"></span>${tCount}/${vCount} Tagged</span>`;
            } else {
                tagBadge = `<span class="font-bold text-xs bg-rose-50 text-rose-700 border border-rose-200/80 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-rose-500"></span>No Tags Assigned</span>`;
            }

            return `
            <tr class="hover:bg-slate-50 transition-colors cursor-pointer group" onclick='openMemberFleetModal(${JSON.stringify(m).replace(/'/g, "&#39;")})'>
                <td class="p-3.5 pl-4">
                    ${m.Profile_pic ? `<img src="/${m.Profile_pic}" class="w-10 h-10 rounded-full object-cover border border-slate-200 shadow-sm">` :
                    `<div class="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center font-bold text-slate-700 text-sm shadow-xs">${initial}</div>`}
                </td>
                <td class="p-3.5">
                    <span class="font-mono text-xs font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg px-2.5 py-1 inline-block">${m.Mem_id}</span>
                </td>
                <td class="p-3.5">
                    <div class="font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">${m.Name}</div>
                    <div class="text-[11px] font-bold text-emerald-600 uppercase">Active Member</div>
                </td>
                <td class="p-3.5">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-bold text-xs bg-indigo-50 text-indigo-700 border border-indigo-200/80 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5">
                            <span class="w-1.5 h-1.5 rounded-full bg-indigo-600"></span>${vCount} ${vCount === 1 ? 'Vehicle' : 'Vehicles'}
                        </span>
                        ${platesPreview ? `<span class="text-xs text-slate-500 font-mono font-semibold truncate max-w-[200px]" title="${allPlates}">${platesPreview}</span>` : ''}
                    </div>
                </td>
                <td class="p-3.5">
                    ${tagBadge}
                </td>
                <td class="p-3.5 text-right pr-6" onclick="event.stopPropagation()">
                    <button type="button" onclick='openMemberFleetModal(${JSON.stringify(m).replace(/'/g, "&#39;")})'
                            class="text-xs font-bold text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded-xl px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 shadow-sm transition inline-flex items-center gap-1.5">
                        View Fleet &rarr;
                    </button>
                </td>
            </tr>`;
        }).join('');

        renderMemPagination(total, page, totalPages, currentMemLimit);
    } catch (err) {
        bodyEl.innerHTML = `<tr><td colspan="6" class="p-8 text-center text-rose-500 font-bold">Error loading members: ${err.message}</td></tr>`;
    }
}

function closeMemberFleetModal() {
    const modal = document.getElementById('memberFleetModal');
    if (modal) modal.classList.add('hidden');
}

function openMemberFleetModal(m) {
    const modal = document.getElementById('memberFleetModal');
    const content = document.getElementById('memberFleetModalContent');
    if (!modal || !content) return;

    const vehicles = m.vehicles || [];
    const initial = m.Name ? m.Name.charAt(0).toUpperCase() : '?';
    const vCount = vehicles.length;
    const taggedCount = vehicles.filter(v => v.E_tag_id && v.E_tag_id.trim()).length;

    content.innerHTML = `
    <div class="relative">
        <div class="h-2 rounded-t-3xl bg-gradient-to-r from-indigo-500 via-purple-500 to-emerald-500"></div>
        <div class="p-6 md:p-8">
            <div class="flex justify-between items-start border-b border-slate-200/80 pb-6 mb-6">
                <div class="flex items-center gap-5">
                    ${m.Profile_pic ? `<img src="/${m.Profile_pic}" class="w-16 h-16 rounded-2xl object-cover border border-slate-200 shadow-sm">` :
                    `<div class="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center font-black text-2xl text-slate-700 shadow-xs">${initial}</div>`}
                    <div>
                        <div class="flex items-center gap-3">
                            <h2 class="text-2xl font-black text-slate-900 tracking-tight">${m.Name}</h2>
                            <span class="font-mono text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-lg">#${m.Mem_id}</span>
                        </div>
                        <p class="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Karachi Gymkhana Club &bull; Member Vehicle Fleet</p>
                        <div class="flex gap-2 mt-2.5">
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase">Active Member</span>
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">${vCount} ${vCount === 1 ? 'Registered Vehicle' : 'Registered Vehicles'}</span>
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full ${taggedCount === vCount ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}">${taggedCount} of ${vCount} Tagged</span>
                        </div>
                    </div>
                </div>
                <button type="button" onclick="closeMemberFleetModal()" class="w-9 h-9 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-400 hover:text-slate-700 font-bold flex items-center justify-center text-xl transition">&times;</button>
            </div>

            <div class="flex justify-between items-center mb-5 flex-wrap gap-3">
                <div>
                    <h3 class="text-base font-extrabold text-slate-800">Authorized Vehicles</h3>
                    <p class="text-xs text-slate-500">All registered motor vehicles and RFID transponders authorized under this membership</p>
                </div>
                <button type="button" onclick='addVehicleToMember("${m.Mem_id}", "${m.Name.replace(/"/g, '&quot;')}", "${m.Profile_pic || ''}")'
                        class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-sm flex items-center gap-2 transition">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    Register Another Vehicle
                </button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                ${vehicles.map((v, idx) => {
                    const hasTag = v.E_tag_id && v.E_tag_id.trim().length > 0;
                    return `
                    <div class="bg-slate-50/70 border border-slate-200 hover:border-indigo-300 rounded-2xl p-5 transition shadow-xs flex flex-col justify-between">
                        <div>
                            <div class="flex justify-between items-start mb-3">
                                <div>
                                    <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Vehicle #${idx + 1}</span>
                                    <span class="font-mono font-extrabold text-xl text-indigo-700 bg-white border border-indigo-100 px-3 py-1 rounded-xl shadow-xs inline-block tracking-wider">${v.Car_number}</span>
                                </div>
                                <span class="text-[10px] font-black px-2.5 py-1 rounded-full ${hasTag ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-amber-100 text-amber-800 border border-amber-200'}">
                                    ${hasTag ? 'TAGGED' : 'NO TAG'}
                                </span>
                            </div>

                            <div class="mb-3">
                                <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-0.5">Make & Model</span>
                                <span class="text-sm font-bold text-slate-800">${v.Make_Model || 'Make/Model not specified'}</span>
                            </div>

                            <div class="bg-white border border-slate-200/80 rounded-xl p-3 mb-4 shadow-xs">
                                <div class="flex justify-between items-center mb-1">
                                    <span class="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">RFID EPC Transponder</span>
                                    ${hasTag ? '<span class="w-2 h-2 rounded-full bg-emerald-500"></span>' : '<span class="w-2 h-2 rounded-full bg-amber-400"></span>'}
                                </div>
                                ${hasTag ? `<span class="font-mono text-xs font-bold text-slate-800 break-all select-all">${v.E_tag_id}</span>` :
                                '<span class="text-xs text-amber-600 font-bold">No RFID tag assigned to this car</span>'}
                            </div>
                        </div>

                        <div class="flex justify-end gap-2 pt-3 border-t border-slate-200/60">
                            <button type="button" onclick='editVehicleFromFleet(${JSON.stringify(v).replace(/'/g, "&#39;")}, ${JSON.stringify(m).replace(/'/g, "&#39;")})'
                                    class="text-xs font-bold text-indigo-600 hover:text-indigo-800 bg-white hover:bg-indigo-50 border border-indigo-200 rounded-xl px-3.5 py-1.5 shadow-xs transition">
                                Edit Vehicle
                            </button>
                            <button type="button" onclick="delVehicleFromFleet(${v.id}, '${v.Car_number}', '${m.Mem_id}')"
                                    class="text-xs font-bold text-rose-600 hover:text-rose-800 bg-white hover:bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-1.5 shadow-xs transition">
                                Delete
                            </button>
                        </div>
                    </div>`;
                }).join('')}
            </div>

            <div class="mt-6 pt-4 border-t flex justify-end">
                <button type="button" onclick="closeMemberFleetModal()"
                        class="px-6 py-2.5 rounded-xl border border-slate-200 font-bold text-slate-700 bg-white hover:bg-slate-50 transition text-sm shadow-xs">
                    Close Fleet View
                </button>
            </div>
        </div>
    </div>`;

    modal.classList.remove('hidden');
}

function addVehicleToMember(memId, name, pic) {
    closeMemberFleetModal();
    cancelEdit();
    document.getElementById('nMemId').value = memId;
    document.getElementById('nName').value = name;
    if (pic) {
        document.getElementById('nPic').value = pic;
        document.getElementById('nPicPreview').src = '/' + pic;
        document.getElementById('nPicPreview').classList.remove('hidden');
        document.getElementById('picName').innerText = 'Photo on file';
    }
    document.getElementById('formTitle').innerText = 'Add Vehicle to ' + name;
    document.getElementById('formSubtitle').innerText = 'Registering additional car for Member #' + memId;
    document.getElementById('submitBtn').innerText = 'Register Vehicle';
    document.getElementById('submitBtn').className = 'bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3.5 rounded-xl font-bold col-span-2 shadow-lg';
    document.getElementById('cancelEditBtn').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function editVehicleFromFleet(v, m) {
    closeMemberFleetModal();
    editMember({
        ...v,
        Name: m.Name,
        Profile_pic: m.Profile_pic
    });
}

async function delVehicleFromFleet(id, carNumber, memId) {
    if (!confirm(`Are you sure you want to remove vehicle ${carNumber} from this member?`)) return;
    try {
        const res = await fetch('/api/members/' + id, { method: 'DELETE' });
        const data = await res.json();
        if (data.ok) {
            const fleetRes = await fetch('/api/members/' + encodeURIComponent(memId) + '/vehicles');
            if (fleetRes.ok) {
                const fleetData = await fleetRes.json();
                openMemberFleetModal({
                    Mem_id: fleetData.mem_id,
                    Name: fleetData.name,
                    Profile_pic: fleetData.profile_pic,
                    Status: fleetData.status,
                    vehicles: fleetData.vehicles
                });
            } else {
                closeMemberFleetModal();
            }
            loadMembers();
        } else {
            alert('Failed to delete vehicle: ' + (data.detail || 'Unknown error'));
        }
    } catch (e) {
        alert('Network error while deleting vehicle');
    }
}

function renderMemPagination(total, page, totalPages, limit) {
    const pagEl = document.getElementById('memPagination');
    if (!pagEl) return;
    if (total === 0) {
        pagEl.innerHTML = `<span class="text-xs text-slate-400">No entries to display</span>`;
        return;
    }

    const start = (page - 1) * limit + 1;
    const end = Math.min(page * limit, total);
    let btns = [];
    btns.push(`<button onclick="loadMembers(1)" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>First</button>`);
    btns.push(`<button onclick="loadMembers(${page - 1})" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Prev</button>`);

    let startPage = Math.max(1, page - 2);
    let endPage = Math.min(totalPages, page + 2);

    for (let p = startPage; p <= endPage; p++) {
        if (p === page) {
            btns.push(`<button class="px-3 py-1 text-xs border rounded-lg bg-indigo-600 text-white font-bold shadow-sm">${p}</button>`);
        } else {
            btns.push(`<button onclick="loadMembers(${p})" class="px-3 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm">${p}</button>`);
        }
    }

    btns.push(`<button onclick="loadMembers(${page + 1})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Next</button>`);
    btns.push(`<button onclick="loadMembers(${totalPages})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Last</button>`);

    pagEl.innerHTML = `
        <div class="flex justify-between items-center w-full flex-wrap gap-3">
            <div class="text-xs text-slate-500 font-medium">
                Showing <span class="font-bold text-slate-800">${start}</span> to <span class="font-bold text-slate-800">${end}</span> of <span class="font-bold text-slate-800">${total.toLocaleString()}</span> members (Page ${page} of ${totalPages})
            </div>
            <div class="flex gap-1 items-center">
                ${btns.join('')}
            </div>
        </div>
    `;
}

function editMember(m) {
    editingMemberRowId = m.id;
    editingMemberMemId = m.Mem_id;
    document.getElementById('editOldId').value = m.id;
    document.getElementById('nMemId').value = m.Mem_id;
    document.getElementById('nName').value = m.Name;
    document.getElementById('nCar').value = m.Car_number;
    document.getElementById('nMake').value = m.Make_Model || '';
    document.getElementById('nTag').value = m.E_tag_id;
    document.getElementById('nPic').value = m.Profile_pic || '';

    if (m.Profile_pic) {
        document.getElementById('nPicPreview').src = '/' + m.Profile_pic;
        document.getElementById('nPicPreview').classList.remove('hidden');
        document.getElementById('picName').innerText = 'Photo on file';
    } else {
        document.getElementById('nPicPreview').classList.add('hidden');
        document.getElementById('picName').innerText = '';
    }

    document.getElementById('formTitle').innerText = 'Edit Member: ' + m.Name;
    document.getElementById('formSubtitle').innerText = 'Modifying vehicle ' + m.Car_number + ' (Member #' + m.Mem_id + ')';
    document.getElementById('submitBtn').innerText = 'Update Vehicle & Tag';
    document.getElementById('submitBtn').className = 'bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3.5 rounded-xl font-bold col-span-2 shadow-lg';
    document.getElementById('cancelEditBtn').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function cancelEdit() {
    editingMemberRowId = null;
    editingMemberMemId = null;
    document.getElementById('memberForm').reset();
    document.getElementById('nPic').value = '';
    document.getElementById('nPicPreview').classList.add('hidden');
    document.getElementById('picName').innerText = '';
    document.getElementById('editOldId').value = '';
    document.getElementById('formTitle').innerText = 'Register New Member';
    document.getElementById('formSubtitle').innerText = 'Add member with vehicle license plate and RFID tag';
    document.getElementById('submitBtn').innerText = 'Add Member';
    document.getElementById('submitBtn').className = 'bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-3.5 rounded-xl font-bold col-span-2 shadow-md transition';
    document.getElementById('cancelEditBtn').classList.add('hidden');
}

async function submitMember(e) {
    e.preventDefault();
    const payload = {
        mem_id: document.getElementById('nMemId').value.trim(),
        name: document.getElementById('nName').value.trim(),
        car_number: document.getElementById('nCar').value.trim(),
        make_model: document.getElementById('nMake').value.trim(),
        e_tag_id: document.getElementById('nTag').value.trim().toUpperCase(),
        profile_pic: document.getElementById('nPic').value
    };

    if (!payload.mem_id || !payload.name || !payload.car_number || !payload.e_tag_id) {
        alert('Please fill in Member ID, Full Name, License Plate, and EPC Tag.');
        return;
    }

    try {
        let res;
        if (editingMemberRowId) {
            payload.id = editingMemberRowId;
            payload.old_mem_id = editingMemberMemId;
            res = await fetch('/api/update-member', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch('/api/add-member', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        let data = {};
        const text = await res.text();
        try {
            data = JSON.parse(text);
        } catch (pe) {
            data = { detail: text || ('Server status: ' + res.status) };
        }

        if (!res.ok) {
            alert(data.detail || data.message || 'Operation failed');
            return;
        }

        alert('Member registration saved successfully.');
        cancelEdit();
        loadMembers();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

const nPicFileEl = document.getElementById('nPicFile');
if (nPicFileEl) {
    nPicFileEl.addEventListener('change', async function() {
        if (!this.files[0]) return;
        const fd = new FormData();
        fd.append('file', this.files[0]);
        try {
            const res = await fetch('/api/upload-profile', { method: 'POST', body: fd });
            const data = await res.json();
            if (!res.ok) {
                alert(data.detail || 'Upload failed');
                return;
            }
            document.getElementById('nPic').value = data.path;
            document.getElementById('nPicPreview').src = '/' + data.path;
            document.getElementById('nPicPreview').classList.remove('hidden');
            document.getElementById('picName').innerText = 'Photo uploaded';
        } catch (e) {
            alert('Upload error: ' + e.message);
        }
    });
}

async function captureEPC(btn) {
    const status = document.getElementById('epcStatus');
    if (epcPollingInterval) {
        stopEpcCapture();
        return;
    }
    btn.innerText = 'Stop';
    btn.className = 'bg-rose-600 text-white px-4 py-2.5 rounded-lg font-bold text-xs whitespace-nowrap';
    await fetch('/api/enroll-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: true })
    });

    status.innerText = 'Enrollment mode active - present RFID tag at reader antenna...';
    status.className = 'text-xs mt-1 text-emerald-600 font-bold';
    let elapsed = 0;

    epcPollingInterval = setInterval(async () => {
        elapsed++;
        try {
            const res = await fetch('/api/waiting-tag');
            const d = await res.json();
            if (d.tag && d.enroll_mode) {
                document.getElementById('nTag').value = d.tag;
                status.innerText = `Tag captured: ${d.tag} (${d.time})`;
                stopEpcCapture();
                return;
            }
        } catch (e) {}

        if (elapsed > 45) {
            status.innerText = 'Enrollment timed out - please retry';
            status.className = 'text-xs mt-1 text-rose-600 font-bold';
            stopEpcCapture();
            return;
        }
        status.innerText = `Awaiting tag presentation... (${elapsed}s)`;
    }, 1000);
}

async function stopEpcCapture() {
    if (epcPollingInterval) {
        clearInterval(epcPollingInterval);
        epcPollingInterval = null;
    }
    await fetch('/api/enroll-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: false })
    });
    const btn = document.getElementById('epcBtn');
    if (btn) {
        btn.innerText = 'Read Tag';
        btn.className = 'bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2.5 rounded-lg font-bold text-xs whitespace-nowrap shadow-sm';
    }
}

async function importMembers() {
    const fileInput = document.getElementById('importFile');
    if (!fileInput || !fileInput.files[0]) {
        alert('Please choose a .csv or .xlsx spreadsheet file first.');
        return;
    }
    const box = document.getElementById('importResult');
    box.classList.remove('hidden');
    box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-slate-50 border text-slate-700';
    box.innerText = 'Processing file import...';

    const fd = new FormData();
    fd.append('file', fileInput.files[0]);

    try {
        const res = await fetch('/api/import-members', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) {
            box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-rose-50 border border-rose-200 text-rose-700';
            box.innerText = data.detail || 'Import failed';
            return;
        }
        let msg = `Successfully imported ${data.imported} of ${data.total_rows} entries (${data.skipped} skipped)`;
        if (data.errors && data.errors.length) {
            msg += `<br><span class="text-xs text-slate-500">${data.errors.join('<br>')}</span>`;
        }
        box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-700';
        box.innerHTML = msg;
        loadMembers();
    } catch (e) {
        box.innerText = 'Import error: ' + e.message;
    }
}

function downloadTemplate() {
    const csvContent = "Mem_id,Name,Car_number,Make_Model,E_tag_id,Profile_pic\n" +
                       "KG-0001,Ahmed Khan,BNC-916,Toyota Corolla,E2806890000000025799E539,\n" +
                       "KG-0002,Bilal Ahmed,BST-422,Honda Civic,E2806890000000025799E540,";
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'members_template.csv';
    a.click();
}

async function alignMemberPhotos() {
    const box = document.getElementById('importResult');
    if (box) {
        box.classList.remove('hidden');
        box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-slate-50 border text-slate-700';
        box.innerText = 'Aligning member profile photos from static/member_profile_img...';
    }
    try {
        const res = await fetch('/api/align-member-photos', { method: 'POST' });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            alert('Alignment error: ' + (data.detail || data.error || 'Failed to align photos'));
            return;
        }
        const msg = `Photo Alignment Complete: ${data.aligned_photos} matching photos found in static/member_profile_img out of ${data.total_members} members (${data.updated_records} records updated).`;
        if (box) {
            box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold';
            box.innerHTML = msg;
        } else {
            alert(msg);
        }
        loadMembers();
    } catch (e) {
        alert('Photo alignment error: ' + e.message);
    }
}

async function delMember(id, identifier) {
    if (!confirm(`Delete vehicle registration for ${identifier}? Associated RFID tag will no longer grant gate clearance.`)) return;
    try {
        const res = await fetch('/api/members/' + id, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) {
            alert(data.detail || 'Deletion failed');
            return;
        }
        loadMembers();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const s = await res.json();
        if (document.getElementById('setClubName')) document.getElementById('setClubName').value = s.club_name || '';
        if (document.getElementById('setCap')) document.getElementById('setCap').value = s.parking_capacity || '500';
        if (document.getElementById('setMsg')) document.getElementById('setMsg').value = s.traffic_msg || '';
        if (document.getElementById('setEntry')) document.getElementById('setEntry').value = s.entry_reader_ip || '';
        if (document.getElementById('setExit')) document.getElementById('setExit').value = s.exit_reader_ip || '';
        if (document.getElementById('setHik')) document.getElementById('setHik').value = s.hikvision_cam_url || '';
    } catch (e) {
        console.error('loadSettings error:', e);
    }
}

async function saveSettings() {
    const payload = {
        club_name: document.getElementById('setClubName')?.value || 'Karachi Gymkhana Club',
        parking_capacity: document.getElementById('setCap')?.value || '500',
        traffic_msg: document.getElementById('setMsg')?.value || '',
        entry_reader_ip: document.getElementById('setEntry')?.value || '',
        exit_reader_ip: document.getElementById('setExit')?.value || '',
        hikvision_cam_url: document.getElementById('setHik')?.value || ''
    };

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert('Settings persisted successfully. Restart background workers for IP adjustments to take effect.');
        } else {
            alert('Failed to save settings.');
        }
    } catch (err) {
        alert('Network error while saving settings: ' + err.message);
    }
}

let currentCamAuditPage = 1;
let currentCamAuditLimit = 24;
let currentCamAuditDate = '';

function setCamAuditPreset(preset) {
    const input = document.getElementById('camAuditDate');
    if (preset === 'all') {
        if (input) input.value = '';
        currentCamAuditDate = 'all';
    } else {
        const now = new Date();
        if (preset === 'yesterday') {
            now.setDate(now.getDate() - 1);
        }
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const val = `${year}-${month}-${day}`;
        if (input) input.value = val;
        currentCamAuditDate = val;
    }
    loadCameraAudit(1);
}

function changeCamAuditLimit() {
    const sel = document.getElementById('camAuditLimitSelect');
    if (sel) currentCamAuditLimit = parseInt(sel.value, 10) || 24;
    loadCameraAudit(1);
}

async function loadCameraAudit(page = currentCamAuditPage) {
    currentCamAuditPage = page;
    const inputVal = document.getElementById('camAuditDate')?.value;
    const dateParam = currentCamAuditDate === 'all' && !inputVal ? 'all' : (inputVal || '');
    const gridEl = document.getElementById('camAuditGrid');
    if (!gridEl) return;

    gridEl.innerHTML = `<div class="col-span-full py-16 text-center text-slate-400 font-bold">Loading camera proof logs...</div>`;

    try {
        const [logsRes, statsRes] = await Promise.all([
            fetch(`/api/camera-audit-logs?date=${encodeURIComponent(dateParam)}&page=${page}&limit=${currentCamAuditLimit}`),
            fetch('/api/camera-audit-stats')
        ]);
        const data = await logsRes.json();
        const stats = await statsRes.json();

        if (document.getElementById('camStatToday')) document.getElementById('camStatToday').innerText = (stats.today_total || 0).toLocaleString();
        if (document.getElementById('camStatWeek')) document.getElementById('camStatWeek').innerText = (stats.week_total || 0).toLocaleString();
        if (document.getElementById('camStatMonth')) document.getElementById('camStatMonth').innerText = (stats.month_total || 0).toLocaleString();
        if (document.getElementById('camBadgeDate')) document.getElementById('camBadgeDate').innerText = dateParam === 'all' ? 'All Time' : (data.date || 'Today');

        const logs = data.logs || [];
        const total = data.total || 0;
        const totalPages = data.pages || Math.ceil(total / currentCamAuditLimit) || 1;

        if (!logs.length) {
            gridEl.innerHTML = `<div class="col-span-full py-20 text-center bg-slate-50 border border-dashed border-slate-200 rounded-3xl">
                <p class="text-sm font-bold text-slate-500">No camera line-crossing proof captures found for ${dateParam === 'all' ? 'the selected filter' : data.date}.</p>
                <p class="text-xs text-slate-400 mt-1">Incoming snapshots sent by Hikvision line-crossing triggers are ingested automatically.</p>
            </div>`;
            renderCamAuditPagination(0, 1, 1, currentCamAuditLimit);
            return;
        }

        gridEl.innerHTML = logs.map(item => {
            const hikImgSrc = item.image_path ? '/' + item.image_path : '';
            const dirBadge = item.direction === 'Entry' ?
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-200">ENTRY</span>' :
                item.direction === 'Exit' ?
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-blue-100 text-blue-800 border border-blue-200">EXIT</span>' :
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-slate-100 text-slate-700 border border-slate-200">LINE CROSS</span>';

            const cleanFileName = item.image_path ? item.image_path.split('/').pop() : '';

            return `
            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden hover:shadow-md hover:border-slate-300 transition duration-200 flex flex-col group">
                <div class="relative bg-slate-900 aspect-video overflow-hidden cursor-pointer" onclick="openCamProofModal('${hikImgSrc}', '${item.timestamp}', '${item.direction}', '${item.event_type || 'Line Crossing'}')">
                    <img src="${hikImgSrc}" alt="Vehicle Proof" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" onerror="this.src='/static/img/no-car.svg'">
                    <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                        <span class="bg-white/90 text-slate-900 px-3 py-1.5 rounded-xl text-xs font-bold shadow-lg">View Proof</span>
                    </div>
                    <div class="absolute top-2.5 left-2.5">
                        ${dirBadge}
                    </div>
                    <div class="absolute bottom-2.5 right-2.5 flex items-center gap-1">
                        <span class="bg-slate-900/80 backdrop-blur-sm text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-md text-[10px] font-mono font-bold">
                            HIKVISION
                        </span>
                    </div>
                </div>
                <div class="p-4 flex-1 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-bold text-slate-800">${item.timestamp}</span>
                            <span class="text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200/60 px-2 py-0.5 rounded-md">${item.event_type || 'Line Crossing'}</span>
                        </div>
                        <p class="text-[11px] text-slate-400 font-mono mt-1.5 truncate" title="${cleanFileName}">${cleanFileName}</p>
                    </div>
                    <div class="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <span class="text-[11px] font-bold text-slate-500">Camera Audit Proof</span>
                        <button type="button" onclick="openCamProofModal('${hikImgSrc}', '${item.timestamp}', '${item.direction}', '${item.event_type || 'Line Crossing'}')" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 transition">
                            View Proof &rarr;
                        </button>
                    </div>
                </div>
            </div>`;
        }).join('');

        renderCamAuditPagination(total, page, totalPages, currentCamAuditLimit);
    } catch (err) {
        gridEl.innerHTML = `<div class="col-span-full py-12 text-center text-rose-500 font-bold">Error loading camera audits: ${err.message}</div>`;
    }
}

function renderCamAuditPagination(total, page, totalPages, limit) {
    const pagEl = document.getElementById('camAuditPagination');
    if (!pagEl) return;
    if (total === 0) {
        pagEl.innerHTML = `<span class="text-xs text-slate-400">No records to display</span>`;
        return;
    }

    const start = (page - 1) * limit + 1;
    const end = Math.min(page * limit, total);
    let btns = [];
    btns.push(`<button onclick="loadCameraAudit(1)" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>First</button>`);
    btns.push(`<button onclick="loadCameraAudit(${page - 1})" ${page === 1 ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Prev</button>`);

    let startPage = Math.max(1, page - 2);
    let endPage = Math.min(totalPages, page + 2);

    for (let p = startPage; p <= endPage; p++) {
        if (p === page) {
            btns.push(`<button class="px-3 py-1 text-xs border rounded-lg bg-indigo-600 text-white font-bold shadow-sm">${p}</button>`);
        } else {
            btns.push(`<button onclick="loadCameraAudit(${p})" class="px-3 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm">${p}</button>`);
        }
    }

    btns.push(`<button onclick="loadCameraAudit(${page + 1})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Next</button>`);
    btns.push(`<button onclick="loadCameraAudit(${totalPages})" ${page === totalPages ? 'disabled class="px-2.5 py-1 text-xs border rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed"' : 'class="px-2.5 py-1 text-xs border rounded-lg bg-white hover:bg-slate-50 font-bold text-slate-700 shadow-sm"'}>Last</button>`);

    pagEl.innerHTML = `
        <div class="flex items-center justify-between flex-wrap gap-3">
            <span class="text-xs font-bold text-slate-500">Showing <span class="font-mono text-slate-800">${start}-${end}</span> of <span class="font-mono text-slate-800">${total}</span> camera proof records</span>
            <div class="flex items-center gap-1.5">${btns.join('')}</div>
        </div>
    `;
}

function openCamProofModal(hikImgSrc, timestamp, direction, eventType) {
    const modal = document.getElementById('camProofModal');
    const hikImgEl = document.getElementById('camProofModalImgHik');
    const infoEl = document.getElementById('camProofModalInfo');
    if (!modal) return;

    if (hikImgEl) {
        hikImgEl.src = hikImgSrc || '';
        hikImgEl.onerror = () => { hikImgEl.src = '/static/img/no-car.svg'; };
    }

    if (infoEl) {
        infoEl.innerHTML = `
            <div class="flex items-center justify-between flex-wrap gap-2">
                <div>
                    <h3 class="text-sm font-bold text-slate-800">Hikvision Camera Proof</h3>
                    <p class="text-xs text-slate-400 font-mono mt-0.5">Recorded: ${timestamp || ''} PKT &bull; Event: ${eventType || 'Line Crossing'} &bull; Direction: ${direction || 'Line Crossing'}</p>
                </div>
                <div class="flex items-center gap-2">
                    ${hikImgSrc ? `<a href="${hikImgSrc}" download target="_blank" class="px-3 py-1.5 text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl hover:bg-emerald-100 transition">
                        Download Hikvision Overview
                    </a>` : ''}
                </div>
            </div>
        `;
    }
    modal.classList.remove('hidden');
}

function closeCamProofModal() {
    const modal = document.getElementById('camProofModal');
    if (modal) modal.classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadStats();
    loadCharts();
    loadHardware();
    loadActivity();
    loadMembers();
    loadSettings();
    loadAudit();

    const urlTab = new URLSearchParams(window.location.search).get('tab');
    if (urlTab === 'camera_audit') {
        const camBtn = document.querySelectorAll('.nav-btn')[2];
        switchTab('camera_audit', camBtn);
    } else if (urlTab === 'logs') {
        const logBtn = document.querySelectorAll('.nav-btn')[1];
        switchTab('logs', logBtn);
    }

    setInterval(loadStats, 5000);
    setInterval(loadCharts, 30000);
    setInterval(loadHardware, 3000);
    setInterval(loadActivity, 5000);
    setInterval(loadAudit, 15000);
});
