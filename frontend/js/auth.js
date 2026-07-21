/**
 * ConversaPay Authentication JavaScript
 * Handles login, registration, and token management
 */

(function() {
    'use strict';

    // ============================================
    // Configuration
    // ============================================
    
    const API_BASE_URL = window.location.origin + '/api/v1';
    const TOKEN_KEY = 'conversapay_auth_token';
    const USER_KEY = 'conversapay_user';

    // ============================================
    // Initialization
    // ============================================
    
    document.addEventListener('DOMContentLoaded', () => {
        initializeEventListeners();
        checkAuthState();
    });

    function initializeEventListeners() {
        // Login form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', handleLogin);
        }

        // Register form
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', handleRegister);
        }
    }

    // ============================================
    // Authentication Functions
    // ============================================
    
    async function handleLogin(event) {
        event.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const rememberMe = document.getElementById('rememberMe').checked;
        const loginBtn = document.getElementById('loginBtn');
        const errorDiv = document.getElementById('errorMessage');
        const successDiv = document.getElementById('successMessage');
        
        // Clear messages
        errorDiv.classList.remove('show');
        successDiv.classList.remove('show');
        
        // Disable button
        loginBtn.disabled = true;
        loginBtn.textContent = 'מתחבר...';
        
        try {
            const response = await fetch(`${API_BASE_URL}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Save token
                const token = data.access_token;
                const user = {
                    user_id: data.user_id,
                    email: data.email
                };
                
                if (rememberMe) {
                    localStorage.setItem(TOKEN_KEY, token);
                    localStorage.setItem(USER_KEY, JSON.stringify(user));
                } else {
                    sessionStorage.setItem(TOKEN_KEY, token);
                    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
                }
                
                // Check if plan=pro parameter is present
                if (getUrlParam('plan') === 'pro') {
                    setTimeout(() => { redirectToProCheckout(); }, 1000);
                } else {
                    successDiv.textContent = 'התחברת בהצלחה! מעביר לדשבורד...';
                    successDiv.classList.add('show');
                    setTimeout(() => { window.location.href = '/dashboard.html'; }, 1000);
                }
                
            } else {
                if (data.detail === 'email_not_verified') {
                    errorDiv.innerHTML = '📧 עליך לאמת את כתובת האימייל שלך לפני הכניסה.<br><small>בדוק את תיבת הדואר שלך ולחץ על קישור האימות.</small>';
                } else {
                    errorDiv.textContent = data.detail || 'שגיאה בהתחברות. אנא נסה שוב.';
                }
                errorDiv.classList.add('show');
                loginBtn.disabled = false;
                loginBtn.textContent = 'התחבר';
            }
            
        } catch (error) {
            console.error('Login error:', error);
            errorDiv.textContent = 'שגיאה בתקשורת עם השרת. אנא נסה שוב.';
            errorDiv.classList.add('show');
            loginBtn.disabled = false;
            loginBtn.textContent = 'התחבר';
        }
    }

    async function handleRegister(event) {
        event.preventDefault();
        
        const fullName = document.getElementById('fullName').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const businessName = document.getElementById('businessName').value;
        const registerBtn = document.getElementById('registerBtn');
        const errorDiv = document.getElementById('errorMessage');
        const successDiv = document.getElementById('successMessage');
        
        // Clear messages
        errorDiv.classList.remove('show');
        successDiv.classList.remove('show');
        
        // Disable button
        registerBtn.disabled = true;
        registerBtn.textContent = 'יוצר חשבון...';
        
        try {
            const response = await fetch(`${API_BASE_URL}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    full_name: fullName,
                    email: email,
                    password: password,
                    business_name: businessName
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Check if email verification is required
                if (data.requires_verification) {
                    successDiv.textContent = 'החשבון נוצר בהצלחה! אנא בדוק את המייל שלך לאימות החשבון.';
                    successDiv.classList.add('show');
                    registerBtn.disabled = false;
                    registerBtn.textContent = 'צור חשבון';
                    
                    // Redirect to login after 3 seconds
                    setTimeout(() => {
                        window.location.href = '/login.html';
                    }, 3000);
} else {
                    // Save token
                    const token = data.access_token;
                    const user = {
                        user_id: data.user_id,
                        email: data.email
                    };
                    
                    localStorage.setItem(TOKEN_KEY, token);
                    localStorage.setItem(USER_KEY, JSON.stringify(user));
                    
                    // Check if plan=pro parameter is present
                    if (getUrlParam('plan') === 'pro') {
                        // Redirect to Pro checkout
                        setTimeout(() => {
                            redirectToProCheckout();
                        }, 1000);
                    } else {
                        // Show success message
                        successDiv.textContent = 'החשבון נוצר בהצלחה! מעביר לדשבורד...';
                        successDiv.classList.add('show');
                        
                        // Redirect to dashboard
                        setTimeout(() => {
                            window.location.href = '/dashboard.html';
                        }, 1000);
                    }
                }
            } else {
                // Show error
                errorDiv.textContent = data.detail || 'שגיאה בהרשמה. אנא נסה שוב.';
                errorDiv.classList.add('show');
                registerBtn.disabled = false;
                registerBtn.textContent = 'צור חשבון';
            }
            
        } catch (error) {
            console.error('Register error:', error);
            errorDiv.textContent = 'שגיאה בתקשורת עם השרת. אנא נסה שוב.';
            errorDiv.classList.add('show');
            registerBtn.disabled = false;
            registerBtn.textContent = 'צור חשבון';
        }
    }

    // ============================================
    // Token Management
    // ============================================
    
    function getToken() {
        // Try localStorage first, then sessionStorage
        return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
    }
    
    function getUser() {
        const userStr = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY);
        return userStr ? JSON.parse(userStr) : null;
    }
    
    /**
     * Decode a JWT token's payload (base64url) without verifying the signature.
     * Returns the parsed payload object, or null if decoding fails.
     */
    function decodeJwtPayload(token) {
        try {
            const parts = token.split('.');
            if (parts.length !== 3) return null;
            // Base64url decode the payload (second part)
            const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
            const decoded = atob(base64);
            return JSON.parse(decoded);
        } catch {
            return null;
        }
    }

    function isAuthenticated() {
        const token = getToken();
        if (!token) return false;
        
        // Decode JWT payload to check expiration
        const payload = decodeJwtPayload(token);
        if (!payload) return false;
        
        // Check if token has expired
        if (payload.exp) {
            const now = Math.floor(Date.now() / 1000);
            if (now >= payload.exp) {
                // Token expired - clean up storage
                localStorage.removeItem(TOKEN_KEY);
                localStorage.removeItem(USER_KEY);
                sessionStorage.removeItem(TOKEN_KEY);
                sessionStorage.removeItem(USER_KEY);
                return false;
            }
        }
        
        return true;
    }
    
    function logout() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(USER_KEY);
        
        // Redirect to login
        window.location.href = '/login.html';
    }
    
function checkAuthState() {
    // If on auth pages and already logged in, redirect to dashboard
    if (isAuthenticated()) {
        const path = window.location.pathname;
        if (path === '/login.html' || path === '/register.html') {
            window.location.href = '/dashboard.html';
        }
    }
}

// ============================================
// Pro Plan Redirect Handling
// ============================================

function getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

async function redirectToProCheckout() {
    try {
        const token = getToken();
        if (!token) return;
        
        const response = await fetch(`${API_BASE_URL}/payments/create-checkout-session`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: getUser()?.user_id || getUser()?.id,
                email: getUser()?.email,
                full_name: getUser()?.full_name || ''
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            window.location.href = data.url;
        } else {
            // If there's an error, just go to dashboard
            window.location.href = '/dashboard.html';
        }
    } catch (error) {
        console.error('Error redirecting to Pro checkout:', error);
        window.location.href = '/dashboard.html';
    }
}

    // ============================================
    // API Helper Functions
    // ============================================
    
    function getAuthHeaders() {
        const token = getToken();
        if (!token) {
            return {};
        }
        
        return {
            'Authorization': `Bearer ${token}`
        };
    }
    
    async function authenticatedFetch(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...getAuthHeaders(),
            ...options.headers
        };
        
        const response = await fetch(url, {
            ...options,
            headers
        });
        
        // If unauthorized, redirect to login
        if (response.status === 401) {
            logout();
        }
        
        return response;
    }

    // ============================================
    // Expose Functions to Global Scope
    // ============================================
    
    window.ConversaPayAuth = {
        getToken,
        getUser,
        isAuthenticated,
        logout,
        getAuthHeaders,
        authenticatedFetch
    };

})();