/**
 * ConversaPay AI Chat Widget
 * Usage: <script src="https://app.example.com/frontend/js/widget.js" data-business-id="UUID" defer></script>
 */
(function () {
  'use strict';

  const CONFIG = {
    API_BASE_URL: '',
    BUSINESS_ID: null,
    WIDGET_ID: 'conversapay-chat-widget',
    WINDOW_ID: 'conversapay-chat-window',
    TOGGLE_ID: 'conversapay-chat-toggle',
  };
  let currentSessionId = null;

  function validBusinessId(value) {
    return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  }

  function getScript() {
    return document.currentScript || document.querySelector('script[src*="widget.js"]');
  }

  function resolveApiOrigin(script) {
    // The widget runs on a merchant's domain, but its API must always be the
    // domain that served widget.js, never window.location.origin.
    try {
      return new URL(script.src, window.location.href).origin;
    } catch (_) {
      return window.location.origin;
    }
  }

  function getOrCreateSessionId() {
    const key = `conversapay_session_${CONFIG.BUSINESS_ID}`;
    const stored = localStorage.getItem(key);
    if (stored) return stored;
    const id = `session_${Date.now()}_${crypto.getRandomValues(new Uint32Array(1))[0].toString(36)}`;
    localStorage.setItem(key, id);
    return id;
  }

  function escapeHtml(value) {
    const el = document.createElement('div');
    el.textContent = String(value || '');
    return el.innerHTML;
  }

  function injectStyles() {
    if (document.getElementById('conversapay-widget-styles')) return;
    const style = document.createElement('style');
    style.id = 'conversapay-widget-styles';
    style.textContent = `
      #conversapay-chat-widget{font-family:system-ui,sans-serif;position:fixed;bottom:20px;left:20px;z-index:99999;direction:rtl}
      .cp-toggle{width:60px;height:60px;border:0;border-radius:50%;background:linear-gradient(135deg,#A855F7,#3B82F6);color:#fff;font-size:24px;cursor:pointer;box-shadow:0 4px 20px rgba(168,85,247,.4)}
      .cp-window{display:none;position:absolute;bottom:75px;left:0;width:380px;max-width:calc(100vw - 40px);height:550px;max-height:calc(100vh - 110px);flex-direction:column;overflow:hidden;border:1px solid #334155;border-radius:18px;background:#0B0F19;color:#f9fafb;box-shadow:0 10px 40px rgba(0,0,0,.5)}
      .cp-window.open{display:flex}.cp-header{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;background:#172033}.cp-header button{border:0;background:transparent;color:#fff;font-size:20px;cursor:pointer}.cp-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}.cp-message{max-width:80%;padding:10px 14px;border-radius:14px;white-space:pre-wrap;overflow-wrap:anywhere}.cp-message.user{align-self:flex-start;background:#5b217d}.cp-message.bot{align-self:flex-end;background:#1e3a5f}.cp-input{display:flex;gap:8px;padding:12px;border-top:1px solid #334155}.cp-input input{min-width:0;flex:1;border:1px solid #475569;border-radius:9px;background:#111827;color:#fff;padding:10px}.cp-input button{border:0;border-radius:9px;background:#A855F7;color:#fff;padding:10px 14px;cursor:pointer}
    `;
    document.head.appendChild(style);
  }

  function appendMessage(text, sender) {
    const list = document.getElementById('cpMessages');
    if (!list) return;
    const item = document.createElement('div');
    item.className = `cp-message ${sender}`;
    // Never use innerHTML for model or customer output.
    item.textContent = String(text || '');
    list.appendChild(item);
    list.scrollTop = list.scrollHeight;
  }

  function appendPaymentLink(url) {
    const list = document.getElementById('cpMessages');
    if (!list) return;
    try {
      const linkUrl = new URL(url, CONFIG.API_BASE_URL);
      if (!['https:', 'http:'].includes(linkUrl.protocol)) return;
      const item = document.createElement('div');
      item.className = 'cp-message bot';
      const link = document.createElement('a');
      link.href = linkUrl.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = '💳 לחץ כאן לתשלום';
      link.style.color = '#67e8f9';
      item.appendChild(link);
      list.appendChild(item);
      list.scrollTop = list.scrollHeight;
    } catch (_) { /* Ignore malformed URLs from upstream services. */ }
  }

  function setTyping(show) {
    const existing = document.getElementById('cpTyping');
    if (existing) existing.remove();
    if (show) {
      const item = document.createElement('div');
      item.id = 'cpTyping'; item.className = 'cp-message bot'; item.textContent = 'מקליד...';
      document.getElementById('cpMessages').appendChild(item);
    }
  }

  function injectWidget(config) {
    if (document.getElementById(CONFIG.WIDGET_ID)) return;
    injectStyles();
    const root = document.createElement('div');
    root.id = CONFIG.WIDGET_ID;
    root.innerHTML = `<button id="${CONFIG.TOGGLE_ID}" class="cp-toggle" aria-label="פתח צ׳אט">💬</button><section id="${CONFIG.WINDOW_ID}" class="cp-window" aria-live="polite"><header class="cp-header"><strong>${escapeHtml(config.bot_name || 'נציג ConversaPay')}</strong><button type="button" aria-label="סגור">×</button></header><div id="cpMessages" class="cp-messages"></div><div class="cp-input"><input id="cpChatInput" type="text" maxlength="2000" placeholder="הקלד הודעה..."><button id="cpSend" type="button">שלח</button></div></section>`;
    document.body.appendChild(root);
    const panel = document.getElementById(CONFIG.WINDOW_ID);
    document.getElementById(CONFIG.TOGGLE_ID).onclick = () => panel.classList.toggle('open');
    panel.querySelector('.cp-header button').onclick = () => panel.classList.remove('open');
    document.getElementById('cpSend').onclick = sendMessage;
    document.getElementById('cpChatInput').addEventListener('keydown', event => { if (event.key === 'Enter') sendMessage(); });
  }

  async function loadWidgetConfig() {
    const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1/widget/config/${encodeURIComponent(CONFIG.BUSINESS_ID)}`, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Widget configuration failed (${response.status})`);
    injectWidget(await response.json());
  }

  async function sendMessage() {
    const input = document.getElementById('cpChatInput');
    const message = input && input.value.trim();
    if (!message || !CONFIG.BUSINESS_ID) return;
    appendMessage(message, 'user');
    input.value = '';
    setTyping(true);
    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, business_id: CONFIG.BUSINESS_ID, session_id: currentSessionId, customer_info: window.ConversaPayWidget.customerInfo || {} }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (data.session_id) {
        currentSessionId = data.session_id;
        localStorage.setItem(`conversapay_session_${CONFIG.BUSINESS_ID}`, currentSessionId);
      }
      appendMessage(data.response || 'הבנתי, אבל אין לי תשובה כרגע.', 'bot');
      if (data.intent === 'checkout' && data.payment_url) appendPaymentLink(data.payment_url);
    } catch (_) {
      appendMessage('שגיאה בתקשורת עם השרת. נסה שוב.', 'bot');
    } finally {
      setTyping(false);
    }
  }

  async function init() {
    const script = getScript();
    CONFIG.API_BASE_URL = resolveApiOrigin(script || {});
    CONFIG.BUSINESS_ID = (window.ConversaPayWidgetConfig && window.ConversaPayWidgetConfig.business_id) || (script && script.getAttribute('data-business-id')) || window.currentBusinessId;
    if (!validBusinessId(CONFIG.BUSINESS_ID)) return;
    currentSessionId = getOrCreateSessionId();
    try { await loadWidgetConfig(); } catch (error) { console.error('ConversaPay Widget:', error); }
  }

  window.ConversaPayWidget = { open: () => document.getElementById(CONFIG.WINDOW_ID)?.classList.add('open'), close: () => document.getElementById(CONFIG.WINDOW_ID)?.classList.remove('open'), sendMessage, customerInfo: {} };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
}());
