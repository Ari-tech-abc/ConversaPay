/* Browser coverage for the cross-page theme, workspace and demo behavior. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..');
const rendered=spawnSync(process.env.TEST_PYTHON||'python',[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(rendered.status!==0)throw Error(rendered.stderr);
const pages=JSON.parse(rendered.stdout);
const screenshotDir=path.join(root,'docs/design-preview/live-review');fs.mkdirSync(screenshotDir,{recursive:true});
const workspace=['dashboard','profile','settings','upgrade','setup-guide','wordpress','product-import','onboarding'];
const screenshots=new Set(['home','dashboard','settings','profile','login','register','setup-guide','upgrade','onboarding','product-import']);
const business={id:'b',business_name:'הסטודיו של נועה'};
function response(endpoint){
 if(endpoint==='/businesses')return[business];
 if(endpoint==='/auth/me')return{email:'demo@example.com',email_verified:true,profile:{full_name:'נועה'},requires_business_onboarding:false};
 if(endpoint==='/profile')return{email:'demo@example.com',profile:{full_name:'נועה',phone:'0500000000'}};
 if(endpoint==='/profile/notifications')return{preferences:{payment_success:true,weekly_digest:true,security_alerts:true,product_updates:false}};
 if(endpoint==='/dashboard/analytics')return{total_revenue:12480,closed_deals:48,total_conversations:326,conversion_rate:14.7};
 if(endpoint==='/dashboard/orders')return{orders:[{id:'1',order_number:'1048',customer_info:{name:'מאיה לוי'},status:'paid',total:249},{id:'2',order_number:'1047',customer_info:{name:'דניאל כהן'},status:'pending',total:580}]};
 if(endpoint==='/products/paged')return{products:[{id:'p',name:'תיק Everyday',item_key:'everyday_bag',price:249,is_active:true}],total:1,total_pages:1,page:1};
 return{keys:[],orders:[],plan_type:'pro',status:'active',sessions:[],usage:{used:2,limit:1000},limited:false,completed:false};
}
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});let checks=0;const failures=[];
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.host!=='design.test')return route.abort();
   if(url.pathname.startsWith('/api/v1/'))return route.fulfill({contentType:'application/json',body:JSON.stringify(response(url.pathname.slice(7).split('?')[0]))});
   const name=url.pathname==='/'?'home':url.pathname.replace(/^\//,'').replace(/\.html$/,'');
   if(pages[name])return route.fulfill({contentType:'text/html',body:pages[name]});
   const file=path.join(root,decodeURIComponent(url.pathname.slice(1)));if(file.startsWith(root)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});
   return route.fulfill({status:404,body:'Not found'});
  });
  for(const name of Object.keys(pages)){
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.addInitScript(authenticated=>{if(window.top!==window)return;localStorage.clear();sessionStorage.clear();if(authenticated)localStorage.setItem('access_token','design-fixture');},workspace.includes(name));
   await page.goto('http://design.test/'+(name==='home'?'':name));
   await page.waitForTimeout(250);
   if(name==='dashboard')await page.waitForFunction(()=>document.querySelector('#businessName').textContent==='הסטודיו של נועה');
   for(const width of [1440,768,375]){
    await page.setViewportSize({width,height:1000});
    const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
    if(dimensions.scroll>dimensions.viewport){const items=await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(el=>el.tagName+'.'+el.className));failures.push(`${name} ${width}px overflow ${JSON.stringify(dimensions)} ${items}`);}
    checks++;
    if(screenshots.has(name)&&(width===1440||width===375))await page.screenshot({path:path.join(screenshotDir,`${name}-${width}.png`),fullPage:true});
   }
   if(workspace.includes(name)){
    const button=page.locator('.t2p-mobile-header button');await button.click();assert.equal(await button.getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await button.getAttribute('aria-expanded'),'false');checks++;
    assert.equal(await page.locator('.t2p-nav a[href="/profile"]').count(),1);assert.equal(await page.locator('.t2p-nav a[href="/settings"]').count(),1);assert.equal(await page.locator('.t2p-nav a[href="/setup-guide"]').count(),1);checks++;
   }
   if(errors.length)failures.push(name+' JavaScript: '+errors.join(', '));
   console.log('Checked: '+name);await page.close();
  }
  const page=await context.newPage();await page.addInitScript(()=>{localStorage.clear();sessionStorage.clear();});await page.goto('http://design.test/register');await page.locator('#submit').click();assert.equal(await page.locator('.t2p-field-error').count()>0,true);assert.equal(await page.locator('#name').getAttribute('aria-invalid'),'true');await page.locator('#name').fill('נועה');assert.equal(await page.locator('#name').getAttribute('aria-invalid'),null);checks++;
  await page.goto('http://design.test/');assert.equal(await page.evaluate(()=>document.getAnimations().length),0);checks++;
  await page.emulateMedia({reducedMotion:'no-preference'});await page.reload();await page.locator('[data-t2p-demo]').scrollIntoViewIfNeeded();await page.waitForFunction(()=>document.querySelector('[data-t2p-demo]').classList.contains('t2p-demo-playing'));
  await page.waitForFunction(()=>document.querySelector('[data-t2p-demo]').classList.contains('t2p-demo-resetting'),{timeout:20000});
  await page.waitForFunction(()=>!document.querySelector('[data-t2p-demo]').classList.contains('t2p-demo-resetting'));checks++;
  await page.locator('[data-t2p-motion]').click();assert.equal(await page.locator('[data-t2p-motion]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('[data-t2p-demo]').evaluate(el=>el.classList.contains('t2p-demo-playing')),false);checks++;
  if(failures.length)throw Error(failures.join('\n'));
  console.log(`PASS: ${checks} theme/layout/navigation/validation/motion checks across ${Object.keys(pages).length} actual delivery pages`);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
