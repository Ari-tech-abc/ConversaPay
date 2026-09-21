(() => {
  'use strict';
  const API = '/api/v1';
  const $ = id => document.getElementById(id);
  const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || localStorage.getItem('conversapay_auth_token') || sessionStorage.getItem('conversapay_auth_token');
  const lang = (localStorage.getItem('conversapay-language') || localStorage.getItem('talk2pay_language') || 'he') === 'en' ? 'en' : 'he';
  const tr = (he, en) => lang === 'en' ? en : he;
  let selected = '';

  function applyLanguage() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'en' ? 'ltr' : 'rtl';
    document.body.dir = lang === 'en' ? 'ltr' : 'rtl';
    document.querySelectorAll('[data-he][data-en]').forEach(el => {
      const value = el.dataset[lang];
      if (value != null) el.textContent = value;
    });
    document.querySelectorAll('[data-placeholder-he][data-placeholder-en]').forEach(el => {
      el.placeholder = lang === 'en' ? el.dataset.placeholderEn : el.dataset.placeholderHe;
    });
    document.querySelectorAll('[data-aria-he][data-aria-en]').forEach(el => {
      el.setAttribute('aria-label', lang === 'en' ? el.dataset.ariaEn : el.dataset.ariaHe);
    });
    document.title = tr('הגדרת העסק | Talk2Pay', 'Business setup | Talk2Pay');
  }

  function headers(extra = {}) { return { Authorization: 'Bearer ' + token, ...extra }; }
  function toast(text, type = 'error') {
    if (window.showSystemMessage) { window.showSystemMessage(text, type); return; }
    const layer = $('localMessageLayer'), textNode = $('localMessageText');
    if (!layer || !textNode) return;
    textNode.textContent = text;
    layer.classList.add('show');
  }
  function closeToast() { $('localMessageLayer')?.classList.remove('show'); }

  function choose(button) {
    selected = button.dataset.id || '';
    document.querySelectorAll('.category-card').forEach(card => {
      const active = card === button;
      card.classList.toggle('selected', active);
      card.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    $('toInstructions').disabled = !selected;
  }

  function restoreSelection() {
    if (!selected) return;
    const button = [...document.querySelectorAll('.category-card')].find(x => x.dataset.id === selected);
    if (button) choose(button);
  }

  function setStep(step) {
    $('step1').classList.toggle('on', step === 1);
    $('step2').classList.toggle('on', step === 2);
    $('dot1').classList.add('on');
    $('dot2').classList.toggle('on', step === 2);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function fetchWithTimeout(url, options = {}, ms = 7000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try { return await fetch(url, { ...options, signal: controller.signal }); }
    finally { clearTimeout(timer); }
  }

  async function loadSavedSettings() {
    const note = $('loadNote');
    if (!token) { location.replace('/login'); return; }
    try {
      const response = await fetchWithTimeout(API + '/auth/onboarding', { headers: headers() }, 7000);
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) { location.replace('/login'); return; }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : tr('לא ניתן לטעון את ההגדרות', 'Could not load settings'));
      if (data.completed) { location.replace('/dashboard'); return; }
      selected = data.business_category || selected;
      $('customInstructions').value = data.custom_ai_instructions || '';
      $('counter').textContent = $('customInstructions').value.length;
      restoreSelection();
      note.textContent = tr('ההגדרות הקיימות נטענו.', 'Existing settings loaded.');
      note.classList.remove('error');
      setTimeout(() => { if (note) note.hidden = true; }, 1600);
    } catch (error) {
      note.textContent = error?.name === 'AbortError'
        ? tr('הטעינה מתעכבת, אבל אפשר לבחור תחום ולהמשיך כרגיל.', 'Loading is taking longer, but you can choose a category and continue normally.')
        : tr('לא הצלחנו לטעון הגדרות קודמות, אבל אפשר להמשיך כרגיל.', 'We could not load previous settings, but you can continue normally.');
      note.classList.add('error');
    }
  }

  async function saveOnboarding() {
    if (!selected) { toast(tr('בחר תחום עיסוק לפני ההמשך.', 'Choose a business category before continuing.')); return; }
    const button = $('finish');
    button.disabled = true;
    const original = button.textContent;
    button.textContent = tr('שומר...', 'Saving...');
    try {
      const response = await fetchWithTimeout(API + '/auth/onboarding', {
        method: 'POST',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          business_category: selected,
          custom_ai_instructions: $('customInstructions').value.trim()
        })
      }, 10000);
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) { location.replace('/login'); return; }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : tr('שמירת ההגדרות נכשלה', 'Could not save settings'));
      $('upgradeLayer').classList.add('show');
    } catch (error) {
      toast(error?.name === 'AbortError'
        ? tr('שמירת ההגדרות ארכה יותר מדי. נסה שוב.', 'Saving took too long. Please try again.')
        : (error?.message || tr('שמירת ההגדרות נכשלה.', 'Could not save settings.')));
    } finally {
      button.disabled = false;
      button.textContent = original;
      applyLanguage();
    }
  }

  function logout() {
    ['access_token','conversapay_auth_token','conversapay_user','user_id','email'].forEach(key => {
      localStorage.removeItem(key); sessionStorage.removeItem(key);
    });
    location.replace('/login');
  }

  applyLanguage();
  document.querySelectorAll('.category-card').forEach(card => {
    card.setAttribute('aria-pressed', 'false');
    card.addEventListener('click', () => choose(card));
    const img = card.querySelector('img');
    if (img) img.addEventListener('error', () => {
      img.hidden = true;
      card.querySelector('.category-icon')?.classList.add('image-fallback');
    }, { once: true });
  });
  $('toInstructions').addEventListener('click', () => setStep(2));
  $('backToCategories').addEventListener('click', () => setStep(1));
  $('customInstructions').addEventListener('input', () => { $('counter').textContent = $('customInstructions').value.length; });
  $('finish').addEventListener('click', saveOnboarding);
  $('continueFree').addEventListener('click', () => location.replace('/dashboard'));
  $('upgradeClose').addEventListener('click', () => location.replace('/dashboard'));
  $('logout').addEventListener('click', logout);
  $('localMessageClose')?.addEventListener('click', closeToast);
  $('localMessageLayer')?.addEventListener('click', event => { if (event.target === $('localMessageLayer')) closeToast(); });
  loadSavedSettings();
})();
