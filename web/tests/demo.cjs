// Explicitly isolated browser fixture test. No live adapter or provider is contacted.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const ts = require(process.env.TYPESCRIPT_MODULE || "typescript");
const fs = require("fs");
const fixture = { exports: {} };
new Function(
  "exports",
  ts.transpileModule(
    fs.readFileSync(
      require("path").join(__dirname, "../fixtures/demo.ts"),
      "utf8",
    ),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } },
  ).outputText,
)(fixture.exports);
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await page.route("**/api/session/", (r) =>
    r.fulfill({
      json: {
        csrfToken: "demo-only",
        user: {
          username: "DEMO reader",
          name: "",
          email: "",
          topics: ["demo-civic"],
          is_staff: false,
        },
      },
    }),
  );
  await page.route("**/api/feed/**", (r) =>
    r.fulfill({ json: fixture.exports.demo }),
  );
  const root = process.env.QUORUM_TEST_URL || "http://127.0.0.1:3017";
  await page.goto(root + "/topics/demo-civic?date=2026-10-22");
  await page
    .getByRole("link", { name: /DEMO · A fictional community meeting/ })
    .click();
  await page.getByRole("heading", { name: "What is established" }).waitFor();
  await page
    .getByText(
      "DEMO · Fictional interface fixture. Not verified news or live findings.",
      { exact: true },
    )
    .waitFor();
  for (const mode of ["allsides", "mbfc", "adfontes", "average"])
    await page.getByLabel("Rating mode").selectOption(mode);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    if (await page.locator("body").evaluate((e) => e.scrollWidth > innerWidth))
      throw Error("Analysis overflows " + width);
  }
  console.log(
    "PASS: explicitly labelled fictional event, evidence sections, date links, four rating modes, mobile analysis",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
