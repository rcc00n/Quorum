# Development rules

- Environment preparation only until the user selects a project and track.
- Use one agent. Reuse installed tools, consult relevant official docs, and limit external operations to two attempts.
- Inspect actual WSL version. Never convert WSL, replace Docker backends, start a Linux daemon on WSL1, expose Docker over unauthenticated TCP, or enable paid services without authorization.
- Keep vendor checkouts, dependencies, credentials, models, logs and runtime data outside this public repository. Never print secrets or commit private configuration.
- Prefer small reversible changes. Do not modify unrelated services or occupied ports.
- Run scripts/doctor.sh and targeted scripts/verify-all.sh checks. Missing credentials are BLOCKED; only actual successful requests pass. Never present mocks as operational integrations.
- Inspect staged paths, diffs, secret patterns and file sizes before committing. Preserve remote history/default branch; never force-push.
- Environment readiness does not establish hackathon submission compliance.

- Use the newly downloaded official Zetaris platform bundle (supersedes Freemium), with the organizer's Data layer and Meterless→Nemotron Power layer. Use the bundle’s required default services and official preflight/verify scripts after resource/authentication checks; preserve supplied environment values. Never put Meterless keys in Cursor settings. Inference is opt-in (`--inference`); routine diagnostics must spend no provider credits.

- Disk cleanup must preserve all user projects/data, models needed for the statistics exam, Docker containers/volumes and files created or modified since 2026-04-21. Windows deletions and WSL memory changes require explicit approval.
