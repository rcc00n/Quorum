# Quorum user portal

Next.js App Router + TypeScript, locally packaged Inter, system Georgia editorial headlines, Lucide icons and plain responsive CSS. No external font request or generated news. Production starts with honest empty states.

## Run

```bash
# From repository root: builds and installs dependencies outside this public repo
bash deploy/build-web.sh
cd ~/.local/share/quorum/portal-web-build
npm run dev -- --port 3017
```

Start Django on `127.0.0.1:8017` first (see [backend setup](../backend/README.md)). Development rewrites `/api/`, `/staff/` and `/staff-static/` to Django. Open `http://127.0.0.1:3017`. In production Nginx provides same-origin routing. `npm run build` and `npm run typecheck` run in the external build directory.

Routes: `/`, `/login`, `/register`, `/onboarding`, `/dashboard`, `/topics/[slug]`, `/events/[id]`, `/history`, `/settings`. Protected routes render no private data until Django verifies the session; every protected API request independently enforces authentication. A stale session receives a recoverable error. No credentials are stored in browser storage.

## Integration contract

The canonical cross-workstream handoff is [PORTAL_INTEGRATION.md](../docs/PORTAL_INTEGRATION.md): owner-specific read lists, current field inventory/examples, API behavior, validation gaps, secure transport proposals and real end-to-end acceptance. `lib/api.ts` remains the executable view-model definition; it is not an approved agent API. Architecture/formulas remain in [project decisions](../docs/DECISIONS.md).

`fixtures/demo.ts` is a fictional view-model test fixture, never imported by production pages or the live adapter. Browser tests explicitly label demo responses; screenshots of the shipped empty workspace show actual pending state.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Typed reasoning 1.0 reading page with paired evidence, cohort grid and recorded feedback loops; neutral identity retained | Make the canonical fictional sample inspectable without inventing scores, times or production results |
| 2026-10-22 | rcc00n / Codex | Optional reading-first article and edition/roundup presentation; explicit completed quiet-day guard; cap ten per topic, not a target | Adopt approved product flow while preserving legacy snapshots and all evidence appendices; production schema/mapping still awaits reasoning agreement |
| 2026-10-22 | rcc00n / Codex | Plain shared CSS, Inter from npm, Georgia fallback, Lucide; outside-repository build | Minimal dependency surface, reproducible fonts, no vendored dependencies in public checkout |
| 2026-10-22 | rcc00n / Codex | Neutral editorial layout; transient entrance/hover/loading transitions with reduced-motion support | Prioritize reading, accessible hierarchy and calm interaction |
| 2026-10-22 | rcc00n / Codex | Optional structured analysis with native disclosures, comparison and public-safe trace; retain legacy evidence arrays | Make evidence inspectable without fabricated metrics or requiring an approved upstream API prematurely |

Optional browser checks use externally installed Playwright/Chromium via `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH`. Run `node web/tests/browser.cjs` against the local portal, `node web/tests/demo.cjs` with `TYPESCRIPT_MODULE` pointing to the external TypeScript package, and `node web/tests/ratings.cjs` on Node 22.19+. `QUORUM_TEST_URL` overrides the test origin. The browser flow creates a temporary account; `QUORUM_SMOKE_ACCOUNT_FILE` records its exact username for cleanup. Demo tests intercept only browser requests and prominently label fictional content.

Snapshot implementation and unapproved transport: [portal-owned proposal](../docs/SNAPSHOT_PROPOSAL.md). Release gates: [checklist](../docs/RELEASE_CHECKLIST.md); workstream evidence: [inventory](../docs/IMPLEMENTATION_STATUS.md). No production snapshot publisher is enabled.


`web/tests/analysis.cjs` tests the rich UI against an externally projected DEMO snapshot (`QUORUM_ANALYSIS_FIXTURE`); this is not real integration. Exact fixture preparation and test evidence are in the release record.

Integration acceptance: `node web/tests/contract.cjs` checks a production-validated projection against the actual TypeScript model. `node web/tests/boundary.cjs` (with external Playwright/Chromium) starts isolated temporary Django/Next/proxy processes, publishes only a labelled TEST snapshot locally, authenticates a generated test account, checks actual API JSON/types/UI and exercises corrections, dateless links, rollback and three widths. It never points at production or uses provisioned account passwords. Existing `analysis.cjs` retains deterministic hostile-service/stale/missing-state UI cases.


`lib/editorial.ts` holds optional presentation-only types and guards, not the reasoning API. Article prose requires resolved claims; photo rendering additionally requires a confirmed-rights flag, approved source hosts and complete credit/license metadata. No photo is synthesized or fetched in tests. The backend schema does not yet emit these fields. `node web/tests/editorial.cjs` and the extended `analysis.cjs` cover the additions; the real local `boundary.cjs` still exercises the original auth/admin/API and rich UI suite. Palette/font reconciliation is held per DECISIONS.md; no new design identity is chosen here.

Canonical reasoning 1.0 **FICTIONAL local preview** and exact sample pin: [integration handoff](../docs/PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview). Start with `node web/tests/boundary.cjs --reasoning --serve` after the external Next build; this isolates local test auth and keeps the production publisher unused. `--reasoning` without `--serve` runs the real HTTP/browser acceptance suite. Neither command accesses production credentials.
