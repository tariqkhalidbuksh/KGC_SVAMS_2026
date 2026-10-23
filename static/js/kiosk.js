let currentGate = 'gate01'; // 'gate01' (Rear Gate) or 'clubroad' (Main Gate)
let lastEntryLogId = 0;
let idleResetTimer = null;
let recentEntriesReqSeq = 0;
let pollLogsReqSeq = 0;

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

async function updateRecentEntries() {
    const reqSeq = ++recentEntriesReqSeq;
    const reqGate = currentGate;
    try {
        const res = await fetch(`/api/recent-entries?limit=4&gate=${encodeURIComponent(reqGate)}`);
        if (!res.ok) return;
        let entries = await res.json();
        // Discard stale responses from older gate requests
        if (reqSeq !== recentEntriesReqSeq || reqGate !== currentGate) return;

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

        if (!entries || entries.length === 0) {
            const gateNameText = currentGate === 'clubroad' ? 'Club Road Gate' : 'Gate 01 (Rear Gate)';
            container.innerHTML = `
                <div class="col-span-4 kiosk-card p-6 rounded-2xl text-center text-slate-400 font-semibold text-xs tracking-wider uppercase border border-slate-200">
                    No recent RFID activity recorded at ${gateNameText} today
                </div>
            `;
            return;
        }

        container.innerHTML = entries.map(entry => {
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
            let tagSignature = '';
            if (isNHA) tagSignature = '🚗 NHA M-Tag';
            else if (isSociety) tagSignature = '🏢 Society Tag';
            else if (isCommercial) tagSignature = '🚚 Commercial Tag';
            else if (isStock) tagSignature = '🎫 Spare Club Tag';
            else if (isUnreg) tagSignature = '⚠️ Unknown RFID';

            const plate = isUnreg ? (entry.scanned_tag || 'NO TAG') : (entry.vehicle_number || '--');
            const timeStr = formatTimestamp(entry.timestamp);
            const dir = entry.direction || 'Entry';
            const gateLabel = entry.gate_no || (currentGate === 'clubroad' ? 'Club Road' : 'Gate-01');

            let badgeClass = 'bg-emerald-50 text-emerald-700 border-emerald-200';
            let badgeLabel = dir.toUpperCase();
            if (isNHA) {
                badgeClass = 'bg-amber-50 text-amber-800 border-amber-200';
                badgeLabel = 'M-TAG';
            } else if (isSociety) {
                badgeClass = 'bg-indigo-50 text-indigo-700 border-indigo-200';
                badgeLabel = 'SOCIETY';
            } else if (isCommercial) {
                badgeClass = 'bg-slate-100 text-slate-700 border-slate-300';
                badgeLabel = 'COMMERCIAL';
            } else if (isStock) {
                badgeClass = 'bg-blue-50 text-blue-700 border-blue-200';
                badgeLabel = 'CLUB STOCK';
            } else if (isUnreg) {
                badgeClass = 'bg-rose-50 text-rose-700 border-rose-200';
                badgeLabel = 'ALERT';
            } else if (dir === 'Exit') {
                badgeClass = 'bg-blue-50 text-blue-700 border-blue-200';
            }

            return `
                <div class="kiosk-card p-3.5 rounded-2xl border border-slate-200 hover:border-slate-300 transition-all flex flex-col justify-between shadow-sm">
                    <div>
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border ${badgeClass}">
                                ${isUnreg ? badgeLabel : dir.toUpperCase()}
                            </span>
                            <span class="text-[11px] font-mono font-bold text-slate-400">${timeStr}</span>
                        </div>
                        <h5 class="text-sm font-extrabold text-slate-900 truncate mb-0.5">${displayName}</h5>
                        ${isUnreg && tagSignature ? `<span class="text-[10px] font-bold text-slate-500">${tagSignature}</span>` : ''}
                    </div>
                    <div class="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
                        <span class="text-xs font-mono font-bold text-indigo-600 tracking-wider truncate max-w-[130px]">${plate}</span>
                        <span class="text-[10px] text-slate-400 font-bold uppercase truncate max-w-[110px]" title="${gateLabel}">${gateLabel}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Error fetching recent entry cards:', err);
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

        if (statusBadge) {
            statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2 rounded-2xl text-xs font-black uppercase tracking-widest bg-rose-50 text-rose-800 border-2 border-rose-300 shadow-sm';
        }
        if (badgeIcon) {
            badgeIcon.className = 'w-3 h-3 rounded-full bg-rose-500 animate-ping';
        }
        if (badgeText) {
            badgeText.innerText = `UNREGISTERED CAR DETECTED • ${direction.toUpperCase()} HELD`;
        }
        if (accentBar) {
            accentBar.className = 'absolute top-0 left-0 w-full h-3 bg-gradient-to-r from-rose-500 via-amber-500 to-rose-600';
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
        if (memberRoleTag) memberRoleTag.innerText = 'VERIFIED ACTIVE MEMBER';

        renderLicensePlate(log.vehicle_number);

        const photoStatusDot = document.getElementById('photoStatusDot');
        if (photoStatusDot) {
            photoStatusDot.className = 'absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-blue-600 border-2 border-white shadow-md flex items-center justify-center';
        }

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
                driverAvatar.className = 'w-36 h-36 rounded-[22px] bg-gradient-to-br from-indigo-50 to-slate-100 border-2 border-white flex items-center justify-center font-black text-4xl text-indigo-700 shadow-inner';
                driverAvatar.innerText = log.name ? log.name.substring(0, 2).toUpperCase() : 'KG';
            }
        }

        if (isExit) {
            if (statusBadge) {
                statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2 rounded-2xl text-xs font-black uppercase tracking-widest bg-blue-50 text-blue-800 border-2 border-blue-300 shadow-sm';
            }
            if (badgeIcon) {
                badgeIcon.className = 'w-3 h-3 rounded-full bg-blue-500 animate-ping';
            }
            if (badgeText) badgeText.innerText = 'CLEARANCE GRANTED • EXIT RECORDED';
            if (accentBar) accentBar.className = 'absolute top-0 left-0 w-full h-3 bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-600';
        } else {
            if (statusBadge) {
                statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2 rounded-2xl text-xs font-black uppercase tracking-widest bg-blue-50 text-blue-900 border-2 border-blue-400 shadow-sm';
            }
            if (badgeIcon) {
                badgeIcon.className = 'w-3 h-3 rounded-full bg-blue-600 animate-ping';
            }
            if (badgeText) badgeText.innerText = 'CLEARANCE GRANTED • ENTRY';
            if (accentBar) accentBar.className = 'absolute top-0 left-0 w-full h-3 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700';
        }
    }

    idleResetTimer = setTimeout(() => {
        viewActive.classList.add('hidden');
        viewIdle.classList.remove('hidden');
    }, 8000);
}

async function pollEntryLogs() {
    const reqSeq = ++pollLogsReqSeq;
    const reqGate = currentGate;
    try {
        const res = await fetch(`/api/latest-log?gate=${encodeURIComponent(reqGate)}`);
        if (!res.ok) return;
        const latest = await res.json();
        // Discard stale responses from older gate requests
        if (reqSeq !== pollLogsReqSeq || reqGate !== currentGate) return;
        if (!latest || !latest.id) return;

        if (lastEntryLogId === 0) {
            lastEntryLogId = latest.id;
            return;
        }

        if (latest.id !== lastEntryLogId) {
            lastEntryLogId = latest.id;
            displayEntry(latest);
            updateRecentEntries();
        }
    } catch (err) {
        console.error('Error polling entry logs:', err);
    }
}

// 1. Initialize gate selection from URL / localStorage FIRST
initGateSelection();

// 2. Fetch initial recent cards and start polling in strict sequence
updateRecentEntries();
pollEntryLogs();

// 3. Register repeating background intervals
setInterval(updateRecentEntries, 3000);
setInterval(pollEntryLogs, 400);
