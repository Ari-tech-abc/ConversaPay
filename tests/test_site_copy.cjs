/* Actual delivery pages: both languages, narrow layouts, labels and script errors. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..');
const rendered=spawnSync(process.env.TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(rendered.status!==0)throw Error(rendered.stderr);const pages=JSON.parse(rendered.stdout);
const names=process.argv.slice(2).length?process.argv.slice(2):Object.keys(pages);
const workspace=['dashboard','profile','settings','upgrade','setup-guide','wordpress','product-import','onboarding'];
function response(endpoint){
 if(endpoint==='/subscription/status')return{plan_type:'pro',is_paid:true,remaining_days:30,subscription_end_date:'2026-11-01'};
 if(endpoint.startsWith('/site-builder/verify/'))return{valid:true};
 if(endpoint==='/businesses')return[{id:'b',business_name:'Sample Store'}];
 if(endpoint==='/auth/me')return{email:'demo@example.com',email_verified:true,profile:{full_name:'Alex'},requires_business_onboarding:false};
 if(endpoint==='/profile')return{email:'demo@example.com',profile:{full_name:'Alex',phone:'0500000000'}};
 if(endpoint==='/profile/notifications')return{preferences:{payment_success:true,weekly_digest:true,security_alerts:true,product_updates:false}};
 if(endpoint==='/dashboard/analytics')return{total_revenue:12480,closed_deals:48,total_conversations:326,conversion_rate:14.7};
 if(endpoint==='/dashboard/orders')return{orders:[{id:'1',order_number:'1048',customer_info:{name:'Alex'},status:'paid',total:249}]};
 if(endpoint==='/products/paged')return{products:[{id:'p',name:'Everyday bag',item_key:'bag',price:249,is_active:true}],total:1,total_pages:1,page:1};
 return{keys:[],orders:[],plan_type:'pro',status:'active',subscription_status:'active',sessions:[],usage:{used:2,limit:1000},limited:false,completed:false};
}
(async()=>{const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});const failures=[],missing={};let checks=0;
try{for(const name of names){
 const context=await browser.newContext({reducedMotion:'reduce'});
 await context.addInitScript(authenticated=>{if(window.top!==window)return;if(!localStorage.getItem('conversapay-language'))localStorage.setItem('conversapay-language','he');if(authenticated)localStorage.setItem('access_token','copy-fixture');sessionStorage.setItem('site_builder_token','copy-builder-fixture');},workspace.includes(name));
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.host!=='copy.test')return route.abort();
  if(url.pathname.startsWith('/api/v1/'))return route.fulfill({contentType:'application/json',body:JSON.stringify(response(url.pathname.slice(7).split('?')[0]))});
  const n=url.pathname==='/'?'home':url.pathname.slice(1);if(pages[n])return route.fulfill({contentType:'text/html',body:pages[n]});
  const file=path.resolve(root,'.'+decodeURIComponent(url.pathname));if(file.startsWith(root+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});return route.fulfill({status:404,body:'Not found'});
 });
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://copy.test/'+name);await page.waitForTimeout(350);
 const legal=['privacy','terms','cookies','refund-policy'].includes(name),originalLinks=legal?await page.locator('.legal-document a').evaluateAll(elements=>elements.map(el=>el.getAttribute('href'))):null;
 for(const language of ['he','en']){
  if(language==='en'){await page.evaluate(()=>{localStorage.setItem('conversapay-language','en');localStorage.setItem('talk2pay_language','en');});await page.reload();await page.waitForTimeout(350);}
  for(const width of [1440,375]){await page.setViewportSize({width,height:1000});const fits=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);if(!fits)failures.push(`${name} ${language} ${width}: horizontal overflow`);checks++;
   if(name==='cookies'&&width===375)assert.equal(await page.locator('.legal-table-scroll').evaluate(el=>el.scrollWidth>el.clientWidth),true,'Mobile cookie table scrolls within its own region');
   await page.screenshot({path:path.join(root,'docs/design-preview/live-review',`${name}-copy-${language}-${width}.png`),fullPage:true});
  }
  if(legal){assert.equal(await page.locator('.legal-document h2').count(),({privacy:13,terms:14,cookies:6,'refund-policy':6})[name]);assert.deepEqual(await page.locator('.legal-document a').evaluateAll(elements=>elements.map(el=>el.getAttribute('href'))),originalLinks,'Legal links survive translation');assert.equal((await page.locator('.legal-document').textContent()).includes('data-i18n-'),false);checks++;}
  if(name==='onboarding'){await page.locator('.category-card').first().click();await page.locator('#toInstructions').click();await page.locator('#finish').click();await page.locator('#upgradeLayer.show').waitFor();await page.screenshot({path:path.join(root,'docs/design-preview/live-review',`${name}-plans-${language}.png`),fullPage:true});checks++;}
  if(name==='upgrade'){await page.locator('#openCancel').click();await page.locator('#cancelLayer.show').waitFor();assert.equal(await page.locator('#requestRefund').evaluate(el=>el.getBoundingClientRect().width<=24),true,'Refund checkbox retains its natural size');await page.screenshot({path:path.join(root,'docs/design-preview/live-review',`${name}-cancel-${language}.png`),fullPage:true});checks++;}
  if(name==='home'&&language==='en')assert.equal(await page.locator('.hero-copy').evaluate(el=>getComputedStyle(el).direction),'ltr','English hero uses left-to-right punctuation');
  if(name==='setup-guide'){for(const tab of ['wordpress','test']){await page.locator('#tab-'+tab).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Guide tab fits mobile');await page.screenshot({path:path.join(root,'docs/design-preview/live-review',`${name}-${tab}-${language}.png`),fullPage:true});checks++;}}
  if(name==='dashboard'){assert.equal(await page.locator('#productSummary').textContent(),language==='en'?'1 product in your catalog':'מוצר אחד בקטלוג');assert.equal(await page.locator('.orders .status').textContent(),language==='en'?'Paid':'שולם');await page.locator('#addProduct').click();await page.screenshot({path:path.join(root,'docs/design-preview/live-review',`${name}-product-${language}.png`),fullPage:true});checks++;}
  if(language==='en'){
   const items=await page.evaluate(()=>{const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),result=[];let n;while(n=walker.nextNode()){const el=n.parentElement;if(el&&!el.closest('script,style,code,pre,textarea,.messages,.msg,#keyValue,#keyList strong,#keyList small,#userName,#businessName,.item strong,input,[data-cp-language-toggle]')&&/[\u0590-\u05ff]/.test(n.nodeValue)&&n.nodeValue.trim()!=='עברית')result.push(n.nodeValue.trim());}for(const el of document.querySelectorAll('[placeholder],[aria-label]'))for(const attr of ['placeholder','aria-label']){const value=el.getAttribute(attr);if(value&&/[\u0590-\u05ff]/.test(value))result.push(value);}return [...new Set(result)];});if(items.length)missing[name]=items;checks++;
  }
 }
 if(errors.length)failures.push(name+': '+errors.join(', '));await context.close();console.log('Reviewed: '+name);
}
fs.writeFileSync(path.join(root,'docs/design-preview/live-review/missing-translations.json'),JSON.stringify(missing,null,2));
if(Object.keys(missing).length)failures.push('Untranslated copy: '+JSON.stringify(missing));assert.deepEqual(failures,[]);console.log(`PASS: ${checks} bilingual/layout checks across ${names.length} pages`);
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
