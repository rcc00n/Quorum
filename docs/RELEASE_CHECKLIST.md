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
