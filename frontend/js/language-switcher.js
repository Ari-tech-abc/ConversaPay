/* ConversaPay bilingual UI. Home page is intentionally excluded by the server injector. */
(() => {
  'use strict';
  const KEY = 'conversapay-language';
  const pairs = [
    ['לוח בקרה', 'Dashboard'], ['דשבורד', 'Dashboard'], ['פרופיל', 'Profile'], ['הגדרות', 'Settings'],
    ['התנתק', 'Log out'], ['יציאה', 'Log out'], ['התחברות', 'Log in'], ['כניסה', 'Log in'], ['הרשמה', 'Sign up'],
    ['שמור', 'Save'], ['שמירה', 'Save'], ['ביטול', 'Cancel'], ['מחיקה', 'Delete'], ['מחק', 'Delete'],
    ['עריכה', 'Edit'], ['ערוך', 'Edit'], ['חזרה', 'Back'], ['המשך', 'Continue'], ['שליחה', 'Submit'],
    ['שלח', 'Send'], ['חיפוש', 'Search'], ['טעינה...', 'Loading...'], ['טוען...', 'Loading...'],
    ['שגיאה', 'Error'], ['הצלחה', 'Success'], ['תשלום', 'Payment'], ['תשלומים', 'Payments'], ['חיוב', 'Billing'],
    ['אבטחה', 'Security'], ['מוצר', 'Product'], ['מוצרים', 'Products'], ['עסק', 'Business'], ['עסקים', 'Businesses'],
    ['שם העסק', 'Business name'], ['אימייל', 'Email'], ['דוא״ל', 'Email'], ['סיסמה', 'Password'],
    ['אימות אימייל', 'Email verification'], ['שכחתי סיסמה', 'Forgot password'], ['איפוס סיסמה', 'Reset password'],
    ['רשימת בדיקות לפרודקשן', 'Production checklist'], ['כלי פיתוח', 'Developer tools'],
    ['לא נמצאו תוצאות', 'No results found'], ['הפעולה נכשלה', 'The action failed'],
    ['הפעולה בוצעה בהצלחה', 'The action was completed successfully'], ['ניהול', 'Management'],
    ['סקירה כללית', 'Overview'], ['לקוחות', 'Customers'], ['הזמנות', 'Orders'], ['הכנסות', 'Revenue'],
    ['הוסף', 'Add'], ['הוספה', 'Add'], ['חדש', 'New'], ['סגור', 'Close'], ['אישור', 'Confirm'],
    ['כן', 'Yes'], ['לא', 'No'], ['שם', 'Name'], ['טלפון', 'Phone'], ['סטטוס', 'Status'],
    ['פעולות', 'Actions'], ['תאריך', 'Date'], ['פרטים', 'Details'], ['התחל', 'Get started'],
    ['צור חשבון', 'Create account'], ['ברוך הבא', 'Welcome'], ['התראות', 'Notifications'], ['שפה', 'Language']
  ];
  const heToEn = new Map(pairs);
  const enToHe = new Map(pairs.map(([he, en]) => [en, he]));
  const originalText = new WeakMap();
  const originalAttrs = new WeakMap();
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE']);
  const attrs = ['placeholder', 'title', 'aria-label'];

  function replacePhrases(value, map) {
    let result = value;
    [...map.keys()].sort((a, b) => b.length - a.length).forEach(source => {
      if (result.includes(source)) result = result.split(source).join(map.get(source));
    });
    return result;
  }

  function translate(root, english) {
    const map = english ? heToEn : enToHe;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; let node;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(textNode => {
      const parent = textNode.parentElement;
      if (!parent || skipTags.has(parent.tagName) || parent.closest('.cp-language-toggle')) return;
      if (!originalText.has(textNode)) originalText.set(textNode, textNode.nodeValue);
      const source = originalText.get(textNode);
      textNode.nodeValue = replacePhrases(source, map);
    });

    document.querySelectorAll(attrs.map(attr => `[${attr}]`).join(',')).forEach(element => {
      if (element.classList.contains('cp-language-toggle')) return;
      if (!originalAttrs.has(element)) {
        const saved = {};
        attrs.forEach(attr => { if (element.hasAttribute(attr)) saved[attr] = element.getAttribute(attr); });
        originalAttrs.set(element, saved);
      }
      const saved = originalAttrs.get(element);
      attrs.forEach(attr => { if (saved[attr] !== undefined) element.setAttribute(attr, replacePhrases(saved[attr], map)); });
    });
  }

  function setLanguage(language) {
    const english = language === 'en';
    document.documentElement.lang = english ? 'en' : 'he';
    document.documentElement.dir = english ? 'ltr' : 'rtl';
    document.body.classList.toggle('cp-lang-en', english);
    translate(document.body, english);
    localStorage.setItem(KEY, english ? 'en' : 'he');
    const button = document.querySelector('[data-cp-language-toggle]');
    if (button) {
      button.innerHTML = `<span aria-hidden="true">🌐</span><span>${english ? 'עברית' : 'English'}</span>`;
      button.setAttribute('aria-label', english ? 'Switch to Hebrew' : 'Switch to English');
      button.setAttribute('title', english ? 'Switch to Hebrew' : 'Switch to English');
    }
  }

  function init() {
    if (!document.body || document.querySelector('[data-cp-language-toggle]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.cpLanguageToggle = 'true';
    button.className = 'cp-language-toggle';
    button.addEventListener('click', () => setLanguage(document.documentElement.lang === 'en' ? 'he' : 'en'));
    document.body.appendChild(button);
    setLanguage(localStorage.getItem(KEY) === 'en' ? 'en' : 'he');
    const observer = new MutationObserver(() => {
      if (document.documentElement.lang === 'en') translate(document.body, true);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
