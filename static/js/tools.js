function statusCard(label, val, isOk) {
    return `
    <div class="rounded-xl border-2 ${isOk ? 'border-emerald-300 bg-emerald-50' : 'border-rose-300 bg-rose-50'} p-4 text-center">
        <p class="text-[10px] uppercase tracking-widest font-bold ${isOk ? 'text-emerald-600' : 'text-rose-500'} mb-1">${label}</p>
        <div class="flex items-center justify-center gap-2">
            <span class="inline-block w-2.5 h-2.5 rounded-full ${isOk ? 'bg-emerald-500 pulse-indicator' : 'bg-rose-500'}"></span>
            <p class="font-black text-sm ${isOk ? 'text-emerald-700' : 'text-rose-600'}">${val}</p>
        </div>
    </div>`;
}

async function loadStatus() {
    try {
        const res = await fetch('/api/tools/status');
        if (!res.ok) return;
        const s = await res.json();

        const grid = document.getElementById('statusGrid');
        if (grid) {
            grid.innerHTML =
                statusCard('Entry RFID Reader', s.readers.Entry, s.readers.Entry === 'CONNECTED') +
                statusCard('Exit RFID Reader', s.readers.Exit, s.readers.Exit === 'CONNECTED') +
                statusCard('Hikvision HD AI Camera', s.cameras.Hikvision, s.cameras.Hikvision === 'ONLINE');
        }

        const okCount = [s.readers.Entry, s.readers.Exit, s.cameras.Hikvision].filter(v => v === 'CONNECTED' || v === 'ONLINE').length;
        const sum = document.getElementById('statusSummary');
        if (sum) {
            if (okCount === 3) {
                sum.className = 'mt-4 text-sm font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3';
                sum.innerText = 'All Subsystems Operational - Ready for Production Access';
            } else {
                sum.className = 'mt-4 text-sm font-bold text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3';
                sum.innerText = `${3 - okCount} subsystem(s) offline - verify network addresses in Settings`;
            }
        }

        const ftpInfo = document.getElementById('ftpInfo');
        if (ftpInfo) {
            ftpInfo.innerText = `Camera line-crossing events received since service startup: ${s.ftp_events}` +
                (s.ftp_events === 0 ? ' (0 = Awaiting vehicle line crossing event)' : '');
        }

        renderTags(s.recent_tags);
    } catch (err) {
        console.error('Error querying hardware status:', err);
    }
}

function renderTags(tags) {
    if (!tags || !tags.length) return;
    const countEl = document.getElementById('rfidCount');
    const feedEl = document.getElementById('rfidFeed');
    if (countEl) countEl.innerText = `${tags.length} tags`;

    if (feedEl) {
        feedEl.innerHTML = tags.slice().reverse().map(t => `
        <div class="flex items-center justify-between bg-slate-50 border rounded-xl px-5 py-3">
            <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span class="font-mono text-sm font-bold text-slate-800">${t.tag}</span>
            </div>
            <div class="flex items-center gap-4">
                <span class="text-xs font-black px-2.5 py-1 rounded-full ${t.direction === 'Entry' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">
                    ${t.direction}
                </span>
                <span class="text-xs text-slate-400 font-mono">${t.time}</span>
            </div>
        </div>`).join('');
    }
}

async function captureFrame(cam, btn) {
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Capturing Frame...';
        btn.disabled = true;
    }

    try {
        const res = await fetch('/api/tools/capture/' + cam, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            alert(`Camera capture failed: ${data.detail || 'Service error'}`);
            return;
        }

        const imgEl = document.getElementById('snapHik');
        const metaEl = document.getElementById('hikMeta');
        if (imgEl) imgEl.src = '/' + data.path + '?t=' + Date.now();
        if (metaEl) metaEl.innerText = `${data.width} x ${data.height} px`;
    } catch (err) {
        alert('Network error during frame capture: ' + err.message);
    } finally {
        if (btn) {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    setInterval(loadStatus, 3000);
});
