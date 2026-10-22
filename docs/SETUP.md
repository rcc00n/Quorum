# Setup on the existing Ubuntu WSL2 machine

Work in `~/Quorum`. Keep the working native Linux Docker backend and all existing workloads. The newly downloaded **official platform bundle** replaces Freemium as the supported installation path; existing vendor checkouts remain untouched outside Git.

```bash
cd ~/Quorum
python3 scripts/services.py prepare
python3 scripts/services.py preflight
./scripts/doctor.sh
./scripts/verify-all.sh
```

The default private bundle path is `~/.local/share/quorum/zetaris-platform-bundle/zetaris-platform`; override only with an absolute `ZETARIS_PLATFORM_DIR` in private configuration. Supplied images, database values and administrator fields remain in its `.env`, not in Quorum. Literal `KEY=value` files are never sourced as shell code. A private Compose override binds UI to localhost. Do not use the server example or enable optional profiles on this laptop.

## Authenticate, pull, start, verify

Azure authentication is the remaining access prerequisite. Use the official Gateway's current registry sign-in in a trusted private WSL terminal, without putting credentials in chat, reports or shell history. Prefer `docker login zetarishackathon.azurecr.io` and enter the supplied username/password interactively. The assistant cannot complete an interactive login without those credentials.

After authentication and sufficient RAM headroom:

```bash
cd ~/Quorum
python3 scripts/services.py preflight
python3 scripts/services.py pull
./scripts/start-services.sh
# Once startup/bootstrap finish:
python3 scripts/services.py verify
./scripts/verify-all.sh
```

Wrappers use the actual official project `zetaris`, supplied Compose/environment and private override. Required services are postgres/init/driver/api/ui/bootstrap. Start uses `--pull never --no-build` and checks static port conflicts. It refuses insufficient current WSL/Windows memory and never stops other services or edits WSL limits. No automatic retries. Pull/start output is captured to avoid leaking credentials; a timeout/blocked status must be diagnosed rather than retried blindly.

Stop only this platform while retaining volumes:

```bash
./scripts/stop-services.sh
```

Never use the bundle's destructive installation-test suite or `down -v` on this installation. Volume/key loss would destroy databases and encrypted data-source credentials. `init`/`bootstrap` exiting 0 is expected success.

## Configuration and diagnostics

```bash
if [ ! -e .env.local ]; then (umask 077; cp .env.example .env.local); fi
chmod 600 .env.local
./scripts/verify-all.sh              # no provider inference
./scripts/verify-all.sh --inference  # explicit one capped hosted test, if configured
python3 scripts/security-check.py
```

Remove obsolete Freemium configuration keys from private Quorum configuration if present; do not delete old vendor/data directories. Do not copy platform credentials into Quorum. Meterless URL/key/model remain organizer-supplied blanks until available. The external pinned H-MEM references and setup script are preserved; their tests do not establish inference readiness.

Statuses are PASS, FAIL, BLOCKED, NOT_TESTED. Exit 0 means all checks passed, 1 means a failure, 2 means blocked/untested work remains. Open ports and reference tests never stand in for authenticated platform SQL or hosted inference.

## Disk safety

The completed cleanup is documented in [disk-cleanup.md](../reports/disk-cleanup.md), including every removed cache object. No reusable cleanup command is provided: deletion authorization was tied to a specific protected period and inspected file metadata. Do not rerun broad prune/cache-clean operations based on that one-time audit.

Review staged files, diffs, secret patterns and sizes before publication. Keep archives, binaries, vendor sources, secrets, models, logs and runtime data outside Git; never force-push. Free Linux blocks do not automatically shrink the Windows-hosted WSL virtual disk. No compaction/reset was performed.
