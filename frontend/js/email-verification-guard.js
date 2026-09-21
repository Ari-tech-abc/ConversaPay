(() => {
  const API = '/api/v1';
  const token = localStorage.getItem('access_token') || localStorage.getItem('conversapay_auth_token') || sessionStorage.getItem('access_token') || sessionStorage.getItem('conversapay_auth_token');
  let blocked = false;

  function clearAuth() {
    ['access_token', 'conversapay_auth_token', 'conversapay_user', 'user_id', 'email'].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
  }

  function showVerificationModal(message = 'חשבונך עדיין לא אומת. חזור למסך הכניסה ובקש קוד אימות חדש.') {
    if (blocked) return;
    blocked = true;
    const overlay = document.createElement('div');
    overlay.id = 'emailVerificationModal';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `<div style="position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:20px;background:rgba(20,18,38,.50);backdrop-filter:blur(12px)"><div style="max-width:560px;width:100%;padding:30px;border-radius:26px;background:#fff;color:#171923;border:1px solid #ded9fb;box-shadow:0 30px 90px rgba(31,24,67,.28);text-align:center;position:relative"><button id="verificationClose" aria-label="סגור" style="position:absolute;top:14px;left:14px;width:38px;height:38px;border:0;border-radius:12px;background:#f1f1f7;font-size:24px;cursor:pointer">×</button><div style="width:48px;height:48px;border-radius:16px;margin:0 auto 14px;display:grid;place-items:center;background:#eeecfd;color:#5b4fe8;font-weight:900">✉</div><h2>נדרש אימות מייל</h2><p style="line-height:1.7;color:#62667a">${message}</p><button id="verificationLogin" style="margin-top:14px;padding:12px 18px;border:0;border-radius:12px;background:#5b4fe8;color:#fff;font-weight:800;cursor:pointer">מעבר לכניסה</button></div></div>`;
    document.body.appendChild(overlay);
    const leave = () => { clearAuth(); location.href = '/login'; };
    document.getElementById('verificationClose').onclick = leave;
    document.getElementById('verificationLogin').onclick = leave;
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (response.status === 403) {
      const clone = response.clone();
      const data = await clone.json().catch(() => ({}));
      if (data.detail === 'EMAIL_NOT_VERIFIED' || data.detail === 'email_not_verified') showVerificationModal();
    }
    return response;
  };

  async function verifyDashboardAccess() {
    if (!token) return;
    try {
      const response = await originalFetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
      if (response.status === 401) return;
      if (response.status === 403) {
        const data = await response.json().catch(() => ({}));
        if (data.detail === 'EMAIL_NOT_VERIFIED' || data.detail === 'email_not_verified') showVerificationModal();
        return;
      }
      if (!response.ok) return;
      const data = await response.json().catch(() => ({}));
      if (data.requires_business_onboarding && location.pathname.startsWith('/dashboard')) {
        location.replace('/onboarding');
      }
    } catch (_) {
      // Dashboard request handling remains the source of truth for transient failures.
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', verifyDashboardAccess, { once: true });
  else verifyDashboardAccess();
})();
