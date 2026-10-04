const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..');
const rendered=spawnSync(process.env.TEST_PYTHON||'python',[path.join(__dirname,'render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(rendered.status!==0)throw Error(rendered.stderr);const pages=JSON.parse(rendered.stdout);
(async()=>{const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});try{
 for(const name of ['home','login','register']){
  const context=await browser.newContext({reducedMotion:'reduce'});await context.addInitScript(()=>{localStorage.setItem('conversapay-language','en');});
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.host!=='copy.test')return route.abort();if(url.pathname==='/'+name)return route.fulfill({contentType:'text/html',body:pages[name]});const file=path.join(root,url.pathname.slice(1));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.js')?'application/javascript':'text/css'});return route.fulfill({status:503,contentType:'application/json',body:'{}'});});
  const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('http://copy.test/'+name);await page.waitForFunction(()=>document.documentElement.lang==='en');
  const missing=await page.evaluate(()=>{const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),items=[];let node;while(node=walker.nextNode()){const element=node.parentElement;if(element&&!element.closest('script,style')&&element.getClientRects().length&&/[\u0590-\u05ff]/.test(node.nodeValue)&&node.nodeValue.trim()!=='עברית')items.push(node.nodeValue.trim());}return [...new Set(items)];});assert.deepEqual(missing,[],name+' English copy');
  await page.locator('[data-cp-language-toggle]').click();await page.waitForFunction(()=>document.documentElement.lang==='he');
  for(const width of [1440,375]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,name+' fits '+width);await page.screenshot({path:path.join(root,'docs/design-preview/live-review',name+'-copy-'+width+'.png'),fullPage:true});}
  if(name==='login'){await page.locator('#email').fill('demo@example.com');await page.locator('#password').fill('demo-password');await page.locator('#submit').click();await page.waitForFunction(()=>document.querySelector('#toastWrap').textContent.includes('השירות אינו זמין'));assert.equal(await page.locator('#submit').textContent(),'כניסה לחשבון');}
  assert.deepEqual(errors,[],name+' script errors');await context.close();console.log('PASS: '+name+' bilingual copy, language switching and desktop/mobile layout');
 }
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
