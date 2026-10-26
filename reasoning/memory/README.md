# Proposed H-MEM source-memory hooks

Owner review required: Yelysei (graph/selection policy) and Anastasia (DocRef namespace/provenance). Default `[engines] hmem = "off"`; forced or requested dry mode returns before any subprocess or store access. This patch does not enable memory for an existing run.

Opt-in prerequisites: existing official reference checkout in `METERLESS_HOME`, its installed TSX (or `QUORUM_HMEM_TSX`), and a new dedicated absolute `QUORUM_HMEM_DIR` outside the repository. No downloads, service, credentials, corpus transfer or inference are needed for offline validation.

`frame` writes actually present attributed framing and supporting evidence of confirmed fact/number claims from internal state. Exact original article/official IDs, source URL/group, publication/hash/access metadata and quote bindings are retained. No synthetic story is needed; zero eligible records truthfully records zero writes. The unchanged reference HMEM class persists records and ledger. Duplicate imports are idempotent. A pending write or occupied lock fails closed; partial stores need owner inspection, not automatic replay.

Research round 2 can prioritize only recalled records that exactly match an authorized current DocRef in the ordinary ranked pool, within the existing edition/history window. Superseded, wrong-namespace, unknown-source, changed-metadata and mismatched fictional records cannot be injected. Memory changes candidate order only when opted in; the existing candidate cap remains unchanged. Selected documents continue through existing fetch, stance, quote/hash/access and independence logic. No remembered verdict or quote is copied into evidence.

Audit rows use the existing `memory` trace node shape with counts and reference-ledger action counts; no snapshot/API fields are added. Failure retains ordinary ranking, emits an honest partial error and withholds private exception contents. The reference implementation is a deterministic reference component, not production storage.

Run `METERLESS_HOME=<existing-checkout> <reasoning-python> -m pytest reasoning/tests/test_source_memory.py -q`. Run the installed TSX with `HMEM_IMPL=<this-directory>/sidecar.mjs` against the official conformance runner. Tests use explicit TEST records and stub model/fetch responses; reference persistence/recall is real. Genuine graph adoption and sponsor compliance remain unverified until the owner approves, executes an authorized genuine workflow and records its evidence. Original v3/config attestation remains separate and blocked.

## Decisions

2026-10-24 · rcc00n / Codex · Propose local subprocess reference-memory hooks at frame/write and research-round2 retrieval; never import recalled evidence or change confirmation rules. Why: exercise the existing owner proposal with exact source provenance and bounded re-verification while preserving default-off/dry behavior and strict snapshot fields.

### Owner objections — no adoption

The default launcher proposal uses `node .../tsx/dist/cli.mjs` instead of the
POSIX `.bin/tsx` shell shim. Linux reference tests and argv-with-spaces tests do
not establish native Windows execution; Yelysei must verify that environment.
The 20-second timeout still fails closed: inspect `quorum.lock`, `quorum.pending`
and the reference ledger privately after a stopped child. Do not delete either
marker or retry writes automatically. Recovery policy remains an owner decision.
Recall relevance, whole-store promotion and the architecture's memory trace/error
stage are unresolved; this patch does not approve a threshold or policy. The
project-level adoption decision is deliberately absent and belongs to Yelysei.
