let lastEntryLogId = 0;
let idleResetTimer = null;

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
    try {
        const res = await fetch('/api/recent-entries?limit=4');
        if (!res.ok) return;
        const entries = await res.json();
        const container = document.getElementById('recentCardsContainer');
        if (!container) return;

        if (!entries || entries.length === 0) {
            container.innerHTML = `
                <div class="col-span-4 kiosk-card p-6 rounded-2xl text-center text-slate-400 font-semibold text-xs tracking-wider uppercase border border-slate-200">
                    No recent RFID gate activity recorded today
                </div>
            `;
            return;
        }

        container.innerHTML = entries.map(entry => {
            const isUnreg = (entry.access_type || '').includes('Unknown') || 
                            (entry.access_type || '').includes('No RFID') || 
                            (entry.name || '').includes('Unregistered') ||
                            (entry.mem_id || '').includes('UNREGISTERED');
            const displayName = isUnreg ? 'Unregistered Vehicle' : entry.name;
            const plate = isUnreg ? (entry.scanned_tag || 'NO TAG') : (entry.vehicle_number || '--');
            const timeStr = formatTimestamp(entry.timestamp);
            const dir = entry.direction || 'Entry';

            let badgeClass = 'bg-emerald-50 text-emerald-700 border-emerald-200';
            if (isUnreg) {
                badgeClass = 'bg-rose-50 text-rose-700 border-rose-200';
            } else if (dir === 'Exit') {
                badgeClass = 'bg-blue-50 text-blue-700 border-blue-200';
            }

            return `
                <div class="kiosk-card p-3.5 rounded-2xl border border-slate-200 hover:border-slate-300 transition-all flex flex-col justify-between shadow-sm">
                    <div>
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border ${badgeClass}">
                                ${isUnreg ? 'ALERT' : dir.toUpperCase()}
                            </span>
                            <span class="text-[11px] font-mono font-bold text-slate-400">${timeStr}</span>
                        </div>
                        <h5 class="text-sm font-extrabold text-slate-900 truncate mb-1">${displayName}</h5>
                    </div>
                    <div class="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
                        <span class="text-xs font-mono font-bold text-indigo-600 tracking-wider truncate max-w-[130px]">${plate}</span>
                        <span class="text-[10px] text-slate-400 font-bold uppercase">${isUnreg ? 'Gate-01' : (entry.make_model || 'Gate-01')}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Error fetching recent entry cards:', err);
    }
}
setInterval(updateRecentEntries, 3000);
updateRecentEntries();

function displayEntry(log) {
    clearTimeout(idleResetTimer);

    const viewIdle = document.getElementById('viewIdle');
    const viewActive = document.getElementById('viewActive');
    if (!viewIdle || !viewActive) return;

    viewIdle.classList.add('hidden');
    viewActive.classList.remove('hidden');

    const isUnregistered = (log.access_type || '').includes('Unknown') || 
                           (log.access_type || '').includes('No RFID') || 
                           (log.name || '').includes('Unregistered') ||
                           (log.mem_id || '').includes('UNREGISTERED') ||
                           (log.mem_id || '').includes('GUEST');

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
            unregDirectionBadge.innerText = `UNREGISTERED CAR DETECTED • ${direction.toUpperCase()} ATTEMPT`;
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
            photoStatusDot.className = 'absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-emerald-500 border-2 border-white shadow-md flex items-center justify-center';
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
                statusBadge.className = 'inline-flex items-center gap-2.5 px-5 py-2 rounded-2xl text-xs font-black uppercase tracking-widest bg-emerald-50 text-emerald-800 border-2 border-emerald-300 shadow-sm';
            }
            if (badgeIcon) {
                badgeIcon.className = 'w-3 h-3 rounded-full bg-emerald-500 animate-ping';
            }
            if (badgeText) badgeText.innerText = 'CLEARANCE GRANTED • ENTRY';
            if (accentBar) accentBar.className = 'absolute top-0 left-0 w-full h-3 bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-600';
        }
    }

    idleResetTimer = setTimeout(() => {
        viewActive.classList.add('hidden');
        viewIdle.classList.remove('hidden');
    }, 8000);
}

async function pollEntryLogs() {
    try {
        const res = await fetch('/api/latest-log');
        if (!res.ok) return;
        const latest = await res.json();
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
setInterval(pollEntryLogs, 400);
