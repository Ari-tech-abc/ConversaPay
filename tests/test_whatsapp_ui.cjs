const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process'),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..'),fixtures=spawnSync(process.env.TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(fixtures.status)throw Error(fixtures.stderr);const pages=JSON.parse(fixtures.stdout),bid='00000000-0000-4000-8000-000000000001';
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});let checks=0;
 const check=(a,b)=>{assert.deepEqual(a,b);checks++;};
 try{for(const language of ['he','en'])for(const width of [1440,375]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  let configured=false,verified=false,serverReady=true,fail=false,last=null,saves=[];
  await page.addInitScript(language=>{localStorage.setItem('access_token','offline');localStorage.setItem('conversapay-language',language);},language);
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());if(u.host!=='wa.test')return route.abort();
   if(u.pathname==='/settings')return route.fulfill({contentType:'text/html',body:pages.settings});
   if(u.pathname.startsWith('/api/v1/')){
    let data={},status=200;
    if(u.pathname==='/api/v1/businesses')data=[{id:bid,business_name:'Store'}];
    else if(u.pathname==='/api/v1/auth/me')data={email:'owner@example.com',profile:{full_name:'Owner'}};
    else if(u.pathname==='/api/v1/profile/notifications')data={preferences:{},delivery:{enabled:false}};
    else if(u.pathname==='/api/v1/profile/billing')data={plan_type:'free',subscription_status:'active',usage:{available:true,used:0}};
    else if(u.pathname==='/api/v1/api-keys')data={keys:[],locked:true};
    else if(u.pathname==='/api/v1/integrations/whatsapp'){
     check(route.request().headers().authorization,'Bearer offline');
     if(route.request().method()==='PUT'){
      const payload=route.request().postDataJSON();saves.push(payload);
      if(fail){status=422;data={detail:{code:'meta_190'}};}else{configured=true;verified=false;data={verify_token:'offline-verify-secret'};}
     }else if(route.request().method()==='DELETE'){configured=false;verified=false;last=null;}
     if(status===200)data={...data,server_ready:serverReady,configured,mode:'test',phone_number_id:configured?'123456789012345':null,test_recipients:configured?['972501234567']:null,webhook_url:configured?'https://wa.test/api/v1/webhooks/whatsapp/test-connection':null,verified_at:verified?'2026-10-04T00:00:00Z':null,last_message:last};
    }
    return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
   }
   const file=path.join(root,u.pathname.slice(1));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});return route.abort();
  });
  await page.goto('http://wa.test/settings#whatsapp-settings');await page.locator('#waSave').waitFor();await page.waitForFunction(()=>!document.getElementById('waSave').disabled);
  check(await page.locator('#whatsapp-settings .wa-guide li').count(),6);
  check(await page.locator('#waStatus').textContent(),language==='en'?'You can now save your test number details.':'אפשר לשמור את פרטי מספר הבדיקה.');
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('.wa-guide summary').click();check(await page.locator('.wa-guide ol').isVisible(),true);
  if(language==='en')check(await page.locator('#whatsapp-settings').evaluate(el=>/[\u0590-\u05ff]/.test(el.innerText)),false);
  await page.locator('#waPhone').fill('123456789012345');await page.locator('#waAccess').fill('offline-access-token-123456');await page.locator('#waRecipients').fill('972501234567\n972501234567');await page.locator('#waSave').click();check(saves.length,0);check(await page.locator('#waError').isVisible(),true);
  await page.locator('#waRecipients').fill('+972501234567');await page.locator('#waSave').click();await page.waitForFunction(()=>document.getElementById('waVerify').value==='offline-verify-secret');
  check(saves[0].business_id,bid);check(saves[0].test_recipients,['+972501234567']);check(await page.locator('#waAccess').inputValue(),'');check(await page.locator('#waVerify').getAttribute('type'),'password');
  check(await page.evaluate(()=>JSON.stringify(localStorage).includes('offline-verify-secret')||JSON.stringify(localStorage).includes('offline-access-token')),false);
  check(await page.locator('#waStatus').textContent(),language==='en'?'Details saved. Verify the webhook in Meta before receiving messages.':'הפרטים נשמרו. נדרש אימות Webhook ב־Meta לפני קבלת הודעות.');
  verified=true;last={status:'accepted'};await page.locator('#waRefresh').click();await page.waitForFunction(()=>!document.getElementById('waRefresh').disabled);
  check((await page.locator('#waStatus').textContent()).includes(language==='en'?'Delivery is not confirmed':'אין אישור מסירה'),true);
  last={status:'delivered'};await page.locator('#waRefresh').click();await page.waitForFunction(()=>!document.getElementById('waRefresh').disabled);
  check((await page.locator('#waStatus').textContent()).includes(language==='en'?'delivered to the phone':'נמסר לטלפון'),true);
  await page.locator('[data-cp-language-toggle]').click();await page.waitForFunction(language=>document.documentElement.lang!==language,language);await page.waitForFunction(language=>document.getElementById('waStatus').textContent.includes(language==='he'?'delivered to the phone':'נמסר לטלפון'),language);check(true,true);await page.locator('[data-cp-language-toggle]').click();await page.waitForFunction(language=>document.documentElement.lang===language,language);await page.locator('.wa-guide summary').click();
  const out=path.join(root,'docs/design-preview/live-review');fs.mkdirSync(out,{recursive:true});await page.locator('#whatsapp-settings').evaluate(el=>scrollTo({top:el.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));await page.screenshot({path:path.join(out,`whatsapp-${language}-${width}.png`)});
  fail=true;await page.locator('#waAccess').fill('offline-expired-token-123456');await page.locator('#waSave').click();await page.waitForFunction(()=>!document.getElementById('waSave').disabled);
  check((await page.locator('#waError').textContent()).includes(language==='en'?'invalid or expired':'אינו תקף או שפג'),true);check(await page.locator('#waSave').getAttribute('data-saved'),null);
  await page.locator('#waDisconnect').click();await page.waitForFunction(()=>document.getElementById('waDisconnect').hidden);check(await page.locator('#waVerify').inputValue(),'');check(await page.locator('#waAccess').inputValue(),'');
  serverReady=false;await page.locator('#waRefresh').click();await page.waitForFunction(()=>!document.getElementById('waRefresh').disabled);
  check(await page.locator('#waSave').isDisabled(),true);check((await page.locator('#waStatus').textContent()).includes(language==='en'?'not enabled':'לא הופעל'),true);check(await page.locator('.wa-guide summary').isEnabled(),true);check(errors,[]);
  await page.close();
 }}finally{await browser.close();}
 console.log(`PASS: ${checks} WhatsApp setup browser checks in Hebrew/English at 1440px and 375px`);
})().catch(error=>{console.error(error);process.exitCode=1;});
