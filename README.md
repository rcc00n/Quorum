# Quorum — AI-powered news intelligence & fact verification

Quorum is a multi-agent system that takes one news event, gathers coverage from sources across the political spectrum and official government documents, separates what is actually known from what is claimed, verifies statements against evidence, and shows how each part of the spectrum frames the same event. It does not ask the user to trust its answer: every substantive conclusion links to the sources it rests on.

Built by team **Quorum** for the [Open Agent Hackathon 2026](https://hackathon.genai.works/event/open-agent-hackathon-2026), Track 03 — **Reasoning Architecture**. Build window 22–27 October 2026; submissions close 27 October 2026, 23:45 UTC.

## What it does

- **Multi-source intelligence** — RSS, news APIs and official publications, federated through Zetaris so agents query everything as one SQL layer; publications are grouped by event.
- **Autonomous fact verification** — agents extract checkable claims, look for supporting and contradicting evidence, request more sources when needed, and separate confirmed facts from disputed and unverifiable ones. Reprints of a single wire story count as one piece of evidence, not ten.
- **Evidence-based reasoning** — every conclusion carries its sources and reasoning trace; when evidence is thin, the system says so instead of guessing. An independent fact-checker agent re-verifies claims without seeing the primary verifier's output.
- **Neutral news brief** — what happened, what interested parties claim, and what is still unknown, kept apart. Signed documents are facts; statements are statements.
- **Narrative & framing comparison** — what each source highlights, omits and how it words it, by cohort (major/minor × left/right) under four selectable bias-rating modes (AllSides, MBFC, Ad Fontes, averaged).
- **Dashboard** — topics chosen by the user, ten major events per topic per day, the spectrum of interpretations, coverage and silence per cohort, and drill-down into evidence and reasoning.

The full set of decisions — scope, principles, source list, cohort rules, UI, stack, demo plan, open questions — is in [docs/DECISIONS.md](docs/DECISIONS.md). That file is the source of truth; code that contradicts it is a bug.

## Stack

| Layer | Technology |
| --- | --- |
| Data | [Zetaris](https://www.zetaris.com/) — one SQL layer over all sources |
| Reasoning | NVIDIA Nemotron via Meterless; additional LLMs for independent review where the rules allow |
| App | Next.js + TypeScript |
| Development | Each team member uses their own AI assistant (Cursor, Codex, Claude Code); shared rules in [AGENTS.md](AGENTS.md) |

## Repository layout

| Path | What it is |
| --- | --- |
| `docs/DECISIONS.md` | Product and architecture decisions, with a change log at the end |
| `docs/SETUP.md`, `docs/SPONSOR_SETUP.md`, `docs/MANUAL_ACTIONS.md` | Local environment: WSL2, Docker, the official Zetaris platform bundle, remaining manual steps |
| `agent/tools_zetaris.py` | Read-only Lightning SQL against the local Zetaris REST API |
| `smoke_test.py` | Checks the Data (Zetaris) and Power (Nemotron via Meterless/NVIDIA) layers from the participant setup guide |
| `scripts/` | `doctor.sh`, `verify-all.sh`, service helpers, security check |
| `reports/` | Dated environment readiness records |
| `AGENTS.md`, `CLAUDE.md` | Rules for AI coding assistants; `CLAUDE.md` only points to `AGENTS.md` |
| `.env.example` | Variable names only. Copy to `.env` (git-ignored) with your own values |

## Working agreements

Everyone on the team codes with a different AI assistant. To keep choices visible across tools, [AGENTS.md](AGENTS.md) requires every non-trivial decision to be recorded where it applies: project-wide ones in `docs/DECISIONS.md`, module-level ones in that folder's `README.md`, file-level ones as a `DECISION(...)` comment at the spot — in the same commit as the code, and never overriding someone else's decision silently. If a task contradicts `docs/DECISIONS.md`, change the decision first, then the code.

## Environment

Ubuntu-20.04 is confirmed as **WSL2**. Use the existing Linux Docker CLI and backend. Dependencies, the official Zetaris platform bundle, private deployment and credentials live outside version control. The deployment uses only the bundle's six required default services (including two one-shot jobs); Nemotron must use organizer-supplied Meterless access.

```bash
./scripts/doctor.sh       # tools, WSL2, Docker, GitHub, Cursor installation
./scripts/verify-all.sh   # doctor + memory/state tests + Zetaris checks; NO provider inference
# Optional: --inference explicitly sends one capped request with real sponsor credentials
```

Exit codes: `0` all checks passed, `1` at least one failure, `2` blocked or untested checks remain. Output uses `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`. Missing sponsor credentials intentionally produce `BLOCKED`.

Start with [setup](docs/SETUP.md), [sponsor configuration](docs/SPONSOR_SETUP.md), [manual actions](docs/MANUAL_ACTIONS.md) and the latest [readiness record](reports/readiness.md). The official platform is extracted and configured; registry login and RAM headroom still block startup on the prepared machine.

Environment readiness alone does not satisfy the hackathon's submission requirements: a 1–4 minute demo video, slides, this repository with a README, and an explanation of how the sponsor technologies were used (verify the current list on the challenge page in HackOS).
