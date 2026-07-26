(() => {
  'use strict';

  const API = '/api/v1';
  const token = localStorage.getItem('access_token') || localStorage.getItem('conversapay_auth_token') || sessionStorage.getItem('access_token') || sessionStorage.getItem('conversapay_auth_token');
  const defaultNames = new Set(['', 'my business', 'business', 'העסק שלי']);

  const authHeaders = () => token ? { Authorization: `Bearer ${token}` } : {};
  const isDefaultName = (value) => {
    const name = String(value || '').trim().toLowerCase();
    return defaultNames.has(name) || name.startsWith('העסק של ');
  };

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'לא ניתן להשלים את ההגדרה');
    return data;
  }

  function addStyles() {
    if (document.getElementById('businessOnboardingStyles')) return;
    const style = document.createElement('style');
    style.id = 'businessOnboardingStyles';
    style.textContent = `
      #businessOnboardingDialog{width:min(520px,calc(100% - 24px));padding:0;border:1px solid var(--cp-line);border-radius:24px;background:var(--cp-panel);color:var(--cp-text);box-shadow:0 24px 80px rgba(15,23,42,.2)}
      #businessOnboardingDialog::backdrop{background:rgba(15,23,42,.46)}
      .cp-onboarding{display:grid;gap:18px;padding:clamp(22px,5vw,36px)}
      .cp-onboarding h2{margin:0;font-size:clamp(1.6rem,4vw,2.2rem);letter-spacing:-.04em}
      .cp-onboarding p{margin:0}.cp-onboarding-field{display:grid;gap:8px}.cp-onboarding-field label{color:var(--cp-muted-strong);font-weight:700}
      .cp-onboarding-field input{width:100%;min-height:48px;padding:12px 14px;border:1px solid var(--cp-line-strong);border-radius:13px;background:var(--cp-bg);color:var(--cp-text);font:inherit}
      .cp-onboarding-field input:focus-visible{outline:3px solid var(--cp-focus);outline-offset:3px}
      .cp-onboarding-actions{display:grid;gap:10px}.cp-onboarding-error{min-height:24px;color:var(--cp-danger);font-weight:600}
      @media(min-width:520px){.cp-onboarding-actions{grid-template-columns:1fr 1fr}.cp-onboarding-actions .cp-button{grid-column:1/-1}}
    `;
    document.head.appendChild(style);
  }

  function buildDialog() {
    addStyles();
    const dialog = document.createElement('dialog');
    dialog.id = 'businessOnboardingDialog';
    dialog.innerHTML = `
      <form class="cp-onboarding" method="dialog" novalidate>
        <span class="cp-kicker">השלב האחרון</span>
        <div><h2>מה שם העסק שלך?</h2><p class="cp-muted">נשתמש בשם הזה בדאשבורד, בקישורי התשלום ובהטמעות שלך.</p></div>
        <div class="cp-onboarding-field"><label for="businessOnboardingName">שם העסק</label><input id="businessOnboardingName" name="business_name" maxlength="255" autocomplete="organization" required></div>
        <div id="businessOnboardingError" class="cp-onboarding-error" role="alert" aria-live="polite"></div>
        <div class="cp-onboarding-actions"><button class="cp-button" id="businessOnboardingSubmit" value="save" type="submit">שמור והמשך</button></div>
      </form>
    `;
    dialog.addEventListener('cancel', (event) => event.preventDefault());
    document.body.appendChild(dialog);
    return dialog;
  }

  async function saveBusiness(dialog, business) {
    const form = dialog.querySelector('form');
    const input = dialog.querySelector('#businessOnboardingName');
    const error = dialog.querySelector('#businessOnboardingError');
    const button = dialog.querySelector('#businessOnboardingSubmit');
    const name = input.value.trim();
    if (name.length < 2) {
      error.textContent = 'נא להזין שם עסק באורך של 2 תווים לפחות.';
      input.focus();
      return;
    }

    button.disabled = true;
    button.textContent = 'שומר...';
    error.textContent = '';
    try {
      if (business?.id) {
        await api(`/businesses/${encodeURIComponent(business.id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ business_name: name })
        });
      } else {
        const slug = `business_${crypto.randomUUID ? crypto.randomUUID().replaceAll('-', '').slice(0, 20) : Date.now()}`;
        await api('/businesses', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ business_id: slug, business_name: name, description: `עסק של ${name}` })
        });
      }
      dialog.close('saved');
      window.location.reload();
    } catch (saveError) {
      error.textContent = saveError.message || 'לא ניתן לשמור את שם העסק';
      button.disabled = false;
      button.textContent = 'שמור והמשך';
    }
    form.addEventListener('submit', (event) => event.preventDefault(), { once: true });
  }

  async function init() {
    if (!token || document.getElementById('businessOnboardingDialog')) return;
    try {
      const [me, businesses] = await Promise.all([api('/auth/me'), api('/businesses')]);
      const rows = Array.isArray(businesses) ? businesses : [];
      const business = rows.find((row) => !isDefaultName(row.business_name)) || rows[0] || null;
      if (!me.requires_business_onboarding && !isDefaultName(business?.business_name)) return;
      const dialog = buildDialog();
      dialog.querySelector('form').addEventListener('submit', (event) => {
        event.preventDefault();
        saveBusiness(dialog, business);
      });
      dialog.showModal();
      dialog.querySelector('#businessOnboardingName').focus();
    } catch (error) {
      console.warn('[ConversaPay] business onboarding check failed', error);
    }
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
