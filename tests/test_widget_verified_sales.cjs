const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
    const requests = [];
    const bid = '11111111-1111-1111-1111-111111111111';
    const widget = fs.readFileSync(path.join(__dirname, '../frontend/js/widget.js'), 'utf8');
    let release;
    let confirmationStarted;
    const pendingConfirmation = new Promise(resolve => { confirmationStarted = resolve; });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'sales.test') return route.abort();
      if (url.pathname === '/widget.js') return route.fulfill({ contentType: 'application/javascript', body: widget });
      if (url.pathname.startsWith('/api/v1/widget/config/')) return route.fulfill({ json: { bot_name: 'TALK2PAY', features: { plan_type: 'pro' } } });
      if (url.pathname === '/api/v1/chat') {
        const request = route.request().postDataJSON();
        requests.push(request);
        if (request.confirmation_token) {
          confirmationStarted();
          await new Promise(resolve => { release = resolve; });
          return route.fulfill({ json: { intent: 'checkout', response: 'Payment pending; no verified expiry supplied.', payment_url: 'https://checkout.example/s1', action_data: { quantity: 1, order_number: 'ORD-demo' } } });
        }
        return route.fulfill({ json: { intent: 'quote', response: 'Plant pot 223.10 + delivery 17.00 = 240.10 ILS. Confirm?', action_data: { product_name: '<img src=x onerror=alert(1)>', quantity: 1, total: '240.10', currency: 'ILS', confirmation_token: 'server-signed-quote', locale: 'en' } } });
      }
      return route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<meta charset='utf-8'><script>window.ConversaPayWidgetConfig={business_id:'${bid}'}</script><script src='/widget.js'></script>` });
    });
    await page.goto('http://sales.test/');
    await page.locator('.cp-toggle').click();
    await page.locator('#cpInput').fill('Buy plant pot with delivery');
    await page.locator('#cpSend').click();
    const confirm = page.getByRole('button', { name: 'Confirm quote and create payment link' });
    await confirm.waitFor();
    assert.equal(requests.length, 1);
    assert.equal(requests[0].confirmation_token, null);
    assert.equal(await page.locator('.cp-checkout-card img').count(), 0);
    assert.match(await page.locator('.cp-checkout-title').textContent(), /240\.10/);
    assert.ok((await confirm.boundingBox()).height >= 44);
    await page.locator('.cp-checkout-title').evaluate(el => { el.textContent = 'Plant pot · 1 · 240.10 ILS'; });
    await confirm.focus();
    await page.keyboard.press('Enter');
    await pendingConfirmation;
    await page.waitForFunction(() => document.querySelector('.cp-quote-confirm').getAttribute('aria-busy') === 'true');
    assert.equal(await page.locator('.cp-quote-confirm').isDisabled(), true);
    await page.locator('.cp-quote-confirm').evaluate(el => el.click());
    assert.equal(requests.length, 2);
    assert.equal(requests[1].confirmation_token, 'server-signed-quote');
    const out = path.join(__dirname, '../artifacts/verified-sales');
    fs.mkdirSync(out, { recursive: true });
    release();
    await page.getByRole('link', { name: /תשלום/ }).waitFor();
    await page.getByRole('link', { name: /תשלום/ }).scrollIntoViewIfNeeded();
    await page.locator('#cpMessages').evaluate(el => el.scrollTo({ top: el.scrollHeight, behavior: 'instant' }));
    assert.equal(await page.getByRole('link', { name: /תשלום/ }).getAttribute('href'), 'https://checkout.example/s1');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(out, 'widget-confirmation.png'), fullPage: true });
    console.log('PASS: verified quote, explicit keyboard confirmation, duplicate prevention, XSS-safe text, mobile width and provider link.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
