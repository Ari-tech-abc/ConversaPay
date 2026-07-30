(() => {
  const API = '/api/v1';
  const message = 'חשבונך עדיין לא אומת. אנא בדוק את תיבת הדואר הנכנס ולחץ על קישור האימות.';
  const token = localStorage.getItem('access_token') || localStorage.getItem('conversapay_auth_token') || sessionStorage.getItem('access_token') || sessionStorage.getItem('conversapay_auth_token');
  let blocked = false;

  function clearAuth() {
    ['access_token', 'conversapay_auth_token', 'conversapay_user', 'user_id', 'email'].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
  }

  function showVerificationModal() {
    if (blocked) return;
    blocked = true;
    const overlay = document.createElement('div');
    overlay.id = 'emailVerificationModal';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `<div style="position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:20px;background:rgba(3,10,20,.82)"><div style="max-width:520px;width:100%;padding:28px;border-radius:24px;background:#0d1b2d;color:#f7fbff;border:1px solid rgba(255,255,255,.14);box-shadow:0 20px 80px rgba(0,0,0,.4);text-align:center"><h2>נדרש אימות מייל</h2><p style="line-height:1.7">${message}</p><p id="verificationStatus" style="color:#a7f3d0"></p><div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap"><button id="resendVerification" style="padding:12px 18px;border:0;border-radius:12px;background:#37d7ff;color:#07111f;font-weight:800;cursor:pointer">שלח מייל אימות שוב</button><button id="verificationLogout" style="padding:12px 18px;border:1px solid rgba(255,255,255,.2);border-radius:12px;background:transparent;color:#f7fbff;cursor:pointer">יציאה</button></div></div></div>`;
    document.body.appendChild(overlay);
    document.getElementById('resendVerification').onclick = async () => {
      const button = document.getElementById('resendVerification');
      const status = document.getElementById('verificationStatus');
      button.disabled = true;
      status.textContent = 'שולח...';
      try {
        const response = await fetch(`${API}/auth/resend-verification`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {} });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'לא ניתן לשלוח כרגע');
        status.textContent = data.message || 'מייל האימות נשלח.';
      } catch (error) {
        status.textContent = error.message || 'לא ניתן לשלוח כרגע';
        button.disabled = false;
      }
    };
    document.getElementById('verificationLogout').onclick = () => { clearAuth(); location.href = '/login'; };
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
})();
