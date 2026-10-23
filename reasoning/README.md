# Reasoning block

The LangGraph graph that turns one day's collected documents for one topic into verified stories, a roundup and a snapshot for the portal. Design: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Product rules it implements: [docs/DECISIONS.md](../docs/DECISIONS.md) (handling facts, impact bar, stories as articles). Owner: Yelysei, branch `yelysei/agents`.

## Run it

```bash
cd reasoning
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# dry run: fixture corpus, deterministic stand-ins for every model call, no credits spent
python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run

# live model on the fixture corpus: tries the prompts and the JSON parsing before collection has data
python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --model live --corpus fixture

# live run: the day's documents through Zetaris, Nemotron via the route in ../.env
python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-23 --model live --corpus zetaris

python -m pytest                                      # rules + end-to-end dry run
python -m quorum_reasoning.run --mermaid              # the graph as Mermaid (docs/ARCHITECTURE.md § 5)
langgraph dev                                         # LangGraph Studio on the same graph
```

`--fixture usecases/quiet_day` (or `QUORUM_FIXTURE`) picks another bundled day for `--corpus fixture`; the use-case days under `fixtures/usecases/` are the ones `tests/test_usecases.py` asserts on.

Two independent switches: the model axis (`--model dry|live`; `dry_run` in the state; `QUORUM_DRY_RUN=1` or a missing key forces dry) and the corpus axis (`--corpus fixture|zetaris`; `corpus` in the state; defaults to fixture when the model is dry, zetaris otherwise). `--dry-run` is the shortcut for dry + fixture.

In Studio the input form has five fields: `topic_id`, `edition_date`, `dry_run` (switch it on unless you mean to spend credits), `corpus` (fixture or zetaris) and an optional `run_id`. Submit with the first two empty and `plan` stops with a message saying so. The yellow "LangSmith API key is missing" banner is expected: tracing to LangSmith stays off (ARCHITECTURE.md § 9); the run's own trace is the `steps` list in the state. The **Deploy** button pushes the graph to LangChain's hosted platform (LangSmith Deployment); we do not use it — the graph runs on our own host.

Output: `snapshots/<topic>/<date>.json` (git-ignored) and the trace printed as a table. A committed copy of the dry-run output is `docs/examples/snapshot.sample.json`, the test dataset for the portal. Exit code 2 when the snapshot is `partial` (a node recorded an error).

Environment, all read from the repo-level `.env` (see `.env.example`): `MODEL_BASE_URL`, `MODEL_API_KEY`, `NEMOTRON_MODEL` (or the `METERLESS_*` names) for the model — the Nightshift URL and Runtime token from its Console, never the NVIDIA key, which lives in Nightshift's Providers tab; `NEMOTRON_MODEL_FACT_CHECKER` for the second lane; `python -m quorum_reasoning.run --models` lists the routes the hotspot offers and `--test-connection` shows which model answers on each lane; `ZETARIS_REST_URL`, `ZETARIS_ORG_ID`, `ZETARIS_API_KEY` for the corpus; `ZETARIS_COLLECTION_DB` when the Lightning database is not `QUORUM_COLLECT`; `COLLECTOR_USER_AGENT` for fetching article text; `QUORUM_DRY_RUN=1` to force the dry run. With no model key configured the graph runs dry on its own.

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
| 2026-10-23 | Yelysei / Claude Code | Roundup status labels follow the vocabulary of DECISIONS.md › Selecting major news: `Disputed` is a label and a group (after `Confirmed`), and an event whose documents span one independence group (wire reprints counted in the wire's group) is `Single source` even when no claim gathered evidence. `Unverified` stays as the label of last resort. | A single-outlet scoop was labelled `unverified` and a disputed below-bar event could never show `disputed` (use-case findings D1, D2); the reader loses the one-outlet warning and the dispute. `docs/examples/snapshot.sample.json` regenerated in the same commit. |
| 2026-10-23 | Yelysei / Claude Code | Untrusted-text layer in `quorum_reasoning/untrusted.py`, wired into every node that builds a model payload or reads a model reply: payload text fields are labelled as data and length-capped; a model-returned stance must be one of the four stance words (else neutral); an extracted claim is kept only when its origin id names a document of its event and its words are found in that document (`grounded_in`, near-match); article source URLs are restricted to URLs the state knows; `cluster` merges only on boolean true; at most 12 claims per event. Every rejection fails safe — toward neutral, dropped or below the bar, never toward confirmed. | Fetched text is hostile input (review 2026-10-23, workstream B, findings B1–B9); tests/test_injection.py holds the attacks. |
| 2026-10-23 | Yelysei / Claude Code | `llm.json_task` parses the model reply as the last balanced JSON object in the text, not the span from the first `{` to the last `}`. | A reply baited into echoing attacker-shaped JSON before its answer merged the two objects and failed, or carried the attacker's keys (finding B7); the last balanced object is the model's own answer. |
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
| 2026-10-23 | Yelysei / Claude Code | Model access follows the Meterless Runtime contract (Setup Guide § 4.5): one hotspot, `meterless-app` and `meterless-scope: user` headers, 180 s timeout, routes read from `GET /v1/models`. Two lanes by env: `NEMOTRON_MODEL` for every task, `NEMOTRON_MODEL_FACT_CHECKER` for the blind second check — pin two different Nemotron routes, not `meterless/auto`. | `meterless/auto` may route to a non-NVIDIA model and makes award evidence ambiguous; a second lane on a different model is the cheapest real independence for the fact-checker. |
| 2026-10-23 | Yelysei / Claude Code | Article text comes from `collectors.common.fetch_text` (one fetcher, one extractor, one `content_hash` for the project); the own fetcher stays only as a named fallback; texts are cached per run and never across runs. Zetaris tables are addressed as `QUORUM_COLLECT.<table>`, the way `collectors/zetaris/01_register_postgres.sql` registers them. | Raised by Vadim: two extractors give two texts for one URL and quotes cut from one cannot be verified against the other; the `public.` segment never existed in the registration. |
| 2026-10-23 | Yelysei / Claude Code | The model axis (`dry_run`) and the corpus axis (`corpus`) are separate switches; a document that carries `text` is read from it in any mode. | A live model on the fixture corpus is how prompts and JSON parsing are tried before collection has data, without waiting on Zetaris; a live corpus with stand-ins checks the SQL without credits. |
| 2026-10-23 | Yelysei / Claude Code | `langgraph.json` names the graph by module path (`quorum_reasoning.graph:graph`), not by file path. | `langgraph dev` loads a file path as a top-level module, so the package's relative imports fail (`attempted relative import with no known parent package`); the module path works because `dependencies: ["."]` installs the package. |
| 2026-10-22 | Yelysei / Claude Code | Storage is not in this version: `publish` builds the snapshot, `run.py` writes it to `snapshots/`; the `analysis` schema and the snapshot endpoint come next. | A snapshot file is enough for the portal adapter to start against; the Postgres store is additive. |
