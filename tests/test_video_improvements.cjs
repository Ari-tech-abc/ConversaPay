/* Exercise delivered auth and demo interactions, including failed server responses. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..');
const rendered=spawnSync(process.env.TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(rendered.status!==0)throw Error(rendered.stderr);
const pages=JSON.parse(rendered.stdout),policy=JSON.parse(fs.readFileSync(path.join(root,'frontend/data/password-policy.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
 const shots=path.join(root,'artifacts/video-review/final');fs.mkdirSync(shots,{recursive:true});
 try{
  for(const language of ['he','en']){
   const context=await browser.newContext({reducedMotion:'reduce',viewport:{width:375,height:900}});
   await context.addInitScript(language=>localStorage.setItem('conversapay-language',language),language);
   const errors=[],requests=[];let signupFails=true;
   await context.route('**/*',route=>{
    const url=new URL(route.request().url());if(url.host!=='review.test')return route.abort();
    const name=url.pathname==='/'?'home':url.pathname.slice(1);
    if(pages[name])return route.fulfill({contentType:'text/html',body:pages[name]});
    if(url.pathname==='/api/v1/auth/signup-code'){
     requests.push(route.request().postDataJSON());
     return route.fulfill({status:signupFails?503:201,json:signupFails?{detail:'server_error'}:{message:'verification_sent'}});
    }
    if(url.pathname.startsWith('/api/v1/'))return route.fulfill({status:401,json:{detail:'not_authenticated'}});
    const file=path.join(root,url.pathname.slice(1));
    if(file.startsWith(root+path.sep)&&fs.existsSync(file))return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.json')?'application/json':'text/css'});
    return route.fulfill({status:404,body:''});
   });
   const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
   await page.goto('http://review.test/register');
   await page.waitForFunction(()=>window.Talk2PayPasswords?.inspect('Password123!').common);
   assert.equal(await page.locator('#confirm').count(),0);
   await page.locator('#name').fill('Test Owner');await page.locator('#business').fill('Test Business');await page.locator('#email').fill('new@example.com');await page.locator('#terms').check();
   await page.locator('#password').fill('Password123!');await page.locator('#submit').click();
   assert.equal(requests.length,0,'Common password is rejected locally');
   await page.locator('.t2p-password-generate').click();
   const generated=await page.locator('#password').inputValue();assert.match(generated,/^[A-Z2-9]{5}(?:-[A-Z2-9]{5}){3}$/);
   assert.equal(await page.locator('#password').getAttribute('type'),'password');
   assert.equal(await page.locator('#password').evaluate(el=>el.validity.valid),true);
   await page.evaluate(()=>{window.originalPasswordField=document.getElementById('password');});
   await page.locator('.t2p-password-toggle').click();assert.equal(await page.locator('#password').getAttribute('type'),'text');
   assert.equal(await page.locator('.t2p-password-toggle').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('.t2p-password-toggle').getAttribute('aria-label'),language==='en'?'Hide password':'הסתרת הסיסמה');
   assert.equal(await page.locator('#password').inputValue(),generated);
   assert.equal(await page.evaluate(()=>originalPasswordField===document.getElementById('password')),true,'Visibility preserves the input element');
   await page.screenshot({path:path.join(shots,`password-${language}-375.png`),fullPage:true});
   await page.locator('.t2p-password-toggle').click();
   await page.locator('#submit').click();await page.waitForFunction(()=>!document.querySelector('#submit').disabled);
   assert.equal(requests.length,1);assert.equal(await page.locator('#verifyLayer').evaluate(el=>el.classList.contains('show')),false,'Failure never displays success');
   assert.equal(requests[0].password,generated);assert.equal('confirm' in requests[0],false);
   signupFails=false;await page.locator('#submit').click();await page.locator('#verifyLayer.show').waitFor();
   assert.equal(requests.length,2);await page.locator('#verifyClose').click();await page.locator('#submit').click();await page.locator('#verifyLayer.show').waitFor();assert.equal(requests.length,2,'Continue reopens verification without a duplicate signup');
   const parity=await page.evaluate(common=>common.every(password=>!Talk2PayPasswords.inspect(password).valid),policy.common_passwords);assert.equal(parity,true);
   await page.goto('http://review.test/');
   for(const scenario of ['catalog','payment','knowledge']){
    await page.locator(`[data-demo-scenario=${scenario}]`).click();
    assert.equal(await page.locator(`[data-demo-scenario=${scenario}]`).getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('.t2p-demo-msg').nth(1).isVisible(),true);
    assert.equal(await page.locator('.t2p-demo-product').isVisible(),scenario!=='knowledge');
    assert.equal(await page.locator('.t2p-demo-pay').isVisible(),scenario==='payment');
   }
   await page.locator('#demo-replay').click();assert.equal(await page.locator('.t2p-demo-msg').nth(2).isVisible(),true);
   assert.equal(await page.locator('.plan-comparison table').count(),1);
   for(const plan of ['free','pro','premium']){
    await page.locator(`[data-plan-preview=${plan}]`).click();
    assert.equal(await page.locator(`[data-plan-preview=${plan}]`).getAttribute('aria-pressed'),'true');
    for(const other of ['free','pro','premium'])assert.equal(await page.locator(`.plan-comparison a[href="/register?plan=${other}"]`).isVisible(),other===plan);
   }

   for(const width of [320,375,768,1440]){
    await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${language} fits ${width}`);
    const hero=await page.evaluate(()=>{const copy=document.querySelector('.hero-copy').getBoundingClientRect(),demo=document.querySelector('.commerce-thread').getBoundingClientRect();return {copy:{top:copy.top,bottom:copy.bottom,left:copy.left,right:copy.right},demo:{top:demo.top,bottom:demo.bottom,left:demo.left,right:demo.right}};});
    if(width===1440)assert.equal(hero.copy.top<hero.demo.bottom&&hero.demo.top<hero.copy.bottom,true,'Desktop hero copy and product share a row');
    if(width===375)assert.equal(hero.copy.bottom<=hero.demo.top,true,'Mobile headline precedes product preview');
    if(width===375||width===1440)await page.screenshot({path:path.join(shots,`home-${language}-${width}.png`),fullPage:true});
   }
   assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0,'Reduced motion has no running animations');
   assert.deepEqual(errors,[]);await context.close();
   console.log(`PASS: ${language} password generation, common-password block, visibility, signup failure/success/retry, three demo scenarios, pricing, 320–1440px and reduced motion`);
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
