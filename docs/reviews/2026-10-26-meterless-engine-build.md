# Meterless Engine working feature (Build rule): work log and hand-over

Owner: Yelysei (reasoning). Branch: `yelysei/meterless-engine`, cut from `yelysei/agents` at 522f848 (the head of PR #29). Go decision: Yelysei, 2026-10-26.

This file is the hand-over. Anyone, human or assistant, who picks the work up reads this first and updates the **Status** section at every step. Commit and push the branch after each step, so the work is never only on one machine.

## Goal

Meet the Build rule (DECISIONS.md › Still to clarify; proposal in [2026-10-24-meterless-engine-proposal.md](2026-10-24-meterless-engine-proposal.md)): at least one Meterless Engine is integrated in a working feature, and its conformance suite passes.

The feature is **H-MEM source memory**:
- `frame` writes each outlet's framing label, and the evidence behind confirmed claims, into H-MEM;
- research round 2 may recall earlier evidence **as candidates only**. A recalled item is re-fetched and re-judged under the ordinary confirmation rule; memory never confirms anything by itself;
- the feature sits behind the flag `[engines] hmem = "off" | "on"` in `reasoning/config/reasoning.toml`. Dry mode never touches it.

## Starting point: Vadim's proposed patches

Vadim (rcc00n / Codex) already wrote these hooks as patches for owner adoption. They are on `origin/support/offline-integration-hmem` (draft PR #6):

- `integration_support/patches/0002-source-memory-hooks.patch`: `reasoning/memory/sidecar.mjs`, `reasoning/memory/README.md`, `reasoning/quorum_reasoning/tools/memory.py`, the hooks in `nodes/frame.py` and `nodes/research.py`, the flag, `tests/test_source_memory.py`;
- `integration_support/patches/0004-memory-storage-safety.patch`: fail-closed storage and exact identity checks;
- `integration_support/patches/0012-hmem-portability-inspection.patch`.

Read them with `git show origin/support/offline-integration-hmem:integration_support/patches/<file>`. We adopt them as the base, credited to Vadim. Then we adapt them to the current code, which has the seed rule, the public-failure redaction and the H-MEM guard.

## The reference engine (outside the repository)

- Official repository: `github.com/Meterless/Meterless`, folder `engines/hmem`. Put the checkout **outside** this repository, for example `C:\Users\eshki\Projects\meterless-hmem`, and point `METERLESS_HOME` at it in your own `.env`. Never commit it.
- Conformance: `HMEM_IMPL=<path> npx tsx <checkout>/conformance/runner.ts`. It exits 0 when green; Vadim recorded 13/13 PASS on the unchanged reference.
- Honest label: *"reference engine integrated as a sidecar, not a production implementation"*.

## Steps

1. [ ] Get the reference engine checkout; record its commit.
2. [ ] Apply 0002, 0004 and 0012 onto this branch (`git apply --3way`), resolve against the current code, and credit Vadim in the commit message.
3. [ ] Full reasoning suite green; `tests/test_source_memory.py` green, with `METERLESS_HOME` set.
4. [ ] Conformance run against the engine actually used, recorded below with its exit code, the checks, the engine commit and the date.
5. [ ] A live check with `[engines] hmem = "on"` on one cheap topic-day. Use a separate `--out`, never the canonical store. The trace must show `memory` rows, and recall must stay candidate-only.
6. [ ] Record the work:
   - DECISIONS.md: › Still to clarify (Build rule met, with its scope) and a log row;
   - `reasoning/README.md` › Decisions;
   - the ARCHITECTURE note.
7. [ ] Open a PR into `integration` (or add the work to PR #29), and post a tracker comment in Issue #2: REASON-ENGINE-01.

## Rules that still apply

- AGENTS.md as a whole.
- No secrets in output.
- Live model runs only with Yelysei's word. The live check in step 5 is part of this go.
- Canonical editions stay on the NVIDIA direct route.
- The memory store directory (`QUORUM_HMEM_DIR`) lives outside the repository.

## Status

- 2026-10-26 18:3xZ: branch created from 522f848; this file written. Next: step 1.
