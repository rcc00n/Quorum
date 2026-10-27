// Public fixture-bound presentation only; no account, model call or database.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const evidence=JSON.parse(fs.readFileSync(path.join(__dirname,'../fixtures/landing/zetaris-evidence-russia-ukraine-war-2026-10-24.json')));
(async()=>{
 const b=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
 try{
  const p=await b.newPage({reducedMotion:'reduce',viewport:{width:1440,height:1100}}),errors=[];p.on('pageerror',e=>errors.push(e.name));
  let queries=0;p.on('request',r=>{if(/\/api\//.test(r.url()))queries++});
  await p.goto(process.env.QUORUM_TEST_URL||'http://127.0.0.1:3017');
  const sheet=p.locator('.lp-sheet-focus'),detail=sheet.locator('.lp-sheet-details');await sheet.waitFor();
  assert.deepEqual(await sheet.locator('.lp-figures dd').allTextContents(),[String(evidence.documents.count),String(Object.keys(evidence.documents.by_source).length)]);
  assert.ok((await sheet.locator('#evidence-title').textContent()).includes(evidence.edition_date));
  assert.equal(await detail.getAttribute('open'),null);assert.equal(await detail.locator('.lp-kv').first().isVisible(),false);
  await detail.locator(':scope > summary').focus();await p.keyboard.press('Enter');assert.notEqual(await detail.getAttribute('open'),null);
  await detail.getByText(evidence.route,{exact:true}).waitFor();
  await detail.locator('.lp-sql > summary').click();
  assert.deepEqual(await detail.locator('pre code').allTextContents(),[evidence.sql.documents,evidence.sql.official_docs]);
  assert.ok((await detail.innerText()).includes(evidence.commit));
  await detail.locator(':scope > summary').click();
  for(const width of [1440,768,390]){await p.setViewportSize({width,height:1100});assert.equal(await p.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);}
  assert.equal(queries,0);assert.deepEqual(errors,[]);
  console.log('PASS: fixture-exact hero counts/date; native provenance/SQL/commit retained on demand; keyboard, three widths and zero API calls');
 }finally{await b.close()}
})().catch(e=>{console.error('FAIL: landing evidence '+e.name+' '+e.message);process.exit(1)});
