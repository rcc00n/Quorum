// Deterministic browser-only DEMO interception. This never proves live integration.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs");
const assert = require("node:assert/strict");
(async () => {
  const demo = JSON.parse(
    fs.readFileSync(process.env.QUORUM_ANALYSIS_FIXTURE, "utf8"),
  );
  assert.equal(demo.status, "demo");
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    let response = structuredClone(demo),
      fail = false;
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.name));
    await page.route("**/api/session/", (r) =>
      r.fulfill({
        json: {
          csrfToken: "demo-only",
          user: {
            username: "DEMO reader",
            name: "DEMO reader",
            email: "",
            topics: ["demo-topic"],
            is_staff: false,
          },
        },
      }),
    );
    const answer = (r) =>
      fail
        ? r.fulfill({
            status: 503,
            json: { error: "Simulated service interruption" },
          })
        : r.fulfill({ json: response });
    await page.route("**/api/feed/**", answer);
    await page.route("**/api/events/**", answer);
    const root = process.env.QUORUM_TEST_URL || "http://127.0.0.1:3017";
    const output =
      process.env.QUORUM_SCREENSHOTS ||
      require("os").homedir() + "/.local/share/quorum/portal-screenshots";
    fs.mkdirSync(output, { recursive: true });
    let readerChecked=false;
    async function open() {
      await page.goto(root + "/events/demo-event?date=2026-10-22");
      if(!readerChecked){await require("./reader-checks.cjs")({page});readerChecked=true;}
      else await page.getByRole("tab",{name:"All sections",exact:true}).click();
      await page
        .getByRole("heading", { name: "Evidence Explorer", exact: true })
        .waitFor();
    }
    const claims = response.events[0].analysis.claims;
    // Explicitly fictional source rows exercise the instrument; no production ratings are assigned here.
    const chartSources = [-.5, 0, .5].map((score, i) => ({
      id: `DEMO-chart-${i}`, name: `DEMO chart source ${i}`, domain: 'example.com',
      allsides: score, mbfc: score, adfontes: i === 1 ? null : score,
      audience: 1000 * 10 ** i, audience_source_url: `https://example.com/demo-audience-${i}`,
    }));
    response.events[0].sources.push(...chartSources);

    response.events[0].article = {
      paragraphs: claims
        .filter((c) => c.status !== "disputed")
        .map((c) => ({
          kind:
            c.status === "established"
              ? "fact"
              : c.status === "attributed"
                ? "statement"
                : "not_confirmed",
          text: c.text,
          claim_ids: [c.id],
        })),
    };
    await open();
    await page
      .getByRole("article", { name: "Source-backed article" })
      .waitFor();
    assert.ok(
      await page
        .getByText("Across the spectrum · Evidence and investigation", {
          exact: true,
        })
        .count(),
    );
    await page
      .getByText(
        "DEMO · Fictional interface fixture. Not verified news or live findings.",
        { exact: true },
      )
      .waitFor();
    await page
      .getByRole("heading", { name: "Perspective Comparison", exact: true })
      .waitFor();
    await page
      .getByRole("heading", { name: "Investigation Timeline", exact: true })
      .waitFor();
    const summaries = page.locator(".claim-detail>summary");
    await summaries.nth(2).focus();
    await page.keyboard.press("Enter");
    assert.equal(
      await page.locator(".claim-detail").nth(2).getAttribute("open"),
      "",
    );
    await page
      .getByText(
        "The supplied reviewers disagree. This claim remains unresolved.",
        { exact: true },
      )
      .waitFor();
    assert.ok(
      await page.getByText("Headline / lead only", { exact: false }).count(),
    );
    assert.ok(
      await page
        .locator('.citation a[href="https://example.com/demo-notice"]')
        .count(),
    );
    assert.ok(
      await page
        .getByText("The eligible source set was not supplied.", {
          exact: false,
        })
        .count(),
    );
    for (const mode of ["allsides", "mbfc", "adfontes", "average"]) {
      await page.getByLabel("Rating mode", { exact: true }).selectOption(mode);
      await page
        .getByLabel("Cohort rating mode", { exact: true })
        .selectOption(mode);
    }
    await require('./spectrum-checks.cjs')({page, sources:response.events[0].sources});
    chartSources[0].audience = 0;
    await open();
    await page.locator('.sp-source-button').filter({hasText:chartSources[0].name}).click();
    assert.equal(await page.locator('.sp-inspector .sp-reading strong').last().textContent(), '0');
    assert.equal(await page.locator(`.sp-point[data-source-id="${chartSources[0].id}"]`).count(), 0);
    chartSources[0].audience = 1000;
    await open();

    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.locator("#evidence-explorer").scrollIntoViewIfNeeded();
      assert.equal(
        await page.locator("body").evaluate((e) => e.scrollWidth > innerWidth),
        false,
        "Overflow at " + width,
      );
      if (width !== 768)
        await page.screenshot({
          path: output + "/analysis-" + width + ".png",
          fullPage: true,
        });
    }
    const revision = page.getByRole("link", {
      name: "Permalink to revision demo-r1",
    });
    assert.ok(
      (await revision.getAttribute("href")).includes("revision=demo-r1"),
    );
    response.publication.status = "stale";
    response.publication.fallback = true;
    await open();
    await page
      .getByText("This edition is out of date", { exact: true })
      .waitFor();
    // A provisional corpus (the login-only reader's label) is named with its capture time.
    response.publication.status = "available";
    response.publication.fallback = false;
    response.publication.provisional = true;
    response.publication.corpus_as_of_utc = "2026-10-22T09:30:00Z";
    await open();
    await page
      .getByText("Provisional corpus as of", { exact: false })
      .waitFor();
    response.publication.provisional = false;
    // A story the producer flagged needs_review carries the label on the claims-only head.
    response.events[0].reasoning = { needs_review: true };
    await open();
    await page
      .getByText("Requires editorial review", { exact: true })
      .first()
      .waitFor();
    delete response.events[0].reasoning;
    response.events[0].analysis.trace = [];
    await open();
    await page
      .getByText("No investigation trace supplied.", { exact: false })
      .waitFor();
    response.events = [];
    response.errors = [];
    response.editions = [
      {
        topic_id: "demo-topic",
        date: "2026-10-22",
        completion: "complete",
        quiet_day: true,
        summary: "DEMO — completed fictional edition.",
        roundup: [
          {
            name: "DEMO notes",
            items: [
              {
                event_id: null,
                text: "DEMO — fictional below-bar item.",
                status: "unknown",
                sources: [],
              },
            ],
          },
        ],
      },
    ];
    response.publication.status = "available";
    response.publication.fallback = false;
    await page.goto(root + "/topics/demo-topic?date=2026-10-22");
    await page
      .getByRole("heading", {
        name: "A quiet day for major stories",
        exact: true,
      })
      .waitFor();
    await page
      .getByRole("heading", { name: "Also today", exact: true })
      .waitFor();
    for (const [status, title] of [
      ["pending", "No edition for 22 October 2026 is installed on this portal."],
      ["error", "This edition is unavailable"],
      ["partial", "This edition is incomplete"],
      ["stale", "This stored edition is out of date"],
    ]) {
      response.publication.status = status;
      await page.reload();
      await page.getByRole("heading", { name: title, exact: true }).waitFor();
      assert.equal(
        await page
          .getByRole("heading", {
            name: "A quiet day for major stories",
            exact: true,
          })
          .count(),
        0,
      );
    }
    response = structuredClone(demo);
    await open();
    fail = true;
    await page.reload();
    await page
      .getByRole("button", { name: "Try again", exact: true })
      .waitFor();
    fail = false;
    response = structuredClone(demo);
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await page.getByRole("tab",{name:"All sections",exact:true}).click();
    await page
      .getByRole("heading", { name: "Evidence Explorer", exact: true })
      .waitFor();
    assert.deepEqual(errors, []);
    console.log(
      "PASS: DEMO evidence, keyboard disclosures, sources/access/nulls, verifier disagreement, comparison modes, timeline/missing trace, stale/fallback, revision link, retry recovery; desktop/tablet/mobile no overflow",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
