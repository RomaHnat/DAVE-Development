document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('login-form');
    
    loginForm.addEventListener('submit', handleLogin);
});

function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    const validEmail = 'test@dave.ie';
    const validPassword = 'test123';
    
    const loginMessage = document.getElementById('login-message');
    loginMessage.style.display = 'none';
    
    if (email === validEmail && password === validPassword) {

        showMessage('Login successful! Redirecting...', 'success');

        sessionStorage.setItem('isLoggedIn', 'true');
        sessionStorage.setItem('userEmail', email);

        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1000);
    } else {

        showMessage('Invalid email or password. Please try again.', 'error');
    }
}

function showMessage(message, type) {
    const loginMessage = document.getElementById('login-message');
    loginMessage.style.display = 'block';
    loginMessage.textContent = message;
    
    loginMessage.className = 'login-message';
    
    if (type === 'success') {
        loginMessage.classList.add('success-alert');
    } else {
        loginMessage.classList.add('error-alert');
    }
}
