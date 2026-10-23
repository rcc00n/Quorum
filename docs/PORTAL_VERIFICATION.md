# Portal proposal verification — 2026-10-22 local / 2026-10-23 UTC

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
