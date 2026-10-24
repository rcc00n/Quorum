// Genuine registry over actual authenticated Django/Next. Existing story fixture remains explicitly FICTIONAL.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=async ({browser,root,env,password})=>{
 const expected=JSON.parse(fs.readFileSync(env.QUORUM_CATALOG_PATH));
 const output=process.env.QUORUM_SCREENSHOTS;fs.mkdirSync(output,{recursive:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:path.join(output,'video'),size:{width:1280,height:720}}});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await page.request.get(root+'/api/preview/reasoning/')).status(),401);
 await page.goto(root+'/');await page.screenshot({path:path.join(output,'real-catalog-landing.png')});
 await page.goto(root+'/login');await page.getByLabel('Username',{exact:true}).fill('DEMO-boundary-reader');await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(/\/(dashboard|onboarding)$/);
 await page.goto(root+'/onboarding');await page.locator('.topic-option input').first().check();await page.getByRole('button',{name:'Continue to your brief'}).click();await page.waitForURL('**/dashboard');
 const api=await (await page.request.get(root+'/api/feed/')).json();assert.equal(api.status,'pending');assert.equal(api.events.length,0);assert.deepEqual(api.sources,expected.sources);assert.equal(api.catalog_revision,expected.revision);
 await page.goto(root+'/topics/'+expected.topics[0].id);await page.getByRole('heading',{name:'Source spectrum',exact:true}).waitFor();
 const score=(s,m)=>m==='average'?(()=>{const v=[s.allsides,s.mbfc,s.adfontes].filter(x=>x!==null);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;})():s[m];
 for(const mode of ['allsides','mbfc','adfontes','average']){
  await page.getByLabel('Rating mode',{exact:true}).selectOption(mode);
  assert.equal(await page.locator('.source-row').count(),expected.sources.length);
  for(const [i,s] of expected.sources.entries()){
   const row=page.locator('.source-row').nth(i),v=score(s,mode);assert((await row.innerText()).includes(v===null?'Unrated':v.toFixed(2)));
  }
 }
 const provenance=page.locator('.rating-provenance').first();await provenance.locator('summary').click();
 assert((await provenance.innerText()).includes(expected.sources[0].ratings_checked_at));
 assert((await provenance.innerText()).includes('Reporting date: Not supplied'));
 assert.deepEqual(await provenance.locator('a').evaluateAll(xs=>xs.map(a=>a.href)),[...Object.values(expected.sources[0].rating_provenance).filter(Boolean),expected.sources[0].audience_source_url]);
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});await page.locator('.spectrum').scrollIntoViewIfNeeded();
  assert.equal(await page.locator('body').evaluate(x=>x.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(output,`real-catalog-${width}.png`)});
 }
 await context.close();
 // No inference: original fictional contract example tests unchanged-source identity binding separately.
 const p=await browser.newPage({viewport:{width:1440,height:1000}});
 const session=await (await p.request.get(root+'/api/session/')).json();
 await p.request.post(root+'/api/login/',{headers:{'X-CSRFToken':session.csrfToken,Origin:root},data:{username:'DEMO-boundary-reader',password}});
 const preview=await (await p.request.get(root+'/api/preview/reasoning/')).json();
 assert(preview.reasoning.provenance.fictional);assert.equal(preview.catalog_revision,expected.revision);assert.deepEqual(preview.sources,expected.sources);
 const original=JSON.parse(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_FILE));assert.deepEqual(preview.reasoning,original);
 await p.goto(root+'/preview/reasoning?event='+original.stories[0].event_id);await p.getByRole('heading',{name:'Perspective Comparison',exact:true}).waitFor();
 assert((await p.locator('#reasoning-perspectives').innerText()).includes("producer's fixed registry cohorts"));
 for(const mode of ['allsides','mbfc','adfontes','average'])await p.getByLabel('Rating mode',{exact:true}).selectOption(mode);
 for(const width of [1440,768,390]){await p.setViewportSize({width,height:1000});assert.equal(await p.locator('body').evaluate(x=>x.scrollWidth>innerWidth),false);}
 assert.equal(errors.length,0);await p.close();
 fs.writeFileSync(path.join(output,'catalog-browser-result.json'),JSON.stringify({real_catalog_sources:expected.sources.length,revision:expected.revision,modes:['allsides','mbfc','adfontes','average'],widths:[1440,768,390],original_reasoning_unchanged:true,fixture_story_explicitly_fictional:true,genuine_model_snapshot:false,publisher_enabled:false,video_scope:'auth/navigation/genuine registry only'},null,2));
 console.log('PASS real registry → authenticated API → Next → 4 modes/provenance/nulls/3 widths; original FICTIONAL reasoning unchanged');
};
