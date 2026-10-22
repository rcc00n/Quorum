# Development rules

- Environment preparation only until the user selects a project and track.
- Use one agent. Reuse installed tools, consult relevant official docs, and limit external operations to two attempts.
- Inspect actual WSL version. Never convert WSL, replace Docker backends, start a Linux daemon on WSL1, expose Docker over unauthenticated TCP, or enable paid services without authorization.
- Keep vendor checkouts, dependencies, credentials, models, logs and runtime data outside this public repository. Never print secrets or commit private configuration.
- Prefer small reversible changes. Do not modify unrelated services or occupied ports.
- Run scripts/doctor.sh and targeted scripts/verify-all.sh checks. Missing credentials are BLOCKED; only actual successful requests pass. Never present mocks as operational integrations.
- Inspect staged paths, diffs, secret patterns and file sizes before committing. Preserve remote history/default branch; never force-push.
- Environment readiness does not establish hackathon submission compliance.

- Follow the organizer's Freemium Data layer and Meterless→Nemotron Power layer. Start only the isolated four-service Zetaris project after memory/access checks. Never put Meterless keys in Cursor settings. Inference is opt-in (`--inference`); routine diagnostics must spend no provider credits.
