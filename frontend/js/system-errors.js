(() => {
  'use strict';
  const CHAT_EXCLUSIONS = '.messages,.widget-panel,.msg,[data-chat],#messages';
  const shown = new Map();

  function ensureWrap() {
    let wrap = document.getElementById('toastWrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'toastWrap';
      wrap.className = 'cp-toast-wrap';
      document.body.appendChild(wrap);
    }
    return wrap;
  }

  function show(text, type = 'error') {
    const clean = String(text || '').trim();
    if (!clean) return;
    const now = Date.now();
    if (shown.has(clean) && now - shown.get(clean) < 1200) return;
    shown.set(clean, now);
    const wrap = ensureWrap();
    const node = document.createElement('div');
    node.className = `cp-toast ${type}`;
    node.setAttribute('role', type === 'error' ? 'alert' : 'status');
    node.innerHTML = `<span class="cp-toast-icon">${type === 'error' ? '✕' : '✓'}</span><span></span><button class="cp-toast-close" type="button" aria-label="סגור">×</button>`;
    node.children[1].textContent = clean;
    node.children[2].onclick = () => node.remove();
    wrap.appendChild(node);
    return node;
  }

  window.showSystemModal = show;
  window.alert = (message) => show(message, 'error');

  function visible(el) {
    if (!el || el.hidden || el.closest(CHAT_EXCLUSIONS) || el.closest('.cp-toast')) return false;
    const style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  }

  function scan(root = document) {
    const selectors = ['.cp-notice.error', '.notice.error', '.gate-error', '[role="alert"]'];
    for (const selector of selectors) {
      root.querySelectorAll?.(selector).forEach((el) => {
        if (!visible(el)) return;
        const text = (el.textContent || '').trim();
        if (!text || el.dataset.systemModalText === text) return;
        el.dataset.systemModalText = text;
        show(text, 'error');
      });
    }
  }

  const start = () => {
    scan();
    new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') scan(mutation.target.parentElement || document);
        else {
          scan(mutation.target instanceof Element ? mutation.target : document);
          mutation.addedNodes.forEach((node) => { if (node instanceof Element) scan(node); });
        }
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden', 'class', 'style'] });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
