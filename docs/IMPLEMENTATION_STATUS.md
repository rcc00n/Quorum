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
| WEB-EVIDENCE | Structured Evidence Explorer | TESTED | DEMO browser + validator tests; code shipped; real analysis blocked | Reasoning contract/real evidence BLOCKED |
| WEB-COMPARISON | Source framing comparison | TESTED | DEMO browser comparison/keyboard tests; code shipped; real analysis blocked | Grounded frames/denominators BLOCKED |
| WEB-TIMELINE | Public-safe investigation timeline | TESTED | DEMO browser trace/missing-state tests; code shipped; real analysis blocked | Genuine processing trace BLOCKED |
| WEB-ADAPTER | Catalog + versioned snapshot projection | TESTED | Catalog/store/adapter + authenticated projection tests; code shipped; real analysis blocked | Upstream mapping agreement |
| WEB-VALIDATE | Strict runtime snapshot validation | TESTED | Strict schema, hostile/null/reference/date tests; code shipped; real analysis blocked | Proposal review |
| WEB-PUBLISH | Atomic immutable local publication/rollback | TESTED | Atomic failure, immutable/hash/fallback/rollback tests; code shipped; real analysis blocked | Transport authorization; production disabled |
| WEB-FRESHNESS | Pending/partial/stale/error display | TESTED | Expiry and DEMO retry/stale/fallback tests; code shipped; real analysis blocked | Agreed expiry policy |
| WEB-REVISION | Immutable revisions/corrections/deep links | TESTED | Revision/correction/rollback tests; code shipped; real analysis blocked | Stable upstream IDs |
| WEB-CONTROL | Branded Django Control | DEPLOYED | Staff browser/API tests | Source/analysis read-only |
| WEB-TELEMETRY | Real publication metadata in Control | TESTED | File audit + authenticated Control metadata test; code shipped; real analysis blocked | No upstream health assumed |
| WEB-VPS | Isolated website deployment | DEPLOYED | Target-host HTTPS + loopback verification | No processing on VPS |
| WEB-MOBILE | Responsive navigation/layout | TESTED | Existing desktop/mobile captures | New components passed 1440/768/390px |
| WEB-A11Y | Labels, keyboard, reduced motion | TESTED | Existing controls checked | No full WCAG audit claimed |
| WEB-AUTH-TEST | Authentication regression suite | TESTED | 29 Django regressions (13 baseline + 16 snapshot/API tests) | Retest on changes |
| WEB-INTEGRATION | Real collection→Zetaris→reasoning→portal | BLOCKED | No real run claimed | Anastasia/Yelysei/auth/transport |
| WEB-SMOKE | Production smoke and rollback evidence | DEPLOYED | Existing `deploy/STATUS.md` evidence | Recheck per release |

Current local release evidence and exact commands: [verification record](PORTAL_VERIFICATION.md). Rich analysis remains TESTED against labelled fixtures, not INTEGRATED with real upstream results. Code is now shipped in `20261023-web-portals-09f5325` (`09f5325`); HTTPS/authenticated pending states and new UI assets are verified. The previous milestone left `20261022-web-portals-r2` unchanged; it is now the rollback target. See the current release evidence below. No production publisher or machine credential may be enabled without cross-team approval. Product changes in `origin/yelysei/agents@49e6d1f` (impact bar/articles/roundup) are a reconciliation dependency, not silently merged decisions.


## Next integration-readiness milestone (feature/web-portals)

| Feature ID | Status | Location / evidence | Deployment / dependency |
| --- | --- | --- | --- |
| WEB-COMPAT | DEPLOYED | `portal_snapshot validate`; safe JSON diagnostic report, zero DB queries and unchanged head/audit tests | Read-only CLI verified on production Python 3.10; no publication/schema ownership |
| WEB-BOUNDARY | TESTED | Real isolated HTTP API → TypeScript → browser, all claim states, disagreement, corrections/rollback/deep links and auth/admin regressions | DEMO/TEST only; real upstream result still BLOCKED |
| WEB-ERRORS | DEPLOYED | Configured catalog failure and processing failure without usable events remain ERROR; expired editions stay STALE | Code shipped; pending production state verified; failure cases covered locally |
| WEB-UPGRADE | DEPLOYED | Six isolated safety tests incl. failed-health rollback; private backup, additive-only pins, migration/publication gates | Guarded production upgrade passed; rollback target r2 |
| WEB-CI | TESTED | Branch-only public Ubuntu job; Python 3.10/backend/upgrade/fixture/Next/TypeScript checks | Hosted run 39887513802 passed on code commit 09f5325 |

Owners: Vadim for all rows; branch `feature/web-portals`; PR #1. Exact implementation/release commit and final deployment evidence are recorded in the milestone section of PORTAL_VERIFICATION.md after the guarded release. Existing capabilities above remain preserved; no upstream integration item is closed.

Release evidence: code commit `09f5325c78fe71677c46a83f952c04b602e6fc7b`, branch `feature/web-portals`, PR #1. [Hosted CI](https://github.com/rcc00n/Quorum/actions/runs/39887513802), 36 Django + six upgrade tests and real local HTTP/browser boundary pass. Website-only release deployed and verified; eight accounts/password hashes/roles and preference rows preserved (normal login timestamps changed). Snapshot publication, transport and machine credentials remain disabled/unconfigured. Genuine processing integration remains BLOCKED.

Concurrent upstream update: reasoning `f3a32ec` now documents an output proposal; matrix and local rejection of its illustrative JSON are recorded in PORTAL_INTEGRATION.md. Real-result integration remains BLOCKED. Master concurrently advanced to `c3cc5ac`; PR #1 conflicts. No merge/rebase/cherry-pick is authorized or attempted. Existing deployed code remains `09f5325`.

## Approved product reconciliation — feature/web-portals only

Owner Vadim; merge `05e87b4`, implementation in PR #1. Production remains `20261023-web-portals-09f5325`, unchanged in this milestone.

| Feature ID | Status | Evidence / remaining dependency |
| --- | --- | --- |
| WEB-RECONCILE | TESTED | Manual README/DECISIONS conflict resolution preserves team and portal/auth history; ARCHITECTURE imported from approved master; no history rewrite |
| WEB-ARTICLE | TESTED | Optional claim-linked prose ahead of analysis appendices; context/attribution guards and responsive DEMO browser checks. Needs real approved editorial mapping; not deployed |
| WEB-ROUNDUP | TESTED | Also today groups/status/source links, optional edition model, no synthesized rankings; cap ten per topic. Needs real reasoning output; not deployed |
| WEB-QUIET | TESTED | Explicit completed/available empty selection only; pending/error/partial/stale are distinct in unit/browser cases. No quiet-day inference from missing data |
| WEB-PHOTO | TESTED | Optional metadata/host/rights guards, attribution and failure handling; no actual photo used or rights independently verified. Upstream license review still required |
| WEB-IDENTITY | BLOCKED | Approved team red/blue/rounded direction conflicts with earlier explicit neutral palette instruction; only this visual-identity change is held |

38 Django tests, six upgrade tests, Next build/typecheck, four tooling checks, contract/ratings/editorial tests and the HTTP/browser boundary pass locally. See PR #1 for exact implementation commit and hosted CI evidence. No genuine processing integration is claimed. Earlier merge-conflict blocker is superseded by the newly authorized merge; no production account/configuration, transport or publisher changed.
