# Quorum — AI-powered news intelligence & fact verification

**Shared release tracker: [GitHub Issue #2](https://github.com/rcc00n/Quorum/issues/2). All developers and coding assistants must follow [AGENTS.md — Shared Project Tracking and Cross-Agent Handoff](AGENTS.md#shared-project-tracking-and-cross-agent-handoff).**

Quorum is a multi-agent system that takes one news event, gathers coverage from sources across the political spectrum and official government documents, separates what is actually known from what is claimed, verifies statements against evidence, and shows how each part of the spectrum frames the same event. It does not ask the user to trust its answer: every substantive conclusion links to the sources it rests on.

Built by team **Quorum** for the [Open Agent Hackathon 2026](https://hackathon.genai.works/event/open-agent-hackathon-2026), Track 03 — **Reasoning Architecture**. Build window 22–27 October 2026; submissions close 27 October 2026, 23:45 UTC.

## What it does

- **Multi-source intelligence** — RSS, news APIs and official publications, federated through Zetaris so agents query everything as one SQL layer; publications are grouped by event.
- **Autonomous fact verification** — agents extract checkable claims, look for supporting and contradicting evidence, request more sources when needed, and separate confirmed facts from disputed and unverifiable ones. Reprints of a single wire story count as one piece of evidence, not ten.
- **Evidence-based reasoning** — every conclusion carries its sources and reasoning trace; when evidence is thin, the system says so instead of guessing. An independent fact-checker agent re-verifies claims without seeing the primary verifier's output.
- **Stories as articles** — each story is a short article built only from verified claims: facts with their sources, the parties' statements with their authors, and what is not confirmed, in a fixed order and with no evaluation added. Signed documents are facts; statements are statements. The reader forms their own view.
- **An impact bar, not a top ten** — up to ten stories a day per topic, shown only if they cross an absolute bar (legal force, reach, irreversibility, at least one independent source). No minimum: a quiet day says so. Everything below the bar goes into an "Also today" roundup, one line per event with its source.
- **Narrative & framing comparison** — as an appendix to each story: what left and right outlets highlight, omit and how they word it, by cohort (major/minor × left/right) under four selectable bias-rating modes (AllSides, MBFC, Ad Fontes, averaged).
- **A simple reader** — topics chosen by the user, one card per topic in the manner of Apple News, text instead of metrics; coverage, silence, evidence and reasoning traces one link away.

The full set of decisions — scope, principles, source list, cohort rules, UI, stack, demo plan, open questions — is in [docs/DECISIONS.md](docs/DECISIONS.md). That file is the source of truth; code that contradicts it is a bug.

## How the sponsor technologies are used

**Zetaris, the data layer.** The collectors write every publication and official record into PostgreSQL (`collectors/schema.sql`). That database is registered in the official Zetaris platform as the datasource `QUORUM_COLLECT` (`collectors/zetaris/register.py`, `collectors/zetaris/01_register_postgres.sql`), and everything downstream reads it only through Zetaris' Lightning SQL REST API (`agent/tools_zetaris.py`): the reasoning graph pulls an edition's corpus with `--corpus zetaris` (`reasoning/quorum_reasoning/nodes/plan.py` via `tools/corpus.py`), and `collectors/zetaris/evidence.py` runs the same two corpus queries without their text columns and writes a sanitised evidence file. Committed evidence: [`collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json`](collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json), a real query over the 2026-10-24 window (86 rows from 17 sources plus one official release; counts; titles cut to 80 characters; no text, no credentials), reconciled against reasoning's own `plan` row on a second machine in [Issue #2, 24 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6386233676). Zetaris runs on team members' machines, never on the public website.

**Meterless Nightshift, the AI provider.**

- *Route.* Every model call of the reasoning graph goes through one OpenAI-compatible route read from `.env` (`MODEL_BASE_URL`, `MODEL_API_KEY`, `NEMOTRON_MODEL`, or the `METERLESS_*` names; `.env.example`). With Nightshift that route is the local runtime (Nightshift 1.2.3, `http://127.0.0.1:8088/v1`), its Runtime token and the two headers Nightshift expects, `meterless-app` and `meterless-scope` (`smoke_test.py`, `reasoning/quorum_reasoning/llm.py`). `python -m quorum_reasoning.run --test-connection` is the preflight; NVIDIA's direct endpoint is the documented development alternative.
- *Models.* Two Nemotron models serve the graph's task lanes: Nemotron 3.5 Lightning on the worker lane, Nemotron 3 Ultra on the blind fact-checker and reviewer lanes (`reasoning/README.md` › Run it). The run ledger records for every call the model that answered and, on the Nightshift route, the receipt id and how many memories the runtime injected (`llm.py` ledger row: `served`, `receipt_id`, `receipt_hmem_injected`); a pinned lane answered by another model is an error row. Each receipt id is meant for Nightshift's Console › Proof (`reasoning/README.md` › Run it). As of 26 October no receipt has been looked up in the Console; Vadim validated the Ed25519 proof signatures of the 180 receipts in one local Nightshift journal under the runtime's supplied public key, which is not an independent NVIDIA or billing attestation ([Issue #2, 24 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6379478959)).
- *Evidence.* Five diagnostic completions, one per Nightshift route, each with a receipt id: the one on the explicit Ultra id was answered by Ultra, the four `meterless/*` dispositions by Lightning ([Issue #2, 23 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6376996285); no graph run). Reported in Issue #2 (counts only, the run files are private): a labelled showcase edition, `climate-policy` for 2026-10-26, through Nightshift from the PR #29 branch, 202 of 202 ledger rows carrying a receipt, 0 injected memories on every row after the guard set `hmemKnowledge` false before the first call ([Issue #2, 26 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6423850385)). The canonical editions of 26 October ran on NVIDIA's direct endpoint with the same code and models ([counts](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6418787032)).
- *Status (26 October).* The guard that keeps Nightshift's source memory out of independent verification is in the open PR #29 (`yelysei/agents` → `integration`, not merged). The Meterless Engine feature (an H-MEM source memory: `frame` writes framing labels and confirmed evidence, research round 2 recalls them as candidates only, off by default) is on the branch `yelysei/meterless-engine`, also unmerged.

**NVIDIA Nemotron** is the model family on both routes; the dry run (`--dry-run`) replaces every model call with a deterministic stand-in and spends no credits.

## Run it

One path through the whole system; each step is documented in its module. The collector and the reasoning block read the repo-level `.env` (`.env.example` lists their names); the portal takes its switches as exported environment variables (`backend/README.md`).

1. **Collect** (`collectors/README.md`): `docker compose -f collectors/docker-compose.yml up -d --build` starts PostgreSQL and the collector (one pass over every topic, then a 15-minute pause); with the official Zetaris platform running, `python3 collectors/zetaris/register.py` registers that database as `QUORUM_COLLECT`.
2. **Reason** (`reasoning/README.md`): from `reasoning/`, `pip install -e ".[dev]"`; a dry run with no credits, `python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run`; a live edition over the collected corpus (model route and `ZETARIS_*` settings in `.env`), `python -m quorum_reasoning.run --topic <topic> --date <date> --model live --corpus zetaris --out snapshots/_private`. The snapshot lands as the next immutable `v<N>.json`.
3. **Serve** (`backend/README.md`, `web/README.md`): Django on `127.0.0.1:8017`; then `bash deploy/build-web.sh` and, from `~/.local/share/quorum/portal-web-build`, `npm run dev -- --hostname 127.0.0.1 --port 3017`.
4. **Check an edition** (`backend/README.md`, `docs/PORTAL_INTEGRATION.md`, `docs/SNAPSHOT_PROPOSAL.md`): a reasoning 1.0 snapshot with its sidecar is checked read-only with `python backend/manage.py reasoning_snapshot --file … --sha256 … --sidecar … --sidecar-sha256 … --producer-commit …` (it never publishes; with `--install`, PR #31, it copies the accepted edition into the login-only reader's directory) and viewed in the development-only preview (`QUORUM_ENABLE_REASONING_PREVIEW=1`, `QUORUM_REASONING_PREVIEW_FILE=<snapshot>`, `DJANGO_DEBUG=1`, localhost, route `/preview/reasoning`). The portal's own store takes proposal-format snapshots: `portal_snapshot validate --file <candidate.json>`, then `portal_snapshot prepare` and `portal_snapshot publish --file $QUORUM_SNAPSHOT_ROOT/staging/<file> --sha256 <sha256>` behind the `QUORUM_ENABLE_SNAPSHOT_PUBLICATION` flag.

## Samples: inputs and outputs

| # | Input | Output | Content |
| --- | --- | --- | --- |
| 1 | The bundled fixture corpus of a normal day (`reasoning/quorum_reasoning/fixtures/sample_day.json`) | [`docs/examples/snapshot.sample.json`](docs/examples/snapshot.sample.json): two stories above the bar, two roundup items, one verifier/fact-checker disagreement resolved by the third blind reviewer, 47 trace rows | fictional, real shape |
| 2 | The quiet-day fixture (`--fixture usecases/quiet_day`) | [`docs/examples/snapshot.empty-day.sample.json`](docs/examples/snapshot.empty-day.sample.json): `status: empty`, no stories, every event in the roundup, 27 trace rows | fictional, real shape |
| 3 | The normal-day fixture of row 1 with every outlet-framing (`frame`) model call made to fail | [`docs/examples/snapshot.partial.sample.json`](docs/examples/snapshot.partial.sample.json): `status: partial`, the failed node and the two affected events named in `errors`, stories without framing labels | fictional, real shape |
| 4 | The collected corpus of 2026-10-24 for `russia-ukraine-war`, queried through Zetaris | [`collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json`](collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json): counts by source and type and a sanitised sample (no text, titles cut to 80 characters) | real |
| 5 | The post-cut corpus of 2026-10-26 (six topics in the dump, [comment](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6414086161)), restored into Zetaris ([comment](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6414901529)) | Five editions run over it, counts per edition in [Issue #2](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6418787032): one story above the bar (immigration), four quiet days; the files are private | real, private |

The fictional three are rebuilt with `python scripts/regenerate_samples.py` from `reasoning/` (`docs/examples/README.md`; last regenerated in `c0c3071`, 25 October); every file carries `provenance.fictional: true` and the portal labels such data as demo.

## Logs and traces

- **Trace in every edition.** A snapshot carries `trace`: one row per node execution with the node, iteration, event, decision, reason, model and duration, plus an optional `detail` (`reasoning/quorum_reasoning/trace.py`); from the 27 October runs the trace also carries `memory` rows. The fictional sample has 47 rows; the development-only reasoning preview (`/preview/reasoning`, `web/components/reasoning-timeline.tsx`) renders it as an Investigation Timeline per story. The public site shows no reasoning trace yet.
- **Journal, ledger, checkpoints.** A live run writes a journal of every request with its full payload (and, through Nightshift, its receipt) to `<out>/_journal/<run_id>.jsonl`, the ledger beside the snapshot as `v<N>.ledger.json` (task, lane, route, answering model, HTTP status, finish reason, tokens, attempts, receipt id, error) and per-node checkpoints in `<out>/_checkpoints/<run_id>.sqlite` (always on for a live run; `--checkpoint` turns them on for a dry run) (`reasoning/quorum_reasoning/run.py`, `llm.py`); `--verbose` prints each model call as it happens, `--resume` continues a live run from its last completed node. A dry run writes no journal.
- **Real runs.** Their files stay outside the public repository (`AGENTS.md` § 3): the journal holds full request payloads with article passages, the snapshots raw error diagnostics and verbatim quotes. Per edition the counts are posted in Issue #2: five editions of 26 October on NVIDIA's direct route, 0 failed calls ([comment](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6418787032)); the Nightshift showcase with receipts ([comment](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6423850385)).
- **Collector and data layer.** `docker compose -f collectors/docker-compose.yml logs -f collector`; sanitised Zetaris query evidence files via `collectors/zetaris/evidence.py` (written to `collectors/zetaris/evidence/<topic>_<date>.json`).

## Submission

- **Event:** Open Agent Hackathon 2026, Track 03 Reasoning Architecture; team Quorum: Vadim (@rcc00n), Anastasia (@AnastasiaShkirpan), Yelysei (@Sor1na). Submissions close 27 October 2026, 23:45 UTC.
- **Repository:** this one, with this README and the module READMEs. It starts on the evening of 21 October (UTC−5; 00:37 UTC on 22 October) with eight commits of environment scripts and docs (`15fe52b` and following); the product code was written in the build window of 22–27 October.
- **Demo video and slides:** the organisers require a 1–4 minute video with audio that shows Meterless doing work ([Issue #2](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6393551309)), plus slides. As of 26 October only a silent 3:42 captioned draft and a seven-slide PDF exist, both private ([Issue #2](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6390833160), [26 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6428420842)); the final video and slides are linked here once they exist.
- **Live portal:** https://quorum.raccncode.com (the landing is public; the reader behind it needs a login). It serves release `20261023-web-portals-09f5325` (`docs/RELEASE_CHECKLIST.md`, `deploy/STATUS.md`) with no real edition installed; a judges' login with real editions is planned with the submission ([Issue #2](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6426106426)).
- **Sponsor use:** the section above; the rules and organiser updates in `docs/RULES_CHECK.md`.

## Web Integration: Start Here

[Web handoff and owner notifications](docs/TEAM_HANDOFF.md) → [current adapter/contract](docs/PORTAL_INTEGRATION.md) → [reproducible tests](docs/PORTAL_VERIFICATION.md#current-reproducible-checks). Reasoning 1.0 preview is FICTIONAL/local-only; production publication remains disabled.

## Stack

| Layer | Technology |
| --- | --- |
| Data | [Zetaris](https://www.zetaris.com/) — one SQL layer over all sources |
| Reasoning | NVIDIA Nemotron (3.5 Lightning, 3 Ultra) through Meterless Nightshift as the primary provider; NVIDIA's direct endpoint is the documented development alternative (`.env.example`) |
| Reasoning orchestration | Python + LangGraph, LangGraph Studio for development and the demo; design in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), code in [`reasoning/`](reasoning/README.md) |
| Web | Next.js + TypeScript frontend; Django auth, API and Quorum Control |
| Development | Vadim uses Codex; team members use their own assistants (Codex, Claude Code); shared rules in [AGENTS.md](AGENTS.md), organizer-update evidence in [docs/RULES_CHECK.md](docs/RULES_CHECK.md); one branch per member, `master` through pull requests |

## Repository layout

| Path | What it is |
| --- | --- |
| `docs/PORTAL_INTEGRATION.md` | Canonical collector/reasoning/portal handoff and proposed interfaces |
| `docs/RULES_CHECK.md` | Official Track 03/sponsor evidence and human-reported Cursor update |
| `docs/DECISIONS.md` | Product and architecture decisions, with a change log at the end |
| `docs/ARCHITECTURE.md` | Reasoning block: the LangGraph graph, rules, analysis schema, snapshot contract for the portal, build plan |
| `docs/SETUP.md`, `docs/SPONSOR_SETUP.md`, `docs/MANUAL_ACTIONS.md` | Local environment: WSL2, Docker, the official Zetaris platform bundle, remaining manual steps |
| `docs/examples/` | Three dry-run reasoning snapshots (fictional content, real shape) with their regenerate commands; see [Samples](#samples-inputs-and-outputs) |
| `reasoning/` | The reasoning block: LangGraph graph, rules, prompts, dry-run fixture, tests; `reasoning/README.md` says how to run it |
| `agent/tools_zetaris.py` | Read-only Lightning SQL against the local Zetaris REST API |
| `smoke_test.py` | Checks the Data (Zetaris) and Power (Nemotron via Meterless/NVIDIA) layers from the participant setup guide |
| `scripts/` | `doctor.sh`, `verify-all.sh`, service helpers, security check |
| `reports/` | Dated environment readiness records |
| `AGENTS.md`, `CLAUDE.md` | Rules for AI coding assistants; `CLAUDE.md` only points to `AGENTS.md` |
| `.env.example` | Variable names only. Copy to `.env` (git-ignored) with your own values |

## Working agreements

Vadim uses Codex; other team members use their own assistants (including Claude Code); the shared rules are tool-independent. To keep choices visible across tools, [AGENTS.md](AGENTS.md) requires every non-trivial decision to be recorded where it applies: project-wide ones in `docs/DECISIONS.md`, module-level ones in that folder's `README.md`, file-level ones as a `DECISION(...)` comment at the spot — in the same commit as the code, and never overriding someone else's decision silently. If a task contradicts `docs/DECISIONS.md`, change the decision first, then the code.

## Environment

Ubuntu-20.04 is confirmed as **WSL2**. Use the existing Linux Docker CLI and backend. Dependencies, the official Zetaris platform bundle, private deployment and credentials live outside version control. The deployment uses only the bundle's six required default services (including two one-shot jobs); The chosen Nemotron/Meterless route uses privately configured credentials; placeholders do not establish access.

```bash
./scripts/doctor.sh       # tools, WSL2, Docker, GitHub; no Cursor acceptance gate
./scripts/verify-all.sh   # doctor + memory/state tests + Zetaris checks; NO provider inference
# Optional: --inference explicitly sends one capped request with real sponsor credentials
```

Exit codes: `0` all checks passed, `1` at least one failure, `2` blocked or untested checks remain. Output uses `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`. Missing sponsor credentials intentionally produce `BLOCKED`. Cursor checks are historical opt-in (`python3 scripts/checks.py cursor-history`) and never affect routine summaries. The team reports that organizers removed mandatory Cursor; public rules still differ, so this is not independently verified. See [rules evidence](docs/RULES_CHECK.md).

Start with [setup](docs/SETUP.md), [sponsor configuration](docs/SPONSOR_SETUP.md), [manual actions](docs/MANUAL_ACTIONS.md) and the historical environment [readiness record](reports/readiness.md). The official Zetaris platform runs on team members' own machines, each with the collectors' database registered as `QUORUM_COLLECT`: Anastasia's, where the collectors run and the committed evidence was queried, and Yelysei's, where each dump is restored and re-registered and the editions run over it ([Issue #2, 24 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6386233676), [26 Oct](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6414901529)).

Environment readiness alone does not satisfy the hackathon's submission requirements: a 1–4 minute demo video, slides, this repository with a README, and an explanation of how the sponsor technologies were used (verify the current list on the challenge page in HackOS).

## Web portals

The Next.js user portal and Django **Quorum Control** are isolated in `web/` and `backend/`. Canonical handoff: [PORTAL_INTEGRATION.md](docs/PORTAL_INTEGRATION.md). Setup: [frontend](web/README.md), [backend](backend/README.md). VPS deployment and rollback: [deploy](deploy/README.md). Editions produced by the reasoning block are not published on the site yet (the no-website-publication rule in `docs/DECISIONS.md` › Still to clarify, and the `QUORUM_ENABLE_SNAPSHOT_PUBLICATION` flag); the planned judges' reader behind a login is tracked in [Issue #2](https://github.com/rcc00n/Quorum/issues/2).
