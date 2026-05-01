// Empty string when served from the backend (same-origin).
// Falls back to localhost when the file is opened directly from the filesystem.
const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : '';

function getToken() {
    return sessionStorage.getItem('token');
}

function getUser() {
    try { return JSON.parse(sessionStorage.getItem('user') || 'null'); }
    catch { return null; }
}

function setSession(token, user) {
    sessionStorage.setItem('token', token);
    sessionStorage.setItem('user', JSON.stringify(user));
}

function clearSession() {
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
}

function requireAuth() {
    if (!getToken()) {
        window.location.replace('login.html');
        return false;
    }
    return true;
}

function requireAdmin() {
    const user = getUser();
    if (!getToken() || !user) { window.location.replace('login.html'); return false; }
    if (user.role !== 'admin' && user.role !== 'super_admin') {
        window.location.replace('index.html');
        return false;
    }
    return true;
}

async function apiLogout() {
    try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch {}
    clearSession();
    window.location.replace('login.html');
}

async function apiFetch(path, options = {}) {
    const isFormData = options.body instanceof FormData;
    const headers = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...options.headers,
    };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (response.status === 401 && !path.includes('/auth/login')) {
        clearSession();
        window.location.replace('login.html');
        throw new Error('Session expired');
    }
    return response;
}

function escapeHtml(str) {
    const el = document.createElement('div');
    el.appendChild(document.createTextNode(str == null ? '' : String(str)));
    return el.innerHTML;
}

function formatDate(isoStr) {
    if (!isoStr) return '—';
    return new Date(isoStr).toLocaleDateString('en-IE', {
        day: '2-digit', month: 'short', year: 'numeric',
    });
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

const STATUS_COLOR = {
    draft:        '#6c757d',
    submitted:    '#0d6efd',
    under_review: '#fd7e14',
    approved:     '#198754',
    rejected:     '#dc3545',
    pending:      '#e0a800',
    ready:        '#0d6efd',
    completed:    '#198754',
    withdrawn:    '#6c757d',
    processing:   '#0d6efd',
    processing_failed: '#dc3545',
    processed:    '#6c757d',
    validated:         '#198754',
    validated_with_issues: '#fd7e14',
};

const STATUS_LABEL_MAP = {
    draft:                 'Draft',
    pending:               'Pending',
    ready:                 'Ready',
    submitted:             'Submitted',
    under_review:          'Under Review',
    approved:              'Approved',
    rejected:              'Rejected',
    completed:             'Completed',
    withdrawn:             'Withdrawn',
    processing:            'Processing',
    processing_failed:     'Processing Failed',
    processed:             'Processed',
    validated:             'Validated ✔',
    validated_with_issues: 'Issues Found ⚠',
};

function statusLabel(s) {
    return STATUS_LABEL_MAP[s] || (s || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function statusBadgeHtml(status, small = false) {
    const color = STATUS_COLOR[status] || '#6c757d';
    const fs = small ? 'font-size:0.78rem;' : '';
    return `<span class="status-chip" style="background:${color};${fs}">${escapeHtml(statusLabel(status))}</span>`;
}
