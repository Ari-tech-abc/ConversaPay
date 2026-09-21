/* ConversaPay bilingual UI. Home page is intentionally excluded by the server injector. */
(() => {
  'use strict';
  const KEY = 'conversapay-language';
  const translations = new Map([
    ['לוח בקרה', 'Dashboard'], ['פרופיל', 'Profile'], ['הגדרות', 'Settings'], ['התנתק', 'Log out'],
    ['התחברות', 'Log in'], ['הרשמה', 'Sign up'], ['שמור', 'Save'], ['ביטול', 'Cancel'],
    ['מחיקה', 'Delete'], ['עריכה', 'Edit'], ['חזרה', 'Back'], ['המשך', 'Continue'],
    ['שליחה', 'Submit'], ['חיפוש', 'Search'], ['טעינה...', 'Loading...'], ['שגיאה', 'Error'],
    ['הצלחה', 'Success'], ['תשלום', 'Payment'], ['תשלומים', 'Payments'], ['חיוב', 'Billing'],
    ['אבטחה', 'Security'], ['מוצר', 'Product'], ['מוצרים', 'Products'], ['עסק', 'Business'],
    ['שם העסק', 'Business name'], ['אימייל', 'Email'], ['סיסמה', 'Password'],
    ['אימות אימייל', 'Email verification'], ['שכחתי סיסמה', 'Forgot password'],
    ['רשימת בדיקות לפרודקשן', 'Production checklist'], ['כלי פיתוח', 'Developer tools'],
    ['לא נמצאו תוצאות', 'No results found'], ['הפעולה נכשלה', 'The action failed'],
    ['הפעולה בוצעה בהצלחה', 'The action was completed successfully']
  ]);
  const reverse = new Map([...translations].map(([he, en]) => [en, he]));
  const original = new WeakMap();
  const attrs = ['placeholder', 'title', 'aria-label'];
  function translate(root, toEnglish) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; let node;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(textNode => {
      const parent = textNode.parentElement;
      if (!parent || ['SCRIPT','STYLE','NOSCRIPT','TEXTAREA'].includes(parent.tagName)) return;
      if (!original.has(textNode)) original.set(textNode, textNode.nodeValue);
      const value = original.get(textNode).trim();
      if (!value) return;
      const replacement = toEnglish ? translations.get(value) : reverse.get(value);
      if (replacement) textNode.nodeValue = textNode.nodeValue.replace(value, replacement);
    });
    document.querySelectorAll(attrs.map(a => `[${a}]`).join(',')).forEach(el => {
      attrs.forEach(attr => {
        if (!el.hasAttribute(attr)) return;
        const key = `${attr}:${el.dataset.i18nOriginal ?? el.getAttribute(attr)}`;
        if (!el.dataset.i18nOriginal) el.dataset.i18nOriginal = el.getAttribute(attr);
        const source = el.dataset.i18nOriginal;
        const replacement = toEnglish ? translations.get(source) : reverse.get(source);
        if (replacement) el.setAttribute(attr, replacement);
      });
    });
  }
  function setLanguage(lang) {
    const english = lang === 'en';
    document.documentElement.lang = english ? 'en' : 'he';
    document.documentElement.dir = english ? 'ltr' : 'rtl';
    document.body.classList.toggle('cp-lang-en', english);
    translate(document.body, english);
    localStorage.setItem(KEY, english ? 'en' : 'he');
    const button = document.querySelector('[data-cp-language-toggle]');
    if (button) {
      button.textContent = english ? 'עברית' : 'English';
      button.setAttribute('aria-label', english ? 'Switch to Hebrew' : 'Switch to English');
      button.setAttribute('aria-pressed', String(english));
    }
  }
  function init() {
    if (!document.body || document.querySelector('[data-cp-language-toggle]')) return;
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.cpLanguageToggle = 'true';
    button.className = 'cp-language-toggle'; button.textContent = 'English';
    button.setAttribute('aria-label', 'Switch to English');
    button.addEventListener('click', () => setLanguage(document.documentElement.lang === 'en' ? 'he' : 'en'));
    document.body.appendChild(button);
    setLanguage(localStorage.getItem(KEY) === 'en' ? 'en' : 'he');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
