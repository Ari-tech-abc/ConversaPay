/* Motion is decorative; server responses remain the source of truth. */
(() => {
 'use strict';
 const reduced = matchMedia('(prefers-reduced-motion: reduce)');
 const running = new Set(), panels = new WeakMap(), timers = new WeakMap();
 const ease = 'cubic-bezier(.16,1,.3,1)';
 function animate(element, frames, options = {}) {
  if (!element || reduced.matches || !element.animate) return null;
  const animation = element.animate(frames, { duration: 260, easing: ease, ...options });
  running.add(animation);
  animation.finished.catch(() => {}).finally(() => running.delete(animation));
  return animation;
 }
 function begin(button) {
  if (!button) return;
  clearTimeout(timers.get(button)); delete button.dataset.saved;
  button.dataset.saving = 'true'; button.setAttribute('aria-busy', 'true');
 }
 function end(button) { if (button) { delete button.dataset.saving; button.removeAttribute('aria-busy'); } }
 function saved(button) {
  if (!button) return;
  end(button); button.dataset.saved = 'true';
  clearTimeout(timers.get(button)); timers.set(button, setTimeout(() => delete button.dataset.saved, 1600));
 }
 function panel(element, open) {
  if (!element) return;
  const old = panels.get(element); old?.animation?.cancel();
  const token = {}; panels.set(element, token);
  element.inert = !open;
  if (open) element.hidden = false;
  const frames = open ? [{ opacity: 0, transform: 'translateY(14px) scale(.97)' }, { opacity: 1, transform: 'none' }] : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(10px) scale(.98)' }];
  token.animation = animate(element, frames, { duration: open ? 260 : 160 });
  const finish = () => { if (panels.get(element) === token && !open) element.hidden = true; };
  if (token.animation) token.animation.finished.then(finish, () => {}); else finish();
 }
 async function removeRows(ids = []) {
  const rows = [...document.querySelectorAll('#products .item')].filter(row => ids.includes(row.querySelector('[data-select-product]')?.dataset.selectProduct));
  await Promise.all(rows.map(async row => {
   row.inert = true;
   const animation = animate(row, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(10px)' }], { duration: 150 });
   if (animation) await animation.finished.catch(() => {});
   row.remove();
  }));
 }
 function reveal() {
  const targets = [...document.querySelectorAll('body.home-page .section-title,body.home-page .cap-row,body.home-page .plan,body.home-page .security-visual,body.home-page .final-cta,body:not(.home-page) .stat')];
  if (!('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver(entries => {
   const visible = entries.filter(entry => entry.isIntersecting);
   visible.forEach((entry, index) => {
    observer.unobserve(entry.target); entry.target.dataset.motionRevealed = 'true';
    animate(entry.target, [{ opacity: .3, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { duration: 420, delay: Math.min(index, 3) * 65 });
   });
  }, { threshold: .12 });
  targets.forEach(target => observer.observe(target));
 }
 function init() {
  reveal();
  const hero = document.querySelector('.hero-frame');
  if (hero) {
   const light = document.createElement('div'); light.className = 't2p-hero-light'; light.setAttribute('aria-hidden', 'true');
   light.innerHTML = '<span></span><span></span>'; hero.prepend(light);
   const control = document.querySelector('[data-t2p-motion]'); let visible = true;
   function update() { hero.classList.toggle('t2p-motion-running', visible && !document.hidden && !reduced.matches && control?.getAttribute('aria-pressed') !== 'true'); }
   if ('IntersectionObserver' in window) new IntersectionObserver(entries => { visible = entries[0].isIntersecting; update(); }).observe(hero);
   if (control) new MutationObserver(update).observe(control, { attributes: true, attributeFilter: ['aria-pressed'] });
   document.addEventListener('visibilitychange', update); reduced.addEventListener('change', update); update();
  }
  const messages = document.getElementById('messages');
  if (messages) new MutationObserver(records => {
   for (const record of records) for (const node of record.addedNodes) if (node.nodeType === 1 && !document.getElementById('widgetPanel')?.hidden) animate(node, [{ opacity: 0, transform: 'translateY(7px)' }, { opacity: 1, transform: 'none' }], { duration: 200 });
  }).observe(messages, { childList: true });
  const authCard = document.querySelector('body[data-t2p-page="login"] .t2p-auth-shell>.cp-card,body[data-t2p-page="register"] .t2p-auth-shell>.cp-card');
  if (authCard) animate(authCard, [{ opacity: .25, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 240 });
 }
 reduced.addEventListener('change', () => { if (reduced.matches) for (const animation of running) animation.finish(); });
 window.Talk2PayMotion = { begin, end, saved, panel, removeRows, animate };
 if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => queueMicrotask(init), { once: true }); else queueMicrotask(init);
})();
