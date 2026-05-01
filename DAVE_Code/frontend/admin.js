﻿let reviewingAppId = null;

document.addEventListener('DOMContentLoaded', async () => {
    if (!requireAdmin()) return;

    document.getElementById('logout-btn')
        .addEventListener('click', e => { e.preventDefault(); apiLogout(); });

    document.getElementById('status-filter')
        .addEventListener('change', loadAdminApps);

    await loadAdminApps();
});

function switchTab(tab) {
    document.getElementById('tab-apps').style.display   = tab === 'apps'  ? 'block' : 'none';
    document.getElementById('tab-users').style.display  = tab === 'users' ? 'block' : 'none';
    document.getElementById('tab-apps-btn').classList.toggle('tab-active',  tab === 'apps');
    document.getElementById('tab-users-btn').classList.toggle('tab-active', tab === 'users');
    if (tab === 'users') loadAdminUsers();
}

async function loadAdminApps() {
    const statusFilter = document.getElementById('status-filter').value;
    let url = '/api/admin/applications?page_size=100';
    if (statusFilter) url += `&status=${statusFilter}`;

    const loadEl = document.getElementById('admin-apps-loading');
    const tableEl = document.getElementById('admin-apps-table');
    loadEl.innerHTML = '<span class="spinner-border spinner-border-sm"></span>&nbsp; Loading…';
    loadEl.style.display = 'block';
    tableEl.style.display = 'none';

    try {
        const res = await apiFetch(url);
        if (!res.ok) {
            loadEl.innerHTML = `<span class="error-alert">Could not load applications (HTTP ${res.status}).</span>`;
            return;
        }
        const data = await res.json();
        renderAdminApps(data.applications || []);
    } catch (e) {
        if (e.message !== 'Session expired')
            loadEl.innerHTML = '<span class="error-alert">Failed to connect to server.</span>';
    }
}

function renderAdminApps(apps) {
    document.getElementById('admin-apps-loading').style.display = 'none';

    const tbody = document.getElementById('admin-apps-tbody');
    tbody.innerHTML = '';

    if (!apps.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#666;padding:1.5em">No applications found.</td></tr>';
        document.getElementById('admin-apps-table').style.display = 'table';
        return;
    }

    apps.forEach(app => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><code>${escapeHtml(app.case_id)}</code></td>
            <td>${escapeHtml(app.application_type_name || '—')}</td>
            <td>${statusBadgeHtml(app.status)}</td>
            <td>${formatDate(app.submitted_at)}</td>
            <td style="white-space:nowrap">
                <a href="application.html?id=${escapeHtml(app.id)}"
                   class="secondary-button"
                   style="padding:0.25em 0.65em;font-size:0.82rem;text-decoration:none;display:inline-block">
                    View
                </a>
                <button
                    onclick="openReviewModal('${escapeHtml(app.id)}','${escapeHtml(app.case_id)}')"
                    class="primary-button"
                    style="padding:0.25em 0.65em;font-size:0.82rem;margin-left:0.35em">
                    Review
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('admin-apps-table').style.display = 'table';
}

function openReviewModal(appId, caseId) {
    reviewingAppId = appId;
    document.getElementById('review-modal-title').textContent = `Review - ${caseId}`;
    document.getElementById('review-info').innerHTML =
        `Updating status for application <strong>${escapeHtml(caseId)}</strong>.`;
    document.getElementById('review-notes').value = '';
    document.getElementById('review-msg').style.display = 'none';
    document.getElementById('review-modal').style.display = 'flex';
}

function closeReviewModal() {
    document.getElementById('review-modal').style.display = 'none';
    reviewingAppId = null;
}

async function submitReview() {
    if (!reviewingAppId) return;

    const status = document.getElementById('review-status').value;
    const notes  = document.getElementById('review-notes').value.trim();
    const msgEl  = document.getElementById('review-msg');

    const body = { status };
    if (notes) body.notes = notes;

    try {
        const res = await apiFetch(`/api/admin/applications/${reviewingAppId}/status`, {
            method: 'PATCH',
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.json();
            const detail = err.detail;
            msgEl.textContent = typeof detail === 'string'
                ? detail
                : (detail?.[0]?.msg || 'Update failed.');
            msgEl.className = 'login-message error-alert';
            msgEl.style.display = 'block';
            return;
        }

        closeReviewModal();
        await loadAdminApps();

    } catch (e) {
        if (e.message !== 'Session expired') {
            msgEl.textContent = 'Could not update status.';
            msgEl.className = 'login-message error-alert';
            msgEl.style.display = 'block';
        }
    }
}

async function loadAdminUsers() {
    const loadEl  = document.getElementById('admin-users-loading');
    const tableEl = document.getElementById('admin-users-table');

    loadEl.innerHTML = '<span class="spinner-border spinner-border-sm"></span>&nbsp; Loading…';
    loadEl.style.display = 'block';
    tableEl.style.display = 'none';

    try {
        const res = await apiFetch('/api/admin/users?page_size=100');
        if (!res.ok) {
            loadEl.innerHTML = `<span class="error-alert">Could not load users (HTTP ${res.status}).</span>`;
            return;
        }
        const data = await res.json();
        renderAdminUsers(data.users || []);
    } catch (e) {
        if (e.message !== 'Session expired')
            loadEl.innerHTML = '<span class="error-alert">Failed to connect to server.</span>';
    }
}

function renderAdminUsers(users) {
    document.getElementById('admin-users-loading').style.display = 'none';

    const tbody = document.getElementById('admin-users-tbody');
    tbody.innerHTML = '';

    if (!users.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#666;padding:1.5em">No users found.</td></tr>';
        document.getElementById('admin-users-table').style.display = 'table';
        return;
    }

    users.forEach(u => {
        const roleColor = (u.role === 'admin' || u.role === 'super_admin') ? '#0d6efd' : '#6c757d';
        const activeColor = u.is_active ? '#198754' : '#dc3545';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(u.full_name || '—')}</td>
            <td>${escapeHtml(u.email)}</td>
            <td><span class="status-chip" style="background:${roleColor}">${escapeHtml(u.role)}</span></td>
            <td><span class="status-chip" style="background:${activeColor}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
            <td>${formatDate(u.created_at)}</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('admin-users-table').style.display = 'table';
}
