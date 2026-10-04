const { chromium } = require('C:/Users/amran/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  const page = await browser.newPage();
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  for (const width of [375,768,1024,1440]) {
    await page.setViewportSize({width,height:1000});
    await page.goto('http://127.0.0.1:4318');
    await page.evaluate(()=>document.fonts.ready);
    for(const view of ['landing','dashboard','login']) {
      await page.locator(`[data-view="${view}"]`).click();
      await page.evaluate(async()=>{await Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})));});
      const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
      if(dimensions.scroll>dimensions.viewport) throw new Error(`Overflow at ${width} ${view}: ${JSON.stringify(dimensions)}`);
      if(width===1440 || width===375) await page.screenshot({path:path.join(__dirname,`${view}-${width}.png`),fullPage:true});
    }
    console.log(`PASS: ${width}px, three views, no page overflow`);
  }
  await page.locator('[data-view="landing"]').click();
  await page.locator('#demo-pay').click();
  if(!await page.locator('#sale-toast').innerText().then(t=>t.includes('לא בוצע חיוב'))) throw new Error('Payment demo failed');
  await page.locator('[data-view="login"]').click();
  await page.locator('#email').fill('demo@example.com');
  await page.locator('#password').fill('sample-password');
  await page.locator('#password-toggle').click();
  if(await page.locator('#password').getAttribute('type')!=='text') throw new Error('Password toggle failed');
  await page.locator('#login-form button[type="submit"]').click();
  if(!await page.locator('#dashboard').isVisible()) throw new Error('Demo navigation failed');
  if(await page.locator('#password').inputValue()) throw new Error('Demo password retained');
  await page.locator('[data-demo="הוספת מוצר"]').click();
  if(!await page.locator('#dash-message').isVisible()) throw new Error('Demo feedback failed');
  await page.locator('[data-view="landing"]').click();
  await page.locator('#motion-toggle').click();
  if(await page.locator('#motion-toggle').getAttribute('aria-pressed')!=='true') throw new Error('Motion stop failed');
  if(await page.evaluate(()=>document.getAnimations().length)) throw new Error('Animations persisted while stopped');
  await page.locator('#motion-toggle').click();
  await page.locator('[data-view="landing"]').click();
  if(!await page.evaluate(()=>document.getAnimations().length>0)) throw new Error('Replay failed');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.reload();
  if(await page.locator('#motion-toggle').getAttribute('aria-pressed')!=='true') throw new Error('Reduced motion preference ignored');
  if(await page.evaluate(()=>document.getAnimations().length)) throw new Error('Reduced motion still animates');
  console.log('PASS: stop/resume, conversation replay, OS reduced-motion preference');
  if(errors.length) throw new Error(errors.join('\n'));
  console.log('PASS: navigation, payment demo, password toggle, demo login, dashboard feedback; no JavaScript errors');
  await browser.close();
})().catch(error=>{console.error(error);process.exitCode=1;});
