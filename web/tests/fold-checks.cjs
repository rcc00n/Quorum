// Keyboard and content check of the "Also today" fold (components/roundup-group.tsx) on a TEST group of five rows.
// Real authenticated HTTP for the session, sign-in and preferences; the board's feed is the real response with one
// TEST edition added by this test (page.route on /api/feed/), built from the FICTIONAL reasoning sample's first
// roundup group, since the reasoning mode installs no reader edition. Never acceptance evidence.
// DECISION(2026-10-27, Anastasia/Claude Code; Vadim's keyboard finding on PR #62, comment 6436653148): the check asserts,
// at 1440 and 390 px, two readable rows and a cut third row that is inert, rows four and five hidden, Tab from the
// second row's last link reaching "Show 3 more" with no stop in unreadable content, Enter opening the group with the
// exact five lines, labels and sources, Space folding it back with focus kept on the button, and no overflow.
const fs = require('node:fs'), assert = require('node:assert/strict');
module.exports = async ({browser, root, env, password}) => {
  const sample = JSON.parse(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_FILE));
  const day = sample.edition_date, base = sample.roundup.groups[0];
  const items = Array.from({length: 5}, (_, i) => {
    const it = base.items[i % base.items.length];
    // Row 2 is flagged and row 3 is a raw-title fallback (2026-10-27): both labels render on the row.
    return {
      event_id: null, text: `TEST fold row ${i + 1}: ${it.line}`, status: 'unknown', label: it.status,
      line_source: i === 2 ? 'title' : null, needs_review: i === 1,
      sources: it.sources.map((s, j) => ({title: `${s.title} TEST ${i + 1}.${j + 1}`, url: s.url})),
    };
  });
  const context = await browser.newContext(), page = await context.newPage();
  const errors = [];
  page.on('pageerror', () => errors.push('page_error'));
  try {
    const session = await (await context.request.get(root + '/api/session/')).json();
    assert.equal((await context.request.post(root + '/api/login/', {
      headers: {'X-CSRFToken': session.csrfToken, Origin: root},
      data: {username: 'DEMO-boundary-reader', password},
    })).status(), 200);
    // The reasoning mode serves an empty catalog, so the followed topic and its catalog row are supplied to the page
    // with the edition: the session and feed responses are the real ones with those TEST fields added.
    const topic = sample.topic_id;
    await page.route('**/api/session/**', async (route) => {
      const res = await route.fetch(), data = await res.json();
      await route.fulfill({response: res, json: {...data, user: data.user && {...data.user, topics: [topic]}}});
    });
    const edition = {
      topic_id: topic, date: day, completion: 'complete', quiet_day: false, summary: 'TEST fold summary.',
      provisional: true, corpus_as_of_utc: null, edition_window_utc: [sample.window.start, sample.window.end],
      closed_edition: false, warnings: [], missing_provenance: [],
      roundup: [{name: 'TEST single source', items}],
    };
    await page.route('**/api/feed/**', async (route) => {
      const res = await route.fetch(), data = await res.json();
      await route.fulfill({response: res, json: {
        ...data, status: 'available', editions: [edition],
        topics: [{id: topic, name: 'TEST fold topic'}, ...(data.topics || []).filter((t) => t.id !== topic)],
        publication: {...(data.publication || {}), status: 'live', mode: 'live'},
      }});
    });
    await page.goto(`${root}/dashboard?date=${day}`);
    const group = page.locator('.roundup-group').first();
    await group.waitFor();
    const rows = group.locator('.roundup-item'), button = group.locator('.roundup-more');
    const focused = () => page.evaluate(() => {
      const el = document.activeElement;
      return el ? (el.className || el.tagName) + '|' + (el.textContent || '').trim().slice(0, 40) : '';
    });
    const folded = async (label) => {
      assert.equal(await rows.count(), 5, label);
      assert.equal(await group.locator('.roundup-item[hidden]').count(), 2, label);
      assert.equal(await group.locator('.roundup-item[inert]').count(), 1, label);
      assert.equal(await rows.nth(2).getAttribute('inert'), '', label);
      assert.equal(await rows.nth(0).getAttribute('inert'), null, label);
      assert.equal(await rows.nth(1).getAttribute('inert'), null, label);
      assert.equal(await button.textContent(), 'Show 3 more', label);
      assert.equal(await button.getAttribute('aria-expanded'), 'false', label);
      // The teaser's links cannot take focus while the row is unreadable.
      assert.equal(await rows.nth(2).locator('a').first().evaluate((a) => { a.focus(); return document.activeElement === a; }), false, label);
    };
    for (const width of [1440, 390]) {
      await page.setViewportSize({width, height: 900});
      await folded(`folded at ${width}`);
      await rows.nth(1).locator('a').last().focus();
      await page.keyboard.press('Tab');
      assert.match(await focused(), /^roundup-more\|Show 3 more$/, `Tab from the second row at ${width}`);
      await page.keyboard.press('Enter');
      assert.equal(await button.getAttribute('aria-expanded'), 'true');
      assert.equal(await button.textContent(), 'Show fewer');
      assert.equal(await group.locator('.roundup-item[hidden]').count(), 0);
      assert.equal(await group.locator('.roundup-item[inert]').count(), 0);
      assert.deepEqual(await rows.evaluateAll((els) => els.map((el) => el.querySelector('p').textContent)), items.map((it) => it.text));
      assert.deepEqual(await rows.locator('.story-review').allTextContents(), ['Requires editorial review']);
      assert.equal(await rows.nth(1).locator('.story-review').count(), 1);
      // The label is the 12 px tag at its own width, never stretched across the text column (review of 2026-10-27).
      assert.deepEqual(await rows.nth(1).locator('.story-review').evaluate((e) => {
        const w = e.getBoundingClientRect().width; e.style.width = 'max-content';
        const natural = e.getBoundingClientRect().width; e.style.width = '';
        return [getComputedStyle(e).fontSize, w <= natural + 1];
      }), ['12px', true]);
      assert.deepEqual(await rows.locator('p.help').allTextContents(), ['Source headline fallback; no generated roundup line was supplied.']);
      assert.equal(await rows.nth(2).locator('p.help').count(), 1);
      // The fallback line is styled like its section's own help line, not like the row text (review of 0c130c2).
      const [fallback, sectionHelp] = await rows.nth(2).locator('p.help').evaluate((e) => {
        const style = (el) => { const s = getComputedStyle(el); return [s.fontSize, s.fontFamily, s.color]; };
        const sibling = e.closest('section')?.querySelector(':scope > p.help');
        return [style(e), sibling ? style(sibling) : null];
      });
      assert.ok(sectionHelp, 'the Also today section has its own help line');
      assert.deepEqual(fallback, sectionHelp);
      assert.deepEqual(await rows.locator('small').allTextContents(),
        items.map((it) => it.label.charAt(0).toUpperCase() + it.label.slice(1)));
      for (let i = 0; i < 5; i++) {
        assert.deepEqual(await rows.nth(i).locator('.article-references a').allTextContents(), items[i].sources.map((s) => s.title));
        assert.equal(await rows.nth(i).evaluate((el) => el.getBoundingClientRect().height > 0 && getComputedStyle(el).overflow !== 'hidden'), true);
      }
      await rows.nth(4).locator('a').last().focus();
      assert.equal(await rows.nth(4).locator('a').last().evaluate((a) => document.activeElement === a), true);
      await button.focus();
      await page.keyboard.press('Space');
      await folded(`folded again at ${width}`);
      assert.match(await focused(), /^roundup-more\|Show 3 more$/, `focus after Space at ${width}`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `overflow at ${width}`);
    }
    assert.deepEqual(errors, []);
    console.log('PASS: TEST five-row roundup group folds at the third row with the teaser inert and rows four and five hidden; Tab skips unreadable content to "Show 3 more"; Enter/Space open and fold with exact lines, labels and sources; focus kept; no overflow at 1440/390');
  } finally {await context.close();}
};
