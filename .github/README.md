# Portal CI

`workflows/portal.yml` runs only for `feature/web-portals` pushes affecting the portal/deploy code (manual runs also require that branch). Python 3.10 matches production. It checks Django/security/validation tests, upgrade tests, fixture compatibility, TypeScript, Next build and ratings. No private credentials, external processing, browser downloads or model calls are required; no external integration success is claimed. Standard public-repository Linux runners are used; no paid service is enabled.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-23 | rcc00n / Codex | One branch-filtered, read-only-permissions Ubuntu CI job; no sponsor calls/browser suite | Protect the real supported Python/runtime contract with compact deterministic checks; browser HTTP boundary remains reproducible locally |

Reference: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [public runner billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
