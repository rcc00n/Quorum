// Unchanged external unpublished snapshot through authenticated Django/Next; no interception.
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os"),
  crypto = require("node:crypto"),
  assert = require("node:assert/strict"),
  { execFileSync } = require("node:child_process");
const digest = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

module.exports = async function ({ browser, root, env, password, temp, sourceFile }) {
  const original = fs.readFileSync(sourceFile), sample = JSON.parse(original);
  const sha256 = digest(original);
  if (process.env.QUORUM_REASONING_EXPECTED_SHA256)
    assert.equal(sha256, process.env.QUORUM_REASONING_EXPECTED_SHA256);
  assert.equal(typeof sample.provenance.fictional, "boolean");
  const banner = sample.provenance.fictional ? "DEMO / FICTIONAL DATA" : "UNPUBLISHED / CORPUS EXPERIMENT";
  const expired = Date.now() >= Date.parse(sample.expires_at);
  assert.equal(digest(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_FILE)), sha256);
  const context = await browser.newContext();
  assert.equal((await context.request.get(root + "/api/preview/reasoning/")).status(), 401);
  const session = await (await context.request.get(root + "/api/session/")).json();
  assert.equal((await context.request.post(root + "/api/login/", {
    headers: { "X-CSRFToken": session.csrfToken, Origin: root },
    data: { username: "DEMO-boundary-reader", password },
  })).status(), 200);
  const response = await context.request.get(root + "/api/preview/reasoning/");
  assert.equal(response.status(), 200);
  const result = await response.json();
  const presented = structuredClone(sample);
  if (presented.errors) presented.errors = presented.errors.map((error) => {
    const message = typeof error === "string" ? error : error.message;
    const safe = /^model route returned HTTP [45]\d{2}$/.test(message) ? message : "Recorded upstream failure; internal details withheld.";
    return typeof error === "string" ? safe : {...error, message: safe};
  });
  assert.deepEqual(result.reasoning, presented);
  assert.equal(result.preview.sha256, sha256);
  assert.equal(result.preview.published, false);
  assert.equal(result.status, "demo");
  assert.equal(result.preview.expiry_hint, expired ? "expired" : "within_hint");
  assert.equal((await (await context.request.get(root + "/api/feed/")).json()).status, "pending");
  const apiFile = path.join(temp, "external-reasoning-api.json");
  fs.writeFileSync(apiFile, JSON.stringify(result), { mode: 0o600 });
  execFileSync(process.execPath, [path.join(__dirname, "contract.cjs")], {
    env: { ...process.env, QUORUM_SNAPSHOT_FILE: apiFile }, stdio: "pipe",
  });
  const errors = [], page = await context.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(15000);
  page.on("pageerror", () => errors.push("page error"));
  await page.emulateMedia({ reducedMotion: "reduce" });
  const output = process.env.QUORUM_SCREENSHOTS || path.join(os.homedir(), ".local/share/quorum/portal-screenshots");
  fs.mkdirSync(output, { recursive: true });
  await page.goto(root + "/preview/reasoning");
  await page.getByRole("heading", { name: "The daily perspective", exact: true }).waitFor();
  await page.getByText(banner, { exact: true }).waitFor();
  assert.equal(await page.locator(".r-topic-summary").textContent(), sample.summary);
  if (sample.errors?.length) {
    const diagnostics = page.locator('.r-upstream-errors');
    await diagnostics.locator('summary').click();
    assert.equal(await diagnostics.locator('p').count(), sample.errors.length);
    await diagnostics.locator('summary').click();
  }
  assert.ok((await page.locator(".r-preview-limits").first().textContent()).includes(sample.published_at === null ? "Not published" : `Reported publication: ${sample.published_at} (unverified)`));
  assert.ok((await page.locator(".r-preview-limits").first().textContent()).includes(expired ? "Expired hint" : "Expiry hint"));
  if (sample.provenance.model_calls !== undefined) {
    const provenance = await page.locator(".r-model-provenance").textContent();
    assert.ok(provenance.includes(`${sample.provenance.model_calls} model calls`));
    assert.ok(provenance.includes(sample.provenance.fact_checker_model));
    for (const [model, count] of Object.entries(sample.provenance.answered_by || {}))
      assert.ok(provenance.includes(`${model} ×${count}`));
  }
  if (!sample.provenance.fictional && sample.provenance.model === "stand-ins")
    assert.ok((await page.locator(".r-demo").textContent()).includes("no AI verification"));
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    assert.equal(await page.locator("body").evaluate((el) => el.scrollWidth > innerWidth), false);
    assert.ok(await page.getByText(banner, { exact: true }).isVisible());
    await page.screenshot({ path: path.join(output, `snapshot-topic-${width}.png`), animations: "disabled" });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  assert.equal(await page.locator(".r-story-row").count(), sample.stories.length);
  const roundup = sample.roundup.groups.flatMap((g) => g.items);
  assert.equal(await page.locator(".r-roundup-row").count(), roundup.length);
  for (const [i, item] of roundup.entries()) {
    const row = page.locator(".r-roundup-row").nth(i);
    assert.equal(await row.getByRole("link", {name:item.line, exact:true}).textContent(), item.line);
    assert.equal(new URL(await row.getByRole("link", {name:item.line, exact:true}).getAttribute("href"), root).searchParams.get("event"), item.event_id);
    assert.equal((await row.locator(".help").first().textContent()).trim(), "Producer status: " + item.status + (item.needs_review ? " · needs review" : ""));
    assert.deepEqual(await row.locator(".r-sources a").evaluateAll((links) => links.map((a) => a.href)), [...new Set(item.sources.map((s) => new URL(s.url).href))]);
  }
  const traceRows = await page.locator(".r-trace>li").evaluateAll((rows) => rows.map((row) => ({
    decision: row.querySelector(".r-step-decision").textContent,
    reason: row.querySelector(".r-trace-body>p:not(.eyebrow)").textContent,
    metadata: row.querySelector(".r-trace-body>small").textContent,
    iteration: row.querySelector(".r-iteration").textContent,
  })));
  assert.equal(traceRows.length, sample.trace.length);
  for (const [i, step] of sample.trace.entries()) {
    assert.equal(traceRows[i].decision, step.decision);
    assert.equal(traceRows[i].reason, step.reason || "No reason supplied.");
    assert.equal(traceRows[i].metadata, `Node: ${step.node} · ${step.duration_ms} ms · Model: ${step.model || "Not supplied"}`);
    assert.ok(traceRows[i].iteration.includes(`Iteration ${step.iteration}`));
  }
  await page.screenshot({ path: path.join(output, "snapshot-topic-1440.png"), animations: "disabled" });
  // Desktop/mobile coverage must run even when the real edition has zero stories.
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.locator("body").evaluate((el) => el.scrollWidth > innerWidth), false);
    await page.locator('#reasoning-roundup').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `snapshot-roundup-${width}.png`), animations: "disabled" });
  }
  if (env.QUORUM_REASONING_PREVIEW_SIDECAR) {
    const binding = JSON.parse(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_SIDECAR));
    assert.equal(result.preview.corpus_binding.provisional, binding.provisional);
    assert.equal(result.preview.corpus_binding.sidecar_sha256, digest(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_SIDECAR)));
    if (binding.snapshot.sha256_file_bytes) {
      await page.getByText(/CLOSED EDITION \(producer-declared\)/).waitFor();
      await page.getByRole('alert').filter({hasText:'IMPACT REVIEW PENDING:'}).waitFor();
      assert.equal(result.preview.corpus_binding.closed_edition, true);
      assert.ok(result.preview.warnings.some(w => w.includes('has not passed independent impact review')));
    } else {
      await page.getByText(/PROVISIONAL CORPUS/).waitFor();
    }
  }
  assert.equal(await page.locator(".r-roundup-row .r-check-notice").count(), roundup.length);
  for (const story of sample.stories) {
    await page.goto(root + "/preview/reasoning?event=" + story.event_id);
    await page.locator(".r-article h1").waitFor();
    assert.equal(await page.locator(".r-article h1").textContent(), story.headline);
    assert.equal(await page.locator(".r-standfirst").textContent(), story.standfirst);
    assert.equal(await page.locator(".r-paragraph").count(), story.article.length);
    for (const [i, block] of story.article.entries()) {
      const row = page.locator(".r-paragraph").nth(i);
      assert.ok((await row.getAttribute("class")).includes("r-kind-" + block.kind));
      assert.ok((await row.locator(":scope > p").allTextContents()).includes(block.text));
      assert.deepEqual(await row.locator(".r-claim-links a").evaluateAll((links) => links.map((a) => a.getAttribute("href").replace("#reasoning-claim-", ""))), block.claim_ids);
      assert.deepEqual(await row.locator(".r-sources a").evaluateAll((links) => links.map((a) => a.href)), [...new Set(block.sources.map((s) => new URL(s.url).href))]);
    }
    assert.equal(await page.locator(".r-claim").count(), story.claims.length);
    for (const claim of story.claims) {
      const row = page.locator("#reasoning-claim-" + claim.id);
      await row.locator(":scope > summary").click();
      assert.equal(await row.locator("summary strong").textContent(), claim.text);
      if (claim.kind === "context")
        assert.ok((await row.locator(".r-claim-status").textContent()).includes("Source-attributed context"));
      assert.equal(await row.locator(".r-final strong").textContent(), claim.status);
      assert.equal(await row.locator(".r-final p").textContent(), claim.reason || "No final rationale supplied.");
      assert.ok((await row.locator(".r-agreement").textContent()).includes(claim.verifier === claim.fact_checker ? "Reviewers agree" : "Reviewers disagree"));
      if (claim.resolved_by) {
        const review = row.locator('aside.r-disagreement');
        assert.equal(await review.locator('strong').textContent(), `Resolution: ${claim.resolved_by}`);
        assert.ok((await review.textContent()).includes(claim.reviewer_status ?? 'No verdict supplied'));
        if (claim.reviewer_reason) assert.ok((await review.locator('p').allTextContents()).includes(claim.reviewer_reason));
        if (claim.reviewer_quote) assert.equal(await review.locator('blockquote').textContent(), claim.reviewer_quote);
        assert.equal(await review.locator('.r-review-proposal-rejected').count(), claim.reviewer_status && claim.resolved_by !== 'reviewer' ? 1 : 0);
      }
      for (const [i, verdict, evidence] of [
        [0, claim.verifier, claim.evidence.filter((e) => ["researcher", "verifier"].includes(e.found_by))],
        [1, claim.fact_checker, claim.evidence.filter((e) => e.found_by === "fact_checker")],
      ]) {
        const chain = row.locator(".r-chain").nth(i);
        assert.equal(await chain.locator("h4").textContent(), verdict);
        assert.equal(await chain.locator(".r-evidence").count(), evidence.length);
        for (const [j, e] of evidence.entries()) {
          const ev = chain.locator(".r-evidence").nth(j);
          assert.equal(await ev.locator("blockquote").textContent(), e.quote);
          assert.ok((await ev.getAttribute("class")).includes("r-stance-" + e.stance));
          assert.ok((await ev.locator("small").textContent()).includes(e.independence_group));
          assert.equal(await ev.locator("a").getAttribute("href"), new URL(e.url).href);
          assert.equal(await ev.locator("a").textContent(), e.title + " ↗");
        }
      }
    }
    for (const link of await page.locator(".r-claim-links a").all()) {
      await link.click();
      assert.notEqual(await page.locator(await link.getAttribute("href")).getAttribute("open"), null);
    }
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.locator("body").evaluate((el) => el.scrollWidth > innerWidth), false);
      await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
      await page.screenshot({ path: path.join(output, `snapshot-article-${width}.png`), animations: "disabled" });
      const label = page.getByText(banner, { exact: true });
      assert.ok(await label.isVisible());
    }
  }
  for (const item of roundup) {
    await page.goto(root + "/preview/reasoning");
    await page.locator(".r-roundup-row > a").filter({ hasText: item.line }).click();
    await page.getByRole("heading", { name: item.line, exact: true }).waitFor();
    await page.getByText(/Only a roundup entry was supplied/).waitFor();
    assert.equal(await page.locator(".r-article, .r-claim").count(), 0);
    await page.getByLabel("Trace event filter", { exact: true }).selectOption(item.event_id);
    await page.waitForFunction(
      (n) => document.querySelectorAll(".r-trace>li").length === n,
      sample.trace.filter((step) => step.event_id === item.event_id).length,
    );
  }
  if (result.catalog_revision) {
    await page.goto(root + '/preview/reasoning');
    for (const mode of ['allsides', 'mbfc', 'adfontes', 'average']) {
      await page.getByLabel('Rating mode', {exact:true}).selectOption(mode);
      assert.equal(await page.locator('.source-row').count(), result.sources.length);
    }
    await page.locator('.rating-provenance').first().locator('summary').click();
    for (const width of [1440, 390]) {
      await page.setViewportSize({width, height:1000});
      await page.locator('.spectrum').scrollIntoViewIfNeeded();
      assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth), false);
      await page.screenshot({path:path.join(output, `snapshot-ratings-${width}.png`), animations:'disabled'});
    }
  }
  assert.deepEqual(errors, []);
  assert.equal(digest(fs.readFileSync(sourceFile)), sha256);
  assert.equal(digest(fs.readFileSync(env.QUORUM_REASONING_PREVIEW_FILE)), sha256);
  await context.close();
  console.log(`PASS: unchanged external unpublished snapshot ${sha256}; authenticated Django/Next/TypeScript, exact prose/reviews/evidence/trace/roundup and three widths; no publication`);
};
