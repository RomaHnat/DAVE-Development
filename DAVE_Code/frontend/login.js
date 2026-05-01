document.addEventListener('DOMContentLoaded', function () {
    // If already logged in, go straight to dashboard
    if (getToken()) { window.location.replace('index.html'); return; }

    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('register-form').addEventListener('submit', handleRegister);
});

function showSection(which) {
    document.getElementById('login-section').style.display   = which === 'login'    ? 'block' : 'none';
    document.getElementById('register-section').style.display = which === 'register' ? 'block' : 'none';
    setMsg('login', '', '');
    setMsg('register', '', '');
}

async function handleLogin(event) {
    event.preventDefault();
    const email    = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    setMsg('login', '', '');

    try {
        const res = await apiFetch('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
            const err = await res.json();
            const msg = typeof err.detail === 'string'
                ? err.detail
                : (err.detail?.[0]?.msg || 'Login failed. Check your credentials.');
            setMsg('login', msg, 'error');
            return;
        }
        const data = await res.json();
        setSession(data.access_token, data.user_data);
        setMsg('login', 'Login successful! Redirecting...', 'success');
        // Redirect based on user role
        const user = data.user_data;
        const dest = (user && (user.role === 'admin' || user.role === 'super_admin')) ? 'admin.html' : 'index.html';
        setTimeout(() => window.location.replace(dest), 700);
    } catch (e) {
        if (e.message !== 'Session expired')
            setMsg('login', 'Cannot connect to server. Make sure the backend is running.', 'error');
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const full_name = document.getElementById('reg-name').value.trim();
    const email     = document.getElementById('reg-email').value.trim();
    const password  = document.getElementById('reg-password').value;
    setMsg('register', '', '');

    try {
        const res = await apiFetch('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password, full_name }),
        });
        if (!res.ok) {
            const err = await res.json();
            const msg = Array.isArray(err.detail)
                ? err.detail.map(e => e.msg).join('; ')
                : (err.detail || 'Registration failed.');
            setMsg('register', msg, 'error');
            return;
        }
        setMsg('register', 'Account created! You can now log in.', 'success');
        setTimeout(() => showSection('login'), 1500);
    } catch (e) {
        if (e.message !== 'Session expired')
            setMsg('register', 'Cannot connect to server.', 'error');
    }
}

function setMsg(form, message, type) {
    const el = document.getElementById(`${form}-message`);
    if (!el) return;
    el.textContent = message;
    el.style.display = message ? 'block' : 'none';
    el.className = 'login-message ' + (
        type === 'success' ? 'success-alert' :
        type === 'error'   ? 'error-alert'   : ''
    );
}
