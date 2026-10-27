# Web platform technical release checklist

Owner: Vadim. Shared release tracker: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). This is the canonical web technical release gate; [implementation inventory](IMPLEMENTATION_STATUS.md) records individual capabilities. Check boxes only for a particular release with its commit, environment, test outcome and rollback revision; a previous release's pass does not approve a new release.

## Sources and motion production acceptance — 27 October 2026 UTC

Only `20261027-spectrum-r1` / `6f16bd7feda9a8e3c1c105ddd3510b2dce9d27fa`.
[Exact evidence](../deploy/FRONTEND_RELEASE.md); earlier release checks remain historical.

- [x] Tracker, contracts, owner coordination and reviews rechecked; PRs #44/#45 normally merged after green exact-head CI.
- [x] Clean build/typecheck, source geometry, HTTP/browser and genuine installed-edition checks; source/artifact-bound archive verified locally and on target.
- [x] Actual VPS preflight/private backups, target-host tests/checks and guarded Quorum-only switch; no migrations or new dependencies.
- [x] Actual r3 code/static rollback and guarded reapply; original edition, accounts, SSH, reader flags and 24 unrelated containers preserved.
- [x] Public authenticated Sources, exact catalog/positions/four modes, keyboard, depth, reduced motion, observer fallback and three widths pass.
- [x] Genuine feed/story/19 roundup/174 exact traces, evidence/review, anonymous/staff/CSRF boundaries and UI login/logout pass.
- [x] Restart preserves judge session/four preferences/exact feed; final HTTPS/TLS/service/SQLite checks and desktop/mobile visual inspection pass.
- [ ] Fresh 27-Oct original editions and full sponsor/recall/submission gates remain with owners in Issue #2.

## Production acceptance — 27 October 2026 UTC

These checks apply only to `20261027-live-r3` / `63418421c1c0909dc0d7dfa1b451da3eed1bcc76`.
Earlier checklists below remain historical. [Full evidence and limitations](../deploy/LIVE_RELEASE.md).

- [x] Current master/tracker/contracts and all owner reviews rechecked; dependency order and decision history preserved.
- [x] Source and final integration CI green, build/typecheck, target-host Django, focused release/security tests and source/artifact-bound package verified.
- [x] Existing VPS preflight, private consistent backups, exact original/sidecar/config hashes, quorum-owned 0700/0600 installed edition checked.
- [x] Guarded Quorum-only cutover; actual previous-code/static rollback and reapply; auth preserved without DB restoration; all 24 unrelated containers unchanged.
- [x] Public HTTPS judge login/logout, restricted anonymous/staff/CSRF boundaries, genuine feed/story/roundup/evidence/reviewer/174 trace, four ratings and three widths pass with no page errors.
- [x] All eight previously issued credentials authenticate with expected roles; all nine pre-existing users/preferences preserved; ordinary judge added through Django, password private.
- [x] Both services restarted; existing judge session, four preferences and exact edition/feed persist; final external HTTPS and service health checked.
- [x] Reader enabled, proposal publisher disabled, historical v4 not installed, provisional/editorial review/freshness limits preserved.
- [ ] Receive/accept/install genuine 27-Oct editions from owners, including Nightshift route and live H-MEM recall evidence.
- [ ] Independently close source-text/provider/sponsor certification and human hackathon submission/workspace/rights gates.

## Current proposal review

Historical gates below refer to their pinned milestone in [PORTAL_VERIFICATION.md](PORTAL_VERIFICATION.md) and PR #1; latest results are in its current compatibility section. No deployment is approved by these local checks; production/contract gates remain open.

## Before integration or deployment

- [ ] Read current master AGENTS.md, Issue #2, DECISIONS.md and both owners' contracts; reconcile conflicts without overwriting decisions.
- [x] Inventory every delivered WEB-* feature and every newly checked tracker item; no silent feature removal.
- [x] Review scope, diff, staged paths, secret patterns, file sizes and dependency changes; no credentials/runtime/DB files.
- [x] Run Django auth/CSRF/registration/login/logout/profile/password/preferences/roles/staff tests, snapshot validation/store/adapter tests, system check and migration drift check.
- [x] Build Next production output and typecheck; run rating/null/URL and analysis component browser tests without inference.
- [x] Verify `/`, `/login`, `/register`, `/onboarding`, `/dashboard`, `/topics/[slug]`, `/events/[id]`, `/history`, `/settings` and every link/date/revision deep link.
- [ ] Verify `/staff/`, user creation/change, read-only topics/sources and status/integration views; regular users denied, superusers allowed.
- [x] Verify empty/loading/error/retry states; unknown facts are not false; stale/partial/fallback states are explicit; no fixtures presented as live results.
- [x] Check Evidence Explorer support/contradiction, original URLs, dates, primary/access restrictions, verifier disagreement and corrections; no invented confidence or citations.
- [x] Check Perspective Comparison, all four rating modes, unknown denominators/audience, independence vs publication count; no inferred group positions.
- [x] Check Investigation Timeline, public-safe summaries, missing trace state and references; no prompts/private chain-of-thought/secrets.
- [x] Inspect desktop/mobile/tablet, keyboard focus/disclosures, labels, chart overflow and reduced motion. Record practical limits of accessibility checks.
- [x] Validate malformed/oversized/non-finite/unsupported payload rejection, safe URL policy, immutable revisions, integrity mismatch, failed publication, last-known-good and rollback.
- [x] Verify the publication gate is disabled in production unless transport/schema/authorization approval is recorded. No public upload endpoint or processing-agent auth DB access. Read-only target-host check confirmed no snapshot root or enabled publisher.
- [ ] Record restricted auth-data backup, previous release, snapshot head/revision and exact rollback procedure. Preserve all users/preferences; do not rotate the eight accounts.
- [ ] Inspect current VPS resource/port/service/container state. Deploy only Quorum services with existing private config, loopback binding and validated Nginx if changed. No global runtimes/firewall/SSH/Docker changes.
- [ ] After deployment, verify target-host and external HTTPS, sessions/CSRF/permissions, catalog selection, dashboard/history/event routes, new UI and asset delivery. Compare auth data and other workload states. Never publish credentials in evidence.
- [ ] Update inventory, release evidence, Issue #2 and PR #1 with commit/tests/deployment and next dependencies.

## Genuine integration and hackathon release gates (remain pending)

- [ ] Actual permitted publication and official record with original IDs/URLs/hash/access/provenance (Anastasia).
- [ ] Authenticated real Zetaris queries/federation with returned data, not a connector receipt (Anastasia).
- [ ] Actual authorized Meterless→Nemotron request, extraction/verification/independent review, disagreement/re-check and corrected conclusion (Yelysei).
- [ ] Agreed versioned contract and narrowly scoped transport/auth; genuine securely published result displayed on the portal with provenance/revision and failure handling (all).
- [ ] Repeatable real end-to-end demo and auditable public-safe trace; fixture tests are separately labelled (all).
- [ ] Confirm Track 03 workspace selection and organizer-rule evidence, including unresolved human-reported Cursor update (all).
- [ ] Judges' reader on the VPS: `QUORUM_ENABLE_REASONING_READER=1` and `QUORUM_REASONING_EDITIONS_ROOT` in `/etc/quorum/portal.env`, each 27 October edition installed with `reasoning_snapshot … --install` after acceptance, checked signed-in on the site (Anastasia, covering Vadim's items).
- [ ] Final 1–4 minute video, slides, source/setup/usage/dependencies, sponsor-use explanation and verified submission before 2026-10-27 23:45 UTC (all).

## Rollback

Use [deploy/README.md](../deploy/README.md). Switch only the Quorum release symlink and restart only its services; restore a consistent private auth backup only if necessary for migrations. Roll snapshot heads back only to an intact validated immutable revision. Preserve unrelated projects/data and certificates. Re-run relevant HTTPS/auth checks and record rollback evidence.


## Integration-readiness release gates (feature/web-portals)

- [x] Baseline branch `9a79ea9` and clean tree verified before edits; remote contracts/tracker read without branch changes.
- [x] Read-only compatibility report, immutable-head/auth no-write tests, full existing regressions and actual local HTTP/type/browser boundary pass.
- [x] Upgrade tool safety tests pass, including simulated failed-health code/static rollback; no migrations or publishing permitted.
- [x] Hosted branch CI result verified: run 39887513802, code SHA `09f5325`.
- [x] Target-host plan, restricted auth backups, previous release and Python 3.10 compatibility verified before cutover.
- [x] Guarded Quorum-only release switch, HTTPS/auth/staff/catalog/pending/new-asset checks and unrelated workload preservation verified.
- [x] Exact code/release SHA, rollback, tracker and draft PR updated with real outcomes (milestone handoff references code `09f5325`).

These deployment gates do not close sponsor or genuine upstream-result gates.

Current release `20261023-web-portals-09f5325` / code `09f5325` passed these deployment gates; rollback is `20261022-web-portals-r2`. See [exact production evidence](PORTAL_VERIFICATION.md#production-release-evidence--integration-readiness). Checkmarks in earlier proposal review sections remain historical; sponsor/contract gates stay open.

## Product reconciliation milestone — no production release

- [x] Explicit permission to merge master into feature only recorded; clean baseline `96eb337`, manual conflict resolution `05e87b4`, both histories preserved.
- [x] Approved impact/article/roundup flow supported additively; production input schema unchanged, identity conflict documented and held.
- [x] Existing 38 Django/snapshot regressions, six upgrade tests, Next build/typecheck, contract/tooling/ratings/editorial and old/new HTTP/browser tests pass locally.
- [x] Completed quiet-day versus pending/error/partial/stale cases, context attribution guards, Unicode code-point offsets and photo prerequisites covered with TEST/DEMO data.
- [x] Production, accounts, publisher, credentials and remote processing untouched; production release remains `20261023-web-portals-09f5325`.
- [x] Hosted CI 39890295440 passed on code `19f3de3`; draft PR #1 verified MERGEABLE after merge `05e87b4`.
- [ ] Real reasoning sample/schema mapping and transport approved; real end-to-end gate remains open.

## Reasoning 1.0 preview milestone — no production release

Code `0fe73256f468a830c56040abce32cfd07e6fa5f9`, only `feature/web-portals`, PR #1. Historical release checkmarks do not authorize deployment of this preview.

- [x] Pin exact canonical FICTIONAL sample/schema/version/hash; preserve upstream ownership and original bytes.
- [x] Hosted CI 39895499332 succeeded on code `0fe7325`; local browser evidence is separate.
- [x] Gate preview behind DEBUG, explicit opt-in, localhost, nonproduction data directory and session; ordinary feed remains pending and production validator rejects raw sample.
- [x] Real isolated HTTP→API→Next checks cover both articles, actual claims/reviewer paths, impact/cohorts/roundup and all 45 recorded steps; labelled TEST derivatives cover absent context, partial/empty/error/missing trace/XSS.
- [x] Preserve 38 original Django regressions plus five preview tests, upgrade/contract/build/type/old/new browser checks; no migrations or new dependencies.
- [x] Inspect 1440/768/390px layouts, source links, keyboard disclosure, reduced motion and screenshots outside Git.
- [x] Verify local launcher uses mode-700 temporary directory/mode-600 local credentials and cleans up; no production file/account read.
- [x] Production, all eight accounts, private configuration, publisher, credentials and transport untouched.
- [ ] Genuine versioned reasoning output with collector IDs/quotes/hash/access/review/freshness/correction metadata validated locally.
- [ ] Agree production bridge, safe public error shape, topic ID, revision/freshness rules and transport before enabling any credentials/publication.
- [ ] Future deployment requires fresh explicit scope, restricted auth backup, rollback target and all original HTTPS/auth/unrelated-service gates. No deployment attempted here.

Verification/hosted CI: [current evidence](PORTAL_VERIFICATION.md#reasoning-10-fictional-preview-milestone).

## Preview UX refinement — no deployment

Branch `feature/web-portals`, code `4eb44109ef22f0d02bec66a002344ca27fd2e70d`, draft PR #1.

- [x] Actual existing preview inspected before/after at1440/768/390px; original branding preserved.
- [x] Recorded returns derive only from same-scope trace records; all45 steps and all original article/source/claim fields retained. No live-inference animation or invented graph dependencies.
- [x] Paired review verdicts/adjudication, exact cohort totals/drilldowns and complete reading journey verified through real local HTTP; every claim link/focus, event/stage/loop filters, keyboard, reduced motion and overflow checked.
- [x] Existing Django/auth/staff/snapshot/rollback/upgrade, Next/type/contract and old/new browser regressions pass; fixture/sample/schema and production publisher unchanged.
- [x] One-command isolated preview preserved; no production account, DB/configuration, services or credentials changed.
- [x] Hosted CI39900552412 succeeded on implementation `4eb4410`; browser/visual evidence verified separately locally.
- [ ] Real snapshot/provenance/bridge and transport approval remain separate prerequisites; this preview does not satisfy a production release or sponsor E2E gate.

## Current 1.0 envelope and handoff — local-only gate

Owner Vadim; `feature/web-portals`, implementation `67b4cf7f8a1c41b2ebc27b41a519b840d43e1ee1`, draft PR #1. This is not a deployment authorization.

- [x] Compare latest canonical §8 and all three exact examples at reasoning `6ea8243`; pin bytes/hashes and inspect latest collector read-only.
- [x] Validate UTC timestamps/nullability/DST windows/provenance types, retain unpublished/expired distinction, safely project structured partial errors and absent framing without fake content.
- [x] Pass 48 Django, six upgrade, four tooling, Next build/typecheck, strict internal validation, all-three TS contract and both actual HTTP/browser regressions including keyboard/reduced motion/three widths.
- [x] Audit web architecture, API/auth, projection/store/revisions/corrections, preview, data/provenance, test setup and safe release/rollback docs; canonical links and notification format included.
- [x] Preserve strict production schema/validator/store, preview security gates, all existing website features and production isolation; no migrations, credentials, inference or production access.
- [x] Hosted [CI39903475716](https://github.com/rcc00n/Quorum/actions/runs/39903475716) passed on `1d27894`; [team announcement](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6357796090) posted with all owners tagged.
- [ ] Receive explicit acknowledgement from Yelysei/Anastasia that their active coding agents follow the Issue #2 notification procedure.
- [ ] Resolve original evidence/review/correction export, topic ID and genuine corpus/model proof with owners; approve production bridge/transport separately.
- [ ] Future production release still needs explicit scope, private backup, rollback and fresh live verification. No deployment attempted.

## Final three-owner readiness — 2026-10-24, local rehearsal only

This supplements Issue #2 and Draft PRs [#4](https://github.com/rcc00n/Quorum/pull/4), [#5](https://github.com/rcc00n/Quorum/pull/5), and [#6](https://github.com/rcc00n/Quorum/pull/6). Historical checkmarks above remain historical. No new deployment, publishing or provider execution is approved. Apply the PR #6 review patches only after the relevant owner approves them; patch availability is not adoption.

| Gate | Evidence state | Required action / owner |
| --- | --- | --- |
| Ordered integration | PASS locally: pinned reasoning `3d89448` → collection `8f126c5` → web `f59e758`; additive conflicts reconciled with all owner decision history retained | Yelysei / Anastasia / Vadim: review each PR, merge with merge commits in that order, rerun combined checks after each stage. No rehearsal merges are pushed. |
| Support patch review | BLOCKED: no submitted Yelysei or Anastasia review on PR #6 at audit time | Yelysei: public failure policy and graph/memory behavior. Anastasia: exact source namespace/hash/access/identity handling. Vadim: offline tooling, keyboard flow and compiled build receipts. Recheck latest review state before application. |
| Combined Python and contracts | PASS locally: 246 reasoning, 70 Django including private-original cases, 12 deployment, eight tooling, three rehearsal tests; collection registry/schema checks static only | Run the combined-tree CI on the actual approved merge SHA. Database migrations/queries and live collection execution remain BLOCKED, owned by Anastasia. |
| Web / authenticated demo | Local and hosted outcomes are recorded in PR #6 and Issue #2; do not infer completion from this checklist | Vadim: require Next build/typecheck, ratings/contract regressions and real authenticated Chromium suites, including desktop/mobile keyboard navigation, on the final reviewed tree. |
| Genuine original v3 | BLOCKED for full execution acceptance; local provisional display is supported (28 roundup, zero stories). Original evidence is immutable | Yelysei: provide genuine execution/config evidence resolving [the existing config-SHA finding](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6390549245). Do not regenerate or edit evidence to satisfy acceptance. Never present skipped independent checks as confirmation. |
| H-MEM | PASS: installed unchanged reference conformance 13/13 and TEST-state persistence/recall/fresh re-verification. Genuine owner graph is NOT TESTED | Yelysei approves/adopts default-off hooks; Anastasia approves exact DocRefs. Then obtain authorized genuine eligible-record persistence, recall, fresh source re-verification and auditable ledger evidence. Dry mode must make no writes; partial/locked/linked stores fail closed. |
| Nightshift → NVIDIA | BLOCKED: historical tiny routing receipts do not establish the complete reasoning workflow | Yelysei / Vadim: agree the authorized execution and evidence plan. No extra inference or spend is authorized by routine acceptance. |
| Zetaris / sponsor compliance | BLOCKED: static interfaces and environment readiness are insufficient | Anastasia: demonstrate permitted actual data queries/federation and exact source provenance. All owners: verify Track 03 rules and sponsor evidence against the organizer requirements before claiming compliance. |
| Publishing boundary / authentication | BLOCKED for production activation; local session/CSRF, strict snapshot validation and disabled production publisher regressions exist | All owners approve transport, versioned contract, topic/revision/freshness handling and narrowly scoped authorization. Keep public uploads disabled and processing agents away from the auth database; test safe public errors. |
| Release packaging | PASS unit checks: receipts bind source and compiled output; modified/missing/added/linked artifacts are rejected | Vadim: rebuild older receipts and review the clean release SHA, complete diff, tracked paths and secret/private-file scan before packaging. Never stamp old assets as a new build. |
| Backup / rollback | PASS offline rollback regressions; current target-host restore rehearsal is NOT TESTED | Vadim after explicit deployment authorization: take a restricted consistent auth backup; record previous release and immutable snapshot head; verify restore and Quorum-only rollback procedures without touching other workloads. |
| Final target environment | NOT TESTED in this session; no production credentials or running services accessed | Vadim after deployment authorization: inspect resources/ports, secure loopback services/proxy/HTTPS, verify permissions/CSRF/session/health/assets and preserve existing accounts/data. |
| Honest demo / submission | Local roundup → source links → recorded trace → four-mode ratings is available; real featured stories/claim evidence are absent from v3 | All owners: rehearse the genuine edition with visible partial/provisional/skipped-check limitations. Label fictional examples separately. Record the 1–4 minute video and finish slides/setup/sponsor explanation and submission before October 27, 23:45 UTC. |

Release review closes only when the actual combined commit has successful CI, original evidence acceptance (or an explicitly approved truthful limited demo), owner approvals and the concrete operational gates above. This checklist does not close unchecked Issue #2 items or authorize `integration` → `master` automatically.
