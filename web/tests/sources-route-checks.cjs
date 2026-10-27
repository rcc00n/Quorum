const assert=require('node:assert/strict');
module.exports=async({page,browser,root})=>{
 await page.getByRole('link',{name:'Sources',exact:true}).click();await page.waitForURL('**/sources');
 await page.getByRole('heading',{name:'Source spectrum',level:1,exact:true}).waitFor();
 const day=await page.evaluate(()=>new Date().toLocaleDateString('en-CA'));
 const response=await page.request.get(`${root}/api/feed/?date=${day}`);assert.equal(response.status(),200);
 const data=await response.json();
 // WEB-SPECTRUM-POLISH-02: the ledger sits behind a closed disclosure whose summary carries the registry count;
 // rows are grouped (institutional sources last), so completeness is checked by name, not by feed position.
 const ledger=page.locator('.spectrum .sp-ledger');
 if(!data.sources.length){assert.equal(await ledger.count(),0);assert.equal(await page.locator('.source-row').count(),0);}
 else{
 assert.equal(await ledger.getAttribute('open'),null);
 assert.equal((await ledger.locator('> summary').innerText()).trim(),`All ${data.sources.length} sources`);
 await ledger.locator('> summary').click();await ledger.locator('.source-row').first().waitFor();
 assert.equal(await page.locator('.source-row').count(),data.sources.length);
 const rowTexts=await page.locator('.source-row').allInnerTexts();
 for(const source of data.sources)assert.ok(rowTexts.some(t=>t.includes(source.name)),'row missing: '+source.name);
 const bodies=data.sources.filter(s=>s.kind==='official'||s.kind==='military');
 if(bodies.length){assert.equal((await page.locator('.sp-ledger-group-head').textContent()).trim(),`${bodies.length} official and institutional ${bodies.length===1?'source':'sources'} · no editorial rating`);
  const groupTexts=await page.locator('.sp-ledger-group .source-row').allInnerTexts();assert.equal(groupTexts.length,bodies.length);
  for(const b of bodies)assert.ok(groupTexts.some(t=>t.includes(b.name)),'institutional row missing: '+b.name);}
 else assert.equal(await page.locator('.sp-ledger-group').count(),0);
 }
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);}
 const visitor=await browser.newPage();try{
  await visitor.goto(root+'/sources');await visitor.waitForURL(url=>url.pathname==='/login');
  assert.equal(new URL(visitor.url()).searchParams.get('next'),'/sources');
  assert.equal(await visitor.locator('.source-row').count(),0);
  assert.equal((await visitor.request.get(root+'/api/feed/')).status(),401);
 }finally{await visitor.close()}
 console.log('PASS: Sources navigation → authenticated registry map; closed ledger with the registry count, complete grouped source list/3 widths; anonymous route redirects and API denies');
};
