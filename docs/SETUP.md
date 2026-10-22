# Reusable setup on the existing WSL2 machine

Run from `~/Quorum` inside Ubuntu-20.04 WSL2. Reuse the verified native Linux Docker CLI and backend; leave existing containers and WSL limits alone.

```bash
cd ~/Quorum
if [ ! -e .env.local ]; then (umask 077; cp .env.example .env.local); fi
chmod 600 .env.local
./scripts/doctor.sh
./scripts/verify-all.sh
```

Configuration files contain literal `KEY=value`, optionally quoted, with no shell execution/expansion. Exported environment values take precedence. Use absolute external paths. Existing old Cloud/NVIDIA/runtime-token settings must be replaced with the current example keys; unknown keys are rejected. Do not print credentials or commit private configuration.

## Freemium preparation and lifecycle

The existing official checkout and private generated deployment are outside Quorum. For a fresh machine, clone the official repo to `~/.local/share/quorum/zetaris-freemium` and checkout revision `9dd4fe943afebca6b204b6ed5eccdca91b831e6c` before preparation.

```bash
python3 scripts/services.py prepare
```

Preparation generates only four core services, keeps DB port 5432 unpublished and binds GUI/REST/JDBC to localhost. Repeating it preserves the existing secrets/configuration. Never start the entire upstream Compose file: it includes optional GPU/model services.

After the organizer grants Docker Hub image access, log in locally. Do not repeat the already-denied pull before access changes. To pull the four core images once after that:

```bash
cd ~/.local/share/quorum/zetaris-runtime
docker login
docker compose -p quorum-zetaris -f compose.json pull zetaris-db zetaris-server zetaris-api zetaris-gui
cd ~/Quorum
./scripts/start-services.sh
./scripts/verify-all.sh
# Stop only Quorum's isolated four services; retain data:
./scripts/stop-services.sh
```

Start validates private Compose and checks 8 GiB Docker allocation plus 8 GiB currently available memory, then uses `--pull never --no-build`. It does not install, download or silently adjust WSL. Successful start requests do not imply readiness; diagnostics must confirm four running containers and application/query responses.

For sample SQL verification, use a matching vendor-supplied JDBC JAR outside Quorum and the existing JDK's Java 11+ source launcher. `ZETARIS_JDBC_DRIVER` is optional when the driver supports JDBC automatic discovery. Credentials are passed in process environment, not command-line arguments. SQL and returned data are withheld from reports. No PostgreSQL client connection is substituted for Zetaris SQL.

## Existing Meterless references

Preserve `~/.local/share/quorum/meterless` at `1742dec56a66e58eef9dda2d2b865823758ca8cd`. `scripts/setup-meterless.sh` is only for missing reference tooling and reuses working dependencies. No models or GPU runtimes are installed. H-MEM uses the official deterministic reference embedder; reference passes do not prove LLM integration. Persistence checks create/reload real temporary JSON files and remove only their own temporary directory.

## Diagnostics and explicit inference

```bash
./scripts/verify-all.sh              # no provider credits spent
./scripts/verify-all.sh --inference  # explicit ONE capped sponsored inference, if configured
python3 scripts/security-check.py   # staged/tracked file safety heuristic
```

Statuses: PASS, FAIL, BLOCKED, NOT_TESTED. Exit 0 means all checks passed; 1 means a failure; 2 means blocked or untested checks remain. Missing credentials, images, RAM, sample SQL or exact endpoints never count as operational integrations. Cursor interactive acceptance requires evidence of actual observed GUI checks, not executable presence.

Inspect staged paths, diff and file sizes before publishing; the secret scanner is heuristic. Never commit `.env*` except `.env.example`, the Freemium checkout, private deployment, keys, data, logs or binaries. Never force-push.
