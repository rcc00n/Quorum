# Offline integration support — owner review bundle

This branch is based on `integration@c3cc5ac`. It contains no rehearsal merge commits and does not duplicate any owner's application history. Executable patches are intended for the combined reasoning → collection → web tree after review. The canonical tracker remains GitHub Issue #2; project rules remain in root AGENTS.md.

## Patches

1. `0001-public-failure-privacy.patch` — Yelysei reviews. Confirmed synthetic failure: provider exception contents enter public trace reasons and third-review adjudication. The patch retains private StepError diagnostics and failure status/counts, while public operational reasons use a fixed safe message. Baseline: 222 reasoning tests; patched: 225 passing, with network blocked.

Apply to a clean disposable combined tree with `git apply --check <patch>` followed by `git apply <patch>`. Review and commit normally; these commands neither fetch nor merge any branch. Never apply automatically to an owner's worktree.

2. `0002-source-memory-hooks.patch` — Yelysei reviews graph/selection behavior; Anastasia reviews exact DocRef namespace/hash/access handling. Default off, zero requested/forced-dry writes, reference persistence/recall and existing-cap fresh re-verification. Nine TEST-state hook cases pass; patched reasoning suite 234/234; unchanged reference conformance 13/13 at engine `1742dec56a66e58eef9dda2d2b865823758ca8cd`. No genuine graph or sponsor completion claim. The patch includes its module README and proposed canonical decision entry; it does not overwrite the owner's go/no-go.

3. `0003-offline-diagnostics.patch` — Vadim reviews. Adds `--offline` to existing doctor/verify wrappers without reading private config or contacting service clients. Six tooling tests pass; each offline command returns five local PASS and one deliberately BLOCKED live-evidence item. `--offline --inference` is rejected before config access.

## Rehearsal pins

- integration: `c3cc5ac4a65855769ab48e36a1d59d5cc1ae261d`
- reasoning: `3d894488835b19b22281784cf8bf1e2ad5fa2be3`
- collection: `8f126c57a9ef9af798543bf23a0a60737b0ce5dc`
- web: `f59e75840c9aee67ca35a8f44bf5dd42747af75f`

Local merge sequence retained all owner decision-log rows verbatim and unioned additive environment/ignore entries. Development handover and production publication remain separate gates. The config-SHA audit in Issue #2 comment 6390549245 is accepted evidence and was not repeated. Original v3 files remain untouched.

## Decisions

2026-10-24 · rcc00n / Codex · Publish review patches and offline tooling on a branch based on integration, keeping rehearsal merges local. Why: owners can review/apply minimal changes without pushing their unmerged histories or the disposable merges through another PR.

## Reproduce safely

```bash
python3 -m unittest discover -s integration_support -p 'test_*.py'
python3 integration_support/rehearse.py --repo <existing-quorum-checkout> \
  --destination <NEW-external-disposable-path> --with-proposed-patches
python3 integration_support/check_tree.py --root <that-disposable-path>
```

The tool uses only the pinned local Git objects, creates a new detached worktree, resolves only the known additive conflicts, verifies every owner decision row, and optionally rehearses all three proposed patches. It never fetches, pushes or touches an existing destination. The new support CI repeats that exact process, tests the combined Python components on 3.11 with sockets blocked, and keeps web/production gates separate. Reference-HMEM and private-original tests are skipped when their external prerequisites are absent; local evidence below includes them.

Offline command checks prove local tooling only: their one BLOCKED item deliberately preserves the absence of live integration evidence. Static schema/enum and registry checks do not establish PostgreSQL migrations or live collection. Existing Nightshift receipts prove five historical tiny routing responses (four nonce probes reported uncached, explicit Ultra selected Ultra); they do not prove a complete Nightshift-powered reasoning workflow or receipt signature verification. No new inference request was made.
