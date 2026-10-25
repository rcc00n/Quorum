// Explicit TEST derivative, real authenticated HTTP. Never genuine acceptance evidence.
const fs = require('node:fs'), assert = require('node:assert/strict');
module.exports = async ({browser, root, env, password}) => {
  const file = env.QUORUM_REASONING_PREVIEW_FILE, original = fs.readFileSync(file);
  const sample = JSON.parse(original), item = sample.roundup.groups[0].items[0];
  item.status = 'confirmed';
  sample.trace.push({node:'fact_check', iteration:1, event_id:item.event_id,
    decision:'  SKIPPED : event cannot reach the impact bar; claims not double-checked', reason:'TEST bar gate', model:null, duration_ms:0});
  const context = await browser.newContext(), page = await context.newPage();
  try {
    fs.writeFileSync(file, JSON.stringify(sample));
    const session = await (await context.request.get(root+'/api/session/')).json();
    assert.equal((await context.request.post(root+'/api/login/', {headers:{'X-CSRFToken':session.csrfToken,Origin:root}, data:{username:'DEMO-boundary-reader',password}})).status(),200);
    await page.goto(root+'/preview/reasoning');
    const row = page.locator('.r-roundup-row').filter({hasText:item.line});
    await row.getByText('Producer status: confirmed', {exact:true}).waitFor();
    await row.getByText('Independent check skipped; not double-checked.', {exact:true}).waitFor();
    for (const width of [1440,390]) {
      await page.setViewportSize({width,height:900});
      await page.getByRole('link',{name:'Skip to content',exact:true}).focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('#main').evaluate(el=>el===document.activeElement),true);
      const roundupLink=page.getByRole('navigation',{name:'Read and investigate'}).getByRole('link',{name:'Also today',exact:true});
      await roundupLink.focus();await page.keyboard.press('Enter');
      assert.equal(await page.locator('#reasoning-roundup').evaluate(el=>el===document.activeElement),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
    const inspect = row.getByRole('link',{name:'Inspect recorded checks →',exact:true});
    const href=new URL(await inspect.getAttribute('href'),root);
    assert.equal(href.searchParams.get('date'),sample.edition_date);
    assert.equal(href.searchParams.get('version'),String(sample.version));
    assert.equal(href.hash,'#reasoning-timeline');
    await inspect.focus(); await page.keyboard.press('Enter');
    await page.getByText('Independent check skipped; not double-checked.', {exact:true}).waitFor();
    await page.waitForFunction(() => document.activeElement?.id === 'reasoning-timeline', null, {timeout:5000});
    await page.keyboard.press('Tab');
    assert.equal(await page.getByLabel('Trace event filter',{exact:true}).evaluate(el=>el===document.activeElement),true);
    assert.equal(await page.getByLabel('Trace event filter',{exact:true}).inputValue(),item.event_id);
    await page.getByLabel('Trace node filter',{exact:true}).selectOption('research');
    await page.getByText('Independent check skipped; not double-checked.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'This event’s steps',exact:true}).waitFor();
    // An event with no recorded skip must not inherit another event's warning.
    sample.trace = sample.trace.filter(s => !(s.node === 'fact_check' && s.event_id === item.event_id));
    fs.writeFileSync(file, JSON.stringify(sample));
    await page.reload();
    await page.getByText(/Independent verification is not established by this roundup entry/).waitFor();
    assert.equal(await page.getByText('Independent check skipped; not double-checked.',{exact:true}).count(),0);
    console.log('PASS: TEST confirmed roundup with skipped check stays producer-attributed on list/detail; absent check never implies verification; keyboard focus and no overflow at 1440/390px');
  } finally {fs.writeFileSync(file, original); await context.close();}
};
