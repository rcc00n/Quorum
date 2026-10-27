// Actual reader navigation; the caller separately verifies all original content in All sections.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
module.exports=async({page})=>{
 const reader=page.locator('.investigation-reader'),tab=name=>reader.getByRole('tab',{name,exact:true});
 const needsReview=await reader.getByText('Requires editorial review',{exact:true}).isVisible();
 assert.equal(await tab('Reading').getAttribute('aria-selected'),'true');
 assert.equal(await reader.locator('[data-reader-panel]:visible').count(),1);
 const search=new URL(page.url()).search;
 let requests=0;const count=r=>{if(/\/api\//.test(r.url()))requests++};page.on('request',count);
 await tab('Source map').click();await reader.locator('[data-reader-panel="map"]').waitFor({state:'visible'});
 await page.waitForFunction(()=>(document.querySelector('[data-reader-panel="map"] .sp-chart')||document.querySelector('[data-reader-panel="map"] .spectrum-instrument'))?.getBoundingClientRect().top<innerHeight);
 // The Map holds the sources used for this story (story source map amendment, 2026-10-27, Anastasia/Claude Code).
 await reader.getByRole('heading',{name:'Sources used for this story',exact:true}).waitFor();
 // A chosen view starts at the bar (2026-10-27, Anastasia/Claude Code; tightened after review): its first visible pane
 // begins right under the bar, which sits under the site header, unless the page cannot scroll that far; checked
 // after the scroll frame, from the top of the page and again with the bar stuck deep in the All view.
 const startsAtBar=async(label)=>{
  // Two frames first, so select()'s scroll frame has run; then the pane must sit right under the bar with no arrival
  // animation running (its 220 ms translate), or the page must be at its end with the pane below the bar.
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  try{await page.waitForFunction(()=>{const bar=document.querySelector('.reader-bar')?.getBoundingClientRect(),el=[...document.querySelectorAll('[data-reader-panel]')].find(e=>!e.hidden),header=document.querySelector('.sidebar')?.getBoundingClientRect().height||0,max=document.documentElement.scrollHeight-innerHeight;if(!bar||!el||el.getAnimations().some(a=>a.playState==='running'))return false;const pane=el.getBoundingClientRect();return Math.abs(bar.top-header)<=1&&Math.abs(pane.top-bar.bottom)<=1||Math.abs(scrollY-max)<=1&&pane.top>=bar.bottom-1;},undefined,{timeout:5000});}
  catch{throw Error('a chosen view starts at the bar ('+label+'): '+JSON.stringify(await page.evaluate(()=>({scrollY,max:document.documentElement.scrollHeight-innerHeight,bar:document.querySelector('.reader-bar')?.getBoundingClientRect().toJSON()??null,pane:[...document.querySelectorAll('[data-reader-panel]')].find(e=>!e.hidden)?.getBoundingClientRect().top??null}))));}
 };
 await startsAtBar('Source map from the top');
 await tab('All sections').click();await startsAtBar('All sections');
 const stickDeep=async(label)=>assert.equal(await page.evaluate(()=>{window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'});const header=document.querySelector('.sidebar')?.getBoundingClientRect().height||0;return Math.abs(document.querySelector('.reader-bar').getBoundingClientRect().top-header)<=1&&scrollY>0;}),true,'the bar is stuck deep in the All view ('+label+')');
 // With the bar stuck, choosing All again keeps the page height, so only a real scroll to the bar passes.
 await stickDeep('before All');await tab('All sections').click();await startsAtBar('All sections with the bar stuck');
 await stickDeep('before Source map');await tab('Source map').click();await startsAtBar('Source map with the bar stuck');
 if(needsReview)await reader.getByText('Requires editorial review',{exact:true}).first().waitFor();
 assert.equal(new URL(page.url()).search,search);assert.equal(new URL(page.url()).hash,'#reader-map');
 assert.equal(await reader.locator('[data-reader-panel="evidence"]').isVisible(),false);
 await tab('Evidence').click();await tab('Source map').click();await page.goBack();
 await page.waitForFunction(()=>document.querySelector('#reader-tab-evidence')?.getAttribute('aria-selected')==='true');
 await tab('Evidence').focus();await page.keyboard.press('ArrowRight');assert.equal(await tab('Perspectives').getAttribute('aria-selected'),'true');
 await page.keyboard.press('End');assert.equal(await tab('All sections').getAttribute('aria-selected'),'true');
 await page.keyboard.press('Home');assert.equal(await tab('Reading').getAttribute('aria-selected'),'true');
 assert.equal(requests,0,'Tab changes must not refetch or trigger processing');page.off('request',count);
 const claim=reader.locator('.r-claim,.claim-detail').first();
 if(await claim.count()){
  const id=await claim.getAttribute('id'),url=new URL(page.url());url.hash=id;
  await page.goto(url.href);
  try { await page.waitForFunction(()=>document.querySelector('#reader-tab-evidence')?.getAttribute('aria-selected')==='true'); }
  catch { throw Error('Deep-link state: '+JSON.stringify(await page.evaluate(id=>({hash:location.hash,target:!!document.getElementById(id),panel:document.getElementById(id)?.closest('[data-reader-panel]')?.getAttribute('data-reader-panel'),view:document.querySelector('.investigation-reader')?.getAttribute('data-reader-view')}),id))); }
  const target=page.locator(`[id="${id}"]`);
  await page.waitForFunction(id=>document.getElementById(id)?.hasAttribute("open")&&document.getElementById(id)?.querySelector(':scope > summary')===document.activeElement,id);
  assert.notEqual(await target.getAttribute("open"),null);
 }
 await page.emulateMedia({reducedMotion:'reduce'});
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});await tab('Source map').click();
  await page.waitForFunction(()=>(document.querySelector('[data-reader-panel="map"] .sp-chart')||document.querySelector('[data-reader-panel="map"] .spectrum-instrument'))?.getBoundingClientRect().top<innerHeight);
  assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);
  assert.equal(await reader.locator('[data-reader-panel="map"]').evaluate(e=>getComputedStyle(e).animationName),'none');
  if(process.env.QUORUM_SCREENSHOTS){fs.mkdirSync(process.env.QUORUM_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.QUORUM_SCREENSHOTS,`reader-map-${width}.png`)});}
 }
 await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({reducedMotion:'no-preference'});
 await tab('All sections').click();assert.equal(await reader.locator('[data-reader-panel]:visible').count(),5);
 console.log('PASS: reading-first panes; one-click visible map/zero API requests; keyboard/back/deep-claim focus; 3 widths/reduced motion; complete All sections');
};
