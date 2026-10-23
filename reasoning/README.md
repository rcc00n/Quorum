# Reasoning block

The LangGraph graph that turns one day's collected documents for one topic into verified stories, a roundup and a snapshot for the portal. Design: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Product rules it implements: [docs/DECISIONS.md](../docs/DECISIONS.md) (handling facts, impact bar, stories as articles). Owner: Yelysei, branch `yelysei/agents`.

## Run it

```bash
cd reasoning
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# dry run: fixture corpus, deterministic stand-ins for every model call, no credits spent
python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run

# live run: reads the day's documents through Zetaris and calls Nemotron via the route in ../.env
python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22

python -m pytest                                      # rules + end-to-end dry run
python -m quorum_reasoning.run --mermaid              # the graph as Mermaid (docs/ARCHITECTURE.md § 5)
langgraph dev                                         # LangGraph Studio on the same graph
```

In Studio the input form has four fields: `topic_id`, `edition_date`, `dry_run` (switch it on unless you mean to spend credits) and an optional `run_id`. Submit with the first two empty and `plan` stops with a message saying so. The yellow "LangSmith API key is missing" banner is expected: tracing to LangSmith stays off (ARCHITECTURE.md § 9); the run's own trace is the `steps` list in the state. The **Deploy** button pushes the graph to LangChain's hosted platform (LangSmith Deployment); we do not use it — the graph runs on our own host.

Output: `snapshots/<topic>/<date>.json` (git-ignored) and the trace printed as a table. A committed copy of the dry-run output is `docs/examples/snapshot.sample.json`, the test dataset for the portal. Exit code 2 when the snapshot is `partial` (a node recorded an error).

Environment, all read from the repo-level `.env` (see `.env.example`): `MODEL_BASE_URL`, `MODEL_API_KEY`, `NEMOTRON_MODEL` (or the `METERLESS_*` names) for the model; `ZETARIS_REST_URL`, `ZETARIS_ORG_ID`, `ZETARIS_API_KEY` for the corpus; `ZETARIS_COLLECTION_DB` when the Lightning database is not `QUORUM_COLLECT`; `COLLECTOR_USER_AGENT` for fetching article text; `QUORUM_DRY_RUN=1` to force the dry run. With no model key configured the graph runs dry on its own.

## Layout

```
reasoning/
  langgraph.json              what `langgraph dev` loads: quorum_reasoning.graph:graph (module path; see Decisions)
  config/reasoning.toml       thresholds, caps, loop limits, forbidden words, model routes
  quorum_reasoning/
    graph.py                  StateGraph assembly, conditional edges, run_local(), mermaid()
    state.py                  RunState, DocRef, Claim, Evidence, Event, Rubric, StepRecord
    nodes/                    one file per node, each `run(state) -> partial state`; routes next to their node
    rules/                    confirmation.py, impact_bar.py, writing_rules.py — pure, unit-tested
    tools/                    corpus.py (Zetaris SQL or fixture), fetch_text.py (access levels, robots.txt)
    prompts/                  one Markdown system prompt per model task
    dryrun.py                 deterministic twin of every model task
    fixtures/sample_day.json  fictional corpus for the dry run and the tests
    trace.py, ids.py, text.py, llm.py, config.py, run.py
  tests/                      test_rules.py (rules), test_graph.py (end-to-end dry run, escalation, Mermaid)
```

Nodes: `plan → cluster → score_importance → extract_claims → research ⇄ verify → fact_check → adjudicate → (escalate →) frame → write ⇄ critique → roundup → publish`. Every node appends a `StepRecord` (node, iteration, event, decision, reason, model, duration); a loop shows as the same node with a higher iteration. The snapshot carries the whole trace.

## What a dry run shows

On the fixture day the trace shows every mechanism the architecture promises: a second research round for thin claims (`research` iteration 2, `verify` iteration 2), a blind fact-checker whose verdict differs from the verifier's on one claim (final status `disputed`, both chains kept), the critic rejecting a planted forbidden word in draft 1 and approving draft 2, two stories above the bar and two events in the roundup with their evidence status. The texts themselves are stand-ins; the real articles come from the model.

## Decisions

Module-level decisions (AGENTS.md § 2). Project-level ones are in `docs/DECISIONS.md`; one-line ones sit as `DECISION(...)` comments in the code.

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-23 | Yelysei / Claude Code | An evidence row carries the wire's independence group when the document has a `wire_origin` (lower-cased slug), not the reprinting outlet's own group. | A wire story plus its reprint counted as two independent groups and falsely confirmed a claim (red-team finding A1); DECISIONS.md › Principles for handling facts: ten reprints of one wire story are one piece of evidence. |
| 2026-10-23 | Yelysei / Claude Code | Official document ids are namespaced above 1 000 000 000 in the DocRef id space (`tools/corpus.OFFICIAL_ID_OFFSET`) and mapped back to the database id on evidence rows; a duplicate id in the day's corpus aborts the run. | `documents.id` and `official_docs.id` are separate Postgres sequences both starting at 1; in one id space every by-id lookup can silently pick the wrong document (red-team finding A2). |
| 2026-10-23 | Yelysei / Claude Code | A document another row supersedes (`supersedes_id`) is dropped from the day's corpus in `load_documents`; only the current version takes part. | Retracted text kept supporting claims after a correction arrived (red-team finding A8, use-case finding D3). Whether superseded rows should still count for spread, and whether corrections can arrive under new URLs, is open with Anastasia — see docs/reviews/2026-10-23-reasoning-review.md. |
| 2026-10-23 | Yelysei / Claude Code | `prompts/stance.md`: a passage that only relays an interested party's assertion ("officials said", "according to the ministry") is `statement`, not support. | Hearsay repeated by an outlet is the party's words with extra steps (red-team finding A10); the confirmation metric counts independent assertions, not relays. |
| 2026-10-23 | Yelysei / Claude Code | Evaluation set: 28 real claims (2026-10-09..22, topic russia-ukraine-war) in `quorum_reasoning/fixtures/eval/` with per-claim expected status justified by a quote, and a runner `tests/eval.py` that prints false confirmed, missed confirmed, disputed rate and above-bar-vs-expected before a confusion matrix. Dry run is the default and the CI mode; `--live` prints the model-call estimate and refuses without `--confirm-credits`. | Measure the pipeline instead of trusting it (review 2026-10-23, workstream C); routine checks spend no credits (AGENTS.md § 3). Provenance and limits in `fixtures/eval/README.md`. |
| 2026-10-22 | Yelysei / Claude Code | The package lives in `reasoning/` with the import name `quorum_reasoning`, not in `agent/` or `agents/`. | `agent/` already holds the setup-phase Zetaris tool and `agents` reads like the generic word; one folder per work block matches `collectors/` and the web branch. ARCHITECTURE.md § 9 updated in the same commit. |
| 2026-10-22 | Yelysei / Claude Code | Nodes are plain functions `run(state) -> dict` returning only the keys they change; routing functions live in the same file as the node they follow (`verify.route`, `adjudicate.route`, `critique.route`). | Keeps each loop readable in one place and lets the tests call a node without the graph. |
| 2026-10-22 | Yelysei / Claude Code | `escalate` goes on to `frame`, not straight to `roundup` as the first diagram in ARCHITECTURE.md had it. | The graph runs once per topic-day over all events; other events of the same run still need framing and writing. The escalated event itself is skipped by `frame`/`write` because it is no longer `above_bar`. Diagram regenerated from the code. |
| 2026-10-22 | Yelysei / Claude Code | Event confirmation points come from the best-supported claim (document or two groups → 2, one group → 1); the article's facts need each claim confirmed on its own. | Makes the escalation case real: an event can score 1–2 confirmation points on partial support and still have no confirmed claim, and then it is a roundup item flagged for review, never a story. |
| 2026-10-22 | Yelysei / Claude Code | The fact-checker has the same document access as the researcher but sees nothing the researcher or verifier produced; it picks its own passages and uses its own prompt role (`stance.md`, role `fact_checker`). | Independence of judgment, not less information: a fact-checker that reads less produces disputes about reading access rather than about facts. |
| 2026-10-22 | Yelysei / Claude Code | The critic is rule-based in this version (`rules/writing_rules.py`: block order, confirmed claims behind facts, sources, attribution, forbidden wording). A model pass for subtler evaluative language is an addition later, never a replacement. | A rule the critic enforces is the same rule the test checks; a model-only critic cannot be unit-tested and can be argued with. |
| 2026-10-22 | Yelysei / Claude Code | Every model task has a deterministic twin in `dryrun.py`; `QUORUM_DRY_RUN=1` or a missing key selects it. Draft 1 of every dry-run article carries a planted forbidden word. | The graph, its loops and the tests run without credits (AGENTS.md § 3: routine checks spend nothing), and the critic → writer loop is exercised on every run, not only when a model slips. |
| 2026-10-22 | Yelysei / Claude Code | Clustering uses cosine on title word sets with the model confirming a borderline band (`config/reasoning.toml › clustering`); no IDF, no leads. | See the `DECISION` note in `nodes/cluster.py`: leads carry each outlet's angle, and IDF in a one-topic corpus penalises the words that define an event. |
| 2026-10-22 | Yelysei / Claude Code | The snapshot carries `trace`, `errors`, `review_reason`, `critic_notes`, `drafts` and per-claim `found_by` on evidence, on top of ARCHITECTURE.md § 8. | The portal and the demo show how a story was arrived at; a `trace_ref` alone needs a second endpoint that does not exist yet. § 8 updated in the same commit. |
| 2026-10-23 | Yelysei / Claude Code | `langgraph.json` names the graph by module path (`quorum_reasoning.graph:graph`), not by file path. | `langgraph dev` loads a file path as a top-level module, so the package's relative imports fail (`attempted relative import with no known parent package`); the module path works because `dependencies: ["."]` installs the package. |
| 2026-10-22 | Yelysei / Claude Code | Storage is not in this version: `publish` builds the snapshot, `run.py` writes it to `snapshots/`; the `analysis` schema and the snapshot endpoint come next. | A snapshot file is enough for the portal adapter to start against; the Postgres store is additive. |
