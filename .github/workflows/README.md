# Portal CI

Historical description (superseded by the combined integration checks below): `workflows/portal.yml` ran only for `feature/web-portals` pushes affecting the portal/deploy code (manual runs also require that branch). Python 3.10 matches production. It checks Django/security/validation tests, upgrade tests, fixture compatibility, TypeScript, Next build and ratings. No private credentials, external processing, browser downloads or model calls are required; no external integration success is claimed. Standard public-repository Linux runners are used; no paid service is enabled.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-27 | Anastasia / Claude Code (covering Vadim's items this week, Issue #2 6426106426) | This file moved from `.github/README.md` to `.github/workflows/README.md`; its content is unchanged. | GitHub renders `.github/README.md` on the repository's front page in place of the root `README.md`, so judges opening github.com/rcc00n/Quorum saw "Portal CI" instead of the project README (seen 2026-10-27 01:40Z). |
| 2026-10-23 | rcc00n / Codex | One branch-filtered, read-only-permissions Ubuntu CI job; no sponsor calls/browser suite | Protect the real supported Python/runtime contract with compact deterministic checks; browser HTTP boundary remains reproducible locally |

Reference: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [public runner billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Combined integration checks

The portal workflow covers web branches and integration pushes, plus PRs into integration/master. Paths include reasoning, collection, agent tools, diagnostics and canonical snapshot examples. The portal job checks Django, release safety, Next/TypeScript and authenticated Chromium. A separate Python 3.11 job runs reasoning pytest, collection registry/provenance contracts, diagnostics and a fresh fictional graph → snapshot → portal handoff with Python sockets blocked. Python 3.10 portal coverage remains intact. Private originals are skipped on hosted runners and tested locally; no model, live collection, sponsor or production acceptance is inferred.

2026-10-24 · rcc00n / Codex · Add a Python 3.11 combined job with blocked sockets beside the Python 3.10 portal job; exercise newly generated and canonical snapshots. Why: web-only green CI cannot establish compatibility with the integrated reasoning/collection tree. Supersedes the branch-only/no-browser CI scope above; that historical decision is retained.
