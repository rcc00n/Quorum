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
    async function open() {
      await page.goto(root + "/events/demo-event?date=2026-10-22");
      await page
        .getByRole("heading", { name: "Evidence Explorer", exact: true })
        .waitFor();
    }
    await open();
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
    response.events[0].analysis.trace = [];
    await open();
    await page
      .getByText("No investigation trace supplied.", { exact: false })
      .waitFor();
    fail = true;
    await page.reload();
    await page
      .getByRole("button", { name: "Try again", exact: true })
      .waitFor();
    fail = false;
    response = structuredClone(demo);
    await page.getByRole("button", { name: "Try again", exact: true }).click();
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
