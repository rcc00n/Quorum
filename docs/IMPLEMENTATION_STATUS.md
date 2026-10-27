# Vadim — web implementation inventory

Canonical cross-team release status: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). Owner for this inventory: Vadim; branch: `feature/web-portals`; baseline: `f3d568a`; backend proposal: `6d70d1a`; UI revision: this PR / [PR #1](https://github.com/rcc00n/Quorum/pull/1). This is a module inventory, not a second cross-team tracker. Status meanings are in AGENTS.md. Baseline deployment evidence is in [deploy/STATUS.md](../deploy/STATUS.md); fixtures are never upstream integration evidence.

**Current handoff:** [Start Here](TEAM_HANDOFF.md) and [current contract review](PORTAL_INTEGRATION.md). Sections below are chronological evidence: older “no sample”, missing timestamp and merge-conflict dependencies are superseded by later milestones. They do not describe today's contract. The latest production milestone is below; older tables remain historical evidence.

## Complete photo coverage — 27 October 2026 UTC

WEB-MEDIA-02 DEPLOYED: `20261027-photo-coverage-r2`, source `0499866`, normal #93/#95/#94.
All nine current and one historical story have reviewed photos; both low-quality orbital stills are
replaced by a sharp 1920px Starlink terminal photo. The landing example now has a credited/licensed,
explicitly illustrative file photograph with readable text on its existing band. Also today #85 is retained.
[Exact source/artifact, CI, actual public image/four-width, session and preservation evidence](reviews/2026-10-27-editorial-photos-release.md#complete-photo-coverage-and-quality-follow-up--web-media-02).
This supersedes the earlier two-unreviewed-photo limitation. No new model run or original-edition change.

## Reviewed lead-photo release — 27 October 2026 UTC

WEB-MEDIA-01 DEPLOYED: `20261027-editorial-photos-r2`, source `169b0fc`, normal #86–#89.
Seven exact-bound reviewed photos on current story cards/pages; four openly licensed/public-domain
assets with credits, factual file-image captions and source/licence links. Two ceasefire stories remain
without a reviewed photo. Original editions, reasoning, accounts and the existing design are preserved.
[Exact source/artifact, CI, genuine browser, rollback/reapply and preservation evidence](reviews/2026-10-27-editorial-photos-release.md).
Data/topic processing stays with the teammates; no new model run. Also today #85 remains a separate release.

## Source-spectrum polish release — 27 October 2026 UTC

WEB-SPECTRUM-POLISH-02 DEPLOYED: `20261027-spectrum-polish-r1`, source `f3e121e`, normal #52/#61/#63.
Registry labels, complete grouped ledger, phone sizing and explicit cohort shares preserve formulas/nulls.
[Exact source/artifact, review/CI, genuine public browser, session persistence, actual rollback/reapply and preservation evidence](reviews/2026-10-27-spectrum-polish-release.md).
Landing tint retained; active cabinet #62 and fresh-edition/sponsor/submission dependencies stay separate.

## Source-bar tint release — 27 October 2026 UTC

WEB-LANDING-TINT-01 DEPLOYED: `20261027-source-tints-r1`, source `b4f05f6`, normal PRs #59/#60.
[Exact source/artifact, CI, public browser, actual rollback/reapply and preservation evidence](reviews/2026-10-27-source-tints/README.md#production-evidence).
The cutoff/publication distinction is agreed with Anastasia for her active cabinet work; no parallel edits.
Spectrum polish #52 is now INTEGRATED after exact-head review/tests, with its guarded release still pending.

## Frontend refinement release — 27 October 2026 UTC

Latest frontend: `20261027-paperclip-r1`, source `b938a12`, code identical to release-master `41aa9d0`.
WEB-VISUAL-HIERARCHY-01, WEB-EDITION-NAV-01, WEB-AUTH-RETURN-01 and WEB-PAPERCLIP-POLISH-01 are DEPLOYED.
[Exact feature releases, CI, genuine public browser, preservation and actual rollback/reapply evidence](reviews/2026-10-27-frontend-refinement-release.md).
Each feature has a separate release/rollback point; #52 is separate. Earlier local-only entries below remain historical evidence.

## Production UX audit — 27 October 2026 UTC

Production UX audit follow-up: WEB-EDITION-NAV-01 / WEB-AUTH-RETURN-01, owner Vadim / Codex,
`feature/web-edition-navigation`, TESTED locally, not DEPLOYED. Date/topic URLs, contextual History,
calendar-day/recovery controls and bounded exact sign-in return preserve the existing design and content.
[Audit, prioritized gaps, checks and review captures](reviews/2026-10-27-production-ux.md).
Production observations and local fixture evidence are distinguished there; #52/#53 remain separate.

## Sources and motion release — 27 October 2026 UTC

Owner Vadim / Codex; branch `feature/web-spectrum-motion`; production `20261027-spectrum-r1`,
source `6f16bd7feda9a8e3c1c105ddd3510b2dce9d27fa`; merged PRs #44/#45.
[Exact release, CI, public browser and rollback evidence](../deploy/FRONTEND_RELEASE.md).

| Feature ID | State | Evidence / limits |
| --- | --- | --- |
| WEB-SPECTRUM-MOTION-01 | DEPLOYED | Actual registry geometry/four modes, source inspector, keyboard/depth/reduced motion; public HTTPS and three widths |
| WEB-SOURCES | DEPLOYED | Authenticated Sources navigation/route, exact 40-source ledger; 34 eligible plotted sources; anonymous redirect/API 401 |
| WEB-PAGE-MOTION | DEPLOYED | Landing/workspace entry and pointer depth, reduced motion and observer fallback; no full no-JS claim |
| WEB-UPGRADE / WEB-SESSION / WEB-PREFS | DEPLOYED | Actual r3 rollback/reapply, preserved accounts, restart session/preferences/feed persistence; 24 unrelated containers unchanged |

These UI states do not close the fresh 27-Oct processing/sponsor/submission gates.

## Live release — 27 October 2026 UTC

Production `20261027-live-r3`, source `63418421c1c0909dc0d7dfa1b451da3eed1bcc76`.
[Exact release/CI/browser/rollback evidence and owner dependencies](../deploy/LIVE_RELEASE.md).

| Feature ID | State | Evidence / limits |
| --- | --- | --- |
| RELEASE-ASSEMBLY-01 | INTEGRATED | Reviewed reasoning → collection → web stack, #22–#38 release dependencies merged; owner decisions retained |
| RELEASE-PROD-01 / WEB-VPS | DEPLOYED | Genuine public HTTPS browser, preserved accounts, service restart persistence and actual code/static rollback/reapply |
| EDITION-REAL-01 / WEB-FEED / WEB-TOPIC / WEB-EVENT | DEPLOYED | Accepted original 26-Oct immigration v1: 1 story, 19 roundup entries; signed-in only; provisional and needs review |
| WEB-EVIDENCE / WEB-TIMELINE / WEB-SPECTRUM | DEPLOYED | Original story and exact 174 trace decisions through API/browser; 9 claims/14 evidence rows, source URLs/reviews and four rating modes |
| WEB-CATALOG-RATINGS | DEPLOYED | Four approved demo topic IDs and 40 reviewed source definitions; fallback display labels documented |
| WEB-ROLES / WEB-SESSION / WEB-PREFS | DEPLOYED | Eight existing account logins/roles pass; all nine old accounts preserved; ordinary judge added privately; restart preserves judge session/four topic preferences |
| INFRA-SSH-01 | INTEGRATED, server configuration | Exact key fingerprint and root-equivalent sudo checked; Anastasia confirms holder login; account remains yelysei-deploy, Yelysei has no separate key |
| SPONSOR-CHAIN-01 | BLOCKED for full independent certification | Installed edition uses direct NVIDIA; fresh 27-Oct Nightshift/H-MEM recall originals and source/provider attestation remain owner dependencies |

## Combined integration checkpoint

Supersedes local-only/merge-pending descriptions below for this checkpoint; historical
milestones and production evidence remain retained. Owner Vadim, web branch
`feature/web-genuine-integration`, merged PR #5, integration `9421cc8`.
Exact checks and remaining evidence limits: [combined verification](PORTAL_VERIFICATION.md#combined-web-integration--code-checkpoint-9421cc8).

| Feature ID | Status | Evidence | Remaining dependency |
| --- | --- | --- | --- |
| WEB-INTEGRATION-03 | INTEGRATED, local snapshot/code boundary | Reasoning + collection + web merged preserving history; fresh fictional graph handoff and unchanged genuine v3/v4 authenticated browser acceptance | Production bridge/release and full execution/sponsor proof remain BLOCKED |
| WEB-GENUINE-V4 | TESTED, unpublished | 1 story / 26 roundup / 235 traces / 12 claims; exact-byte private originals, visible impact hold | Full config/ledger/journal provenance and owner impact disposition |
| WEB-INTEGRATION-CI | TESTED hosted | Both portal/Chromium and socket-blocked combined-python jobs passed for PR #5 | Recheck each new integration SHA |
| WEB-RELEASE-INTEGRITY | TESTED locally | Compiled-output receipt, actual package startup, disposable auth backup/restore/login; temporary-filesystem rollback | Target-host release/security/rollback acceptance |
| REASONING-PUBLIC-FAILURE-01 | TESTED; owner review pending | PR #9, 420 socket-blocked tests; requested type/status/lowercase/raw-error disclosures | Yelysei review; no H-MEM adoption |

| Feature ID | Feature / implementation | Status | Test evidence / deployment | Dependencies |
| --- | --- | --- | --- | --- |
| WEB-CATALOG-RATINGS | Provenance-preserving export, exact preview source join, real registry four modes and attributed audience | TESTED locally; not DEPLOYED | 58 Django tests, exporter/upgrade tests, build/TS and authenticated real-catalog browser acceptance at three widths | Final genuine model snapshot; production bridge/release approval |
| WEB-NVIDIA-ACCEPT | Optional model-ledger/context compatibility and original real-model FICTIONAL snapshot through local Django/Next preview | TESTED locally; not DEPLOYED or real-news integration | 50 Django tests; build/typecheck; unchanged snapshot/API/TypeScript/DOM equality, 12 published claims/77 evidence rows/39 steps/3 roundup items, three widths; see PORTAL_VERIFICATION.md | Upstream summary inconsistency, genuine Zetaris provenance/topic/date and approved production bridge/transport remain open |
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

Owner Vadim; merge `05e87b4`, implementation `19f3de300f0479d8f81166e6eccb326ae0eb65cc`, branch `feature/web-portals`, PR #1. Production remains `20261023-web-portals-09f5325`, unchanged in this milestone.

| Feature ID | Status | Evidence / remaining dependency |
| --- | --- | --- |
| WEB-RECONCILE | TESTED | Manual README/DECISIONS conflict resolution preserves team and portal/auth history; ARCHITECTURE imported from approved master; no history rewrite |
| WEB-ARTICLE | TESTED | Optional claim-linked prose ahead of analysis appendices; context/attribution guards and responsive DEMO browser checks. Needs real approved editorial mapping; not deployed |
| WEB-ROUNDUP | TESTED | Also today groups/status/source links, optional edition model, no synthesized rankings; cap ten per topic. Needs real reasoning output; not deployed |
| WEB-QUIET | TESTED | Explicit completed/available empty selection only; pending/error/partial/stale are distinct in unit/browser cases. No quiet-day inference from missing data |
| WEB-PHOTO | TESTED | Optional metadata/host/rights guards, attribution and failure handling; no actual photo used or rights independently verified. Upstream license review still required |
| WEB-IDENTITY | BLOCKED | Approved team red/blue/rounded direction conflicts with earlier explicit neutral palette instruction; only this visual-identity change is held |

38 Django tests, six upgrade tests, Next build/typecheck, four tooling checks, contract/ratings/editorial tests and the HTTP/browser boundary pass locally. See PR #1 for exact implementation commit and hosted CI evidence. No genuine processing integration is claimed. Earlier merge-conflict blocker is superseded by the newly authorized merge; no production account/configuration, transport or publisher changed.

Reconciliation hosted evidence: [CI 39890295440](https://github.com/rcc00n/Quorum/actions/runs/39890295440) succeeded on `19f3de3`; draft PR verified MERGEABLE. Legacy DEMO browser test also passed separately. No deployment in this milestone.

## Canonical reasoning 1.0 preview — local-only

Owner Vadim; branch `feature/web-portals`; implementation `0fe73256f468a830c56040abce32cfd07e6fa5f9`; PR #1. This milestone does not modify production release `20261023-web-portals-09f5325` or its eight accounts. The rows below are **TESTED against FICTIONAL data**, never INTEGRATED/DEPLOYED. They supersede older statements that no sample/typed reasoning consumer exists.

| Feature ID | Status | Exact evidence | Deployment / dependency |
| --- | --- | --- | --- |
| WEB-R1-ADAPTER | TESTED | Exact `8a4d453` reasoning-1.0 fixture → bounded/reference-safe `reasoning_preview` mapping → existing optional Snapshot/Event types; raw output retained; production validator still rejects it | Local-only; original collector provenance/production bridge pending |
| WEB-R1-PREVIEW | TESTED | Authenticated real Django/Next HTTP; DEBUG + explicit opt-in + localhost + nonproduction DATA_DIR gates; `--reasoning --serve` separate temporary DB/private credentials/cleanup verified | No publisher/store/transport, no production credentials |
| WEB-R1-ARTICLE | TESTED | Both stories, all supplied block kinds, claim anchors/original links, rubric/rank, attributed statements and unknown passages; TEST-derived sourced context and escaped XSS | No real articles/photos or post-publication corrections supplied |
| WEB-R1-CHAINS | TESTED | Actual found_by evidence split, per-review verdicts, adjudication/disagreement and recorded source groups; keyboard disclosures, reduced motion | Missing document IDs/hash/offset/access/review records shown explicitly |
| WEB-R1-COHORTS | TESTED | Exact 2×2 numerator/denominator pairs, structural outlet membership, interpretations/links; four modes retain missing-rating state | No source ratings/audience; cannot recompute cohorts from demo prose |
| WEB-R1-TRACE | TESTED | All 45 actual steps, all four event IDs, filters, iteration-2 research/critique and two feedback loop summaries; zero durations/null models retained | No invented times, private reasoning or claim→step links |
| WEB-R1-ROUNDUP | TESTED | Two actual groups/events, stable preview deep links; TEST partial/empty/missing-trace/error/retry | Real empty-day/failure/revision metadata still pending |
| WEB-R1-ACCEPT | TESTED | 43 Django tests, six upgrade tests, build/typecheck, static old/new JSON→TypeScript, ratings/editorial, four tooling checks, original and new real-HTTP/browser suites; desktop/tablet/mobile | Deterministic local evidence only; hosted CI recorded in PORTAL_VERIFICATION |

Real end-to-end remains WEB-INTEGRATION **BLOCKED**. Canonical reasoning §8 is confirmed; the publication bridge/transport is not. Concrete metadata and owner questions: [handoff](PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview). Next milestone: one genuine `ukraine-aid` output with retained collector quote/version provenance, validated and rendered locally before any publication authorization. Neutral branding and all existing auth/admin/store/rollback/analysis functionality are preserved.

Hosted CI for this milestone: [39895499332](https://github.com/rcc00n/Quorum/actions/runs/39895499332), **success** on implementation `0fe7325`. Final handoff commit changes documentation only; tested implementation is pinned above.

## Reasoning preview usability refinement

Owner Vadim; `feature/web-portals`, implementation `4eb44109ef22f0d02bec66a002344ca27fd2e70d`, draft PR #1. All rows **TESTED locally with FICTIONAL/TEST snapshots, not INTEGRATED/DEPLOYED**. Production remains `20261023-web-portals-09f5325`; no accounts/configuration/publication change.

| Feature ID | Status | Evidence / remaining dependency |
| --- | --- | --- |
| WEB-R1-UX-LOOPS | TESTED | Observed same-event return diagrams, actual iterations, stage/node/event filtering, all45 decisions; pure negative-case and real HTTP/browser tests. No invented causal graph |
| WEB-R1-UX-REVIEWS | TESTED | Final adjudication/paired verdict hierarchy, stance counts, all article evidence links focus correctly, original quotes/groups/URLs retained; provenance remains missing |
| WEB-R1-UX-COHORTS | TESTED | Compact 2×2 exact ratios, keyboard outlet drilldowns, four honest missing-rating modes; no denominator/member/rating fabrication |
| WEB-R1-UX-JOURNEY | TESTED | Persistent DEMO label and active section navigation, filtered-result focus, static loading, desktop/tablet/mobile screenshots, keyboard/reduced-motion/overflow checks |

43 Django, six upgrade, four tooling tests, Next build/typecheck, old/new contract and browser suites pass. Exact before/after and visual evidence: [verification](PORTAL_VERIFICATION.md#reasoning-preview-ux-refinement--local-only). Real-data dependencies and palette/font clarification remain unchanged; no live integration attempted.

Hosted [CI39900552412](https://github.com/rcc00n/Quorum/actions/runs/39900552412) **succeeded** on implementation `4eb44109ef22f0d02bec66a002344ca27fd2e70d`, including the new recorded-loop negative-case checks. The handoff commit changes documentation only. PR remains draft; production is untouched.

## Current canonical envelope and complete web handoff

Owner Vadim; branch `feature/web-portals`; implementation **`67b4cf7f8a1c41b2ebc27b41a519b840d43e1ee1`**, draft PR #1. Upstream reasoning inspected at `6ea82434d0f06cefb51f5536732ceac68e9780ef`, collector at `18fb009b4b36e995e765563203edbf742475a20b`. No production access/deployment/account change; release remains `20261023-web-portals-09f5325`.

| Feature ID | Status | Evidence / dependencies |
| --- | --- | --- |
| WEB-R1-ENVELOPE | TESTED | Canonical generated/published/expiry/timezone/window/corpus/model fields, DST calendar checks, null publication and expired hint; structured errors with safe redaction. Existing strict publisher untouched |
| WEB-R1-THREE | TESTED | Exact main/empty/partial fixtures via parser, authenticated API, actual TypeScript and Next browser boundary: 2/0/2 stories, 45/29/45 trace steps; partial missing-framing state retains coverage |
| WEB-HANDOFF | TESTED | Canonical architecture, field mapping/missing-provenance matrix, commands, security/release boundaries and owner read lists audited; relative links, diff and public-index checks pass |
| WEB-NOTIFY | IMPLEMENTED | Bidirectional protocol [announced in Issue #2](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6357796090) with all three owners tagged; other assistants' acknowledgement **pending**, no adoption claimed |
| WEB-INTEGRATION | BLOCKED | Genuine run and production bridge; original provenance/review/correction export, topic registry alignment and approved transport. Dates/DST/namespace/extractor delegation now supplied, not stale blockers |

All previous auth/admin/session/CSRF/store/rollback/UI guarantees remain covered. 48 Django + six upgrade + four tooling tests, Next build/typecheck, static contract/ratings/editorial/trace checks and both real HTTP/browser suites pass. Current commands and audit evidence: [verification](PORTAL_VERIFICATION.md#current-reproducible-checks). The short [Start Here](TEAM_HANDOFF.md) links canonical specs rather than asking teammates to implement UI types as reasoning API. No real integration or new deployment checkbox is closed.

Hosted [CI39903475716](https://github.com/rcc00n/Quorum/actions/runs/39903475716) **succeeded** on `1d27894026616f7d5f4d8d7f7c092dd0258278e2` (adapter implementation `67b4cf7`). Final follow-up changes documentation/evidence only. [Team notification](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6357796090) posted; @Sor1na and @AnastasiaShkirpan have not explicitly acknowledged at this check. PR remains draft, production untouched.

## FULL-REAL-01 local experiment and current consumer

Owner Vadim / Codex; `feature/web-portals`, local changes only; PR #1 remains draft and production untouched. These observations supersede the earlier local registry/startup blockers, not release/publication gates. Private evidence remains outside Git under `~/.local/share/quorum/experiments/full-real-integration-20261023/`.

| Feature ID | Status | Actual evidence / remaining dependency |
| --- | --- | --- |
| REAL-ZETARIS-01 | TESTED | Official default stack/verify, authenticated SQL and canonical loader; unique isolated datasource exposes the preserved 43 articles/50 officials/14 collected sources. Original metadata identical; no recollection or teammate datasource overwrite |
| REAL-EDITION-01 | TESTED | `ukraine-aid/2026-10-23`: 11 articles/6 sources/0 same-edition officials. Latest 0224ca6 loader adds 14 explicitly historical rows (including 1 official), which do not count as same-edition corroboration |
| REAL-GRAPH-DRY-01 | TESTED | Original graph at 58c9078 with actual Zetaris corpus and deterministic stand-ins: no inference/errors, 10 roundup entries; original non-fixture artifact accepted through authenticated Django/Next and three widths |
| REAL-GRAPH-LIVE-01 | BLOCKED | One execution: 172 confirmed genuine Lightning completions, 136401 known tokens; attempt 173 failed Windows interop with unknown outcome. No final live snapshot or full graph/Ultra-review claim. Reconcile unresolved receipt before replay; no whole rerun performed |
| WEB-R1-CURRENT | TESTED | 0224ca6 additive quote/identity/access/third-review/summary-source contract; old fixture compatibility and non-fixture stand-in labels retain unpublished/auth gates. Three latest original fixtures parse; actual main-file bytes accepted by Django/TypeScript/browser |
| WEB-INTEGRATION | BLOCKED | Complete original real-live snapshot still absent. New upstream provenance/reviewer/summary fixes need genuine acceptance; missing same-edition official corroboration and production bridge decisions remain explicit |

Validation: 52 Django tests, 4 tooling tests, Next production build/typecheck, static contract/ratings/editorial/trace tests, original portal HTTP/auth/store/rollback browser regression, prior reasoning fixture suite, current upstream main fixture and genuine stand-in corpus browser acceptance. Current main fixture SHA-256 is `68ed0b449bdaedee01435ee702b8d454496b6d9e286543ecbc7b9976695c642b` from git show 0224ca6, differing from the owner's notice hash; unchanged original bytes are the acceptance basis. No new hosted CI or deployment is claimed.
