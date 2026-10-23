// Recorded FICTIONAL/TEST traces only. No inference, hidden graph or timestamps.
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const { recordedLoops } = require("../lib/reasoning-trace.ts");
const sample = JSON.parse(
  fs.readFileSync(
    path.join(
      __dirname,
      "../../backend/portal/fixtures/reasoning-demo/snapshot.sample.json",
    ),
  ),
);
assert.equal(sample.trace.length, 45);
assert.deepEqual(
  recordedLoops(sample.trace).map((l) => l.returns.length),
  [3, 2],
);
assert.deepEqual(
  recordedLoops(
    sample.trace.filter((s) => s.event_id === sample.stories[0].event_id),
  ).map((l) => l.returns.length),
  [1, 1],
);
const step = (node, iteration, event_id = "TEST-event") => ({
  node,
  iteration,
  event_id,
  decision: "TEST recorded decision",
  reason: "TEST public reason",
  model: null,
  duration_ms: 0,
});
assert.equal(
  recordedLoops([
    step("research", 1),
    step("verify", 1),
    step("research", 2),
  ])[0].returns.length,
  1,
);
// Cross-event adjacency, standalone repeats, missing middle stages, intervening same-event stages,
// and non-increasing iterations cannot establish a recorded A→B→A return.
for (const trace of [
  [
    step("research", 1, "TEST-a"),
    step("verify", 1, "TEST-b"),
    step("research", 2, "TEST-a"),
  ],
  [step("research", 2)],
  [step("research", 1), step("research", 2)],
  [
    step("research", 1),
    step("verify", 1),
    step("frame", 1),
    step("research", 2),
  ],
  [step("research", 1), step("verify", 1), step("research", 1)],
  [step("research", 2), step("verify", 2), step("research", 1)],
])
  assert.equal(recordedLoops(trace)[0].returns.length, 0);
const interleaved = [
  step("research", 1, "TEST-a"),
  step("research", 1, "TEST-b"),
  step("verify", 1, "TEST-a"),
  step("verify", 1, "TEST-b"),
  step("research", 2, "TEST-a"),
];
assert.deepEqual(recordedLoops(interleaved)[0].returns, [
  { event: "TEST-a", from: 1, to: 2 },
]);
assert.deepEqual(
  recordedLoops([]).map((l) => l.returns.length),
  [0, 0],
);
console.log(
  "PASS: exact sample loop counts; event isolation, interleaving, no invented returns from repeat labels or absent stages (FICTIONAL/TEST)",
);
