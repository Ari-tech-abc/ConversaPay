(() => {
  'use strict';

  const VERSION = 1;
  const MAX_AGE_MS = 1000 * 60 * 60 * 24 * 30;
  const METRICS = {
    revenue: { type: 'money', decimals: 2 },
    deals: { type: 'number', decimals: 0 },
    conversations: { type: 'number', decimals: 0 },
    conversion: { type: 'percent', decimals: 1 },
  };
  const META_IDS = ['userName', 'businessName', 'plan', 'sidePlan'];
  const metricState = new Map();
  const metaObservers = [];
  let snapshot = null;
  let cacheKey = null;
  let saveTimer = null;

  function getUserId() {
    return localStorage.getItem('user_id') || sessionStorage.getItem('user_id') || '';
  }

  function getKey() {
    const userId = getUserId();
    return userId ? `talk2pay_dashboard_snapshot_v${VERSION}:${userId}` : null;
  }

  function readSnapshot() {
    cacheKey = getKey();
    if (!cacheKey) return null;
    try {
      const data = JSON.parse(localStorage.getItem(cacheKey) || 'null');
      if (!data || data.version !== VERSION || !data.savedAt) return null;
      if (Date.now() - Number(data.savedAt) > MAX_AGE_MS) return null;
      return data;
    } catch (_) {
      return null;
    }
  }

  function parseValue(text, type) {
    const cleaned = String(text ?? '')
      .replace(/[₪,%\s]/g, '')
      .replace(/,/g, '');
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : null;
  }

  function formatValue(value, spec) {
    if (spec.type === 'money') {
      return '₪' + Number(value).toLocaleString('he-IL', {
        minimumFractionDigits: 0,
        maximumFractionDigits: spec.decimals,
      });
    }
    if (spec.type === 'percent') {
      return Number(value).toFixed(spec.decimals) + '%';
    }
    return Math.round(Number(value)).toLocaleString('he-IL');
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function animationDuration(from, to) {
    const delta = Math.abs(to - from);
    if (!delta) return 0;
    const magnitude = Math.max(Math.abs(from), Math.abs(to), 1);
    const relative = Math.min(delta / magnitude, 1);
    // Large jumps animate fast; small changes get enough time to be noticeable.
    return Math.max(320, Math.min(760, 560 - relative * 180 + Math.log10(delta + 1) * 38));
  }

  function animateMetric(el, from, to, spec) {
    const state = metricState.get(el.id) || {};
    if (state.raf) cancelAnimationFrame(state.raf);
    const duration = animationDuration(from, to);
    state.animating = true;
    state.target = to;
    metricState.set(el.id, state);

    if (!duration || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      el.textContent = formatValue(to, spec);
      state.animating = false;
      state.current = to;
      saveSoon();
      return;
    }

    const started = performance.now();
    const render = now => {
      const t = Math.min(1, (now - started) / duration);
      const eased = easeOutCubic(t);
      const value = from + (to - from) * eased;
      el.textContent = formatValue(value, spec);
      if (t < 1) {
        state.raf = requestAnimationFrame(render);
      } else {
        el.textContent = formatValue(to, spec);
        state.animating = false;
        state.current = to;
        state.raf = null;
        el.closest('.stat')?.classList.add(to > from ? 'metric-updated-up' : 'metric-updated-down');
        setTimeout(() => el.closest('.stat')?.classList.remove('metric-updated-up', 'metric-updated-down'), 700);
        saveSoon();
      }
    };
    state.raf = requestAnimationFrame(render);
  }

  function snapshotFromDom() {
    const metrics = {};
    for (const [id, spec] of Object.entries(METRICS)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const state = metricState.get(id);
      const value = state && Number.isFinite(state.current)
        ? state.current
        : parseValue(el.textContent, spec.type);
      if (value !== null) metrics[id] = value;
    }
    const meta = {};
    for (const id of META_IDS) {
      const el = document.getElementById(id);
      if (el && String(el.textContent || '').trim()) meta[id] = el.textContent.trim();
    }
    return { version: VERSION, savedAt: Date.now(), metrics, meta };
  }

  function saveNow() {
    saveTimer = null;
    cacheKey = getKey() || cacheKey;
    if (!cacheKey) return;
    try {
      localStorage.setItem(cacheKey, JSON.stringify(snapshotFromDom()));
    } catch (_) {}
  }

  function saveSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 120);
  }

  function restoreSnapshot(data) {
    if (!data) return false;
    let restored = false;
    for (const [id, spec] of Object.entries(METRICS)) {
      const el = document.getElementById(id);
      const value = data.metrics?.[id];
      if (!el || !Number.isFinite(Number(value))) continue;
      const n = Number(value);
      metricState.set(id, { current: n, animating: false, raf: null });
      el.textContent = formatValue(n, spec);
      restored = true;
    }
    for (const id of META_IDS) {
      const el = document.getElementById(id);
      const value = data.meta?.[id];
      if (el && value) el.textContent = value;
    }
    if (restored) {
      const content = document.getElementById('content');
      if (content) content.style.visibility = 'visible';
      const loader = document.getElementById('dashboardLoader');
      if (loader) {
        loader.classList.add('hide');
        setTimeout(() => loader.remove(), 180);
      }
      document.documentElement.classList.add('dashboard-cache-restored');
    }
    return restored;
  }

  function watchMetric(id, spec) {
    const el = document.getElementById(id);
    if (!el) return;
    const initial = parseValue(el.textContent, spec.type);
    if (!metricState.has(id)) metricState.set(id, { current: initial ?? 0, animating: false, raf: null });

    const observer = new MutationObserver(() => {
      const state = metricState.get(id);
      if (!state || state.animating) return;
      const incoming = parseValue(el.textContent, spec.type);
      if (incoming === null) return;
      const current = Number.isFinite(state.current) ? state.current : incoming;
      if (Math.abs(incoming - current) < 0.00001) {
        state.current = incoming;
        saveSoon();
        return;
      }
      animateMetric(el, current, incoming, spec);
    });
    observer.observe(el, { childList: true, characterData: true, subtree: true });
  }

  function watchMeta() {
    for (const id of META_IDS) {
      const el = document.getElementById(id);
      if (!el) continue;
      const observer = new MutationObserver(saveSoon);
      observer.observe(el, { childList: true, characterData: true, subtree: true });
      metaObservers.push(observer);
    }
  }

  function init() {
    snapshot = readSnapshot();
    restoreSnapshot(snapshot);
    for (const [id, spec] of Object.entries(METRICS)) watchMetric(id, spec);
    watchMeta();

    // Save a fresh snapshot after the normal dashboard loader finishes, and when leaving.
    const loader = document.getElementById('dashboardLoader');
    if (loader) {
      new MutationObserver(() => {
        if (loader.classList.contains('hide')) saveSoon();
      }).observe(loader, { attributes: true, attributeFilter: ['class'] });
    }
    window.addEventListener('pagehide', saveNow);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') saveNow();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
