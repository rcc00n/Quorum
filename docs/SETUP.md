# Setup

Run commands inside the existing Ubuntu-20.04 WSL2 distribution from `~/Quorum`. Do not convert WSL or replace the working Docker backend. Git, Node.js 22.19.0, npm 10.9.3, Python 3.10.18, Docker 29.0.2 and Compose 2.40.3 were already installed.

## Private configuration

```bash
cd ~/Quorum
# Only create a private configuration if none exists:
if [ ! -e .env.local ]; then (umask 077; cp .env.example .env.local); fi
chmod 600 .env.local
```

Edit `.env.local` locally. Never put real credentials in `.env.example`, shell history, reports or commits. Scripts accept literal `KEY=value`, optionally quoted, without executing code or expanding variables. Exported environment values take precedence. Empty values use documented defaults. Custom paths must be absolute; use the full home path rather than `$HOME` in the file.

No package installation is needed for diagnostics: Bash and Python's standard library suffice.

## Meterless reference engines

The existing sparse vendor checkout is `~/.local/share/quorum/meterless`, pinned to `1742dec56a66e58eef9dda2d2b865823758ca8cd`. Preserve it. It contains only the H-MEM and World Model reference directories plus upstream root files. H-MEM test dependencies are outside Quorum.

For a fresh machine only:

```bash
./scripts/setup-meterless.sh
```

The script reuses existing installed dependencies, checks source revision and origin, disables install hooks, and installs no models or GPU runtime. Direct tooling versions are tsx 4.23.0 and Vitest 2.1.9. The generated npm lock stays with the external checkout; reuse it via `npm ci` when dependencies are absent. A fresh initial install resolves transitive dependencies, so it is not a fully hermetic dependency snapshot.

```bash
./scripts/verify-all.sh
```

The H-MEM official suite tests actual reference behavior. Its embedder is upstream's deterministic hash implementation; passing it does not prove production embeddings, LLM inference or sponsor runtime access. The separate persistence check writes and reloads real temporary JSON files for memory, audit ledger and World Model, then removes only its own temporary directory.

## Docker and service lifecycle

Native Linux `docker` accesses the existing Unix socket. Docker Desktop integration is reported separately: a reachable Linux Engine does not prove Desktop integration. Do not modify existing unrelated containers or change Docker contexts.

Zetaris requires its official matching distribution outside Quorum. After obtaining access, configure `ZETARIS_BUNDLE_DIR`, complete official setup/preflight, and pull images explicitly in that external directory. Review port bindings and set least-privilege credentials first.

```bash
./scripts/start-services.sh
./scripts/stop-services.sh
```

These commands operate only on the explicitly configured external Zetaris Compose file. Start validates Compose, requires at least 6 GiB allocated and currently available RAM (8 GiB recommended), and runs official preflight. It never pulls images or builds. Stop retains volumes. Missing configuration exits 2 without touching other services. No automatic WSL/Docker installation or conversion occurs.

## Publishing safely

```bash
python3 scripts/security-check.py
```

This scans staged/tracked blobs, not ignored private files, and reports filenames without secret values. Inspect staged paths and diffs as well. It is a heuristic check, not a guarantee against every secret format. Never force-push.
