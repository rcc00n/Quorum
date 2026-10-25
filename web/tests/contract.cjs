// Static compatibility of actual projected/API JSON with the current TypeScript models.
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const { execFileSync } = require("node:child_process");
const repo = path.resolve(__dirname, "../..");
const build =
  process.env.QUORUM_WEB_BUILD ||
  path.join(os.homedir(), ".local/share/quorum/portal-web-build");
const python =
  process.env.QUORUM_PYTHON ||
  path.join(os.homedir(), ".local/share/quorum/portal-venv/bin/python");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "quorum-contract-"));
try {
  const raw = process.env.QUORUM_SNAPSHOT_FILE
    ? fs.readFileSync(process.env.QUORUM_SNAPSHOT_FILE, "utf8")
    : execFileSync(
        python,
        [
          "backend/manage.py",
          "shell",
          "--verbosity",
          "0",
          "-c",
          `import json; from pathlib import Path; from portal.snapshot_validation import parse_snapshot; from portal.snapshot_projection import project; p=parse_snapshot(Path('backend/portal/fixtures/analysis-demo.json').read_bytes()); from portal.reasoning_preview import load_preview; candidates=[project(p, {'status':'partial'}), *[load_preview(Path('backend/portal/fixtures/reasoning-demo')/name) for name in ('snapshot.sample.json','snapshot.empty-day.sample.json','snapshot.partial.sample.json')]]; candidates.extend(load_preview(path) for path in sorted(Path('docs/examples').glob('snapshot*.json'))); print(json.dumps(candidates))`,
        ],
        {
          cwd: repo,
          env: { ...process.env, DJANGO_DEBUG: "1" },
          encoding: "utf8",
        },
      );
  const snapshot = JSON.parse(raw);
  const file = path.join(temp, "contract.ts");
  fs.writeFileSync(
    file,
    `import type { Snapshot } from ${JSON.stringify(path.join(repo, "web/lib/api"))};\nconst candidate = ${JSON.stringify(snapshot)} satisfies ${process.env.QUORUM_SNAPSHOT_FILE ? "Snapshot" : "Snapshot[]"};\n`,
  );
  execFileSync(
    process.execPath,
    [
      path.join(build, "node_modules/typescript/bin/tsc"),
      "--noEmit",
      "--strict",
      "--skipLibCheck",
      "--target",
      "ES2020",
      "--module",
      "esnext",
      "--moduleResolution",
      "bundler",
      file,
    ],
    { stdio: "pipe" },
  );
  console.log(
    "PASS: validated projection/API JSON satisfies current TypeScript Snapshot and structured analysis + reasoning 1.0 preview models (TEST only)",
  );
} catch {
  console.error(
    "FAIL: portal contract type check; no candidate contents emitted",
  );
  process.exitCode = 1;
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
