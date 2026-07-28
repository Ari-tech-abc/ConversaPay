(function () {
  'use strict';

  const ROOT = 'conversapay-chat-widget';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const script = () => document.currentScript || document.querySelector('script[src*="widget.js"]');
  const source = script();
  const origin = source ? new URL(source.src, window.location.href).origin : window.location.origin;
  const config = window.ConversaPayWidgetConfig || {};
  const businessId = config.business_id || source?.dataset.businessId;
  const apiKey = config.api_key || source?.dataset.apiKey || '';
  const position = config.position || source?.dataset.position || 'bottom-right';
  const color = config.color || source?.dataset.color || '#635bff';
  let sessionId;

  const escapeText = (value) => String(value ?? '');
  const session = () => {
    const key = `cp_session_${businessId}`;
    let value = localStorage.getItem(key);
    if (!value) {
      value = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(key, value);
    }
    return value;
  };
  const addMessage = (text, kind) => {
    const messages = document.getElementById('cpMessages');
    if (!messages) return;
    const item = document.createElement('div');
    item.className = `cp-message ${kind}`;
    item.setAttribute('role', 'listitem');
    item.textContent = escapeText(text);
    messages.appendChild(item);
    messages.scrollTop = messages.scrollHeight;
  };

  function inject(widget) {
    if (document.getElementById(ROOT)) return;
    const style = document.createElement('style');
    style.textContent = `
      #${ROOT}{--cp-widget-color:${color};position:fixed;${position === 'bottom-left' ? 'left:18px' : 'right:18px'};bottom:max(18px,env(safe-area-inset-bottom));z-index:99999;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;direction:rtl}
      #${ROOT} *{box-sizing:border-box} .cp-toggle{width:58px;height:58px;border:0;border-radius:50%;background:var(--cp-widget-color);color:#fff;font-size:22px;cursor:pointer;box-shadow:0 12px 32px color-mix(in srgb,var(--cp-widget-color),transparent 60%);transition:transform .2s ease,filter .2s ease}
      .cp-toggle:hover{transform:translateY(-2px);filter:brightness(1.08)} .cp-toggle:focus-visible,.cp-input input:focus-visible,.cp-input button:focus-visible,.cp-head button:focus-visible{outline:3px solid #fff;outline-offset:3px}
      .cp-window{display:none;position:absolute;bottom:72px;${position === 'bottom-left' ? 'left:0' : 'right:0'};width:360px;height:min(520px,calc(100dvh - 110px));max-width:calc(100vw - 28px);background:#17202d;color:#f5f7fa;border:1px solid #ffffff22;border-radius:20px;overflow:hidden;flex-direction:column;box-shadow:0 24px 70px #0008}
      .cp-window.open{display:flex;animation:cp-in .22s cubic-bezier(.16,1,.3,1)} .cp-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:15px 16px;background:#242d3b}.cp-head button{background:none;border:0;color:#fff;font-size:22px;cursor:pointer;min-width:44px;min-height:44px}
      .cp-messages{flex:1;overflow:auto;padding:15px;display:flex;flex-direction:column;gap:9px;scroll-behavior:smooth}.cp-message{max-width:82%;padding:10px 13px;border-radius:14px;white-space:pre-wrap;line-height:1.45}.cp-message.user{align-self:flex-start;background:#4d3aa4}.cp-message.bot{align-self:flex-end;background:#263c56}
      .cp-input{display:flex;gap:8px;padding:12px;border-top:1px solid #ffffff18;background:#121a25}.cp-input input{min-width:0;flex:1;padding:11px 12px;border-radius:10px;border:1px solid #ffffff22;background:#0f1419;color:#fff;font-size:16px}.cp-input button{border:0;border-radius:10px;background:var(--cp-widget-color);color:#fff;padding:10px 14px;cursor:pointer;font-weight:700;min-width:64px}
      @keyframes cp-in{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}} @media(max-width:480px){#${ROOT}{right:10px;left:10px;bottom:max(10px,env(safe-area-inset-bottom));display:flex;justify-content:flex-end}.cp-window{position:fixed;inset:auto 10px max(78px,calc(env(safe-area-inset-bottom) + 68px));width:auto;max-width:none;height:min(620px,calc(100dvh - 100px))}}
    `;
    document.head.appendChild(style);
    const root = document.createElement('div');
    root.id = ROOT;
    root.innerHTML = `<button class="cp-toggle" type="button" aria-label="פתח צ׳אט" aria-expanded="false">💬</button><section class="cp-window" role="dialog" aria-label="צ׳אט עם Talk2Pay"><header class="cp-head"><strong></strong><button type="button" aria-label="סגור צ׳אט">×</button></header><div id="cpMessages" class="cp-messages" role="list" aria-live="polite"></div><form class="cp-input"><input id="cpInput" maxlength="2000" autocomplete="off" placeholder="הקלד הודעה..." aria-label="הודעה"><button id="cpSend" type="submit">שלח</button></form></section>`;
    document.body.appendChild(root);
    root.querySelector('.cp-head strong').textContent = widget.bot_name || 'נציג Talk2Pay';
    const win = root.querySelector('.cp-window');
    const toggle = root.querySelector('.cp-toggle');
    const setOpen = (open) => { win.classList.toggle('open', open); toggle.setAttribute('aria-expanded', String(open)); if (open) root.querySelector('#cpInput').focus(); };
    toggle.addEventListener('click', () => setOpen(!win.classList.contains('open')));
    root.querySelector('.cp-head button').addEventListener('click', () => setOpen(false));
    root.querySelector('.cp-input').addEventListener('submit', (event) => { event.preventDefault(); send(); });
    addMessage(widget.greeting_message || 'שלום! איך אפשר לעזור?', 'bot');
  }

  async function send() {
    const input = document.getElementById('cpInput');
    const message = input?.value.trim();
    if (!message) return;
    addMessage(message, 'user');
    input.value = '';
    try {
      const response = await fetch(`${origin}/api/v1/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Widget-Key': apiKey }, body: JSON.stringify({ message, business_id: businessId, session_id: sessionId, customer_info: {} }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error('request failed');
      addMessage(data.response || 'לא הצלחתי לענות כרגע.', 'bot');
    } catch (_) { addMessage('שגיאה בתקשורת עם השרת. נסה שוב.', 'bot'); }
  }

  async function init() {
    if (!UUID.test(String(businessId || ''))) return;
    sessionId = session();
    const headers = { Accept: 'application/json' };
    if (apiKey) headers['X-Widget-Key'] = apiKey;
    try {
      const response = await fetch(`${origin}/api/v1/widget/config/${encodeURIComponent(businessId)}`, { headers });
      if (!response.ok) throw new Error('Widget access denied');
      inject(await response.json());
    } catch (error) { console.warn('[Talk2Pay] widget unavailable', error); }
  }

  window.Talk2PayWidget = window.ConversaPayWidget = { open: () => document.querySelector('.cp-window')?.classList.add('open'), close: () => document.querySelector('.cp-window')?.classList.remove('open') };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
}());
