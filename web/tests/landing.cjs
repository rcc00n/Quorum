// Landing page checks. Always: the fixtures the page renders are byte-for-byte copies of their sources
// (web/fixtures/landing/README.md). With QUORUM_TEST_URL set: the served page carries every section anchor,
// the hero figures equal the evidence file's counts, and the fictional label is present whenever the trace
// comes from the dry-run sample. No model call, no database, no credentials.
//   node web/tests/landing.cjs
//   QUORUM_TEST_URL=http://127.0.0.1:3017 node web/tests/landing.cjs
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const root = path.resolve(__dirname, "..", "..");
const fixtures = path.join(root, "web", "fixtures", "landing");

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

// 1. Evidence copy equals its source.
const evidenceSource = path.join(root, "collectors", "zetaris", "evidence", "russia-ukraine-war_2026-10-24.json");
const evidenceCopy = path.join(fixtures, "zetaris-evidence-russia-ukraine-war-2026-10-24.json");
if (fs.existsSync(evidenceSource)) {
  assert.ok(
    fs.readFileSync(evidenceSource).equals(fs.readFileSync(evidenceCopy)),
    "web/fixtures/landing evidence copy differs from collectors/zetaris/evidence",
  );
  console.log("PASS: evidence fixture is a byte-for-byte copy of collectors/zetaris/evidence");
} else {
  console.log("SKIP: collectors/ not in this checkout; evidence copy not compared");
}
const evidence = readJson(evidenceCopy);
assert.strictEqual(evidence.sanitization, "no lead, no article/official text, no credentials; titles truncated to 80 chars");
const reuters = evidence.documents.sample.filter((s) => s.source_id === "reuters");
assert.strictEqual(reuters.length, 3, "the typewriter expects the three Reuters titles of the sample");

// 2. Trace sample rows exist verbatim in the committed dry-run sample, and are labelled fictional.
const traceCopy = readJson(path.join(fixtures, "trace.sample.json"));
assert.strictEqual(traceCopy.fictional, true, "trace.sample.json must be labelled fictional");
const sampleSource = path.join(root, "docs", "examples", "snapshot.sample.json");
if (fs.existsSync(sampleSource)) {
  const sample = readJson(sampleSource);
  const keys = ["node", "iteration", "event_id", "decision", "reason", "model", "duration_ms"];
  for (const row of traceCopy.rows) {
    const found = sample.trace.some((r) => keys.every((k) => (r[k] ?? null) === (row[k] ?? null)));
    assert.ok(found, "trace row not found verbatim in docs/examples/snapshot.sample.json: " + row.node);
  }
  assert.strictEqual(sample.provenance.fictional, true);
  console.log("PASS: " + traceCopy.rows.length + " trace rows are verbatim rows of the fictional dry-run sample");
} else {
  console.log("SKIP: docs/examples not in this checkout; trace rows not compared");
}

// 3. Served page, when a URL is given.
const url = process.env.QUORUM_TEST_URL;
if (!url) {
  console.log("SKIP: QUORUM_TEST_URL not set; served page not checked");
  process.exit(0);
}
(async () => {
  const res = await fetch(url + "/");
  assert.strictEqual(res.status, 200);
  const html = await res.text();
  for (const id of ["get", "loop", "limits", "team", "main"]) {
    assert.ok(html.includes('id="' + id + '"'), "missing section anchor #" + id);
  }
  const docs = evidence.documents;
  const figures = [docs.count, Object.keys(docs.by_source).length, docs.by_flank.left, docs.by_flank.right];
  for (const n of figures) assert.ok(html.includes(">" + n + "<") || html.includes(">" + n + "</"), "figure missing: " + n);
  assert.ok(html.includes("Dry run · fictional content · real shape"), "fictional trace label missing");
  assert.ok(html.includes(reuters[0].title_80), "typewriter static copy missing the Reuters title");
  assert.ok(!/every call runs through Meterless/i.test(html), "forbidden claim about Meterless");
  console.log("PASS: served landing carries anchors, evidence figures, fictional label and the real titles");
})().catch((e) => {
  console.error("FAIL: " + e.message);
  process.exit(1);
});
