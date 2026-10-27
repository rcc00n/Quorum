// Exact registry cohort shares on a TEST fixture: values, mode change, null rating, zero and absent audience.
const assert = require('node:assert/strict');
const { cohortShares } = require('../lib/spectrum-cohorts.ts');
const fixture = [
  { id: 'TEST-major-left', tier: 'major', score: -0.5, audience: 600, audienceCited: true },
  { id: 'TEST-major-left-2', tier: 'major', score: -0.3, audience: 200, audienceCited: true },
  { id: 'TEST-major-right', tier: 'major', score: 0.6, audience: 200, audienceCited: true },
  { id: 'TEST-minor-left', tier: 'minor', score: -1, audience: null, audienceCited: false },
  { id: 'TEST-minor-right', tier: 'minor', score: 0.25, audience: 0, audienceCited: true },
  { id: 'TEST-minor-centre', tier: 'minor', score: 0.1, audience: 50, audienceCited: true },
  { id: 'TEST-agency', tier: null, score: 0, audience: 900, audienceCited: true },
  { id: 'TEST-unrated', tier: 'major', score: null, audience: 100, audienceCited: true },
  { id: 'TEST-uncited', tier: 'minor', score: -0.5, audience: 70, audienceCited: false },
];
const original = structuredClone(fixture);
const r = cohortShares(fixture);
assert.deepEqual(fixture, original);
assert.equal(r.unrated, 1); assert.equal(r.noTier, 1); assert.equal(r.tiered, 7); assert.equal(r.centre, 1);
assert.equal(r.withAudience, 5); assert.equal(r.withoutAudience, 2); assert.equal(r.audienceDenominator, 1050);
const row = k => r.rows.find(x => x.key === k);
assert.deepEqual([row('major-left').outlets, row('major-right').outlets, row('minor-left').outlets, row('minor-right').outlets], [2, 1, 2, 1]);
assert.equal(row('major-left').outletShare, 2 / 7); assert.equal(row('minor-right').outletShare, 1 / 7);
assert.equal(row('major-left').audience, 800); assert.equal(row('major-left').audienceShare, 800 / 1050);
assert.equal(row('minor-right').audience, 0); assert.equal(row('minor-right').audienceShare, 0, 'a cited zero audience is a zero share, not absent');
assert.equal(row('minor-left').audience, 0); assert.equal(row('minor-left').withoutAudience, 2, 'absent and uncited audiences are counted apart');
// mode change: the same registry under another mode moves a source across the centre
const other = cohortShares(fixture.map(s => s.id === 'TEST-major-right' ? { ...s, score: -0.4 } : s));
assert.deepEqual([other.rows[0].outlets, other.rows[1].outlets], [3, 0]); assert.equal(other.rows[1].audienceShare, 0);
// null and empty cases
const none = cohortShares([]);
assert.deepEqual(none.rows.map(x => [x.outlets, x.outletShare, x.audience, x.audienceShare]), [[0, null, 0, null], [0, null, 0, null], [0, null, 0, null], [0, null, 0, null]]);
assert.equal(none.audienceDenominator, 0);
const noAudience = cohortShares([{ id: 'TEST', tier: 'major', score: -1, audience: null, audienceCited: false }]);
assert.equal(noAudience.rows[0].outletShare, 1); assert.equal(noAudience.rows[0].audienceShare, null, 'no cited audience means no audience share, never zero');
assert.equal(noAudience.withoutAudience, 1);
console.log('PASS: exact registry cohort shares, stated denominators, mode change, null rating, zero and absent audience kept apart, immutable input');
