const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'),root=path.join(__dirname,'..');
const fixture=spawnSync(process.env.TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'render_frontend_fixtures.py')],{encoding:'utf8',maxBuffer:8*1024*1024});
if(fixture.status)throw Error(fixture.stderr);const pages=JSON.parse(fixture.stdout),bid='00000000-0000-4000-8000-000000000002';
(async()=>{const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});try{
 for(const lang of ['he','en']){
  let saved,confirmation;const context=await browser.newContext({viewport:{width:375,height:900},reducedMotion:'reduce'});
  const shots=path.join(root,'artifacts/production-repairs');fs.mkdirSync(shots,{recursive:true});
  await context.addInitScript(lang=>{localStorage.setItem('access_token','offline');localStorage.setItem('conversapay-language',lang);},lang);
  await context.route('**/*',async route=>{const url=new URL(route.request().url());if(url.host!=='commerce.test')return route.abort();
   if(['/settings','/dashboard','/setup-guide'].includes(url.pathname))return route.fulfill({contentType:'text/html',body:pages[url.pathname.slice(1)]});
   if(url.pathname.startsWith('/api/v1/')){
    const endpoint=url.pathname.slice(7);let body={};
    if(endpoint==='/payments/wordpress-plugin/'+bid){assert.equal(route.request().headers().authorization,'Bearer offline');return route.fulfill({contentType:'application/zip',body:'offline-plugin-zip'});}
    if(endpoint==='/businesses')body=[{id:bid,business_name:'Store'}];
    else if(endpoint==='/auth/me')body={email:'owner@example.com',profile:{full_name:'Owner',email_verified:true}};
    else if(endpoint==='/dashboard/features')body={plan_type:'pro'};
    else if(endpoint==='/dashboard/orders')body={orders:[{id:'order',order_number:'ORD-1',status:'paid',total:'37.00',fulfillment:'delivery',customer_info:{name:'Buyer',phone:'0501234567',address:'<img src=x onerror=alert(1)>'},items:[{name:'Product',quantity:1}]}]};
    else if(endpoint==='/products/paged')body={products:[],total:0,total_pages:0};
    else if(endpoint==='/profile/notifications')body={preferences:{payment_success:true}};
    else if(endpoint==='/api-keys')body={keys:[]};
    else if(endpoint.endsWith('/commerce')){if(route.request().method()==='PUT'){saved=route.request().postDataJSON();body=saved;}else body={pickup_ils:'0.00',shipping_ils:'17.00',shipping_business_days:[2,5]};}
    else if(endpoint==='/merchant-payments/status')body={connected:true,ready:true,connection_available:true};
    else if(endpoint==='/chat'){const request=route.request().postDataJSON();if(request.confirmation_token){confirmation=request;body={intent:'checkout',response:'Payment pending',payment_url:'https://checkout.stripe.com/test',action_data:{order_number:'ORD-1'}};}else body={intent:'quote',response:'20 + 17 = 37',action_data:{item_key:'P',product_name:'Product',quantity:1,total:'37.00',currency:'ILS',fulfillment:'delivery',locale:lang,confirmation_token:'signed-quote'}};}
    return route.fulfill({json:body});
   }
   const file=path.join(root,url.pathname.slice(1));if(file.startsWith(root+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});
   return route.abort();
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://commerce.test/settings');await page.waitForFunction(()=>!document.querySelector('#commerce-pickup_ils').disabled);
  assert.equal(await page.locator('#commerce-pickup_ils').inputValue(),'0.00');await page.locator('#commerce-shipping_ils').fill('25.50');
  await page.locator('#commerceSettings button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#commerceSettings [role=status]:last-child').textContent.length>0);
  assert.deepEqual(saved,{pickup_ils:'0.00',shipping_ils:'25.50',shipping_business_days:[2,5]});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('#commerceSettings').screenshot({path:path.join(shots,'settings-'+lang+'-375.png')});
  await page.goto('http://commerce.test/setup-guide?tab=wordpress');
  const downloadPromise=page.waitForEvent('download');await page.locator('#panel-wordpress button').first().click();
  const download=await downloadPromise;assert.equal(download.suggestedFilename(),'conversapay-chat.zip');
  await page.goto('http://commerce.test/dashboard');await page.waitForFunction(()=>document.querySelector('#businessName').textContent==='Store');
  await page.locator('#orders details summary').click();assert.equal(await page.locator('#orders details img').count(),0);assert.match(await page.locator('#orders details').textContent(),/0501234567/);
  await page.locator('#widgetFab').click();await page.locator('#widgetInput').fill('Buy product with delivery');await page.locator('#widgetSend').click();
  const form=page.locator('#messages form');await form.waitFor();await form.locator('button').click();assert.equal(confirmation,undefined,'Empty contact cannot confirm checkout');
  await form.screenshot({path:path.join(shots,'quote-'+lang+'-375.png')});
  for(const [key,value]of Object.entries({name:'Buyer',email:'buyer@example.com',phone:'0501234567',address:'Main street 12'}))await form.locator('[name='+key+']').fill(value);
  await form.locator('button').click();await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Payment pending'));
  assert.equal(confirmation.confirmation_token,'signed-quote');assert.equal(confirmation.customer_info.address,'Main street 12');assert.deepEqual(errors,[]);
  await context.close();console.log('PASS: '+lang+' commerce settings save, mobile width, required fulfillment details and dashboard quote confirmation');
 }
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
