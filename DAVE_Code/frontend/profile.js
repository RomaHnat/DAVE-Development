// ── profile.js ──────────────────────────────────────────────────────────────
// Handles the My Profile page: personal info, change password,
// notification preferences, and active sessions tabs.

document.addEventListener('DOMContentLoaded', async () => {
    if (!requireAuth()) return;

    const user = getUser();
    document.getElementById('header-user-name').textContent =
        user?.full_name || user?.email || '';

    if (user?.role === 'admin' || user?.role === 'super_admin') {
        document.getElementById('admin-link').style.display = 'inline';
    }

    document.getElementById('logout-btn')
        .addEventListener('click', e => { e.preventDefault(); apiLogout(); });

    initTabs();

    // Load profile data straight away; lazy-load other tabs on first open
    await loadProfile();
});

// ── Tabs ──────────────────────────────────────────────────────────────────────

const _tabLoaded = {};

function initTabs() {
    document.querySelectorAll('.profile-tab').forEach(tab => {
        tab.addEventListener('click', () => activateTab(tab.dataset.tab));
    });
    document.getElementById('info-form')
        .addEventListener('submit', saveProfile);
    document.getElementById('pw-form')
        .addEventListener('submit', changePassword);
    document.getElementById('notif-save-btn')
        .addEventListener('click', saveNotifPrefs);
    document.getElementById('logout-all-btn')
        .addEventListener('click', logoutAll);
}

function activateTab(tabId) {
    document.querySelectorAll('.profile-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tabId));
    document.querySelectorAll('.tab-panel').forEach(p =>
        p.style.display = p.id === tabId ? 'block' : 'none');

    if (!_tabLoaded[tabId]) {
        _tabLoaded[tabId] = true;
        if (tabId === 'tab-notif')    loadNotifPrefs();
        if (tabId === 'tab-sessions') loadSessions();
    }
}

// ── Personal Info ─────────────────────────────────────────────────────────────

async function loadProfile() {
    try {
        const res = await apiFetch('/api/users/me');
        if (!res.ok) throw new Error();
        const u = await res.json();

        document.getElementById('p-full-name').value = u.full_name || '';
        document.getElementById('p-email').value     = u.email     || '';
        document.getElementById('p-phone').value     = u.phone     || '';
        document.getElementById('p-role').value      = u.role      || '';
        document.getElementById('p-created').value   = formatDate(u.created_at);

        // Keep sessionStorage fresh
        setSession(getToken(), u);
        document.getElementById('header-user-name').textContent =
            u.full_name || u.email || '';
    } catch {
        showMsg('info-msg', 'Could not load profile.', 'error');
    }
}

async function saveProfile(e) {
    e.preventDefault();
    const btn     = document.getElementById('info-save-btn');
    const fullName = document.getElementById('p-full-name').value.trim();
    const phone    = document.getElementById('p-phone').value.trim();

    if (!fullName) {
        showMsg('info-msg', 'Full name is required.', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Saving…';
    hideMsg('info-msg');

    try {
        const res = await apiFetch('/api/users/me', {
            method: 'PUT',
            body: JSON.stringify({ full_name: fullName, phone: phone || null }),
        });

        if (res.ok) {
            const u = await res.json();
            setSession(getToken(), u);
            document.getElementById('header-user-name').textContent =
                u.full_name || u.email || '';
            showMsg('info-msg', 'Profile updated successfully.', 'success');
        } else {
            const err = await res.json().catch(() => ({}));
            showMsg('info-msg', err.detail || 'Could not save changes.', 'error');
        }
    } catch {
        showMsg('info-msg', 'Could not connect to server.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Changes';
    }
}

// ── Change Password ───────────────────────────────────────────────────────────

async function changePassword(e) {
    e.preventDefault();
    const btn        = document.getElementById('pw-save-btn');
    const current    = document.getElementById('pw-current').value;
    const newPw      = document.getElementById('pw-new').value;
    const confirm    = document.getElementById('pw-confirm').value;

    if (!current || !newPw || !confirm) {
        showMsg('pw-msg', 'All fields are required.', 'error');
        return;
    }
    if (newPw !== confirm) {
        showMsg('pw-msg', 'New passwords do not match.', 'error');
        return;
    }
    if (newPw.length < 8 || !/[A-Z]/.test(newPw) || !/[0-9]/.test(newPw)) {
        showMsg('pw-msg',
            'Password must be at least 8 characters and include one uppercase letter and one number.',
            'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Updating…';
    hideMsg('pw-msg');

    try {
        const res = await apiFetch('/api/users/me/change-password', {
            method: 'POST',
            body: JSON.stringify({ current_password: current, new_password: newPw }),
        });

        if (res.ok) {
            showMsg('pw-msg', 'Password updated successfully.', 'success');
            document.getElementById('pw-form').reset();
        } else {
            const err = await res.json().catch(() => ({}));
            showMsg('pw-msg', err.detail || 'Could not update password.', 'error');
        }
    } catch {
        showMsg('pw-msg', 'Could not connect to server.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Update Password';
    }
}

// ── Notification Preferences ──────────────────────────────────────────────────

const NOTIF_LABELS = {
    application_submitted : 'Application submitted',
    application_approved  : 'Application approved',
    application_rejected  : 'Application rejected',
    document_processed    : 'Document processed',
    status_change         : 'Application status changed',
};

let _currentPrefs = {};

async function loadNotifPrefs() {
    const body = document.getElementById('notif-prefs-body');
    body.innerHTML = '<div style="text-align:center;padding:2em"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';
    try {
        const res = await apiFetch('/api/users/me/notification-preferences');
        if (!res.ok) throw new Error();
        const data = await res.json();
        _currentPrefs = data.preferences || data || {};
        renderNotifPrefs();
    } catch {
        body.innerHTML = '<p style="padding:1em;color:#721c24">Could not load preferences.</p>';
    }
}

function renderNotifPrefs() {
    const body  = document.getElementById('notif-prefs-body');
    const prefs = _currentPrefs;

    // Build a table: event | In-app | Email
    const rows = Object.entries(NOTIF_LABELS).map(([key, label]) => {
        const inApp = prefs[key]?.in_app   ?? prefs[`${key}_in_app`]   ?? true;
        const email = prefs[key]?.email    ?? prefs[`${key}_email`]    ?? true;
        return `
            <tr>
                <td style="padding:0.6em 0.75em;vertical-align:middle">${escapeHtml(label)}</td>
                <td style="padding:0.6em 0.75em;text-align:center;vertical-align:middle">
                    <input type="checkbox" class="form-check-input pref-check"
                           data-key="${key}" data-channel="in_app"
                           ${inApp ? 'checked' : ''} style="cursor:pointer;width:1.1em;height:1.1em">
                </td>
                <td style="padding:0.6em 0.75em;text-align:center;vertical-align:middle">
                    <input type="checkbox" class="form-check-input pref-check"
                           data-key="${key}" data-channel="email"
                           ${email ? 'checked' : ''} style="cursor:pointer;width:1.1em;height:1.1em">
                </td>
            </tr>`;
    }).join('');

    body.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:0.95rem">
            <thead>
                <tr style="border-bottom:2px solid #dee2e6;background:#f8f9fa">
                    <th style="padding:0.6em 0.75em;text-align:left">Event</th>
                    <th style="padding:0.6em 0.75em;text-align:center;width:8em">In-App</th>
                    <th style="padding:0.6em 0.75em;text-align:center;width:8em">Email</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;
}

async function saveNotifPrefs() {
    const btn = document.getElementById('notif-save-btn');
    hideMsg('notif-prefs-msg');
    btn.disabled = true;
    btn.textContent = 'Saving…';

    // Build payload from checkboxes
    const updated = {};
    document.querySelectorAll('.pref-check').forEach(cb => {
        const { key, channel } = cb.dataset;
        if (!updated[key]) updated[key] = {};
        updated[key][channel] = cb.checked;
    });

    try {
        const res = await apiFetch('/api/users/me/notification-preferences', {
            method: 'POST',
            body: JSON.stringify({ preferences: updated }),
        });

        if (res.ok) {
            const data = await res.json();
            _currentPrefs = data.preferences || data || updated;
            showMsg('notif-prefs-msg', 'Preferences saved.', 'success');
        } else {
            const err = await res.json().catch(() => ({}));
            showMsg('notif-prefs-msg', err.detail || 'Could not save preferences.', 'error');
        }
    } catch {
        showMsg('notif-prefs-msg', 'Could not connect to server.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Preferences';
    }
}

// ── Active Sessions ───────────────────────────────────────────────────────────

async function loadSessions() {
    const body = document.getElementById('sessions-body');
    body.innerHTML = '<div style="text-align:center;padding:2em"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';
    try {
        const res = await apiFetch('/api/users/me/sessions');
        if (!res.ok) throw new Error();
        const data = await res.json();
        const sessions = Array.isArray(data) ? data : (data.sessions || []);
        renderSessions(sessions);
    } catch {
        body.innerHTML = '<p style="padding:1em;color:#721c24">Could not load sessions.</p>';
    }
}

function renderSessions(sessions) {
    const body = document.getElementById('sessions-body');
    if (!sessions.length) {
        body.innerHTML = '<p style="padding:1em;color:#666">No active sessions found.</p>';
        return;
    }

    const rows = sessions.map(s => `
        <tr style="border-bottom:1px solid #dee2e6">
            <td style="padding:0.75em">
                <span style="font-size:1.3rem;margin-right:0.5em">${deviceIcon(s.device_info || s.user_agent || '')}</span>
                <span>${escapeHtml(s.device_info || s.user_agent || 'Unknown device')}</span>
            </td>
            <td style="padding:0.75em;color:#555;font-size:0.9rem">${formatDate(s.created_at || s.last_used_at)}</td>
            <td style="padding:0.75em;color:#555;font-size:0.9rem">${escapeHtml(s.ip_address || '—')}</td>
            <td style="padding:0.75em;text-align:right">
                ${s.is_current
                    ? '<span class="status-badge" style="background:#0d6efd;font-size:0.78rem">Current</span>'
                    : ''}
            </td>
        </tr>`).join('');

    body.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:0.92rem">
            <thead>
                <tr style="border-bottom:2px solid #dee2e6;background:#f8f9fa">
                    <th style="padding:0.75em;text-align:left">Device</th>
                    <th style="padding:0.75em;text-align:left">First seen</th>
                    <th style="padding:0.75em;text-align:left">IP Address</th>
                    <th style="padding:0.75em"></th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;
}

async function logoutAll() {
    if (!confirm('Sign out all devices? You will be logged out here too.')) return;
    try {
        await apiFetch('/api/users/me/sessions', { method: 'DELETE' });
    } catch {}
    apiLogout();
}

function deviceIcon(ua) {
    ua = ua.toLowerCase();
    if (ua.includes('mobile') || ua.includes('android') || ua.includes('iphone')) return '📱';
    if (ua.includes('tablet') || ua.includes('ipad')) return '📟';
    return '🖥️';
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function showMsg(id, text, type) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = `login-message ${type === 'success' ? 'success-alert' : 'error-alert'}`;
    el.style.display = 'block';
    if (type === 'success') setTimeout(() => hideMsg(id), 4000);
}

function hideMsg(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
}
