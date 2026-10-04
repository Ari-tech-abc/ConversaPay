/* Shared navigation, inline validation and the marketing conversation demo. */
(() => {
 'use strict';
 const icons={overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',box:'<path d="m12 3 9 5-9 5-9-5 9-5Zm9 5v10l-9 5-9-5V8m9 5v10M7.5 5.5l9 5"/>',bag:'<path d="M5 7h14l1 14H4L5 7Zm3 1V6a4 4 0 0 1 8 0v2"/>',profile:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',settings:'<path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',card:'<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20M6 15h4"/>',guide:'<path d="M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3V4Zm9 2v15"/>',chat:'<path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-7l-6 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="m8 11 3 3 5-6"/>',import:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',check:'<path d="m5 12 4 4L19 6"/>',menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',pause:'<path d="M8 5v14M16 5v14"/>',play:'<path d="m7 4 13 8-13 8V4Z"/>'};
 const svg=name=>'<svg class="t2p-icon" viewBox="0 0 24 24" aria-hidden="true">'+icons[name]+'</svg>';
 const english=()=>document.documentElement.lang==='en';
 const text=(he,en)=>english()?en:he;
 const label=(he,en)=>'<span data-i18n-he="'+he+'" data-i18n-en="'+en+'">'+text(he,en)+'</span>';
 const links=[
  ['/dashboard','סקירה כללית','Overview','overview'],['/dashboard#productCard','מוצרים','Products','box'],['/dashboard#ordersCard','הזמנות','Orders','bag'],['/product-import','ייבוא מוצרים','Import products','import'],
  ['/profile','פרופיל','Profile','profile'],['/settings','הגדרות','Settings','settings'],['/upgrade','מסלולים וחיוב','Plans and billing','card'],
  ['/setup-guide','מדריך הטמעת הווידגט','Widget installation guide','guide'],['/wordpress','הטמעה ב־WordPress','WordPress integration','guide'],['/onboarding','הגדרת עוזר AI','AI assistant setup','chat'],['/settings#api-settings','API ואינטגרציות','API and integrations','settings'],['/settings#whatsapp-settings','חיבור WhatsApp','WhatsApp connection','chat']
 ];
 const workspacePages=new Set(['dashboard','settings','profile','upgrade','setup-guide','wordpress','product-import','onboarding']);
 function initWorkspace(){
  const page=document.body.dataset.t2pPage;
  if(!workspacePages.has(page))return;
  const sidebar=document.createElement('aside');sidebar.className='t2p-sidebar';sidebar.id='t2p-workspace-nav';
  sidebar.innerHTML='<a class="cp-brand" href="/dashboard"><span class="cp-brand-mark" aria-hidden="true">'+svg('chat')+'</span><span>Talk2Pay</span></a><nav class="t2p-nav" aria-label="'+text('סביבת העבודה','Workspace')+'">'+links.map((link,index)=>(index===4?'<p class="t2p-nav-label">'+label('חשבון ועסק','Account and business')+'</p>':index===7?'<p class="t2p-nav-label">'+label('חיבורים והטמעה','Connections and setup')+'</p>':'')+'<a href="'+link[0]+'">'+svg(link[3])+label(link[1],link[2])+'</a>').join('')+'</nav><footer class="t2p-nav-footer"><a href="/">'+label('דף הבית','Home')+'</a><a href="/privacy">'+label('פרטיות','Privacy')+'</a><a href="/terms">'+label('תנאי שימוש','Terms')+'</a></footer>';
  const mobile=document.createElement('header');mobile.className='t2p-mobile-header';mobile.innerHTML='<a class="cp-brand" href="/dashboard"><span class="cp-brand-mark" aria-hidden="true">'+svg('chat')+'</span><span>Talk2Pay</span></a><button type="button" aria-controls="t2p-workspace-nav" aria-expanded="false" aria-label="'+text('פתיחת תפריט ניווט','Open navigation menu')+'">'+svg('menu')+'</button>';
  const backdrop=document.createElement('button');backdrop.className='t2p-nav-backdrop';backdrop.tabIndex=-1;backdrop.setAttribute('aria-label',text('סגירת תפריט','Close menu'));
  const app=document.querySelector('.app');
  if(page==='dashboard'&&app){
   const side=document.querySelector('.side');side.prepend(sidebar);const plan=document.getElementById('sideBottom');if(plan)sidebar.insertBefore(plan,sidebar.querySelector('footer'));
   document.body.insertBefore(mobile,app);
  }else{
   const main=document.querySelector('body>main'),topbar=document.querySelector('body>.cp-topbar,body>.ob-topbar');
   if(!main)return;
   const shell=document.createElement('div');shell.className='t2p-workspace';const content=document.createElement('div');content.className='t2p-workspace-main';
   document.body.insertBefore(shell,topbar||main);shell.append(sidebar,content);if(topbar)content.append(topbar);content.append(main);document.body.insertBefore(mobile,shell);
  }
  document.body.append(backdrop);
  const menuButton=mobile.querySelector('button');let previousFocus=null;
  function close(){document.body.classList.remove('t2p-nav-open');menuButton.setAttribute('aria-expanded','false');sidebar.removeAttribute('role');sidebar.removeAttribute('aria-modal');if(previousFocus?.isConnected&&innerWidth<=900)previousFocus.focus();previousFocus=null;}
  menuButton.addEventListener('click',()=>{if(document.body.classList.contains('t2p-nav-open'))return close();previousFocus=document.activeElement;document.body.classList.add('t2p-nav-open');menuButton.setAttribute('aria-expanded','true');sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');sidebar.setAttribute('aria-label',text('תפריט ניווט','Navigation menu'));sidebar.querySelector('a').focus();});
  backdrop.addEventListener('click',close);sidebar.addEventListener('click',event=>{if(event.target.closest('a'))close();});
  document.addEventListener('keydown',event=>{if(!document.body.classList.contains('t2p-nav-open'))return;if(event.key==='Escape'){event.preventDefault();close();}if(event.key==='Tab'){const focusables=[...sidebar.querySelectorAll('a[href],button:not(:disabled)')].filter(el=>el.getClientRects().length);const first=focusables[0],last=focusables.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
  matchMedia('(min-width:901px)').addEventListener('change',event=>{if(event.matches)close();});
  function current(){const pathname=location.pathname.replace(/\.html$/,'');sidebar.querySelectorAll('.t2p-nav a').forEach(a=>{const url=new URL(a.href);const selected=url.pathname===pathname&&(url.hash?url.hash===location.hash:!location.hash);if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
  current();window.addEventListener('hashchange',current);
 }
 function initValidation(){
  let errorIndex=0;const errors=new WeakMap();
  function clear(field){const message=errors.get(field);if(!message)return;const ids=(field.getAttribute('aria-describedby')||'').split(' ').filter(id=>id&&id!==message.id);if(ids.length)field.setAttribute('aria-describedby',ids.join(' '));else field.removeAttribute('aria-describedby');field.removeAttribute('aria-invalid');field.classList.remove('t2p-invalid');message.remove();errors.delete(field);}
  function explain(field){const validity=field.validity;if(validity.valueMissing)return field.type==='checkbox'?text('יש לאשר כדי להמשיך.','Please confirm to continue.'):text('יש למלא את השדה.','Please fill in this field.');if(validity.typeMismatch)return field.type==='email'?text('יש להזין כתובת אימייל תקינה.','Enter a valid email address.'):text('יש להזין כתובת תקינה.','Enter a valid URL.');if(validity.tooShort)return text('יש להזין לפחות '+field.minLength+' תווים.','Enter at least '+field.minLength+' characters.');if(validity.rangeUnderflow)return text('הערך המינימלי הוא '+field.min+'.','The minimum value is '+field.min+'.');if(validity.rangeOverflow)return text('הערך המקסימלי הוא '+field.max+'.','The maximum value is '+field.max+'.');return text('יש לבדוק את הערך שהוזן.','Please check the entered value.');}
  function show(field){clear(field);const message=document.createElement('span');message.id='t2p-field-error-'+(++errorIndex);message.className='t2p-field-error';message.textContent=explain(field);field.classList.add('t2p-invalid');field.setAttribute('aria-invalid','true');field.setAttribute('aria-describedby',((field.getAttribute('aria-describedby')||'')+' '+message.id).trim());const parent=field.closest('.cp-field,.field,.builder-field,.form-field');if(parent)parent.append(message);else field.insertAdjacentElement('afterend',message);errors.set(field,message);}
  const prepare=form=>{if(form.dataset.t2pValidation)return;form.dataset.t2pValidation='true';form.noValidate=true;};
  document.querySelectorAll('form').forEach(prepare);
  document.addEventListener('submit',event=>{const form=event.target;if(!(form instanceof HTMLFormElement))return;const invalid=[...form.elements].filter(field=>field.willValidate&&!field.validity.valid);if(invalid.length){event.preventDefault();event.stopImmediatePropagation();invalid.forEach(show);invalid[0].focus();}},true);
  document.addEventListener('invalid',event=>{if(event.target.form){event.preventDefault();show(event.target);}},true);
  document.addEventListener('input',event=>{if(errors.has(event.target)&&event.target.validity.valid)clear(event.target);});
  document.addEventListener('change',event=>{if(errors.has(event.target)&&event.target.validity.valid)clear(event.target);});
  new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1){if(node.matches('form'))prepare(node);node.querySelectorAll('form').forEach(prepare);}}).observe(document.body,{childList:true,subtree:true});
 }
 function initDemo(){
  const scene=document.querySelector('[data-t2p-demo]');if(!scene)return;
  const reduced=matchMedia('(prefers-reduced-motion:reduce)');let timer=null,visible=false,paused=false;
  const control=document.querySelector('[data-t2p-motion]');
  function cancel(){clearTimeout(timer);timer=null;scene.classList.remove('t2p-demo-resetting');}
  function allowed(){return visible&&!document.hidden&&!paused&&!reduced.matches;}
  function schedule(){cancel();if(!allowed())return;timer=setTimeout(()=>{if(!allowed())return;scene.classList.add('t2p-demo-resetting');timer=setTimeout(()=>{if(!allowed()){cancel();return;}scene.classList.remove('t2p-demo-playing');void scene.offsetWidth;scene.classList.remove('t2p-demo-resetting');scene.classList.add('t2p-demo-playing');schedule();},750);},13500);}
  function update(){cancel();if(paused||reduced.matches){scene.classList.remove('t2p-demo-playing');}else if(allowed()){scene.classList.add('t2p-demo-playing');schedule();}if(control){const stopped=paused||reduced.matches;control.setAttribute('aria-pressed',String(stopped));control.setAttribute('aria-label',stopped?text('הפעלת האנימציות','Play animations'):text('עצירת האנימציות','Pause animations'));control.innerHTML=svg(stopped?'play':'pause');}}
  control?.addEventListener('click',()=>{paused=!paused;update();});
  reduced.addEventListener('change',update);document.addEventListener('visibilitychange',update);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;update();},{threshold:.15}).observe(scene);
  update();
 }
 function initAuth(){
  const page=document.body.dataset.t2pPage;if(!['login','register'].includes(page))return;
  const main=document.querySelector('body>main');if(!main)return;
  main.classList.add('t2p-auth-shell');
  const story=document.createElement('aside');story.className='t2p-auth-story';
  story.innerHTML='<div class="t2p-auth-copy"><span class="cp-kicker">Talk2Pay</span><h2>'+label('מהשיחה עם הלקוח ועד לתשלום.','From customer conversation to payment.')+'</h2><div class="t2p-auth-journey"><div>'+svg('chat')+label('שיחות','Conversations')+'</div><span aria-hidden="true"></span><div>'+svg('box')+label('מוצרים','Products')+'</div><span aria-hidden="true"></span><div>'+svg('check')+label('תשלום','Payment')+'</div></div></div>';
  main.prepend(story);
 }
 function init(){initWorkspace();initAuth();initValidation();initDemo();
  const page=document.body.dataset.t2pPage;
  if(page==='dashboard'){
   const product=document.getElementById('productCard');const order=document.getElementById('orders')?.closest('article');if(order)order.id='ordersCard';
   // Authenticated data loads asynchronously; preserve deep links once their section is visible.
   if(['#productCard','#ordersCard'].includes(location.hash)){const content=document.getElementById('content');const observer=new MutationObserver(()=>{if(getComputedStyle(content).visibility==='visible'){document.querySelector(location.hash)?.scrollIntoView({block:'start'});observer.disconnect();}});observer.observe(content,{attributes:true,attributeFilter:['style']});}
  }
  if(page==='settings'){const sections=document.querySelectorAll('.settings-shell>section');['settings-overview','business-settings','security-settings','notification-settings','billing-settings','api-settings','privacy-settings'].forEach((id,index)=>{if(sections[index])sections[index].id=id;});}
  const reduced=matchMedia('(prefers-reduced-motion:reduce)');if(!window.Talk2PayMotion&&!reduced.matches){const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('t2p-enter');observer.unobserve(entry.target);}});},{threshold:.1});document.querySelectorAll('.cp-card,.cap-row,.plan,.stat').forEach(el=>observer.observe(el));}
 }
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
