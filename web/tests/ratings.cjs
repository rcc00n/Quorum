const assert = require("node:assert/strict");
const { rating, cohort, safeUrl } = require("../lib/api.ts");
// Numeric unit inputs only; these are not ratings assigned to any news source.
const row = { allsides: null, mbfc: null, adfontes: null };
assert.equal(rating(row, "average"), null);
assert.equal(rating({ ...row, allsides: 0 }, "average"), 0);
assert.equal(rating({ ...row, allsides: -0.5, mbfc: 0 }, "average"), -0.25);
assert.equal(rating({ ...row, allsides: -0.5 }, "mbfc"), null);
assert.equal(cohort(-0.25), "Left");
assert.equal(cohort(0.25), "Right");
assert.equal(cohort(0.249), "Center");
assert.equal(safeUrl("javascript:alert(1)"), undefined);
assert.equal(
  safeUrl("https://example.com/source"),
  "https://example.com/source",
);
console.log(
  "PASS: available-rating mean, missing ratings, thresholds and safe evidence links",
);
