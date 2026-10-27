// Public DOM/motion only; no credentials, source fetch, model call or generated metric.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
 const root=process.env.QUORUM_TEST_URL||'http://127.0.0.1:3017';
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'no-preference'}),errors=[];
  page.on('pageerror',e=>errors.push(e.name));await page.goto(root);
  const sheet=page.locator('.lp-sheet.q-depth');await sheet.waitFor();
  const heading=await page.locator('#hero-title').textContent();assert.ok(heading);
  await sheet.scrollIntoViewIfNeeded();const b=await sheet.boundingBox();
  await page.mouse.move(b.x+b.width*.75,b.y+b.height*.3);
  await page.waitForFunction(()=>Math.abs(parseFloat(document.querySelector('.lp-sheet').style.getPropertyValue('--q-ry')))>0);
  await page.locator('#sources').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#sources').dataset.revealed==='true');
  assert.equal(await page.locator('#sources').evaluate(e=>getComputedStyle(e).animationName),'q-section-arrive');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await sheet.evaluate(e=>getComputedStyle(e).transform),'none');
  assert.equal(await page.locator('#sources').evaluate(e=>getComputedStyle(e).animationName),'none');
  for(const width of [1440,768,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);}
  assert.deepEqual(errors,[]);await page.close();
  const nojs=await browser.newPage();await nojs.addInitScript(() => { window.IntersectionObserver = undefined; });await nojs.goto(root);await nojs.locator('.lp-sheet').waitFor({state:'visible'});
  assert.equal(await nojs.locator('#hero-title').textContent(),heading);
  assert.equal(await nojs.locator('#sources').evaluate(e=>getComputedStyle(e).opacity),'1');
  assert.ok(await nojs.locator('.lp-sheet').isVisible());await nojs.close();
  console.log('PASS: public section reveal/depth, reduced motion, 3 widths and readable IntersectionObserver fallback');
 }finally{await browser.close()}
})().catch(e=>{console.error('FAIL: motion browser regression '+e.name);process.exit(1)});
