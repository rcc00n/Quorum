# Portal verification

Latest release: **20261023-web-portals-09f5325**, deployed and verified with publication disabled. Code SHA `09f5325c78fe71677c46a83f952c04b602e6fc7b`; see [current release evidence](#production-release-evidence--integration-readiness). Earlier sections below retain historical milestone evidence.

## Previous proposal milestone — 2026-10-22 local / 2026-10-23 UTC

Backend foundation: `6d70d1a`; shared master coordination: `d5fe6bf`. UI/tests and documentation are reviewed together in PR #1.

Owner: Vadim; branch `feature/web-portals`; [PR #1](https://github.com/rcc00n/Quorum/pull/1). This release is **TESTED locally, not INTEGRATED or DEPLOYED**. Production remains `20261022-web-portals-r2` because the reasoning schema and cross-team transport/authorization are unapproved. No machine identity, snapshot environment, ingestion route, auth migration or production write was introduced.

## Results

- 29 Django tests pass: 13 original regressions plus 16 validation/store/API tests. Includes authenticated fixture→publisher→feed/event→Control, role denial, strict input/null/quote/reference checks, immutable revisions, integrity fallback, expiry, rollback, failed atomic head write, corrupt metadata and no-config pending state. This is local DEMO data, not sponsor integration.
- Django system check passes; `makemigrations --check --dry-run`: no changes.
- Next production build and TypeScript typecheck pass via `bash deploy/build-web.sh`; all existing routes retained.
- Four tooling regressions and rating/null/threshold/safe-link tests pass.
- Chromium existing route/registration/onboarding/profile/logout/auth-redirect regression passes against isolated local Django (development proxy and production Next build with a local same-origin review proxy). Legacy fixture evidence/date/four-mode/mobile tests pass.
- New rich DEMO browser tests pass at 1440/768/390 widths: keyboard disclosures, source links/access, reviewer disagreement, unknown denominator, all four comparison/rating modes, timeline/missing trace, stale/fallback/revision permalink and 503 retry recovery. No overflow or page errors. Full-page desktop/mobile screenshots visually inspected; no comprehensive WCAG audit claimed.
- Required `doctor.sh`: PASS=15 FAIL=0 BLOCKED=1 NOT_TESTED=1. `verify-all.sh`: PASS=19 FAIL=0 BLOCKED=14 NOT_TESTED=1. WSL2 confirmed. Remaining blockers are Zetaris startup headroom, missing Azure registry auth, official bundle prerequisites and missing model-route credentials. NOT_TESTED is optional Docker Desktop integration; Cursor is absent from routine gates. No inference requested.
- Read-only production verification: external HTTPS home 200; target-host home/login/register/session/staff login 200, unauthenticated feed 401. Both Quorum services active, snapshot root unconfigured and publisher disabled. Exactly eight expected accounts with correct roles remain. No password/plaintext credential file was accessed. No service/container/Nginx/DB configuration changed; other containers retain their previous uptime/health (including the already unhealthy route-map-backend). Password authentication was not repeated this run; prior eight-account HTTPS evidence remains in `deploy/STATUS.md`.

## Reproduce locally

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py test portal
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py check
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py makemigrations --check --dry-run
python3 -m unittest discover -s scripts -p test_checks.py
node web/tests/ratings.cjs
bash deploy/build-web.sh
# With the isolated local backend and portal running, and externally installed browser tools:
PLAYWRIGHT_MODULE=<external-playwright> CHROMIUM_PATH=<chromium> node web/tests/browser.cjs
PLAYWRIGHT_MODULE=<external-playwright> CHROMIUM_PATH=<chromium> TYPESCRIPT_MODULE=<external-typescript> node web/tests/demo.cjs
```

Prepare the richer browser fixture **outside Git**, validating it through the real projection:

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py shell <<'PY'
import json
from pathlib import Path
from portal.snapshot_validation import parse_snapshot
from portal.snapshot_projection import project
payload = parse_snapshot(Path('backend/portal/fixtures/analysis-demo.json').read_bytes())
publication = {k: payload[k] for k in ('revision', 'edition', 'run_id', 'generated_at', 'expires_at', 'source_revision', 'mode')}
publication.update(status='partial', fallback=False, published_at=payload['generated_at'])
out = Path.home() / '.local/share/quorum/analysis-browser-fixture.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(project(payload, publication)))
PY
PLAYWRIGHT_MODULE=<external-playwright> CHROMIUM_PATH=<chromium> QUORUM_ANALYSIS_FIXTURE="$HOME/.local/share/quorum/analysis-browser-fixture.json" node web/tests/analysis.cjs
```

Screenshots remain outside the public repository at `~/.local/share/quorum/portal-screenshots/analysis-{1440,390}.png`; binaries are excluded by repository safety rules. Backend/API tests use isolated temporary storage and Django test databases. Browser registration uses a dedicated local runtime database, never production. No fixture is loaded automatically by the production adapter.

## Release limits and next owner

Yelysei must supply/agree the actual reasoning result and safe trace; Anastasia must confirm provenance/access/hash semantics and real Zetaris retrieval. All owners must approve versioning, expiry and restricted transport, and reconcile reasoning-branch product amendments before integration. Credentials/real upstream readiness remain BLOCKED. Keep the [web deployment gates](RELEASE_CHECKLIST.md) unchecked until the corresponding production evidence exists. No new deployment backup was necessary because no production mutation/deployment occurred; every future deployment still requires a restricted auth backup and rollback verification.


## Integration-readiness milestone — 2026-10-23 UTC

Branch `feature/web-portals`, baseline `9a79ea9`; PR #1. Read-only collector review advanced to `09890a0`; reasoning remains `49e6d1f`, without a real structured sample. Compatibility matrix and product approval options are in PORTAL_INTEGRATION.md. No other branch was checked out, merged, rebased, cherry-picked, committed or pushed in this milestone.

Local checks: 36 Django tests; six temporary-filesystem upgrade safety tests; Django system/migration drift checks; Next production build/typecheck; four tooling tests; rating checks; validated JSON→actual TypeScript model check. The new isolated HTTP browser harness exercises actual candidate validation/publication→session-authenticated API→TypeScript→Evidence/Perspective/Timeline, corrections, missing trace, stable dateless links and rollback, plus admin access/regular-user denial, all existing auth/routes through browser.cjs and the rich recovery/responsive suite through analysis.cjs. Desktop/tablet/mobile widths pass. All snapshots/accounts here are explicitly TEST/DEMO, outside production; no sponsor calls occur.

Reproduce after installing/building per module READMEs:

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py portal_snapshot validate --file backend/portal/fixtures/analysis-demo.json
node web/tests/contract.cjs
PLAYWRIGHT_MODULE=<external-playwright> CHROMIUM_PATH=<chromium> node web/tests/boundary.cjs
python3 -m unittest discover -s deploy -p 'test_*.py'
```

Doctor: PASS=15 FAIL=0 BLOCKED=1 NOT_TESTED=1. Verify: PASS=19 FAIL=0 BLOCKED=14 NOT_TESTED=1. Same actual resource/registry/model prerequisites; no Cursor gate and no inference. A compact branch-only CI workflow is added; a local pass is not a claim that hosted CI has run. Guarded production plan/backup/deploy and authenticated HTTPS results are recorded below when actually completed.


## Production release evidence — integration readiness

- Owner Vadim; **only branch `feature/web-portals`**. Deployed code SHA `09f5325c78fe71677c46a83f952c04b602e6fc7b`, release `20261023-web-portals-09f5325`; rollback `20261022-web-portals-r2`. The later handoff/documentation commit does not change deployed application code.
- [Hosted CI 39887513802](https://github.com/rcc00n/Quorum/actions/runs/39887513802) **success**: Python 3.10, 36 Django tests, six upgrade tests, schema fixture command, Next build/typecheck, rating and actual TypeScript contract checks. Local real-HTTP/browser boundary, old auth/routes/admin and rich responsive/recovery tests also passed. No external sponsor service was mocked into a PASS.
- Guarded read-only plan passed. Apply created root-private SQLite backups before dependency installation and a final cutover backup after stopping only Quorum. Backup directory mode 700, DB/rollback metadata mode 600; integrity checked. Existing dependency pins were unchanged; only five missing pinned validator dependencies were added. Isolated tests also passed on the VPS Python 3.10.12. No auth migrations were pending/applied.
- Both Quorum services restarted successfully on loopback; Node v22.19.0 retained. Target-host and external HTTPS home/login/register/session/staff checks passed, unauthenticated feed remains 401. All other Docker container IDs/start timestamps stayed unchanged; no Nginx, SSH, firewall or other project runtime configuration changed. Code/static automatic rollback was tested with a simulated health failure, not forced on live production.
- Actual HTTPS checks authenticated all eight existing accounts, verified four admin accesses and four regular-user staff denials, Secure/HttpOnly cookies, CSRF denial and logout. Staff overview/users/add/topics/sources/status/integrations and all existing protected routes were checked; desktop/mobile layouts did not overflow. Existing catalog remains 19 sources/one topic, events/digests empty/pending. Event-page JS assets include all three rich UI modules; no invented analysis was served.
- Registration/onboarding/persistent topic selection/logout were tested using exact temporary accounts, then cleaned up. Initial automation stopped on the two desktop settings logout controls; scoping the test selector resolved this, with no application patch required. A final read-only audit against the cutover backup proved all eight original account records/password hashes/roles (except expected login timestamps) and every original preference row unchanged; no temporary accounts remain.
- Production read-only `portal_snapshot validate` successfully checked the labelled fixture with `published:false`. Snapshot root is unset; publication flag remains off. No machine credential, transport, remote processing, inference, DEMO feed or live upstream result was enabled.

Remaining blockers: no actual reasoning result/schema or verified trace/correction semantics; collector hash/offset/provenance agreement; approved transport/authorization, freshness/ranking/timezone/retention and genuine sponsor execution. Next owner handoff: Yelysei provides one real result, Anastasia confirms provenance/access/independence, all approve transport before publishing. The code is DEPLOYED; external result integration is still BLOCKED.

### Concurrent upstream change / branch-isolation limit

Final fetch found `origin/yelysei/agents@f3a32ec` and master `c3cc5ac` (PR #3 merged by the team during this session). Read-only review found a written reasoning snapshot proposal, still no runtime sample. Its illustrative JSON failed read-only compatibility validation as expected; diagnostics stayed private/value-free and no publication occurred. Updated field gaps/options are in PORTAL_INTEGRATION.md. Draft PR #1 is now CONFLICTING with master. No merge/rebase/cherry-pick or master write was attempted; strict branch isolation takes precedence. Production remains the tested `09f5325` release, unaffected by this remote documentation change.
