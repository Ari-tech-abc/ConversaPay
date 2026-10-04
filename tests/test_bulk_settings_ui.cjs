const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.join(__dirname, '..');
const fixtures = spawnSync(process.env.TEST_PYTHON || path.join(root, '.venv/Scripts/python.exe'), [path.join(__dirname, 'render_frontend_fixtures.py')], { cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
if (fixtures.status) throw Error(fixtures.stderr);
const pages = JSON.parse(fixtures.stdout), bid = '00000000-0000-4000-8000-000000000001';
(async () => {
 const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
 let checks = 0; const check = (a, b) => { assert.deepEqual(a, b); checks++; };
 try {
  for (const lang of ['he', 'en']) for (const width of [1440, 375]) {
   let products = Array.from({ length: 55 }, (_, i) => ({ id: 'product-' + i, name: 'Product ' + i, item_key: 'SKU-' + i, price: 10, is_active: true })), payloads = [];
   const page = await browser.newPage({ viewport: { width, height: 900 } }), errors = [];
   page.on('pageerror', e => errors.push(e.message));
   await page.addInitScript(lang => { localStorage.setItem('access_token', 'offline'); localStorage.setItem('conversapay-language', lang); }, lang);
   let confirmation = true, conflict = false, schemaMissing = false, deletionJob = null;
   page.on('dialog', dialog => confirmation ? dialog.accept() : dialog.dismiss());
   await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.host !== 'bulk.test') return route.abort();
    if (url.pathname === '/dashboard' || url.pathname === '/settings') return route.fulfill({ contentType: 'text/html', body: pages[url.pathname.slice(1)] });
    if (url.pathname.startsWith('/api/v1/')) {
     const endpoint = url.pathname.slice(7); let body = {}, status = 200;
     if (endpoint === '/businesses') body = [{ id: bid, business_name: 'Store' }];
     else if (endpoint === '/auth/me') body = { email: 'owner@example.com', profile: { full_name: 'Owner' } };
     else if (endpoint === '/dashboard/features') body = { plan_type: 'pro' };
     else if (endpoint === '/products/paged') { const n = Number(url.searchParams.get('page') || 1); body = { products: products.slice((n-1)*50, n*50), page: n, total: products.length, total_pages: Math.ceil(products.length/50) }; }
     else if (endpoint === '/products/bulk-delete') {
      const payload = route.request().postDataJSON(); check(route.request().headers().authorization,'Bearer offline'); payloads.push(payload);
      if (schemaMissing) { status = 503; body = { detail: { code: 'product_delete_schema_missing', message: 'Database update required' } }; }
      else if (conflict) { status = 409; body = { detail: { code: 'selection_changed', message: 'Selection changed' } }; }
      else if(payload.expected_count>500){deletionJob={id:'00000000-0000-4000-8000-000000000009',status:'pending',total:payload.expected_count,deleted:0};body={job_id:deletionJob.id,status:'pending'};}
      else { const before = products.length; products = products.filter(p => !payload.all_products && !payload.product_ids.includes(p.id)); body = { deleted: before - products.length }; }
     } else if(endpoint.startsWith('/products/delete-jobs/')) {
      deletionJob.deleted=Math.min(deletionJob.total,deletionJob.deleted+500);deletionJob.status=deletionJob.deleted===deletionJob.total?'completed':'pending';if(deletionJob.status==='completed')products=[];body={...deletionJob};
     } else if (endpoint === '/profile/notifications') body = { preferences: { payment_success: true, weekly_digest: true, security_alerts: true, product_updates: false }, delivery: { enabled: width === 1440 } };
     else if (endpoint === '/profile/billing') body = { plan_type: 'pro', subscription_status: 'active', usage: { used: 37, available: true }, preview: { limit: null, remaining: null } };
     else if (endpoint === '/api-keys') { status = 500; body = { detail: 'An unexpected error occurred' }; }
     else body = { keys: [], orders: [], plan_type: 'pro', limited: false, sessions: [] };
     return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    }
    const file = path.join(root, url.pathname.slice(1));
    if (fs.existsSync(file) && fs.statSync(file).isFile()) return route.fulfill({ body: fs.readFileSync(file), contentType: file.endsWith('.js') ? 'application/javascript' : 'text/css' });
    return route.abort();
   });
   await page.goto('http://bulk.test/dashboard');
   await page.waitForFunction(() => document.querySelectorAll('[data-select-product]').length === 50);
   for (const height of [900,480,375]) {
    await page.setViewportSize({width,height});
    await page.locator('#widgetFab').click();
    const closeIsClickable = await page.locator('#widgetClose').evaluate(button => {
     const rect=button.getBoundingClientRect();
     return rect.top>=0 && rect.bottom<=innerHeight && button.contains(document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2));
    });
    check(closeIsClickable,true);
    await page.locator('#widgetClose').click();
    await page.waitForFunction(()=>document.querySelector('#widgetPanel').hidden);
    check(await page.locator('#widgetPanel').isVisible(),false);
   }
   await page.setViewportSize({width,height:900});
   await page.locator('[data-select-product="product-0"]').check();
   await page.locator('#productPagination [data-page="2"]').first().click();
   await page.waitForFunction(() => document.querySelectorAll('[data-select-product]').length === 5);
   await page.locator('[data-select-product="product-50"]').check();
   confirmation = false; await page.locator('.product-delete-selected').click(); check(payloads.length, 0);
   confirmation = true; await page.locator('.product-delete-selected').click();
   await page.waitForFunction(() => document.querySelector('#productSummary').textContent.includes('53'));
   check(payloads[0].product_ids, ['product-0', 'product-50']); check(payloads[0].expected_count, 2);
   await page.locator('.product-selection-bar input').check();
   check(await page.locator('[data-select-product]:checked').count(), 50);
   const screenshotDir = path.join(root, 'docs/design-preview/live-review'); fs.mkdirSync(screenshotDir, { recursive: true });
   await page.locator('.product-selection-bar').scrollIntoViewIfNeeded();
   await page.screenshot({ path: path.join(screenshotDir, `product-selection-${lang}-${width}.png`) });
   await page.locator('.product-selection-bar button').nth(1).click();
   check(await page.locator('[data-select-product]:checked').count(), 0);
   await page.locator('.product-selection-bar button').first().click();
   conflict = true; await page.locator('.product-delete-selected').click();
   await page.waitForFunction(() => !document.querySelector('.product-delete-selected').disabled);
   check(products.length, 53); check(payloads.at(-1).all_products, true); check(payloads.at(-1).expected_count, 53);
   conflict = false; schemaMissing = true; await page.locator('.product-delete-selected').click();
   await page.waitForFunction(()=>!document.querySelector('.product-delete-selected').disabled);
   check(products.length,53);
   check((await page.locator('#notice').textContent()).includes(lang==='he'?'עדכון במסד הנתונים':'database update'),true);
   check(payloads.at(-1).all_products,true);
   schemaMissing = false; await page.locator('.product-delete-selected').click();
   await page.waitForFunction(() => document.querySelector('.product-selection-bar').hidden);
   check(products.length, 0);
   products=Array.from({length:1500},(_,i)=>({id:'large-'+i,name:'Large '+i,item_key:'large-'+i,price:10,is_active:true}));
   await page.reload();await page.waitForFunction(()=>document.querySelector('#productSummary').textContent.includes('1500'));
   const callsBefore=payloads.length;
   await page.locator('.product-selection-bar button').first().click();await page.locator('.product-delete-selected').click();
   await page.waitForFunction(()=>Object.keys(localStorage).some(key=>key.startsWith('talk2pay-product-delete-')));
   await page.reload();
   await page.waitForFunction(()=>document.querySelector('.product-selection-bar')?.hidden);
   check(products.length,0);check(payloads.length,callsBefore+1);check(payloads.at(-1).expected_count,1500);
   await page.goto('http://bulk.test/settings');
   await page.waitForSelector('#keyList + .settings-load-error, #keyList ~ .settings-load-error');
   check(await page.locator('#usageText').textContent(), '37');
   check(await page.locator('#toastWrap .cp-toast').count(), 0);
   check((await page.locator('body').textContent()).includes('An unexpected error occurred'), false);
   check(await page.locator('#product_updates').isChecked(), false);
   check((await page.locator('#notificationDelivery').textContent()).includes(width === 1440 ? (lang === 'he' ? 'המאומתת' : 'verified') : (lang === 'he' ? 'אינה פעילה' : 'not active')), true);
   await page.evaluate(() => window.showSystemModal('Example error'));
   check(await page.locator('.cp-toast-close').count(), 1); check(await page.locator('.cp-toast-icon').count(), 0);
   check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
   await page.screenshot({ path: path.join(screenshotDir, `bulk-settings-${lang}-${width}.png`), fullPage: true });
   check(errors, []); await page.close();
  }
  console.log(`PASS: ${checks} bulk-selection/settings browser checks in Hebrew and English at 1440px and 375px`);
 } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
