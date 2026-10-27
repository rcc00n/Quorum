// Compare UI positions to the supplied source model; never generates live source facts.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
module.exports=async({page,sources,scope='registry'})=>{
 const spectrum=page.locator('.spectrum').first();
 // DECISION(2026-10-27, Anastasia/Claude Code): a story's Map (scope 'story', lib/story-sources.ts) draws the sources used
 // for the story: its title and caption say so, each listed source says how it was used, and no registry cohort table is
 // drawn. Why: the story source map amendment, docs/DECISIONS.md › Stories as articles.
 if(scope==='story'){
  assert.equal((await spectrum.locator('.section-heading :is(h1,h2)').first().textContent()).trim(),'Sources used for this story');
  assert.ok((await spectrum.locator('.sp-caption').textContent()).includes(`${sources.length} used for this story`),'story caption counts the used sources');
  // Page-side: every listed source says how it was used, in the ledger and, for the selected one, in the inspector.
  const {usedLabel}=require('../lib/story-sources.ts');
  const ledger=spectrum.locator('details.sp-ledger');const wasOpen=await ledger.evaluate(d=>d.open);
  if(!wasOpen)await ledger.locator(':scope > summary').click();
  assert.equal(await ledger.locator('.source-row').count(),sources.length,'the ledger lists exactly the used sources');
  for(const s of sources){
   const row=ledger.locator('.source-row').filter({has:page.locator('.sp-source-button',{hasText:s.name})}).first();
   assert.equal((await row.locator('.used-value').textContent()).trim(),usedLabel(s),'ledger says how '+s.id+' was used');
  }
  if(!wasOpen)await ledger.locator(':scope > summary').click();
  const name=(await spectrum.locator('.sp-inspector h3').textContent()).trim();
  const selected=sources.find(s=>s.name===name);
  if(selected)assert.equal((await spectrum.locator('.sp-inspector .sp-source-used').textContent()).trim(),usedLabel(selected),'the inspector says how the selected source was used');
 }
 const rating=(s,m)=>{const v=m==='average'?[s.allsides,s.mbfc,s.adfontes].filter(v=>v!==null):[s[m]].filter(v=>v!==null);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null};
 for(const mode of ['allsides','mbfc','adfontes','average']){
  await spectrum.getByLabel('Rating mode',{exact:true}).selectOption(mode);
  // WEB-SPECTRUM-POLISH-02: the registry cohort table's outlet counts equal the tiered sources rated under the
  // mode at the agreed thresholds; the table is absent when no tiered source is rated.
  const tiered=sources.filter(s=>rating(s,mode)!==null&&(s.tier==='major'||s.tier==='minor'));
  const table=spectrum.locator('.sp-cohorts');assert.equal(await table.count(),scope==='registry'&&tiered.length?1:0,'cohort table presence under '+mode);
  for(const tier of ['major','minor'])for(const side of ['left','right']){
   const n=tiered.filter(s=>s.tier===tier&&(side==='left'?rating(s,mode)<=-0.25:rating(s,mode)>=0.25)).length;
   if(scope==='registry'&&tiered.length)assert.equal(Number(await table.locator(`[data-cohort="${tier}-${side}"] [data-outlets]`).getAttribute('data-outlets')),n,`cohort ${tier}-${side} under ${mode}`);
  }
  const expected=sources.filter(s=>rating(s,mode)!==null&&s.audience>0&&/^https?:/.test(s.audience_source_url||''));
  const points=spectrum.locator('.sp-point');assert.equal(await points.count(),expected.length);
  for(const s of expected){
   const p=spectrum.locator(`.sp-point[data-source-id="${s.id}"]`);
   assert.equal(Number(await p.getAttribute('data-score')),rating(s,mode));
   assert.equal(Number(await p.getAttribute('data-audience')),s.audience);
   assert.equal(Number(await p.getAttribute('data-x')),(rating(s,mode)+1)*50);
  }
  if(expected.length>1){
   await points.first().focus();await page.keyboard.press('ArrowRight');
   await spectrum.locator('.sp-inspector h3').filter({hasText:expected[1].name}).waitFor();
   assert.equal(await points.nth(1).getAttribute('aria-pressed'),'true');
   await page.keyboard.press('Home');assert.equal(await points.first().getAttribute('aria-pressed'),'true');
  }
 }
 await spectrum.getByLabel('Rating mode',{exact:true}).selectOption('average');
 // WEB-SPECTRUM-POLISH-02: every mark's label comes from the registry identity: a major-tier source wears its id
 // as a badge (upper case, hyphens as spaces), every other source its name; badges are the only labels shown at
 // rest from 701 px, a name appears on hover or selection.
 for(const s of sources.filter(s=>rating(s,'average')!==null&&s.audience>0&&/^https?:/.test(s.audience_source_url||''))){
  const point=spectrum.locator(`.sp-point[data-source-id="${s.id}"]`);
  assert.equal((await point.locator('.sp-point-label').innerText()).trim(),s.tier==='major'?s.id.toUpperCase().replace(/-/g,' '):s.name);
  assert.equal(await point.evaluate(e=>e.classList.contains('sp-point-major')),s.tier==='major');
 }
 if(await spectrum.locator('.sp-point').count()){
  await page.setViewportSize({width:1440,height:1000});await page.mouse.move(0,0);
  // a selected mark shows its label by design.
  // DECISION(2026-10-27, Anastasia/Claude Code): hover the first such mark whose centre is its own. On the real
  // 26 October registry the Associated Press mark's centre lies under The Washington Post's 44 px target, so a
  // pointer there names the Post; that overlap is reported for the component, not hidden here. Why: this check is
  // about a name appearing on hover, not about which of two overlapping targets wins.
  const candidates=spectrum.locator('.sp-point:not(.sp-point-major):not([aria-pressed="true"])');
  const ownId=await candidates.evaluateAll(els=>{for(const el of els){el.scrollIntoView({block:'center',behavior:'instant'});const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(hit&&hit.closest('.sp-point')===el)return el.dataset.sourceId;}return null;});
  const minor=ownId?spectrum.locator(`.sp-point[data-source-id="${ownId}"]`):candidates.first();
  // DECISION(2026-10-27, rcc00n/Codex): wait for label opacity to settle after the phone-to-desktop resize.
  // Why: the production browser can observe the existing 120ms CSS transition; keep the exact visibility assertion.
  if(await minor.count()){await page.waitForFunction(e=>getComputedStyle(e.querySelector('.sp-point-label')).opacity==='0',await minor.elementHandle());assert.equal(await minor.locator('.sp-point-label').evaluate(e=>getComputedStyle(e).opacity),'0');await minor.hover();await page.waitForFunction(e=>getComputedStyle(e.querySelector('.sp-point-label')).opacity==='1',await minor.elementHandle());}
  const major=spectrum.locator('.sp-point-major').first();
  if(await major.count()){await page.waitForFunction(e=>getComputedStyle(e.querySelector('.sp-point-label')).opacity==='1',await major.elementHandle());assert.equal(await major.locator('.sp-point-label').evaluate(e=>getComputedStyle(e).opacity),'1');}
  const stage=spectrum.locator('.sp-stage');await stage.scrollIntoViewIfNeeded();
  const box=await stage.boundingBox();await page.mouse.move(box.x+box.width*.7,box.y+box.height*.35);
  await page.waitForFunction(()=>Math.abs(parseFloat(document.querySelector('.sp-stage').style.getPropertyValue('--sp-ry')))>0);
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await stage.evaluate(e=>getComputedStyle(e).transform),'none');
  assert.equal(await spectrum.locator('.sp-point-core').first().evaluate(e=>getComputedStyle(e).animationName),'none');
 }
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});await spectrum.locator('.spectrum-instrument').scrollIntoViewIfNeeded();
  assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false,'Spectrum overflow at '+width);
  if(process.env.QUORUM_SCREENSHOTS){fs.mkdirSync(process.env.QUORUM_SCREENSHOTS,{recursive:true});await spectrum.locator('.spectrum-instrument').screenshot({path:path.join(process.env.QUORUM_SCREENSHOTS,`spectrum-${width}.png`)});}
 }
 await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1440,height:1000});await page.mouse.move(0,0);
 console.log('PASS: source-bound spectrum positions/4 modes; registry-bound mark labels; keyboard selection, depth, reduced motion, 3 widths');
};
