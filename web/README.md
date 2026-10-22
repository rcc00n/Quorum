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

Canonical integration seam and current availability: [backend README](../backend/README.md#integration-boundary--pending-not-operational). `lib/api.ts` defines portal-only `Snapshot`, `Event`, `Evidence` and `Source` types. These await upstream agreement, rather than imposing an API on reasoning. Live adapter is pending; an optional, revision-labelled external team catalog enables topic selection and registry inspection today. Event IDs and narratives cannot be derived from collector documents in this workstream.

AllSides/MBFC/Ad Fontes values arrive normalized and nullable. Average uses only available values; unrated sources stay unrated. Spectrum thresholds/formulas: [project decisions](../docs/DECISIONS.md#spectrum-ratings-and-cohorts). No invented rating, audience, health status, or importance value is substituted. No cohort shares are claimed without complete denominators. The source list uses neutral colors throughout.

`fixtures/demo.ts` is a fictional view-model test fixture, never imported by production pages or the live adapter. Browser tests explicitly label demo responses; screenshots of the shipped empty workspace show actual pending state.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Plain shared CSS, Inter from npm, Georgia fallback, Lucide; outside-repository build | Minimal dependency surface, reproducible fonts, no vendored dependencies in public checkout |
| 2026-10-22 | rcc00n / Codex | Neutral editorial layout; transient entrance/hover/loading transitions with reduced-motion support | Prioritize reading, accessible hierarchy and calm interaction |

Optional browser checks use externally installed Playwright/Chromium via `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH`. Run `node web/tests/browser.cjs` against the local portal, `node web/tests/demo.cjs` with `TYPESCRIPT_MODULE` pointing to the external TypeScript package, and `node web/tests/ratings.cjs` on Node 22.19+. `QUORUM_TEST_URL` overrides the test origin. The browser flow creates a temporary account; `QUORUM_SMOKE_ACCOUNT_FILE` records its exact username for cleanup. Demo tests intercept only browser requests and prominently label fictional content.
