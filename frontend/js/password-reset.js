/* Recovery sessions are kept in this page and passed explicitly to the API. */
(() => {
  'use strict';
  const API = '/api/v1';
  const $ = id => document.getElementById(id);
  const query = new URLSearchParams(location.search);
  const fragment = new URLSearchParams(location.hash.slice(1));
  let recoveryToken = null;
  let ready = false;
  function note(message, error = false) {
    $('notice').textContent = message;
    $('notice').className = error ? 'cp-notice error' : 'cp-notice';
    $('notice').hidden = false;
  }
  async function initializeRecovery() {
    const hasRecovery = fragment.get('type') === 'recovery' || query.has('code') || query.get('type') === 'recovery';
    if (!hasRecovery) return;
    $('request').hidden = true;
    $('reset').hidden = false;
    const button = $('resetForm').querySelector('button');
    button.disabled = true;
    // Capture the parameters above before removing secrets from the address bar.
    history.replaceState({}, document.title, '/forgot-password');
    try {
      const response = await fetch(`${API}/config/public`);
      if (!response.ok) throw new Error('configuration');
      const config = await response.json();
      const client = window.supabase.createClient(config.supabase_url, config.supabase_anon_key, {
        auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
      });
      let result;
      if (fragment.get('access_token') && fragment.get('refresh_token')) {
        result = await client.auth.setSession({ access_token: fragment.get('access_token'), refresh_token: fragment.get('refresh_token') });
      } else if (query.get('token_hash') && query.get('type') === 'recovery') {
        result = await client.auth.verifyOtp({ token_hash: query.get('token_hash'), type: 'recovery' });
      } else if (query.get('code')) {
        result = await client.auth.exchangeCodeForSession(query.get('code'));
      } else {
        throw new Error('missing recovery session');
      }
      if (result.error || !result.data?.session?.access_token) throw new Error('invalid recovery session');
      recoveryToken = result.data.session.access_token;
      ready = true;
      button.disabled = false;
    } catch (_) {
      note('קישור האיפוס פג או אינו תקין. בקש קישור חדש.', true);
      $('request').hidden = false;
      $('reset').hidden = true;
    }
  }
  $('requestForm').onsubmit = async event => {
    event.preventDefault();
    const button = event.target.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(`${API}/auth/password-reset/request`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: $('email').value.trim() }),
      });
      if (!response.ok) throw new Error('request');
      note('אם קיים חשבון, נשלח אליו קישור איפוס. בדוק את תיבת הדואר.');
    } catch (_) { note('לא ניתן לשלוח את הקישור כרגע.', true); }
    finally { button.disabled = false; }
  };
  $('resetForm').onsubmit = async event => {
    event.preventDefault();
    const password = $('password').value;
    if (!ready || !recoveryToken) return note('נדרש קישור איפוס תקף.', true);
    if (password.length < 8 || password !== $('confirm').value) return note('הסיסמה חייבת להכיל 8 תווים ולהיות זהה באימות.', true);
    const button = event.target.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(`${API}/auth/password-reset/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: recoveryToken, new_password: password }),
      });
      if (!response.ok) throw new Error('reset');
      recoveryToken = null;
      ready = false;
      note('הסיסמה עודכנה. מעביר לכניסה...');
      setTimeout(() => location.replace('/login'), 1800);
    } catch (_) { note('קישור האיפוס פג או אינו תקין. בקש קישור חדש.', true); button.disabled = false; }
  };
  initializeRecovery();
})();
