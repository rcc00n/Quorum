const assert = require('node:assert/strict');
(async () => {
  const { validEditionDate, shiftEditionDate, editionHref } = await import('../lib/edition-navigation.mjs');
  const { workspaceReturnPath } = await import('../lib/return-path.mjs');
  for (const day of ['2026-10-26', '2024-02-29', '2026-12-31']) assert.ok(validEditionDate(day));
  for (const day of [undefined, '', '2026-02-29', '2026-04-31', '2026-13-01', '2026-2-01', '0000-01-01']) assert.equal(validEditionDate(day), false);
  assert.equal(shiftEditionDate('2026-11-01', -1), '2026-10-31');
  assert.equal(shiftEditionDate('2026-12-31', 1), '2027-01-01');
  assert.equal(shiftEditionDate('2024-03-01', -1), '2024-02-29');
  assert.equal(shiftEditionDate('bad', 1), null);
  assert.equal(shiftEditionDate('9999-12-31', 1), null);
  assert.equal(editionHref('/history', '2026-10-26', 'policy & trade'), '/history?date=2026-10-26&topic=policy+%26+trade');
  const target = '/events/story-one?date=2026-10-26&revision=original%201#reader-evidence';
  assert.equal(workspaceReturnPath(target), target);
  for (const value of [null, '', 'https://example.com', '//example.com', '/\\example.com', '/login?next=/login', '/api/logout/', '/staff/', '/sources\n', '/%2fexample.com']) assert.equal(workspaceReturnPath(value), '/dashboard');
  assert.equal(workspaceReturnPath('/history?date=2026-10-26&topic=policy'), '/history?date=2026-10-26&topic=policy');
  console.log('PASS: calendar/leap/year/DST-safe edition dates, encoded topic filters and bounded local sign-in destinations');
})().catch(e => { console.error(e); process.exit(1); });
