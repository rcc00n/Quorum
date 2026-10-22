# Quorum — hackathon development environment

Reusable environment preparation for Open Agent Hackathon 2026. No project or track has been selected; this repository contains no application or agent.

Ubuntu-20.04 is confirmed as **WSL2**. Use the existing Linux Docker CLI and backend. Dependencies, the newly downloaded official Zetaris platform bundle, private deployment and credentials live outside version control. The deployment uses only the bundle’s six required default services (including two one-shot jobs); Nemotron must use organizer-supplied Meterless access.

```bash
./scripts/doctor.sh       # tools, WSL2, Docker, GitHub, Cursor installation
./scripts/verify-all.sh   # doctor + memory/state tests + Zetaris checks; NO provider inference
# Optional: --inference explicitly sends one capped request with real sponsor credentials
```

Exit codes: `0` all checks passed, `1` at least one failure, `2` blocked or untested checks remain. Output uses `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`. Missing sponsor credentials intentionally produce `BLOCKED`.

Start with [setup](docs/SETUP.md), [sponsor configuration](docs/SPONSOR_SETUP.md), [manual actions](docs/MANUAL_ACTIONS.md) and the [verified readiness record](reports/readiness.md).

Environment readiness alone does not satisfy final hackathon project or submission requirements.

The official platform is extracted/configured but registry login and RAM headroom block startup. The completed safe Linux cleanup reclaimed approximately 5.40 GB; see [disk cleanup](reports/disk-cleanup.md).
