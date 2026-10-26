# Rules for AI coding assistants

This file is the single rulebook for every AI assistant working in this repository: Cursor, Codex, Claude Code, Copilot or anything else. Cursor and Codex read it directly; `CLAUDE.md` only points here. Do not create a second rulebook, and do not put project rules anywhere else.

## 1. Project

- Quorum is an AI-powered news intelligence and fact-verification system, built for the Open Agent Hackathon 2026, Track 03 "Reasoning Architecture". Build window 22–27 October 2026; submissions close 27 October 23:45 UTC.
- Product and architecture decisions live in [docs/DECISIONS.md](docs/DECISIONS.md). Read it before changing anything that touches product behaviour, data, agents, sources, scoring or UI.
- If a task contradicts `docs/DECISIONS.md`, do not improvise and do not pick the "more sensible" option silently. Stop, tell the human what conflicts, and let them change the decision first.

## 2. Decisions: record them where they apply

Every team member works with a different AI assistant. A choice made silently inside one tool is invisible to the others and gets redone differently somewhere else. So every non-trivial decision is written down at the level where it applies, in one canonical place, with pointers elsewhere.

| Scope of the decision | Where to record it | Format |
| --- | --- | --- |
| Project-wide: product scope, agent roles and loops, data model and schema, API contracts, stack, source list, scoring formulas, naming of core concepts | `docs/DECISIONS.md`: edit the relevant section **and** add a row at the top of the "Decision log" table | date · human / tool · what · why |
| One module or folder: how `agent/` is structured, which library a folder uses, conventions local to it | `README.md` inside that folder, section `## Decisions` (create it if missing) | same fields, one line per decision |
| One file, function or query: a threshold, a workaround, a non-obvious choice | A comment at that spot: `DECISION(2026-10-23, <name>/<tool>): <what>. Why: <reason>.` | one or two lines, right where the code is |

Rules:

- **Author** is the human running the assistant (their `git config user.name`), **tool** is the assistant (Cursor, Codex, Claude Code, …). Never a bare "AI" or "agent".
- Record the decision in the **same commit** as the code that implements it. A decision without code and code without its decision are both incomplete.
- **Never change or delete someone else's decision silently.** Edit the entry, mark the old one `superseded <date>` and keep it, so pointers in code stay valid. If you disagree with it, say so to the human instead of working around it.
- **Do not duplicate.** One canonical entry; everywhere else a pointer such as `see docs/DECISIONS.md › Sources`.
- Do not record the trivial (variable names, formatting, obvious library calls). Record what another person would otherwise redo differently: thresholds, formats, contracts, excluded options, workarounds.
- If you are unsure whether something is a decision, it is. A one-line entry is cheap; a silent fork is not.
- Everything in the repository is written in English: code, comments, docs, decision entries, commit messages. Team chat may be in any language; what lands in the repo is English.

## 3. Working rules

- Use one agent. Reuse installed tools, consult relevant official docs, and limit external operations to two attempts.
- Prefer small reversible changes. Do not modify unrelated services or occupied ports.
- Keep vendor checkouts, dependencies, credentials, models, logs and runtime data outside this public repository. Never print secrets or commit private configuration. Secrets live in a local `.env` (git-ignored); `.env.example` holds placeholders only.
- Run scripts/doctor.sh and targeted scripts/verify-all.sh checks. Missing credentials are BLOCKED; only actual successful requests pass. Never present mocks as operational integrations.
- Inspect staged paths, diffs, secret patterns and file sizes before committing. Preserve remote history/default branch; never force-push.
- Environment readiness does not establish hackathon submission compliance.

## 4. Environment rules (from the setup phase)

- Inspect actual WSL version. Never convert WSL, replace Docker backends, start a Linux daemon on WSL1, expose Docker over unauthenticated TCP, or enable paid services without authorization.
- Use the newly downloaded official Zetaris platform bundle (supersedes Freemium), with the organizer's Data layer and Meterless→Nemotron Power layer. Use the bundle's required default services and official preflight/verify scripts after resource/authentication checks; preserve supplied environment values. Never put Meterless keys in Cursor settings. Inference is opt-in (`--inference`); routine diagnostics must spend no provider credits.
- Disk cleanup must preserve all user projects/data, models needed for the statistics exam, Docker containers/volumes and files created or modified since 2026-04-21. Windows deletions and WSL memory changes require explicit approval.

## Shared Project Tracking and Cross-Agent Handoff

The canonical cross-team release tracker is [GitHub Issue #2](https://github.com/rcc00n/Quorum/issues/2). It is shared across branches and computers; do not create a competing tracker or agent rulebook.

Every coding assistant must:

1. Before development, read Issue #2, the latest canonical `AGENTS.md`, `docs/DECISIONS.md`, its module README and relevant interface contracts. Fetch remote state and inspect other team branches read-only; identify the tracker items it owns.
2. Work only in its authorized scope/branch: Vadim — `feature/web-portals` (web/platform); Anastasia — `data-collection`; Yelysei — `yelysei/agents`. Do not edit another owner's branch, code or decisions without agreement. For the final assembly a shared branch `integration` (cut from `master`, agreed in Issue #2 on 2026-10-24) is written only through pull requests from the owner branches in the order reasoning → collection → web, with merge commits; small compatibility fixes directly on it are allowed when they carry a decision record and the affected owner is told in Issue #2; `integration` reaches `master` through one reviewed pull request.
3. Record progress as work proceeds. Give every feature a stable identifier, owner, explicit status, branch, commit/PR, relevant test evidence, operational evidence when applicable, remaining dependencies and release impact. Update assigned checklists only after verifying completion; preserve existing checked items and their evidence.
4. Use `NOT_STARTED`, `IN_PROGRESS`, `IMPLEMENTED` (code exists), `TESTED` (relevant tests pass), `INTEGRATED` (actual required components work together), `DEPLOYED` (verified in the intended environment), `BLOCKED` (name the concrete dependency), or `DEFERRED`. These are evidence states, not interchangeable claims. Fixtures, mocks and prepared scripts never establish live integration.
5. Record interface changes another owner must adopt and concrete integration blockers in Issue #2. Project decisions still follow section 2 above. Never silently remove a feature or overwrite another owner's decision.
6. Before integration, merge or deployment, recheck completed features and relevant contracts, run regression checks and preserve existing data/accounts. Reopen failed items with evidence. Web releases follow `docs/RELEASE_CHECKLIST.md` on the web branch; its workstream inventory is `docs/IMPLEMENTATION_STATUS.md`. These files supplement, not replace, Issue #2.
7. Finish each session with a short tracker update and handoff: completed/blocked IDs, branch/commit/PR, tests, actual integration/deployment evidence, next dependencies and recommended actions. Never publish secrets, credentials, private logs or unsupported completion claims.

One-time adoption for old feature branches or already-running assistants: `git fetch origin`, then explicitly read `git show origin/master:AGENTS.md` and Issue #2 and ask the active assistant to apply them. Reading master does not automatically update a running session. Incorporate only the approved coordination commit (or its reviewed documentation diff); do not merge another feature branch's application code. Future sessions must repeat the tracker/rules read.
