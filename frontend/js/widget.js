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
  // Only used for the dashboard's authenticated "test your own widget"
  // preview — never set this on a real third-party embed, where the
  // widget API key is the correct credential.
  const authToken = config.auth_token || source?.dataset.authToken || '';
  const authHeader = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});
  const upgradeUrl = config.upgrade_url || source?.dataset.upgradeUrl || '';
  const position = config.position || source?.dataset.position || 'bottom-right';
  const fallbackColor = config.color || source?.dataset.color || '#635bff';
  const FREE_LIMIT = 5;
  let sessionId;
  let unreadCount = 0;
  let sending = false;
  let msgCount = 0;
  let limitReached = false;

  const escapeText = (value) => String(value ?? '');

  // Defense-in-depth: payment_url should always be a real Stripe/Cardcom
  // checkout link from the backend, but never trust it blindly before
  // wiring it to an href — this blocks javascript:/data: etc.
  const isValidPaymentUrl = (url) => {
    if (!url) return false;
    if (url.startsWith('/')) return true;
    try {
      const parsed = new URL(url, window.location.href);
      return parsed.protocol === 'https:' || parsed.protocol === 'http:';
    } catch {
      return false;
    }
  };
  const session = () => {
    const key = `cp_session_${businessId}`;
    let value = localStorage.getItem(key);
    if (!value) {
      value = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(key, value);
    }
    return value;
  };

  function scrollToBottom() {
    const messages = document.getElementById('cpMessages');
    if (messages) messages.scrollTop = messages.scrollHeight;
  }

  // Plain textContent everywhere below — never innerHTML with server/user data.
  const addMessage = (text, kind) => {
    const messages = document.getElementById('cpMessages');
    if (!messages) return null;
    const item = document.createElement('div');
    item.className = `cp-message ${kind}`;
    item.setAttribute('role', 'listitem');
    item.textContent = escapeText(text);
    messages.appendChild(item);
    scrollToBottom();
    return item;
  };

  // Renders the checkout action as its own card instead of dropping it.
  const addCheckoutCard = (paymentUrl, actionData) => {
    const messages = document.getElementById('cpMessages');
    if (!messages || !isValidPaymentUrl(paymentUrl)) return;
    const card = document.createElement('div');
    card.className = 'cp-message bot cp-checkout-card';
    card.setAttribute('role', 'listitem');

    const title = document.createElement('div');
    title.className = 'cp-checkout-title';
    title.textContent = actionData?.order_number ? `\u05d4\u05d6\u05de\u05e0\u05d4 ${actionData.order_number}` : '\u05d4\u05d4\u05d6\u05de\u05e0\u05d4 \u05de\u05d5\u05db\u05e0\u05d4 \u05dc\u05ea\u05e9\u05dc\u05d5\u05dd';
    card.appendChild(title);

    if (actionData?.quantity) {
      const meta = document.createElement('div');
      meta.className = 'cp-checkout-meta';
      meta.textContent = `\u05db\u05de\u05d5\u05ea: ${escapeText(actionData.quantity)}`;
      card.appendChild(meta);
    }

    const link = document.createElement('a');
    link.className = 'cp-checkout-btn';
    link.href = paymentUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = '\u05d4\u05de\u05e9\u05da \u05dc\u05ea\u05e9\u05dc\u05d5\u05dd \u05de\u05d0\u05d5\u05d1\u05d8\u05d7 \u2192';
    card.appendChild(link);

    messages.appendChild(card);
    scrollToBottom();
  };

  function addUpgradeCard() {
    const messages = document.getElementById('cpMessages');
    if (!messages) return;
    const input = document.getElementById('cpInput');
    const button = document.getElementById('cpSend');
    if (input) { input.disabled = true; input.placeholder = '\u05e0\u05d2\u05de\u05e8\u05d5 \u05d4\u05d4\u05d5\u05d3\u05e2\u05d5\u05ea \u05d4\u05d7\u05d9\u05e0\u05de\u05d9\u05d5\u05ea'; }
    if (button) button.disabled = true;
    const card = document.createElement('div');
    card.className = 'cp-message bot cp-upgrade-card';
    card.setAttribute('role', 'listitem');
    const title = document.createElement('div');
    title.className = 'cp-upgrade-title';
    title.textContent = '\u05e0\u05d2\u05de\u05e8\u05d5 \u05dc\u05da 5 \u05d4\u05d4\u05d5\u05d3\u05e2\u05d5\u05ea \u05d4\u05d7\u05d9\u05e0\u05de\u05d9\u05d5\u05ea \u05dc\u05e9\u05e2\u05d4 \u05d6\u05d5 \ud83d\udd12';
    const desc = document.createElement('div');
    desc.className = 'cp-upgrade-desc';
    desc.textContent = '\u05e9\u05d3\u05e8\u05d2 \u05dc-PRO \u05dc\u05e9\u05d9\u05d7\u05d5\u05ea \u05d1\u05dc\u05ea\u05d9 \u05de\u05d5\u05d2\u05d1\u05dc\u05d5\u05ea, \u05d0\u05d5 \u05d7\u05db\u05d4 \u05e9\u05e2\u05d4 \u05d5\u05e0\u05e1\u05d4 \u05e9\u05d5\u05d1.';
    card.appendChild(title);
    card.appendChild(desc);
    if (upgradeUrl) {
      const link = document.createElement('a');
      link.className = 'cp-upgrade-btn';
      link.href = upgradeUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = '\u05e9\u05d3\u05e8\u05d2 \u05dc-PRO \u2192';
      card.appendChild(link);
    }
    messages.appendChild(card);
    scrollToBottom();
  }

  const showTyping = () => {
    if (document.getElementById('cpTyping')) return;
    const messages = document.getElementById('cpMessages');
    if (!messages) return;
    const el = document.createElement('div');
    el.id = 'cpTyping';
    el.className = 'cp-message bot cp-typing';
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML = '<span></span><span></span><span></span>'; // static markup only, no data
    messages.appendChild(el);
    scrollToBottom();
  };
  const hideTyping = () => document.getElementById('cpTyping')?.remove();

  const setUnread = (n) => {
    unreadCount = n;
    const badge = document.getElementById('cpBadge');
    if (!badge) return;
    if (unreadCount > 0) {
      badge.textContent = unreadCount > 9 ? '9+' : String(unreadCount);
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  };

  function applyTheme(themeColors) {
    const root = document.getElementById(ROOT);
    if (!root || !themeColors) return;
    if (themeColors.primary) root.style.setProperty('--cp-widget-color', themeColors.primary);
    if (themeColors.secondary) root.style.setProperty('--cp-widget-accent', themeColors.secondary);
    if (themeColors.background) root.style.setProperty('--cp-widget-bg', themeColors.background);
  }

  function inject(widget) {
    if (document.getElementById(ROOT)) return;
    const style = document.createElement('style');
    style.textContent = `
      #${ROOT}{--cp-widget-color:${fallbackColor};--cp-widget-accent:${fallbackColor};--cp-widget-bg:#17202d;position:fixed;${position === 'bottom-left' ? 'left:18px' : 'right:18px'};bottom:max(18px,env(safe-area-inset-bottom));z-index:99999;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;direction:rtl}
      #${ROOT} *{box-sizing:border-box}
      .cp-toggle{position:relative;width:58px;height:58px;border:0;border-radius:50%;background:var(--cp-widget-color);color:#fff;cursor:pointer;box-shadow:0 12px 32px color-mix(in srgb,var(--cp-widget-color),transparent 60%);transition:transform .2s ease,filter .2s ease;display:grid;place-items:center}
      .cp-toggle:hover{transform:translateY(-2px);filter:brightness(1.08)}
      .cp-toggle svg{width:26px;height:26px}
      .cp-toggle:focus-visible,.cp-input input:focus-visible,.cp-input button:focus-visible,.cp-head button:focus-visible{outline:3px solid #fff;outline-offset:3px}
      .cp-badge{position:absolute;top:-2px;${position === 'bottom-left' ? 'left:-2px' : 'right:-2px'};min-width:20px;height:20px;padding:0 5px;border-radius:10px;background:#ef4444;color:#fff;font-size:11px;font-weight:800;display:grid;place-items:center;border:2px solid #fff}
      .cp-window{display:none;position:absolute;bottom:72px;${position === 'bottom-left' ? 'left:0' : 'right:0'};width:360px;height:min(520px,calc(100dvh - 110px));max-width:calc(100vw - 28px);background:var(--cp-widget-bg);color:#f5f7fa;border:1px solid #ffffff22;border-radius:20px;overflow:hidden;flex-direction:column;box-shadow:0 24px 70px #0008}
      .cp-window.open{display:flex;animation:cp-in .22s cubic-bezier(.16,1,.3,1)}
      .cp-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:15px 16px;background:color-mix(in srgb,var(--cp-widget-bg),#fff 8%)}
      .cp-head-info{display:flex;align-items:center;gap:10px;min-width:0}
      .cp-avatar{width:34px;height:34px;border-radius:50%;background:var(--cp-widget-color);color:#fff;display:grid;place-items:center;font-weight:800;font-size:14px;flex-shrink:0}
      .cp-head-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .cp-head button{background:none;border:0;color:#fff;font-size:22px;cursor:pointer;min-width:44px;min-height:44px}
      .cp-messages{flex:1;overflow:auto;padding:15px;display:flex;flex-direction:column;gap:9px;scroll-behavior:smooth}
      .cp-message{max-width:82%;padding:10px 13px;border-radius:14px;white-space:pre-wrap;line-height:1.45}
      .cp-message.user{align-self:flex-start;background:var(--cp-widget-accent)}
      .cp-message.bot{align-self:flex-end;background:#263c56}
      .cp-typing{display:flex;gap:4px;align-items:center;padding:12px 14px}
      .cp-typing span{width:6px;height:6px;border-radius:50%;background:#9fb0c4;animation:cp-bounce 1.1s infinite}
      .cp-typing span:nth-child(2){animation-delay:.15s}.cp-typing span:nth-child(3){animation-delay:.3s}
      @keyframes cp-bounce{0%,60%,100%{transform:translateY(0);opacity:.5}30%{transform:translateY(-4px);opacity:1}}
      .cp-checkout-card{background:color-mix(in srgb,var(--cp-widget-color),#000 55%);border:1px solid color-mix(in srgb,var(--cp-widget-color),#fff 20%)}
      .cp-checkout-title{font-weight:800;margin-bottom:4px}
      .cp-checkout-meta{font-size:.85rem;opacity:.8;margin-bottom:10px}
      .cp-checkout-btn{display:block;text-align:center;padding:10px 12px;border-radius:10px;background:#fff;color:color-mix(in srgb,var(--cp-widget-color),#000 20%);font-weight:800;text-decoration:none}
      .cp-upgrade-card{background:linear-gradient(135deg,#1a1040,#0f2040);border:1px solid #7c5cfc55;max-width:92%}
      .cp-upgrade-title{font-weight:800;font-size:.95rem;margin-bottom:6px}
      .cp-upgrade-desc{font-size:.82rem;opacity:.8;margin-bottom:10px;line-height:1.5}
      .cp-upgrade-btn{display:block;text-align:center;padding:9px 12px;border-radius:10px;background:linear-gradient(135deg,#7c5cfc,#22d3ee);color:#fff;font-weight:800;text-decoration:none;font-size:.88rem}
      .cp-input{display:flex;gap:8px;padding:12px;border-top:1px solid #ffffff18;background:color-mix(in srgb,var(--cp-widget-bg),#000 10%)}
      .cp-input input{min-width:0;flex:1;padding:11px 12px;border-radius:10px;border:1px solid #ffffff22;background:#0f1419;color:#fff;font-size:16px}
      .cp-input input:disabled{opacity:.6}
      .cp-input button{border:0;border-radius:10px;background:var(--cp-widget-color);color:#fff;padding:10px 14px;cursor:pointer;font-weight:700;min-width:64px;display:grid;place-items:center}
      .cp-input button:disabled{opacity:.6;cursor:not-allowed}
      .cp-spin{width:16px;height:16px;border-radius:50%;border:2px solid #ffffff55;border-top-color:#fff;animation:cp-spin .7s linear infinite}
      @keyframes cp-spin{to{transform:rotate(360deg)}}
      @keyframes cp-in{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}
      @media(max-width:480px){#${ROOT}{right:10px;left:10px;bottom:max(10px,env(safe-area-inset-bottom));display:flex;justify-content:flex-end}.cp-window{position:fixed;inset:auto 10px max(78px,calc(env(safe-area-inset-bottom) + 68px));width:auto;max-width:none;height:min(620px,calc(100dvh - 100px))}}
      @media(prefers-reduced-motion:reduce){.cp-toggle,.cp-window.open,.cp-typing span,.cp-spin{animation:none!important}}
    `;
    document.head.appendChild(style);

    const root = document.createElement('div');
    root.id = ROOT;
    root.innerHTML = `<button class="cp-toggle" type="button" aria-label="\u05e4\u05ea\u05d7 \u05e6\u05f3\u05d0\u05d8" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span id="cpBadge" class="cp-badge" hidden></span></button><section class="cp-window" role="dialog" aria-label="\u05e6\u05f3\u05d0\u05d8"><header class="cp-head"><div class="cp-head-info"><span class="cp-avatar" id="cpAvatar"></span><strong class="cp-head-title" id="cpTitle"></strong></div><button type="button" aria-label="\u05e1\u05d2\u05d5\u05e8 \u05e6\u05f3\u05d0\u05d8">\xd7</button></header><div id="cpMessages" class="cp-messages" role="list" aria-live="polite"></div><form class="cp-input"><input id="cpInput" maxlength="2000" autocomplete="off" placeholder="\u05d4\u05e7\u05dc\u05d3 \u05d4\u05d5\u05d3\u05e2\u05d4..." aria-label="\u05d4\u05d5\u05d3\u05e2\u05d4"><button id="cpSend" type="submit"><span id="cpSendLabel">\u05e9\u05dc\u05d7</span></button></form></section>`;
    document.body.appendChild(root);

    applyTheme(widget.theme_colors);
    const botName = widget.bot_name || '\u05e0\u05e6\u05d9\u05d2 ConversaPay';
    root.querySelector('#cpTitle').textContent = botName;
    root.querySelector('#cpAvatar').textContent = botName.trim().charAt(0).toUpperCase();

    const win = root.querySelector('.cp-window');
    const toggle = root.querySelector('.cp-toggle');
    const setOpen = (open) => {
      win.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', String(open));
      if (open) { root.querySelector('#cpInput').focus(); setUnread(0); }
    };
    toggle.addEventListener('click', () => setOpen(!win.classList.contains('open')));
    root.querySelector('.cp-head button').addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && win.classList.contains('open')) setOpen(false); });
    root.querySelector('.cp-input').addEventListener('submit', (event) => { event.preventDefault(); send(); });

    addMessage(widget.greeting_message || '\u05e9\u05dc\u05d5\u05dd! \u05d0\u05d9\u05da \u05d0\u05e4\u05e9\u05e8 \u05dc\u05e2\u05d6\u05d5\u05e8?', 'bot');
    if (!win.classList.contains('open')) setUnread(1);
  }

  function setSending(isSending) {
    sending = isSending;
    const input = document.getElementById('cpInput');
    const button = document.getElementById('cpSend');
    const label = document.getElementById('cpSendLabel');
    if (!input || !button || !label) return;
    if (!limitReached) input.disabled = isSending;
    button.disabled = isSending || limitReached;
    label.innerHTML = ''; // static toggle only, no interpolated data
    if (isSending) {
      const spinner = document.createElement('span');
      spinner.className = 'cp-spin';
      label.appendChild(spinner);
    } else {
      label.textContent = '\u05e9\u05dc\u05d7';
    }
  }

  function friendlyError(status) {
    if (status === 401 || status === 403) return '\u05d0\u05d9\u05df \u05db\u05e8\u05d2\u05e2 \u05d4\u05e8\u05e9\u05d0\u05d4 \u05dc\u05e9\u05d5\u05d7\u05d5\u05d7 \u05e2\u05dd \u05d4\u05e2\u05e1\u05e7 \u05d4\u05d6\u05d4.';
    if (status === 404) return '\u05d4\u05e2\u05e1\u05e7 \u05dc\u05d0 \u05e0\u05de\u05e6\u05d0.';
    return '\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05ea\u05e7\u05e9\u05d5\u05e8\u05ea \u05e2\u05dd \u05d4\u05e9\u05e8\u05ea. \u05e0\u05e1\u05d4 \u05e9\u05d5\u05d1.';
  }

  async function send() {
    if (sending || limitReached) return;
    const input = document.getElementById('cpInput');
    const message = input?.value.trim();
    if (!message) return;
    addMessage(message, 'user');
    input.value = '';
    setSending(true);
    showTyping();
    try {
      const response = await fetch(`${origin}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Widget-Key': apiKey, ...authHeader() },
        body: JSON.stringify({ message, business_id: businessId, session_id: sessionId, customer_info: {} }),
      });
      const data = await response.json().catch(() => ({}));
      hideTyping();
      if (response.status === 429 || data?.error === 'free_limit_reached') {
        limitReached = true;
        addUpgradeCard();
        return;
      }
      if (!response.ok) {
        addMessage(friendlyError(response.status), 'bot');
        return;
      }
      msgCount++;
      const wasClosed = !document.querySelector('.cp-window.open');
      addMessage(data.response || '\u05dc\u05d0 \u05d4\u05e6\u05dc\u05d7\u05ea\u05d9 \u05dc\u05e2\u05e0\u05d5\u05ea \u05db\u05e8\u05d2\u05e2.', 'bot');
      if (msgCount === FREE_LIMIT - 1) {
        addMessage('\u05e9\u05d9\u05dd \u05dc\u05d1: \u05e0\u05d5\u05ea\u05e8\u05ea \u05dc\u05da \u05e2\u05d5\u05d3 \u05d4\u05d5\u05d3\u05e2\u05d4 \u05d0\u05d7\u05ea \u05d1\u05e9\u05e2\u05d4 \u05d6\u05d5. \u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d7\u05d5\u05db\u05de\u05d4 \ud83d\ude4f', 'bot');
      }
      if (data.payment_url) addCheckoutCard(data.payment_url, data.action_data);
      if (wasClosed) setUnread(unreadCount + 1);
    } catch (_) {
      hideTyping();
      addMessage(friendlyError(), 'bot');
    } finally {
      setSending(false);
    }
  }

  async function init() {
    if (!UUID.test(String(businessId || ''))) return;
    sessionId = session();
    const headers = { Accept: 'application/json', ...authHeader() };
    if (apiKey) headers['X-Widget-Key'] = apiKey;
    try {
      const response = await fetch(`${origin}/api/v1/widget/config/${encodeURIComponent(businessId)}`, { headers });
      if (!response.ok) throw new Error('Widget access denied');
      inject(await response.json());
    } catch (error) { console.warn('[ConversaPay] widget unavailable', error); }
  }

  window.Talk2PayWidget = window.ConversaPayWidget = {
    open: () => document.querySelector('.cp-window')?.classList.add('open'),
    close: () => document.querySelector('.cp-window')?.classList.remove('open'),
  };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
}());
