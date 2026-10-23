# Web platform technical release checklist

Owner: Vadim. Shared release tracker: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). This is the canonical web technical release gate; [implementation inventory](IMPLEMENTATION_STATUS.md) records individual capabilities. Check boxes only for a particular release with its commit, environment, test outcome and rollback revision; a previous release's pass does not approve a new release.

## Current proposal review

Local gates below refer to [PORTAL_VERIFICATION.md](PORTAL_VERIFICATION.md), PR #1, 29 passing Django tests and the built/browser-tested proposal. No deployment is approved by these local checks; production/contract gates remain open.

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
