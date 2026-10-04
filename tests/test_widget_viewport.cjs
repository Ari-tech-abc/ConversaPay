const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});let checks=0;
 try{
  for(const [width,height] of [[1440,900],[1024,480],[375,812],[812,375]]){
   const page=await browser.newPage({viewport:{width,height}});
   await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.host!=='widget.test')return route.abort();
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width,initial-scale=1"><script>window.ConversaPayWidgetConfig={business_id:"00000000-0000-4000-8000-000000000001",api_key:"offline-widget-key"}</script><script src="/frontend/js/widget.js"></script>'});
    if(url.pathname==='/frontend/js/widget.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(__dirname,'../frontend/js/widget.js'))});
    return route.fulfill({json:{bot_name:'Sample store',greeting_message:'Hello',features:{plan_type:'pro'}}});
   });
   await page.goto('http://widget.test/');await page.locator('.cp-toggle').click();
   assert.equal(await page.locator('.cp-head button').evaluate(button=>{const r=button.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&button.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2))}),true);checks++;
   assert.ok(await page.locator('.cp-window').evaluate(el=>el.getBoundingClientRect().height<=430));checks++;
   await page.locator('.cp-head button').click();assert.equal(await page.locator('.cp-window').isVisible(),false);checks++;
   await page.close();
  }
  console.log(`PASS: ${checks} embedded widget viewport/close checks`);
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
