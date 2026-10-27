// The sources used for a story on a TEST fixture: the outlets grouped into the event and the evidence's source ids, registry
// order, how each was used, nothing inferred, the inputs untouched.
const assert = require('node:assert/strict');
const { storySources, usedLabel } = require('../lib/story-sources.ts');
const row = (id) => ({ id, name: 'TEST ' + id, domain: id + '.test', kind: 'outlet', allsides: 0, mbfc: 0, adfontes: 0, audience: 1000, audience_source_url: 'https://audience.test/' + id });
const registry = ['TEST-a', 'TEST-b', 'TEST-c', 'TEST-d', 'TEST-e'].map(row);
const event = {
  sources: [row('TEST-d'), row('TEST-b'), row('TEST-outside')],
  reasoning: { claims: [
    { evidence: [{ source_id: 'TEST-a' }, { source_id: 'TEST-b' }, { source_id: null }, {}] },
    { evidence: [{ source_id: 'TEST-unknown' }] },
    { evidence: [] },
  ] },
};
const before = structuredClone({ event, registry });
const used = storySources(event, registry);
assert.deepEqual({ event, registry }, before, 'inputs are not modified');
assert.deepEqual(used.map((s) => s.id), ['TEST-a', 'TEST-b', 'TEST-d', 'TEST-outside'], 'registry order, then story sources the registry lacks');
assert.deepEqual(used.find((s) => s.id === 'TEST-a').used, { story: false, evidence: true });
assert.deepEqual(used.find((s) => s.id === 'TEST-b').used, { story: true, evidence: true });
assert.deepEqual(used.find((s) => s.id === 'TEST-d').used, { story: true, evidence: false });
assert.ok(!used.some((s) => s.id === 'TEST-c' || s.id === 'TEST-e'), 'an unused registry source is not drawn');
assert.ok(!used.some((s) => s.id === 'TEST-unknown'), 'an evidence id outside the registry has no row to draw');
assert.equal(used.find((s) => s.id === 'TEST-b').audience, 1000, 'the registry row carries the values');
assert.equal(usedLabel(used.find((s) => s.id === 'TEST-b')), 'Grouped into this event · Quoted in its evidence');
assert.equal(usedLabel(used.find((s) => s.id === 'TEST-a')), 'Quoted in its evidence');
assert.equal(usedLabel(used.find((s) => s.id === 'TEST-d')), 'Grouped into this event');
assert.equal(usedLabel(registry[0]), null, 'a registry row carries no use label');
assert.deepEqual(storySources({ sources: [row('TEST-c')] }, registry).map((s) => s.id), ['TEST-c'], 'no reasoning: the story sources alone');
assert.deepEqual(storySources({ sources: [], reasoning: { claims: [] } }, registry), [], 'nothing used, nothing drawn');
console.log('PASS: story sources = the outlets grouped into the event and those its evidence quotes by source id, registry order, use labelled, nothing inferred, inputs untouched (TEST)');
