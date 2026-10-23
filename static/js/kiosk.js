let currentGate = 'gate01'; // 'gate01' (Rear Gate) or 'clubroad' (Main Gate)
let lastEntryLogId = 0;
let idleResetTimer = null;
let isUpdatingRecentEntries = false;
let isPollingEntryLogs = false;

function initGateSelection() {
    const urlParams = new URLSearchParams(window.location.search);
    const qGate = urlParams.get('gate');
    const path = window.location.pathname.toLowerCase();

    if (qGate) {
        if (qGate.toLowerCase().includes('club') || qGate.toLowerCase().includes('main')) {
            currentGate = 'clubroad';
        } else {
            currentGate = 'gate01';
        }
    } else if (path.includes('clubroad') || path.includes('main')) {
        currentGate = 'clubroad';
    } else if (path.includes('gate01') || path.includes('gate1') || path.includes('rear')) {
        currentGate = 'gate01';
    } else {
        const saved = localStorage.getItem('kiosk_gate');
        if (saved && (saved === 'clubroad' || saved === 'gate01')) {
            currentGate = saved;
        } else {
            currentGate = 'gate01';
        }
    }

    applyGateUI(currentGate);
}

function setKioskGate(gate) {
    const target = (gate === 'clubroad') ? 'clubroad' : 'gate01';
    if (currentGate === target) return;
    currentGate = target;
    try {
        localStorage.setItem('kiosk_gate', currentGate);
    } catch (e) {}

    const newUrl = new URL(window.location);
    newUrl.searchParams.set('gate', currentGate);
    window.history.replaceState({}, '', newUrl);

    applyGateUI(currentGate);
    lastEntryLogId = 0;

    // Reset view to idle mode for the new gate
    clearTimeout(idleResetTimer);
    const viewIdle = document.getElementById('viewIdle');
    const viewActive = document.getElementById('viewActive');
    if (viewActive) viewActive.classList.add('hidden');
    if (viewIdle) viewIdle.classList.remove('hidden');

    updateRecentEntries();
    pollEntryLogs();
}

function applyGateUI(gate) {
    const isClub = (gate === 'clubroad');

    const btnGate01 = document.getElementById('btnGate01');
    const btnClubRoad = document.getElementById('btnClubRoad');
    const gateSubtitle = document.getElementById('gateSubtitle');
    const gatePulseDot = document.getElementById('gatePulseDot');
    const gateStationBadge = document.getElementById('gateStationBadge');
    const telemetryLaneStatus = document.getElementById('telemetryLaneStatus');
    const recentFooterTitle = document.getElementById('recentFooterTitle');
    const kioskWelcome = document.getElementById('kioskWelcome');
    const kioskDescription = document.getElementById('kioskDescription');

    if (isClub) {
        document.title = "Club Road Gate Access Terminal - Karachi Gymkhana";
        if (btnGate01) {
            btnGate01.className = "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center gap-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100";
            const dot = btnGate01.querySelector('span');
            if (dot) dot.className = "w-2 h-2 rounded-full bg-slate-400";
        }
        if (btnClubRoad) {
            btnClubRoad.className = "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center gap-2 bg-indigo-600 text-white shadow-md";
            const dot = btnClubRoad.querySelector('span');
            if (dot) dot.className = "w-2 h-2 rounded-full bg-white animate-pulse";
        }
        if (gateSubtitle) gateSubtitle.innerHTML = 'RFID Smart Access Terminal &bull; Club Road Gate (Main Gate)';
        if (gatePulseDot) gatePulseDot.className = 'inline-block w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse';
        if (gateStationBadge) gateStationBadge.innerText = 'CLUB ROAD GATE (MAIN GATE) • FAST-TRACK';
        if (telemetryLaneStatus) telemetryLaneStatus.innerText = 'Club Road Main Lane';
        if (recentFooterTitle) recentFooterTitle.innerText = 'Recent Club Road Gate RFID Activity';
        if (kioskWelcome) kioskWelcome.innerText = 'Club Road Gate • Approach For Clearance';
        if (kioskDescription) kioskDescription.innerText = 'Club Road contactless RFID access lane armed. Please slow down to 5 km/h for instant barrier clearance.';
    } else {
        document.title = "Gate 01 (Rear Gate) Terminal - Karachi Gymkhana";
        if (btnGate01) {
            btnGate01.className = "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center gap-2 bg-emerald-600 text-white shadow-md";
            const dot = btnGate01.querySelector('span');
            if (dot) dot.className = "w-2 h-2 rounded-full bg-white animate-pulse";
        }
        if (btnClubRoad) {
            btnClubRoad.className = "px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center gap-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100";
            const dot = btnClubRoad.querySelector('span');
            if (dot) dot.className = "w-2 h-2 rounded-full bg-slate-400";
        }
        if (gateSubtitle) gateSubtitle.innerHTML = 'RFID Smart Access Terminal &bull; Gate 01 (Rear Gate)';
        if (gatePulseDot) gatePulseDot.className = 'inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse';
        if (gateStationBadge) gateStationBadge.innerText = 'GATE 01 (REAR GATE) • FAST-TRACK';
        if (telemetryLaneStatus) telemetryLaneStatus.innerText = 'Gate 01 Rear Lane';
        if (recentFooterTitle) recentFooterTitle.innerText = 'Recent Gate 01 (Rear Gate) RFID Activity';
        if (kioskWelcome) kioskWelcome.innerText = 'Gate 01 (Rear Gate) • Approach For Clearance';
        if (kioskDescription) kioskDescription.innerText = 'Fast-track contactless RFID access lane armed. Please slow down to 5 km/h for instant barrier clearance.';
    }
}

function toggleFullScreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(err => console.log(err));
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
}

function updateClock() {
    const now = new Date();
    let hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    const hoursStr = String(hours).padStart(2, '0');

    const clockEl = document.getElementById('kioskClock');
    const ampmEl = document.getElementById('kioskAmpm');
    const dateEl = document.getElementById('kioskDate');

    if (clockEl) clockEl.innerText = `${hoursStr}:${minutes}:${seconds}`;
    if (ampmEl) ampmEl.innerText = ampm;
    if (dateEl) {
        dateEl.innerText = now.toLocaleDateString('en-US', {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    }
}
setInterval(updateClock, 1000);
updateClock();

async function fetchOccupancy() {
    try {
        const [settingsRes, statsRes] = await Promise.all([
            fetch('/api/settings'),
            fetch('/api/stats')
        ]);
        const settings = await settingsRes.json();
        const stats = await statsRes.json();

        const capacity = parseInt(settings.parking_capacity || '500', 10);
        const inside = parseInt(stats.currently_in_club || '0', 10);
        const available = Math.max(0, capacity - inside);

        const slotsEl = document.getElementById('slotsCount');
        const totalEl = document.getElementById('totalSlots');
        const titleEl = document.getElementById('clubTitle');

        if (slotsEl) slotsEl.innerText = available;
        if (totalEl) totalEl.innerText = capacity;
        if (titleEl && settings.club_name) titleEl.innerText = settings.club_name.toUpperCase();
    } catch (err) {
        console.error('Failed to update facility occupancy:', err);
    }
}
setInterval(fetchOccupancy, 5000);
fetchOccupancy();

function formatTimestamp(ts) {
    if (!ts) return 'Just now';
    try {
        const cleaned = String(ts).replace('T', ' ');
        const parts = cleaned.split(' ');
        if (parts.length >= 2) {
            const timeParts = parts[1].split(':');
            let hour = parseInt(timeParts[0], 10);
            const minute = timeParts[1];
            const ampm = hour >= 12 ? 'PM' : 'AM';
            hour = hour % 12 || 12;
            const hourStr = hour < 10 ? '0' + hour : String(hour);
            return `${hourStr}:${minute} ${ampm}`;
        }
        return ts;
    } catch (e) {
        return ts;
    }
}

function renderLicensePlate(carNum) {
    const plateSeriesEl = document.getElementById('plateSeries');
    const plateDigitsEl = document.getElementById('plateDigits');
    const plateRawEl = document.getElementById('plateNumber');

    const clean = (carNum || '').trim().toUpperCase();
    if (plateRawEl) plateRawEl.innerText = clean || '--';

    if (!clean || clean === '--' || clean === 'NO TAG') {
        if (plateSeriesEl) {
            plateSeriesEl.innerText = '---';
            plateSeriesEl.classList.remove('hidden');
        }
        if (plateDigitsEl) plateDigitsEl.innerText = '---';
        return;
    }

    const parts = clean.split(/[-_\s]+/);
    if (parts.length >= 2) {
        if (plateSeriesEl) {
            plateSeriesEl.innerText = parts[0];
            plateSeriesEl.classList.remove('hidden');
        }
        if (plateDigitsEl) plateDigitsEl.innerText = parts.slice(1).join(' ');
    } else {
        if (plateSeriesEl) {
            plateSeriesEl.innerText = '';
            plateSeriesEl.classList.add('hidden');
        }
        if (plateDigitsEl) plateDigitsEl.innerText = clean;
    }
}

function renderMiniSindhPlate(carNum, isUnreg) {
    const clean = (carNum || '').trim().toUpperCase();
    if (!clean || clean === '--' || clean === 'NO TAG') {
        return `
            <div class="mini-sindh-plate w-32 h-10 shrink-0">
                <div class="mini-ajrak-banner"></div>
                <div class="flex-1 flex items-center justify-center px-1">
                    <span class="mini-plate-emboss text-[10px] font-mono font-black text-slate-400">NO PLATE</span>
                </div>
                <div class="text-center py-0.2 bg-slate-100/90 border-t border-slate-200">
                    <span class="text-[6.5px] font-black tracking-[0.25em] text-slate-800 uppercase font-mono leading-none block">SINDH</span>
                </div>
            </div>
        `;
    }

    if (isUnreg || clean.length > 10 || clean.startsWith('E2')) {
        const shortTag = clean.length > 10 ? clean.substring(0, 4) + '..' + clean.slice(-4) : clean;
        return `
            <div class="mini-sindh-plate w-32 h-10 shrink-0 shadow-xs group-hover:shadow transition-shadow">
                <div class="mini-ajrak-banner"></div>
                <div class="flex-1 flex items-center justify-center gap-1 px-1 my-0.5">
                    <span class="mini-plate-emboss text-[10px] tracking-tight font-mono uppercase">${shortTag}</span>
                </div>
                <div class="text-center py-0.2 bg-slate-100/90 border-t border-slate-200">
                    <span class="text-[6.5px] font-black tracking-[0.25em] text-slate-900 uppercase font-mono leading-none block">SINDH</span>
                </div>
            </div>
        `;
    }

    let series = '';
    let digits = '';
    const parts = clean.split(/[-_\s]+/);
    if (parts.length >= 2) {
        series = parts[0];
        digits = parts.slice(1).join(' ');
    } else {
        digits = clean;
    }

    return `
        <div class="mini-sindh-plate w-34 h-10 shrink-0 shadow-xs group-hover:shadow transition-shadow">
            <div class="mini-ajrak-banner"></div>
            <div class="flex-1 flex items-center justify-center gap-1.5 px-1 my-0.5">
                ${series ? `<span class="mini-plate-emboss text-xs tracking-tight uppercase">${series}</span>` : ''}
                <div class="w-3.5 h-3.5 rounded-full bg-gradient-to-tr from-amber-500 via-yellow-400 to-amber-200 border border-amber-600 shadow-xs flex items-center justify-center shrink-0">
                    <div class="w-1.5 h-1.5 rounded-full bg-amber-950/80"></div>
                </div>
                <span class="mini-plate-emboss text-xs tracking-tight uppercase">${digits}</span>
            </div>
            <div class="text-center py-0.2 bg-slate-100/90 border-t border-slate-200">
                <span class="text-[7px] font-black tracking-[0.3em] text-slate-900 uppercase font-mono leading-none block">SINDH</span>
            </div>
        </div>
    `;
}

async function updateRecentEntries() {
    if (isUpdatingRecentEntries) return;
    const reqGate = currentGate;
    isUpdatingRecentEntries = true;
    try {
        const res = await fetch(`/api/recent-entries?limit=4&gate=${encodeURIComponent(reqGate)}`);
        if (!res.ok) return;
        let entries = await res.json();
        if (reqGate !== currentGate) return;

        const container = document.getElementById('recentCardsContainer');
        if (!container) return;

        // Strictly filter out any system clearance or auto midnight records
        if (Array.isArray(entries)) {
            entries = entries.filter(e => {
                const acc = (e.access_type || '').toLowerCase();
                const gate = (e.gate_no || '').toLowerCase();
                return !acc.includes('midnight') && !acc.includes('clearance') && !acc.includes('bulk') &&
                       !gate.includes('system') && !gate.includes('clearance') && !gate.includes('bulk');
            });
        }

        window.currentRecentEntries = entries || [];

        if (!entries || entries.length === 0) {
            const gateNameText = currentGate === 'clubroad' ? 'Club Road Gate' : 'Gate 01 (Rear Gate)';
            container.innerHTML = `
                <div class="col-span-4 kiosk-card p-6 rounded-2xl text-center text-slate-400 font-semibold text-xs tracking-wider uppercase border border-slate-200">
                    No recent RFID activity recorded at ${gateNameText} today
                </div>
            `;
            return;
        }

        container.innerHTML = entries.map((entry, idx) => {
            const acc = entry.access_type || '';
            const memId = String(entry.mem_id || '').trim();
            const tag = (entry.scanned_tag || '').toUpperCase();
            const name = String(entry.name || '').trim();

            const isMember = Boolean(
                memId &&
                !['GUEST-LOG', 'AI-CAM', 'UNREGISTERED', 'NHA-MTAG', 'SOCIETY-TAG', 'FLEET-TAG', 'CLUB-STOCK', ''].includes(memId) &&
                !name.toLowerCase().includes('unregistered') &&
                !acc.toLowerCase().includes('unregistered') &&
                !acc.toLowerCase().includes('unknown') &&
                !acc.toLowerCase().includes('no rfid')
            );

            const isNHA = !isMember && (acc.includes('NHA') || acc.includes('M-Tag') || memId === 'NHA-MTAG' || tag.startsWith('E2801105') || tag.startsWith('E2801114'));
            const isSociety = !isMember && (acc.includes('Society') || acc.includes('Resident') || memId === 'SOCIETY-TAG' || tag.startsWith('E2803821') || tag.startsWith('E2003412'));
            const isCommercial = !isMember && (acc.includes('Commercial') || acc.includes('Fleet') || memId === 'FLEET-TAG' || tag.startsWith('E280F336'));
            const isStock = !isMember && (acc.includes('Club Tag') || acc.includes('Spare') || acc.includes('Unassigned') || memId === 'CLUB-STOCK' || tag.startsWith('E28068940') || tag.startsWith('E28068900'));
            const isUnreg = !isMember;

            const displayName = isUnreg ? 'Unregistered Vehicle' : (entry.name || 'Member');
            const plate = isUnreg ? (entry.scanned_tag || 'NO TAG') : (entry.vehicle_number || '--');
            const timeStr = formatTimestamp(entry.timestamp);
            const dir = entry.direction || 'Entry';
            const isExit = dir.toLowerCase() === 'exit';
            const gateLabel = entry.gate_no || (currentGate === 'clubroad' ? 'Club Road' : 'Gate-01');

            // Distinct Direction Badges & Borders
            let badgeClass = 'bg-emerald-100 text-emerald-800 border-emerald-300';
            let badgeIcon = '↓';
            let badgeLabel = 'ENTRY';
            let cardBorder = 'border-slate-200/90';

            if (isUnreg) {
                badgeClass = 'bg-rose-100 text-rose-800 border-rose-300';
                badgeIcon = '⚠️';
                badgeLabel = isNHA ? 'M-TAG' : isSociety ? 'SOCIETY' : isCommercial ? 'FLEET' : isStock ? 'STOCK' : 'ALERT';
                cardBorder = 'border-rose-200';
            } else if (isExit) {
                badgeClass = 'bg-blue-100 text-blue-800 border-blue-300';
                badgeIcon = '↑';
                badgeLabel = 'EXIT';
                cardBorder = 'border-blue-100';
            } else {
                cardBorder = 'border-emerald-100';
            }

            // Initials for avatar fallback
            let initials = 'KG';
            if (displayName && displayName !== 'Unregistered Vehicle') {
                const words = displayName.trim().split(/\s+/);
                if (words.length >= 2) {
                    initials = (words[0][0] + words[1][0]).toUpperCase();
                } else if (words.length === 1 && words[0].length >= 2) {
                    initials = words[0].substring(0, 2).toUpperCase();
                }
            }

            const picUrl = entry.profile_pic ? '/' + entry.profile_pic.replace(/\\/g, '/') : null;
            const makeModel = entry.make_model || (isUnreg ? 'Unknown Vehicle' : 'Registered Member');

            return `
                <div onclick="selectRecentCard(${idx})" class="kiosk-card p-3 rounded-2xl border ${cardBorder} hover:border-indigo-400 hover:shadow-lg cursor-pointer transition-all flex flex-col justify-between shadow-xs active:scale-[0.98] group relative overflow-hidden bg-white/95" title="Click to view full details on main terminal">
                    <div class="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-slate-100/50 to-transparent rounded-bl-3xl pointer-events-none"></div>
                    
                    <!-- Top Bar: Direction Pill + Timestamp -->
                    <div class="flex items-center justify-between mb-2">
                        <span class="text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border ${badgeClass} flex items-center gap-1 shadow-2xs">
                            <span class="font-bold leading-none">${badgeIcon}</span>
                            <span>${badgeLabel}</span>
                        </span>
                        <span class="text-[11px] font-mono font-extrabold text-slate-400 group-hover:text-indigo-600 transition-colors">${timeStr}</span>
                    </div>

                    <!-- Middle: Member Profile Photo + Name + ID -->
                    <div class="flex items-center gap-2.5 mb-2.5">
                        ${picUrl ? `
                            <img src="${picUrl}" alt="${displayName}" class="w-10 h-10 rounded-xl object-cover border-2 border-slate-200/90 shadow-sm shrink-0" onerror="this.outerHTML='<div class=\\'w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-50 to-slate-100 border-2 border-slate-200/90 shadow-sm flex items-center justify-center font-black text-xs text-indigo-700 shrink-0\\'>${initials}</div>'">
                        ` : `
                            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-50 to-slate-100 border-2 border-slate-200/90 shadow-sm flex items-center justify-center font-black text-xs text-indigo-700 shrink-0">
                                ${initials}
                            </div>
                        `}
                        <div class="min-w-0 flex-1">
                            <h5 class="text-xs font-black text-slate-900 truncate leading-tight group-hover:text-indigo-950 transition-colors">${displayName}</h5>
                            <div class="flex items-center gap-1 text-[10px] text-slate-500 font-mono mt-0.5 truncate">
                                ${isMember ? `<span class="font-black text-indigo-600 bg-indigo-50 px-1 py-0.2 rounded border border-indigo-200/70">${memId}</span>` : ''}
                                <span class="truncate text-slate-400 font-bold">${makeModel}</span>
                            </div>
                        </div>
                    </div>

                    <!-- Bottom: Miniature Authentic Sindh License Plate + Gate Indicator -->
                    <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                        ${renderMiniSindhPlate(plate, isUnreg)}
                        <div class="flex flex-col items-end justify-center text-right shrink-0">
                            <span class="text-[9px] font-extrabold text-slate-400 group-hover:text-indigo-600 uppercase tracking-tight truncate max-w-[80px]" title="${gateLabel}">${gateLabel}</span>
                            <span class="text-[9px] font-black text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity">VIEW ↗</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Error fetching recent entry cards:', err);
    } finally {
        isUpdatingRecentEntries = false;
    }
}

function selectRecentCard(idx) {
    if (window.currentRecentEntries && window.currentRecentEntries[idx]) {
        displayEntry(window.currentRecentEntries[idx]);
    }
}

function displayEntry(log) {
    clearTimeout(idleResetTimer);

    const viewIdle = document.getElementById('viewIdle');
    const viewActive = document.getElementById('viewActive');
    if (!viewIdle || !viewActive) return;

    viewIdle.classList.add('hidden');
    viewActive.classList.remove('hidden');

    const activeReaderBadge = document.getElementById('activeReaderBadge');
    if (activeReaderBadge) {
        const readerText = log.gate_no || (currentGate === 'clubroad' ? 'Club Road Reader' : 'Gate-01 Reader');
        activeReaderBadge.innerText = `READER: ${readerText.toUpperCase()}`;
    }

    const isUnregistered = (log.access_type || '').includes('Unknown') || 
                           (log.access_type || '').includes('Unregistered') ||
                           (log.access_type || '').includes('No RFID') || 
                           (log.name || '').includes('Unregistered') ||
                           (log.mem_id || '').includes('UNREGISTERED') ||
                           (log.mem_id || '').includes('GUEST') ||
                           ['NHA-MTAG', 'SOCIETY-TAG', 'FLEET-TAG', 'CLUB-STOCK'].includes(log.mem_id || '');

    const direction = log.direction || 'Entry';
    const isExit = direction.toLowerCase() === 'exit';

    const entryTimestamp = document.getElementById('entryTimestamp');
    const badgeText = document.getElementById('badgeText');
    const statusBadge = document.getElementById('statusBadge');
    const badgeIcon = document.getElementById('badgeIcon');
    const accentBar = document.getElementById('accentBar');
    const ambientGlowTop = document.getElementById('ambientGlowTop');
    const driverPhotoFrame = document.getElementById('driverPhotoFrame');
    const photoStatusDot = document.getElementById('photoStatusDot');
    const sindhPlateBox = document.getElementById('sindhPlateBox');
    const barrierStatusText = document.getElementById('barrierStatusText');

    const memberDisplayContainer = document.getElementById('memberDisplayContainer');
    const unregisteredDisplayContainer = document.getElementById('unregisteredDisplayContainer');

    if (entryTimestamp) entryTimestamp.innerText = formatTimestamp(log.timestamp);

    if (isUnregistered) {
        // Hide member container, show unregistered container
        if (memberDisplayContainer) memberDisplayContainer.classList.add('hidden');
        if (unregisteredDisplayContainer) unregisteredDisplayContainer.classList.remove('hidden');

        // UNREGISTERED CAR DETECTED keyword preserved
        const unregTagId = document.getElementById('unregisteredTagId');
        if (unregTagId) unregTagId.innerText = log.scanned_tag || 'NO TAG DETECTED';

        const unregDirectionBadge = document.getElementById('unregDirectionBadge');
        if (unregDirectionBadge) {
            let flagNote = '';
            const acc = log.access_type || '';
            const tag = (log.scanned_tag || '').toUpperCase();
            if (acc.includes('NHA') || tag.startsWith('E2801105') || tag.startsWith('E2801114')) flagNote = ' • 🚗 NHA M-TAG';
            else if (acc.includes('Society') || tag.startsWith('E2803821') || tag.startsWith('E2003412')) flagNote = ' • 🏢 SOCIETY TAG';
            else if (acc.includes('Commercial') || tag.startsWith('E280F336')) flagNote = ' • 🚚 COMMERCIAL TAG';
            else if (acc.includes('Club Tag') || acc.includes('Spare') || tag.startsWith('E28068940') || tag.startsWith('E20047')) flagNote = ' • 🎫 SPARE CLUB TAG';
            unregDirectionBadge.innerText = `UNREGISTERED CAR DETECTED • ${direction.toUpperCase()} ATTEMPT${flagNote}`;
        }

        viewActive.className = "w-full max-w-6xl kiosk-panel rounded-3xl p-6 lg:p-7 border-2 border-rose-500 shadow-2xl shadow-rose-500/15 relative overflow-hidden transition-all duration-500 terminal-alert-theme bg-gradient-to-b from-rose-50/25 via-white to-slate-50";

        if (ambientGlowTop) {
            ambientGlowTop.className = 'ambient-glow bg-rose-500 w-[650px] h-[650px] -top-40 -left-40 z-0 opacity-40';
        }
        if (statusBadge) {
            statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest bg-rose-600 text-white border-2 border-rose-700 shadow-lg shadow-rose-500/30';
        }
        if (badgeIcon) {
            badgeIcon.className = 'w-3 h-3 rounded-full bg-rose-200 animate-ping';
        }
        if (badgeText) {
            badgeText.innerText = `UNREGISTERED CAR DETECTED • ${direction.toUpperCase()} HELD`;
        }
        if (accentBar) {
            accentBar.className = 'absolute top-0 left-0 w-full h-3.5 bg-gradient-to-r from-rose-600 via-amber-500 to-rose-600 shadow-sm';
        }
    } else {
        // Show member container, hide unregistered container
        if (memberDisplayContainer) memberDisplayContainer.classList.remove('hidden');
        if (unregisteredDisplayContainer) unregisteredDisplayContainer.classList.add('hidden');

        const driverName = document.getElementById('driverName');
        const memberIdVal = document.getElementById('memberIdVal');
        const vehicleMake = document.getElementById('vehicleMake');
        const epcTag = document.getElementById('epcTag');
        const driverPhoto = document.getElementById('driverPhoto');
        const driverAvatar = document.getElementById('driverAvatar');
        const memberRoleTag = document.getElementById('memberRoleTag');

        if (driverName) driverName.innerText = log.name || '--';
        if (memberIdVal) memberIdVal.innerText = log.mem_id || 'KG-MEM';
        if (vehicleMake) vehicleMake.innerText = log.make_model || 'Registered Vehicle';
        if (epcTag) epcTag.innerText = log.scanned_tag || 'EPC DETECTED';

        renderLicensePlate(log.vehicle_number);

        if (log.profile_pic) {
            if (driverPhoto) {
                driverPhoto.src = '/' + log.profile_pic.replace(/\\/g, '/');
                driverPhoto.classList.remove('hidden');
            }
            if (driverAvatar) driverAvatar.classList.add('hidden');
        } else {
            if (driverPhoto) driverPhoto.classList.add('hidden');
            if (driverAvatar) {
                driverAvatar.classList.remove('hidden');
                driverAvatar.className = 'w-32 h-32 lg:w-36 lg:h-36 rounded-[22px] bg-gradient-to-br from-indigo-50 to-slate-100 border-2 border-white flex items-center justify-center font-black text-4xl text-indigo-700 shadow-inner';
                driverAvatar.innerText = log.name ? log.name.substring(0, 2).toUpperCase() : 'KG';
            }
        }

        if (isExit) {
            // ==========================================
            // EXIT (DEPARTURE) DISTINCT STYLING: ELECTRIC SAPPHIRE / AZURE
            // ==========================================
            viewActive.className = "w-full max-w-6xl kiosk-panel rounded-3xl p-6 lg:p-7 border-2 border-blue-500/80 shadow-2xl shadow-blue-500/15 relative overflow-hidden transition-all duration-500 terminal-exit-theme bg-gradient-to-b from-blue-50/20 via-white to-slate-50";

            if (ambientGlowTop) {
                ambientGlowTop.className = 'ambient-glow bg-blue-600 w-[650px] h-[650px] -top-40 -left-40 z-0 opacity-40';
            }
            if (statusBadge) {
                statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest bg-blue-600 text-white border-2 border-blue-700 shadow-lg shadow-blue-500/30';
            }
            if (badgeIcon) {
                badgeIcon.className = 'w-3 h-3 rounded-full bg-cyan-300 animate-ping';
            }
            if (badgeText) {
                badgeText.innerHTML = '<span class="text-base mr-1">↑</span> VEHICLE DEPARTURE • CLEARANCE GRANTED • FAREWELL';
            }
            if (accentBar) {
                accentBar.className = 'absolute top-0 left-0 w-full h-3.5 bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 shadow-sm';
            }
            if (memberRoleTag) {
                memberRoleTag.className = 'text-[11px] font-black uppercase tracking-widest px-3.5 py-1.5 rounded-xl bg-blue-100 text-blue-900 border border-blue-300 flex items-center gap-1.5';
                memberRoleTag.innerHTML = '<span>↑ EXIT VERIFIED</span> &bull; <span>GOODBYE &amp; SAFE JOURNEY</span>';
            }
            if (driverPhotoFrame) {
                driverPhotoFrame.className = 'p-1.5 rounded-3xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 shadow-xl shadow-blue-500/30 transition-all duration-300';
            }
            if (photoStatusDot) {
                photoStatusDot.className = 'absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-blue-600 border-2 border-white shadow-md flex items-center justify-center text-white font-black text-xs';
                photoStatusDot.innerHTML = '↑';
            }
            if (sindhPlateBox) {
                sindhPlateBox.className = 'sindh-license-plate h-32 flex flex-col justify-between shadow-xl ring-4 ring-blue-500/30 border-blue-700 transition-all duration-300';
            }
            if (barrierStatusText) {
                barrierStatusText.className = 'font-black text-blue-700 flex items-center gap-1.5 text-xs';
                barrierStatusText.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-blue-600 animate-pulse"></span> RAISED / CLEARANCE OPEN &bull; FAREWELL';
            }
        } else {
            // ==========================================
            // ENTRY (ARRIVAL) DISTINCT STYLING: LUSH EMERALD / TEAL
            // ==========================================
            viewActive.className = "w-full max-w-6xl kiosk-panel rounded-3xl p-6 lg:p-7 border-2 border-emerald-500/80 shadow-2xl shadow-emerald-500/15 relative overflow-hidden transition-all duration-500 terminal-entry-theme bg-gradient-to-b from-emerald-50/20 via-white to-slate-50";

            if (ambientGlowTop) {
                ambientGlowTop.className = 'ambient-glow bg-emerald-500 w-[650px] h-[650px] -top-40 -left-40 z-0 opacity-40';
            }
            if (statusBadge) {
                statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest bg-emerald-600 text-white border-2 border-emerald-700 shadow-lg shadow-emerald-500/30';
            }
            if (badgeIcon) {
                badgeIcon.className = 'w-3 h-3 rounded-full bg-emerald-200 animate-ping';
            }
            if (badgeText) {
                badgeText.innerHTML = '<span class="text-base mr-1">↓</span> VEHICLE ARRIVAL • ACCESS GRANTED • WELCOME';
            }
            if (accentBar) {
                accentBar.className = 'absolute top-0 left-0 w-full h-3.5 bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-600 shadow-sm';
            }
            if (memberRoleTag) {
                memberRoleTag.className = 'text-[11px] font-black uppercase tracking-widest px-3.5 py-1.5 rounded-xl bg-emerald-100 text-emerald-900 border border-emerald-300 flex items-center gap-1.5';
                memberRoleTag.innerHTML = '<span>↓ ENTRY VERIFIED</span> &bull; <span>WELCOME TO KARACHI GYMKHANA</span>';
            }
            if (driverPhotoFrame) {
                driverPhotoFrame.className = 'p-1.5 rounded-3xl bg-gradient-to-tr from-emerald-500 via-teal-400 to-emerald-600 shadow-xl shadow-emerald-500/30 transition-all duration-300';
            }
            if (photoStatusDot) {
                photoStatusDot.className = 'absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-emerald-600 border-2 border-white shadow-md flex items-center justify-center text-white font-black text-xs';
                photoStatusDot.innerHTML = '↓';
            }
            if (sindhPlateBox) {
                sindhPlateBox.className = 'sindh-license-plate h-32 flex flex-col justify-between shadow-xl ring-4 ring-emerald-500/30 border-emerald-700 transition-all duration-300';
            }
            if (barrierStatusText) {
                barrierStatusText.className = 'font-black text-emerald-700 flex items-center gap-1.5 text-xs';
                barrierStatusText.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span> RAISED / PASSAGE OPEN &bull; WELCOME IN';
            }
        }
    }

    idleResetTimer = setTimeout(() => {
        viewActive.classList.add('hidden');
        viewIdle.classList.remove('hidden');
    }, 15000);
}

async function pollEntryLogs() {
    if (isPollingEntryLogs) return;
    const reqGate = currentGate;
    isPollingEntryLogs = true;
    try {
        const res = await fetch(`/api/latest-log?gate=${encodeURIComponent(reqGate)}`);
        if (!res.ok) return;
        const latest = await res.json();
        // If gate was switched while request was in-flight, ignore
        if (reqGate !== currentGate) return;
        if (!latest || !latest.id) return;

        // On first load or gate switch: display the latest passage event immediately!
        if (lastEntryLogId === 0) {
            lastEntryLogId = latest.id;
            displayEntry(latest);
            return;
        }

        if (latest.id !== lastEntryLogId) {
            lastEntryLogId = latest.id;
            displayEntry(latest);
            updateRecentEntries();
        }
    } catch (err) {
        console.error('Error polling entry logs:', err);
    } finally {
        isPollingEntryLogs = false;
    }
}

// 1. Initialize gate selection from URL / localStorage FIRST
initGateSelection();

// 2. Fetch initial recent cards and start polling in strict sequence
updateRecentEntries();
pollEntryLogs();

// 3. Register repeating background intervals
setInterval(updateRecentEntries, 3000);
setInterval(pollEntryLogs, 750);

