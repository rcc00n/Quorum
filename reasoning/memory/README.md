# H-MEM source memory (reference engine sidecar)

Status 2026-10-26: adopted by Yelysei as the Meterless Engine working feature (Build rule; hand-over log
`docs/reviews/2026-10-26-meterless-engine-build.md`). Written by Vadim (rcc00n / Codex) as patches 0002, 0004 and 0012
on `support/offline-integration-hmem`, applied on `yelysei/meterless-engine` and adapted to the current code (Decisions
below). Label: *reference engine integrated as a sidecar, not a production implementation*. The flag stays `off`;
canonical editions run with it off. Not to be confused with Nightshift's runtime H-MEM injection, which live runs
switch off and refuse (`reasoning/README.md` › Decisions, 2026-10-25): this store is local, adds nothing to any prompt,
and its recall only reorders documents that research round 2 then judges afresh.

The text below is Vadim's proposal as written, kept so pointers to it stay valid.

## Proposal (Vadim, 2026-10-24)

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

## Decisions (adoption, 2026-10-26)

2026-10-26 · Yelysei / Claude Code (go: Yelysei 2026-10-26) · Adopted as the Build-rule feature: patches 0002, 0004 and 0012 applied as written (commit 378315a; only the two hunks that no longer applied, the `frame.py` return and `research.py`'s import and round-2 candidate line, re-placed by hand with Vadim's content). The flag stays `off` in `config/reasoning.toml`; dry mode never reaches the sidecar. Why: the Build rule needs one Meterless Engine in a working feature; this one writes what `frame` already produces and only reorders round-2 candidates, so the confirmation rule is untouched.

2026-10-26 · Yelysei / Claude Code (proposed by Claude Code, to confirm) · Answers to "Owner objections" above, which stay as written: the Node + `tsx/dist/cli.mjs` launcher is accepted, and native Windows execution is **not yet verified** (the engine-backed tests and the conformance runner had not run on Windows when this was written; see the hand-over log); the 20 s timeout, `quorum.lock` and `quorum.pending` stay fail-closed with no automatic replay or deletion, and the recovery procedure stays with the owner; recall uses threshold 0 over the whole store and changes only the order inside the ordinary ranked pool, under the unchanged `research.candidates_per_claim`, with the engine's relevance ordering recalled candidates among themselves; trace stage: one `memory` row after `frame` (event null) and one per thin claim in research round 2 (its event), and a memory failure is a run error with node `memory`, so that edition is `partial`. Known limit: the recall reply is capped at 2 MB and recall fails closed beyond it (ordinary ranking). Why: these were the open points Vadim named; each answer keeps the existing behaviour rather than adding policy two days before the deadline.

2026-10-26 · Yelysei / Claude Code · Adaptations to the current code: the sidecar's stdin and stdout are decoded as UTF-8 (`tools/memory._call`); a memory failure names its exception type through `untrusted.public_failure`, never its text (`tools/memory.remember`); the engine-backed tests skip exactly when `memory._launcher` cannot start the sidecar, and the symlink tests skip where the OS refuses to create a link (Windows without Developer Mode); `tests/test_source_memory_contract.py` proves default off, no sidecar call in any dry run (a whole fixture dry run with the flag forced on included) and candidate-only recall (fresh fetch and stance decide; a remembered `supports` never confirms; the cap is never widened) against an in-process stand-in of the sidecar contract. Decisions at those places. Why: on Windows `text=True` decodes cp1252 outside `python -X utf8`; the redaction rule of 2026-10-25 applies to every public failure; the guarantees must hold in the suite on machines without the reference checkout.

Conformance (Windows, from `<METERLESS_HOME>/engines/hmem/reference`, with `METERLESS_HOME` set): `HMEM_IMPL=<repo>/reasoning/memory/sidecar.mjs node node_modules/tsx/dist/cli.mjs ../conformance/runner.ts` (forward slashes, absolute path; exit 0 when green). The checkout must be the pinned revision of `scripts/checks.py` (`PIN`).
