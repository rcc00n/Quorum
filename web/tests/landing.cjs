// Landing page checks. Always: the fixtures the page renders are copies of their sources
// (web/fixtures/landing/README.md) and the Reuters sample forms one supersede chain. With QUORUM_TEST_URL set:
// the served page carries every section anchor, the hero figures, the fictional label, the real titles in chain
// order, every source id of the window, the loop limits, and the blurred field's text nodes are exactly the
// "id count" pairs of the evidence file. No model call, no database, no credentials.
//   node web/tests/landing.cjs
//   QUORUM_TEST_URL=http://127.0.0.1:3017 node web/tests/landing.cjs
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const root = path.resolve(__dirname, "..", "..");
const fixtures = path.join(root, "web", "fixtures", "landing");
const readJson = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const exists = (p) => fs.existsSync(p);

// 1. Evidence copy equals its source; the Reuters rows form one supersede chain.
const evidenceSource = path.join(root, "collectors", "zetaris", "evidence", "russia-ukraine-war_2026-10-24.json");
const evidenceCopy = path.join(fixtures, "zetaris-evidence-russia-ukraine-war-2026-10-24.json");
if (exists(evidenceSource)) {
  assert.ok(fs.readFileSync(evidenceSource).equals(fs.readFileSync(evidenceCopy)), "evidence copy differs from collectors/zetaris/evidence");
  console.log("PASS: evidence fixture is a byte-for-byte copy of collectors/zetaris/evidence");
} else {
  console.log("SKIP: collectors/ not in this checkout; evidence copy not compared");
}
const evidence = readJson(evidenceCopy);
assert.strictEqual(evidence.sanitization, "no lead, no article/official text, no credentials; titles truncated to 80 chars");
const reuters = evidence.documents.sample.filter((s) => s.source_id === "reuters");
assert.strictEqual(reuters.length, 3, "the typewriter expects the three Reuters titles of the sample");
function chain(rows) {
  const byId = new Map(rows.map((r) => [r.id, r]));
  let head = rows.find((r) => !r.supersedes_id || !byId.has(r.supersedes_id));
  const out = [];
  while (head && !out.includes(head)) {
    out.push(head);
    const cur = head;
    head = rows.find((r) => r.supersedes_id === cur.id);
  }
  return out;
}
const ordered = chain(reuters);
assert.strictEqual(ordered.length, 3, "the three Reuters rows must form one supersede chain");
for (let i = 1; i < ordered.length; i++) assert.strictEqual(ordered[i].supersedes_id, ordered[i - 1].id, "chain order by supersedes_id");
console.log("PASS: Reuters chain " + ordered.map((r) => r.id).join(" → ") + " ordered by supersedes_id");

// 2. Trace sample rows exist verbatim in the committed dry-run sample, and are labelled fictional.
const traceCopy = readJson(path.join(fixtures, "trace.sample.json"));
assert.strictEqual(traceCopy.fictional, true, "trace.sample.json must be labelled fictional");
const sampleSource = path.join(root, "docs", "examples", "snapshot.sample.json");
if (exists(sampleSource)) {
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

// 3. Source names and access levels are the registry's own, nothing added or renamed.
const sourcesCopy = readJson(path.join(fixtures, "sources.json"));
const sourcesCsv = path.join(root, "collectors", "sources.csv");
if (exists(sourcesCsv)) {
  const lines = fs.readFileSync(sourcesCsv, "utf8").split(/\r?\n/).filter(Boolean);
  const header = lines[0].split(",");
  const col = (name) => header.indexOf(name);
  const fromCsv = lines.slice(1).map((l) => {
    const cells = [];
    let cur = "", q = false;
    for (const ch of l) {
      if (ch === '"') q = !q;
      else if (ch === "," && !q) { cells.push(cur); cur = ""; }
      else cur += ch;
    }
    cells.push(cur);
    const lvl = cells[col("access_level_default")];
    return {
      id: cells[col("id")], name: cells[col("name")], domain: cells[col("domain")], kind: cells[col("kind")],
      flank: cells[col("flank")] || null, tier: cells[col("tier")] || null, access_level_default: lvl ? Number(lvl) : null,
    };
  });
  assert.deepStrictEqual(sourcesCopy.sources, fromCsv, "web/fixtures/landing/sources.json differs from collectors/sources.csv");
  assert.strictEqual(sourcesCopy.count, fromCsv.length);
  for (const id of Object.keys(evidence.documents.by_source)) assert.ok(fromCsv.some((s) => s.id === id), "evidence source not in registry: " + id);
  console.log("PASS: " + sourcesCopy.count + " source rows equal the registry; every evidence source is registered");
} else {
  console.log("SKIP: collectors/sources.csv not in this checkout; source names not compared");
}

// 4. Loop limits and word lists equal reasoning/config/reasoning.toml; graph nodes exist in ARCHITECTURE § 5.
const rulesCopy = readJson(path.join(fixtures, "rules.json"));
const toml = path.join(root, "reasoning", "config", "reasoning.toml");
if (exists(toml)) {
  const text = fs.readFileSync(toml, "utf8");
  const loops = text.slice(text.indexOf("[loops]"));
  for (const key of ["research_rounds_max", "drafts_max", "review_disputed_max"]) {
    const m = loops.match(new RegExp("^" + key + "\\s*=\\s*(\\d+)", "m"));
    assert.ok(m, "missing [loops] key " + key);
    assert.strictEqual(rulesCopy.loops[key], Number(m[1]), "loop limit differs: " + key);
  }
  const list = (name) => [...text.match(new RegExp(name + "\\s*=\\s*\\[([\\s\\S]*?)\\]"))[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepStrictEqual(rulesCopy.forbidden_words, list("forbidden_words"), "forbidden_words differ from the TOML");
  assert.deepStrictEqual(rulesCopy.attribution_verbs, list("attribution_verbs"), "attribution_verbs differ from the TOML");
  console.log("PASS: loop limits, " + rulesCopy.forbidden_words.length + " forbidden words and " + rulesCopy.attribution_verbs.length + " attribution verbs equal reasoning.toml");
} else {
  console.log("SKIP: reasoning/config/reasoning.toml not in this checkout");
}
const graphCopy = readJson(path.join(fixtures, "graph.json"));
const arch = path.join(root, "docs", "ARCHITECTURE.md");
if (exists(arch)) {
  const text = fs.readFileSync(arch, "utf8");
  for (const n of graphCopy.nodes) assert.ok(text.includes("`" + n + "`"), "graph node not in ARCHITECTURE.md: " + n);
  for (const l of graphCopy.loops) {
    assert.ok(graphCopy.nodes.includes(l.from) && graphCopy.nodes.includes(l.to), "loop names a node that is not in the graph");
    assert.ok(l.limit_key in rulesCopy.loops, "loop limit key not in rules.json: " + l.limit_key);
  }
  console.log("PASS: " + graphCopy.nodes.length + " graph nodes and " + graphCopy.loops.length + " loops exist in ARCHITECTURE.md § 5");
} else {
  console.log("SKIP: docs/ARCHITECTURE.md not in this checkout");
}

// 5. Served page, when a URL is given.
const url = process.env.QUORUM_TEST_URL;
if (!url) {
  console.log("SKIP: QUORUM_TEST_URL not set; served page not checked");
  process.exit(0);
}
(async () => {
  const res = await fetch(url + "/");
  assert.strictEqual(res.status, 200);
  const html = await res.text();
  for (const id of ["get", "loop", "limits", "team", "main", "sources", "trace"]) {
    assert.ok(html.includes('id="' + id + '"'), "missing section anchor #" + id);
  }
  const docs = evidence.documents;
  const figures = [docs.count, Object.keys(docs.by_source).length];
  for (const n of figures) assert.ok(html.includes(">" + n + "<"), "figure missing: " + n);
  assert.ok(html.includes(docs.by_flank.left + " · " + docs.by_flank.right + " · "), "flank figures missing");
  assert.ok(html.includes("Dry run · fictional content · real shape"), "fictional label missing");
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/'/g, "&#x27;").replace(/"/g, "&quot;");
  let last = -1;
  for (const r of ordered) {
    const at = html.indexOf(esc(r.title_80));
    assert.ok(at > last, "Reuters titles must appear in chain order: " + r.id);
    last = at;
  }
  for (const id of Object.keys(docs.by_source)) assert.ok(html.includes(">" + id + " · "), "source id missing from the tally: " + id);
  for (const [key, n] of Object.entries(rulesCopy.loops)) {
    if (graphCopy.loops.some((l) => l.limit_key === key)) assert.ok(html.includes("loops." + key + " = " + n), "loop limit missing: " + key);
  }
  const svgs = [...html.matchAll(/<svg class="lp-field"[\s\S]*?<\/svg>/g)];
  assert.ok(svgs.length >= 1, "blurred field not found");
  const allowed = new Set(Object.entries(docs.by_source).map(([id, n]) => id + " " + n));
  for (const svg of svgs) {
    const nodes = [...svg[0].matchAll(/<text[^>]*>([^<]*)<\/text>/g)].map((m) => m[1].replace(/<!--.*?-->/g, ""));
    assert.strictEqual(nodes.length, allowed.size, "field must carry exactly the by_source pairs");
    for (const t of nodes) assert.ok(allowed.has(t), "field text node is not an evidence pair: " + t);
  }
  assert.ok(!/every (model )?(call|request) (runs|goes|is routed) through Meterless|all (calls|requests) (run|go) through Meterless/i.test(html), "forbidden claim about Meterless");
  assert.ok(!/built (in|with) Cursor|Cursor/i.test(html), "forbidden claim about Cursor");
  assert.ok(!/Nunito/.test(html), "the rounded face must not be referenced on the landing");
  console.log("PASS: served landing carries anchors, figures, fictional label, chain order, tally ids, loop limits and an honest field");
})().catch((e) => {
  console.error("FAIL: " + e.message);
  process.exit(1);
});
