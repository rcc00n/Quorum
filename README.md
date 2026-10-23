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

## Stack

| Layer | Technology |
| --- | --- |
| Data | [Zetaris](https://www.zetaris.com/) — one SQL layer over all sources |
| Reasoning | NVIDIA Nemotron via Meterless; additional LLMs for independent review where the rules allow |
| Reasoning orchestration | Python + LangGraph, LangGraph Studio for development and the demo; design in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), code in [`reasoning/`](reasoning/README.md) |
| Web | Next.js + TypeScript frontend; Django auth, API and Quorum Control |
| Development | Each team member uses their own AI assistant (Codex, Claude Code); shared rules in [AGENTS.md](AGENTS.md), organizer-update evidence in [docs/RULES_CHECK.md](docs/RULES_CHECK.md); one branch per member, `master` through pull requests |

## Repository layout

| Path | What it is |
| --- | --- |
| `docs/PORTAL_INTEGRATION.md` | Canonical collector/reasoning/portal handoff and proposed interfaces |
| `docs/RULES_CHECK.md` | Official Track 03/sponsor evidence and human-reported Cursor update |
| `docs/DECISIONS.md` | Product and architecture decisions, with a change log at the end |
| `docs/ARCHITECTURE.md` | Reasoning block: the LangGraph graph, rules, analysis schema, snapshot contract for the portal, build plan |
| `docs/SETUP.md`, `docs/SPONSOR_SETUP.md`, `docs/MANUAL_ACTIONS.md` | Local environment: WSL2, Docker, the official Zetaris platform bundle, remaining manual steps |
| `reasoning/` | The reasoning block: LangGraph graph, rules, prompts, dry-run fixture, tests; `reasoning/README.md` says how to run it |
| `agent/tools_zetaris.py` | Read-only Lightning SQL against the local Zetaris REST API |
| `smoke_test.py` | Checks the Data (Zetaris) and Power (Nemotron via Meterless/NVIDIA) layers from the participant setup guide |
| `scripts/` | `doctor.sh`, `verify-all.sh`, service helpers, security check |
| `reports/` | Dated environment readiness records |
| `AGENTS.md`, `CLAUDE.md` | Rules for AI coding assistants; `CLAUDE.md` only points to `AGENTS.md` |
| `.env.example` | Variable names only. Copy to `.env` (git-ignored) with your own values |

## Working agreements

Everyone on the team codes with a different AI assistant (Codex, Claude Code); the shared rules are tool-independent. To keep choices visible across tools, [AGENTS.md](AGENTS.md) requires every non-trivial decision to be recorded where it applies: project-wide ones in `docs/DECISIONS.md`, module-level ones in that folder's `README.md`, file-level ones as a `DECISION(...)` comment at the spot — in the same commit as the code, and never overriding someone else's decision silently. If a task contradicts `docs/DECISIONS.md`, change the decision first, then the code.

## Environment

Ubuntu-20.04 is confirmed as **WSL2**. Use the existing Linux Docker CLI and backend. Dependencies, the official Zetaris platform bundle, private deployment and credentials live outside version control. The deployment uses only the bundle's six required default services (including two one-shot jobs); The chosen Nemotron/Meterless route uses privately configured credentials; placeholders do not establish access.

```bash
./scripts/doctor.sh       # tools, WSL2, Docker, GitHub; no Cursor acceptance gate
./scripts/verify-all.sh   # doctor + memory/state tests + Zetaris checks; NO provider inference
# Optional: --inference explicitly sends one capped request with real sponsor credentials
```

Exit codes: `0` all checks passed, `1` at least one failure, `2` blocked or untested checks remain. Output uses `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`. Missing sponsor credentials intentionally produce `BLOCKED`. Cursor checks are historical opt-in (`python3 scripts/checks.py cursor-history`) and never affect routine summaries. The team reports that organizers removed mandatory Cursor; public rules still differ, so this is not independently verified. See [rules evidence](docs/RULES_CHECK.md).

Start with [setup](docs/SETUP.md), [sponsor configuration](docs/SPONSOR_SETUP.md), [manual actions](docs/MANUAL_ACTIONS.md) and the historical environment [readiness record](reports/readiness.md). The official platform is extracted and configured; registry login and RAM headroom still block startup on the prepared machine.

Environment readiness alone does not satisfy the hackathon's submission requirements: a 1–4 minute demo video, slides, this repository with a README, and an explanation of how the sponsor technologies were used (verify the current list on the challenge page in HackOS).

## Web portals

The Next.js user portal and Django **Quorum Control** are isolated in `web/` and `backend/`. Canonical handoff: [PORTAL_INTEGRATION.md](docs/PORTAL_INTEGRATION.md). Setup: [frontend](web/README.md), [backend](backend/README.md). VPS deployment and rollback: [deploy](deploy/README.md). Live data remains pending until the Zetaris adapter and reasoning contract are connected.
