const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.setContent('<div id="preview"></div><div id="mapping"></div><button id="import"></button><section><form id="keyForm"><button></button></form><input id="keyName"><div id="keyList"></div><span id="keyCount"></span></section>');
    const importHtml = fs.readFileSync(path.join(__dirname, '../frontend/html/product-import.html'), 'utf8');
    const renderFunctions = importHtml.slice(importHtml.indexOf('function makeMapping()'), importHtml.indexOf("$('drop').onclick"));
    await page.addScriptTag({ content: "const $=id=>document.getElementById(id);let headers=[],rows=[],business={id:'offline'};const normalize=v=>String(v??'').trim();" + renderFunctions });
    const payload = '<img src=x onerror="window.__xss=true">';
    await page.evaluate(value => { headers=[value,'name'];rows=[{[value]:value,name:value}];render(); }, payload);
    assert.equal(await page.locator('#preview img, #mapping img').count(), 0);
    assert.equal(await page.locator('#preview tbody td').first().textContent(), payload);
    assert.equal(await page.locator('#mapping select').first().locator('option').nth(1).getAttribute('value'), payload);
    assert.equal(await page.evaluate(() => window.__xss === true), false);
    const settings = fs.readFileSync(path.join(__dirname, '../frontend/html/settings.html'), 'utf8');
    const loadKeys = settings.slice(settings.indexOf('async function loadKeys()'), settings.indexOf('async function load()'));
    await page.addScriptTag({ content: "business={id:'test'};const toast=()=>{};const api=async()=>({keys:[{id:'key',name:" + JSON.stringify(payload) + ",key_prefix:" + JSON.stringify(payload) + "}]});" + loadKeys });
    await page.evaluate(() => loadKeys());
    assert.equal(await page.locator('#keyList img').count(), 0);
    assert.equal(await page.locator('#keyList strong').textContent(), payload);
    assert.equal(await page.evaluate(() => window.__xss === true), false);
    console.log('PASS: import cells, column headers/options, and API key names remain plain text in Chromium.');
    const recovery = await browser.newPage();
    await recovery.addInitScript(() => {
      localStorage.setItem('access_token', 'other-user-session');
      window.supabase = { createClient: () => ({ auth: {
        setSession: async tokens => {
          window.boundRecoveryTokens=tokens;
          return { data:{session:{access_token:'validated-recovery-token'}}, error:null };
        },
      } }) };
    });
    let submitted;
    const recoveryHtml=fs.readFileSync(path.join(__dirname,'../frontend/html/forgot-password.html'),'utf8');
    const recoveryScript=fs.readFileSync(path.join(__dirname,'../frontend/js/password-reset.js'),'utf8');
    await recovery.route('**/*',async route => {
      const url=new URL(route.request().url());
      if(url.hostname!=='security.test') return route.abort();
      if(url.pathname==='/api/v1/config/public') return route.fulfill({json:{supabase_url:'https://offline.invalid',supabase_anon_key:'test'}});
      if(url.pathname==='/api/v1/auth/password-reset/confirm') {
        submitted=route.request().postDataJSON();
        return route.fulfill({json:{message:'Password reset successfully'}});
      }
      if(url.pathname==='/frontend/js/password-reset.js') return route.fulfill({contentType:'application/javascript',body:recoveryScript});
      if(url.pathname.endsWith('.js')||url.pathname.endsWith('.css')) return route.fulfill({body:''});
      return route.fulfill({contentType:'text/html',body:recoveryHtml});
    });
    await recovery.goto('http://security.test/forgot-password#type=recovery&access_token=recovery-access&refresh_token=recovery-refresh');
    await recovery.waitForFunction(()=>!document.querySelector('#resetForm button').disabled);
    assert.equal(new URL(recovery.url()).hash,'');
    await recovery.locator('#password').fill('test-password-123');
    await recovery.locator('#confirm').fill('test-password-123');
    await recovery.locator('#resetForm button').click();
    await recovery.waitForFunction(()=>document.getElementById('notice').textContent.includes('הסיסמה עודכנה'));
    assert.equal(submitted.token,'validated-recovery-token');
    assert.equal(await recovery.evaluate(()=>localStorage.getItem('access_token')),'other-user-session');
    assert.deepEqual(await recovery.evaluate(()=>window.boundRecoveryTokens),{access_token:'recovery-access',refresh_token:'recovery-refresh'});
    console.log('PASS: recovery binds the link session, clears URL secrets, and never uses another stored login.');
    const cachePage=await browser.newPage();
    const cacheScript=fs.readFileSync(path.join(__dirname,'../frontend/js/dashboard-instant-cache.js'),'utf8');
    await cachePage.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<span id="revenue">0</span><div id="products"></div><div id="orders"></div><div id="productPagination"></div>'}));
    await cachePage.goto('http://cache.security.test');
    await cachePage.evaluate(value=>{
      localStorage.setItem('user_id','cache-user');
      localStorage.setItem('talk2pay_dashboard_snapshot_v2:cache-user',JSON.stringify({sections:{orders:'private customer data'}}));
      localStorage.setItem('talk2pay_dashboard_snapshot_v3:cache-user',JSON.stringify({version:3,savedAt:Date.now(),metrics:{revenue:123},sections:{products:value,orders:value},productPagination:{html:value}}));
    },payload);
    await cachePage.addScriptTag({content:cacheScript});
    assert.equal(await cachePage.locator('#revenue').textContent(),'₪123');
    assert.equal(await cachePage.locator('img').count(),0);
    assert.equal(await cachePage.evaluate(()=>localStorage.getItem('talk2pay_dashboard_snapshot_v2:cache-user')),null);
    await cachePage.evaluate(()=>{document.getElementById('orders').textContent='private customer data';window.dispatchEvent(new Event('pagehide'));});
    const snapshot=await cachePage.evaluate(()=>JSON.parse(localStorage.getItem('talk2pay_dashboard_snapshot_v3:cache-user')));
    assert.equal(snapshot.sections,undefined);
    assert.equal(snapshot.productPagination,undefined);
    assert.equal(JSON.stringify(snapshot).includes('private customer data'),false);
    assert.equal(await cachePage.evaluate(()=>window.__xss===true),false);
    console.log('PASS: dashboard cache ignores injected HTML and does not persist customer order markup.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
