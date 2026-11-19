/* Explicit confirmation and fulfillment details for the dashboard preview. */
(() => {
 window.Talk2PayQuoteCard=(action,root,submit)=>{
  if(!action?.confirmation_token)return;
  root.querySelectorAll('[data-quote-confirm]').forEach(button=>button.disabled=true);
  const english=action.locale==='en',form=document.createElement('form');form.className='msg bot';form.dir=english?'ltr':'rtl';
  const fields={},definitions=[['name','שם מלא','Full name','text'],['email','אימייל','Email','email'],['phone','טלפון','Phone','tel']];
  if(action.fulfillment==='delivery')definitions.push(['address','כתובת מלאה למשלוח','Delivery address','text']);
  for(const [key,he,en,type] of definitions){const label=document.createElement('label'),input=document.createElement('input');label.textContent=english?en:he;input.name=key;input.type=type;input.required=true;input.minLength=key==='address'?5:key==='phone'?7:1;input.maxLength=key==='address'?1000:key==='phone'?30:160;input.autocomplete=({name:'name',email:'email',phone:'tel',address:'street-address'})[key];input.className='cp-input';input.style.cssText='display:block;box-sizing:border-box;width:100%;min-height:44px;margin:6px 0 12px';label.append(input);form.append(label);fields[key]=input;}
  const button=document.createElement('button');button.type='submit';button.dataset.quoteConfirm='true';button.className='cp-button';button.textContent=english?'Confirm quote and create payment link':'אישור ההצעה ויצירת קישור תשלום';form.append(button);
  form.onsubmit=async event=>{event.preventDefault();if(button.disabled||!form.reportValidity())return;button.disabled=true;button.setAttribute('aria-busy','true');await submit(action.confirmation_token,Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.value.trim()])));button.removeAttribute('aria-busy');};
  root.append(form);root.scrollTop=root.scrollHeight;
 };
})();
