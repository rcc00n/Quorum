// Isolated TEST-only real HTTP boundary. Never points at production or reads account files.
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path"),
  http = require("node:http"),
  net = require("node:net");
const { spawn, execFileSync } = require("node:child_process");
const repo = path.resolve(__dirname, "../.."),
  python =
    process.env.QUORUM_PYTHON ||
    path.join(os.homedir(), ".local/share/quorum/portal-venv/bin/python");
const build =
  process.env.QUORUM_WEB_BUILD ||
  path.join(os.homedir(), ".local/share/quorum/portal-web-build");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "quorum-boundary-")),
  children = [];
let proxy, browser;
const reasoningMode = process.argv.includes("--reasoning");
const sourceIndex = process.argv.indexOf("--reasoning-file");
const reasoningFile = sourceIndex < 0 ? null : process.argv[sourceIndex + 1];
if (sourceIndex >= 0 && (!reasoningMode || !reasoningFile || reasoningFile.startsWith("--")))
  throw Error("--reasoning-file requires --reasoning and a source file path");
const serveMode = reasoningMode && process.argv.includes("--serve");
fs.chmodSync(temp, 0o700);
const freePort = () =>
  new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
  });
const run = (args, env) =>
  execFileSync(python, args, { cwd: repo, env, stdio: "pipe" });
(async () => {
  const [apiPort, webPort] = await Promise.all([freePort(), freePort()]);
  proxy = http.createServer((req, res) => {
    const upstream = http.request(
      {
        host: "127.0.0.1",
        port: /^\/(api|staff|staff-static)\//.test(req.url) ? apiPort : webPort,
        path: req.url,
        method: req.method,
        headers: req.headers,
      },
      (r) => {
        res.writeHead(r.statusCode, r.headers);
        r.pipe(res);
      },
    );
    upstream.on("error", () => {
      res.writeHead(502);
      res.end();
    });
    req.pipe(upstream);
  });
  await new Promise((resolve) => proxy.listen(0, "127.0.0.1", resolve));
  const root = "http://127.0.0.1:" + proxy.address().port;
  const password = require("node:crypto").randomBytes(32).toString("base64url");
  const env = {
    ...process.env,
    DJANGO_DEBUG: "1",
    DJANGO_SECRET_KEY: require("node:crypto")
      .randomBytes(48)
      .toString("base64url"),
    DJANGO_ALLOWED_HOSTS: "127.0.0.1",
    DJANGO_CSRF_ORIGINS: root,
    QUORUM_PORTAL_DATA: path.join(temp, "auth"),
    QUORUM_CATALOG_PATH: "",
    QUORUM_SNAPSHOT_ROOT: reasoningMode ? "" : path.join(temp, "snapshots"),
    QUORUM_ENABLE_SNAPSHOT_PUBLICATION: reasoningMode ? "" : "1",
    QUORUM_ENABLE_REASONING_PREVIEW: reasoningMode ? "1" : "",
    QUORUM_REASONING_PREVIEW_FILE: path.join(temp, "reasoning.json"),
    QUORUM_TEST_REASONING_ONLY: reasoningMode ? "1" : "",
    PYTHONPATH: path.join(repo, "backend"),
    QUORUM_TEST_PASSWORD: password,
  };
  if (reasoningMode)
    fs.copyFileSync(
      reasoningFile || path.join(
        repo,
        "backend/portal/fixtures/reasoning-demo/snapshot.sample.json",
      ),
      env.QUORUM_REASONING_PREVIEW_FILE,
    );
  run(["backend/manage.py", "migrate", "--noinput"], env);
  run(
    [
      "-c",
      `import os,json,hashlib,django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from django.contrib.auth.models import User
from portal.snapshot_store import SnapshotStore
from pathlib import Path
from datetime import datetime,timezone,timedelta
User.objects.create_user('DEMO-boundary-reader',password=os.environ['QUORUM_TEST_PASSWORD'])
User.objects.create_superuser('DEMO-boundary-admin',password=os.environ['QUORUM_TEST_PASSWORD'])
if os.getenv('QUORUM_TEST_REASONING_ONLY'):
 import sys;sys.exit(0)
p=json.loads(Path('backend/portal/fixtures/analysis-demo.json').read_text())
p['generated_at']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
p['expires_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat().replace('+00:00','Z')
s=SnapshotStore();s.prepare();f=s.root/'staging/input.json';f.write_text(json.dumps(p));s.publish(f,hashlib.sha256(f.read_bytes()).hexdigest(),allow_demo=True)`,
    ],
    env,
  );
  children.push(
    spawn(
      python,
      ["backend/manage.py", "runserver", `127.0.0.1:${apiPort}`, "--noreload"],
      { cwd: repo, env, stdio: "ignore" },
    ),
  );
  children.push(
    spawn(
      process.execPath,
      [
        path.join(build, "node_modules/next/dist/bin/next"),
        "start",
        "--hostname",
        "127.0.0.1",
        "--port",
        String(webPort),
      ],
      {
        cwd: build,
        env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
        stdio: "ignore",
      },
    ),
  );
  for (let i = 0; i < 60; i++) {
    try {
      if (
        (await fetch(root + "/api/session/")).ok &&
        (await fetch(root + "/login")).ok
      )
        break;
    } catch {}
    if (i === 59) throw Error("local startup failed");
    await new Promise((r) => setTimeout(r, 500));
  }
  if (serveMode) {
    const accountFile = path.join(temp, "LOCAL-DEMO-accounts.txt");
    fs.writeFileSync(
      accountFile,
      `LOCAL FICTIONAL PREVIEW ONLY\nUsername: DEMO-boundary-reader\nPassword: ${password}\nUsername: DEMO-boundary-admin (local staff)\nPassword: ${password}\n`,
      { mode: 0o600 },
    );
    console.log(
      `FICTIONAL local preview: ${root}/preview/reasoning\nPrivate LOCAL test credentials: ${accountFile}\nSign in using that file; Ctrl+C removes all temporary runtime data. No production account or publisher is used.`,
    );
    await new Promise((resolve) => {
      process.once("SIGINT", resolve);
      process.once("SIGTERM", resolve);
    });
    return;
  }
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH,
    args: ["--no-sandbox"],
  });
  if (reasoningMode) {
    await require(reasoningFile ? "./reasoning-snapshot-checks.cjs" : "./reasoning-checks.cjs")({
      browser,
      root,
      env,
      password,
      temp,
      sourceFile: reasoningFile,
    });
    return;
  }
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", () => errors.push("browser_error"));
  const session = await (await page.request.get(root + "/api/session/")).json();
  const login = await page.request.post(root + "/api/login/", {
    headers: { "X-CSRFToken": session.csrfToken, Origin: root },
    data: { username: "DEMO-boundary-reader", password },
  });
  if (!login.ok()) throw Error("TEST login failed");
  const result = await page.request.get(root + "/api/events/demo-event/");
  const snapshot = await result.json();
  if (
    snapshot.status !== "demo" ||
    snapshot.events[0].analysis.claims.length !== 4
  )
    throw Error("API projection failed");
  const output = path.join(temp, "api.json");
  fs.writeFileSync(output, JSON.stringify(snapshot));
  execFileSync(process.execPath, [path.join(repo, "web/tests/contract.cjs")], {
    env: { ...env, QUORUM_SNAPSHOT_FILE: output, QUORUM_WEB_BUILD: build },
    stdio: "pipe",
  });
  await page.goto(root + "/events/demo-event");
  for (const name of [
    "Evidence Explorer",
    "Perspective Comparison",
    "Investigation Timeline",
  ])
    await page.getByRole("heading", { name, exact: true }).waitFor();
  await page
    .getByText(
      "DEMO · Fictional interface fixture. Not verified news or live findings.",
      { exact: true },
    )
    .waitFor();
  await page.locator(".claim-detail>summary").nth(2).click();
  await page
    .getByText(
      "The supplied reviewers disagree. This claim remains unresolved.",
      { exact: true },
    )
    .waitFor();
  run(
    [
      "-c",
      `import os,json,hashlib,django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from portal.snapshot_store import SnapshotStore
s=SnapshotStore();f=s.root/'staging/input.json';p=json.loads(f.read_text());p.update(revision='demo-r2',parent_revision='demo-r1')
a=p['events'][0]['analysis'];a['trace']=[];a['corrections']=[dict(supersedes_claim_id='demo-unknown',replacement_claim_id='demo-unknown',previous_revision='demo-r1',timestamp=p['generated_at'],summary='DEMO boundary correction')]
f.write_text(json.dumps(p));s.publish(f,hashlib.sha256(f.read_bytes()).hexdigest(),allow_demo=True)`,
    ],
    env,
  );
  await page.reload();
  await page.getByText("DEMO boundary correction", { exact: true }).waitFor();
  await page
    .getByText("No investigation trace supplied.", { exact: false })
    .waitFor();
  await page
    .getByRole("link", { name: "Permalink to revision demo-r2" })
    .waitFor();
  run(
    [
      "backend/manage.py",
      "portal_snapshot",
      "rollback",
      "--revision",
      "demo-r1",
    ],
    env,
  );
  await page.reload();
  await page
    .getByRole("link", { name: "Permalink to revision demo-r1" })
    .waitFor();
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    if (await page.locator("body").evaluate((e) => e.scrollWidth > innerWidth))
      throw Error("overflow");
  }
  const denied = await page.request.get(root + "/staff/", { maxRedirects: 0 });
  if (denied.status() !== 302) throw Error("regular staff denial failed");
  const adminContext = await browser.newContext();
  const adminRequest = adminContext.request;
  const adminSession = await (
    await adminRequest.get(root + "/api/session/")
  ).json();
  const adminLogin = await adminRequest.post(root + "/api/login/", {
    headers: { "X-CSRFToken": adminSession.csrfToken, Origin: root },
    data: { username: "DEMO-boundary-admin", password },
  });
  if (!adminLogin.ok()) throw Error("TEST admin login failed");
  for (const route of [
    "/staff/",
    "/staff/auth/user/",
    "/staff/auth/user/add/",
    "/staff/topics/",
    "/staff/sources/",
    "/staff/status/",
    "/staff/integrations/",
  ]) {
    if (!(await adminRequest.get(root + route)).ok())
      throw Error("staff route failed");
  }
  await adminContext.close();
  async function browserScript(file, extra = {}) {
    await new Promise((resolve, reject) => {
      const child = spawn(
        process.execPath,
        [path.join(repo, "web/tests", file)],
        {
          env: { ...process.env, QUORUM_TEST_URL: root, ...extra },
          stdio: "ignore",
        },
      );
      children.push(child);
      child.on("error", reject);
      child.on("exit", (code) =>
        code === 0 ? resolve() : reject(Error("browser regression failed")),
      );
    });
  }
  await browserScript("analysis.cjs", { QUORUM_ANALYSIS_FIXTURE: output });
  await browserScript("demo.cjs", {
    TYPESCRIPT_MODULE: path.join(build, "node_modules/typescript"),
  });
  // Remove only this temporary TEST store's heads for the existing pending/auth suite.
  for (const file of ["current.json", "previous.json"])
    fs.rmSync(path.join(temp, "snapshots", file), { force: true });
  await browserScript("browser.cjs");
  if (errors.length) throw Error("page errors");
  console.log(
    "PASS: TEST candidate → validation/store → authenticated HTTP API → TypeScript → rich UI; dateless links, disagreement, corrections, missing trace, rollback, three widths; no sponsor integration claimed",
  );
})()
  .catch((error) => {
    // Value-free locations help diagnose local checks without printing inputs/passwords.
    const locations =
      String(error.stack || "").match(/web\/tests\/[A-Za-z0-9_.-]+:\d+:\d+/g) ||
      [];
    if (locations.length)
      console.error("Check location: " + locations.join(", "));
    console.error(
      "FAIL: isolated portal HTTP boundary; input and credentials withheld",
    );
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    for (const child of children) child.kill();
    if (proxy) await new Promise((r) => proxy.close(r));
    fs.rmSync(temp, { recursive: true, force: true });
  });
