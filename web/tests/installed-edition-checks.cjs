// Read-only accepted editions through real local HTTP; original bytes and credentials never printed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');

module.exports = async ({browser, root, password, temp, build}) => {
  assert.equal(new URL(root).hostname, '127.0.0.1');
  const source = process.env.QUORUM_TEST_INSTALLED_SOURCE;
  const raw = fs.readFileSync(source);
  const hash = crypto.createHash('sha256').update(raw).digest('hex');
  const original = JSON.parse(raw);
  assert.equal(original.provenance.fictional, false);
  const day = original.edition_date;
  const context = await browser.newContext({timezoneId: 'Pacific/Honolulu'});
  assert.equal((await context.request.get(`${root}/api/feed/?date=${day}`)).status(), 401);
  const session = await (await context.request.get(root + '/api/session/')).json();
  assert.equal((await context.request.post(root + '/api/login/', {
    headers: {'X-CSRFToken': session.csrfToken, Origin: root},
    data: {username: 'DEMO-boundary-reader', password},
  })).status(), 200);
  const feed = await (await context.request.get(`${root}/api/feed/?date=${day}`)).json();
  assert.equal(feed.status, 'available');
  assert.equal(feed.publication.mode, 'live');
  assert.equal(feed.events.length, original.stories.length);
  assert.equal(feed.publication.provisional, true);
  assert.ok(feed.publication.corpus_as_of_utc);
  const typed = path.join(temp, 'installed-api.json');
  fs.writeFileSync(typed, JSON.stringify(feed), {mode: 0o600});
  execFileSync(process.execPath, [path.join(__dirname, 'contract.cjs')], {
    env: {...process.env, QUORUM_SNAPSHOT_FILE: typed, QUORUM_WEB_BUILD: build}, stdio: 'pipe',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', () => errors.push('page_error'));
  const preferenceSession = await (await context.request.get(root + '/api/session/')).json();
  assert.equal((await context.request.post(root + '/api/preferences/', {
    headers: {'X-CSRFToken': preferenceSession.csrfToken, Origin: root},
    data: {topics: [original.topic_id]},
  })).status(), 200);
  await page.goto(`${root}/dashboard?date=${day}`);
  await page.locator('.tb-card h3').first().waitFor();
  // The head never animates (cabinet pages pass, 2026-10-27); the sections below the rule do, unless motion is reduced.
  await page.locator('.tb-section[data-revealed="true"]').first().waitFor();
  assert.equal(await page.locator('.tb-head').evaluate(e=>e.classList.contains('q-reveal')),false);
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.tb-section').first().evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});

  const localLabel = await page.evaluate(() => new Intl.DateTimeFormat('en', {
    month: 'long', day: 'numeric', year: 'numeric',
  }).format(new Date()));
  assert.equal(await page.locator('.workspace-header span').last().textContent(), localLabel);
  assert.equal(await page.locator('input[type="date"]').inputValue(), day);
  assert.equal(await page.locator('.tb-card h3').first().textContent(), original.stories[0].headline);
  if (original.stories[0].needs_review)
    await page.getByText(/Requires editorial review/).first().waitFor();
  for (const story of original.stories) {
    const result = await (await context.request.get(`${root}/api/events/${story.event_id}/?date=${day}`)).json();
    assert.deepEqual(result.events[0].reasoning, story);
    assert.deepEqual(result.events[0].reasoning_context.trace, original.trace);
    await page.goto(`${root}/events/${story.event_id}?date=${day}`);
    await page.getByRole('heading', {name: story.headline, exact: true}).waitFor();
    await require('./impact-checks.cjs')({page,event:feed.events.find(e=>e.id===story.event_id)});
    await require('./reader-checks.cjs')({page});
    await require("./navigator-checks.cjs")({page});
    for (const name of ['Evidence Explorer', 'Perspective Comparison', 'Investigation Timeline'])
      await page.getByRole('heading', {name, exact: true}).waitFor();
    await page.getByText(/Provisional corpus as of/).first().waitFor();
    if (story.needs_review)
      await page.getByText('Requires editorial review', {exact: true}).first().waitFor();
    assert.equal(await page.locator('.r-claim').count(), story.claims.length);
    await page.locator('.r-claim').first().locator(':scope > summary').click();
    assert.ok(await page.locator('.r-claim').first().locator('.r-chain').count() >= 1);
    await page.getByLabel('Trace event filter', {exact: true}).selectOption('');
    assert.equal(await page.locator('.r-trace>li').count(), original.trace.length);
    assert.deepEqual(await page.locator('.r-step-decision').allTextContents(), original.trace.map(s => s.decision));
    const links = await page.locator('#reasoning-evidence a[href]').evaluateAll(rows => rows.map(a => a.href));
    assert.ok(story.claims.flatMap(c => c.evidence).some(e => links.includes(e.url)));
    for (const mode of ['allsides', 'mbfc', 'adfontes', 'average']) {
      await page.getByLabel('Rating mode', {exact: true}).first().selectOption(mode);
      await page.getByLabel('Cohort rating context', {exact: true}).selectOption(mode);
    }
    // The Map draws the sources used for this story, not the registry (story source map amendment, 2026-10-27).
    const {storySources} = require('../lib/story-sources.ts');
    const used = storySources(result.events[0], result.sources || feed.sources);
    await require('./spectrum-checks.cjs')({page, sources:used, scope:'story'});
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({width, height: 900});
      assert.equal(await page.locator('body').evaluate(e => e.scrollWidth > innerWidth), false);
    }
    assert.equal(await page.getByText(/DEMO · Fictional interface fixture/).count(), 0);
    assert.equal(await page.locator('a[href^="/preview/reasoning"]').count(), 0);
  }
  // "Also today" lives on Home only since the cabinet pages pass (web/DESIGN.md › Cabinet, PR #69), as analysis.cjs
  // asserts: the topic page has none, the board carries every roundup line of the edition (rows past the fold are in
  // the DOM, hidden). This check is not in CI and had kept the old placement (2026-10-27, Anastasia/Claude Code).
  await page.goto(`${root}/topics/${original.topic_id}?date=${day}`);
  if (original.stories.length) await page.locator('.topic-story-title', {hasText: original.stories[0].headline}).first().waitFor();
  else await page.getByText('A quiet day for major stories').first().waitFor();
  assert.equal(await page.getByRole('heading', {name: 'Also today', exact: true}).count(), 0);
  await page.goto(`${root}/dashboard?date=${day}`);
  await page.getByRole('heading', {name: 'Also today', exact: true}).waitFor();
  assert.equal(await page.locator('.roundup-item').count(), original.roundup.count);
  await require('./sources-route-checks.cjs')({page,browser,root});
  const next = await (await context.request.get(root + '/api/session/')).json();
  assert.equal((await context.request.post(root + '/api/logout/', {
    headers: {'X-CSRFToken': next.csrfToken, Origin: root}, data: {},
  })).status(), 200);
  assert.equal((await context.request.get(`${root}/api/feed/?date=${day}`)).status(), 401);
  assert.deepEqual(errors, []);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex'), hash);
  await context.close();
  console.log(`PASS: genuine installed edition → authenticated Django/Next/browser; dated board, ${original.stories.length} stories, ${original.roundup.count} roundup, ${original.trace.length} exact trace rows; evidence/review/rating modes/three widths/logout; original unchanged`);
};
