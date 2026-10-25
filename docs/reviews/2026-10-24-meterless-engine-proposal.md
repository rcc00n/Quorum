# Meterless Engine working feature — proposal (Build rule), 2026-10-24

Owner: Yelysei (reasoning). Status: PROPOSED, go / no-go pending. Written by Yelysei / Claude Code from the public
Meterless repository (`engines/hmem/AGENTS.md`, `engines/hmem/README.md`, `engines/hmem/conformance/README.md`,
`engines/hmem/reference/README.md` at `github.com/Meterless/Meterless`, read 2026-10-24) and from Vadim's
HMEM-RECALL-POC (Issue #2, FULL-REAL-01: external working proof of concept over the reference engine, conformance
13/13 PASS on his machine). No Meterless checkout exists on Yelysei's machine (`METERLESS_HOME` is empty); the
proposal needs one (`npx degit meterless/meterless/engines/hmem <dir>` outside the repository).

## The rule

DECISIONS.md › Still to clarify: *at least one Meterless Engine (H-MEM, Markovian, World Model or Scout Intent)
integrated in a working feature with its conformance suite passing; nothing in Quorum satisfies it yet.* Nightshift
provider routing (the Power rule) is a separate requirement and does not count; neither do the reference
persistence smoke tests in `scripts/meterless-persistence.mjs` (they check the reference component, not a feature).

## What H-MEM is, in the engine's own terms

A memory record store with provenance (`source`, `confidence`, `provenance.origin`, `supersedes`/`supersededBy`,
`derivedFrom`), three tiers (short-term, working, long-term), hybrid retrieval over eight signals, a trust ledger
of 17 action types, dreaming (proposals that need human approval) and a sleep cycle. The repository is a spec with
a deterministic TypeScript reference implementation (zero dependencies, JSON persistence, hash embedder) and a
conformance runner (`HMEM_IMPL=<path to index.ts> npx tsx runner.ts`) that asserts the spec's arithmetic and
behaviour contracts; it exits 0 when green. The module under test must export an `HMEM` class with `add`, `query`,
`feedback` and the `store`, `ledger`, `sleep`, `dreaming`, `conflicts` services.

## The feature: source memory behind research round 2 and the framing history

Two things Quorum already produces every day are exactly what a memory with provenance is for, and both are things
DECISIONS.md says must accumulate from day one:

1. **Per-source interpretation labels per event per day** (`frame`: `interpretation_label`, `highlights`, `omits`,
   `wording` per outlet) — the raw material of "shift in party positions over time" (DECISIONS › After the
   hackathon: *from day one, each source's and cohort's interpretations are stored by day*). Today they live only
   inside each day's snapshot.
2. **Evidence hits from earlier days** — research round 2 now reads the previous two edition windows through SQL
   (work item E4). A memory of which documents supported which claim, with the quote's hash and offsets as
   provenance, is the recall that lets round 2 start from what earlier days already established instead of
   re-scanning every document.

Feature as the user sees it: on the topic page, under a story, "Earlier coverage: <outlet> framed the same event as
'<label>' on <date>" and, in the trace, a `memory` row per research round 2 saying which earlier evidence H-MEM
recalled and which the run then re-verified against the current text. Memory is **candidate retrieval only**: a
recalled quote is re-fetched and re-judged under the ordinary confirmation rule before it counts; a remembered
title never becomes a verified fact (Vadim's caveat in FULL-REAL-01, adopted).

## Integration shape

- A small Node sidecar, `reasoning/memory/` (TypeScript, the reference engine vendored or imported from the
  checkout), exposing a JSON-lines CLI: `add`, `query`, `feedback`, `ledger`. Python calls it per run through
  `subprocess` (`tools/memory.py`); no HTTP service, no new port.
- Records: one per (source, event, edition_date) framing label with `provenance.origin = "frame"`,
  `source = <snapshot run_id>`, entities = [source_id, event_id, topic_id]; one per evidence row that supported a
  confirmed claim with the quote hash and offsets in `tags`; `supersedes` set when a later run of the same
  topic-day replaces a record (versions are immutable, memories are superseded, never deleted).
- Persist directory outside the repository (`QUORUM_HMEM_DIR`, git-ignored), one JSON store per topic.
- Flag `[engines] hmem = off | on` in `config/reasoning.toml`; **dry run never touches it**; with `on`, the trace
  shows one `memory` row per read and one per write (counts, recall reasons, ledger action ids).
- Conformance: `HMEM_IMPL=<reasoning/memory/src/index.ts> npx tsx <checkout>/engines/hmem/conformance/runner.ts`
  recorded in `docs/reviews/` with the run's output (exit code, 13 checks), the engine HEAD it was run against and
  the date. With the reference engine wrapped unchanged this is green by construction; the honest label is
  *"reference engine integrated as a sidecar, not a production implementation"*, and the write-up says so.

## Effort and risk

| Step | Effort | Risk |
| --- | --- | --- |
| Checkout, sidecar CLI over the reference engine, `tools/memory.py`, flag, trace rows | half a day | low: deterministic reference, zero deps |
| Writes from `frame` and from confirmed evidence; reads in research round 2 as candidates | half a day | medium: the recall must stay candidate-only; tests must prove a remembered quote never confirms without re-verification |
| Conformance run recorded; DECISIONS row; ARCHITECTURE § 7/§ 9; Issue #2 owner comment | 2 hours | low |
| Portal: "Earlier coverage" line | Vadim's, optional for the rule | — |

Total about a day of work after the first genuine live run (D4), which has priority. Risk to the 27 Oct deadline:
medium. Doing it before D4 would put the Build rule ahead of the product gate; doing it after leaves one day.

## Alternative considered: World Model for the shared event/claim state

A World Model engine would hold the event/claim graph itself; Quorum's state already is that graph (LangGraph
state, snapshot). Replacing it two days before the deadline is not credible; wrapping it would be a facade. Not
recommended.

## Decision needed from Yelysei

- **Go**: implement behind the flag after D4 as above; record a DECISIONS row (feature, owner, conformance
  evidence) and answer Vadim's owner question on Issue #2 with the feature name.
- **No-go**: record in DECISIONS › Still to clarify that the Build rule is DEFERRED with the reason (time after the
  genuine run), answer Vadim's question plainly (owner Yelysei, feature not built, reference smoke tests are not
  the feature), and say so in the submission write-up rather than imply it.
