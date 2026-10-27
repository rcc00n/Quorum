const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
module.exports = async ({ browser, root, password }) => {
  const context = await browser.newContext({ timezoneId: 'Pacific/Honolulu', reducedMotion: 'reduce' });
  const page = await context.newPage(), errors = [];
  page.on('pageerror', e => errors.push(e.name));
  try {
    const target = '/events/demo-event?date=2026-10-22&revision=demo-r1#reader-evidence';
    await page.goto(root + target);
    await page.waitForURL(url => url.pathname === '/login');
    assert.equal(new URL(page.url()).searchParams.get('next'), target);
    await page.getByLabel('Username', { exact: true }).fill('DEMO-boundary-reader');
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL(root + target);
    await page.getByRole('tab', { name: 'Evidence', exact: true }).waitFor();
    assert.equal(await page.getByRole('tab', { name: 'Evidence', exact: true }).getAttribute('aria-selected'), 'true');
    await page.locator('.sidebar nav').getByRole('link', { name: 'History', exact: true }).click();
    await page.getByLabel('Edition date', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Edition date', { exact: true }).inputValue(), '2026-10-22');

    const historyFeed = await (await context.request.get(root + '/api/feed/?date=2026-10-22')).json();
    assert.ok(historyFeed.topics.some(topic => topic.id === 'demo-topic'), 'The real local history fixture must expose its topic');
    await page.waitForFunction(() => [...document.querySelectorAll('select option')].some(option => option.value === 'demo-topic'));
    await page.getByLabel('Topic', { exact: true }).selectOption('demo-topic');
    await page.waitForURL(url => url.searchParams.get('topic') === 'demo-topic');
    await page.reload();
    await page.getByLabel('Topic', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Topic', { exact: true }).inputValue(), 'demo-topic');
    await page.getByRole('button', { name: 'Previous day', exact: true }).click();
    await page.waitForURL(url => url.searchParams.get('date') === '2026-10-21');
    await page.getByLabel('Edition date', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Edition date', { exact: true }).inputValue(), '2026-10-21');
    assert.equal(new URL(page.url()).searchParams.get('topic'), 'demo-topic');
    assert.equal(await page.getByLabel('Topic', { exact: true }).inputValue(), 'demo-topic');
    await page.getByRole('button', { name: 'Next day', exact: true }).click();
    await page.waitForURL(url => url.searchParams.get('date') === '2026-10-22');
    await page.getByLabel('Edition date', { exact: true }).waitFor();
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('input[type=date]')?.value === '2026-10-21');
    await page.goForward();
    await page.waitForFunction(() => document.querySelector('input[type=date]')?.value === '2026-10-22');

    for (const route of ['/dashboard?date=2026-10-22', '/topics/demo-topic?date=2026-10-22', '/history?date=2026-10-22&topic=demo-topic']) {
      await page.goto(root + route);
      await page.getByLabel('Edition date', { exact: true }).waitFor();
      await page.getByLabel('Edition date', { exact: true }).fill('2026-10-23');
      await page.waitForURL(url => url.searchParams.get('date') === '2026-10-23');
      await page.reload();
      await page.getByLabel('Edition date', { exact: true }).waitFor();
      assert.equal(await page.getByLabel('Edition date', { exact: true }).inputValue(), '2026-10-23');
      for (const width of [1440, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, route + ' at ' + width);
        for (const name of ['Previous day', 'Next day']) {
          const box = await page.getByRole('button', { name, exact: true }).boundingBox();
          assert.ok(box.width >= 44 && box.height >= 44);
        }
        if (process.env.QUORUM_SCREENSHOTS) {
          fs.mkdirSync(process.env.QUORUM_SCREENSHOTS, { recursive: true });
          await page.screenshot({ path: path.join(process.env.QUORUM_SCREENSHOTS, `edition-${route.split('?')[0].split('/')[1]}-${width}.png`) });
        }
      }
    }
    await page.getByRole('button', { name: 'Today', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('input[type=date]')?.value === new Date().toLocaleDateString('en-CA'));
    assert.equal(await page.getByRole('button', { name: 'Next day', exact: true }).isDisabled(), true);
    assert.deepEqual(errors, []);
    console.log('PASS: real HTTP sign-in returns to exact edition/revision/pane; History/date/topic refresh/back/forward; day controls, local today, 44px targets and four widths');
  } catch (error) {
    console.error('Local edition navigation state: ' + JSON.stringify(await page.evaluate(() => ({
      route: location.pathname + location.search + location.hash,
      date: document.querySelector('input[type=date]')?.value,
      options: [...document.querySelectorAll('select option')].map(option => option.value),
      loading: !!document.querySelector('.loading'),
      alert: document.querySelector('[role=alert]')?.textContent,
    }))));
    throw error;
  } finally { await context.close(); }
};
