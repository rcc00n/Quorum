// Unit checks for the edition-cut helper used by the brief's waiting state.
//   node web/tests/edition-cut.cjs
const assert = require("assert");
const path = require("path");
const { pathToFileURL } = require("url");

(async () => {
  const { cutUtc, describeCut, utcLabel } = await import(pathToFileURL(path.join(__dirname, "..", "lib", "edition-cut.mjs")).href);
  const iso = (d) => cutUtc(d).toISOString();
  assert.strictEqual(iso("2026-10-26"), "2026-10-26T09:30:00.000Z", "daylight saving: 05:30 EDT = 09:30Z");
  assert.strictEqual(iso("2026-10-31"), "2026-10-31T09:30:00.000Z", "last daylight-saving edition");
  assert.strictEqual(iso("2026-11-01"), "2026-11-01T10:30:00.000Z", "daylight saving ends on 2026-11-01: 05:30 EST = 10:30Z");
  assert.strictEqual(iso("2027-01-15"), "2027-01-15T10:30:00.000Z", "standard time in January");
  assert.strictEqual(iso("2026-03-08"), "2026-03-08T09:30:00.000Z", "daylight saving starts 2026-03-08 at 02:00, before the cut");
  assert.strictEqual(utcLabel(cutUtc("2026-10-26")), "09:30 UTC");
  const before = describeCut("2026-10-26", new Date("2026-10-26T07:00:00Z"));
  assert.strictEqual(before.passed, false);
  assert.strictEqual(before.hoursUntil, 3, "2.5 h rounds up to 3");
  const after = describeCut("2026-10-26", new Date("2026-10-26T12:00:00Z"));
  assert.strictEqual(after.passed, true);
  assert.strictEqual(after.hoursUntil, 0);
  assert.throws(() => cutUtc("26-10-2026"), /YYYY-MM-DD/);
  console.log("PASS: edition cut (10 cases)");
})().catch((e) => {
  console.error("FAIL: " + e.message);
  process.exit(1);
});
