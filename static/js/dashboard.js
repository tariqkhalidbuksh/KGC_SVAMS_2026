// Global Application State & Pagination Variables
let currentAuditPage = 1;
let currentAuditLimit = 25;
let currentAuditStatus = 'all';
let auditData = [];
let auditSearchTimer = null;

let currentCamAuditPage = 1;
let currentCamAuditLimit = 24;
let currentCamAuditDate = 'today';
let currentCamAuditItems = [];
let camAuditSearchTimer = null;

let currentMemPage = 1;
let currentMemLimit = 25;
let editingMemberRowId = null;
let editingMemberMemId = null;
let memSearchTimer = null;
let epcPollingInterval = null;

let quickSearchTimer = null;

// Authentication & User Session Management
let currentUser = null;
let cachedUsersList = [];

async function initAuth() {
    try {
        const res = await fetch('/api/auth/me');
        if (!res.ok) {
            window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
            return;
        }
        const data = await res.json();
        if (!data.authenticated || !data.user) {
            window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
            return;
        }
        currentUser = data.user;
        updateUserUI(currentUser);
    } catch (e) {
        console.error('Error verifying auth session:', e);
    }
}

function updateUserUI(user) {
    if (!user) return;
    const avatar = document.getElementById('userAvatar');
    const nameEl = document.getElementById('userFullName');
    const roleBadge = document.getElementById('userRoleBadge');
    const banner = document.getElementById('viewerReadOnlyBanner');

    if (avatar) {
        const initials = user.full_name ? user.full_name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() : 'U';
        avatar.innerText = initials;
        if (user.role === 'Admin') avatar.className = 'w-7 h-7 rounded-lg bg-indigo-600 text-white font-black text-xs flex items-center justify-center uppercase shadow-2xs';
        else if (user.role === 'Editor') avatar.className = 'w-7 h-7 rounded-lg bg-emerald-600 text-white font-black text-xs flex items-center justify-center uppercase shadow-2xs';
        else avatar.className = 'w-7 h-7 rounded-lg bg-blue-600 text-white font-black text-xs flex items-center justify-center uppercase shadow-2xs';
    }

    if (nameEl) nameEl.innerText = user.full_name || user.username;

    if (roleBadge) {
        roleBadge.innerText = user.role.toUpperCase();
        if (user.role === 'Admin') {
            roleBadge.className = 'text-[9px] font-black uppercase tracking-wider px-1.5 py-0.2 rounded font-mono bg-indigo-100 text-indigo-700';
        } else if (user.role === 'Editor') {
            roleBadge.className = 'text-[9px] font-black uppercase tracking-wider px-1.5 py-0.2 rounded font-mono bg-emerald-100 text-emerald-700';
        } else {
            roleBadge.className = 'text-[9px] font-black uppercase tracking-wider px-1.5 py-0.2 rounded font-mono bg-blue-100 text-blue-700';
        }
    }

    // Role-based UI restrictions
    if (user.role === 'Viewer') {
        if (banner) banner.classList.remove('hidden');

        // Disable Add Member submit button
        const subBtn = document.getElementById('submitBtn');
        if (subBtn) {
            subBtn.disabled = true;
            subBtn.classList.remove('bg-emerald-600', 'hover:bg-emerald-700');
            subBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            subBtn.innerText = 'Add Member (Restricted in Viewer Mode)';
        }

        // Disable Save Settings
        const saveBtn = document.getElementById('btnSaveConfig');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.classList.remove('bg-slate-900', 'hover:bg-slate-800');
            saveBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            saveBtn.title = 'Viewers cannot modify system settings';
        }

        // Disable Reset Activity
        const resetBtn = document.getElementById('btnResetActivity');
        if (resetBtn) {
            resetBtn.disabled = true;
            resetBtn.classList.remove('bg-rose-600', 'hover:bg-rose-700');
            resetBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            resetBtn.title = 'Viewers cannot perform system reset';
        }

        // Disable Add User
        const addUBtn = document.getElementById('addUserBtn');
        if (addUBtn) {
            addUBtn.disabled = true;
            addUBtn.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
            addUBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            addUBtn.title = 'Viewers cannot create user accounts';
        }
    } else if (user.role === 'Editor') {
        if (banner) banner.classList.add('hidden');

        // Disable Save Settings & Reset for Editor (Admin only)
        const saveBtn = document.getElementById('btnSaveConfig');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.classList.remove('bg-slate-900', 'hover:bg-slate-800');
            saveBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            saveBtn.title = 'Only administrators can save configuration';
        }

        const resetBtn = document.getElementById('btnResetActivity');
        if (resetBtn) {
            resetBtn.disabled = true;
            resetBtn.classList.remove('bg-rose-600', 'hover:bg-rose-700');
            resetBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            resetBtn.title = 'Only administrators can reset system activity';
        }

        const addUBtn = document.getElementById('addUserBtn');
        if (addUBtn) {
            addUBtn.disabled = true;
            addUBtn.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
            addUBtn.classList.add('bg-slate-300', 'cursor-not-allowed');
            addUBtn.title = 'Only administrators can add users';
        }
    } else {
        // Admin
        if (banner) banner.classList.add('hidden');
    }
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

function switchSettingsSubtab(name) {
    const hwView = document.getElementById('settingsViewHardware');
    const uView = document.getElementById('settingsViewUsers');
    const hwBtn = document.getElementById('subtabSetHwBtn');
    const uBtn = document.getElementById('subtabSetUsersBtn');

    if (name === 'users') {
        if (hwView) hwView.classList.add('hidden');
        if (uView) uView.classList.remove('hidden');
        if (hwBtn) {
            hwBtn.className = 'px-5 py-2.5 rounded-xl text-xs font-bold text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition flex items-center gap-2';
        }
        if (uBtn) {
            uBtn.className = 'px-5 py-2.5 rounded-xl text-xs font-extrabold bg-white border border-slate-200 shadow-xs text-indigo-700 flex items-center gap-2 transition';
        }
        loadUsers();
    } else {
        if (hwView) hwView.classList.remove('hidden');
        if (uView) uView.classList.add('hidden');
        if (hwBtn) {
            hwBtn.className = 'px-5 py-2.5 rounded-xl text-xs font-extrabold bg-white border border-slate-200 shadow-xs text-indigo-700 flex items-center gap-2 transition';
        }
        if (uBtn) {
            uBtn.className = 'px-5 py-2.5 rounded-xl text-xs font-bold text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition flex items-center gap-2';
        }
        loadHardwareSettingsStatus();
    }
}

async function loadUsers() {
    try {
        const res = await fetch('/api/users');
        if (!res.ok) return;
        const data = await res.json();
        cachedUsersList = data.users || [];
        renderUsersTable(cachedUsersList);
    } catch (e) {
        console.error('loadUsers error:', e);
    }
}

function renderUsersTable(users) {
    const totalEl = document.getElementById('uStatTotal');
    const adminsEl = document.getElementById('uStatAdmins');
    const editorsEl = document.getElementById('uStatEditors');
    const viewersEl = document.getElementById('uStatViewers');
    const badgeCount = document.getElementById('usersBadgeCount');
    const tableCount = document.getElementById('uTableCount');
    const tbody = document.getElementById('usersTableBody');

    if (!tbody) return;

    const admins = users.filter(u => u.role === 'Admin').length;
    const editors = users.filter(u => u.role === 'Editor').length;
    const viewers = users.filter(u => u.role === 'Viewer').length;

    if (totalEl) totalEl.innerText = users.length;
    if (adminsEl) adminsEl.innerText = admins;
    if (editorsEl) editorsEl.innerText = editors;
    if (viewersEl) viewersEl.innerText = viewers;
    if (badgeCount) badgeCount.innerText = users.length;
    if (tableCount) tableCount.innerText = users.length;

    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="p-8 text-center text-slate-400 font-bold">No operator accounts found.</td></tr>`;
        return;
    }

    tbody.innerHTML = users.map(u => {
        const initials = u.full_name ? u.full_name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() : 'U';
        const isCurrent = currentUser && currentUser.id === u.id;
        const isAdmin = currentUser && currentUser.role === 'Admin';
        
        let roleBadgeHtml = '';
        if (u.role === 'Admin') {
            roleBadgeHtml = `
                <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-extrabold">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
                    <span>Full Admin</span>
                </div>
            `;
        } else if (u.role === 'Editor') {
            roleBadgeHtml = `
                <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-extrabold">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                    <span>Edit Rights (Operator)</span>
                </div>
            `;
        } else {
            roleBadgeHtml = `
                <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-extrabold">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    <span>View Rights (Read-Only)</span>
                </div>
            `;
        }

        const statusBadgeHtml = u.is_active
            ? `<span class="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-700"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>Active</span>`
            : `<span class="inline-flex items-center gap-1.5 text-xs font-bold text-slate-400"><span class="w-2 h-2 rounded-full bg-slate-300"></span>Disabled</span>`;

        const userEscaped = JSON.stringify(u).replace(/"/g, '&quot;');

        let actionsHtml = '';
        if (isAdmin || isCurrent) {
            actionsHtml = `
                <div class="flex items-center justify-end gap-2 pr-4">
                    <button type="button" onclick="openEditUserModal(${userEscaped})" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition">Edit Rights</button>
                    ${(!isCurrent && isAdmin) ? `<button type="button" onclick="deleteUser(${u.id}, '${u.username}')" class="text-xs font-bold text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 p-1.5 rounded-lg transition" title="Delete Account"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>` : ''}
                </div>
            `;
        } else {
            actionsHtml = `<span class="text-slate-400 text-xs pr-4 font-semibold">Read Only</span>`;
        }

        return `
            <tr class="hover:bg-slate-50/70 transition">
                <td class="p-4 pl-6">
                    <div class="flex items-center gap-3">
                        <div class="w-9 h-9 rounded-xl ${u.role === 'Admin' ? 'bg-indigo-100 text-indigo-700' : u.role === 'Editor' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'} font-black text-xs flex items-center justify-center uppercase shadow-2xs">
                            ${initials}
                        </div>
                        <div>
                            <div class="flex items-center gap-2">
                                <span class="font-extrabold text-slate-800 text-sm">${u.full_name}</span>
                                ${isCurrent ? '<span class="text-[9px] font-bold bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-mono">YOU</span>' : ''}
                            </div>
                            <span class="text-xs font-mono text-slate-400">@${u.username}</span>
                        </div>
                    </div>
                </td>
                <td class="p-4">${roleBadgeHtml}</td>
                <td class="p-4">${statusBadgeHtml}</td>
                <td class="p-4 font-mono text-xs text-slate-500">${u.created_at || '--'}</td>
                <td class="p-4 font-mono text-xs text-slate-500">${u.last_login ? u.last_login : '<span class="text-slate-400 italic">Never</span>'}</td>
                <td class="p-4 text-right">${actionsHtml}</td>
            </tr>
        `;
    }).join('');
}

function filterUsersTable() {
    const input = document.getElementById('userSearchInput');
    const term = (input ? input.value : '').toLowerCase().trim();
    if (!term) {
        renderUsersTable(cachedUsersList);
        return;
    }
    const filtered = cachedUsersList.filter(u => 
        (u.username && u.username.toLowerCase().includes(term)) ||
        (u.full_name && u.full_name.toLowerCase().includes(term)) ||
        (u.role && u.role.toLowerCase().includes(term))
    );
    renderUsersTable(filtered);
}

function openAddUserModal() {
    const modal = document.getElementById('addUserModal');
    const err = document.getElementById('addUserError');
    if (err) err.classList.add('hidden');
    document.getElementById('addFullName').value = '';
    document.getElementById('addUsername').value = '';
    document.getElementById('addPassword').value = '';
    if (modal) modal.classList.remove('hidden');
}

function closeAddUserModal() {
    const modal = document.getElementById('addUserModal');
    if (modal) modal.classList.add('hidden');
}

async function submitAddUser(e) {
    e.preventDefault();
    const errBox = document.getElementById('addUserError');
    const fullName = document.getElementById('addFullName').value.trim();
    const username = document.getElementById('addUsername').value.trim();
    const password = document.getElementById('addPassword').value;
    const roleRadio = document.querySelector('input[name="addRole"]:checked');
    const role = roleRadio ? roleRadio.value : 'Viewer';

    const btn = document.getElementById('submitAddUserBtn');
    btn.disabled = true;
    btn.innerText = 'Creating Account...';

    try {
        const res = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                password: password,
                full_name: fullName,
                role: role,
                is_active: 1
            })
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            closeAddUserModal();
            showToast('User Account Created', `Operator ${fullName} registered with ${role} rights`, 'success');
            loadUsers();
        } else {
            if (errBox) {
                errBox.innerText = data.error || 'Failed to create user account';
                errBox.classList.remove('hidden');
            }
        }
    } catch (err) {
        if (errBox) {
            errBox.innerText = 'Network error creating user';
            errBox.classList.remove('hidden');
        }
    } finally {
        btn.disabled = false;
        btn.innerText = 'Create Account';
    }
}

function openEditUserModal(user) {
    if (!user) return;
    const modal = document.getElementById('editUserModal');
    const err = document.getElementById('editUserError');
    if (err) err.classList.add('hidden');

    document.getElementById('editUserId').value = user.id;
    document.getElementById('editUsername').value = '@' + user.username;
    document.getElementById('editFullName').value = user.full_name || '';
    document.getElementById('editRole').value = user.role || 'Viewer';
    document.getElementById('editStatus').value = user.is_active ? '1' : '0';
    document.getElementById('editPassword').value = '';

    if (modal) modal.classList.remove('hidden');
}

function closeEditUserModal() {
    const modal = document.getElementById('editUserModal');
    if (modal) modal.classList.add('hidden');
}

async function submitEditUser(e) {
    e.preventDefault();
    const errBox = document.getElementById('editUserError');
    const userId = document.getElementById('editUserId').value;
    const fullName = document.getElementById('editFullName').value.trim();
    const role = document.getElementById('editRole').value;
    const isActive = document.getElementById('editStatus').value === '1';
    const password = document.getElementById('editPassword').value;

    const btn = document.getElementById('submitEditUserBtn');
    btn.disabled = true;
    btn.innerText = 'Saving...';

    try {
        const payload = {
            full_name: fullName,
            role: role,
            is_active: isActive ? 1 : 0
        };
        if (password && password.trim()) {
            payload.password = password.trim();
        }

        const res = await fetch(`/api/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            closeEditUserModal();
            showToast('Permissions Updated', `User permissions updated successfully`, 'success');
            loadUsers();
            if (currentUser && currentUser.id == userId) {
                initAuth();
            }
        } else {
            if (errBox) {
                errBox.innerText = data.error || 'Failed to update user';
                errBox.classList.remove('hidden');
            }
        }
    } catch (err) {
        if (errBox) {
            errBox.innerText = 'Network error saving changes';
            errBox.classList.remove('hidden');
        }
    } finally {
        btn.disabled = false;
        btn.innerText = 'Save Permissions';
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Are you sure you want to permanently delete user account '@${username}'?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.ok) {
            showToast('User Deleted', `Account '@${username}' has been removed`, 'info');
            loadUsers();
        } else {
            alert(data.error || 'Failed to delete user');
        }
    } catch (e) {
        alert('Network error deleting user account');
    }
}

function toggleMobileMenu() {
    const drawer = document.getElementById('mobileDrawer');
    if (drawer) drawer.classList.toggle('hidden');
}

function closeMobileMenu() {
    const drawer = document.getElementById('mobileDrawer');
    if (drawer) drawer.classList.add('hidden');
}

async function loadHardwareSettingsStatus() {
    const grid = document.getElementById('settingsHwGrid');
    if (!grid) return;
    try {
        const res = await fetch('/api/tools/status');
        if (!res.ok) return;
        const s = await res.json();
        const entryOk = s.readers?.Entry === 'CONNECTED';
        const exitOk = s.readers?.Exit === 'CONNECTED';
        const camOk = s.cameras?.Hikvision === 'ONLINE';

        grid.innerHTML = `
            <div class="p-4 rounded-xl border ${entryOk ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'} flex items-center justify-between">
                <div>
                    <span class="text-[10px] font-extrabold uppercase tracking-widest text-slate-400">Entry RFID Reader</span>
                    <h4 class="font-bold text-slate-800 text-sm mt-0.5">Fixed UHF Antenna</h4>
                    <p class="text-xs font-mono text-slate-500 mt-1">192.168.0.217:60000</p>
                </div>
                <span class="px-2.5 py-1 rounded-full text-xs font-bold ${entryOk ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-rose-100 text-rose-800 border border-rose-300'}">
                    ${entryOk ? 'ONLINE' : 'DISCONNECTED'}
                </span>
            </div>
            <div class="p-4 rounded-xl border ${exitOk ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'} flex items-center justify-between">
                <div>
                    <span class="text-[10px] font-extrabold uppercase tracking-widest text-slate-400">Exit RFID Reader</span>
                    <h4 class="font-bold text-slate-800 text-sm mt-0.5">Fixed UHF Antenna</h4>
                    <p class="text-xs font-mono text-slate-500 mt-1">192.168.0.216:60000</p>
                </div>
                <span class="px-2.5 py-1 rounded-full text-xs font-bold ${exitOk ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-rose-100 text-rose-800 border border-rose-300'}">
                    ${exitOk ? 'ONLINE' : 'DISCONNECTED'}
                </span>
            </div>
            <div class="p-4 rounded-xl border ${camOk ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'} flex items-center justify-between">
                <div>
                    <span class="text-[10px] font-extrabold uppercase tracking-widest text-slate-400">Hikvision AI Camera</span>
                    <h4 class="font-bold text-slate-800 text-sm mt-0.5">Line-Crossing Optical Sensor</h4>
                    <p class="text-xs font-mono text-slate-500 mt-1">192.168.0.220:554</p>
                </div>
                <span class="px-2.5 py-1 rounded-full text-xs font-bold ${camOk ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-rose-100 text-rose-800 border border-rose-300'}">
                    ${camOk ? 'ONLINE' : 'OFFLINE'}
                </span>
            </div>
        `;
        if (typeof loadBulkExitSettings === 'function') {
            loadBulkExitSettings();
        }
    } catch (e) {
        console.error('loadHardwareSettingsStatus error:', e);
    }
}

function switchTab(name, btn) {
    if (!name) name = 'overview';
    // Normalize aliases
    if (name === 'users') {
        switchTab('settings');
        switchSettingsSubtab('users');
        return;
    }
    if (name === 'hardware' || name === 'hardware-settings' || name === 'hardware-setting') name = 'settings';
    if (name === 'audit' || name === 'reports') name = 'logs';
    if (name === 'camera') name = 'camera_audit';
    if (name === 'tag_audit' || name === 'tag' || name === 'etag' || name === 'etag-audit') name = 'etag_audit';

    // Deselect desktop and mobile nav buttons
    document.querySelectorAll('.nav-btn, .nav-btn-mobile').forEach(b => {
        b.classList.remove('active', 'bg-emerald-50', 'text-emerald-700', 'font-bold');
    });

    // Mark matching desktop and mobile buttons as active
    document.querySelectorAll(`[data-tab="${name}"]`).forEach(b => {
        b.classList.add('active');
        if (b.classList.contains('nav-btn-mobile')) {
            b.classList.add('bg-emerald-50', 'text-emerald-700', 'font-bold');
        }
    });

    // Hide all tab panels
    document.querySelectorAll('[id^="tab-"]').forEach(panel => panel.classList.add('hidden'));

    // Show target panel
    const target = document.getElementById('tab-' + name);
    if (target) {
        target.classList.remove('hidden');
    } else {
        const fallback = document.getElementById('tab-overview');
        if (fallback) fallback.classList.remove('hidden');
    }

    // Update Page Title
    const titleEl = document.getElementById('pageTitle');
    if (titleEl) {
        titleEl.innerText = name === 'overview' ? 'Command Overview' :
                            name === 'logs' ? 'Vehicle Audit Reports' :
                            name === 'camera_audit' ? 'Camera Vehicle Audit' :
                            name === 'members' ? 'Member Directory' :
                            name === 'etag_audit' ? 'E-TAG Activity Audit Studio' :
                            name === 'settings' ? 'Settings' : 'Command Overview';
    }

    // Update URL query parameter without page reload
    try {
        const url = new URL(window.location.href);
        if (name === 'overview') {
            url.searchParams.delete('tab');
        } else {
            url.searchParams.set('tab', name);
        }
        window.history.replaceState({ tab: name }, '', url.toString());
    } catch (e) {}

    // Load or refresh data for the selected tab
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
    } else if (name === 'members') {
        loadMembers(1);
    } else if (name === 'etag_audit') {
        if (!currentAuditedTag) {
            loadRecentEtagTags();
        }
    } else if (name === 'settings') {
        loadSettings();
        loadHardwareSettingsStatus();
        loadUsers();
    } else if (name === 'overview') {
        loadStats();
        loadCharts();
    }

    closeMobileMenu();
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
        if (document.getElementById('sGuests')) document.getElementById('sGuests').innerText = (s.unregistered_transits_today || s.guests_today || 0).toLocaleString();
        if (document.getElementById('sPeak')) document.getElementById('sPeak').innerText = s.peak_hour ? `${s.peak_hour} (${s.peak_count})` : 'None';
        if (document.getElementById('parkPct')) document.getElementById('parkPct').innerText = Math.round(((s.currently_in_club || 0) / cap) * 100) + '%';
        if (document.getElementById('parkIn')) document.getElementById('parkIn').innerText = (s.currently_in_club || 0).toLocaleString();
        if (document.getElementById('parkFree')) document.getElementById('parkFree').innerText = Math.max(0, cap - (s.currently_in_club || 0)).toLocaleString();

        // Real Average Stay Duration & Adoption Metrics
        if (document.getElementById('sAvgDuration')) document.getElementById('sAvgDuration').innerText = s.avg_duration || '--';
        if (document.getElementById('sPairedVisits')) document.getElementById('sPairedVisits').innerText = (s.paired_visits_count || 0).toLocaleString();
        if (document.getElementById('sAdoptionRate')) document.getElementById('sAdoptionRate').innerText = `${s.tag_adoption_rate !== undefined ? s.tag_adoption_rate : 100}%`;
        if (document.getElementById('gapSummaryBadge')) document.getElementById('gapSummaryBadge').innerText = `${s.tag_adoption_rate !== undefined ? s.tag_adoption_rate : 100}% COVERAGE`;
        if (document.getElementById('adoptionRateVal')) document.getElementById('adoptionRateVal').innerText = `${s.tag_adoption_rate !== undefined ? s.tag_adoption_rate : 100}%`;
        if (document.getElementById('adoptionRegCount')) document.getElementById('adoptionRegCount').innerText = (s.registered_transits_today || 0).toLocaleString();
        if (document.getElementById('adoptionUnregCount')) document.getElementById('adoptionUnregCount').innerText = (s.unregistered_transits_today || 0).toLocaleString();
        if (document.getElementById('adoptionBufferCount')) document.getElementById('adoptionBufferCount').innerText = (s.unassigned_tags_buffer || 0).toLocaleString();

        const overstayBadge = document.getElementById('sOverstayBadge');
        if (overstayBadge) {
            if (s.overstay_count && s.overstay_count > 0) {
                overstayBadge.innerText = `${s.overstay_count} Overstay`;
                overstayBadge.classList.remove('hidden');
            } else {
                overstayBadge.classList.add('hidden');
            }
        }

        updateParkingDonut(s.currently_in_club || 0, cap);
        updateAdoptionDonut(s.registered_transits_today || 0, s.unregistered_transits_today || 0);
    } catch (err) {
        console.error('loadStats error:', err);
    }
}

let hourlyChart = null;
let weeklyChart = null;
let parkingChart = null;
let adoptionChart = null;

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
                    backgroundColor: 'rgba(16, 185, 129, 0.14)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#10B981'
                },
                {
                    label: 'Exits',
                    data: [],
                    borderColor: '#3B82F6',
                    backgroundColor: 'rgba(59, 130, 246, 0.08)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#3B82F6'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0F172A',
                    titleFont: { weight: 'bold', size: 12 },
                    bodyFont: { size: 11 },
                    padding: 10,
                    cornerRadius: 8
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxRotation: 0, font: { size: 10 } }
                },
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0, stepSize: 1, font: { size: 10 } },
                    grid: { color: 'rgba(226, 232, 240, 0.7)' }
                }
            }
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

    const adoptEl = document.getElementById('adoptionChart');
    if (adoptEl) {
        adoptionChart = new Chart(adoptEl, {
            type: 'doughnut',
            data: {
                labels: ['Registered Tags', 'Unregistered Gap'],
                datasets: [{
                    data: [100, 0],
                    backgroundColor: ['#10B981', '#F59E0B'],
                    borderWidth: 0,
                    cutout: '76%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } }
            }
        });
    }
}

function updateParkingDonut(inside, cap) {
    if (parkingChart) {
        parkingChart.data.datasets[0].data = [inside, Math.max(0, cap - inside)];
        parkingChart.update();
    }
}

function updateAdoptionDonut(reg, unreg) {
    if (adoptionChart) {
        const safeReg = (reg === 0 && unreg === 0) ? 100 : reg;
        const safeUnreg = (reg === 0 && unreg === 0) ? 0 : unreg;
        adoptionChart.data.datasets[0].data = [safeReg, safeUnreg];
        adoptionChart.update();
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

            // Calculate peak hour and totals for KPI banner
            let maxTotal = 0;
            let peakHourStr = '--';
            let sumEntries = 0;
            let sumExits = 0;

            if (c.hours && c.hourly_entries) {
                for (let i = 0; i < c.hours.length; i++) {
                    const en = c.hourly_entries[i] || 0;
                    const ex = (c.hourly_exits && c.hourly_exits[i]) || 0;
                    sumEntries += en;
                    sumExits += ex;
                    const tot = en + ex;
                    if (tot > maxTotal) {
                        maxTotal = tot;
                        peakHourStr = `${c.hours[i]}:00 (${tot} transits)`;
                    }
                }
            }

            const peakEl = document.getElementById('chartPeakHour');
            if (peakEl) peakEl.innerText = maxTotal > 0 ? peakHourStr : 'None yet';

            const inEl = document.getElementById('chartTotalInflow');
            if (inEl) inEl.innerText = `${sumEntries} ${sumEntries === 1 ? 'Entry' : 'Entries'}`;

            const outEl = document.getElementById('chartTotalOutflow');
            if (outEl) outEl.innerText = `${sumExits} ${sumExits === 1 ? 'Exit' : 'Exits'}`;
        }
        if (weeklyChart) {
            weeklyChart.data.labels = c.days;
            weeklyChart.data.datasets[0].data = c.daily_entries;
            weeklyChart.data.datasets[1].data = c.daily_exits;
            weeklyChart.update();
        }
        if (c.fleet_adoption) {
            updateAdoptionDonut(c.fleet_adoption.registered_transits || 0, c.fleet_adoption.unregistered_transits || 0);
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

function onAuditSearchInput() {
    clearTimeout(auditSearchTimer);
    auditSearchTimer = setTimeout(() => {
        currentAuditPage = 1;
        loadAudit(1);
    }, 300);
}

let currentAuditDatePreset = 'today';

function setAuditDatePreset(preset) {
    currentAuditDatePreset = preset;
    const startInput = document.getElementById('auditDate');
    const endInput = document.getElementById('auditEndDate');
    const todayBtn = document.getElementById('auditPresetToday');
    const yestBtn = document.getElementById('auditPresetYesterday');
    const weekBtn = document.getElementById('auditPresetWeek');
    const allBtn = document.getElementById('auditPresetAll');

    [todayBtn, yestBtn, weekBtn, allBtn].forEach(b => {
        if (b) {
            b.classList.remove('bg-slate-900', 'text-white');
            b.classList.add('text-slate-700', 'hover:bg-slate-100');
        }
    });

    const now = new Date();
    const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    if (preset === 'all') {
        if (startInput) startInput.value = '';
        if (endInput) endInput.value = '';
        if (allBtn) {
            allBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            allBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else if (preset === 'yesterday') {
        const y = new Date();
        y.setDate(y.getDate() - 1);
        const yStr = fmt(y);
        if (startInput) startInput.value = yStr;
        if (endInput) endInput.value = yStr;
        if (yestBtn) {
            yestBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            yestBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else if (preset === 'week') {
        const w = new Date();
        w.setDate(w.getDate() - 7);
        if (startInput) startInput.value = fmt(w);
        if (endInput) endInput.value = fmt(now);
        if (weekBtn) {
            weekBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            weekBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else {
        const tStr = fmt(now);
        if (startInput) startInput.value = tStr;
        if (endInput) endInput.value = tStr;
        if (todayBtn) {
            todayBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            todayBtn.classList.add('bg-slate-900', 'text-white');
        }
    }
    loadAudit(1);
}

function onAuditDateChange() {
    const todayBtn = document.getElementById('auditPresetToday');
    const yestBtn = document.getElementById('auditPresetYesterday');
    const weekBtn = document.getElementById('auditPresetWeek');
    const allBtn = document.getElementById('auditPresetAll');
    [todayBtn, yestBtn, weekBtn, allBtn].forEach(b => {
        if (b) {
            b.classList.remove('bg-slate-900', 'text-white');
            b.classList.add('text-slate-700', 'hover:bg-slate-100');
        }
    });
    currentAuditDatePreset = 'custom';
    loadAudit(1);
}

function resetAuditFilters() {
    const searchInput = document.getElementById('auditSearch');
    if (searchInput) searchInput.value = '';
    const camSelect = document.getElementById('auditCamera');
    if (camSelect) camSelect.value = 'all';
    currentAuditStatus = 'all';
    document.querySelectorAll('.audit-status-pill').forEach(b => {
        b.className = 'audit-status-pill px-3 py-1 text-xs font-bold rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition';
    });
    const firstPill = document.querySelector('.audit-status-pill');
    if (firstPill) firstPill.className = 'audit-status-pill px-3 py-1 text-xs font-bold rounded-lg bg-indigo-600 text-white shadow-sm transition';
    setAuditDatePreset('today');
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
    const startD = document.getElementById('auditDate')?.value || '';
    const endD = document.getElementById('auditEndDate')?.value || '';
    const cam = document.getElementById('auditCamera')?.value || 'all';
    const q = (document.getElementById('auditSearch') || {}).value || '';
    const bodyEl = document.getElementById('auditBody');
    if (!bodyEl) return;

    bodyEl.innerHTML = `<tr><td colspan="8" class="p-10 text-center text-slate-400 font-bold">Loading audit logs...</td></tr>`;

    try {
        const dateParam = (currentAuditDatePreset === 'all' && !startD) ? 'all' : startD;
        const url = `/api/audit?date=${encodeURIComponent(dateParam)}&start_date=${encodeURIComponent(startD)}&end_date=${encodeURIComponent(endD)}&camera=${encodeURIComponent(cam)}&page=${page}&limit=${currentAuditLimit}&search=${encodeURIComponent(q)}&status=${currentAuditStatus}`;
        const res = await fetch(url);
        const data = await res.json();

        if (document.getElementById('auditStatTotal')) document.getElementById('auditStatTotal').innerText = (data.total || 0).toLocaleString();
        if (document.getElementById('auditStatInside')) document.getElementById('auditStatInside').innerText = (data.currently_inside || 0).toLocaleString();
        if (document.getElementById('auditStatExited')) document.getElementById('auditStatExited').innerText = (data.exited_count || 0).toLocaleString();
        if (document.getElementById('auditStatAlerts')) document.getElementById('auditStatAlerts').innerText = (data.alert_count || 0).toLocaleString();
        if (document.getElementById('auditStatOverstay')) document.getElementById('auditStatOverstay').innerText = (data.overstay_count || 0).toLocaleString();
        if (document.getElementById('auditBadgeDate')) document.getElementById('auditBadgeDate').innerText = data.date || 'Today';

        auditData = data.audits || [];
        const total = data.total_filtered !== undefined ? data.total_filtered : auditData.length;
        const totalPages = data.total_pages || Math.ceil(total / currentAuditLimit) || 1;

        if (!auditData.length) {
            bodyEl.innerHTML = `<tr><td colspan="8" class="p-12 text-center text-slate-400 font-bold">No vehicle audit records matching active criteria</td></tr>`;
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
            if (a.is_overstay) {
                statusPill = `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300 shadow-2xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-600 animate-pulse"></span>OVERSTAY (>8h)</span>`;
            } else if (a.status === 'Inside Facility' || a.status === 'Alert / Inside') {
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
            const accType = (thumb.access_type || '');
            if (accType.includes('VIP')) {
                methodPill = `<span class="text-[10px] font-black px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300">VIP Committee</span>`;
            } else if (accType.includes('Security Alert')) {
                methodPill = `<span class="text-[10px] font-black px-2.5 py-1 rounded-full bg-rose-100 text-rose-800 border border-rose-300">Security Alert</span>`;
            } else if (isMember) {
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
                    <div class="inline-flex items-center justify-end gap-2">
                        ${(a.status === 'Inside Facility' || a.status === 'Alert / Inside' || a.is_overstay || (!x && e)) ? `
                        <button type="button" onclick='event.stopPropagation(); triggerRowManualExit(${JSON.stringify(a).replace(/'/g, "&#39;")})' class="inline-flex items-center gap-1.5 text-xs font-bold text-amber-800 hover:text-white border border-amber-300 hover:bg-amber-600 rounded-xl px-2.5 py-1.5 bg-amber-50 shadow-2xs transition" title="Manually record vehicle departure">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
                            <span>Manual Exit</span>
                        </button>
                        ` : ''}
                        <button type="button" onclick='openAudit(${JSON.stringify(a).replace(/'/g, "&#39;")})' class="inline-flex items-center gap-1.5 text-xs font-extrabold text-indigo-700 hover:text-indigo-900 border border-indigo-200 rounded-xl px-3.5 py-1.5 bg-indigo-50/80 hover:bg-indigo-100 shadow-2xs transition">
                            <svg class="w-3.5 h-3.5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                            <span>Create Report</span>
                        </button>
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

let currentReportIncident = null;
let currentReportEntryImg = null;
let currentReportExitImg = null;
let currentReportMovements = [];
let currentReportAvailableImages = [];
let currentReportAnalysis = null;
let reportGalleryDirectionFilter = 'all';
let reportGallerySearchQuery = '';

function openAudit(a) {
    let e = a.entry, x = a.exit;
    if (e && x && e.timestamp && x.timestamp && String(e.timestamp) > String(x.timestamp)) {
        const tmp = e; e = x; x = tmp;
    }
    const v = e || x || {};
    const isUnreg = Boolean((v.access_type || '').includes('Unknown') || (v.name || '').includes('Unregistered'));
    const isNoTag = Boolean((v.access_type || '').includes('No RFID') || !v.scanned_tag || v.scanned_tag === 'NO_TAG');
    const isMember = !isUnreg && !isNoTag && v.mem_id && !['GUEST-LOG', 'AI-CAM'].includes(v.mem_id);
    const epc = (v.scanned_tag && v.scanned_tag !== 'NO_TAG') ? v.scanned_tag : '';

    currentReportIncident = a;
    currentReportAnalysis = null;
    currentReportEntryImg = (e && e.image_path) ? e.image_path : null;
    currentReportExitImg = (x && x.image_path) ? x.image_path : null;
    currentReportMovements = [];

    const visitDate = String((e && e.timestamp) || (x && x.timestamp) || '').substring(0, 10) || new Date().toISOString().substring(0, 10);

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

    document.getElementById('auditModalContent').innerHTML = `
    <div class="relative bg-white rounded-3xl overflow-hidden shadow-2xl">
        <div class="h-2.5 ${a.status === 'Exited' || a.status === 'Exit Only' ? 'bg-gradient-to-r from-slate-400 to-slate-600' : 'bg-gradient-to-r from-emerald-500 to-teal-600'}"></div>
        <div class="p-6 md:p-8">
            <!-- Modal Header -->
            <div class="flex justify-between items-start border-b border-slate-200/80 pb-6 mb-6 flex-wrap gap-4">
                <div class="flex items-center gap-5">
                    <img src="/api/logo" class="h-14 object-contain" onerror="this.style.display='none'">
                    <div>
                        <div class="flex items-center gap-3">
                            <h1 class="text-xl md:text-2xl font-black text-slate-900 tracking-tight uppercase">Official Vehicle Audit &amp; Report Studio</h1>
                            <span class="font-mono text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-0.5 rounded-lg border border-slate-200">AUD-${String(v.id || 1).padStart(6, '0')}</span>
                        </div>
                        <p class="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Karachi Gymkhana Club &bull; Human-Curated Evidence &amp; Transit Verification</p>
                        <div class="flex flex-wrap gap-2 mt-2.5">
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full ${isMember ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : isUnreg ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}">
                                ${isMember ? 'RFID VERIFIED MEMBER' : isUnreg ? 'UNKNOWN RFID TAG' : 'OPTICAL CAPTURE - NO RFID'}
                            </span>
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">${(v.direction || 'ENTRY').toUpperCase()} TRANSIT</span>
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">DATE: ${visitDate}</span>
                        </div>
                    </div>
                </div>
                <div class="text-right text-xs text-slate-500 space-y-1">
                    <button type="button" onclick="closeAudit()" class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-400 hover:text-slate-700 font-bold flex items-center justify-center text-lg transition ml-auto mb-2">&times;</button>
                    <p class="text-[11px]"><span class="font-bold text-slate-400">Timestamp:</span> <span class="font-mono font-bold text-slate-700">${v.timestamp || '--'}</span></p>
                    <p class="text-[11px]"><span class="font-bold text-slate-400">Status:</span> <span class="inline-block text-[10px] font-black px-2 py-0.5 rounded-full ${a.status === 'Inside Facility' ? 'bg-emerald-100 text-emerald-800' : a.status === 'Exited' || a.status === 'Exit Only' ? 'bg-slate-100 text-slate-700' : 'bg-amber-100 text-amber-800'}">${(a.status || 'Inside Facility').toUpperCase()}</span></p>
                    ${(a.status === 'Inside Facility' || a.status === 'Alert / Inside' || a.is_overstay || (!x && e)) ? `
                    <div class="pt-1.5">
                        <button type="button" onclick="openManualExitFromAuditModal()" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs shadow-sm transition">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
                            <span>Mark Vehicle Exited</span>
                        </button>
                    </div>` : ''}
                </div>
            </div>

            <!-- Subject Particulars Grid -->
            <div class="grid grid-cols-1 md:grid-cols-12 gap-4 mb-6">
                <div class="md:col-span-5 bg-slate-50/70 rounded-2xl p-5 border border-slate-200">
                    <p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Driver / Member Identity</p>
                    <div class="flex items-center gap-4 mb-4">
                        ${(v.profile_pic || v.Profile_pic) ? `<img src="/${(v.profile_pic || v.Profile_pic).replace(/^\//, '')}" class="w-16 h-16 rounded-2xl object-cover border border-slate-200 shadow-xs">` :
                        `<div class="w-16 h-16 rounded-2xl ${isUnreg || isNoTag ? 'bg-amber-100 text-amber-700' : 'bg-slate-200 text-slate-700'} flex items-center justify-center text-2xl font-black">${(v.name || '?').charAt(0)}</div>`}
                        <div>
                            <p class="font-extrabold text-base text-slate-900">${v.name || 'Unregistered Driver'}</p>
                            <p class="text-xs text-slate-500 font-mono mt-0.5">${v.mem_id || 'N/A'}</p>
                            <p class="text-[10px] font-bold ${isMember ? 'text-emerald-700' : 'text-amber-700'} mt-1 uppercase tracking-wide">${isMember ? 'Club Member' : 'Visitor Tag'}</p>
                        </div>
                    </div>
                    <div class="space-y-2 text-xs border-t border-slate-200/80 pt-3">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Member Account</span><span class="font-mono font-bold text-slate-800">${v.mem_id || 'N/A'}</span></div>
                        <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">RFID EPC Tag</span>${epc ? `<button type="button" onclick="closeAudit(); auditEtag('${epc}')" class="font-mono font-bold text-emerald-700 hover:text-emerald-900 hover:underline text-[11px] truncate max-w-[60%] select-all flex items-center gap-1" title="Click to audit this E-TAG">${epc} <span class="text-[9px] bg-emerald-100 px-1 rounded text-emerald-800 font-sans">Audit &rarr;</span></button>` : `<span class="font-mono text-slate-400 text-[11px]">No RFID Assigned</span>`}</div>
                    </div>
                </div>

                <div class="md:col-span-4 bg-slate-50/70 rounded-2xl p-5 border border-slate-200">
                    <p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Vehicle Particulars</p>
                    <p class="font-mono font-black text-2xl text-indigo-700 tracking-wider">${v.vehicle_number || 'NO PLATE'}</p>
                    <p class="text-sm text-slate-700 font-bold mt-1">${v.make_model || 'Make/Model not specified'}</p>
                    <div class="space-y-2 text-xs border-t border-slate-200/80 pt-3 mt-3">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Gate Station</span><span class="font-bold font-mono text-slate-800">${v.gate_no || 'Gate-01'}</span></div>
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Verification Protocol</span><span class="font-bold text-slate-800">${v.access_type || 'UHF RFID'}</span></div>
                    </div>
                </div>

                <div class="md:col-span-3 bg-slate-50/70 rounded-2xl p-5 border border-slate-200 text-center flex flex-col justify-between">
                    <div>
                        <p class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5" id="reportStayCardTitle">Facility Stay Duration</p>
                        <p class="text-3xl font-black ${modalDur ? 'text-indigo-700' : 'text-slate-400'} py-1" id="reportStayCardValue">${modalDur || '--'}</p>
                        <div id="reportStayCardSub" class="text-[10px] font-bold text-slate-400 mb-1">Transit Passage Duration</div>
                    </div>
                    <div class="space-y-1.5 text-xs border-t border-slate-200/80 pt-3 text-left" id="reportStayCardBreakdown">
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Entry:</span><span class="font-bold text-slate-800 font-mono text-[11px]">${e ? String(e.timestamp).substring(11, 19) : '--'}</span></div>
                        <div class="flex justify-between"><span class="text-slate-400 font-bold">Exit:</span><span class="font-bold text-slate-800 font-mono text-[11px]">${x ? String(x.timestamp).substring(11, 19) : '--'}</span></div>
                    </div>
                </div>
            </div>

            <!-- SECTION 1: All-Day In/Out Movements Chronology -->
            <div class="border border-slate-200 rounded-2xl p-5 bg-white mb-6 shadow-2xs">
                <div class="flex justify-between items-center mb-3 flex-wrap gap-2">
                    <div>
                        <h3 class="text-xs font-black text-slate-800 uppercase tracking-wider flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-indigo-600"></span>
                            Full-Day Movement Chronology (All-Day In/Out Journal)
                        </h3>
                        <p class="text-[11px] text-slate-500">Chronological transit sequence recorded for this vehicle across all gates on ${visitDate}</p>
                    </div>
                    <span id="reportMovementsCountBadge" class="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">Loading Journal...</span>
                </div>
                <div id="reportMovementsContainer" class="overflow-x-auto min-h-[70px]">
                    <div class="py-6 text-center text-xs text-slate-400">Loading daily movements...</div>
                </div>
            </div>

            <!-- SECTION 2: Optical Camera Evidence Selector -->
            <div class="border border-slate-200 rounded-2xl p-5 bg-slate-50/40 mb-6 shadow-2xs">
                <div class="flex justify-between items-center mb-4 flex-wrap gap-2">
                    <div>
                        <h3 class="text-xs font-black text-slate-800 uppercase tracking-wider flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-emerald-600"></span>
                            Curate Optical Evidence Proof
                        </h3>
                        <p class="text-[11px] text-slate-500">Hand-pick Entry &amp; Exit camera frames to attach directly into the official security report.</p>
                    </div>
                    <span class="text-[10px] font-extrabold text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-lg">HUMAN VERIFIED EVIDENCE</span>
                </div>

                <!-- Currently Selected Proof Cards (Side-by-Side) -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                    <div id="selectedEntryProofSlot" class="bg-white rounded-2xl p-4 border border-slate-200 shadow-2xs"></div>
                    <div id="selectedExitProofSlot" class="bg-white rounded-2xl p-4 border border-slate-200 shadow-2xs"></div>
                </div>

                <!-- Available Camera Captures Gallery -->
                <div class="bg-white rounded-2xl p-4 border border-slate-200">
                    <div class="flex justify-between items-center mb-3 flex-wrap gap-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-slate-700">Available System Camera Captures (${visitDate})</span>
                            <span id="reportGalleryCount" class="text-[11px] font-mono text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded-full font-bold">Loading captures...</span>
                        </div>
                        <div class="flex items-center gap-2 flex-wrap">
                            <div class="flex items-center rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-[11px] font-bold">
                                <button type="button" id="btnReportFilterAll" onclick="filterReportGallery('direction', 'all')" class="px-2.5 py-0.5 rounded-md bg-white text-indigo-700 shadow-2xs font-extrabold">All</button>
                                <button type="button" id="btnReportFilterEntry" onclick="filterReportGallery('direction', 'entry')" class="px-2.5 py-0.5 rounded-md text-slate-500 hover:text-slate-800">Entry</button>
                                <button type="button" id="btnReportFilterExit" onclick="filterReportGallery('direction', 'exit')" class="px-2.5 py-0.5 rounded-md text-slate-500 hover:text-slate-800">Exit</button>
                            </div>
                            <div class="relative">
                                <input type="text" id="reportGallerySearchInput" oninput="filterReportGallery('search', this.value)"
                                       placeholder="Filter by time (e.g. 17:30)..."
                                       class="text-[11px] px-3 py-1 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:border-indigo-500 w-44 sm:w-56 font-mono">
                            </div>
                            <button type="button" onclick="loadReportAvailableImages('${visitDate}')" title="Reload All Captures"
                                    class="p-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-600 transition flex items-center justify-center">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                            </button>
                        </div>
                    </div>
                    <div id="reportCameraGalleryContainer" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-96 overflow-y-auto p-2 bg-slate-50/60 rounded-xl border border-slate-100">
                        <div class="col-span-full py-8 text-center text-xs text-slate-400">Loading camera captures for this date...</div>
                    </div>
                </div>
            </div>

            <!-- SECTION 3: Investigator Remarks & Notes -->
            <div class="mb-6">
                <label class="block text-[11px] font-black uppercase tracking-wider text-slate-500 mb-2">Security Officer Remarks / Incident Notes (Included in PDF)</label>
                <textarea id="reportNotesInput" rows="2" placeholder="Enter optional security observations or officer remarks to attach to this official PDF certificate..."
                          class="w-full text-xs font-medium border border-slate-200 rounded-xl p-3 bg-white focus:outline-none focus:border-indigo-500 shadow-2xs"></textarea>
            </div>

            <!-- SECTION 4: Action Footer -->
            <div class="flex justify-between items-center pt-5 border-t border-slate-200/80 flex-wrap gap-3">
                <div class="text-xs text-slate-500 flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                    <span>Ready to compile authenticated document with selected optical proof.</span>
                </div>
                <div class="flex items-center gap-3">
                    <button type="button" onclick="closeAudit()" class="px-5 py-2.5 rounded-xl font-bold text-xs border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs transition">Cancel</button>
                    <button type="button" id="btnGenerateCustomPdf" onclick="generateCustomReportPdf()"
                            class="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl font-bold text-xs text-white bg-indigo-600 hover:bg-indigo-700 border border-indigo-700 shadow-sm transition">
                        <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                        <span>Generate Official PDF Report</span>
                    </button>
                </div>
            </div>
        </div>
    </div>`;

    document.getElementById('auditModal').classList.remove('hidden');

    // Load dynamic data
    updateSelectedEvidenceUI();
    loadReportMovements(v.vehicle_number, v.mem_id, visitDate, modalDur);
    loadReportAvailableImages(visitDate);
}

function updateSelectedEvidenceUI() {
    const entrySlot = document.getElementById('selectedEntryProofSlot');
    const exitSlot = document.getElementById('selectedExitProofSlot');
    if (!entrySlot || !exitSlot) return;

    if (currentReportEntryImg) {
        entrySlot.innerHTML = `
            <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                    <img src="/${currentReportEntryImg.replace(/^\//, '')}" class="w-20 h-14 object-cover rounded-xl border border-emerald-300 shadow-2xs cursor-pointer" onclick="window.open('/${currentReportEntryImg.replace(/^\//, '')}')">
                    <div>
                        <span class="text-[10px] font-black px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase">Selected Entry Proof</span>
                        <p class="text-xs font-mono font-bold text-slate-800 mt-1 truncate max-w-[200px]">${currentReportEntryImg.split('/').pop()}</p>
                        <p class="text-[10px] text-slate-400">Click image to expand</p>
                    </div>
                </div>
                <button type="button" onclick="clearReportProofImage('entry')" class="text-xs font-bold text-slate-400 hover:text-rose-600 transition p-1" title="Remove">&times; Remove</button>
            </div>
        `;
    } else {
        entrySlot.innerHTML = `
            <div class="flex items-center justify-between p-2 text-slate-400 text-xs">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-slate-300"></span>
                    <span class="font-bold">No Entry Proof Selected</span>
                </div>
                <span class="text-[10px] text-slate-400 italic">Pick from captures below</span>
            </div>
        `;
    }

    if (currentReportExitImg) {
        exitSlot.innerHTML = `
            <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                    <img src="/${currentReportExitImg.replace(/^\//, '')}" class="w-20 h-14 object-cover rounded-xl border border-indigo-300 shadow-2xs cursor-pointer" onclick="window.open('/${currentReportExitImg.replace(/^\//, '')}')">
                    <div>
                        <span class="text-[10px] font-black px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 uppercase">Selected Exit Proof</span>
                        <p class="text-xs font-mono font-bold text-slate-800 mt-1 truncate max-w-[200px]">${currentReportExitImg.split('/').pop()}</p>
                        <p class="text-[10px] text-slate-400">Click image to expand</p>
                    </div>
                </div>
                <button type="button" onclick="clearReportProofImage('exit')" class="text-xs font-bold text-slate-400 hover:text-rose-600 transition p-1" title="Remove">&times; Remove</button>
            </div>
        `;
    } else {
        exitSlot.innerHTML = `
            <div class="flex items-center justify-between p-2 text-slate-400 text-xs">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-slate-300"></span>
                    <span class="font-bold">No Exit Proof Selected</span>
                </div>
                <span class="text-[10px] text-slate-400 italic">Pick from captures below</span>
            </div>
        `;
    }
}

function setReportProofImage(type, imagePath) {
    if (type === 'entry') {
        currentReportEntryImg = imagePath;
    } else {
        currentReportExitImg = imagePath;
    }
    updateSelectedEvidenceUI();
}

function clearReportProofImage(type) {
    if (type === 'entry') {
        currentReportEntryImg = null;
    } else {
        currentReportExitImg = null;
    }
    updateSelectedEvidenceUI();
}

async function loadReportMovements(vehicleNumber, memId, dateStr, tripDuration) {
    const cont = document.getElementById('reportMovementsContainer');
    const badge = document.getElementById('reportMovementsCountBadge');
    if (!cont) return;

    try {
        const queryParams = new URLSearchParams({
            vehicle_number: vehicleNumber || '',
            mem_id: memId || '',
            date: dateStr || ''
        });
        const res = await fetch(`/api/audit/day-movements?${queryParams}`);
        if (!res.ok) throw new Error('Failed to fetch daily movements');
        const data = await res.json();
        currentReportMovements = data.movements || [];
        currentReportAnalysis = data;

        const stayTitle = document.getElementById('reportStayCardTitle');
        const stayVal = document.getElementById('reportStayCardValue');
        const staySub = document.getElementById('reportStayCardSub');
        const stayBreakdown = document.getElementById('reportStayCardBreakdown');

        if (data.visits_count > 1) {
            if (stayTitle) {
                stayTitle.innerHTML = `Total Daily Stay <span class="bg-indigo-100 text-indigo-700 text-[10px] font-black px-2 py-0.5 rounded-full ml-1 border border-indigo-200">${data.visits_count} Visits Today</span>`;
            }
            if (stayVal) {
                stayVal.innerText = data.total_stay_duration || '--';
                stayVal.className = 'text-3xl font-black text-indigo-700 py-1';
            }
            if (staySub) {
                staySub.innerHTML = `<span class="text-indigo-600 font-extrabold">Cumulative Stay Across Complete Day</span>`;
            }
            if (stayBreakdown) {
                stayBreakdown.innerHTML = `
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">Total Daily Stay:</span><span class="font-black text-indigo-700 font-mono text-xs">${data.total_stay_duration} (${data.visits_count} Visits)</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">This Transit Trip:</span><span class="font-bold text-slate-800 font-mono text-[11px]">${tripDuration || currentReportIncident?.duration || '--'}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">First Entry Today:</span><span class="font-bold text-slate-700 font-mono text-[11px]">${data.first_entry_time || '--'}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-bold">Latest Exit Today:</span><span class="font-bold text-slate-700 font-mono text-[11px]">${data.last_exit_time || '--'}</span></div>
                `;
            }
        }

        if (badge) {
            if (data.visits_count > 1) {
                badge.innerHTML = `<span class="font-mono text-indigo-800 font-extrabold">${currentReportMovements.length} Passages</span> &bull; <span class="text-indigo-700 font-black">${data.visits_count} Visits</span> &bull; <span class="text-indigo-700 font-black">${data.total_stay_duration} Total Stay</span>`;
                badge.className = "text-[10px] font-black px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200";
            } else {
                badge.innerText = `${currentReportMovements.length} Total Passages Recorded`;
            }
        }

        if (currentReportMovements.length === 0) {
            cont.innerHTML = `<div class="py-4 text-center text-xs text-slate-400">No additional transits recorded for this vehicle on ${dateStr}.</div>`;
            return;
        }

        cont.innerHTML = `
            <table class="w-full text-left text-xs">
                <thead class="text-[10px] uppercase font-black text-slate-400 bg-slate-50 border-b">
                    <tr>
                        <th class="py-2.5 px-3">#</th>
                        <th class="py-2.5 px-3">Time (PKT)</th>
                        <th class="py-2.5 px-3">Movement</th>
                        <th class="py-2.5 px-3">Gate Station</th>
                        <th class="py-2.5 px-3">Access Protocol</th>
                        <th class="py-2.5 px-3">Visit Stay</th>
                        <th class="py-2.5 px-3">Verification Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${currentReportMovements.map((m, idx) => {
                        const isEntry = (m.direction || '').toLowerCase() === 'entry';
                        const timeStr = String(m.timestamp || '').substring(11, 19) || m.timestamp;
                        const isCurrent = currentReportIncident && (
                            (currentReportIncident.entry && currentReportIncident.entry.id === m.id) ||
                            (currentReportIncident.exit && currentReportIncident.exit.id === m.id) ||
                            (currentReportIncident.id === m.id)
                        );
                        const stayBadge = m.stay_duration ? 
                            `<span class="inline-flex items-center gap-1 font-mono font-bold text-xs text-indigo-700 bg-indigo-50 border border-indigo-200/80 px-2 py-0.5 rounded-md"><svg class="w-3 h-3 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>${m.stay_duration}</span>` :
                            `<span class="text-slate-300 font-mono text-xs">—</span>`;
                        return `
                            <tr class="${isCurrent ? 'bg-indigo-50/60 font-semibold' : 'hover:bg-slate-50/70'} transition">
                                <td class="py-2.5 px-3 font-mono font-bold text-slate-400">
                                    ${String(idx + 1).padStart(2, '0')}
                                    ${isCurrent ? '<span class="text-[9px] bg-indigo-600 text-white font-black px-1.5 py-0.5 rounded ml-1 uppercase tracking-wide">Selected</span>' : ''}
                                </td>
                                <td class="py-2.5 px-3 font-mono font-bold text-slate-800">${timeStr}</td>
                                <td class="py-2.5 px-3">
                                    <span class="text-[10px] font-black px-2 py-0.5 rounded-full ${isEntry ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-blue-50 text-blue-700 border border-blue-200'}">
                                        ${(m.direction || 'PASSAGE').toUpperCase()}
                                    </span>
                                </td>
                                <td class="py-2.5 px-3 font-bold text-slate-700">${m.gate_no || 'Gate-01'}</td>
                                <td class="py-2.5 px-3 text-slate-600">${m.access_type || 'UHF RFID Access'}</td>
                                <td class="py-2.5 px-3">${stayBadge}</td>
                                <td class="py-2.5 px-3 font-bold ${isEntry ? 'text-emerald-700' : 'text-blue-700'}">
                                    ${isEntry ? 'Authorized Entry' : `Authorized Exit ${m.stay_duration ? `<span class="text-[11px] font-semibold text-slate-500">(${m.stay_duration} stay)</span>` : ''}`}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        cont.innerHTML = `<div class="py-3 text-center text-xs text-rose-500 font-bold">Could not load movement journal: ${err.message}</div>`;
    }
}

async function loadReportAvailableImages(dateStr) {
    const gallery = document.getElementById('reportCameraGalleryContainer');
    const countBadge = document.getElementById('reportGalleryCount');
    if (!gallery) return;

    reportGalleryDirectionFilter = 'all';
    reportGallerySearchQuery = '';
    const searchInput = document.getElementById('reportGallerySearchInput');
    if (searchInput) searchInput.value = '';
    updateReportFilterButtonsUI();

    try {
        gallery.innerHTML = `<div class="col-span-full py-8 text-center text-xs text-slate-400">Loading all camera captures for ${dateStr}...</div>`;
        const res = await fetch(`/api/audit/available-images?date=${encodeURIComponent(dateStr)}&limit=0`);
        if (!res.ok) throw new Error('Failed to load captures');
        const data = await res.json();
        currentReportAvailableImages = data.images || [];

        renderReportGalleryCards(dateStr);
    } catch (err) {
        gallery.innerHTML = `<div class="col-span-full py-4 text-center text-xs text-rose-500 font-bold">Failed to load camera gallery: ${err.message}</div>`;
        if (countBadge) countBadge.innerText = '0 Captures Available';
    }
}

function updateReportFilterButtonsUI() {
    ['all', 'entry', 'exit'].forEach(dir => {
        const btn = document.getElementById(`btnReportFilter${dir.charAt(0).toUpperCase() + dir.slice(1)}`);
        if (btn) {
            if (reportGalleryDirectionFilter === dir) {
                btn.className = 'px-2.5 py-0.5 rounded-md bg-white text-indigo-700 shadow-2xs font-extrabold';
            } else {
                btn.className = 'px-2.5 py-0.5 rounded-md text-slate-500 hover:text-slate-800';
            }
        }
    });
}

function filterReportGallery(type, value) {
    if (type === 'direction') {
        reportGalleryDirectionFilter = value;
        updateReportFilterButtonsUI();
    } else if (type === 'search') {
        reportGallerySearchQuery = (value || '').toLowerCase().trim();
    }
    renderReportGalleryCards();
}

function renderReportGalleryCards(optDateStr) {
    const gallery = document.getElementById('reportCameraGalleryContainer');
    const countBadge = document.getElementById('reportGalleryCount');
    if (!gallery) return;

    const filtered = (currentReportAvailableImages || []).filter(img => {
        // Direction check
        if (reportGalleryDirectionFilter !== 'all') {
            const dir = (img.direction || '').toLowerCase();
            if (reportGalleryDirectionFilter === 'entry' && !dir.includes('entry') && !dir.includes('in')) {
                return false;
            }
            if (reportGalleryDirectionFilter === 'exit' && !dir.includes('exit') && !dir.includes('out')) {
                return false;
            }
        }
        // Search query check
        if (reportGallerySearchQuery) {
            const matchTime = (img.timestamp || '').toLowerCase().includes(reportGallerySearchQuery);
            const matchEvent = (img.event_type || '').toLowerCase().includes(reportGallerySearchQuery);
            const matchPlate = (img.vehicle_number || '').toLowerCase().includes(reportGallerySearchQuery);
            const matchPath = (img.image_path || '').toLowerCase().includes(reportGallerySearchQuery);
            if (!matchTime && !matchEvent && !matchPlate && !matchPath) return false;
        }
        return true;
    });

    if (countBadge) {
        if (filtered.length === currentReportAvailableImages.length) {
            countBadge.innerText = `${currentReportAvailableImages.length} Captures Available (All events for this date)`;
        } else {
            countBadge.innerText = `Showing ${filtered.length} of ${currentReportAvailableImages.length} Captures`;
        }
    }

    if (filtered.length === 0) {
        gallery.innerHTML = `<div class="col-span-full py-8 text-center text-xs text-slate-400">No camera captures match filter (${reportGalleryDirectionFilter !== 'all' ? reportGalleryDirectionFilter : 'all'} ${reportGallerySearchQuery ? `"${reportGallerySearchQuery}"` : ''}).</div>`;
        return;
    }

    gallery.innerHTML = filtered.map(img => {
        const cleanPath = (img.image_path || '').replace(/^\//, '');
        const timePart = String(img.timestamp || '').substring(11, 19) || img.timestamp;
        const dir = (img.direction || 'Crossing').toUpperCase();
        const isEntry = dir.includes('ENTRY') || dir.includes('IN');
        return `
            <div class="bg-white rounded-xl border border-slate-200 p-2 shadow-2xs hover:shadow-sm transition flex flex-col justify-between">
                <div>
                    <div class="relative rounded-lg overflow-hidden bg-slate-100 aspect-video mb-1.5 cursor-pointer" onclick="window.open('/${cleanPath}')">
                        <img loading="lazy" src="/${cleanPath}" class="w-full h-full object-cover" onerror="this.src='/static/img/no-car.svg'">
                        <span class="absolute bottom-1 left-1 text-[9px] font-mono font-bold bg-slate-900/80 text-white px-1.5 py-0.5 rounded">${timePart}</span>
                    </div>
                    <div class="flex items-center justify-between text-[10px] mb-2">
                        <span class="font-bold text-slate-700 truncate max-w-[65%]" title="${img.event_type || 'Camera Event'}">${img.event_type || 'Camera Event'}</span>
                        <span class="font-bold ${isEntry ? 'text-emerald-700' : 'text-indigo-700'}">${dir}</span>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-1 pt-1 border-t border-slate-100">
                    <button type="button" onclick="setReportProofImage('entry', '${cleanPath}')"
                            class="px-1.5 py-1 text-[10px] font-bold rounded-lg bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200 transition text-center" title="Set as Entry Optical Evidence">
                        + Entry
                    </button>
                    <button type="button" onclick="setReportProofImage('exit', '${cleanPath}')"
                            class="px-1.5 py-1 text-[10px] font-bold rounded-lg bg-indigo-50 text-indigo-800 hover:bg-indigo-100 border border-indigo-200 transition text-center" title="Set as Exit Optical Evidence">
                        + Exit
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function generateCustomReportPdf() {
    const btn = document.getElementById('btnGenerateCustomPdf');
    if (!btn || !currentReportIncident) return;

    const originalText = btn.innerHTML;
    try {
        btn.innerHTML = `
            <svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
            <span>Compiling Executive PDF...</span>
        `;
        btn.disabled = true;

        const notes = (document.getElementById('reportNotesInput') ? document.getElementById('reportNotesInput').value : '').trim();

        const isMultiVisit = Boolean(currentReportAnalysis && currentReportAnalysis.visits_count > 1);
        const resolvedDuration = isMultiVisit ? currentReportAnalysis.total_stay_duration : (currentReportIncident?.duration || null);

        const payload = {
            incident: currentReportIncident,
            entry: currentReportIncident?.entry || null,
            exit: currentReportIncident?.exit || null,
            duration: resolvedDuration,
            single_trip_duration: currentReportIncident?.duration || null,
            total_stay_duration: currentReportAnalysis?.total_stay_duration || null,
            visits_count: currentReportAnalysis?.visits_count || null,
            first_entry_time: currentReportAnalysis?.first_entry_time || null,
            last_exit_time: currentReportAnalysis?.last_exit_time || null,
            status: currentReportIncident?.status || null,
            entry_image_path: currentReportEntryImg,
            exit_image_path: currentReportExitImg,
            daily_movements: currentReportMovements,
            notes: notes
        };

        const res = await fetch('/api/audit/custom-report/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errJson = await res.json().catch(() => ({}));
            throw new Error(errJson.detail || `Server error (${res.status})`);
        }

        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank');
    } catch (err) {
        alert(`Failed to generate report PDF: ${err.message}`);
    } finally {
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
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
        if (document.getElementById('memSubtabBadge')) document.getElementById('memSubtabBadge').innerText = (data.unique_members || 0).toLocaleString();

        if (!members.length) {
            bodyEl.innerHTML = `<tr><td colspan="7" class="p-12 text-center text-slate-400 font-bold">No registered members found matching query</td></tr>`;
            renderMemPagination(0, 1, 1, currentMemLimit);
            loadUnregisteredTags(true);
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

            const isInside = (m.Current_Location || 'Outside') === 'Inside';
            const locationBadge = isInside ?
                `<span class="font-bold text-xs bg-emerald-50 text-emerald-700 border border-emerald-200/90 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5 shadow-2xs">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>Inside Club
                 </span>` :
                `<span class="font-bold text-xs bg-slate-50 text-slate-600 border border-slate-200 px-2.5 py-1 rounded-lg inline-flex items-center gap-1.5 shadow-2xs">
                    <span class="w-2 h-2 rounded-full bg-slate-400"></span>Outside Club
                 </span>`;

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
                    ${locationBadge}
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
        loadUnregisteredTags(true);
    } catch (err) {
        bodyEl.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-rose-500 font-bold">Error loading members: ${err.message}</td></tr>`;
    }
}

let currentMemberSubtab = 'members';

function switchMemberSubtab(tabName) {
    currentMemberSubtab = tabName;
    const isMem = tabName === 'members';
    
    const subtabMemBtn = document.getElementById('subtabMemBtn');
    const subtabUnregBtn = document.getElementById('subtabUnregBtn');
    const viewMem = document.getElementById('subtabViewMembers');
    const viewUnreg = document.getElementById('subtabViewUnregistered');

    if (subtabMemBtn && subtabUnregBtn && viewMem && viewUnreg) {
        if (isMem) {
            subtabMemBtn.className = "px-4 py-2 text-xs font-extrabold rounded-t-xl bg-white border-t border-l border-r border-slate-200 text-indigo-700 shadow-xs flex items-center gap-2";
            subtabUnregBtn.className = "px-4 py-2 text-xs font-bold rounded-t-xl text-slate-600 hover:text-slate-900 hover:bg-slate-200/50 transition flex items-center gap-2";
            viewMem.classList.remove('hidden');
            viewUnreg.classList.add('hidden');
        } else {
            subtabUnregBtn.className = "px-4 py-2 text-xs font-extrabold rounded-t-xl bg-white border-t border-l border-r border-slate-200 text-amber-700 shadow-xs flex items-center gap-2";
            subtabMemBtn.className = "px-4 py-2 text-xs font-bold rounded-t-xl text-slate-600 hover:text-slate-900 hover:bg-slate-200/50 transition flex items-center gap-2";
            viewMem.classList.add('hidden');
            viewUnreg.classList.remove('hidden');
            loadUnregisteredTags(false);
        }
    }
}

async function loadUnregisteredTags(countOnly = false) {
    try {
        const res = await fetch('/api/unregistered-tags?limit=50');
        if (!res.ok) return;
        const tags = await res.json();
        
        const badge = document.getElementById('unregSubtabBadge');
        const statEl = document.getElementById('statUnregTags');
        if (badge) badge.innerText = tags.length.toLocaleString();
        if (statEl) statEl.innerText = tags.length.toLocaleString();

        if (countOnly) return;

        const body = document.getElementById('unregBody');
        if (!body) return;

        if (!tags.length) {
            body.innerHTML = '<tr><td colspan="6" class="p-12 text-center text-slate-400 font-bold">No unassigned RFID tags detected at the gates yet</td></tr>';
            return;
        }

        body.innerHTML = tags.map(t => {
            const dirBadge = t.direction === 'Exit' ?
                '<span class="px-2.5 py-1 text-xs font-bold rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200/80">Exit Gate</span>' :
                '<span class="px-2.5 py-1 text-xs font-bold rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200/80">Entry Gate</span>';

            return `
            <tr class="hover:bg-amber-50/40 transition">
                <td class="p-3.5 pl-5">
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-xs font-extrabold text-amber-900 bg-amber-50 border border-amber-200/90 px-2.5 py-1 rounded-lg select-all">${t.tag}</span>
                        <button type="button" onclick="navigator.clipboard.writeText('${t.tag}'); this.innerText='Copied!'; setTimeout(() => this.innerText='Copy', 1500);"
                                class="text-[10px] font-bold text-slate-500 hover:text-slate-800 bg-white border border-slate-200 px-2 py-0.5 rounded shadow-2xs">
                            Copy
                        </button>
                    </div>
                </td>
                <td class="p-3.5 text-xs text-slate-500 font-medium">${t.first_seen || '--'}</td>
                <td class="p-3.5 text-xs text-slate-700 font-bold">${t.last_seen || '--'}</td>
                <td class="p-3.5">${dirBadge}</td>
                <td class="p-3.5">
                    <span class="font-bold text-xs bg-slate-100 text-slate-700 px-2.5 py-1 rounded-md">${t.read_count || 1} Scans</span>
                </td>
                <td class="p-3.5 text-right pr-6">
                    <div class="flex items-center justify-end gap-2">
                        <button type="button" onclick="assignUnregisteredTagToMember('${t.tag}')"
                                class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3.5 py-1.5 rounded-xl shadow-xs transition inline-flex items-center gap-1.5">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                            1-Click Assign
                        </button>
                        <button type="button" onclick="dismissUnregisteredTag('${t.tag}')"
                                class="text-xs font-bold text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-200 rounded-xl px-2.5 py-1.5 bg-white hover:bg-rose-50 transition">
                            Dismiss
                        </button>
                    </div>
                </td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error("Error loading unregistered tags:", e);
    }
}

function assignUnregisteredTagToMember(tag) {
    switchMemberSubtab('members');
    cancelEdit();
    const tagInput = document.getElementById('nTag');
    const statusEl = document.getElementById('epcStatus');
    const memInput = document.getElementById('nMemId');
    if (tagInput) tagInput.value = tag;
    if (statusEl) {
        statusEl.innerText = "Pre-filled from Unassigned RFID Tag buffer (" + tag.substring(0, 8) + "...)";
        statusEl.className = "text-xs mt-1 text-emerald-600 font-bold";
    }
    const formEl = document.getElementById('memberForm');
    if (formEl) {
        formEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (memInput) {
        memInput.focus();
    }
}

async function dismissUnregisteredTag(tag) {
    try {
        const res = await fetch(`/api/unregistered-tags/${encodeURIComponent(tag)}`, { method: 'DELETE' });
        if (res.ok) {
            loadUnregisteredTags(false);
        }
    } catch (e) {
        console.error("Error dismissing tag:", e);
    }
}

async function toggleVehicleLocation(rowId, memId) {
    try {
        const res = await fetch('/api/members/toggle-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: rowId })
        });
        if (res.ok) {
            await openMemberFleetModal(memId);
            loadMembers(currentMemPage);
        }
    } catch (e) {
        console.error("Toggle location error:", e);
    }
}

function closeMemberFleetModal() {
    const modal = document.getElementById('memberFleetModal');
    if (modal) modal.classList.add('hidden');
}

async function openMemberFleetModal(m) {
    const modal = document.getElementById('memberFleetModal');
    const content = document.getElementById('memberFleetModalContent');
    if (!modal || !content) return;

    if (typeof m === 'string' || typeof m === 'number') {
        const memId = String(m);
        try {
            const res = await fetch(`/api/members/${encodeURIComponent(memId)}/vehicles`);
            if (res.ok) {
                const fleet = await res.json();
                m = {
                    Mem_id: fleet.mem_id || memId,
                    Name: fleet.name || `Member #${memId}`,
                    Profile_pic: fleet.profile_pic || '',
                    Status: fleet.status || 'Active',
                    Current_Location: fleet.current_location || 'Outside',
                    vehicles: fleet.vehicles || []
                };
            } else {
                m = { Mem_id: memId, Name: `Member #${memId}`, vehicles: [] };
            }
        } catch (e) {
            m = { Mem_id: memId, Name: `Member #${memId}`, vehicles: [] };
        }
    }

    const vehicles = m.vehicles || [];
    const initial = m.Name ? m.Name.charAt(0).toUpperCase() : '?';
    const vCount = vehicles.length;
    const taggedCount = vehicles.filter(v => v.E_tag_id && v.E_tag_id.trim()).length;
    const isInsideMember = (m.Current_Location || 'Outside') === 'Inside' || vehicles.some(v => (v.Current_Location || 'Outside') === 'Inside');

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
                        <div class="flex flex-wrap gap-2 mt-2.5">
                            <span class="text-[10px] font-black px-2.5 py-0.5 rounded-full ${isInsideMember ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-700 border border-slate-200'} uppercase inline-flex items-center gap-1">
                                <span class="w-1.5 h-1.5 rounded-full ${isInsideMember ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}"></span>
                                ${isInsideMember ? 'Currently Inside Club' : 'Currently Outside'}
                            </span>
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
                    <h3 class="text-base font-extrabold text-slate-800">Authorized Vehicles & Location State</h3>
                    <p class="text-xs text-slate-500">Live gate presence tracking and registered RFID transponders authorized under this membership</p>
                </div>
                ${(currentUser && currentUser.role === 'Viewer') ? '' : `
                <button type="button" onclick='addVehicleToMember("${m.Mem_id}", "${m.Name.replace(/"/g, '&quot;')}", "${m.Profile_pic || ''}")'
                        class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-sm flex items-center gap-2 transition">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    Register Another Vehicle
                </button>
                `}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                ${vehicles.map((v, idx) => {
                    const hasTag = v.E_tag_id && v.E_tag_id.trim().length > 0;
                    const vInside = (v.Current_Location || 'Outside') === 'Inside';
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

                            <!-- Live Gate Location Ribbon -->
                            <div class="flex items-center justify-between mb-3 px-3 py-2 bg-white rounded-xl border border-slate-200 shadow-2xs">
                                <div class="flex items-center gap-2">
                                    <span class="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">Gate Location:</span>
                                    ${vInside ?
                                    '<span class="text-xs font-black text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-lg inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>Inside Club</span>' :
                                    '<span class="text-xs font-bold text-slate-600 bg-slate-50 border border-slate-200 px-2.5 py-0.5 rounded-lg inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>Outside Club</span>'}
                                </div>
                                ${(currentUser && currentUser.role === 'Viewer') ? '' : `
                                <button type="button" onclick="toggleVehicleLocation(${v.id}, '${m.Mem_id}')"
                                        class="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2.5 py-1 rounded-lg transition">
                                    Switch to ${vInside ? 'Outside' : 'Inside'}
                                </button>
                                `}
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

                        ${(currentUser && currentUser.role === 'Viewer') ? '' : `
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
                        `}
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

async function resetActivityData() {
    const confirmed = confirm(
        "Are you sure you want to reset all previous activity and audit logs?\n\n" +
        "This will:\n" +
        "- Clear all past vehicle passage logs\n" +
        "- Clear raw RFID scans and camera audit captures\n" +
        "- Retain 100% of Member Directory records (10,798)\n" +
        "- Retain all Hardware and System Settings\n\n" +
        "Click OK to proceed with the reset."
    );
    if (!confirmed) return;

    const noticeEl = document.getElementById('resetActivityNotice');
    if (noticeEl) {
        noticeEl.textContent = 'Resetting activity data...';
        noticeEl.className = 'text-xs text-amber-600 font-semibold';
    }

    try {
        const res = await fetch('/api/settings/reset-activity', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.ok) {
            if (noticeEl) {
                noticeEl.textContent = data.message;
                noticeEl.className = 'text-xs text-emerald-600 font-semibold';
            }
            alert(data.message || 'Activity data successfully reset.');
            if (typeof loadStats === 'function') loadStats();
            if (typeof loadLogs === 'function') loadLogs(1);
            if (typeof loadCameraAudit === 'function') loadCameraAudit(1);
            if (typeof loadMembers === 'function') loadMembers();
        } else {
            alert('Reset failed: ' + (data.detail || data.message || 'Unknown error'));
            if (noticeEl) {
                noticeEl.textContent = 'Reset failed.';
                noticeEl.className = 'text-xs text-rose-600 font-semibold';
            }
        }
    } catch (err) {
        alert('Network error during reset: ' + err.message);
        if (noticeEl) {
            noticeEl.textContent = 'Network error.';
            noticeEl.className = 'text-xs text-rose-600 font-semibold';
        }
    }
}

function onCamAuditSearchInput() {
    clearTimeout(camAuditSearchTimer);
    camAuditSearchTimer = setTimeout(() => {
        loadCameraAudit(1);
    }, 300);
}

function setCamAuditPreset(preset) {
    currentCamAuditDate = preset;
    const startInput = document.getElementById('camAuditDate');
    const endInput = document.getElementById('camAuditEndDate');
    const todayBtn = document.getElementById('camPresetToday');
    const yestBtn = document.getElementById('camPresetYesterday');
    const weekBtn = document.getElementById('camPresetWeek');
    const allBtn = document.getElementById('camPresetAll');

    [todayBtn, yestBtn, weekBtn, allBtn].forEach(b => {
        if (b) {
            b.classList.remove('bg-slate-900', 'text-white');
            b.classList.add('text-slate-700', 'hover:bg-slate-100');
        }
    });

    const now = new Date();
    const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    if (preset === 'all') {
        if (startInput) startInput.value = '';
        if (endInput) endInput.value = '';
        if (allBtn) {
            allBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            allBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else if (preset === 'yesterday') {
        const y = new Date();
        y.setDate(y.getDate() - 1);
        const yStr = fmt(y);
        if (startInput) startInput.value = yStr;
        if (endInput) endInput.value = yStr;
        if (yestBtn) {
            yestBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            yestBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else if (preset === 'week') {
        const w = new Date();
        w.setDate(w.getDate() - 7);
        if (startInput) startInput.value = fmt(w);
        if (endInput) endInput.value = fmt(now);
        if (weekBtn) {
            weekBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            weekBtn.classList.add('bg-slate-900', 'text-white');
        }
    } else {
        const tStr = fmt(now);
        if (startInput) startInput.value = tStr;
        if (endInput) endInput.value = tStr;
        if (todayBtn) {
            todayBtn.classList.remove('text-slate-700', 'hover:bg-slate-100');
            todayBtn.classList.add('bg-slate-900', 'text-white');
        }
    }
    loadCameraAudit(1);
}

function onCamAuditDateChange() {
    const todayBtn = document.getElementById('camPresetToday');
    const yestBtn = document.getElementById('camPresetYesterday');
    const weekBtn = document.getElementById('camPresetWeek');
    const allBtn = document.getElementById('camPresetAll');
    [todayBtn, yestBtn, weekBtn, allBtn].forEach(b => {
        if (b) {
            b.classList.remove('bg-slate-900', 'text-white');
            b.classList.add('text-slate-700', 'hover:bg-slate-100');
        }
    });
    currentCamAuditDate = 'custom';
    loadCameraAudit(1);
}

function resetCamAuditFilters() {
    const searchInput = document.getElementById('camAuditSearch');
    if (searchInput) searchInput.value = '';
    const dirSelect = document.getElementById('camAuditDirection');
    if (dirSelect) dirSelect.value = 'all';
    const limitSelect = document.getElementById('camAuditLimitSelect');
    if (limitSelect) limitSelect.value = '24';
    currentCamAuditLimit = 24;
    setCamAuditPreset('today');
}

function changeCamAuditLimit() {
    const sel = document.getElementById('camAuditLimitSelect');
    if (sel) currentCamAuditLimit = parseInt(sel.value, 10) || 24;
    loadCameraAudit(1);
}

function openCamProofModalById(id) {
    const item = currentCamAuditItems.find(l => String(l.id) === String(id));
    if (item) {
        openCamProofModal(item);
    }
}

async function loadCameraAudit(page = currentCamAuditPage) {
    currentCamAuditPage = page;
    const startD = document.getElementById('camAuditDate')?.value || '';
    const endD = document.getElementById('camAuditEndDate')?.value || '';
    const dir = document.getElementById('camAuditDirection')?.value || 'all';
    const searchVal = document.getElementById('camAuditSearch')?.value || '';
    const gridEl = document.getElementById('camAuditGrid');
    if (!gridEl) return;

    // Show loading skeleton only on page transition if grid is empty
    if (!currentCamAuditItems.length) {
        gridEl.innerHTML = `<div class="col-span-full py-16 text-center text-slate-400 font-bold">Loading camera proof logs...</div>`;
    }

    try {
        const dateParam = (currentCamAuditDate === 'all' && !startD) ? 'all' : (startD || '');
        const url = `/api/camera-audit-logs?date=${encodeURIComponent(dateParam)}&start_date=${encodeURIComponent(startD)}&end_date=${encodeURIComponent(endD)}&direction=${encodeURIComponent(dir)}&page=${page}&limit=${currentCamAuditLimit}&search=${encodeURIComponent(searchVal)}`;
        const [logsRes, statsRes] = await Promise.all([
            fetch(url),
            fetch('/api/camera-audit-stats')
        ]);
        const data = await logsRes.json();
        const stats = await statsRes.json();

        if (document.getElementById('camStatToday')) document.getElementById('camStatToday').innerText = (stats.today_total || 0).toLocaleString();
        if (document.getElementById('camStatWeek')) document.getElementById('camStatWeek').innerText = (stats.week_total || 0).toLocaleString();
        if (document.getElementById('camStatMonth')) document.getElementById('camStatMonth').innerText = (stats.month_total || 0).toLocaleString();
        if (document.getElementById('camBadgeDate')) document.getElementById('camBadgeDate').innerText = data.date || 'Today';

        const logs = data.logs || [];
        currentCamAuditItems = logs;
        const total = data.total || 0;
        const totalPages = data.pages || Math.ceil(total / currentCamAuditLimit) || 1;

        if (!logs.length) {
            gridEl.innerHTML = `<div class="col-span-full py-20 text-center bg-slate-50 border border-dashed border-slate-200 rounded-3xl">
                <p class="text-sm font-bold text-slate-500">No camera line-crossing proof captures found ${searchVal ? `matching "${searchVal}"` : `for ${dateParam === 'all' ? 'the selected filter' : data.date}`}.</p>
                <p class="text-xs text-slate-400 mt-1">Incoming snapshots sent by Hikvision line-crossing triggers are ingested automatically.</p>
            </div>`;
            renderCamAuditPagination(0, 1, 1, currentCamAuditLimit);
            return;
        }

        gridEl.innerHTML = logs.map(item => {
            const rawPath = (item.image_path || '').replace(/^\/+/, '');
            const thumbSrc = rawPath ? `/api/thumbnail?path=${encodeURIComponent(rawPath)}&w=440&q=65` : '/static/img/no-car.svg';
            const origSrc = rawPath ? '/' + rawPath : '';
            const dirBadge = item.direction === 'Entry' ?
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-200">ENTRY</span>' :
                item.direction === 'Exit' ?
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-blue-100 text-blue-800 border border-blue-200">EXIT</span>' :
                '<span class="px-2 py-0.5 rounded-full text-[10px] font-black bg-slate-100 text-slate-700 border border-slate-200">LINE CROSS</span>';

            const cleanFileName = rawPath ? rawPath.split('/').pop() : '';

            return `
            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden hover:shadow-md hover:border-slate-300 transition duration-200 flex flex-col group">
                <div class="relative bg-slate-900 aspect-video overflow-hidden cursor-pointer" onclick="openCamProofModalById(${item.id})">
                    <img src="${thumbSrc}" alt="Vehicle Proof" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" onerror="this.onerror=null; this.src='${origSrc || '/static/img/no-car.svg'}';">
                    <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                        <span class="bg-white/90 text-slate-900 px-3 py-1.5 rounded-xl text-xs font-bold shadow-lg">Inspect Full HD</span>
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
                        <p class="text-[11px] text-slate-400 font-mono mt-2 truncate" title="${cleanFileName}">${cleanFileName}</p>
                    </div>
                    <div class="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <span class="text-[11px] font-bold text-slate-500">Camera Audit Proof</span>
                        <button type="button" onclick="openCamProofModalById(${item.id})" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 transition">
                            Inspect HD &rarr;
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

// ==========================================
// CAMERA PROOF MODAL & FORENSIC ZOOM TOOLS
// ==========================================
let camZoomState = {
    scale: 1.0,
    panX: 0,
    panY: 0,
    rotation: 0,
    isDragging: false,
    startX: 0,
    startY: 0,
    eventsBound: false
};

function updateCamProofTransform() {
    const img = document.getElementById('camProofModalImgHik');
    const badge = document.getElementById('camProofZoomLevel');
    const hud = document.getElementById('camProofZoomHud');
    if (!img) return;

    img.style.transform = `translate(${camZoomState.panX}px, ${camZoomState.panY}px) scale(${camZoomState.scale}) rotate(${camZoomState.rotation}deg)`;
    const pct = `${Math.round(camZoomState.scale * 100)}%`;
    if (badge) badge.innerText = pct;
    if (hud) hud.innerText = pct;
}

function camProofZoomIn() {
    camZoomState.scale = Math.min(6.0, +(camZoomState.scale * 1.25).toFixed(2));
    updateCamProofTransform();
}

function camProofZoomOut() {
    camZoomState.scale = Math.max(0.25, +(camZoomState.scale / 1.25).toFixed(2));
    if (camZoomState.scale <= 1.0) {
        camZoomState.panX = 0;
        camZoomState.panY = 0;
    }
    updateCamProofTransform();
}

function camProofZoomReset() {
    camZoomState.scale = 1.0;
    camZoomState.panX = 0;
    camZoomState.panY = 0;
    camZoomState.rotation = 0;
    updateCamProofTransform();
}

function camProofZoom100() {
    camZoomState.scale = 1.0;
    camZoomState.panX = 0;
    camZoomState.panY = 0;
    updateCamProofTransform();
}

function camProofRotate() {
    camZoomState.rotation = (camZoomState.rotation + 90) % 360;
    updateCamProofTransform();
}

function initCamProofZoomEvents() {
    if (camZoomState.eventsBound) return;
    const container = document.getElementById('camProofCanvasContainer');
    const img = document.getElementById('camProofModalImgHik');
    if (!container || !img) return;

    camZoomState.eventsBound = true;

    // Mouse wheel zoom
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        const zoomDelta = e.deltaY < 0 ? 1.15 : 0.85;
        const newScale = Math.min(6.0, Math.max(0.25, +(camZoomState.scale * zoomDelta).toFixed(2)));
        camZoomState.scale = newScale;
        if (newScale <= 1.0) {
            camZoomState.panX = 0;
            camZoomState.panY = 0;
        }
        updateCamProofTransform();
    }, { passive: false });

    // Drag to pan
    container.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        camZoomState.isDragging = true;
        camZoomState.startX = e.clientX - camZoomState.panX;
        camZoomState.startY = e.clientY - camZoomState.panY;
        container.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
        if (!camZoomState.isDragging) return;
        camZoomState.panX = e.clientX - camZoomState.startX;
        camZoomState.panY = e.clientY - camZoomState.startY;
        updateCamProofTransform();
    });

    window.addEventListener('mouseup', () => {
        if (camZoomState.isDragging) {
            camZoomState.isDragging = false;
            if (container) container.style.cursor = 'grab';
        }
    });

    // Double-click toggle (1.0x <-> 2.2x)
    container.addEventListener('dblclick', (e) => {
        e.preventDefault();
        if (camZoomState.scale > 1.2) {
            camProofZoomReset();
        } else {
            camZoomState.scale = 2.2;
            updateCamProofTransform();
        }
    });

    // Touch events for mobile / tablets
    let initialTouchDist = null;
    container.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
            camZoomState.isDragging = true;
            camZoomState.startX = e.touches[0].clientX - camZoomState.panX;
            camZoomState.startY = e.touches[0].clientY - camZoomState.panY;
        } else if (e.touches.length === 2) {
            initialTouchDist = Math.hypot(
                e.touches[0].clientX - e.touches[1].clientX,
                e.touches[0].clientY - e.touches[1].clientY
            );
        }
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && camZoomState.isDragging) {
            camZoomState.panX = e.touches[0].clientX - camZoomState.startX;
            camZoomState.panY = e.touches[0].clientY - camZoomState.startY;
            updateCamProofTransform();
        } else if (e.touches.length === 2 && initialTouchDist) {
            const dist = Math.hypot(
                e.touches[0].clientX - e.touches[1].clientX,
                e.touches[0].clientY - e.touches[1].clientY
            );
            const scaleFactor = dist / initialTouchDist;
            camZoomState.scale = Math.min(6.0, Math.max(0.25, +(camZoomState.scale * scaleFactor).toFixed(2)));
            initialTouchDist = dist;
            updateCamProofTransform();
        }
    }, { passive: true });

    container.addEventListener('touchend', () => {
        camZoomState.isDragging = false;
        initialTouchDist = null;
    });

    // Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
        const modal = document.getElementById('camProofModal');
        if (!modal || modal.classList.contains('hidden')) return;

        if (e.key === 'Escape') {
            closeCamProofModal();
        } else if (e.key === '+' || e.key === '=') {
            camProofZoomIn();
        } else if (e.key === '-' || e.key === '_') {
            camProofZoomOut();
        } else if (e.key === '0') {
            camProofZoomReset();
        } else if (e.key.toLowerCase() === 'r') {
            camProofRotate();
        }
    });
}

// Expose zoom functions to global window scope for inline onclicks
window.camProofZoomIn = camProofZoomIn;
window.camProofZoomOut = camProofZoomOut;
window.camProofZoomReset = camProofZoomReset;
window.camProofZoom100 = camProofZoom100;
window.camProofRotate = camProofRotate;

function openCamProofModal(itemOrHikImg, timestamp, direction, eventType) {
    const modal = document.getElementById('camProofModal');
    const hikImgEl = document.getElementById('camProofModalImgHik');
    const infoEl = document.getElementById('camProofModalInfo');
    const resEl = document.getElementById('camProofResolution');
    if (!modal) return;

    let item = {};
    if (typeof itemOrHikImg === 'object' && itemOrHikImg !== null) {
        item = itemOrHikImg;
    } else {
        item = {
            image_path: (itemOrHikImg || '').replace(/^\/+/, ''),
            timestamp: timestamp || '',
            direction: direction || 'Line Crossing',
            event_type: eventType || 'Hikvision Line Crossing'
        };
    }

    const rawPath = (item.image_path || '').replace(/^\/+/, '');
    // ALWAYS load the FULL RESOLUTION ORIGINAL image in modal
    const originalImgSrc = rawPath ? '/' + rawPath : '';

    if (resEl) {
        resEl.innerText = 'Loading Full HD Resolution...';
    }

    if (hikImgEl) {
        hikImgEl.onload = function() {
            if (resEl && hikImgEl.naturalWidth) {
                resEl.innerText = `Native HD Resolution: ${hikImgEl.naturalWidth} × ${hikImgEl.naturalHeight} px (Full Quality Original)`;
            }
        };
        hikImgEl.src = originalImgSrc || '';
        hikImgEl.onerror = () => {
            hikImgEl.src = '/static/img/no-car.svg';
            if (resEl) resEl.innerText = 'Hikvision Overview Frame';
        };
    }

    // Reset zoom and pan on opening modal
    camProofZoomReset();
    initCamProofZoomEvents();

    if (infoEl) {
        infoEl.innerHTML = `
            <div class="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <div class="flex items-center gap-2">
                        <h3 class="text-sm font-bold text-slate-800">Hikvision Camera Proof (Original Quality)</h3>
                        <span class="text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-md">${item.event_type || 'Line Crossing'}</span>
                    </div>
                    <p class="text-xs text-slate-400 font-mono mt-0.5">Recorded: ${item.timestamp || ''} PKT &bull; Direction: ${item.direction || 'Line Crossing'} &bull; File: ${rawPath.split('/').pop()}</p>
                </div>
                <div class="flex items-center gap-2">
                    ${originalImgSrc ? `<a href="${originalImgSrc}" download target="_blank" class="px-3 py-2 text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl hover:bg-emerald-100 transition shadow-2xs">
                        Download Original HD
                    </a>` : ''}
                    <button type="button" onclick="closeCamProofModal()" class="px-3.5 py-2 text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition">
                        Close
                    </button>
                </div>
            </div>
        `;
    }
    modal.classList.remove('hidden');
}

function closeCamProofModal() {
    const modal = document.getElementById('camProofModal');
    if (modal) modal.classList.add('hidden');
    camProofZoomReset();
}

let lastSeenTransitId = null;
let kioskIdleTimer = null;

function renderKioskLicensePlate(carNum) {
    const seriesEl = document.getElementById('kioskMiniPlateSeries');
    const digitsEl = document.getElementById('kioskMiniPlateDigits');
    const rawPlateEl = document.getElementById('kioskMiniPlate');

    const clean = (carNum || '').trim().toUpperCase();
    if (rawPlateEl) rawPlateEl.innerText = clean || '--';

    if (!clean || clean === '--' || clean === 'NO TAG') {
        if (seriesEl) seriesEl.innerText = '---';
        if (digitsEl) digitsEl.innerText = '---';
        return;
    }

    const parts = clean.split(/[-_\s]+/);
    if (parts.length >= 2) {
        if (seriesEl) seriesEl.innerText = parts[0];
        if (digitsEl) digitsEl.innerText = parts.slice(1).join(' ');
    } else {
        if (seriesEl) seriesEl.innerText = '';
        if (digitsEl) digitsEl.innerText = clean;
    }
}

function renderKioskElements(log) {
    if (!log || !log.id) return;

    const miniStatusBadge = document.getElementById('kioskMiniStatusBadge');
    const miniBadgeDot = document.getElementById('kioskMiniBadgeDot');
    const miniBadgeText = document.getElementById('kioskMiniBadgeText');
    const miniTime = document.getElementById('kioskMiniTime');
    const miniRegContainer = document.getElementById('kioskMiniRegContainer');
    const miniUnregContainer = document.getElementById('kioskMiniUnregContainer');
    const miniMake = document.getElementById('kioskMiniMake');
    const miniPhoto = document.getElementById('kioskMiniPhoto');
    const miniAvatar = document.getElementById('kioskMiniAvatar');
    const miniName = document.getElementById('kioskMiniName');
    const miniStatusPill = document.getElementById('kioskMiniStatusPill');
    const miniMemId = document.getElementById('kioskMiniMemId');
    const miniEpc = document.getElementById('kioskMiniEpc');
    const miniBarrier = document.getElementById('kioskMiniBarrier');
    const miniUnregTagId = document.getElementById('kioskMiniUnregTagId');

    const statusUpper = (log.member_status || log.access_type || '').toUpperCase();
    const isEntry = log.direction === 'Entry';
    const isSuspended = statusUpper.includes('SUSPEND') || statusUpper.includes('BARRED') || statusUpper.includes('ALERT');
    const isVip = statusUpper.includes('VIP') || statusUpper.includes('COMMITTEE');
    const isUnreg = statusUpper.includes('UNKNOWN') || statusUpper.includes('UNREGISTERED') ||
                    (log.mem_id || '').includes('UNREGISTERED') || (log.mem_id || '').includes('GUEST');

    if (miniTime && log.timestamp) {
        miniTime.innerText = log.timestamp.substring(11, 19) + ' PKT';
    }

    if (isUnreg) {
        if (miniRegContainer) miniRegContainer.classList.add('hidden');
        if (miniUnregContainer) miniUnregContainer.classList.remove('hidden');
        if (miniUnregTagId) miniUnregTagId.innerText = log.scanned_tag || 'NO TAG DETECTED';

        if (miniStatusBadge) {
            miniStatusBadge.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-[10px] font-black uppercase tracking-wider bg-rose-50 text-rose-800 border-2 border-rose-300 shadow-2xs';
        }
        if (miniBadgeDot) miniBadgeDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
        if (miniBadgeText) miniBadgeText.innerText = `UNREGISTERED VEHICLE • ${log.direction ? log.direction.toUpperCase() : 'ENTRY'} HELD`;
    } else {
        if (miniRegContainer) miniRegContainer.classList.remove('hidden');
        if (miniUnregContainer) miniUnregContainer.classList.add('hidden');

        renderKioskLicensePlate(log.vehicle_number);

        if (miniStatusBadge) {
            if (isSuspended) {
                miniStatusBadge.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-[10px] font-black uppercase tracking-wider bg-rose-50 text-rose-800 border-2 border-rose-300 shadow-2xs';
                if (miniBadgeText) miniBadgeText.innerText = 'SECURITY ALERT • ACCESS DENIED';
                if (miniBadgeDot) miniBadgeDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
            } else if (isEntry) {
                miniStatusBadge.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-[10px] font-black uppercase tracking-wider bg-emerald-50 text-emerald-800 border-2 border-emerald-300 shadow-2xs';
                if (miniBadgeText) miniBadgeText.innerText = 'CLEARANCE GRANTED • ENTRY';
                if (miniBadgeDot) miniBadgeDot.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-ping';
            } else {
                miniStatusBadge.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-[10px] font-black uppercase tracking-wider bg-blue-50 text-blue-800 border-2 border-blue-300 shadow-2xs';
                if (miniBadgeText) miniBadgeText.innerText = 'CLEARANCE GRANTED • EXIT RECORDED';
                if (miniBadgeDot) miniBadgeDot.className = 'w-2 h-2 rounded-full bg-blue-500 animate-ping';
            }
        }

        if (miniMake) {
            miniMake.innerText = log.make_model || (log.vehicle_number ? 'Verified Vehicle' : 'Vehicle Make Not Detected');
        }

        if (miniPhoto && miniAvatar) {
            if (log.profile_pic) {
                miniPhoto.src = '/' + log.profile_pic.replace(/\\/g, '/');
                miniPhoto.classList.remove('hidden');
                miniAvatar.classList.add('hidden');
            } else {
                miniPhoto.classList.add('hidden');
                miniAvatar.classList.remove('hidden');
                miniAvatar.innerText = (log.name || 'KG').substring(0, 2).toUpperCase();
            }
        }

        if (miniName) miniName.innerText = log.name || 'Visitor / Guest';
        if (miniMemId) miniMemId.innerText = log.mem_id || 'KG-MEM';
        if (miniEpc) miniEpc.innerText = log.scanned_tag || 'EPC DETECTED';

        if (miniStatusPill) {
            if (isVip) {
                miniStatusPill.className = 'text-[8px] font-black px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 border border-amber-300';
                miniStatusPill.innerText = 'VIP COMMITTEE';
            } else if (isSuspended) {
                miniStatusPill.className = 'text-[8px] font-black px-1.5 py-0.2 rounded bg-rose-100 text-rose-800 border border-rose-300';
                miniStatusPill.innerText = 'SUSPENDED';
            } else {
                miniStatusPill.className = 'text-[8px] font-black px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800 border border-emerald-200';
                miniStatusPill.innerText = 'ACTIVE MEMBER';
            }
        }

        if (miniBarrier) {
            if (isSuspended) {
                miniBarrier.className = 'font-extrabold text-rose-600 flex items-center gap-1';
                miniBarrier.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>LOCKED / ALERT';
            } else {
                miniBarrier.className = 'font-extrabold text-emerald-600 flex items-center gap-1';
                miniBarrier.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>RAISED / OPEN';
            }
        }
    }
}

async function loadGateFeed() {
    try {
        const res = await fetch('/api/latest-log');
        if (!res.ok) return;
        const log = await res.json();

        const miniActive = document.getElementById('kioskMiniActive');
        const miniIdle = document.getElementById('kioskMiniIdle');

        // Legacy Feed elements (if present elsewhere)
        const dirBadge = document.getElementById('feedDirectionBadge');
        const vehImg = document.getElementById('feedVehicleImg');
        const placeholder = document.getElementById('feedPlaceholder');
        const timeOverlay = document.getElementById('feedTimeOverlay');
        const memPic = document.getElementById('feedMemberPic');
        const avatarFallback = document.getElementById('feedAvatarFallback');
        const memName = document.getElementById('feedMemberName');
        const vehNum = document.getElementById('feedVehicleNumber');
        const memId = document.getElementById('feedMemId');
        const statusPill = document.getElementById('feedStatusPill');

        if (!log || !log.id) {
            if (miniActive) miniActive.classList.add('hidden');
            if (miniIdle) miniIdle.classList.remove('hidden');
            return;
        }

        const isFirstLoad = (lastSeenTransitId === null);
        const isNewTransit = (lastSeenTransitId !== null && lastSeenTransitId !== log.id);
        lastSeenTransitId = log.id;

        // Render data into Kiosk elements
        renderKioskElements(log);

        if (isNewTransit) {
            // New scan received live: show Trigger view, then reset after 8 seconds (exact kiosk mirror)
            if (miniActive) miniActive.classList.remove('hidden');
            if (miniIdle) miniIdle.classList.add('hidden');

            clearTimeout(kioskIdleTimer);
            kioskIdleTimer = setTimeout(() => {
                if (miniActive) miniActive.classList.add('hidden');
                if (miniIdle) miniIdle.classList.remove('hidden');
            }, 8000);
        } else if (isFirstLoad) {
            // On initial page load: check if the transit is fresh (< 8s old)
            let isRecent = false;
            if (log.timestamp) {
                try {
                    const logDate = new Date(log.timestamp.replace(' ', 'T'));
                    const now = new Date();
                    const ageSec = (now.getTime() - logDate.getTime()) / 1000;
                    if (ageSec >= 0 && ageSec <= 8) isRecent = true;
                } catch (e) {}
            }
            if (isRecent) {
                if (miniActive) miniActive.classList.remove('hidden');
                if (miniIdle) miniIdle.classList.add('hidden');
                kioskIdleTimer = setTimeout(() => {
                    if (miniActive) miniActive.classList.add('hidden');
                    if (miniIdle) miniIdle.classList.remove('hidden');
                }, 8000);
            } else {
                // Normal standby state: show the authentic Idle Radar display
                if (miniActive) miniActive.classList.add('hidden');
                if (miniIdle) miniIdle.classList.remove('hidden');
            }
        }

        // Backward-compatible update for legacy feed elements if present
        const isEntry = log.direction === 'Entry';
        const statusUpper = (log.member_status || log.access_type || '').toUpperCase();
        const isVip = statusUpper.includes('VIP') || statusUpper.includes('COMMITTEE');
        const isSuspended = statusUpper.includes('SUSPEND') || statusUpper.includes('BARRED') || statusUpper.includes('ALERT');
        const isUnreg = statusUpper.includes('UNKNOWN') || statusUpper.includes('UNREGISTERED');

        if (dirBadge) {
            dirBadge.className = `text-[10px] font-black uppercase tracking-wider px-2.5 py-1 rounded-full ${isEntry ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-blue-100 text-blue-800 border border-blue-200'}`;
            dirBadge.innerText = `${(log.direction || 'Transit').toUpperCase()} ACTIVE`;
        }

        const imgPath = log.image_path || log.plate_image_path;
        if (imgPath && vehImg) {
            vehImg.src = '/' + imgPath;
            vehImg.classList.remove('hidden');
            if (placeholder) placeholder.classList.add('hidden');
        } else if (vehImg && !vehImg.src) {
            vehImg.classList.add('hidden');
            if (placeholder) placeholder.classList.remove('hidden');
        }

        if (timeOverlay && log.timestamp) {
            timeOverlay.innerText = log.timestamp.substring(11, 19) + ' PKT';
            timeOverlay.classList.remove('hidden');
        }

        if (memPic && avatarFallback) {
            if (log.profile_pic) {
                memPic.src = '/' + log.profile_pic;
                memPic.classList.remove('hidden');
                avatarFallback.classList.add('hidden');
            } else {
                memPic.classList.add('hidden');
                avatarFallback.classList.remove('hidden');
                avatarFallback.innerText = (log.name || 'KG').substring(0, 2).toUpperCase();
            }
        }

        if (memName) memName.innerText = log.name || 'Visitor';
        if (vehNum) vehNum.innerText = log.vehicle_number || '--';
        if (memId) memId.innerText = `${log.mem_id || 'GUEST'} • ${log.gate_no || 'Gate-01'}`;

        if (statusPill) {
            statusPill.classList.remove('hidden');
            if (isVip) {
                statusPill.className = 'text-[9px] font-black px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300';
                statusPill.innerText = 'VIP COMMITTEE';
            } else if (isSuspended) {
                statusPill.className = 'text-[9px] font-black px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 border border-rose-300';
                statusPill.innerText = 'SECURITY ALERT';
            } else if (isUnreg) {
                statusPill.className = 'text-[9px] font-black px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200';
                statusPill.innerText = 'UNREGISTERED';
            } else {
                statusPill.className = 'text-[9px] font-black px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200';
                statusPill.innerText = 'RFID VERIFIED';
            }
        }

        // Trigger toast alerts for new VIP / Suspended arrivals
        if (isNewTransit) {
            if (isVip) {
                showToast('vip', `VIP Transit: ${log.name}`, `${log.vehicle_number || ''} (${log.mem_id || ''})`);
            } else if (isSuspended) {
                showToast('security', `Security Alert: ${log.name}`, `Flagged Vehicle: ${log.vehicle_number || ''} (${log.mem_id || ''})`);
            }
        }
        lastSeenTransitId = log.id;
    } catch (err) {
        console.error('loadGateFeed error:', err);
    }
}

function showToast(type, title, message) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    const isVip = type === 'vip';
    toast.className = `transform transition-all duration-300 ease-out translate-y-2 opacity-0 flex items-start gap-3 p-4 rounded-2xl shadow-xl border ${
        isVip 
        ? 'bg-amber-50/95 border-amber-300 text-amber-900' 
        : 'bg-rose-50/95 border-rose-300 text-rose-900'
    } backdrop-blur-md max-w-sm pointer-events-auto`;

    toast.innerHTML = `
        <div class="w-8 h-8 rounded-xl ${isVip ? 'bg-amber-200 text-amber-900' : 'bg-rose-200 text-rose-900'} flex items-center justify-center font-black text-xs shrink-0">
            ${isVip ? 'VIP' : '!'}
        </div>
        <div class="flex-1 min-w-0">
            <h5 class="text-xs font-black truncate">${title}</h5>
            <p class="text-[11px] opacity-80 mt-0.5 truncate">${message}</p>
        </div>
        <button type="button" onclick="this.parentElement.remove()" class="text-slate-400 hover:text-slate-600 font-bold text-sm ml-1">&times;</button>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
    });

    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 350);
    }, 6000);
}

function exportAuditData(format) {
    const startD = document.getElementById('auditDate')?.value || '';
    const endD = document.getElementById('auditEndDate')?.value || '';
    const cam = document.getElementById('auditCamera')?.value || 'all';
    const q = (document.getElementById('auditSearch') || {}).value || '';
    const dateParam = (currentAuditDatePreset === 'all' && !startD) ? 'all' : startD;
    const url = `/api/audit/export?date=${encodeURIComponent(dateParam)}&start_date=${encodeURIComponent(startD)}&end_date=${encodeURIComponent(endD)}&camera=${encodeURIComponent(cam)}&format=${format}&search=${encodeURIComponent(q)}&status=${currentAuditStatus}`;
    window.location.href = url;
}

function setupGlobalSearch() {
    const input = document.getElementById('globalSearchInput');
    const resultsBox = document.getElementById('globalSearchResults');
    if (!input || !resultsBox) return;

    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            input.focus();
            input.select();
        } else if (e.key === 'Escape') {
            resultsBox.classList.add('hidden');
        }
    });

    input.addEventListener('focus', () => {
        if (input.value.trim().length >= 2) resultsBox.classList.remove('hidden');
    });

    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !resultsBox.contains(e.target)) {
            resultsBox.classList.add('hidden');
        }
    });

    input.addEventListener('input', () => {
        clearTimeout(quickSearchTimer);
        const q = input.value.trim();
        if (q.length < 2) {
            resultsBox.classList.add('hidden');
            resultsBox.innerHTML = '';
            return;
        }

        quickSearchTimer = setTimeout(async () => {
            try {
                const res = await fetch(`/api/quick-search?q=${encodeURIComponent(q)}`);
                if (!res.ok) return;
                const data = await res.json();
                renderQuickSearchResults(data.results || [], q);
            } catch (err) {
                console.error('Quick search error:', err);
            }
        }, 200);
    });
}

function renderQuickSearchResults(results, query) {
    const box = document.getElementById('globalSearchResults');
    if (!box) return;

    if (!results.length) {
        box.innerHTML = `<div class="p-4 text-center text-xs text-slate-400 font-semibold">No members, vehicles, or tags matching "${query}"</div>`;
        box.classList.remove('hidden');
        return;
    }

    box.innerHTML = `
        <div class="p-2.5 border-b border-slate-100 text-[10px] uppercase font-black tracking-widest text-slate-400 px-3.5 bg-slate-50">
            Search Matches (${results.length})
        </div>
        <div class="max-h-80 overflow-y-auto divide-y divide-slate-100">
            ${results.map(r => `
                <div class="p-3 hover:bg-slate-50 transition cursor-pointer flex items-center justify-between gap-3" onclick="selectQuickSearchMember('${r.mem_id}')">
                    <div class="flex items-center gap-3 min-w-0">
                        ${r.profile_pic ? 
                            `<img src="/${r.profile_pic}" class="w-10 h-10 rounded-xl object-cover border border-slate-200 shrink-0" />` :
                            `<div class="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-700 font-black text-xs flex items-center justify-center shrink-0">${r.name.substring(0, 2).toUpperCase()}</div>`
                        }
                        <div class="min-w-0">
                            <div class="flex items-center gap-2">
                                <h5 class="text-xs font-black text-slate-800 truncate">${r.name}</h5>
                                <span class="text-[9px] font-bold px-1.5 py-0.5 rounded-full ${r.status === 'VIP' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">${r.status}</span>
                                <span class="text-[9px] font-black px-1.5 py-0.5 rounded-full ${r.current_location === 'Inside' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-600'}">${r.current_location === 'Inside' ? 'Inside Club' : 'Outside'}</span>
                            </div>
                            <p class="text-[11px] font-mono text-indigo-600 font-bold mt-0.5">${r.primary_car} ${r.primary_model ? '&bull; ' + r.primary_model : ''}</p>
                            <p class="text-[10px] text-slate-400 font-mono">${r.mem_id} &bull; ${r.vehicle_count} vehicle(s)</p>
                        </div>
                    </div>
                    <div class="text-right shrink-0">
                        <span class="text-[10px] font-bold text-slate-500 bg-white border border-slate-200 px-2.5 py-1 rounded-lg hover:border-indigo-400">View Fleet &rarr;</span>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    box.classList.remove('hidden');
}

function selectQuickSearchMember(memId) {
    const box = document.getElementById('globalSearchResults');
    if (box) box.classList.add('hidden');
    openMemberFleetModal(memId);
}

// ==========================================
// E-TAG ACTIVITY AUDIT STUDIO
// ==========================================
let currentAuditedTag = null;
let currentAuditedTagData = null;

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    const bg = type === 'success' ? 'bg-emerald-600' : (type === 'error' ? 'bg-rose-600' : 'bg-slate-900');
    toast.className = `${bg} text-white px-4 py-2.5 rounded-2xl shadow-xl text-xs font-bold flex items-center gap-2 transform transition-all duration-300 translate-y-2 opacity-0 pointer-events-auto`;
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
    });
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

async function loadRecentEtagTags() {
    const pillsContainer = document.getElementById('etagRecentPills');
    const welcomeTable = document.getElementById('etagWelcomeTableBody');
    if (!pillsContainer && !welcomeTable) return;

    try {
        const res = await fetch('/api/etag/recent-tags?limit=15');
        if (!res.ok) throw new Error('Failed to load recent tags');
        const data = await res.json();
        const tags = data.tags || [];

        if (pillsContainer) {
            if (tags.length === 0) {
                pillsContainer.innerHTML = '<span class="text-slate-500 italic text-[11px]">No RFID tag scans recorded yet.</span>';
            } else {
                pillsContainer.innerHTML = tags.slice(0, 7).map(t => {
                    const tagShort = t.scanned_tag.length > 16 ? t.scanned_tag.substring(0, 8) + '...' + t.scanned_tag.slice(-6) : t.scanned_tag;
                    return `
                        <button type="button" onclick="auditEtag('${t.scanned_tag}')" 
                                class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-indigo-900/60 border border-slate-700/80 text-[11px] font-mono text-indigo-300 hover:text-white transition group shadow-2xs"
                                title="${t.scanned_tag} • ${t.name || 'Visitor'} • ${t.total_scans} scans">
                            <span class="w-1.5 h-1.5 rounded-full ${t.mem_id && t.mem_id !== 'GUEST-LOG' ? 'bg-emerald-400' : 'bg-amber-400'}"></span>
                            <span class="font-bold">${tagShort}</span>
                            <span class="text-[9px] px-1 rounded bg-slate-700/60 text-slate-400 font-sans font-bold">${t.total_scans}</span>
                        </button>
                    `;
                }).join('');
            }
        }

        if (welcomeTable) {
            if (tags.length === 0) {
                welcomeTable.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-slate-400 text-xs">No RFID tag scan records found in the database.</td></tr>';
            } else {
                welcomeTable.innerHTML = tags.map((t, idx) => {
                    const isMem = Boolean(t.mem_id && t.mem_id !== 'GUEST-LOG' && t.mem_id !== 'UNREGISTERED');
                    return `
                        <tr class="hover:bg-slate-50/80 transition cursor-pointer" onclick="auditEtag('${t.scanned_tag}')">
                            <td class="py-3 px-4 font-mono font-bold text-xs text-indigo-700">
                                <div class="flex items-center gap-2">
                                    <span class="w-2 h-2 rounded-full ${isMem ? 'bg-emerald-500' : 'bg-amber-500'} shrink-0"></span>
                                    <span class="truncate max-w-[220px] select-all">${t.scanned_tag}</span>
                                </div>
                            </td>
                            <td class="py-3 px-4">
                                <p class="font-extrabold text-slate-800">${t.name || 'Unregistered Visitor'}</p>
                                <p class="text-[10px] text-slate-400 font-mono">${t.mem_id || 'Visitor Tag'} &bull; ${isMem ? '<span class="text-emerald-700 font-bold">Member</span>' : '<span class="text-amber-700 font-bold">Unregistered</span>'}</p>
                            </td>
                            <td class="py-3 px-4 font-mono font-bold text-slate-700">${t.vehicle_number || 'NO PLATE'}</td>
                            <td class="py-3 px-4 font-bold font-mono text-slate-800"><span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">${t.total_scans} scans</span></td>
                            <td class="py-3 px-4 font-mono text-slate-500 text-[11px]">${t.last_seen || '--'}</td>
                            <td class="py-3 px-4 text-right pr-4">
                                <button type="button" onclick="event.stopPropagation(); auditEtag('${t.scanned_tag}')" class="px-3 py-1 rounded-xl text-xs font-bold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 shadow-2xs transition">
                                    Audit &rarr;
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }
    } catch (err) {
        console.error('Error loading recent tags:', err);
    }
}

function onEtagSearchSubmit(e) {
    if (e) e.preventDefault();
    const input = document.getElementById('etagSearchInput');
    const val = input ? input.value.trim() : '';
    if (!val) {
        alert('Please enter or paste an RFID EPC Tag ID');
        return;
    }
    loadEtagAudit(val);
}

function auditEtag(tagId) {
    if (!tagId) return;
    switchTab('etag_audit');
    loadEtagAudit(tagId);
}

async function loadEtagAudit(tagId, isSilent = false) {
    const cleanTag = (tagId || '').trim();
    if (!cleanTag) return;
    currentAuditedTag = cleanTag;

    const input = document.getElementById('etagSearchInput');
    if (input) input.value = cleanTag;

    const btn = document.getElementById('btnRunEtagAudit');
    let origBtnText = '';
    if (btn && !isSilent) {
        origBtnText = btn.innerHTML;
        btn.innerHTML = `<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>Auditing...</span>`;
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/etag/audit?tag_id=${encodeURIComponent(cleanTag)}`);
        if (!res.ok) {
            const errJson = await res.json().catch(() => ({}));
            throw new Error(errJson.detail || `Server error (${res.status})`);
        }
        const data = await res.json();
        currentAuditedTagData = data;

        // Show Active Dossier Container
        const welcomeState = document.getElementById('etagAuditWelcomeState');
        const activeContainer = document.getElementById('etagActiveAuditContainer');
        if (welcomeState) welcomeState.classList.add('hidden');
        if (activeContainer) activeContainer.classList.remove('hidden');

        renderEtagDossier(data);
        renderEtagMetrics(data);
        renderEtagDailyBreakdown(data);
        renderEtagChronology(data);

        // Update URL query
        try {
            const url = new URL(window.location.href);
            url.searchParams.set('tab', 'etag_audit');
            url.searchParams.set('tag', cleanTag);
            window.history.replaceState({ tab: 'etag_audit', tag: cleanTag }, '', url.toString());
        } catch (e) {}

    } catch (err) {
        alert(`Failed to load E-TAG audit: ${err.message}`);
    } finally {
        if (btn && !isSilent) {
            btn.innerHTML = origBtnText;
            btn.disabled = false;
        }
    }
}

function renderEtagDossier(data) {
    const card = document.getElementById('etagDossierCard');
    if (!card) return;

    const m = data.member || {};
    const isReg = Boolean(data.is_registered);
    const tag = data.tag_id;

    card.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
            <!-- Col 1: Member / Driver Profile -->
            <div class="md:col-span-5 flex items-center gap-5 border-b md:border-b-0 md:border-r border-slate-200 pb-5 md:pb-0 md:pr-6">
                ${m.profile_pic ? 
                    `<img src="/${m.profile_pic.replace(/^\//, '')}" class="w-20 h-20 rounded-2xl object-cover border-2 border-slate-200 shadow-md">` :
                    `<div class="w-20 h-20 rounded-2xl ${isReg ? 'bg-indigo-100 text-indigo-700' : 'bg-amber-100 text-amber-700'} font-black text-3xl flex items-center justify-center border-2 border-slate-200 shadow-xs">${(m.name || '?').charAt(0)}</div>`
                }
                <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                        <span class="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full ${isReg ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}">
                            ${isReg ? 'RFID Verified Member' : 'Unregistered RFID Tag'}
                        </span>
                        <span class="text-[10px] font-mono font-bold text-slate-400">ID: ${m.mem_id || 'N/A'}</span>
                    </div>
                    <h3 class="text-xl font-black text-slate-900 truncate">${m.name || 'Unregistered Tag'}</h3>
                    <p class="text-xs text-slate-500 font-medium mt-0.5">${m.phone ? `Phone: ${m.phone} &bull; ` : ''}${m.status || 'Active'}</p>
                </div>
            </div>

            <!-- Col 2: Vehicle Particulars -->
            <div class="md:col-span-4 border-b md:border-b-0 md:border-r border-slate-200 pb-5 md:pb-0 md:pr-6">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-2">Registered Vehicle Particulars</p>
                <div class="inline-block px-4 py-1.5 bg-slate-100 border border-slate-300 rounded-xl shadow-2xs font-mono font-black text-xl text-slate-900 tracking-wider">
                    ${m.vehicle_number || 'NO PLATE'}
                </div>
                <p class="text-xs font-bold text-slate-700 mt-2">${m.make_model || 'Make/Model not specified'}</p>
                <p class="text-[11px] text-slate-400 mt-0.5">Automated Gate UHF Sentry Verification</p>
            </div>

            <!-- Col 3: Tag Identification & Quick Actions -->
            <div class="md:col-span-3 space-y-3">
                <div>
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-[10px] font-black uppercase tracking-wider text-slate-400">Audited EPC Identifier</span>
                        <button type="button" onclick="copyEtagId('${tag}')" class="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 transition flex items-center gap-1">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 022z"></path></svg>
                            <span>Copy</span>
                        </button>
                    </div>
                    <div class="p-2.5 rounded-xl bg-slate-900 text-emerald-400 font-mono font-bold text-xs select-all truncate border border-slate-800 shadow-inner">
                        ${tag}
                    </div>
                </div>

                ${!isReg ? `
                    <button type="button" onclick="assignTagToMember('${tag}')" class="w-full py-2 px-3 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 font-bold text-xs transition flex items-center justify-center gap-1.5 shadow-2xs">
                        <svg class="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path></svg>
                        <span>Bind Tag to Member Record</span>
                    </button>
                ` : `
                    <div class="flex items-center gap-1.5 text-xs text-emerald-700 font-bold bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-xl">
                        <svg class="w-4 h-4 text-emerald-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        <span>Active RFID Credential Validated</span>
                    </div>
                `}
            </div>
        </div>
    `;
}

function renderEtagMetrics(data) {
    const grid = document.getElementById('etagMetricsGrid');
    if (!grid) return;

    const s = data.summary || {};
    const firstStr = s.first_detected ? String(s.first_detected).substring(0, 16) : '--';
    const lastStr = s.latest_detected ? String(s.latest_detected).substring(0, 16) : '--';

    grid.innerHTML = `
        <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-indigo-600">
            <p class="text-[10px] font-black uppercase tracking-wider text-slate-400">Total Scans</p>
            <h4 class="text-2xl font-black text-indigo-700 mt-1">${s.total_detections || 0}</h4>
            <p class="text-[11px] text-slate-400 font-medium mt-0.5">All-time detections</p>
        </div>

        <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-emerald-600">
            <p class="text-[10px] font-black uppercase tracking-wider text-slate-400">Active Days</p>
            <h4 class="text-2xl font-black text-emerald-700 mt-1">${s.days_active || 0}</h4>
            <p class="text-[11px] text-slate-400 font-medium mt-0.5">Distinct facility dates</p>
        </div>

        <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-blue-600">
            <p class="text-[10px] font-black uppercase tracking-wider text-slate-400">Primary Reader</p>
            <h4 class="text-2xl font-black text-slate-900 mt-1 truncate">${s.most_active_reader || 'Gate-01'}</h4>
            <p class="text-[11px] text-slate-400 font-medium mt-0.5">Most frequent station</p>
        </div>

        <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-slate-400">
            <p class="text-[10px] font-black uppercase tracking-wider text-slate-400">First Detection</p>
            <h4 class="text-sm font-black font-mono text-slate-800 mt-1.5 truncate">${firstStr}</h4>
            <p class="text-[11px] text-slate-400 font-medium mt-0.5">Earliest recorded scan</p>
        </div>

        <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-amber-500">
            <p class="text-[10px] font-black uppercase tracking-wider text-slate-400">Latest Detection</p>
            <h4 class="text-sm font-black font-mono text-slate-800 mt-1.5 truncate">${lastStr}</h4>
            <p class="text-[11px] text-slate-400 font-medium mt-0.5">Most recent transit</p>
        </div>
    `;
}

function renderEtagDailyBreakdown(data) {
    const tbody = document.getElementById('etagDailyBreakdownBody');
    const badge = document.getElementById('etagDailyCountBadge');
    if (!tbody) return;

    const days = data.daily_breakdown || [];
    if (badge) badge.innerText = `${days.length} Active Days Recorded`;

    if (days.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-400 text-xs">No daily movement breakdown available for this tag.</td></tr>`;
        return;
    }

    tbody.innerHTML = days.map((d, idx) => {
        const readersList = Object.entries(d.readers || {}).map(([r, c]) => `<span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-bold font-mono text-[10px]">${r} (${c})</span>`).join(' ');
        return `
            <tr class="hover:bg-slate-50/70 transition">
                <td class="py-3 px-4 font-mono font-bold text-xs text-slate-900">
                    <span class="inline-flex items-center gap-1.5">
                        <span class="w-2 h-2 rounded-full bg-indigo-600"></span>
                        <span>${d.date}</span>
                    </span>
                </td>
                <td class="py-3 px-4">
                    <span class="text-xs font-black px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 font-mono">
                        ${d.total_detections} Detections
                    </span>
                </td>
                <td class="py-3 px-4 text-xs font-medium text-slate-700">
                    <span class="text-emerald-700 font-bold">${d.entries} IN</span> &bull; <span class="text-blue-700 font-bold">${d.exits} OUT</span>
                    ${d.visits_count ? `<span class="text-slate-400 text-[11px] ml-1">(${d.visits_count} visits)</span>` : ''}
                </td>
                <td class="py-3 px-4 font-mono font-bold text-xs text-slate-800">
                    ${d.first_scan_time} &rarr; ${d.last_scan_time}
                </td>
                <td class="py-3 px-4 font-mono font-black text-xs text-indigo-700">
                    ${d.stay_duration && d.stay_duration !== '-- --' ? `<span class="px-2 py-0.5 rounded bg-indigo-50 border border-indigo-200">${d.stay_duration}</span>` : '<span class="text-slate-300">—</span>'}
                </td>
                <td class="py-3 px-4">
                    <div class="flex items-center gap-1.5 flex-wrap">
                        ${readersList || '<span class="text-slate-400 font-mono">Gate-01</span>'}
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function renderEtagChronology(data) {
    const tbody = document.getElementById('etagChronologyBody');
    const badge = document.getElementById('etagTotalScansBadge');
    if (!tbody) return;

    const scans = data.scans || [];
    if (badge) badge.innerText = `${scans.length} Total Scans`;

    if (scans.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="py-8 text-center text-slate-400 text-xs">No scan events recorded for this tag.</td></tr>`;
        return;
    }

    tbody.innerHTML = scans.map((s, idx) => {
        const isEntry = (s.direction || '').toLowerCase() === 'entry';
        const timePart = s.timestamp || '--';
        const hasImg = Boolean(s.image_path || s.plate_image_path);
        const imgPath = s.image_path || s.plate_image_path;

        return `
            <tr class="hover:bg-slate-50/70 transition">
                <td class="py-3 px-4 font-mono font-bold text-slate-400 text-xs">${String(idx + 1).padStart(2, '0')}</td>
                <td class="py-3 px-4 font-mono font-bold text-slate-800 text-xs">${timePart}</td>
                <td class="py-3 px-4 font-bold text-slate-700 text-xs">${s.gate_no || 'Gate-01'}</td>
                <td class="py-3 px-4">
                    <span class="text-[10px] font-black px-2 py-0.5 rounded-full ${isEntry ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-blue-50 text-blue-700 border border-blue-200'}">
                        ${(s.direction || 'PASSAGE').toUpperCase()}
                    </span>
                </td>
                <td class="py-3 px-4 text-xs text-slate-600 font-medium">${s.access_type || 'UHF RFID Access'}</td>
                <td class="py-3 px-4 font-mono font-bold text-xs text-slate-800">${s.vehicle_number || 'NO PLATE'}</td>
                <td class="py-3 px-4">
                    ${hasImg ? `
                        <img src="/${imgPath.replace(/^\//, '')}" class="w-12 h-8 rounded-lg object-cover border border-slate-200 shadow-2xs cursor-pointer hover:scale-110 transition" onclick="window.open('/${imgPath.replace(/^\//, '')}')" title="Click to view optical proof">
                    ` : `<span class="text-slate-300 font-mono text-xs">—</span>`}
                </td>
                <td class="py-3 px-4 text-right pr-4">
                    <button type="button" onclick="inspectScanRecord(${s.id})" class="px-3 py-1 rounded-xl text-xs font-bold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 shadow-2xs transition">
                        Report &rarr;
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function copyEtagId(tag) {
    if (!tag) return;
    navigator.clipboard.writeText(tag).then(() => {
        showToast('E-TAG EPC copied to clipboard', 'success');
    }).catch(() => {
        prompt('Copy E-TAG ID:', tag);
    });
}

async function pasteEtagFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        if (text && text.trim()) {
            loadEtagAudit(text.trim());
        } else {
            const manual = prompt('Paste EPC Tag ID:');
            if (manual && manual.trim()) loadEtagAudit(manual.trim());
        }
    } catch (err) {
        const manual = prompt('Paste EPC Tag ID:');
        if (manual && manual.trim()) loadEtagAudit(manual.trim());
    }
}

async function captureEtagLive() {
    try {
        const res = await fetch('/api/latest-log');
        if (!res.ok) throw new Error('Could not fetch antenna status');
        const data = await res.json();
        const tag = data.scanned_tag;
        if (tag && tag !== 'NO_TAG' && tag !== '') {
            loadEtagAudit(tag);
            showToast(`Live Tag Captured: ${tag}`, 'info');
        } else {
            alert('No active tag currently detected at RFID reader antenna.');
        }
    } catch (err) {
        alert(`Failed to read antenna: ${err.message}`);
    }
}

function assignTagToMember(tag) {
    switchTab('members');
    const tagInput = document.getElementById('nTag');
    if (tagInput) {
        tagInput.value = tag;
        tagInput.focus();
        showToast(`EPC ${tag} transferred to member registration form`, 'info');
    }
}

async function inspectScanRecord(logId) {
    try {
        const res = await fetch(`/api/audit?search=${logId}&limit=1`);
        if (res.ok) {
            const data = await res.json();
            if (data.records && data.records.length > 0) {
                openAudit(data.records[0]);
                return;
            }
        }
    } catch (e) {}
    window.open(`/api/audit/${logId}/pdf`, '_blank');
}

function exportEtagAuditData(format = 'csv') {
    if (!currentAuditedTagData || !currentAuditedTagData.scans || currentAuditedTagData.scans.length === 0) {
        alert('No scan data to export.');
        return;
    }

    const scans = currentAuditedTagData.scans;
    const tag = currentAuditedTagData.tag_id;
    const mem = currentAuditedTagData.member || {};

    const headers = ['#', 'Tag_EPC', 'Member_ID', 'Member_Name', 'Vehicle_Plate', 'Gate_Station', 'Direction', 'Timestamp', 'Access_Protocol'];
    const rows = scans.map((s, idx) => [
        idx + 1,
        tag,
        mem.mem_id || '',
        `"${(mem.name || s.name || '').replace(/"/g, '""')}"`,
        `"${(mem.vehicle_number || s.vehicle_number || '').replace(/"/g, '""')}"`,
        s.gate_no || 'Gate-01',
        s.direction || '',
        s.timestamp || '',
        `"${(s.access_type || '').replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ETAG_Audit_${tag}_${new Date().toISOString().substring(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// ============================================================================
// MANUAL VEHICLE EXIT & BULK FACILITY CLEARANCE CONTROLLERS
// ============================================================================

let currentManualExitTarget = null;
let currentManualExitSelectedProof = null;
let bulkExitExceptionsCache = [];

function triggerRowManualExit(a) {
    if (!a) return;
    let e = a.entry, x = a.exit;
    if (e && x && e.timestamp && x.timestamp && String(e.timestamp) > String(x.timestamp)) {
        const tmp = e; e = x; x = tmp;
    }
    const v = e || x || {};
    openManualExitModal({
        plate: v.vehicle_number || '',
        name: v.name || '',
        memId: v.mem_id || '',
        tag: (v.scanned_tag && v.scanned_tag !== 'NO_TAG') ? v.scanned_tag : '',
        entryTime: (e && e.timestamp) || v.timestamp || '',
        logId: (e && e.id) || v.id || null
    });
}

function openManualExitFromAuditModal() {
    if (!currentReportIncident) return;
    let e = currentReportIncident.entry, x = currentReportIncident.exit;
    if (e && x && e.timestamp && x.timestamp && String(e.timestamp) > String(x.timestamp)) {
        const tmp = e; e = x; x = tmp;
    }
    const v = e || x || {};
    openManualExitModal({
        plate: v.vehicle_number || '',
        name: v.name || '',
        memId: v.mem_id || '',
        tag: (v.scanned_tag && v.scanned_tag !== 'NO_TAG') ? v.scanned_tag : '',
        entryTime: (e && e.timestamp) || v.timestamp || '',
        logId: (e && e.id) || v.id || null
    });
}

function openManualExitModal(target) {
    currentManualExitTarget = target;
    currentManualExitSelectedProof = null;

    const modal = document.getElementById('manualExitModal');
    if (!modal) return;

    // Populate Dossier
    const initialEl = document.getElementById('manualExitInitial');
    const plateEl = document.getElementById('manualExitPlate');
    const nameEl = document.getElementById('manualExitName');
    const memEl = document.getElementById('manualExitMemId');
    const tagEl = document.getElementById('manualExitTag');
    const entryTimeEl = document.getElementById('manualExitEntryTime');

    if (initialEl) initialEl.innerText = (target.name || target.plate || 'V').charAt(0).toUpperCase();
    if (plateEl) plateEl.innerText = target.plate || 'NO PLATE';
    if (nameEl) nameEl.innerText = target.name || 'Visitor / Driver';
    if (memEl) memEl.innerText = target.memId || 'N/A';
    if (tagEl) tagEl.innerText = target.tag || 'NO TAG';
    if (entryTimeEl) entryTimeEl.innerText = target.entryTime || '--';

    // Clear proof preview
    clearManualExitSelectedProof();

    // Set Default Timestamp to 'Now' (local PKT)
    setManualExitTimestamp('now');

    // Reset notes and gate
    const notesInput = document.getElementById('manualExitNotesInput');
    if (notesInput) notesInput.value = '';
    const gateSelect = document.getElementById('manualExitGateSelect');
    if (gateSelect) gateSelect.value = 'Gate-01-Out';

    const btn = document.getElementById('btnConfirmManualExit');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>Confirm Vehicle Exit</span>`;
    }

    modal.classList.remove('hidden');

    // Load available optical captures
    const visitDate = (target.entryTime || '').substring(0, 10) || new Date().toISOString().substring(0, 10);
    loadManualExitAvailableProof(visitDate);
}

function closeManualExitModal() {
    const modal = document.getElementById('manualExitModal');
    if (modal) modal.classList.add('hidden');
    currentManualExitTarget = null;
    currentManualExitSelectedProof = null;
}

function setManualExitTimestamp(mode) {
    const input = document.getElementById('manualExitCustomDatetime');
    if (!input) return;

    const now = new Date();
    if (mode === 'now') {
        const localIso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().substring(0, 16);
        input.value = localIso;
    } else if (mode === 'entryPlus15' || mode === 'entryPlus30') {
        const offsetMin = mode === 'entryPlus15' ? 15 : 30;
        let baseDate = now;
        if (currentManualExitTarget && currentManualExitTarget.entryTime) {
            const parsed = new Date(currentManualExitTarget.entryTime.replace(' ', 'T'));
            if (!isNaN(parsed.getTime())) {
                baseDate = parsed;
            }
        }
        const targetMs = baseDate.getTime() + offsetMin * 60000;
        const offsetDate = new Date(targetMs);
        const localIso = new Date(offsetDate.getTime() - offsetDate.getTimezoneOffset() * 60000).toISOString().substring(0, 16);
        input.value = localIso;
    }
}

async function loadManualExitAvailableProof(dateStr) {
    const gallery = document.getElementById('manualExitGallery');
    const countBadge = document.getElementById('manualExitCapturesCount');
    if (!gallery) return;

    gallery.innerHTML = `<div class="col-span-full py-4 text-center text-slate-400">Loading captures for ${dateStr}...</div>`;

    try {
        const res = await fetch(`/api/audit/available-images?date=${encodeURIComponent(dateStr)}&limit=0`);
        if (!res.ok) throw new Error('Failed to fetch images');
        const data = await res.json();
        const images = data.images || [];

        if (countBadge) countBadge.innerText = `${images.length} Captures Available`;

        if (!images.length) {
            gallery.innerHTML = `<div class="col-span-full py-4 text-center text-slate-400 italic">No camera captures found for ${dateStr}. Exit can be logged without visual proof.</div>`;
            return;
        }

        gallery.innerHTML = images.map(img => {
            const timeStr = String(img.timestamp || '').substring(11, 19) || img.timestamp;
            const cleanPath = (img.image_path || '').replace(/^\//, '');
            const isExit = (img.direction || '').toLowerCase() === 'exit';
            return `
                <div class="relative group rounded-xl overflow-hidden border border-slate-200 bg-white hover:border-amber-400 hover:shadow-md cursor-pointer transition p-1"
                     onclick="selectManualExitProof('${cleanPath}', '${img.timestamp || ''}')">
                    <img src="/${cleanPath}" class="w-full h-16 object-cover rounded-lg" onerror="this.src='/static/img/no-avatar.svg'">
                    <div class="mt-1 flex items-center justify-between text-[10px] px-0.5">
                        <span class="font-mono font-bold text-slate-700">${timeStr}</span>
                        <span class="px-1 py-0.2 rounded font-black text-[9px] ${isExit ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">${img.direction || 'CAM'}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        gallery.innerHTML = `<div class="col-span-full py-4 text-center text-rose-500 font-bold">Failed to load camera captures: ${e.message}</div>`;
        if (countBadge) countBadge.innerText = `Error loading proof`;
    }
}

function selectManualExitProof(imagePath, timeStr) {
    currentManualExitSelectedProof = { image_path: imagePath, timestamp: timeStr };
    const box = document.getElementById('manualExitSelectedProofBox');
    const imgEl = document.getElementById('manualExitSelectedProofImg');
    const timeEl = document.getElementById('manualExitSelectedProofTime');

    if (box) box.classList.remove('hidden');
    if (imgEl) imgEl.src = '/' + imagePath.replace(/^\//, '');
    if (timeEl) timeEl.innerText = `${timeStr || 'Attached Image'} • Attached as Exit Evidence`;

    // Sync timestamp if capture timestamp is valid
    if (timeStr && timeStr.length >= 16) {
        const formatted = timeStr.substring(0, 16).replace(' ', 'T');
        const dtInput = document.getElementById('manualExitCustomDatetime');
        if (dtInput) dtInput.value = formatted;
    }
}

function clearManualExitSelectedProof() {
    currentManualExitSelectedProof = null;
    const box = document.getElementById('manualExitSelectedProofBox');
    if (box) box.classList.add('hidden');
}

async function submitManualExit() {
    if (!currentManualExitTarget) {
        alert('No vehicle selected for manual exit clearance.');
        return;
    }

    const btn = document.getElementById('btnConfirmManualExit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="inline-block animate-spin mr-1.5">&circlearrowright;</span> Processing Exit...`;
    }

    const dtInput = document.getElementById('manualExitCustomDatetime');
    const gateSelect = document.getElementById('manualExitGateSelect');
    const notesInput = document.getElementById('manualExitNotesInput');

    const payload = {
        vehicle_number: currentManualExitTarget.plate,
        mem_id: currentManualExitTarget.memId,
        name: currentManualExitTarget.name,
        scanned_tag: currentManualExitTarget.tag,
        log_id: currentManualExitTarget.logId,
        timestamp: dtInput ? dtInput.value : '',
        gate_no: gateSelect ? gateSelect.value : 'Gate-01-Out',
        image_path: currentManualExitSelectedProof ? currentManualExitSelectedProof.image_path : '',
        notes: notesInput ? notesInput.value.trim() : ''
    };

    try {
        const res = await fetch('/api/audit/manual-exit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            throw new Error(data.detail || data.message || 'Server rejected manual exit.');
        }

        alert(`Success: ${data.message || 'Vehicle successfully exited.'}`);
        closeManualExitModal();
        if (typeof closeAudit === 'function') closeAudit();
        if (typeof loadAudit === 'function') loadAudit(currentAuditPage);
        if (typeof loadStats === 'function') loadStats();
        if (typeof loadBulkExitSettings === 'function') loadBulkExitSettings();
    } catch (err) {
        alert(`Error executing manual exit: ${err.message}`);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>Confirm Vehicle Exit</span>`;
        }
    }
}

// ----------------------------------------------------------------------------
// BULK FACILITY EXIT & EXCEPTION WHITELIST CONTROLLER
// ----------------------------------------------------------------------------

async function loadBulkExitSettings() {
    const insideEl = document.getElementById('bulkInsideCount');
    const exemptEl = document.getElementById('bulkExceptionCount');
    const clearEl = document.getElementById('bulkClearableCount');
    const badgeEl = document.getElementById('whitelistItemCountBadge');
    const container = document.getElementById('bulkExceptionsContainer');
    const dtInput = document.getElementById('bulkExitDatetimeInput');

    if (dtInput && !dtInput.value) {
        setBulkExitNow();
    }

    try {
        const res = await fetch('/api/settings/bulk-exit-exceptions');
        if (!res.ok) return;
        const data = await res.json();

        bulkExitExceptionsCache = data.exceptions || [];

        if (insideEl) insideEl.innerText = (data.total_inside || 0).toLocaleString();
        if (exemptEl) exemptEl.innerText = (data.exempt_inside_count || 0).toLocaleString();
        if (clearEl) clearEl.innerText = (data.clearable_count || 0).toLocaleString();
        if (badgeEl) badgeEl.innerText = `${bulkExitExceptionsCache.length} Cars Protected`;

        if (container) {
            if (!bulkExitExceptionsCache.length) {
                container.innerHTML = `<span class="text-xs text-slate-400 italic">No vehicles currently on the stay-inside exception list.</span>`;
            } else {
                container.innerHTML = bulkExitExceptionsCache.map(item => `
                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl bg-white border border-slate-300 font-mono font-bold text-xs text-slate-800 shadow-2xs">
                        <span>${item}</span>
                        <button type="button" onclick="removeBulkExitException('${item}')" class="text-slate-400 hover:text-rose-600 font-extrabold text-sm leading-none ml-1 transition" title="Remove from Whitelist">&times;</button>
                    </span>
                `).join('');
            }
        }
    } catch (e) {
        console.error('loadBulkExitSettings error:', e);
    }
}

function setBulkExitNow() {
    const input = document.getElementById('bulkExitDatetimeInput');
    if (!input) return;
    const now = new Date();
    const localIso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().substring(0, 16);
    input.value = localIso;
}

async function addBulkExitException() {
    const input = document.getElementById('inputNewExceptionPlate');
    if (!input) return;
    const val = input.value.trim().toUpperCase();
    if (!val) return;

    if (bulkExitExceptionsCache.includes(val)) {
        alert(`"${val}" is already on the exception whitelist.`);
        input.value = '';
        return;
    }

    const updated = [...bulkExitExceptionsCache, val];
    try {
        const res = await fetch('/api/settings/bulk-exit-exceptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exceptions: updated })
        });
        if (!res.ok) throw new Error('Failed to save exception');
        input.value = '';
        await loadBulkExitSettings();
    } catch (e) {
        alert(`Failed to add exception: ${e.message}`);
    }
}

async function removeBulkExitException(val) {
    const updated = bulkExitExceptionsCache.filter(x => x !== val);
    try {
        const res = await fetch('/api/settings/bulk-exit-exceptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exceptions: updated })
        });
        if (!res.ok) throw new Error('Failed to update whitelist');
        await loadBulkExitSettings();
    } catch (e) {
        alert(`Failed to remove exception: ${e.message}`);
    }
}

async function executeBulkExit() {
    const btn = document.getElementById('btnExecuteBulkExit');
    const notice = document.getElementById('bulkExitStatusNotice');
    const dtInput = document.getElementById('bulkExitDatetimeInput');

    const exemptCount = bulkExitExceptionsCache.length;
    const confirmMsg = `Are you sure you want to mark all vehicles inside the club as EXITED?\n\n` +
        `• All non-whitelisted cars will receive an Exit record and status changed to Outside.\n` +
        `• ${exemptCount} whitelisted vehicle(s) will be strictly preserved and stay INSIDE.\n\n` +
        `Proceed with bulk exit?`;

    if (!confirm(confirmMsg)) return;

    if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-75');
    }
    if (notice) {
        notice.className = 'text-xs font-bold text-amber-600 animate-pulse';
        notice.innerText = 'Clearing facility vehicles...';
    }

    try {
        const res = await fetch('/api/audit/bulk-manual-exit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp: dtInput ? dtInput.value : '',
                gate_no: 'Gate-01-Out (Bulk Clearance)',
                notes: 'Bulk Facility Override',
                exempt_identifiers: bulkExitExceptionsCache
            })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            throw new Error(data.detail || data.message || 'Bulk exit failed');
        }

        if (notice) {
            notice.className = 'text-xs font-bold text-emerald-600';
            notice.innerText = `Cleared ${data.exited_count} cars (${data.exempted_count} whitelisted stayed inside).`;
        }

        alert(`Bulk clearance complete!\n\n${data.message}`);

        await loadBulkExitSettings();
        if (typeof loadAudit === 'function') loadAudit(currentAuditPage);
        if (typeof loadStats === 'function') loadStats();
    } catch (e) {
        if (notice) {
            notice.className = 'text-xs font-bold text-rose-600';
            notice.innerText = `Error: ${e.message}`;
        }
        alert(`Bulk exit error: ${e.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('opacity-75');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initAuth();
    initCharts();
    loadStats();
    loadCharts();
    loadHardware();
    loadGateFeed();
    loadActivity();
    loadMembers();
    loadSettings();
    loadAudit();
    setupGlobalSearch();

    const urlParams = new URLSearchParams(window.location.search);
    const urlTab = urlParams.get('tab');
    const urlTag = urlParams.get('tag') || urlParams.get('etag');
    if (urlTag) {
        switchTab('etag_audit');
        loadEtagAudit(urlTag);
    } else if (urlTab) {
        switchTab(urlTab);
    }

    setInterval(loadStats, 5000);
    setInterval(loadGateFeed, 800);
    setInterval(loadCharts, 30000);
    setInterval(loadHardware, 3000);
    setInterval(loadActivity, 5000);

    // Smart auto-refresh: Vehicle Audit refreshes every 12s when visible
    setInterval(() => {
        const logsTab = document.getElementById('tab-logs');
        if (logsTab && !logsTab.classList.contains('hidden')) {
            loadAudit(currentAuditPage);
        }
    }, 12000);

    // Smart auto-refresh: Camera Vehicle Audit refreshes every 8s when visible
    setInterval(() => {
        const camTab = document.getElementById('tab-camera_audit');
        if (camTab && !camTab.classList.contains('hidden')) {
            loadCameraAudit(currentCamAuditPage);
        }
    }, 8000);

    // Smart auto-refresh: E-TAG Audit refreshes every 10s when visible
    setInterval(() => {
        const etagTab = document.getElementById('tab-etag_audit');
        if (etagTab && !etagTab.classList.contains('hidden') && currentAuditedTag) {
            loadEtagAudit(currentAuditedTag, true);
        }
    }, 10000);
});
