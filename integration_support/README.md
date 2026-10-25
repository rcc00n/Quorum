# Offline integration support — owner review bundle

This branch is based on `integration@c3cc5ac`. It contains no rehearsal merge commits and does not duplicate any owner's application history. Executable patches are intended for the combined reasoning → collection → web tree after review. The canonical tracker remains GitHub Issue #2; project rules remain in root AGENTS.md.

## Patches

1. `0001-public-failure-privacy.patch` — Yelysei reviews. Confirmed synthetic failure: provider exception contents enter public trace reasons and third-review adjudication. The patch retains private StepError diagnostics and failure status/counts, while public operational reasons use a fixed safe message. Baseline: 222 reasoning tests; patched: 225 passing, with network blocked.

Apply to a clean disposable combined tree with `git apply --check <patch>` followed by `git apply <patch>`. Review and commit normally; these commands neither fetch nor merge any branch. Never apply automatically to an owner's worktree.

2. `0002-source-memory-hooks.patch` — Yelysei reviews graph/selection behavior; Anastasia reviews exact DocRef namespace/hash/access handling. Default off, zero requested/forced-dry writes, reference persistence/recall and existing-cap fresh re-verification. Nine TEST-state hook cases pass; patched reasoning suite 234/234; unchanged reference conformance 13/13 at engine `1742dec56a66e58eef9dda2d2b865823758ca8cd`. No genuine graph or sponsor completion claim. The patch includes its module README and proposed canonical decision entry; it does not overwrite the owner's go/no-go.

3. `0003-offline-diagnostics.patch` — Vadim reviews. Adds `--offline` to existing doctor/verify wrappers without reading private config or contacting service clients. Six tooling tests pass; each offline command returns five local PASS and one deliberately BLOCKED live-evidence item. `--offline --inference` is rejected before config access.

4. `0004-memory-storage-safety.patch` — additional Yelysei/Anastasia review required. Seven negative cases cover linked state/root/ledger, invalid ownership marker and type-coerced identity/fictional flags. Six original audit cases failed before correction; all 16 memory tests now pass using temporary TEST stores and the installed unchanged reference. Reject unrelated entries before reference reads/writes; exact JSON identity prevents Python bool/float equality from prioritizing a different record. Private operator-controlled storage is still required; this does not defend against concurrent malicious same-user mutation.

## Rehearsal pins

- integration: `c3cc5ac4a65855769ab48e36a1d59d5cc1ae261d`
- reasoning: `3d894488835b19b22281784cf8bf1e2ad5fa2be3`
- collection: `8f126c57a9ef9af798543bf23a0a60737b0ce5dc`
- web: `f59e75840c9aee67ca35a8f44bf5dd42747af75f`

Local merge sequence retained all owner decision-log rows verbatim and unioned additive environment/ignore entries. Development handover and production publication remain separate gates. The config-SHA audit in Issue #2 comment 6390549245 is accepted evidence and was not repeated. Original v3 files remain untouched.

## Decisions

2026-10-25 UTC · rcc00n / Codex · Build the private final cut from reviewed genuine footage plus authenticated UI still holds, with frame-indexed captions and an explicit no-audio fallback script. Why: exact runtime and readable four-mode scenes must not depend on drifting capture timestamps; no UI data or producer evidence is edited.

2026-10-25 UTC · rcc00n / Codex · `demo_tour.cjs --scenes` captures authenticated original-evidence stills without a timed movie. Why: final offline edits need deterministic, auditable rating/provenance frames while preserving all existing original-hash, catalog and publication guards.

2026-10-24 · rcc00n / Codex · `--patch-profile web-owned --require-current` applies only independent web/deployment/diagnostic patches and refuses stale fetched owner pins before worktree creation. Why: unapproved reasoning/privacy/memory proposals must remain distinguishable from the candidate used for the genuine demo. This is a module decision; owner merge approvals are still required.

2026-10-24 · rcc00n / Codex · Publish review patches and offline tooling on a branch based on integration, keeping rehearsal merges local. Why: owners can review/apply minimal changes without pushing their unmerged histories or the disposable merges through another PR.

## Reproduce safely

```bash
python3 -m unittest discover -s integration_support -p 'test_*.py'
python3 integration_support/rehearse.py --repo <existing-quorum-checkout> \
  --destination <NEW-external-disposable-path> --with-proposed-patches
python3 integration_support/check_tree.py --root <that-disposable-path>
```

The tool uses only the pinned local Git objects, creates a new detached worktree, resolves only the known additive conflicts, verifies every owner decision row, and optionally rehearses all numbered proposed patches. It never fetches, pushes or touches an existing destination. The new support CI repeats that exact process, tests the combined Python components on 3.11 with sockets blocked, and builds/tests the combined web with authenticated Chromium; production gates remain separate. Reference-HMEM and private-original tests are skipped when their external prerequisites are absent; local evidence below includes them.

Offline command checks prove local tooling only: their one BLOCKED item deliberately preserves the absence of live integration evidence. Static schema/enum and registry checks do not establish PostgreSQL migrations or live collection. Existing Nightshift receipts prove five historical tiny routing responses (four nonce probes reported uncached, explicit Ultra selected Ultra); they do not prove a complete Nightshift-powered reasoning workflow or receipt signature verification. No new inference request was made.

## Previous support milestone evidence — 2026-10-24

| Check | Result and scope |
| --- | --- |
| Three-owner rehearsal | PASS: reasoning merged cleanly; collection resolved `.env.example`/`docs/DECISIONS.md`; web resolved `.gitignore`/`docs/DECISIONS.md`; all owner log rows retained. Both original and scripted disposable trees are clean. |
| Reasoning | PASS: baseline 222; privacy patch 225; all proposed patches 234 (including nine real-reference TEST-state memory cases). Socket connections blocked. |
| Fixture output → strict portal parser | PASS: sample plus eight use-case editions, including zero stories, cap ten, dispute, retraction, headline-only and statements-only. Deterministic fictional inputs only. |
| Collection | PASS: 40 registry rows, ratings provenance, wire groups, schema/doc-type enum statics, shared fetcher import, matching hash formula and Unicode quote offsets. BLOCKED: database/schema execution and live collection intentionally not contacted. |
| Web/backend | PASS: 70 Django tests with private-original cases, system/migration-drift, strict internal validator, Next build/typecheck, ratings/editorial/trace/TypeScript checks. |
| Browser | PASS on the combined tree: original authenticated portal/store/rollback, canonical fictional, skipped-check, and genuine unchanged v3 (28 roundup / zero stories / 264 trace / 63 errors); no production publisher. |
| Release safety | PASS: ten deployment/export/build-integrity/backup/rollback tests. No production credentials/accounts/services accessed or changed. |
| H-MEM | PASS: nine targeted hooks and official reference conformance 13/13. BLOCKED: owner approval, genuine eligible-record persistence/recall/re-verification evidence and sponsor claim. |
| Routine diagnostics | PASS: six tooling tests; offline doctor and verify each report 5 PASS / 0 FAIL / 1 BLOCKED (live evidence intentionally unavailable). |
| Existing Nightshift evidence | Five historical successful tiny routing responses; explicit Ultra pin worked, four nonce probes reported uncached. BLOCKED: full genuine Nightshift-powered workflow and independent receipt-signature evidence. No new requests. |
| Original v3 execution attestation | BLOCKED: preserve Issue #2 comment 6390549245 findings; original config SHA mismatch remains unresolved. No historical-config investigation repeated. |

Original local rehearsal merge commits: reasoning `a26a6c6`, collection `9ede1b2`, web `77fd495`; proposed fixes were tested on local `f88c0e4`. The script separately reconstructed a clean patched tree (`23d943d` in this session). These are local evidence references, not branches or merges to publish. Support publication contains patches/tooling only. Yelysei approves reasoning/privacy/H-MEM behavior; Anastasia approves source identity/schema assumptions; Vadim approves diagnostics and web/security effects. Combined offline success does not authorize production publication or certify hackathon compliance.


## Final-readiness audit — 2026-10-24

PR #6 had no submitted owner reviews or comments at audit time; existing requests to Yelysei and Anastasia remain pending. No owner feedback was adopted without approval. Patches 0001/0002/0004/0005 require Yelysei review, with Anastasia reviewing exact source provenance/selection assumptions. Web/deployment/diagnostics changes are Vadim-owned proposals in the same bundle; no owner worktree was edited.

- `0005-public-failure-audit-tests.patch`: all eight exception-redaction cases pass, covering score, extraction, publishing, research, fact-checking, writing, framing and third review; partial/dispute/unverified status and restricted diagnostics remain visible where appropriate.
- `0006-offline-diagnostics-audit-tests.patch`: eight tooling tests pass, including missing-tool/diff failures and rejecting incompatible historical/inference flags before private configuration access. Both actual offline wrappers report 5 PASS / 0 FAIL / 1 BLOCKED; service evidence remains deliberately blocked.
- `0007-compiled-build-integrity.patch`: confirmed pre-fix gap accepted modified compiled server bytes. Version-2 receipts bind source plus standalone/static output; tests reject modified, removed, added and linked artifacts, old receipts and malformed fields. Twelve deployment/backup/rollback/export tests pass. Older builds need rebuilding with local dependencies; symlinked dependency trees cannot be packaged.
- `0008-keyboard-investigation-flow.patch`: Chromium reproduced focus left behind after an investigation link. Corrected section/skip navigation transfers focus; at 1440/390px the trace event filter is the next Tab stop and the page has no horizontal overflow. Skipped-check notices remain explicit.
- `0009-final-readiness-checklist.patch`: extends the existing canonical web release checklist with evidence states, owner responsibilities and exact remaining integration/data/sponsor/security/backup/demo gates. It does not close tracker checkboxes.

Patched reasoning: **246 PASS**, including **16 actual-reference TEST-state memory cases**. Unchanged reference conformance: **13/13 PASS**. Django: **70 PASS**, with the two unchanged-original cases enabled locally. Rehearsal safety: **3 PASS**. A fresh nine-patch reproduction has exactly the same Git tree as the audited/tested tree (`5be9c3db0edf711b40a54f064ff31a052c7119c3`); applied-tree whitespace and owner-history/schema/config statics pass. Next production build/typecheck, matching compiled receipt, ratings/editorial/trace and TypeScript contracts pass locally. All four authenticated Chromium suites pass on that reproduced tree: original store/auth/correction/rollback, canonical fictional, skipped-check/keyboard and unchanged genuine v3 (all 28 roundup entries, zero stories, source links, trace/provenance and three widths). Hosted final-head CI is recorded in PR #6 and Issue #2; external-reference/private-original tests remain explicitly skipped in CI, not counted as operational integration.

Original snapshot and sidecar hashes were rechecked unchanged; their historical config mismatch was not reinvestigated. Full genuine acceptance, owner adoption, sponsor workflow, production bridge, live database, deployment/restore and final release remain BLOCKED or NOT TESTED as detailed in the proposed canonical checklist. No model/provider call, new collection, production credential access, service change, merge to integration/master or deployment occurred.


## Release-candidate profiles

See Decisions above for candidate profile policy.

```bash
python3 integration_support/rehearse.py --repo <checkout> \
  --destination <NEW-external-RC-path> --patch-profile web-owned --require-current
```

Fetch first, then use this profile: it does not contact any service itself. Patches 0003/0006/0007/0008/0009 are applied; owner-dependent 0001/0002/0004/0005 remain provisional review artifacts. `--with-proposed-patches` retains the separately labelled all-provisional audit profile. Neither profile approves integration, production publishing, or sponsor completion.


Release-candidate evidence and the timed private recording procedure are in [RELEASE_MATRIX.md](RELEASE_MATRIX.md) and [DEMO.md](DEMO.md). These supplement the canonical tracker/release checklist. The candidate applies five web-owned patches; full owner-patch tests and sponsor proposals remain separately labelled. Demo recordings, originals, captions, receipts and packaged releases remain outside Git.


For private submission editing, `demo_tour.cjs --scenes` accepts the same five paths/environment as the timed recorder and writes actual UI screenshots plus an explicit authenticated-stills receipt. It does not alter the product DOM or original snapshot/sidecar. It remains local-only and does not claim a timed video or sponsor completion.


Private submission tooling: `build_submission_video.py --raw <reviewed-genuine-movie> --scenes <authenticated-scene-directory> --output <NEW-external-package-directory> --ffmpeg <installed-encoder>` creates the 222-second WebM, burned/sidecar captions, exact recording script and edit manifest. Pillow and the installed official recorder encoder are used offline; no voice clone, model call or publication occurs. `prepare_submission_docs.py --repo <support> --candidate <local-RC> --root <package-directory> --scenes <scenes>` adds PDF/offline HTML slides, disclosures, setup/dependencies and a tracked-source archive. ReportLab is required only for document generation. Private originals and runtime auth/configuration are excluded; promotion/public upload still requires human review and genuine sponsor proof.


## V4 owner review — 2026-10-25 UTC

Canonical owner response: [Issue #2 comment 6391691017](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6391691017), read in full. Reasoning pin advanced to `25e3745`; the producer of genuine v4 is `88e3dcf`. Ordinary `--with-proposed-patches` now means `privacy-review` and excludes H-MEM. `--patch-profile hmem-review` is an explicit disposable proposal audit only; never adoption. Web-owned is unchanged except later web-owned safety amendments. The owner rejected memory hook adoption and requires three privacy amendments before acceptance.

The unadopted `docs/DECISIONS.md` hunk was removed from 0002 at Yelysei's explicit request: it depended on rehearsal-only context and preempted his go/no-go. Its history remains in previous support commits. Only Yelysei records the project adoption row if he accepts the feature. All actual owner decision history remains untouched.

H-MEM blockers: Windows TSX shell-launch incompatibility; timeout/process/store recovery policy; unapproved whole-store recall relevance/promotion; missing architecture definition of the memory trace/error stage. None is waived by reference conformance or prior TEST-state hook evidence. Default off, and no H-MEM hooks are applied to the primary candidate or ordinary CI profiles.

Privacy amendment 0010 implements Yelysei's three requested changes: bounded exception type and structured HTTP status, explicit raw snapshot `errors[].message` disclosure (portal projection alone redacts it), and lowercase failure wording in adjudication. HTTP status is never parsed from exception text. Eighteen focused tests and the 243-test reasoning suite pass on `25e3745` in a socket-blocked process. This is an owner-review amendment, not adoption permission.

Web-owned 0011 adds an exact-hash v4 editorial advisory and acceptance hold, preserving the producer score and strict validator. The known 6-versus-5 contradiction is never auto-corrected. Original v4 bytes were unavailable when the advisory was implemented: focused tests exercise the hold and metadata separation using explicitly synthetic inputs, not fabricated v4 data. The original closed-v4 file, sidecar, corrective v3 attestation and D5 report still require private handoff.
