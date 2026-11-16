/* Exercise account billing flows with mocked APIs and no live transactions. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const rendered = spawnSync(process.env.TEST_PYTHON, [path.join(__dirname,'render_frontend_fixtures.py')], {cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
assert.equal(rendered.status,0,rendered.stderr);
const html = JSON.parse(rendered.stdout).upgrade;
(async()=>{
 const browser = await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 try {
  for (const language of ['he','en']) {
   const context = await browser.newContext({viewport:{width:375,height:900}});
   await context.addInitScript(language=>{localStorage.setItem('access_token','offline');localStorage.setItem('conversapay-language',language);},language);
   let pending = null, writes = [], state = {plan_type:'pro',is_paid:true,remaining_days:20,subscription_end_date:'2099-01-01',next_billing_at:'2099-01-01',auto_renew:true,subscription_status:'active',provider_subscription_id:'sub_one',can_cancel:true,checkout_available:false,plan_change_request_available:true};
   await context.route('**/*',route=>{
    const url = new URL(route.request().url());
    if(url.host!=='billing.test')return route.abort();
    if(url.pathname.startsWith('/api/v1/')){
     let data={}; const endpoint=url.pathname.slice('/api/v1'.length), method=route.request().method();
     if(endpoint==='/subscription/status')data=state;
     else if(endpoint==='/subscription/history')data={invoices:[{id:'in_one',status:'paid',amount_minor:20000,currency:'ILS',occurred_at:'2026-11-01T10:00:00Z'}],plan_change_request:pending,cancellation:null};
     else if(endpoint==='/subscription/plan-change'&&method==='POST'){
      writes.push(endpoint); const body=route.request().postDataJSON();
      pending={id:'00000000-0000-4000-8000-000000000010',requested_plan:body.plan_type,status:'requested'};
      data={request:pending,provider_confirmed:false,effective_at:null,charge_created:false};
     } else if(endpoint.startsWith('/subscription/plan-change/')&&method==='DELETE'){writes.push(endpoint);pending=null;data={withdrawn:true};}
     else throw Error('Unexpected API: '+endpoint);
     return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    }
    if(url.pathname==='/upgrade')return route.fulfill({contentType:'text/html',body:html});
    const file=path.resolve(root,'.'+url.pathname);
    if(file.startsWith(root+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});
    return route.fulfill({status:404,body:''});
   });
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://billing.test/upgrade');
   await page.locator('#planRequestArea').waitFor({state:'visible'});
   assert.match(await page.locator('#billingHistory').textContent(),language==='he'?/שולם/:/Paid/);
   assert.equal(await page.locator('[data-plan="premium"]').isDisabled(),true,'An existing contract cannot buy a second contract');
   await page.locator('#requestPlanChange').click();
   await page.locator('#pendingPlanText').waitFor({state:'visible'});
   assert.equal(await page.locator('#current').textContent(),'PRO','A request does not change the plan');
   assert.match(await page.locator('#pendingPlanText').textContent(),/PREMIUM/);
   await page.locator('#withdrawPlanChange').click();
   await page.locator('#planRequestArea').waitFor({state:'visible'});
   assert.equal(writes.length,2,'Only request persistence APIs were called');
   state={...state,subscription_status:'past_due',payment_action_required:true,plan_change_request_available:false,next_billing_at:null};
   await page.reload();await page.locator('#billingAction').waitFor({state:'visible'});
   assert.equal(await page.locator('#planRequestArea').isHidden(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   const output=path.join(root,'artifacts/subscription-management');fs.mkdirSync(output,{recursive:true});
   await page.screenshot({path:path.join(output,`renewal-failure-${language}.png`),fullPage:true});
   state={...state,subscription_status:'pending_cancellation',auto_renew:false,payment_action_required:false};
   await page.reload();await page.waitForFunction(()=>document.getElementById('billingState').textContent.includes('2099'));
   assert.match(await page.locator('#billingState').textContent(),language==='he'?/החידוש האוטומטי בוטל/:/Automatic renewal is canceled/);
   assert.deepEqual(errors,[]);
   await context.close();
  }
  console.log('PASS: Hebrew and English plan requests, withdrawal, unchanged access, verified history, failed renewal, cancellation and mobile layout; no checkout or charge API called');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
