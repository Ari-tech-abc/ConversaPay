/* Shared request bounds and keyboard behavior for application dialogs. */
(() => {
 'use strict';
 const t=(he,en)=>(localStorage.getItem('conversapay-language')||localStorage.getItem('talk2pay_language'))==='en'?en:he;
 const error=(status,detail='')=> status===429?t('בוצעו יותר מדי ניסיונות. נסה שוב בעוד כמה דקות.','Too many attempts. Try again in a few minutes.'):status>=500?t('השירות אינו זמין כרגע. נסה שוב.','The service is unavailable. Please try again.'):!status?t('לא ניתן להתחבר לשירות. בדוק את החיבור ונסה שוב.','Could not connect. Check your connection and retry.'):t('אימייל או סיסמה שגויים.','Incorrect email or password.');
 window.Talk2PayUX={t,error};
 const originalFetch=window.fetch.bind(window);
 window.fetch=async(input,options={})=>{
  const url=new URL(input instanceof Request?input.url:input,location.href);
  if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return originalFetch(input,options);
  const controller=new AbortController(),external=options.signal||(input instanceof Request?input.signal:null);
  const abort=()=>controller.abort(external?.reason);if(external?.aborted)abort();else external?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>controller.abort(),15000);
  try{return await originalFetch(input,{...options,signal:controller.signal})}finally{clearTimeout(timer);external?.removeEventListener('abort',abort)}
 };
 function init(){
  let active=null,previous=null,lastOutside=document.activeElement;
  const visible=el=>!el.hidden&&el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden';
  const focusable=el=>[...el.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(visible);
  function sync(){
   const dialogs=[...document.querySelectorAll('[role="dialog"],[role="alertdialog"]')].filter(visible);const next=dialogs.at(-1)||null;
   if(next===active)return;
   const closed=active;active=next;if(closed&&previous?.isConnected)previous.focus();
   if(active){previous=lastOutside;if(!active.hasAttribute('aria-label')&&!active.hasAttribute('aria-labelledby')){const heading=active.querySelector('h1,h2,h3');if(heading){heading.id ||= 'dialog-title-'+Math.random().toString(36).slice(2);active.setAttribute('aria-labelledby',heading.id)}}if(!active.contains(document.activeElement))(focusable(active).find(el=>el.matches('input,textarea'))||focusable(active)[0])?.focus()}
  }
  document.addEventListener('keydown',event=>{if(!active)return;const nodes=focusable(active);if(event.key==='Escape'){const close=active.querySelector('[id*="Close"],[id*="close"],.close,.verify-close,.cancel-close');if(close){event.preventDefault();close.click()}}else if(event.key==='Tab'){const index=nodes.indexOf(document.activeElement);if(!nodes.length){event.preventDefault();return}if(event.shiftKey&&(index<=0)){event.preventDefault();nodes.at(-1).focus()}else if(!event.shiftKey&&(index===nodes.length-1||index<0)){event.preventDefault();nodes[0].focus()}}});
  document.addEventListener('focusin',event=>{if(active&&!active.contains(event.target))focusable(active)[0]?.focus();else if(!event.target.closest('[role="dialog"],[role="alertdialog"]'))lastOutside=event.target});
  new MutationObserver(sync).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','hidden','style']});sync();
 }
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
