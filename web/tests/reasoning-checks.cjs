// Canonical FICTIONAL sample through real HTTP; no browser API interception.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  os = require("node:os");
module.exports = async function ({ browser, root, env, password, temp }) {
  const file = env.QUORUM_REASONING_PREVIEW_FILE;
  const original = fs.readFileSync(file),
    sample = JSON.parse(original);
  const anonymous = await browser.newContext();
  assert.equal(
    (await anonymous.request.get(root + "/api/preview/reasoning/")).status(),
    401,
  );
  await anonymous.close();
  const context = await browser.newContext(),
    page = await context.newPage({ viewport: { width: 1440, height: 1000 } }),
    errors = [];
  page.on("pageerror", () => errors.push("page error"));
  const session = await (
    await context.request.get(root + "/api/session/")
  ).json();
  assert.equal(
    (
      await context.request.post(root + "/api/login/", {
        headers: { "X-CSRFToken": session.csrfToken, Origin: root },
        data: { username: "DEMO-boundary-reader", password },
      })
    ).status(),
    200,
  );
  const result = await (
    await context.request.get(root + "/api/preview/reasoning/")
  ).json();
  assert.deepEqual(result.reasoning, sample);
  assert.equal(result.preview.published, false);
  assert.equal(result.events.length, 2);
  assert.equal(
    (await (await context.request.get(root + "/api/feed/")).json()).status,
    "pending",
  );
  console.log("CHECK: reasoning topic HTTP/UI");
  await page.goto(root + "/preview/reasoning");
  await page
    .getByRole("heading", { name: "The daily perspective", exact: true })
    .waitFor();
  await page.getByText("DEMO / FICTIONAL DATA", { exact: true }).waitFor();
  assert.equal(await page.locator(".r-story-row").count(), 2);
  for (const group of sample.roundup.groups)
    await page
      .getByRole("heading", { name: group.name, exact: true })
      .waitFor();
  assert.equal(await page.locator(".r-trace>li").count(), 45);
  assert.equal(await page.locator(".r-trace-body").count(), 45);
  assert.ok(
    (await page.locator(".r-repeat").allTextContents()).some((t) =>
      t.includes("Iteration 2"),
    ),
  );
  await page
    .getByLabel("Trace node filter", { exact: true })
    .selectOption("research");
  assert.equal(await page.locator(".r-trace>li").count(), 7);
  await page
    .getByLabel("Trace event filter", { exact: true })
    .selectOption(sample.stories[0].event_id);
  assert.equal(await page.locator(".r-trace>li").count(), 2);
  await page
    .getByLabel("Trace node filter", { exact: true })
    .selectOption("critique");
  assert.equal(await page.locator(".r-trace>li").count(), 2);
  await page.getByLabel("Trace event filter", { exact: true }).selectOption("");
  await page.getByLabel("Trace node filter", { exact: true }).selectOption("");
  const output =
    process.env.QUORUM_SCREENSHOTS ||
    path.join(os.homedir(), ".local/share/quorum/portal-screenshots");
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({
    path: path.join(output, "reasoning-topic-1440.png"),
    fullPage: false,
  });
  for (const story of sample.stories) {
    console.log("CHECK: reasoning story", story.event_id);
    await page.getByRole("link", { name: story.headline, exact: true }).click();
    await page
      .locator(".r-article h1")
      .filter({ hasText: story.headline })
      .waitFor();
    await page.locator(".r-paragraph").last().waitFor();
    assert.equal(
      await page.locator(".r-paragraph").count(),
      story.article.length,
    );
    await page
      .getByText(
        "Impact " + story.rubric.total + " / 9 · open the supplied rubric",
        { exact: true },
      )
      .click();
    assert.ok((await page.locator(".r-impact dd").count()) === 4);
    const first = page.locator(".r-claim-links a").first();
    await first.click();
    assert.ok(await page.locator(".r-claim[open]").count());
    const disputed = story.claims.find((c) => c.verifier !== c.fact_checker);
    if (disputed) {
      const detail = page.locator("#reasoning-claim-" + disputed.id);
      await detail.locator("summary").focus();
      if ((await detail.getAttribute("open")) === null)
        await page.keyboard.press("Enter");
      await detail.getByText(/The two reviewers disagree/).waitFor();
      assert.equal(await detail.locator(".r-chain").count(), 2);
    }
    for (const mode of ["allsides", "mbfc", "adfontes", "average"]) {
      await page
        .getByLabel("Cohort rating context", { exact: true })
        .selectOption(mode);
      await page.getByLabel("Rating mode", { exact: true }).selectOption(mode);
    }
    assert.equal(await page.locator(".r-cohort").count(), 4);
    for (const [i, key] of [
      "major_left",
      "major_right",
      "minor_left",
      "minor_right",
    ].entries()) {
      const cohort = page.locator(".r-cohort").nth(i),
        pair = story.spectrum.coverage[key];
      assert.equal(
        await cohort.locator(".r-cohort-number strong").textContent(),
        String(pair[0]),
      );
      assert.ok(
        (await cohort.locator(".r-cohort-number").textContent()).includes(
          "/ " + pair[1],
        ),
      );
    }
    const firstEvidence = story.claims[0].evidence[0];
    const firstClaim = page.locator("#reasoning-claim-" + story.claims[0].id);
    assert.equal(
      await firstClaim.locator(".r-chain .r-evidence").count(),
      story.claims[0].evidence.length,
    );
    assert.ok(
      (await firstClaim.textContent()).includes(
        firstEvidence.independence_group,
      ),
    );
    assert.ok(
      await page
        .locator(".r-sources a")
        .evaluateAll(
          (links, url) => links.some((link) => link.href === url),
          firstEvidence.url,
        ),
    );
    for (const claim of story.claims)
      assert.ok(
        (
          await page
            .locator("#reasoning-claim-" + claim.id + " summary")
            .textContent()
        ).includes(claim.status),
      );
    assert.ok(
      await page
        .getByText(/Original document IDs, content hashes, quote offsets/)
        .count(),
    );
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(
        await page.locator("body").evaluate((e) => e.scrollWidth > innerWidth),
        false,
      );
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    const animated = page.locator(".r-evidence").first();
    assert.equal(
      await animated.evaluate((e) => getComputedStyle(e).animationName),
      "none",
    );
    await page.emulateMedia({ reducedMotion: "no-preference" });
    if (story === sample.stories[0]) {
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() => {
          document.activeElement?.blur();
          scrollTo({ top: 0, behavior: "instant" });
        });
        await page.waitForFunction(() => scrollY === 0);
        await page.screenshot({
          path: path.join(output, `reasoning-reading-${width}.png`),
          fullPage: false,
          animations: "disabled",
        });
        await page.screenshot({
          path: path.join(output, `reasoning-story-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      for (const [selector, name] of [
        ["#reasoning-claim-" + disputed.id, "evidence"],
        ["#reasoning-perspectives", "cohorts"],
        [".r-loop-overview", "feedback"],
      ]) {
        await page
          .locator(selector)
          .screenshot({
            path: path.join(output, `reasoning-${name}-1440.png`),
            animations: "disabled",
          });
      }
    }
    await page
      .getByRole("link", { name: "Topic edition", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "The daily perspective", exact: true })
      .waitFor();
  }
  console.log("CHECK: reasoning TEST variants");
  // Native context block is absent from the upstream fixture; test it as an explicit TEST variant.
  let variant = structuredClone(sample);
  variant.stories[0].article.splice(1, 0, {
    kind: "context",
    text: "TEST context, not established by the adapter.",
    claim_ids: [variant.stories[0].claims[0].id],
    sources: [variant.stories[0].sources[0]],
  });
  fs.writeFileSync(file, JSON.stringify(variant));
  await page.goto(
    root + "/preview/reasoning?event=" + sample.stories[0].event_id,
  );
  await page
    .getByText(
      "Source-attributed context · not promoted to an established fact by the adapter.",
      { exact: true },
    )
    .waitFor();
  variant.stories[0].article[0].text =
    '<img src=x onerror="window.TEST_XSS=1">';
  fs.writeFileSync(file, JSON.stringify(variant));
  await page.reload();
  await page
    .getByText('<img src=x onerror="window.TEST_XSS=1">', { exact: true })
    .waitFor();
  assert.equal(await page.evaluate(() => window.TEST_XSS), undefined);
  variant = structuredClone(sample);
  variant.status = "partial";
  variant.errors = ["TEST recorded failure"];
  variant.sources_missing = ["TEST missing source"];
  fs.writeFileSync(file, JSON.stringify(variant));
  await page.goto(root + "/preview/reasoning");
  await page.getByText("This preview is incomplete", { exact: true }).waitFor();
  await page.getByText("TEST recorded failure", { exact: true }).waitFor();
  variant = structuredClone(sample);
  variant.status = "empty";
  variant.stories = [];
  variant.trace = [];
  variant.roundup.empty_day = true;
  fs.writeFileSync(file, JSON.stringify(variant));
  await page.reload();
  await page
    .getByRole("heading", {
      name: "No featured stories crossed the bar",
      exact: true,
    })
    .waitFor();
  await page
    .getByText("No execution trace supplied.", { exact: true })
    .waitFor();
  variant = structuredClone(sample);
  variant.stories[0].sources[0].url = "javascript:alert(1)";
  fs.writeFileSync(file, JSON.stringify(variant));
  assert.equal(
    (await context.request.get(root + "/api/preview/reasoning/")).status(),
    422,
  );
  await page.reload();
  await page
    .getByRole("heading", {
      name: "Reasoning preview unavailable",
      exact: true,
    })
    .waitFor();
  fs.writeFileSync(file, original);
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await page
    .getByRole("heading", { name: "The daily perspective", exact: true })
    .waitFor();
  assert.equal(
    (
      await context.request.get(root + "/api/preview/reasoning/?version=999")
    ).status(),
    404,
  );
  assert.deepEqual(errors, []);
  await context.close();
  console.log(
    "PASS: exact FICTIONAL reasoning 1.0 → real local authenticated API → both articles, claim chains/disagreement, rubric, cohorts/four modes, grouped roundup, all 45 trace steps and repeated research/critique; TEST context/XSS/empty/partial/error/retry; three widths, keyboard, reduced motion; publisher unused",
  );
};
