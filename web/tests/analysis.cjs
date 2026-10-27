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
    // A rated registry row that no source of the story uses: the story Map must not draw it (story source map amendment,
    // 2026-10-27, Anastasia/Claude Code); spectrum-checks counts the drawn points and the ledger rows.
    (response.sources ||= []).push({ id: 'DEMO-unused', name: 'DEMO unused registry source', domain: 'example.com', kind: 'outlet',
      allsides: .25, mbfc: .25, adfontes: .25, audience: 5000, audience_source_url: 'https://example.com/demo-audience-unused' });

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
    // The Map draws the sources used for this story (story source map amendment, 2026-10-27; lib/story-sources.ts).
    const {storySources}=require('../lib/story-sources.ts');
    await require('./spectrum-checks.cjs')({page, sources:storySources(response.events[0],(response.sources||[]).length?response.sources:response.events[0].sources), scope:'story'});
    const suppliedArticle=response.events[0].article,suppliedImportance=response.events[0].importance;
    // WEB-MEDIA-01 regression: an unrenderable DEMO prose block keeps the claims-only view,
    // while independently reviewed media still exposes its caption/source/licence. No real photo fetched.
    const testPhoto={url:'https://upload.wikimedia.org/TEST-reviewed.svg',source_url:'https://commons.wikimedia.org/wiki/File:TEST-reviewed',
      license_url:'https://creativecommons.org/publicdomain/zero/1.0/',license:'CC0-1.0',credit:'TEST photographer',caption:'TEST reviewed context image.',rights_confirmed:true};
    await page.route(testPhoto.url,r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="gray"/></svg>'}));
    response.events[0].article={...suppliedArticle,paragraphs:[{kind:'fact',text:'DEMO invalid prose must remain hidden.',claim_ids:['TEST-absent-claim']}],photo:testPhoto};
    await open();await page.getByRole('tab',{name:'Reading',exact:true}).click();
    assert.equal(await page.locator('.story').count(),0);assert.equal(await page.locator('.reader-brief').count(),1);
    assert.equal(await page.getByText('DEMO invalid prose must remain hidden.',{exact:true}).count(),0);
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:1000});const image=page.locator('.story-photo img');await image.scrollIntoViewIfNeeded();
      await page.waitForFunction(e=>e.complete&&e.naturalWidth>0,await image.elementHandle());
      assert.equal(await image.getAttribute('alt'),testPhoto.caption);
      assert.equal(await page.locator('.story-credit').getAttribute('href'),testPhoto.source_url);
      assert.equal(await page.locator('.story-caption a').getAttribute('href'),testPhoto.license_url);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    }
    await page.unroute(testPhoto.url);await page.setViewportSize({width:1440,height:1000});
    response.events[0].article=suppliedArticle;
    response.events[0].importance={label:"DEMO Impact 6 / 9",explanation:"DEMO original selection notes, unchanged."};
    delete response.events[0].article;
    response.events[0].reasoning={rubric:{legal_force:2,reach:2,irreversibility:1,confirmation:1,total:6,rationale:{legal_force:'DEMO supplied legal rationale'}}};
    await open();await page.getByRole('tab',{name:'Reading',exact:true}).click();
    await require('./impact-checks.cjs')({page,event:response.events[0]});
    response.events[0].article=suppliedArticle;
    await open();await page.getByRole('tab',{name:'Reading',exact:true}).click();
    await require('./impact-checks.cjs')({page,event:response.events[0]});
    delete response.events[0].article;response.events[0].reasoning.rubric.total=99;
    await open();await page.getByRole('tab',{name:'Reading',exact:true}).click();
    assert.equal(await page.locator('.impact-assessment').count(),response.events[0].importance?1:0);
    assert.equal(await page.locator('.impact-total-value').count(),0);
    delete response.events[0].reasoning;response.events[0].article=suppliedArticle;response.events[0].importance=suppliedImportance;
    chartSources[0].audience = 0;
    await open();
    // WEB-SPECTRUM-POLISH-02: the source ledger is a closed disclosure; open it before reaching a row.
    const ledger = page.locator('.spectrum .sp-ledger').first();
    if (await ledger.count() && (await ledger.getAttribute('open')) === null) await ledger.locator('> summary').click();
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
    // "Also today" lives on Home only since the cabinet pages pass (Anastasia, 2026-10-27, web/DESIGN.md › Cabinet):
    // absent on the topic page, present on the board for the followed topic.
    assert.equal(
      await page
        .getByRole("heading", { name: "Also today", exact: true })
        .count(),
      0,
    );
    await page.goto(root + "/dashboard?date=2026-10-22");
    // On Home the block is named for its topic, the board's card jumps to it, and the quiet-day panel is not repeated
    // under the board (2026-10-27, Anastasia/Claude Code; web/DESIGN.md › Cabinet).
    const alsoToday = page.getByRole("heading", { name: /^Also today · / });
    await alsoToday.first().waitFor();
    assert.equal(await alsoToday.count(), 1);
    assert.equal(
      await page
        .getByRole("heading", { name: "A quiet day for major stories", exact: true })
        .count(),
      0,
    );
    await page.locator('a.tb-card-link[href="#also-today-demo-topic"]').click();
    await page.waitForFunction(() => location.hash === "#also-today-demo-topic");
    assert.equal(new URL(page.url()).pathname, "/dashboard");
    await page.goto(root + "/topics/demo-topic?date=2026-10-22");
    await page
      .getByRole("heading", {
        name: "A quiet day for major stories",
        exact: true,
      })
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
    // The DEMO notice closes for the visit and shows again in a fresh context (2026-10-27, Anastasia/Claude Code;
    // components/dismissible-notice.tsx): its wording stays, a click on its named close button hides it, a reload in the
    // same tab keeps it hidden (sessionStorage), and a new browser context sees it again.
    // A click on text deep in the page focuses nothing, so Tab goes on from there, not back to a notice's close button
    // or to the main column (2026-10-27: #main is focusable only for the moment a notice closes).
    {
      const text = page.locator("#evidence-explorer .analysis-block-heading p:not(.eyebrow)").first();
      await text.scrollIntoViewIfNeeded();
      await text.click();
      await page.keyboard.press("Tab");
      const where = await page.evaluate(() => {
        const a = document.activeElement, t = document.querySelector("#evidence-explorer .analysis-block-heading p:not(.eyebrow)");
        return { close: !!(a && a.classList && a.classList.contains("notice-close")), main: a === document.getElementById("main"), body: a === document.body,
          after: !!(a && t && (t.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)), mainTabindex: document.getElementById("main").hasAttribute("tabindex") };
      });
      assert.deepEqual(where, { close: false, main: false, body: false, after: true, mainTabindex: false }, "Tab continues from the clicked text");
    }
    const demoNote = (p) => p.getByText("DEMO · Fictional interface fixture. Not verified news or live findings.", { exact: true });
    await demoNote(page).waitFor();
    await page.getByRole("button", { name: "Close DEMO notice", exact: true }).click();
    assert.equal(await demoNote(page).count(), 0, "the DEMO notice hides when closed");
    await page.reload();
    await page.locator(".investigation-reader").waitFor();
    assert.equal(await demoNote(page).count(), 0, "it stays hidden for the visit");
    {
      const fresh = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const page2 = await fresh.newPage();
      await page2.route("**/api/session/", (r) => r.fulfill({ json: { csrfToken: "demo-only", user: { username: "DEMO reader", name: "DEMO reader", email: "", topics: ["demo-topic"], is_staff: false } } }));
      await page2.route("**/api/feed/**", (r) => r.fulfill({ json: response }));
      await page2.route("**/api/events/**", (r) => r.fulfill({ json: response }));
      await page2.goto(root + "/events/demo-event?date=2026-10-22");
      // The reader renders with the data, in the same render as the DEMO notice, after the storage read has run.
      await page2.locator(".investigation-reader").waitFor();
      assert.equal(await demoNote(page2).count(), 1, "a fresh context shows the DEMO notice again");
      await fresh.close();
    }
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
