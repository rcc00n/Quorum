const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("fs");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const issues = [];
  page.on("pageerror", (e) => issues.push(e.message));
  const root = process.env.QUORUM_TEST_URL || "http://127.0.0.1:3017";
  const shot =
    process.env.QUORUM_SCREENSHOTS ||
    require("os").homedir() + "/.local/share/quorum/portal-screenshots";
  fs.mkdirSync(shot, { recursive: true });
  async function go(route) {
    await page.goto(root + route);
    await page.waitForLoadState("networkidle");
    if (await page.locator("body").evaluate((e) => e.scrollWidth > innerWidth))
      throw Error("Overflow " + route);
  }
  await go("/");
  await page.screenshot({
    path: shot + "/landing-desktop.png",
    fullPage: true,
  });
  const username = "quorum-smoke-" + Date.now();
  const password =
    require("node:crypto").randomBytes(24).toString("base64url") + "A1!";
  if (process.env.QUORUM_SMOKE_ACCOUNT_FILE)
    fs.writeFileSync(process.env.QUORUM_SMOKE_ACCOUNT_FILE, username, {
      mode: 0o600,
    });
  await go("/register");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.waitForURL("**/onboarding");
  const choices = page.locator(".topic-option input");
  const hasTopics = (await choices.count()) > 0;
  if (hasTopics) await choices.first().check();
  await page.getByRole("button", { name: "Continue to your brief" }).click();
  await page.waitForURL("**/dashboard");
  await page.getByText("No published events are available").waitFor();
  // The AI headline notice opens Home too, first in the main column (2026-10-27, Anastasia/Claude Code).
  await page.getByRole("note").filter({ hasText: "AI-written headlines." }).waitFor();
  assert.equal(await page.locator("#main > :first-child").evaluate((e) => e.classList.contains("ai-notice")), true);
  // It closes for the visit and shows again in a fresh browser context (2026-10-27, Anastasia/Claude Code;
  // components/dismissible-notice.tsx): the named close button hides it, a reload in the same tab keeps it hidden
  // (sessionStorage), and a new context, given the signed-in cookies but no sessionStorage, sees it again.
  const aiNote = (p) => p.getByRole("note").filter({ hasText: "AI-written headlines." });
  await page.getByRole("button", { name: "Close AI headline notice", exact: true }).click();
  assert.equal(await aiNote(page).count(), 0, "the AI notice hides when closed");
  // A full load paints it hidden from the start: the pre-paint script marks <html> before hydration (app/layout.tsx).
  await page.reload({ waitUntil: "domcontentloaded" });
  assert.equal(await page.evaluate(() => document.documentElement.getAttribute("data-notice-ai-headlines")), "closed");
  assert.ok(["none", "absent"].includes(await page.evaluate(() => { const n = document.querySelector(".ai-notice"); return n ? getComputedStyle(n).display : "absent"; })), "hidden before hydration");
  await page.getByText("No published events are available").waitFor();
  assert.equal(await aiNote(page).count(), 0, "it stays hidden for the visit");
  {
    const fresh = await browser.newContext({ storageState: await page.context().storageState() });
    const tab = await fresh.newPage();
    await tab.goto(page.url());
    // After hydration and the client fetch, so the storage read has run: the notice is there again.
    await tab.getByText("No published events are available").waitFor();
    assert.equal(await aiNote(tab).count(), 1, "a fresh context shows the AI notice again");
    await fresh.close();
  }
  if (hasTopics)
    await page.getByText("1 topic in your brief", { exact: true }).waitFor();
  await page.screenshot({
    path: shot + "/dashboard-desktop.png",
    fullPage: true,
  });
  // Cabinet pass (2026-10-27): the topic picker lives on the board, so the persistence check reads it there.
  for (const r of [
    "/history",
    "/topics/pending",
    "/events/pending",
    "/settings",
    "/dashboard",
  ])
    await go(r);
  if (
    hasTopics &&
    !(await page.locator(".topic-option input").first().isChecked())
  )
    throw Error("Selected topic did not persist");
  await go("/settings"); // the profile form lives on Account
  await page.getByLabel("Name", { exact: true }).fill("Visual Reader");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await page.getByText("Profile saved.", { exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  for (const r of [
    "/dashboard",
    "/history",
    "/onboarding",
    "/topics/pending",
    "/events/pending",
    "/settings",
    "/",
  ]) {
    await go(r);
    if (r === "/dashboard" || r === "/")
      await page.screenshot({
        path:
          shot + (r === "/" ? "/landing-mobile.png" : "/dashboard-mobile.png"),
        fullPage: true,
      });
  }
  await go("/settings");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.waitForURL("**/login");
  await go("/dashboard");
  await page.waitForURL("**/login");
  if (issues.length) throw Error(issues.join("\n"));
  console.log(
    "PASS: desktop/mobile routes, registration, onboarding, preferences, profile, logout, auth redirect, no overflow or browser errors",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
