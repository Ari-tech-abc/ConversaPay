/* An explicitly labelled, local illustration. No API calls or simulated charges. */
(() => {
 'use strict';
 function init(){
  const scene=document.querySelector('[data-t2p-demo]');if(!scene)return;
  const original=scene.innerHTML;
  const scenarios={
   catalog:{question:['אני מחפשת תיק ליומיום. מה יש בקטלוג?','I need an everyday bag. What is in the catalog?'],answer:['תיק Everyday מופיע בקטלוג ההדגמה: ירוק זית, במחיר ₪249.','The demo catalog lists the Everyday bag in olive green for ₪249.']},
   payment:{question:['בחרתי את התיק. איך משלמים?','I chose the bag. How do I pay?'],answer:['לפני התשלום מאשרים את המוצר והסכום. לאחר האישור נוצר קישור אצל ספק הסליקה.','Confirm the item and total before paying. Once confirmed, a link is created by the payment provider.']},
   knowledge:{question:['אפשר להחזיר את התיק אחרי חודש?','Can I return the bag after a month?'],answer:['מדיניות ההחזרות לא מופיעה בקטלוג ההדגמה. צריך לבדוק מול העסק לפני שמבטיחים החזר.','The demo catalog does not include a returns policy. Check with the business before promising a refund.']}
  };
  const tr=values=>values[document.documentElement.lang==='en'?1:0];
  let current=null;
  const status=document.getElementById('demo-status');
  function display(){
   if(!current)return;
   const row=scenarios[current],messages=scene.querySelectorAll('.t2p-demo-msg');
   messages[0].textContent=tr(row.question);messages[1].textContent=tr(row.answer);messages[2].hidden=true;
   scene.querySelector('.t2p-demo-product').hidden=current==='knowledge';
   const pay=scene.querySelector('.t2p-demo-pay');pay.hidden=current!=='payment';
   if(current==='payment')pay.lastChild.textContent=tr(['סיכום לדוגמה · תיק Everyday · ₪249','Example summary · Everyday bag · ₪249']);
   scene.querySelector('.t2p-demo-confirm').hidden=true;
   status.textContent=tr(['הדגמה מקומית. התוכן נכתב מראש ולא מתבצע חיוב.','Local demo. Responses are scripted and no payment is taken.']);
  }
  document.querySelectorAll('[data-demo-scenario]').forEach(button=>button.addEventListener('click',()=>{
   const control=document.querySelector('[data-t2p-motion]');
   if(control?.getAttribute('aria-pressed')!=='true')control?.click();
   if(control)control.disabled=true;current=button.dataset.demoScenario;scene.dataset.interactive='true';scene.classList.remove('t2p-demo-playing','t2p-demo-resetting');
   document.querySelectorAll('[data-demo-scenario]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));display();
  }));
  document.getElementById('demo-replay')?.addEventListener('click',()=>{
   current=null;delete scene.dataset.interactive;scene.innerHTML=original;window.ConversaPayLanguage?.refresh();
   document.querySelectorAll('[data-demo-scenario]').forEach(button=>button.setAttribute('aria-pressed','false'));
   status.textContent='';const control=document.querySelector('[data-t2p-motion]');if(control){control.disabled=false;if(control.getAttribute('aria-pressed')==='true')control.click();}
  });
  let language=document.documentElement.lang;
  new MutationObserver(()=>{if(language===document.documentElement.lang)return;language=document.documentElement.lang;display();}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
 }
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
