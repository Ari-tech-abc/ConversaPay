/* Passwords are evaluated locally, never sent to a strength or analytics service. */
(() => {
 'use strict';
 const t=(he,en)=>document.documentElement.lang==='en'?en:he;
 let policy={min_length:8,max_length:128,recommended_length:16,common_passwords:[]};
 const widgets=[];
 const length=value=>Array.from(value).length;
 function inspect(value){
  const count=length(value),common=!!value&&(policy.common_passwords.includes(value.toLowerCase())||new Set(value).size===1||!value.trim());
  const valid=count>=policy.min_length&&count<=policy.max_length&&!common;
  const unique=new Set(value).size;
  const strength=!valid?0:count>=policy.recommended_length&&unique>=8?3:count>=12&&unique>=6?2:1;
  return {count,common,valid,strength};
 }
 function error(detail){
  const code=Array.isArray(detail)?detail.find(e=>['password_common','string_too_short','string_too_long'].includes(e.type))?.type:detail;
  if(code==='password_common')return t('הסיסמה נפוצה מדי. כדאי לבחור ביטוי אחר או ליצור סיסמה אקראית.','This password is too common. Choose a different phrase or generate a password.');
  if(['password_length','string_too_short','string_too_long'].includes(code))return t('יש לבחור סיסמה באורך 8 עד 128 תווים.','Choose a password with 8 to 128 characters.');
  return '';
 }
 function mount(input){
  if(input.dataset.passwordReady)return;
  input.dataset.passwordReady='true';input.spellcheck=false;input.autocapitalize='none';
  const isNew=input.autocomplete==='new-password';
  const wrap=document.createElement('div');wrap.className='t2p-password-input';
  input.before(wrap);wrap.append(input);
  const toggle=document.createElement('button');toggle.type='button';toggle.className='t2p-password-toggle';toggle.setAttribute('aria-controls',input.id);toggle.setAttribute('aria-pressed','false');wrap.append(toggle);
  if(isNew){const guardian=document.createElement('span');guardian.className='t2p-password-guardian';guardian.setAttribute('aria-hidden','true');guardian.innerHTML='<svg viewBox="0 0 32 18"><g><ellipse cx="10" cy="8" rx="3" ry="4"/><ellipse cx="22" cy="8" rx="3" ry="4"/></g><path d="M12 15q4 3 8 0"/></svg>';wrap.append(guardian);}
  let hideTimer,touched=false,submitted=false,announceTimer;
  const field=input.closest('.cp-field')||wrap.parentElement;
  const feedback=document.createElement('div');feedback.className='t2p-password-feedback';feedback.id=input.id+'-feedback';
  const live=document.createElement('span');live.className='t2p-password-live';live.setAttribute('role','status');live.setAttribute('aria-live','polite');
  const hint=document.createElement('span');hint.className='t2p-password-hint';
  const meter=document.createElement('meter');meter.min=0;meter.max=3;meter.value=0;meter.className='t2p-password-meter';
  const description=(input.getAttribute('aria-describedby')||'').split(' ').filter(Boolean);
  if(isNew){feedback.append(meter,hint,live);field.append(feedback);description.push(feedback.id);input.setAttribute('aria-describedby',description.join(' '));}
  function label(){const shown=input.type==='text';toggle.textContent=shown?t('הסתרה','Hide'):t('הצגה','Show');toggle.setAttribute('aria-label',shown?t('הסתרת הסיסמה','Hide password'):t('הצגת הסיסמה','Show password'));toggle.setAttribute('aria-pressed',String(shown));wrap.classList.toggle('is-revealed',shown);}
  function conceal(){clearTimeout(hideTimer);input.type='password';label();}
  toggle.addEventListener('click',()=>{const start=input.selectionStart,end=input.selectionEnd;if(input.type==='text')conceal();else{input.type='text';label();hideTimer=setTimeout(conceal,30000);}input.focus();if(start!==null)input.setSelectionRange(start,end);});
  input.addEventListener('blur',()=>{touched=true;render();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)conceal();});
  function render(){
   label();if(!isNew)return;
   const state=inspect(input.value);let message;
   if(!state.count)message=t('8–128 תווים. אפשר להשתמש בביטוי שקל לזכור.','8–128 characters. A memorable phrase works too.');
   else if(state.common)message=t('כדאי לבחור סיסמה פחות נפוצה.','Choose a less common password.');
   else if(state.count<policy.min_length)message=t('עוד '+(policy.min_length-state.count)+' תווים ואפשר להמשיך.','Add '+(policy.min_length-state.count)+' more characters to continue.');
   else if(state.count>policy.max_length)message=error('password_length');
   else message=[null,t('אפשר להמשיך. ביטוי ארוך יותר יחזק את הסיסמה.','Ready to continue. A longer phrase would be stronger.'),t('סיסמה טובה.','Good password.'),t('סיסמה ארוכה ומגוונת.','Long and varied password.')][state.strength];
   const invalid=(touched||submitted)&&!state.valid&&!!state.count;
   wrap.dataset.strength=String(state.strength);wrap.classList.toggle('is-invalid',invalid);
   input.setCustomValidity((submitted||touched)&&!state.valid?(state.common?error('password_common'):error('password_length')):'');
   if(invalid)input.setAttribute('aria-invalid','true');else input.removeAttribute('aria-invalid');
   meter.value=state.strength;meter.hidden=!state.count;meter.setAttribute('aria-label',t('חוזק משוער של הסיסמה','Estimated password strength'));meter.setAttribute('aria-valuetext',message);
   hint.textContent=message;clearTimeout(announceTimer);announceTimer=setTimeout(()=>{live.textContent=message;},600);
  }
  input.addEventListener('input',()=>{input.setCustomValidity('');render();});
  input.addEventListener('change',render);
  if(isNew){
   input.minLength=policy.min_length;input.maxLength=policy.max_length;
   const tools=document.createElement('div');tools.className='t2p-password-tools';
   const generate=document.createElement('button');generate.type='button';generate.className='t2p-password-generate';
   const copy=document.createElement('button');copy.type='button';copy.className='t2p-password-copy';copy.hidden=true;
   generate.addEventListener('click',()=>{
    // 20 independently sampled base32 characters = 100 bits, grouped for legibility.
    const alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';const bytes=new Uint8Array(20);crypto.getRandomValues(bytes);
    input.value=Array.from(bytes,b=>alphabet[b&31]).join('').match(/.{5}/g).join('-');
    input.type='password';copy.hidden=false;touched=false;submitted=false;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
   });
   copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(input.value);live.textContent=t('הסיסמה הועתקה. כדאי לשמור אותה במנהל הסיסמאות.','Password copied. Save it in your password manager.');}catch(_){live.textContent=t('לא ניתן להעתיק כאן. אפשר להציג את הסיסמה ולהעתיק ידנית.','Copy is unavailable here. Show the password to copy it manually.');}});
   input.addEventListener('input',()=>{copy.hidden=!input.value;});tools.append(generate,copy);field.append(tools);
   const form=input.form;
   form?.addEventListener('submit',event=>{submitted=true;touched=true;render();if(!inspect(input.value).valid){event.preventDefault();event.stopImmediatePropagation();input.focus();}},true);
   form?.addEventListener('reset',()=>{queueMicrotask(()=>{touched=false;submitted=false;copy.hidden=true;conceal();input.setCustomValidity('');render();});});
   widgets.push(()=>{generate.textContent=t('יצירת סיסמה אקראית','Generate a password');copy.textContent=t('העתקה','Copy');render();});
  }else widgets.push(render);
  widgets.at(-1)();
 }
 function init(){
  document.querySelectorAll('input[type=password]').forEach(mount);
  let language=document.documentElement.lang;
  new MutationObserver(()=>{if(language===document.documentElement.lang)return;language=document.documentElement.lang;widgets.forEach(update=>update());}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  fetch('/frontend/data/password-policy.json',{credentials:'omit'}).then(response=>{if(!response.ok)throw Error();return response.json();}).then(data=>{if(data.min_length===8&&data.max_length===128&&Array.isArray(data.common_passwords)){policy=data;widgets.forEach(update=>update());}}).catch(()=>{});
 }
 window.Talk2PayPasswords={inspect,error};
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
