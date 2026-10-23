# Vadim — web implementation inventory

Canonical cross-team release status: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). Owner for this inventory: Vadim; branch: `feature/web-portals`; baseline: `f3d568a`; backend proposal: `6d70d1a`; UI revision: this PR / [PR #1](https://github.com/rcc00n/Quorum/pull/1). This is a module inventory, not a second cross-team tracker. Status meanings are in AGENTS.md. Baseline deployment evidence is in [deploy/STATUS.md](../deploy/STATUS.md); fixtures are never upstream integration evidence.

| Feature ID | Feature / implementation | Status | Test evidence / deployment | Dependencies |
| --- | --- | --- | --- | --- |
| WEB-LANDING | `/`, editorial landing; `web/app/page.tsx` | DEPLOYED | Prior desktop/mobile browser checks; HTTPS smoke | None |
| WEB-REGISTER | `/register`, Django UserCreationForm | DEPLOYED | Auth tests; prior live registration | Email flows deferred pending delivery |
| WEB-LOGIN | Login/logout/session expiry | DEPLOYED | Auth tests; production account flow evidence | None |
| WEB-SESSION | HttpOnly/Secure sessions, CSRF | DEPLOYED | CSRF/session tests; HTTPS cookies verified | Same-origin proxy |
| WEB-ROLES | Regular user permissions | DEPLOYED | Role tests and production staff denial | Preserve accounts |
| WEB-STAFF | Staff/superuser boundaries | DEPLOYED | Staff tests and production access verification | No privilege relaxation |
| WEB-ONBOARD | Topic onboarding | DEPLOYED | Browser topic selection | Catalog export; no scheduling sync |
| WEB-PREFS | Persistent topic preferences | DEPLOYED | Preference persistence tests | Synchronization with collectors undecided |
| WEB-DASH | Personalized dashboard shell | DEPLOYED | Browser checks | Live events BLOCKED |
| WEB-FEED | Authenticated `/api/feed/` | TESTED | Catalog/pending API tests; endpoint deployed | Actual processing result/contract BLOCKED |
| WEB-TOPIC | Topic/day detail | TESTED | Browser route/empty states; shell deployed | Live edition BLOCKED |
| WEB-EVENT | Event analysis detail | TESTED | Labelled fixture/empty route; shell deployed | Live analysis BLOCKED |
| WEB-HISTORY | Date/topic digest history | TESTED | Browser empty states; shell deployed | Real digests BLOCKED |
| WEB-SETTINGS | Profile/password/topics/logout | DEPLOYED | Auth/API and browser tests | Email is unverified profile data |
| WEB-SPECTRUM | Four normalized rating modes | TESTED | Ratings/null/threshold tests; control deployed | Actual sourced ratings/audience pending |
| WEB-EVIDENCE | Structured Evidence Explorer | TESTED | DEMO browser + validator tests; not deployed | Reasoning contract/real evidence BLOCKED |
| WEB-COMPARISON | Source framing comparison | TESTED | DEMO browser comparison/keyboard tests; not deployed | Grounded frames/denominators BLOCKED |
| WEB-TIMELINE | Public-safe investigation timeline | TESTED | DEMO browser trace/missing-state tests; not deployed | Genuine processing trace BLOCKED |
| WEB-ADAPTER | Catalog + versioned snapshot projection | TESTED | Catalog/store/adapter + authenticated projection tests; not deployed | Upstream mapping agreement |
| WEB-VALIDATE | Strict runtime snapshot validation | TESTED | Strict schema, hostile/null/reference/date tests; not deployed | Proposal review |
| WEB-PUBLISH | Atomic immutable local publication/rollback | TESTED | Atomic failure, immutable/hash/fallback/rollback tests; not deployed | Transport authorization; production disabled |
| WEB-FRESHNESS | Pending/partial/stale/error display | TESTED | Expiry and DEMO retry/stale/fallback tests; not deployed | Agreed expiry policy |
| WEB-REVISION | Immutable revisions/corrections/deep links | TESTED | Revision/correction/rollback tests; not deployed | Stable upstream IDs |
| WEB-CONTROL | Branded Django Control | DEPLOYED | Staff browser/API tests | Source/analysis read-only |
| WEB-TELEMETRY | Real publication metadata in Control | TESTED | File audit + authenticated Control metadata test; not deployed | No upstream health assumed |
| WEB-VPS | Isolated website deployment | DEPLOYED | Target-host HTTPS + loopback verification | No processing on VPS |
| WEB-MOBILE | Responsive navigation/layout | TESTED | Existing desktop/mobile captures | New components passed 1440/768/390px |
| WEB-A11Y | Labels, keyboard, reduced motion | TESTED | Existing controls checked | No full WCAG audit claimed |
| WEB-AUTH-TEST | Authentication regression suite | TESTED | 29 Django regressions (13 baseline + 16 snapshot/API tests) | Retest on changes |
| WEB-INTEGRATION | Real collection→Zetaris→reasoning→portal | BLOCKED | No real run claimed | Anastasia/Yelysei/auth/transport |
| WEB-SMOKE | Production smoke and rollback evidence | DEPLOYED | Existing `deploy/STATUS.md` evidence | Recheck per release |

Current local release evidence and exact commands: [verification record](PORTAL_VERIFICATION.md). New snapshot/UI capabilities are TESTED, not INTEGRATED or DEPLOYED. Existing production release remains `20261022-web-portals-r2`; current read-only smoke reconfirmed HTTPS, service state and all eight account roles. No credentials were accessed, no database was mutated and no deployment occurred. No production publisher or machine credential may be enabled without cross-team approval. Product changes in `origin/yelysei/agents@49e6d1f` (impact bar/articles/roundup) are a reconciliation dependency, not silently merged decisions.


## Next integration-readiness milestone (feature/web-portals)

| Feature ID | Status | Location / evidence | Deployment / dependency |
| --- | --- | --- | --- |
| WEB-COMPAT | TESTED | `portal_snapshot validate`; safe JSON diagnostic report, zero DB queries and unchanged head/audit tests | Local tool; not publication or schema ownership |
| WEB-BOUNDARY | TESTED | Real isolated HTTP API → TypeScript → browser, all claim states, disagreement, corrections/rollback/deep links and auth/admin regressions | DEMO/TEST only; real upstream result still BLOCKED |
| WEB-ERRORS | TESTED | Configured catalog failure and processing failure without usable events remain ERROR; expired editions stay STALE | Included in candidate release |
| WEB-UPGRADE | TESTED | Six isolated safety tests incl. failed-health rollback; private backup, additive-only pins, migration/publication gates | Production application pending guarded preflight |
| WEB-CI | IMPLEMENTED | Branch-only public Ubuntu job; Python 3.10/backend/upgrade/fixture/Next/TypeScript checks | Hosted result recorded after push |

Owners: Vadim for all rows; branch `feature/web-portals`; PR #1. Exact implementation/release commit and final deployment evidence are recorded in the milestone section of PORTAL_VERIFICATION.md after the guarded release. Existing capabilities above remain preserved; no upstream integration item is closed.
