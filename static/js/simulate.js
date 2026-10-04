let membersCache = [];
let selectedLineCrossFile = null;
let epcPollSim = null;

function $(id) {
    return document.getElementById(id);
}

async function runSelfTest() {
    const grid = $('selfTestGrid');
    if (!grid) return;
    grid.innerHTML = '<p class="col-span-5 text-slate-400 font-bold py-2">Running diagnostic self-test...</p>';

    const tests = [
        { name: 'Dashboard Endpoint', url: '/', method: 'GET' },
        { name: 'Kiosk Terminal', url: '/kiosk', method: 'GET' },
        { name: 'Members API', url: '/api/members?limit=1', method: 'GET' },
        { name: 'Stats API', url: '/api/stats', method: 'GET' },
        { name: 'Hardware Telemetry', url: '/api/tools/status', method: 'GET' }
    ];

    let html = '';
    for (const t of tests) {
        try {
            const res = await fetch(t.url, { method: t.method });
            const isOk = res.ok;
            html += `
            <div class="border rounded-xl p-3 ${isOk ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-rose-50 border-rose-200 text-rose-800'} flex items-center justify-between">
                <div>
                    <p class="font-bold text-xs">${t.name}</p>
                    <p class="text-[10px] font-mono">${t.method} ${t.url}</p>
                </div>
                <span class="text-xs font-black font-mono">${isOk ? 'PASS' : 'FAIL'}</span>
            </div>`;
        } catch (e) {
            html += `
            <div class="border rounded-xl p-3 bg-rose-50 border-rose-200 text-rose-800 flex items-center justify-between">
                <div>
                    <p class="font-bold text-xs">${t.name}</p>
                    <p class="text-[10px] font-mono">${t.method} ${t.url}</p>
                </div>
                <span class="text-xs font-black font-mono">ERR</span>
            </div>`;
        }
    }
    grid.innerHTML = html;
}

async function loadMembersDropdown() {
    const status = $('memberLoadStatus');
    const select = $('simMember');
    if (!select) return;

    try {
        const res = await fetch('/api/members?all=true');
        membersCache = await res.json();
        select.innerHTML = '<option value="">- Choose a registered member -</option>' +
            membersCache.map(m => `<option value="${m.E_tag_id}">${m.Name} (${m.Car_number || 'NO PLATE'} - ${m.Mem_id})</option>`).join('');
        if (status) status.innerText = `Loaded ${membersCache.length} registered member profiles.`;
    } catch (e) {
        if (status) status.innerText = 'Error loading member list.';
    }
}

function setupMemberListener() {
    const select = $('simMember');
    if (!select) return;

    select.addEventListener('change', () => {
        const epc = select.value;
        const tagInput = $('simTag2');
        if (tagInput && epc) tagInput.value = epc;

        const preview = $('memberPreview');
        if (!preview) return;

        const m = membersCache.find(x => x.E_tag_id === epc);
        if (m) {
            preview.innerHTML = `
                ${m.Profile_pic ? 
                    `<img src="/${m.Profile_pic}" class="w-16 h-16 rounded-full object-cover border-2 border-indigo-100 shadow">` :
                    `<div class="w-16 h-16 rounded-full bg-indigo-600 text-white flex items-center justify-center font-bold text-xl shadow">${m.Name.charAt(0)}</div>`
                }
                <div>
                    <p class="font-bold text-slate-800 text-sm">${m.Name}</p>
                    <p class="text-xs text-indigo-600 font-mono font-bold">${m.Car_number} &bull; ${m.Mem_id}</p>
                    <p class="text-[11px] text-slate-500 font-mono truncate max-w-xs">${m.E_tag_id}</p>
                </div>
            `;
        } else {
            preview.innerHTML = `
                <div class="w-16 h-16 rounded-full bg-slate-200 flex items-center justify-center font-bold text-slate-400">?</div>
                <div><p class="text-xs text-slate-400">Select a member to preview profile</p></div>
            `;
        }
    });
}

async function captureEPCTest(btn) {
    const status = $('epcStatus2');
    if (epcPollSim) {
        stopEpcSim();
        return;
    }

    btn.innerText = 'Stop';
    btn.className = 'bg-rose-600 text-white px-4 py-2.5 rounded-lg font-bold text-xs whitespace-nowrap';
    await fetch('/api/enroll-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: true })
    });

    if (status) {
        status.innerText = 'Listening for live RFID tag... wave tag near antenna.';
        status.className = 'text-xs mt-1 text-emerald-600 font-bold';
    }

    let elapsed = 0;
    epcPollSim = setInterval(async () => {
        elapsed++;
        try {
            const res = await fetch('/api/waiting-tag');
            const d = await res.json();
            if (d.tag && d.enroll_mode) {
                $('simTag2').value = d.tag;
                if (status) status.innerText = `Tag captured: ${d.tag} (${d.time})`;
                stopEpcSim();
                return;
            }
        } catch (e) {}

        if (elapsed > 30) {
            if (status) {
                status.innerText = 'Capture timed out.';
                status.className = 'text-xs mt-1 text-rose-600 font-bold';
            }
            stopEpcSim();
        }
    }, 1000);
}

async function stopEpcSim() {
    if (epcPollSim) {
        clearInterval(epcPollSim);
        epcPollSim = null;
    }
    await fetch('/api/enroll-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: false })
    });
    const btn = $('epcBtn2');
    if (btn) {
        btn.innerText = 'Read Live';
        btn.className = 'bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2.5 rounded-lg font-bold text-xs whitespace-nowrap';
    }
}

function setupDropZone() {
    const dropZone = $('dropZone');
    const fileInput = $('evFile');
    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files[0]) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            handleFileSelect(fileInput.files[0]);
        }
    });
}

function handleFileSelect(file) {
    selectedLineCrossFile = file;
    const preview = $('evPreview');
    const emptyMsg = $('evEmptyMsg');
    if (preview && file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.classList.remove('hidden');
        };
        reader.readAsDataURL(file);
    }
    if (emptyMsg) emptyMsg.classList.add('hidden');
}

async function submitLineCrossTest(btn) {
    if (!selectedLineCrossFile) {
        alert('Please select or drop a vehicle photo first to test line-crossing.');
        return;
    }

    const orig = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Uploading to Camera Audit...';
        btn.disabled = true;
    }

    const fd = new FormData();
    fd.append('file', selectedLineCrossFile);
    fd.append('direction', 'Line Crossing');

    try {
        const res = await fetch('/api/simulate-linecross', {
            method: 'POST',
            body: fd
        });
        const data = await res.json();
        const box = $('linecrossResult');
        if (box) {
            box.classList.remove('hidden');
            box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-blue-50 border border-blue-200 text-blue-800';
            box.innerHTML = `Hikvision Line-Crossing Recorded: Captured image stored in Camera Vehicle Audit table.`;
        }
    } catch (e) {
        alert('Line-crossing upload failed: ' + e.message);
    } finally {
        if (btn) {
            btn.innerHTML = orig;
            btn.disabled = false;
        }
    }
}

async function submitRFIDTest(btn) {
    const orig = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = 'Scanning RFID...';
        btn.disabled = true;
    }

    const tag = $('simTag2').value.trim();
    const dir = $('simDir2').value;

    if (!tag) {
        alert('Please enter an EPC tag or select a registered member.');
        if (btn) {
            btn.innerHTML = orig;
            btn.disabled = false;
        }
        return;
    }

    try {
        const res = await fetch('/api/simulate-rfid-full', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tag: tag,
                direction: dir
            })
        });
        const data = await res.json();

        const box = $('rfidResult');
        if (box) {
            box.classList.remove('hidden');
            box.className = 'mt-4 text-sm rounded-xl px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-800';
            box.innerHTML = `RFID Antenna Scan Processed: Log ID #${data.log_id}.`;
        }
        loadTestReport();
    } catch (e) {
        alert('Simulation failed: ' + e.message);
    } finally {
        if (btn) {
            btn.innerHTML = orig;
            btn.disabled = false;
        }
    }
}

async function loadTestReport() {
    const body = $('testReportBody');
    if (!body) return;

    try {
        const res = await fetch('/api/simulate/recent?limit=15');
        const rows = await res.json();

        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="7" class="p-8 text-center text-slate-400 font-bold">No test records generated yet</td></tr>';
            return;
        }

        body.innerHTML = rows.map(r => {
            const isUnreg = (r.name || '').includes('Unregistered');
            const timeStr = String(r.timestamp).replace('T', ' ').substring(11, 19);

            return `
            <tr class="hover:bg-slate-50 transition">
                <td class="p-4 font-mono text-xs font-bold text-slate-400">#${r.id}</td>
                <td class="p-4 text-xs font-mono text-slate-500">${timeStr}</td>
                <td class="p-4 font-bold ${isUnreg ? 'text-rose-600' : 'text-slate-800'}">${r.name}</td>
                <td class="p-4 font-mono font-bold text-indigo-600">${r.vehicle_number || '--'}</td>
                <td class="p-4">
                    <span class="text-[10px] font-extrabold px-2.5 py-1 rounded-full ${
                        r.access_type.includes('Verified') ? 'bg-emerald-100 text-emerald-800' :
                        r.access_type.includes('Unknown') ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                    }">${r.access_type}</span>
                </td>
                <td class="p-4 text-xs font-bold ${r.direction === 'Exit' ? 'text-blue-600' : 'text-emerald-600'}">${r.direction}</td>
                <td class="p-4 font-mono text-[11px] text-slate-500">${r.scanned_tag}</td>
            </tr>`;
        }).join('');
    } catch (e) {
        body.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-rose-500">Error loading report: ${e.message}</td></tr>`;
    }
}

async function clearAllLogs() {
    if (!confirm('This action purges all vehicle access journals and camera audit records to reset the database. Proceed?')) return;
    try {
        const res = await fetch('/api/simulate/clear-logs', { method: 'DELETE' });
        const data = await res.json();
        alert(data.message || 'Access logs cleared.');
        loadTestReport();
    } catch (e) {
        alert('Failed to clear logs: ' + e.message);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    runSelfTest();
    loadMembersDropdown();
    setupMemberListener();
    setupDropZone();
    loadTestReport();
});
