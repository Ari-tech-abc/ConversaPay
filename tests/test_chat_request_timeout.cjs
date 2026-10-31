const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.fulfill({ contentType: 'text/html', body: '<body></body>' }));
    await page.goto('http://timeout.test/');
    await page.clock.install();
    // Simulate a slow model without wall-clock sleeps or external services.
    await page.evaluate(() => {
      window.fetch = (input, options = {}) => new Promise((resolve, reject) => {
        const timer = setTimeout(() => resolve(new Response('{}')), 20000);
        const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
        if (options.signal?.aborted) abort();
        else options.signal?.addEventListener('abort', abort, { once: true });
      });
    });
    await page.addScriptTag({ content: fs.readFileSync(path.join(__dirname, '../frontend/js/ux.js'), 'utf8') });
    await page.evaluate(() => {
      window.results = {};
      const watch = (key, promise) => promise.then(() => { results[key] = 'ok'; }, e => { results[key] = e.name; });
      watch('chat', fetch('/api/v1/chat', { method: 'POST' }));
      watch('ordinary', fetch('/api/v1/profile'));
      const controller = new AbortController();
      watch('cancelled', fetch('/api/v1/chat', { signal: controller.signal }));
      setTimeout(() => controller.abort(), 1000);
    });
    await page.clock.runFor(16000);
    assert.deepEqual(await page.evaluate(() => results), { ordinary: 'AbortError', cancelled: 'AbortError' });
    await page.clock.runFor(5000);
    assert.equal(await page.evaluate(() => results.chat), 'ok');
    // A permanently stalled chat still has a bounded deadline.
    await page.evaluate(() => {
      // The wrapper captured this fake response delay through global setTimeout.
      const originalTimer = window.setTimeout.bind(window);
      window.setTimeout = (fn, ms, ...args) => originalTimer(fn, ms === 20000 ? 200000 : ms, ...args);
      fetch('/api/v1/chat').then(() => { results.stalled = 'ok'; }, e => { results.stalled = e.name; });
    });
    await page.clock.runFor(111000);
    assert.equal(await page.evaluate(() => results.stalled), 'AbortError');
    console.log('PASS: chat survives 15s, ordinary API remains bounded, explicit cancellation works, stalled chat times out.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
