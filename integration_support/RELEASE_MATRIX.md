# Release-candidate evidence matrix — 2026-10-24

RC-01 · Owner: Vadim / Codex. Supplemental evidence for [Issue #2](https://github.com/rcc00n/Quorum/issues/2) and [Draft PR #6](https://github.com/rcc00n/Quorum/pull/6); the canonical release gates remain `docs/RELEASE_CHECKLIST.md` in the web candidate. This is an unapproved local candidate, not a release or sponsor-compliance claim.

Candidate `f9bf7995c5d21fd275830a616e30e31317416c53`, tree `1083d5e98bda8adcb57a10abafdf93d2dae4a01f`: integration `c3cc5ac` → reasoning `3d89448` → collection `8f126c5` → web `f59e758`, then web-owned patches 0003/0006/0007/0008/0009. Owner-dependent patches 0001/0002/0004/0005 remain separate provisional proposals. Fresh fetch found no owner-head changes; PRs #4–#6 had no feedback or submitted reviews. All owner decision rows and additive configuration survive; collection conflicts were `.env.example`/decisions and web conflicts `.gitignore`/decisions.

| Capability / gate | State | Evidence / exact limit | Responsible owner |
| --- | --- | --- | --- |
| Ordered local integration | VERIFIED | Fresh disposable candidate; five rehearsal-safety tests; owner-history/config/schema checks pass. No integration/master branch changed. | Vadim; all owners approve actual merges |
| Owner review / adoption | BLOCKED | [PR #6](https://github.com/rcc00n/Quorum/pull/6) requests pending; code availability and CI do not confer approval. | Yelysei / Anastasia |
| Reasoning rules and deterministic fixtures | VERIFIED | 222 tests PASS on the web-owned candidate with Python socket connections blocked and dry mode forced. | Yelysei |
| Collection source/schema interfaces | VERIFIED | 40 unique sources; 34 rated rows with attribution; wire/doc-type enums, actual hash formula and Unicode quote offsets pass offline. | Anastasia |
| Actual database / Zetaris operation | BLOCKED | No service was contacted. Collector owner documentation is not independently verified query/row evidence. | Anastasia |
| Django auth, CSRF, revisions and strict provenance guards | VERIFIED | 70 tests PASS, including both unchanged-original negative-test cases; system check and migration drift pass. | Vadim |
| Genuine v3 presentation | VERIFIED | Four authenticated Chromium suites pass: original portal/store/rollback, fictional, skipped-check/keyboard, genuine v3. All 28 roundup entries, zero stories, 264 trace rows, 63 safe errors; source links and three widths. | Vadim |
| Full original execution / corpus attestation | BLOCKED | Existing [config-SHA evidence](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6390549245) remains unresolved. Original snapshot and sidecar unchanged; presentation compatibility is not attestation. | Yelysei; Anastasia for corpus manifest |
| Four rating modes and source attribution | VERIFIED | AllSides / MBFC / Ad Fontes / available-rating mean; genuine source joins and ratings/editorial/trace/TypeScript regressions PASS. Missing ratings/audience stay explicit. | Vadim / Anastasia |
| Desktop/mobile keyboard investigation | VERIFIED | Actual Chromium 1440/390px: skip/section focus, event trace scope, next Tab stop, no overflow, skipped-check notice persistence. | Vadim |
| Next build and typed contracts | VERIFIED | Fresh production build/typecheck, source and compiled-output receipt validation PASS. | Vadim |
| Release archive | VERIFIED | Actual archive: 2,662 safe entries; version-2 receipt; no original evidence, runtime DB/log/account/env files or links. Packaged standalone boots on an isolated loopback port. SHA-256 `4bc13b3e9807bcd5f5c319e49f5734cf023e649de2dcbafbef591b3467bca9c6`. | Vadim |
| Backup / rollback mechanisms | VERIFIED | 12 deployment/export/backup/rollback tests PASS on temporary files and stubbed services. No production auth data read. | Vadim |
| Target-host restore / deployment | NOT TESTED | No production credentials, services or target host accessed; fresh deployment authorization and restricted backup/restore review required. | Vadim |
| Public producer failure redaction | IMPLEMENTED | Separate proposal 0001/0005: eight negative node-path cases and combined provisional CI pass. Not adopted into this candidate; review remains a publication blocker. | Yelysei |
| H-MEM reference component | VERIFIED | Unchanged installed reference at `1742dec` passes 13/13 official conformance again; this checks the reference class, not owner-graph integration. | Yelysei / Vadim |
| H-MEM hooks/storage/selection safeguards | IMPLEMENTED | Separate default-off proposals 0002/0004; prior local 16 TEST-state persistence/recall/re-verification cases PASS, with six pre-fix failures reproduced. No dry writes. [Evidence](https://github.com/rcc00n/Quorum/pull/6). | Yelysei / Anastasia |
| Genuine owner-graph memory behavior | BLOCKED | Owner approval and genuine eligible-record persistence/recall/fresh verification remain missing. | Yelysei / Anastasia |
| Complete Nightshift → NVIDIA workflow | BLOCKED | Five historical tiny routing receipts are insufficient. No inference or sponsor service request made in this session. | Yelysei / Vadim |
| Production bridge / publishing authorization | BLOCKED | Strict production validator/publisher stays separate and disabled. Transport, machine authorization and release review remain unapproved. | All owners |
| Hosted candidate-profile checks | IMPLEMENTED | Both profiles are configured in [PR #6 checks](https://github.com/rcc00n/Quorum/pull/6/checks); exact final-head outcome is recorded in the PR and Issue #2 handoff. External-reference/private-original skips are explicit. | Vadim |
| Demo recorder / timed narration | IMPLEMENTED | Original-hash-only private 230-second recorder, blocked external requests, disposable local auth, captions and substitution/output-location guards. Capture evidence is recorded in the session handoff. | Vadim |
| Final narrated video / slides / workspace submission | NOT TESTED | Human review of the private recording, final narration/edit, sponsor evidence and Track 03 submission are still required before October 27, 23:45 UTC. | All owners |

**GO:** private offline rehearsal of the genuine, explicitly limited local product. **NO-GO:** production release, unqualified genuine execution acceptance, complete sponsor claims, or final submission certification. Critical path: owner review plus genuine execution/config evidence; then approved ordered merges and combined CI, sponsor evidence, secure bridge and final operational/submission review.
