// Private local rehearsal: original evidence, disposable auth, no provider or external page requests.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const PINS={snapshot:'c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30',sidecar:'1afba4c0eb7934139d0428f15f55db4d0683bf73d6a0da7edb08992aa5785775'};
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function verifyEvidence(snapshot,sidecar) {
  assert.equal(sha(snapshot),PINS.snapshot,'Original snapshot required');
  assert.equal(sha(sidecar),PINS.sidecar,'Original sidecar required');
  const p=JSON.parse(snapshot);
  assert.equal(p.provenance.fictional,false);assert.equal(p.status,'partial');
  assert.equal(p.stories.length,0);assert.equal(p.roundup.count,28);
  return p;
}
function externalNewOutput(output) {
  assert.ok(path.isAbsolute(output));assert.ok(!fs.existsSync(output),'Output must be new');
  for(let dir=path.dirname(output);;dir=path.dirname(dir)) {
    assert.ok(!fs.existsSync(path.join(dir,'.git')),'Keep recordings outside repositories');
    if(dir===path.dirname(dir))break;
  }
}
function captions() {
  return `WEBVTT

00:00.000 --> 00:12.000
Quorum separates collected reports, source attribution and recorded verification. The dashboard remains pending; this is an unpublished local preview.

00:12.000 --> 00:32.000
This is the unchanged genuine provisional v3: partial, 28 roundup events and zero featured stories. We do not manufacture an article to fill the page.

00:32.000 --> 01:02.000
Each roundup entry retains the producer's status and original source links. These are attributions; a label alone does not establish independent verification.

01:02.000 --> 01:30.000
Open recorded checks for this event. The timeline shows the actual recorded stages and iterations, rather than live inference or hidden chain-of-thought.

01:30.000 --> 01:50.000
A skipped independent check remains explicit when recorded. Missing or incomplete checks never imply that a claim was independently confirmed.

01:50.000 --> 02:50.000
The 40-source registry supports AllSides, MBFC, Ad Fontes and the mean of available ratings. Positions and cohorts recompute; rating and audience attribution stays inspectable.

02:50.000 --> 03:15.000
Partial errors, provisional capture and model declarations remain visible. The config digest discrepancy blocks full execution acceptance; the original evidence has not been altered.

03:15.000 --> 03:50.000
Offline checks demonstrate implemented capabilities. H-MEM hooks remain a default-off proposal despite reference conformance and TEST-state recall evidence. Historical Nightshift probes do not prove the full workflow. Sponsor completion and production release remain blocked.
`;
}
async function main(args) {
  const [candidate,snapshot,sidecar,output,matrix]=args.map(p=>path.resolve(p));
  assert.equal(args.length,5,'Use candidate snapshot sidecar NEW-output matrix-html');
  externalNewOutput(output);
  const original=fs.readFileSync(snapshot),originalSidecar=fs.readFileSync(sidecar),sample=verifyEvidence(original,originalSidecar);
  assert.ok(!fs.existsSync(path.join(candidate,'reasoning/quorum_reasoning/tools/memory.py')),'Use the web-owned candidate, not the provisional owner-patch audit');
  assert.equal(execFileSync('git',['status','--porcelain'],{cwd:candidate,encoding:'utf8'}).trim(),'');
  const build=process.env.QUORUM_WEB_BUILD,python=process.env.QUORUM_PYTHON;
  assert.ok(build&&python,'Explicit isolated build and Python required');
  execFileSync(python,['-c','from deploy.build_integrity import validate_build; import sys; validate_build(".",sys.argv[1])',build],{cwd:candidate,stdio:'pipe'});
  assert.ok(fs.statSync(matrix).isFile());fs.mkdirSync(output,{recursive:true,mode:0o700});
  fs.copyFileSync(matrix,path.join(output,'release-matrix.html'));
  fs.writeFileSync(path.join(output,'narration.vtt'),captions(),{mode:0o600});
  const env={PATH:process.env.PATH,HOME:process.env.HOME,LANG:'C.UTF-8',QUORUM_DRY_RUN:'1',NEXT_TELEMETRY_DISABLED:'1',QUORUM_WEB_BUILD:build,QUORUM_PYTHON:python,QUORUM_TEST_REASONING_SIDECAR:sidecar};
  const child=spawn(process.execPath,[path.join(candidate,'web/tests/boundary.cjs'),'--reasoning','--reasoning-file',snapshot,'--serve'],{cwd:candidate,env,stdio:['ignore','pipe','ignore']});
  let browser,context;
  try {
    const {root,accountFile}=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(Error('Local startup timeout')),45000);
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Local startup stopped'));});
      child.stdout.on('data',chunk=>{
        text+=chunk;const match=text.match(/Unpublished local preview: (http:\/\/127\.0\.0\.1:\d+)\/preview\/reasoning\nPrivate LOCAL test credentials: ([^\n]+)/);
        if(match){clearTimeout(timer);resolve({root:match[1],accountFile:match[2]});}
      });
    });
    assert.ok(path.dirname(accountFile).startsWith(path.join(os.tmpdir(),'quorum-boundary-')));
    assert.equal(path.basename(accountFile),'LOCAL-DEMO-accounts.txt');
    const password=fs.readFileSync(accountFile,'utf8').match(/Password: (\S+)/)[1];
    const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
    // DECISION(2026-10-24, rcc00n/Codex): a 230-second private capture leaves margin below four minutes.
    // Why: the requested 3–5 minute rehearsal must also fit the existing submission checklist's 1–4 minute gate.
    context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:output,size:{width:1440,height:900}}});
    const session=await (await context.request.get(root+'/api/session/')).json();
    assert.equal((await context.request.post(root+'/api/login/',{headers:{'X-CSRFToken':session.csrfToken,Origin:root},data:{username:'DEMO-boundary-reader',password}})).status(),200);
    const payload=await (await context.request.get(root+'/api/preview/reasoning/')).json();
    assert.equal(payload.preview.sha256,PINS.snapshot);assert.equal(payload.preview.published,false);
    assert.equal(payload.reasoning.roundup.count,28);assert.equal(payload.reasoning.stories.length,0);
    assert.equal((await (await context.request.get(root+'/api/feed/')).json()).status,'pending');
    const page=await context.newPage(),errors=[],video=page.video();
    page.on('pageerror',()=>errors.push('page error'));
    await context.route('**/*',route=>{
      const url=route.request().url();
      if(url.startsWith(root+'/')||url===require('node:url').pathToFileURL(path.join(output,'release-matrix.html')).href)return route.continue();
      return route.abort();
    });
    const start=Date.now(),hold=async seconds=>{const remaining=start+seconds*1000-Date.now();if(remaining>0)await page.waitForTimeout(remaining);};
    await page.goto(root+'/dashboard');await page.locator('main').waitFor();await hold(12);
    await page.goto(root+'/preview/reasoning');await page.getByText('UNPUBLISHED / CORPUS EXPERIMENT',{exact:true}).waitFor();
    assert.equal(await page.locator('.r-roundup-row').count(),28);assert.equal(await page.locator('.r-story-row').count(),0);await hold(32);
    const row=page.locator('.r-roundup-row').first();await row.scrollIntoViewIfNeeded();
    assert.ok(await row.locator('.r-sources a').count());await hold(46);
    await row.getByRole('link',{name:'Inspect recorded checks →',exact:true}).focus();await page.keyboard.press('Enter');
    await page.locator('#reasoning-timeline').waitFor();await hold(62);
    await page.locator('#reasoning-timeline').scrollIntoViewIfNeeded();
    const event=sample.roundup.groups[0].items[0].event_id;
    assert.equal(await page.getByLabel('Trace event filter',{exact:true}).inputValue(),event);await hold(90);
    await page.getByLabel('Trace node filter',{exact:true}).selectOption('research');await hold(110);
    await page.goto(root+'/preview/reasoning');await page.getByLabel('Rating mode',{exact:true}).waitFor();
    for(const [i,mode] of ['allsides','mbfc','adfontes','average'].entries()) {
      await page.getByLabel('Rating mode',{exact:true}).selectOption(mode);
      await page.locator('.spectrum').scrollIntoViewIfNeeded();
      assert.equal(await page.locator('.source-row').count(),40);
      if(i===3){const detail=page.locator('.rating-provenance').first();await detail.locator('summary').click();}
      await hold(125+i*15);
    }
    await page.locator('.r-corpus-binding').scrollIntoViewIfNeeded();await hold(185);
    await page.locator('.r-upstream-errors > summary').click();await hold(195);
    await page.goto(require('node:url').pathToFileURL(path.join(output,'release-matrix.html')).href);await hold(230);
    assert.deepEqual(errors,[]);
    assert.equal(sha(fs.readFileSync(snapshot)),PINS.snapshot);assert.equal(sha(fs.readFileSync(sidecar)),PINS.sidecar);
    await context.close();context=null;
    fs.renameSync(await video.path(),path.join(output,'quorum-demo-rehearsal.webm'));
    fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify({duration_target_seconds:230,snapshot_sha256:PINS.snapshot,sidecar_sha256:PINS.sidecar,candidate:execFileSync('git',['rev-parse','HEAD'],{cwd:candidate,encoding:'utf8'}).trim(),published:false,execution_attested:false,owner_memory_adopted:false,sponsor_completion:false},null,2)+'\n',{mode:0o600});
    console.log('PASS: private 230-second genuine demo rehearsal; original hashes unchanged; no inference/publication; narration captions and receipt saved');
  } finally {
    if(context)await context.close();if(browser)await browser.close();
    child.kill('SIGINT');
    await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill('SIGTERM');resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});
  }
}
module.exports={verifyEvidence,externalNewOutput,captions};
if(require.main===module)main(process.argv.slice(2)).catch(()=>{console.error('FAIL: private demo rehearsal; inputs and local credentials withheld');process.exitCode=1;});
