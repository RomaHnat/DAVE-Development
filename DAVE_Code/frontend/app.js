let cachedTypes = [];

document.addEventListener('DOMContentLoaded', async () => {

    if (!requireAuth()) return;

    const user = getUser();
    // Force redirect admin users to admin.html if they land on index.html
    if (user?.role === 'admin' || user?.role === 'super_admin') {
        window.location.replace('admin.html');
        return;
    }
    document.getElementById('header-user-name').textContent = user?.full_name || user?.email || '';

    // Logout
    document.getElementById('logout-btn').addEventListener('click', e => { e.preventDefault(); apiLogout(); });

    // Notification panel toggle
    document.getElementById('notif-toggle').addEventListener('click', e => { e.preventDefault(); toggleNotifPanel(); });
    document.getElementById('mark-all-btn').addEventListener('click', markAllRead);

    // New-application modal
    document.getElementById('new-app-btn').addEventListener('click', openModal);
    document.getElementById('modal-close-btn').addEventListener('click', closeModal);
    document.getElementById('modal-cancel-btn').addEventListener('click', closeModal);
    document.getElementById('modal-create-btn').addEventListener('click', createApplication);
    document.getElementById('type-select').addEventListener('change', onTypeSelected);

    await Promise.all([loadApplications(), loadNotifCount()]);
});

async function loadApplications() {
    try {
        const res = await apiFetch('/api/applications?page_size=50');
        if (!res.ok) throw new Error();
        const data = await res.json();
        renderApplications(data.applications || []);
    } catch {
        document.getElementById('apps-loading').innerHTML =
            '<span class="error-alert" style="padding:0.5em">Failed to load applications.</span>';
    }
}

function renderApplications(apps) {
    document.getElementById('apps-loading').style.display = 'none';
    if (!apps.length) {
        document.getElementById('apps-empty').style.display = 'block';
        return;
    }
    const tbody = document.getElementById('apps-tbody');
    tbody.innerHTML = apps.map(app => `
        <tr>
            <td><code>${escapeHtml(app.case_id)}</code></td>
            <td>${escapeHtml(app.application_type_name || '-') }</td>
            <td>${statusBadgeHtml(app.status)}</td>
            <td>${formatDate(app.created_at)}</td>
            <td>${formatDate(app.updated_at)}</td>
            <td style="white-space:nowrap">
                <a href="application.html?id=${escapeHtml(app.id)}"
                   class="primary-button" style="padding:0.25em 0.75em;font-size:0.82rem;text-decoration:none;display:inline-block">
                   View
                </a>
                ${(app.status === 'draft' || app.status === 'ready') ? `
                <button onclick="deleteApp('${escapeHtml(app.id)}')"
                        class="danger-button" style="padding:0.25em 0.75em;font-size:0.82rem;margin-left:0.3em">
                    Delete
                </button>` : ''}
            </td>
        </tr>`).join('');
    document.getElementById('apps-table').style.display = 'table';
}

async function deleteApp(id) {
    if (!confirm('Delete this application? This cannot be undone.')) return;
    try {
        const res = await apiFetch(`/api/applications/${id}`, { method: 'DELETE' });
        if (res.ok) await loadApplications();
        else alert('Could not delete application.');
    } catch {}
}

let notifOpen = false;

async function loadNotifCount() {
    try {
        const res = await apiFetch('/api/notifications/unread-count');
        if (!res.ok) return;
        const { unread_count } = await res.json();
        const badge = document.getElementById('notif-badge');
        badge.textContent = unread_count > 9 ? '9+' : unread_count;
        badge.style.display = unread_count > 0 ? 'inline-block' : 'none';
    } catch {}
}

async function toggleNotifPanel() {
    const panel = document.getElementById('notif-panel');
    notifOpen = !notifOpen;
    panel.style.display = notifOpen ? 'block' : 'none';
    if (notifOpen) await loadNotifications();
}

async function loadNotifications() {
    const list = document.getElementById('notif-list');
    list.innerHTML = '<div style="padding:1em;text-align:center"><span class="spinner-border spinner-border-sm"></span></div>';
    try {
        const res = await apiFetch('/api/notifications?page_size=15');
        if (!res.ok) { list.innerHTML = '<p style="padding:0.8em;color:#666">Could not load.</p>'; return; }
        const { notifications } = await res.json();
        if (!notifications?.length) {
            list.innerHTML = '<p style="padding:0.8em;color:#666">No notifications.</p>';
            return;
        }
        list.innerHTML = notifications.map(n => `
            <div class="notif-item ${n.is_read ? '' : 'notif-unread'}" data-id="${escapeHtml(n.id)}">
                <div class="notif-title">${escapeHtml(n.title)}</div>
                <div class="notif-msg">${escapeHtml(n.message)}</div>
                <div class="notif-time">${formatDate(n.created_at)}</div>
            </div>`).join('');
        list.querySelectorAll('.notif-item').forEach(el =>
            el.addEventListener('click', () => markOneRead(el.dataset.id, el)));
    } catch {}
}

async function markOneRead(id, el) {
    try { await apiFetch(`/api/notifications/${id}/read`, { method: 'PATCH' }); } catch {}
    el?.classList.remove('notif-unread');
    await loadNotifCount();
}

async function markAllRead() {
    try { await apiFetch('/api/notifications/read-all', { method: 'POST' }); } catch {}
    await Promise.all([loadNotifications(), loadNotifCount()]);
}

async function openModal() {
    document.getElementById('modal-msg').style.display = 'none';
    document.getElementById('new-app-modal').style.display = 'flex';
    if (!cachedTypes.length) await loadTypes();
}

function closeModal() {
    document.getElementById('new-app-modal').style.display = 'none';
}

async function loadTypes() {
    try {
        const res = await apiFetch('/api/application-types');
        if (!res.ok) return;
        const data = await res.json();
        const types = (Array.isArray(data) ? data : (data.application_types || []))
            .filter(t => t.status === 'active');
        cachedTypes = types;
        const sel = document.getElementById('type-select');
        sel.innerHTML = '<option value="">Select a type</option>' +
            types.map(t => `<option value="${escapeHtml(t.id)}">${escapeHtml(t.type_name)}</option>`).join('');
    } catch {}
}

function onTypeSelected() {
    const id  = document.getElementById('type-select').value;
    const el  = document.getElementById('type-desc');
    const t   = cachedTypes.find(x => x.id === id);
    if (t?.description) { el.textContent = t.description; el.style.display = 'block'; }
    else                 { el.style.display = 'none'; }
}

async function createApplication() {
    const typeId = document.getElementById('type-select').value;
    const msgEl  = document.getElementById('modal-msg');
    if (!typeId) {
        msgEl.textContent = 'Please select an application type.';
        msgEl.className   = 'login-message error-alert';
        msgEl.style.display = 'block';
        return;
    }
    try {
        const res = await apiFetch('/api/applications', {
            method: 'POST',
            body: JSON.stringify({ application_type_id: typeId, form_data: {} }),
        });
        if (!res.ok) {
            const err = await res.json();
            msgEl.textContent   = err.detail || 'Could not create application.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
            return;
        }
        const app = await res.json();
        closeModal();
        window.location.href = `application.html?id=${app.id}`;
    } catch (e) {
        if (e.message !== 'Session expired') {
            msgEl.textContent   = 'Could not connect to server.';
            msgEl.className     = 'login-message error-alert';
            msgEl.style.display = 'block';
        }
    }
}

