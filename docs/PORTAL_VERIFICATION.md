# Portal verification

Latest release: **20261023-web-portals-09f5325**, deployed and verified with publication disabled. Code SHA `09f5325c78fe71677c46a83f952c04b602e6fc7b`; see [current release evidence](#production-release-evidence--integration-readiness). Earlier sections below retain historical milestone evidence.

## Current reproducible checks

Run from the repo root on `feature/web-portals`. [Backend setup](../backend/README.md#local-setup) and [Next setup](../web/README.md#run) own installation/start commands. Dependencies/build/runtime remain outside Git. **Do not target production with local account-creating/browser tests.** Existing fixtures never establish real integration.

```bash
export DJANGO_DEBUG=1
export QUORUM_PORTAL_DATA="$HOME/.local/share/quorum/portal-local-auth"
PY="$HOME/.local/share/quorum/portal-venv/bin/python"
"$PY" backend/manage.py check
"$PY" backend/manage.py makemigrations --check --dry-run
"$PY" backend/manage.py test portal
"$PY" backend/manage.py test portal.test_reasoning_preview
python3 -m unittest discover -s deploy -p 'test_*.py'
python3 -m unittest discover -s scripts -p 'test_*.py'
"$PY" backend/manage.py portal_snapshot validate --file backend/portal/fixtures/analysis-demo.json
bash deploy/build-web.sh  # includes production build + TypeScript typecheck
node web/tests/ratings.cjs
node web/tests/editorial.cjs
node web/tests/reasoning-trace.cjs
node web/tests/contract.cjs  # production projection + all three reasoning JSON -> actual TS types
export PLAYWRIGHT_MODULE="$HOME/.local/share/quorum/portal-browser/node_modules/playwright"
export CHROMIUM_PATH="$HOME/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
node web/tests/boundary.cjs
node web/tests/boundary.cjs --reasoning  # exact main/empty/partial via actual authenticated Django/Next
node web/tests/boundary.cjs --reasoning --serve
# The last command prints a localhost URL + PRIVATE LOCAL test-account file path, not passwords.
# Sign in using that file. Ctrl+C deletes only its owned temporary runtime.
bash scripts/doctor.sh
bash scripts/verify-all.sh  # no --inference; credential/resource blockers stay BLOCKED
```

`boundary.cjs` starts disposable loopback Django/Next/proxy services and a separate temporary auth DB; it never uses the eight production accounts. Ordinary boundary tests exercise the TEST snapshot store plus original browser/analysis/demo suites; `--reasoning` keeps publishing disabled and tests the preview through real HTTP, including all45 main trace steps,29 empty steps, both articles, partial frame gaps, keyboard/reduced-motion and1440/768/390px. No API interception is used for reasoning. Screenshots default outside Git to `~/.local/share/quorum/portal-screenshots`; override `QUORUM_SCREENSHOTS`. Independently run `browser.cjs`, `analysis.cjs` or `demo.cjs` only against a disposable local `QUORUM_TEST_URL`; they create TEST users and require the documented external browser packages. `TYPESCRIPT_MODULE` and `QUORUM_ANALYSIS_FIXTURE` select external TS/projected TEST fixture for those standalone scripts; boundary supplies them automatically.

To test an upstream contract change: fetch/read the new canonical §8 and publisher, record branch/SHA/sample hashes, copy exact public-safe samples with `git show <sha>:docs/examples/<name> > backend/portal/fixtures/reasoning-demo/<name>`, then deliberately update consumer/tests if the contract changed. Reject unknown fields rather than guessing. `QUORUM_REASONING_PREVIEW_FILE` selects a candidate when starting a manually configured local Django server with `DJANGO_DEBUG=1`, `QUORUM_ENABLE_REASONING_PREVIEW=1` and nonproduction `QUORUM_PORTAL_DATA`; authenticate on the same origin. Read-only reasoning validation without a server: `PYTHONPATH=backend "$PY" -c 'from portal.reasoning_preview import load_preview; load_preview("/path/to/candidate.json"); print("compatible development preview; not published")'`. It prints no input contents. Raw reasoning files deliberately fail the **internal production** `portal_snapshot validate` command; do not weaken it to pass them.

Relevant environment names: Django `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_ORIGINS`, `QUORUM_PORTAL_DATA`, `QUORUM_STATIC_ROOT`; integration `QUORUM_CATALOG_PATH`, `QUORUM_SNAPSHOT_ROOT`, `QUORUM_ENABLE_SNAPSHOT_PUBLICATION`; preview `QUORUM_ENABLE_REASONING_PREVIEW`, `QUORUM_REASONING_PREVIEW_FILE`; tools `QUORUM_PYTHON`, `QUORUM_WEB_BUILD`, `PLAYWRIGHT_MODULE`, `CHROMIUM_PATH`, `QUORUM_SCREENSHOTS`. Names are configuration documentation, **not authorization to enable production publication**. Secrets are private, never passed in example values or committed.

Hosted CI: `.github/workflows/portal.yml`, push to `feature/web-portals` for backend/web/deploy/workflow changes or manual `workflow_dispatch`; job also refuses other branches. Python3.10 regression/check/migration/upgrade/security/validator + Node22 build/typecheck/static fixtures; no browser download, sponsor service or paid model required. Reproduce browser tests locally as above. Inspect `gh run list --workflow portal.yml --branch feature/web-portals` / `gh run view <id>` for actual hosted results, never assume a green local run is hosted CI.

## External real-model fixture acceptance

The original direct-NVIDIA result remains private and unchanged outside Git. This is real model output over **FICTIONAL source data**, not verified news or a Zetaris/Meterless Engine run. The consumer accepts its optional model ledger and `context` claim kind, retains exact source JSON in the authenticated API and displays the reported model provenance. The known summary contradiction remains visible verbatim; parser acceptance does not certify editorial consistency.

After the normal build, test that exact file through disposable authenticated Django → Next.js → Chromium, including TypeScript validation of the actual API response:

```bash
export QUORUM_NVIDIA_SNAPSHOT="$HOME/.local/share/quorum/experiments/nvidia-first-20261023/live-graph-resumed/snapshots/russia-ukraine-war/2026-10-22.json"
QUORUM_REASONING_EXPECTED_SHA256=8f86e67c5a7a011465e72fa16123d1b904df5a1f4e586a3ad92ceedc9ea75017 \
  node web/tests/boundary.cjs --reasoning --reasoning-file "$QUORUM_NVIDIA_SNAPSHOT"
```

Use the browser environment variables from the current reproducible checks above. `--reasoning-file` requires `--reasoning`, copies source bytes only into its owned temporary runtime, keeps publisher/store disabled, and never replaces canonical fixtures. It verifies the source/copy hashes before and after, exact upstream API equality, unchanged summary, all article blocks/claim links/source URLs, every supplied paired verdict and evidence quote/stance/group, all trace decisions/reasons/models/durations, roundup links/statuses and responsive layouts. Screenshots stay outside Git. The source snapshot contains **1 article, 12 published story claims, 77 published evidence rows, 39 trace records and 3 roundup entries**; the graph's full private state contains 20 claims/117 evidence rows, so the UI must not invent omitted roundup claim details.

Run the ordinary `boundary.cjs` and `boundary.cjs --reasoning` suites too; the external-file check supplements all original auth/analysis/demo and main/empty/partial fixture regressions. No model request is made by these checks. Local acceptance does not activate publication, change production configuration/accounts or authorize transport.

### Local acceptance evidence — 2026-10-23

WEB-NVIDIA-ACCEPT is **TESTED locally**, not deployed or verified real-news processing. The original SHA-256 above is unchanged. Authenticated API `reasoning` equals the entire original JSON; actual returned API JSON satisfies the TypeScript model. Chromium compares the one article/headline/standfirst/five blocks, all 12 published claims and both review verdicts/reasons, all 77 published evidence quotes/stances/groups/source URLs, 39 ordered trace decisions/reasons/model identities/durations, three roundup statuses/links and absent roundup claim details. Desktop/tablet/mobile widths 1440/768/390 have no horizontal overflow; the retained FICTIONAL label, unpublished/expired hints and model declarations are visible. Desktop topic and mobile article screenshots were inspected outside Git.

The original summary still says both “1 story crossed the bar” and “No story crossed the bar today”; it is displayed verbatim, not repaired by this consumer. The upstream snapshot reports `ok`; this is retained as a producer status, not an editorial correctness claim. The article's paired reviewers agree on its supplied verdicts; the four reviewer disagreements on the escalated roundup event are exported in its trace, not as invented claim detail.

Relevant local checks: 50 Django tests (including ledger/context preservation and malformed-count/unknown-field rejection), two focused fixed-clock tests, system check and no migration drift; six deployment safety tests; four tooling tests; Next production build/typecheck; rating/editorial/recorded-loop/TypeScript contract checks; original isolated auth/analysis/demo browser boundary and the external snapshot boundary. The main/empty/partial canonical browser suite also passes: 2/0/2 stories and 45/29/45 trace records, plus context/XSS/partial/error/retry, keyboard, reduced motion and three widths. No model calls, hosted CI, push, merge or production check/deployment is claimed by these local checks. Private logs/screenshots: `~/.local/share/quorum/experiments/web-nvidia-accept-20261023/`.

Routine doctor:15 PASS/0 FAIL/1 BLOCKED/1 NOT_TESTED; verify without inference:19 PASS/0 FAIL/14 BLOCKED/1 NOT_TESTED. Model credentials are not loaded into routine diagnostics; the separately recorded real NVIDIA/Meterless experiments remain the inference evidence. Local Zetaris resource/auth/runtime/SQL gates remain unresolved. Production publisher/store, account/configuration data and deployment code were not changed.

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

## Product reconciliation — local-only milestone (2026-10-22 client date)

Authorized merge `05e87b4` incorporates master `c3cc5ac` into feature/web-portals only. README/DECISIONS conflicts were resolved individually, preserving team product changes and portal/auth/security history. New optional UI models do not alter the production input schema. Article/roundup/quiet-day flow is tested; palette/font contradiction is documented and held.

Local evidence: 38 Django/snapshot tests (including Unicode offsets and explicit upstream-version mismatch), six upgrade safety tests, Next production build/typecheck, four tooling checks, ratings/editorial invariants and TypeScript contract check pass. `web/tests/boundary.cjs` passes actual local API/auth/admin/original-route checks plus extended `analysis.cjs` article/roundup/quiet/pending/error/partial/stale and 1440/768/390 tests. Desktop/mobile article screenshots were visually reviewed outside Git. No photo is fetched by the synthetic rights/host unit tests; no real photo license verification is claimed.

Doctor PASS=15 FAIL=0 BLOCKED=1 NOT_TESTED=1; verify PASS=19 FAIL=0 BLOCKED=14 NOT_TESTED=1, no inference. Missing sponsor credentials/runtime remain actual blockers. Anastasia's confirmed semantics are attributed to Issue #2, not presented as an authenticated Zetaris run by this milestone. No genuine reasoning JSON exists yet. Production/account/configuration was not accessed or changed in this milestone; deployed code stays `09f5325`.

Reconciliation final evidence: code `19f3de300f0479d8f81166e6eccb326ae0eb65cc`, branch `feature/web-portals`, merge `05e87b4`. [Hosted CI 39890295440](https://github.com/rcc00n/Quorum/actions/runs/39890295440) passed Python 3.10 / 38 Django tests / six upgrade tests / Next build-typecheck / ratings-editorial / contract fixture checks. The real local HTTP/browser harness and separate legacy DEMO browser test passed; new documentation links and secret/scope scans passed. PR #1 verified MERGEABLE and remains draft. Later handoff commits are documentation only.

## Reasoning 1.0 fictional preview milestone

Owner Vadim; branch `feature/web-portals`; baseline `6934298`; code `0fe73256f468a830c56040abce32cfd07e6fa5f9`; PR #1. No merge/rebase/teammate-branch or production change. Canonical upstream pin: `yelysei/agents@8a4d453e0ab1f1338abcf77c5eac62d18d9ec2d6`, sample `docs/examples/snapshot.sample.json`, schema1.0/version1, edition2026-10-22, run `2026-10-22-russia-ukraine-war-1`; exact SHA in fixture README. Collector read-only pin `18fb009`. Sample is **FICTIONAL**, not genuine integration evidence.

Local results:

- **43 Django tests** pass (all 38 original auth/CSRF/roles/snapshot/store/rollback/API regressions + five new preview tests); system check and migration drift check pass. Production publication rejects raw reasoning sample; preview mapping preserves the exact envelope, stable IDs and 45 steps without forged provenance. Targeted five preview tests rerun after additional hostile-trace checks pass.
- **Six upgrade safety tests**, **four tooling tests**, production proposal read-only validation, ratings/editorial tests, actual old/new projected JSON→TypeScript checks pass.
- **Next production build and typecheck pass**, including dynamic `/preview/reasoning`; no new dependencies.
- Original `boundary.cjs` passes actual authenticated HTTP/API→TypeScript→UI, then existing `analysis.cjs`, `demo.cjs`, `browser.cjs`: corrections/rollback, missing/stale/partial/error, level2/3 restrictions, auth/registration/preferences/staff and original routes.
- New `boundary.cjs --reasoning` passes actual sample→Django→Next with **no interception** and publication disabled: both stories, all supplied blocks/claim statuses/source links, reviewer disagreements/groups, rubric, exact four cohort pairs/all four missing-rating modes, all45 trace steps/repeated research+critique, roundup groups, three widths, keyboard and reduced motion. TEST-only derivatives exercise sourced context (absent from exact sample), escaped XSS, completed empty day, partial failures, missing trace, unsafe URL422/error/retry and unavailable edition version404. Existing suites cover stale/pending/error rather than inventing preview freshness timestamps.
- `--reasoning --serve` verified independently: mode700 runtime/mode600 credentials, actual session login and fixture API, ordinary feed pending, signal cleanup removes temporary credentials/runtime.
- Changed Markdown relative links, staged diff/size/secret checks pass. No runtime/private/binary artifacts committed. Doctor: PASS15/FAIL0/BLOCKED1/NOT_TESTED1; verify: PASS19/FAIL0/BLOCKED14/NOT_TESTED1, no inference. Missing registry/provider credentials and local Zetaris startup headroom remain actual blockers; Docker Desktop integration is unrequired historical diagnostic, not a claimed sponsor success.

Reproduce from repository root using externally installed Python/Next/Playwright/Chromium:

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py test portal
python3 -m unittest discover -s deploy -p 'test_*.py'
python3 -m unittest discover -s scripts -p 'test_*.py'
bash deploy/build-web.sh
node web/tests/contract.cjs
node web/tests/ratings.cjs
node web/tests/editorial.cjs
export PLAYWRIGHT_MODULE="$HOME/.local/share/quorum/portal-browser/node_modules/playwright"
export CHROMIUM_PATH="$HOME/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
node web/tests/boundary.cjs
node web/tests/boundary.cjs --reasoning
# Interactive isolated preview; no browser dependency required:
node web/tests/boundary.cjs --reasoning --serve
```

Visual evidence (external to Git, **FICTIONAL**): `~/.local/share/quorum/portal-screenshots/reasoning-topic-1440.png`, `reasoning-reading-{1440,390}.png`, `reasoning-story-{1440,390}.png`, `reasoning-evidence-1440.png`, `reasoning-cohorts-1440.png`, `reasoning-feedback-1440.png`. Desktop reading/evidence/cohorts/feedback and mobile reading were visually inspected. Tablet overflow tested at768px. Screenshots demonstrate layout, not factual/source validity; no comprehensive WCAG audit claimed.

**Production not accessed/deployed**: release remains `20261023-web-portals-09f5325`; eight accounts/private auth/configuration untouched. Local TEST sessions do not use those credentials. No collector/reasoning/Zetaris workloads, model requests, machine credentials or publishing transport added. Next real-data milestone and exact missing fields: [handoff](PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview).

Hosted [CI 39895499332](https://github.com/rcc00n/Quorum/actions/runs/39895499332) **succeeded** on implementation `0fe73256f468a830c56040abce32cfd07e6fa5f9` (Python3.10, Django/check/migrations/upgrade/validator, Next/typecheck/ratings/editorial and old/new TypeScript contract). Browser suites remain separately verified locally; CI does not claim sponsor or production execution.

## Reasoning preview UX refinement — local only

Owner Vadim; only `feature/web-portals`; baseline `57f5122`; code `4eb44109ef22f0d02bec66a002344ca27fd2e70d`; PR #1 stays draft. Adapter, canonical reasoning1.0 sample/schema and strict production publication validation are unchanged. All examples below are **FICTIONAL/TEST**.

| Actual browser finding before | Change verified after |
| --- | --- |
| 45 similar rows obscure feedback and hide each decision | Interactive recorded research↔verify / write↔critique diagrams, actual iterations/return counts, stage index and decisions visible in rows; reasons remain expandable |
| Final adjudication below long evidence, repeated warning text, weak reviewer hierarchy | Final status/reason first, explicit agreement and paired verdicts/stance counts, preserved quotes/groups/original links; duplicate explanation removed |
| Long outlet prose makes the four coverage cells hard to compare | Exact covered/eligible numbers and equal-scale bars in a compact 2×2; native keyboard source drilldowns, explicit missing ratings/0-eligible states |
| DEMO warning disappears on scroll; reading sections hard to revisit | Persistent fictional label, active reading navigation, article→evidence→timeline→spectrum→roundup links, back-to-article and focused filtered results |

Only consecutive same-event (or run-scope) A→B→A records with an increased A iteration establish a return. Interleaved events are isolated; stage labels alone cannot invent a loop. Diagrams show recorded sequence, **not causal dependencies or live execution**. Exact fixture has three research returns and two writing returns; second story has no research return. All45 steps remain available by default.

Motion: short hover/pressed transitions, disclosure-icon rotation and recorded evidence/details reveals; section navigation scrolls rather than simulating execution. Arrows are static. Reduced motion removes transitions/animation and smooth scrolling. Loading placeholders are static and explicitly load a recorded sample. Fonts/palette unchanged; no new dependency.

Evidence:

- 43 Django regressions, system/migration checks, six upgrade and four tooling tests pass. Next build/typecheck, ratings/editorial and existing JSON→TypeScript contract checks pass.
- New `node web/tests/reasoning-trace.cjs` passes exact-sample and TEST negative cases: cross-event adjacency, isolated iteration2, missing/intervening stages and non-increasing iteration cannot fabricate returns. Included in branch CI.
- Original real HTTP/browser boundary passes legacy auth/CSRF/registration/preferences/staff/routes, analysis, corrections/rollback and error states. Extended reasoning HTTP/browser boundary passes both articles, **every article claim link and focus**, all45 steps, stage/loop/event filters, focused keyboard loop actions, source drilldowns and unchanged original hrefs, exact cohort pairs, four rating modes, empty/partial/error/retry/XSS/missing-trace cases. No browser interception in the reasoning path.
- Final 1440/768/390px screenshot captures and actual visual inspection cover reading, loops, verdicts and cohorts; no overflow. A rotated disclosure icon stretching long open claims was caught and fixed; explicit icon dimensions preserve mobile/tablet widths. Filter checks now wait for committed DOM state instead of timing React updates. Reduced-motion styles and persistent visible DEMO label asserted.
- Interactive `node web/tests/boundary.cjs --reasoning --serve` verified with isolated local auth, mode600 test credentials, actual45-step API/UI and ordinary feed pending; no production account/configuration is read. Existing setup/build instructions remain in the canonical handoff.
- Doctor15PASS/0FAIL/1BLOCKED/1NOT_TESTED; verify19PASS/0FAIL/14BLOCKED/1NOT_TESTED, no inference. Registry/provider credentials and local Zetaris headroom remain blockers; no sponsor execution claimed.

Screenshots outside Git: `~/.local/share/quorum/portal-screenshots/ux/`. Before: `before-DEMO-{story,timeline,cohorts}-{1440,768,390}.png` and `before-DEMO-evidence-1440.png`. Final: `after-DEMO-{story,timeline,evidence,disagreement,cohorts}-{1440,768,390}.png`, plus `after-DEMO-recorded-decisions-1440.png`. The latter shows an actual recorded critique rejection, rewrite and approval for the first story. These are visual evidence, not real news or genuine provenance. Original source hrefs are preserved; fictional external pages are not asserted to return HTTP200. No full WCAG audit claimed.

**Production unchanged**, release `20261023-web-portals-09f5325`; eight accounts, auth DB/config, services, credentials and publisher untouched. No canonical contract/data model/transport change. Real integration still BLOCKED on one genuine result and original IDs/hash/Unicode offsets/achieved access/wire/review/freshness/correction metadata; see the existing [handoff](PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview). This milestone does not advance those integration gates.

Hosted [CI39900552412](https://github.com/rcc00n/Quorum/actions/runs/39900552412) **succeeded** on implementation `4eb44109ef22f0d02bec66a002344ca27fd2e70d`, including the new recorded-loop negative-case checks. The handoff commit changes documentation only. PR remains draft; production is untouched.

## Current reasoning envelope and web documentation audit

Owner Vadim; branch `feature/web-portals`; implementation `67b4cf7f8a1c41b2ebc27b41a519b840d43e1ee1`; PR #1 draft. Reasoning read-only pin `6ea82434d0f06cefb51f5536732ceac68e9780ef`; collector `18fb009b4b36e995e765563203edbf742475a20b`; master `c3cc5ac4a65855769ab48e36a1d59d5cc1ae261d`. Fixture hash manifest: [fixture README](../backend/portal/fixtures/reasoning-demo/README.md).

| Exact canonical sample | Parser / authenticated Django / TS / Next HTTP browser | Stories / trace | Honesty guarantees |
| --- | --- | --- | --- |
| snapshot.sample.json | PASS | 2 / 45 | FICTIONAL, published_at null, preview unpublished |
| snapshot.empty-day.sample.json | PASS | 0 / 29 | Completed fictional quiet selection, three roundup items; not a missing/pending run |
| snapshot.partial.sample.json | PASS | 2 / 45 | Structured frame failures, framing unavailable, recorded coverage counts retained |

Regression evidence: **48 Django tests pass** (38 original +10 reasoning), system check and migration drift clean; six upgrade and four tooling tests pass; Next production build/typecheck and ratings/editorial/recorded-loop/JSON→actual TypeScript checks pass. Strict internal `portal_snapshot validate` passes the TEST proposal without publication; all three raw reasoning samples are deliberately rejected by that production schema. New tests cover invalid/missing timestamps, publication-before-generation, expired hint, 23/25-hour DST windows, unknown/unsafe error shapes/references and raw-message redaction. Self-declared published_at or fictional:false never activates publication.

Both real HTTP/browser suites pass: existing auth/CSRF/staff/routes/preferences plus immutable store/corrections/rollback; new reasoning suite renders all three exact envelopes, both articles/claim links/review verdicts/cohorts/roundup and all recorded steps, keyboard/reduced-motion/1440/768/390 layouts and hostile/error/missing-state cases. Screenshot capture now uses actual navigation and settled responsive layout, avoiding a race with prior smooth claim-anchor scrolling; assertions retained. Failure diagnostics print only test file/line locations, never candidate values or credentials. Interactive `--reasoning --serve` was started and stopped, local authenticated API/reading navigation inspected, and owned temporary runtime removed.

Actual screenshots outside Git: `~/.local/share/quorum/portal-screenshots/reasoning-reading-{1440,390}.png` and `ux/after-DEMO-{story,timeline,evidence,disagreement,cohorts}-{1440,768,390}.png`. Desktop metadata/article and mobile evidence were visually inspected; no redesign or full WCAG audit claimed. All data remains FICTIONAL.

Documentation audit and canonical ownership:

| Audited document(s) | Outcome |
| --- | --- |
| Local + master AGENTS.md, local/master DECISIONS.md | Existing team coordination and decision history preserved; module compatibility decision recorded in backend README; no new master rule installed |
| docs/ARCHITECTURE.md vs latest reasoning §8/publisher/state/corpus/fetcher | Branch-local architecture is an older copy; integration guide pins latest owner branch instead of editing a competing specification |
| docs/PORTAL_INTEGRATION.md | Consolidated obsolete review sections into current architecture/API/model/mapping/provenance/status/security/real-acceptance guide; exact missing export fields and topic mismatch retained; supplied dates/DST/QUORUM_COLLECT/shared-extractor preference no longer called missing |
| docs/TEAM_HANDOFF.md + root README | Discoverable Start Here, owner responsibilities, required agent read list, bidirectional change notification and explicit pending acknowledgement |
| backend/README.md, web/README.md | Setup/API/roles and current consumer decision preserved; preview endpoint added; testing commands link canonical verification; Next dev binds loopback |
| docs/SNAPSHOT_PROPOSAL.md | Strict proposal unchanged; confirmed offset semantics and superseded agreement checklist clarified through current handoff link |
| docs/IMPLEMENTATION_STATUS.md, docs/RELEASE_CHECKLIST.md | Current feature/test/dependency/production states explicit; historical sections labelled, no real integration gates closed |
| deploy/README.md + deploy/STATUS.md | Existing release evidence retained; deployment owner/restrictions/backups/rollback documented; misleading first-install-as-update example removed; status evidence not rewritten or re-verified against VPS |
| docs/PORTAL_VERIFICATION.md | One current reproducible command/config-name index plus dated evidence; changed relative links, staged paths/diff/sizes and secret-pattern index checks pass |

Doctor:15PASS/0FAIL/1BLOCKED/1NOT_TESTED; verify:19PASS/0FAIL/14BLOCKED/1NOT_TESTED, no inference. Actual WSL2 confirmed. Local Zetaris headroom/registry/runtime prerequisites and absent model route remain blockers; optional Docker Desktop integration is not a required gate. This milestone makes no external sponsor or production claims.

**Production untouched**, known release `20261023-web-portals-09f5325`; all eight accounts, DB/preferences/configuration/services remain unaccessed. Production validator/publisher/store and deployment code unchanged. Model/corpus declarations are supplied but no genuine result is established. Next: receive one actual complete public-safe reasoning result with collector evidence binding, validate locally, resolve registry/revision/bridge/transport decisions in Issue #2 before any activation.

Hosted [CI39903475716](https://github.com/rcc00n/Quorum/actions/runs/39903475716) **succeeded** on `1d27894026616f7d5f4d8d7f7c092dd0258278e2`, covering implementation `67b4cf7` and consolidated docs. Final evidence follow-up is documentation-only. [Exact team-wide announcement](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6357796090) tags @Sor1na, @AnastasiaShkirpan and @rcc00n, requests instruction of active agents and explicit acknowledgement. Latest observed replies contain no acknowledgement from either teammate; adoption remains pending. No stronger master rule or bot was installed.

## Local collected-corpus and updated contract acceptance

FULL-REAL-01 evidence is outside Git in `~/.local/share/quorum/experiments/full-real-integration-20261023/REPORT.md` and `WEB-ACCEPTANCE.json`. Current consumer retains optional upstream 0224ca6 quote identities/bindings, third reviewer, summary source, by-headline and roundup-origin declarations, with strict structural checks and explicit lack of independent source-text verification. Fixture labels remain; producer-declared collected inputs stay unpublished, and stand-ins explicitly mean no AI verification. No source prose or producer snapshot is rewritten.

52 Django tests, four tooling tests, Next build/typecheck and static contract/ratings/editorial/trace checks pass. Local HTTP/browser acceptance passes the original auth/admin/store/rollback flow, original reasoning fixture suite, latest main fixture and real-corpus stand-in snapshot through actual Django/Next/TypeScript at 1440/768/390px. The external acceptance harness also checks widths when the producer supplies zero featured stories. No API interception or production account is used. These browser results do not establish a completed live model graph; that execution has no final snapshot after its interop failure.

Use the browser variables above with `node web/tests/boundary.cjs --reasoning --reasoning-file <original-file>` and optional `QUORUM_REASONING_EXPECTED_SHA256`. Do not replace canonical fixtures, turn an aborted checkpoint into a completed producer snapshot, or activate publication. The actual latest main fixture exported from 0224ca6 hashes `68ed0b449bdaedee01435ee702b8d454496b6d9e286543ecbc7b9976695c642b`; all three original new files parse. Changes are local; no fresh hosted CI is claimed.

## Genuine source catalog acceptance (local only)

`deploy/export-catalog.py <reviewed-collection-SHA> <private-catalog.json>` retains source IDs, normalized ratings, provider labels/URLs, registry check date, audience attribution and nullable reporting date. No reporting month is inferred from the check date. Catalog data is definition/provenance, not collection health or an operational news feed. The unchanged reasoning object remains available alongside the catalog-enriched portal projection. Exact evidence source IDs take precedence over unique normalized hostname matching; ambiguous identities fail and unmatched sources stay unrated.

After the external build, run `QUORUM_TEST_CATALOG_FILE=<private-catalog.json> node web/tests/boundary.cjs --reasoning --catalog` with the documented browser/build variables. This creates disposable local auth/services, checks all source metadata over real HTTP and all four rating modes/nulls/attribution at1440/768/390px, and captures a local auth/navigation/real-registry video. The separate original story example remains explicitly FICTIONAL; no real graph output is fabricated. Video requires the Playwright-version FFmpeg in an external runtime; production is never used.

The later genuine snapshot uses the existing --reasoning-file path plus the same optional catalog, full expected SHA and owner sidecar procedure. Publisher remains off. The four source-rating modes calculate per-source position; producer coverage denominators/registry cohorts are retained, not recomputed from the whole registry.

## Genuine provisional v3 — local presentation acceptance, 2026-10-24

Owner Vadim / Codex; isolated web worktree based on preserved local `8cc9ed1`, remote web remains `fd3101e`. Feature IDs: **WEB-GENUINE-V3**, **WEB-ROUNDUP-CHECK**, **WEB-INTEGRATION-CI**. No merge, push, deployment, publication or provider inference.

The two original privately received files match the owner-published SHA-256 values exactly:

- Snapshot: `c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30` (129366 bytes).
- Sidecar: `1afba4c0eb7934139d0428f15f55db4d0683bf73d6a0da7edb08992aa5785775`.

**TESTED — genuine local presentation:** authenticated Django → API → actual TypeScript contract → Next → Chromium preserves all 28 roundup items, zero stories, 264 trace records and 63 redacted partial errors. Source links and each roundup event's trace filter are checked against the unchanged original. Desktop/tablet/mobile and reduced motion are exercised; zero-story editions now receive mobile checks too. Provisional capture `2026-10-24T03:53Z` is displayed from the hash-bound sidecar. A producer `published_at` timestamp is explicitly unverified; the preview remains unpublished, and the ordinary feed remains pending. The 40-source catalog/four-mode work from `8cc9ed1` is preserved.

Actual incompatibilities repaired: an exact-original-hash exception retains the historical v3 ledger's 61 transport errors plus two invalid replies (63 total); all other ledger consistency checks stay strict. External acceptance now expects the existing public-safe error redaction and producer-set publication timestamp. Counted expandable diagnostics retain every partial error without pushing the reading journey below 63 messages. The optional sidecar projects only provisional/capture/hash metadata after edition/run/status/window/hash binding; private paths and logs are never exported.

**TESTED — verification safeguard:** latest reasoning `3d89448` skips blind checks when an event cannot reach the bar, but `roundup.status_label` can still emit `confirmed`. The web preserves producer labels and explicitly shows an event-scoped skipped-check notice on list and detail. Missing claims or absent trace never establish independent verification. A separate explicit TEST derivative verifies the skipped case over real authenticated HTTP; it is not genuine-result evidence. No upstream branch, grouping, threshold or verification policy was changed.

**BLOCKED — full execution/corpus attestation:** the original sidecar declares config SHA `5228bf2d354bd56cadbd36705ebec81b8714072ec62df4e5bc4feee14f1aabb9`; producer `c1b37f9f743a609b45087cba9c7890c4414f0b79` has `reasoning/config/reasoning.toml` SHA `cb8ede9df15edba7deeeb783589c4caf12ceab01f3214a17ce2e2566a5aad630`. Common LF/CRLF/BOM/final-newline representations do not explain it. The existing private full-acceptance tool correctly stops on this mismatch. Producer Yelysei must reconcile the exact execution config and provide original ledger/manifest verification evidence; those private execution artifacts were not present locally. The sidecar declares 66 current rows (23 superseded; 43 eligible), 65 history rows, 131 total, and the original dump digest; these are declarations, not independently recomputed row manifests. No replacement corpus or inference run is requested.

**IMPLEMENTED — integration CI:** web regressions now target integration pushes and PRs into integration/master, including reasoning/collector paths; hosted execution remains unverified until an authorized push. Read-only merge-tree analysis found reasoning/collection conflicts in `.env.example` and `docs/DECISIONS.md`, and reasoning/web conflicts in `.gitignore` and `docs/DECISIONS.md`. Shared README/environment content also overlaps and needs review. No application-code path overlaps between the three owners were found. Keep every owner's decision history and credentials outside Git.

Validation: 21 focused Django preview/catalog tests, Next production build/typecheck, rating/trace checks, current three upstream samples, genuine original HTTP/browser acceptance and the canonical fictional compatibility browser suite. Routine doctor: 15 PASS / 0 FAIL / 1 BLOCKED / 1 NOT_TESTED. Routine verify: 30 PASS / 1 FAIL / 2 BLOCKED / 1 NOT_TESTED; authenticated sample SQL returned HTTP 400, startup headroom was below the safety gate, and Meterless model configuration was absent. The official bundle verifier passed. No service changes or inference attempted; routine diagnostics do not certify sponsor compliance.

Local demo: dashboard and topic source registry → explicitly unpublished `/preview/reasoning` → Also today → original source link → event-scoped Agent timeline → source registry/four ratings modes. There is no genuine exported story or claim-level evidence in this artifact; do not claim an Evidence Explorer or independently resolved dispute demonstration from v3. Partial/provisional qualifications stay visible. Nightshift→NVIDIA, owner-graph H-MEM persistence/recall/re-verification/conformance, secure production bridge, combined CI and backup/rollback/release review remain separate gates.

Reproduce with the existing `boundary.cjs --reasoning --reasoning-file <original-private-file>` and `QUORUM_REASONING_EXPECTED_SHA256`, `QUORUM_TEST_REASONING_SIDECAR`, external build/catalog/browser paths from the local environment. `--reasoning --roundup-checks` exercises the explicit TEST skipped-check derivative. `--serve` opens a disposable unpublished preview and prints a private local account-file path. Never commit the input, sidecar, screenshots, runtime accounts or execution logs.

## Genuine integration feature branch — 2026-10-24

Owner Vadim / Codex; branch `feature/web-genuine-integration`, based on clean `1317031` and preserving `fd3101e → 8cc9ed1 → 1317031`. Workstream **WEB-GENUINE-SAFETY** adds strict sidecar JSON/type/size/chronology checks, exact historical-ledger negative tests and production-validator isolation, persistent known-provisional labelling without a sidecar, and document/source consistency across the article/official ID namespaces. The new read-only acceptance command is documented in [backend/README.md](../backend/README.md); the unchanged original is compatible for presentation but still returns `producer_config_mismatch`. Full execution/corpus attestation remains BLOCKED on Yelysei's genuine evidence.

**WEB-ROUNDUP-CHECK — TESTED:** whitespace/case in a recorded skip cannot suppress the warning; trace filters cannot remove it. Keyboard investigation links retain edition/version and open an event-scoped trace; roundup entries correctly say “This event’s steps”. Mobile links have a separate target from source evidence. Source verdicts remain producer-attributed; no claim or article was synthesized.

**Local regression evidence:** 70 Django tests pass with both private-original tests enabled; system and migration-drift checks pass. Ten deploy/export/build-integrity/rollback tests and four tooling tests pass. Production Next build/typecheck, ratings/editorial/trace checks, current TypeScript contracts, newest reasoning main/empty/partial samples, and all three actual HTTP/browser boundaries pass: original portal/auth/publication/rollback, canonical fictional reasoning, and the original genuine v3 with 28 roundup items/zero stories/264 trace records/63 safe errors. The focused skipped-check browser case passes separately. Desktop/mobile screenshots were inspected outside Git. Latest collector registry `8f126c5` still has 40 sources and unchanged definitions; all four modes are preserved.

**WEB-RELEASE-INTEGRITY — TESTED locally:** a successful source-bound build receipt is required before packaging; stale/incomplete builds and changed sources are rejected. Packaging exports tracked portal/deploy files only and rejects private runtime paths. Existing upgrade backup/rollback tests pass. No production package was deployed, no service changed and no publication was enabled. **WEB-INTEGRATION-CI — IMPLEMENTED:** feature-web/integration/PR triggers now run isolated Chromium auth/reasoning/skipped-check tests; hosted results must be verified separately after push.

Routine diagnostics: doctor 15 PASS / 0 FAIL / 1 BLOCKED / 1 NOT_TESTED; verify 31 PASS / 0 FAIL / 2 BLOCKED / 1 NOT_TESTED. Actual bundled sample SQL passed this session; startup headroom and missing Meterless model configuration remain blockers. No inference requested. Read-only merge-tree conflicts remain `.env.example` + `docs/DECISIONS.md` for reasoning/collection, `.gitignore` + `docs/DECISIONS.md` for reasoning/web; no owner application paths overlap. Integration remains reasoning → collection → web, followed by combined verification/review. Config attestation, sponsor execution/H-MEM, secure production bridge, genuine exported claim evidence/story and final release gates remain open.

## Combined web integration — code checkpoint 9421cc8

Owner: Vadim / Codex. WEB-INTEGRATION-03 is INTEGRATED for the combined code and
local snapshot handoff; production publishing and full sponsor acceptance remain BLOCKED.
PR #5 merged with two-parent commit `9421cc831d4a72e3dc8c08d5351e0e7c9dc19f7e`.
Its tree equals tested web HEAD `1d72e451a706c4475c34e641c703e2661994ecb8` exactly.
The web branch merged reasoning+collection `b1d9ee9` through `b86e672`; all decision
rows, environment blocks and owner ancestry survived. Master and existing worktrees
were preserved; no squash, force-push, inference, production deployment or publisher activation.

### Verification and limits

- Reasoning: 402 PASS with Python socket connections blocked. The existing journal
  test requires a synthetic route (`http://127.0.0.1:1`, TEST key), even though it stubs
  graph execution. PR #9 removes that credential dependency and adapts the requested
  public-failure privacy amendments to current reasoning; its 420 tests pass without
  model credentials. Owner review remains required; H-MEM hooks are excluded.
- Django: 75 PASS with all three private-original tests enabled (v3 and v4).
  System check and migration-drift checks pass. Hosted CI skips private originals.
- Deployment: 12 PASS; tooling: 8 PASS. Temporary filesystem rollback tests stub
  service commands; they do not establish target-host restore/rollback acceptance.
- Next production build, TypeScript, ratings/null/threshold/link checks, editorial
  guards, trace isolation/skipped-check logic and projected API TypeScript contracts PASS.
- Current collection CSV/provenance/wire/outlet contracts PASS. All three canonical
  `docs/examples` snapshots and a newly generated fictional graph snapshot pass the
  actual portal parser. Stand-ins do not establish real inference integration.
- Actual isolated HTTP/Chromium suites PASS: existing auth/CSRF/roles/routes and
  snapshot correction/rollback; canonical fictional main/empty/partial/retry/XSS;
  skipped-check attribution and keyboard focus; unchanged genuine v3 and genuine v4.
  Desktop/tablet/mobile widths 1440/768/390; v4 screenshots inspected.
- Genuine v4: exact original SHA `ef231a4f0797c1128869ed5bd69d4d2869771766f634e754aa02dbf375756d79`,
  1 story, 26 roundup, 235 traces, 12 claims. Historical score 6 is retained with an
  explicit impact hold; rejected reviewer proposals are distinguished from final verdicts.
  Native acceptance returns compatible true, metadata/execution/source-text verification
  and publication false; issues `producer_config_hash_incomplete` and
  `impact_score_review_required`. Original evidence is unchanged.
- Fresh read-only extraction of the hash-matching closed corpus dump: 61/61 DocRef
  identities/URLs, 12/12 level-2 Unicode quote/hash bindings, no superseded evidence;
  86 rows = 48 active + 38 folded; current 49/18/1 official, earlier 76+1.
  Document 141 remains the known collector/quote hash difference. The 49 level-1
  evidence rows were not independently re-fetched. No ledger/journal execution proof.
- Actual clean package: 2663 entries, no links/credentials/private originals/runtime
  database; SHA `6cb9a27d0ef52c721422258d9a53e9b9af295c7b506fa246c41dfbfa8ec591e0`.
  Actual temporary SQLite backup and independent restore preserve integrity and the
  TEST account. The actual packaged Django and standalone Next also start on fresh
  loopback ports; after restoring the disposable auth database, CSRF login succeeds
  and the authenticated feed correctly stays pending with publication disabled.
  This local package is not a production release.
- Routine diagnostics: doctor 15 PASS / 0 FAIL / 1 BLOCKED / 1 NOT_TESTED; verify
  31 PASS / 0 FAIL / 2 BLOCKED / 1 NOT_TESTED. Real Zetaris SQL `SELECT 1`, bundled
  dataset rows and the official bundle verifier PASS. Startup headroom and missing
  Meterless model route remain blocked. Official reference H-MEM smoke (10 tests)
  and persistence/state smoke pass; owner-graph adoption/conformance remains blocked.
- Hosted code-head checks: [push 40166062182](https://github.com/rcc00n/Quorum/actions/runs/40166062182)
  and [PR 40166064848](https://github.com/rcc00n/Quorum/actions/runs/40166064848)
  SUCCESS, both portal/Chromium and combined-python jobs. The combined job uses
  Python 3.11 with sockets blocked; portal retains production-compatible Python 3.10.

Private logs, reports, database rehearsals and screenshots remain outside Git under
`~/.local/share/quorum/experiments/web-final-integration/`. Pending gates: reasoning
owner review of PR #9, genuine execution/config/ledger/journal reconciliation,
historical impact disposition, Meterless → Nemotron proof, owner H-MEM decisions,
approved production bridge and target-host release/security/restore acceptance.
The next canonical paid run belongs to the reasoning owner and needs separate spend
agreement. Existing collection work and provenance review are not requested again.
