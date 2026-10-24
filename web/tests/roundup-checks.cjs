// Explicit TEST derivative, real authenticated HTTP. Never genuine acceptance evidence.
const fs = require('node:fs'), assert = require('node:assert/strict');
module.exports = async ({browser, root, env, password}) => {
  const file = env.QUORUM_REASONING_PREVIEW_FILE, original = fs.readFileSync(file);
  const sample = JSON.parse(original), item = sample.roundup.groups[0].items[0];
  item.status = 'confirmed';
  sample.trace.push({node:'fact_check', iteration:1, event_id:item.event_id,
    decision:'skipped: event cannot reach the impact bar; claims not double-checked', reason:'TEST bar gate', model:null, duration_ms:0});
  const context = await browser.newContext(), page = await context.newPage();
  try {
    fs.writeFileSync(file, JSON.stringify(sample));
    const session = await (await context.request.get(root+'/api/session/')).json();
    assert.equal((await context.request.post(root+'/api/login/', {headers:{'X-CSRFToken':session.csrfToken,Origin:root}, data:{username:'DEMO-boundary-reader',password}})).status(),200);
    await page.goto(root+'/preview/reasoning');
    const row = page.locator('.r-roundup-row').filter({hasText:item.line});
    await row.getByText('Producer status: confirmed', {exact:true}).waitFor();
    await row.getByText('Independent check skipped; not double-checked.', {exact:true}).waitFor();
    await row.locator(':scope > a').click();
    await page.getByText('Independent check skipped; not double-checked.', {exact:true}).waitFor();
    // An event with no recorded skip must not inherit another event's warning.
    sample.trace = sample.trace.filter(s => !(s.node === 'fact_check' && s.event_id === item.event_id));
    fs.writeFileSync(file, JSON.stringify(sample));
    await page.reload();
    await page.getByText(/Independent verification is not established by this roundup entry/).waitFor();
    assert.equal(await page.getByText('Independent check skipped; not double-checked.',{exact:true}).count(),0);
    console.log('PASS: TEST confirmed roundup with skipped check stays producer-attributed on list/detail; absent check never implies verification');
  } finally {fs.writeFileSync(file, original); await context.close();}
};
