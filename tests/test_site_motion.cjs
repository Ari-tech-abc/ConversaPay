const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..');
const fixture=spawnSync(process.env.TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(fixture.status)throw Error(fixture.stderr);
const pages=JSON.parse(fixture.stdout),bid='00000000-0000-4000-8000-000000000001';
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});let checks=0;
 const check=(a,b)=>{assert.deepEqual(a,b);checks++;};
 const shot=path.join(root,'docs/design-preview/live-review');fs.mkdirSync(shot,{recursive:true});
 try{
  for(const width of [1440,375])for(const reduced of [false,true]){
   const context=await browser.newContext({viewport:{width,height:900},reducedMotion:reduced?'reduce':'no-preference'}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   let release=null,fail=false;
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(url.host!=='motion.test')return route.abort();
    const name=url.pathname.slice(1);
    if(pages[name])return route.fulfill({contentType:'text/html',body:pages[name]});
    if(url.pathname.startsWith('/api/v1/')){
     const ep=url.pathname.slice(7);let body={},status=200;
     if(ep.startsWith('/businesses/')&&route.request().method()==='PATCH'){
      await new Promise(resolve=>release=resolve);status=fail?503:200;body=fail?{detail:'Save failed'}:{id:bid,business_name:'New store'};
     }else if(ep==='/businesses')body=[{id:bid,business_name:'Store'}];
     else if(ep==='/auth/me')body={email:'owner@example.com',profile:{full_name:'Owner'}};
     else if(ep==='/profile/notifications')body={preferences:{payment_success:true},delivery:{enabled:false}};
     else if(ep==='/profile/billing')body={plan_type:'pro',usage:{available:true,used:1}};
     else if(ep==='/products/paged')body={products:[{id:'p1',name:'One',item_key:'ONE',price:1},{id:'p2',name:'Two',item_key:'TWO',price:2}],total:2,total_pages:1};
     else body={plan_type:'pro',keys:[],orders:[],sessions:[],profile:{full_name:'Owner'},limited:false};
     return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    }
    const file=path.join(root,name);if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});return route.abort();
   });
   await page.goto('http://motion.test/home');await page.waitForSelector('.t2p-hero-light');
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   check(await page.locator('.t2p-hero-light span').count(),2);
   check(await page.locator('.t2p-hero-light span').first().evaluate((el,reduced)=>reduced?getComputedStyle(el).animationName:getComputedStyle(el).animationPlayState,reduced),reduced?'none':'running');
   if(!reduced){await page.locator('[data-t2p-motion]').click();await page.waitForFunction(()=>!document.querySelector('.hero-frame').classList.contains('t2p-motion-running'));check(await page.locator('.t2p-hero-light span').first().evaluate(el=>getComputedStyle(el).animationPlayState),'paused');}
   await page.locator('#capabilities').scrollIntoViewIfNeeded();await page.waitForSelector('[data-motion-revealed]');
   await page.waitForFunction(()=>getComputedStyle(document.querySelector('.section-title')).opacity==='1');check(await page.locator('.section-title').first().evaluate(el=>getComputedStyle(el).opacity),'1');
   await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.waitForTimeout(500);await page.screenshot({path:path.join(shot,`motion-home-${width}-${reduced}.png`)});
   await page.evaluate(()=>localStorage.removeItem('access_token'));await page.goto('http://motion.test/login');await page.waitForSelector('.t2p-auth-shell');
   const link=page.locator('a[href="/register"]').first();await link.click();await page.waitForURL('**/register');await page.waitForSelector('#register-form');check(await page.locator('#register-form').isVisible(),true);
   await page.locator('a[href="/login"]').first().click();await page.waitForURL('**/login');check(await page.locator('#login-form').isVisible(),true);
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.evaluate(()=>localStorage.setItem('access_token','offline'));await page.goto('http://motion.test/settings');await page.waitForFunction(()=>!document.querySelector('#saveBusiness').disabled);
   await page.locator('#businessName').fill('New store');await page.locator('#saveBusiness').click();await page.waitForFunction(()=>document.querySelector('#saveBusiness').dataset.saving==='true');
   check(await page.locator('#saveBusiness').getAttribute('aria-busy'),'true');check(await page.locator('#saveBusiness').getAttribute('data-saved'),null);
   release();await page.waitForFunction(()=>document.querySelector('#saveBusiness').dataset.saved==='true');check(await page.locator('#saveBusiness').isDisabled(),false);
   fail=true;await page.locator('#saveBusiness').click();await page.waitForFunction(()=>document.querySelector('#saveBusiness').dataset.saving==='true');release();await page.waitForFunction(()=>!document.querySelector('#saveBusiness').disabled);
   check(await page.locator('#saveBusiness').getAttribute('data-saved'),null);check(await page.locator('#saveBusiness').getAttribute('aria-busy'),null);
   await page.goto('http://motion.test/dashboard');await page.waitForFunction(()=>document.querySelectorAll('[data-select-product]').length===2);
   await page.locator('#widgetFab').click();check(await page.locator('#widgetPanel').evaluate(el=>el.inert),false);
   await page.locator('#widgetClose').click();await page.waitForFunction(()=>document.querySelector('#widgetPanel').hidden);check(await page.evaluate(()=>document.activeElement.id),'widgetFab');
   await page.evaluate(()=>{const p=document.querySelector('#widgetPanel');Talk2PayMotion.panel(p,true);Talk2PayMotion.panel(p,false);Talk2PayMotion.panel(p,true)});
   await page.waitForTimeout(300);check(await page.locator('#widgetPanel').evaluate(el=>el.hidden||el.inert),false);
   if(!reduced){await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(50);check(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0);}
   check(errors,[]);await context.close();
  }
  console.log(`PASS: ${checks} motion browser checks for home, auth navigation, save success/failure, widget interruption, mobile and reduced motion`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
