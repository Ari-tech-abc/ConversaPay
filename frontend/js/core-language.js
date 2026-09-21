(() => {
  'use strict';
  const KEY='conversapay-language', LEGACY='talk2pay_language';
  const MAP={
    'כניסה לחשבון | Talk2Pay':'Log in | Talk2Pay','כניסה מאובטחת לחשבון Talk2Pay.':'Secure login to your Talk2Pay account.',
    'חזרה לדף הבית':'Back to home','כניסה ל‑Talk2Pay':'Log in to Talk2Pay','ניהול העסק, ההזמנות והתשלומים — במקום אחד.':'Manage your business, orders, and payments — in one place.',
    'אימייל':'Email','סיסמה':'Password','להשאיר אותי מחובר במכשיר הזה':'Keep me signed in on this device','כניסה':'Log in','מתחבר...':'Signing in...','המשך עם Google':'Continue with Google','שכחתי סיסמה':'Forgot password','הרשמה':'Sign up',
    'אימות אימייל':'Email verification','החשבון עדיין לא אומת':'Your account is not verified yet','אימות וכניסה':'Verify and sign in','שלח קוד חדש':'Send a new code','מאמת...':'Verifying...','שולח...':'Sending...',
    'כבר יש חשבון?':'Already have an account?','פתיחת חשבון':'Create account','מתחילים בחינם':'Get started for free','אימות באימייל עם קוד חד-פעמי, ואז מגדירים את העסק.':'Verify your email with a one-time code, then set up your business.',
    'שם מלא':'Full name','שם העסק':'Business name','סיסמה, לפחות 8 תווים':'Password, at least 8 characters','אימות סיסמה':'Confirm password','פתיחת חשבון':'Create account','כבר יש חשבון? כניסה':'Already have an account? Log in',
    'שלחנו לך קוד בן 6 ספרות':'We sent you a 6-digit code','אימות והמשך':'Verify and continue','שלח קוד מחדש':'Resend code','פותח חשבון...':'Creating account...','שולח קוד חדש...':'Sending a new code...',
    'מדיניות פרטיות':'Privacy Policy','תנאי שימוש':'Terms of Service','עדכון אחרון: 27 ביולי 2026':'Last updated: July 27, 2026',
    'פרטי בעלת השליטה ויצירת קשר':'Controller details and contact','איזה מידע אנו אוספים':'Information we collect','פרטי חשבון וזהות':'Account and identity information','OAuth וחיבורים חיצוניים':'OAuth and external connections','נתוני שימוש ותפעול':'Usage and operational data','נתוני העסק ותוכן שהוזן':'Business data and submitted content','תשלומים ומנויים':'Payments and subscriptions','מידע ממקורות אחרים':'Information from other sources','מטרות ובסיסים משפטיים':'Purposes and legal bases','תפקידנו כפלטפורמה ומאפשרת מסחר':'Our role as a platform and commerce enabler','שיתוף מידע ומעבדים משניים':'Sharing and subprocessors','העברות מידע מחוץ לישראל או לאזור הכלכלי האירופי':'International data transfers','עוגיות וטכנולוגיות דומות':'Cookies and similar technologies','אבטחת מידע':'Information security','שמירת מידע ומחיקה':'Data retention and deletion','זכויות משתמשים':'User rights','מידע של לקוחות העסק':'Business customer data','קטינים':'Minors','שינויים במדיניות':'Changes to this policy',
    'השירות ותפקיד Talk2Pay':'The service and Talk2Pay’s role','חשבון והרשאות':'Account and permissions','תוכן שהמשתמש מזין':'User-submitted content','פרטיות ונתוני לקוחות':'Privacy and customer data','תשלומים, Stripe ו-PayMe':'Payments, Stripe and PayMe','שימושים אסורים':'Prohibited uses','קניין רוחני':'Intellectual property','מפתחות API ואינטגרציות':'API keys and integrations','זמינות, שינויים והשעיה':'Availability, changes and suspension','אחריות והגבלת אחריות':'Liability and limitation of liability','שיפוי':'Indemnification','סיום החשבון':'Account termination','דין וסמכות':'Governing law and jurisdiction','עדכונים ויצירת קשר':'Updates and contact',
    'סגור':'Close'
  };
  const REV=Object.fromEntries(Object.entries(MAP).map(([he,en])=>[en,he]));
  const skip=new Set(['SCRIPT','STYLE','NOSCRIPT','CODE','PRE']);
  let applying=false;
  function lang(){return (localStorage.getItem(KEY)||localStorage.getItem(LEGACY))==='en'?'en':'he'}
  function translateText(text,to){const raw=String(text??''), trimmed=raw.trim(); if(!trimmed)return raw; const map=to==='en'?MAP:REV; const v=map[trimmed]; return v?raw.replace(trimmed,v):raw}
  function apply(root=document.body){if(!root||applying)return; applying=true; const to=lang(), en=to==='en'; document.documentElement.lang=to; document.documentElement.dir=en?'ltr':'rtl';
    const scope=root.nodeType===1?root:document.body;
    if(scope.matches?.('[data-i18n-he]')){const v=scope.getAttribute(en?'data-i18n-en':'data-i18n-he');if(v!==null)scope.textContent=v}
    scope.querySelectorAll?.('[data-i18n-he]').forEach(el=>{const v=el.getAttribute(en?'data-i18n-en':'data-i18n-he');if(v!==null)el.textContent=v});
    const walker=document.createTreeWalker(scope,NodeFilter.SHOW_TEXT); let n; const nodes=[]; while((n=walker.nextNode()))nodes.push(n); nodes.forEach(node=>{const p=node.parentElement;if(!p||skip.has(p.tagName)||p.closest('.cp-language-toggle'))return;node.nodeValue=translateText(node.nodeValue,to)});
    document.querySelectorAll('[data-i18n-placeholder-he]').forEach(el=>el.setAttribute('placeholder',el.getAttribute(en?'data-i18n-placeholder-en':'data-i18n-placeholder-he')||''));
    applying=false; updateButton();
  }
  function updateButton(){const b=document.querySelector('[data-cp-language-toggle]');if(!b)return;const en=lang()==='en';b.innerHTML='<span aria-hidden="true">🌐</span><span>'+(en?'עברית':'English')+'</span>';b.setAttribute('aria-label',en?'Switch to Hebrew':'Switch to English')}
  function setLanguage(v){localStorage.setItem(KEY,v);localStorage.setItem(LEGACY,v);apply(document.body)}
  function init(){let b=document.querySelector('[data-cp-language-toggle]');if(!b){b=document.createElement('button');b.type='button';b.className='cp-language-toggle';b.dataset.cpLanguageToggle='true';b.addEventListener('click',()=>setLanguage(lang()==='en'?'he':'en'));document.body.appendChild(b)}apply(document.body);
    new MutationObserver(records=>{if(applying)return;for(const r of records){if(r.type==='characterData'){const n=r.target,p=n.parentElement;if(p&&!skip.has(p.tagName)&&!p.closest('.cp-language-toggle')){const v=translateText(n.nodeValue,lang());if(v!==n.nodeValue){applying=true;n.nodeValue=v;applying=false}}}else r.addedNodes.forEach(n=>{if(n.nodeType===1)apply(n)})}}).observe(document.body,{subtree:true,childList:true,characterData:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
