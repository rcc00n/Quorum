# Isolated VPS deployment

[Web Integration: Start Here](../docs/TEAM_HANDOFF.md) · Deployment owner: **Vadim (@rcc00n)**. Teammates must not run portal releases, migrations, account provisioning or transport activation themselves. Publication/transport approval requires all three owners; release execution remains Vadim's responsibility. Current known release: `20261023-web-portals-09f5325`, verified previously; this compatibility milestone does not access production. [Evidence](STATUS.md).

Target: `quorum.raccncode.com` / `144.202.24.190`. Existing Nginx hosts and Docker workloads must remain untouched. Remote data/processing integration is described in the canonical [portal handoff](../docs/PORTAL_INTEGRATION.md#transport-proposal--not-implemented-or-approved); its transport is still a proposal. Only Quorum services may be restarted. No inference, collectors, data workers or Zetaris run here.

## Build and package locally

```bash
bash deploy/build-web.sh
python3 deploy/package-release.py <unique-release-label>
scp ~/.local/share/quorum/<unique-release-label>.tar.gz root@144.202.24.190:/opt/quorum/
# On VPS: tar -xzf /opt/quorum/<unique-release-label>.tar.gz -C /opt/quorum/releases
# Existing deployment: follow Guarded upgrades below; never use install-release.sh to update.
```

Use `/opt/quorum/releases/<release>/`, symlinked by `/opt/quorum/current`. Node 22 belongs only in `/opt/quorum/runtime/node`; Python environment only in `/opt/quorum/venv`. Do not install or replace a global Node/Python. Create dedicated `quorum` system user, `/var/lib/quorum` (owner quorum, mode 750), and root-only `/etc/quorum/portal.env` (mode 600):

```text
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<generate privately with secrets.token_urlsafe(64)>
DJANGO_ALLOWED_HOSTS=quorum.raccncode.com
DJANGO_CSRF_ORIGINS=https://quorum.raccncode.com
QUORUM_PORTAL_DATA=/var/lib/quorum
QUORUM_STATIC_ROOT=/opt/quorum/static
QUORUM_CATALOG_PATH=/etc/quorum/catalog.json
# Optional, the judges' reader of installed reasoning editions (backend/README.md › Control and checks):
# QUORUM_ENABLE_REASONING_READER=1
# QUORUM_REASONING_EDITIONS_ROOT=/var/lib/quorum/editions
```

The two reader variables are optional and outside `upgrade-release.py`'s publication checks: the proposal store and `QUORUM_ENABLE_SNAPSHOT_PUBLICATION` stay off. To show real editions to signed-in readers, create the editions directory (mode 0700, owned by the service user), set both variables, restart `quorum-api`, and install each accepted edition from the release's venv with `manage.py reasoning_snapshot … --install --producer-config <reasoning.toml of the producer commit>` (a release tarball has no `.git`, so the producer's config is hashed from that file; its sha256 must match the sidecar); or run `--install` on a full clone after `git fetch origin` and copy `<root>/<topic>/<date>/` to the VPS editions directory (directories 0700, files 0600, owned by the service user). Anonymous visitors see nothing new.

Install `backend/requirements.txt` in the isolated venv, load the private environment without printing it, then run `manage.py migrate`, `check --deploy`, `collectstatic --noinput`, and optionally `createsuperuser` interactively. Source/migrations create no default administrator. The authorized production account provisioning is recorded in [status](STATUS.md#account-and-email-follow-up). Keep auth database backups private and take one before every subsequent migration. Stop only Quorum API briefly for a consistent SQLite copy, or use SQLite's backup API.

## First installation gates (historical setup; not the update path)

Inspect `free -m`, `df -h`, `ss -ltn`, existing Nginx configs, services, certificate names and containers first. Ports 3017 and 8017 must be unused; application servers bind loopback. Preserve supplied runtime configuration of other projects. Upload the two service files to `/etc/systemd/system/`; they cap memory/CPU and run as the dedicated user.

For a new domain, create only `/etc/nginx/conf.d/quorum.conf`, initially serving `/.well-known/acme-challenge/` from existing `/var/www/certbot` and returning 503 elsewhere. Run `nginx -t` **before** reload. With DNS confirmed, run existing Certbot with `certonly --webroot -w /var/www/certbot -d quorum.raccncode.com` (never `--nginx`, which could rewrite hosts). Then replace only the Quorum bootstrap config with `quorum.nginx.conf`, validate, reload, and start/enable only `quorum-api` and `quorum-web`. Inspect existing configuration before subsequent updates; never overwrite an unrelated or unrecognized domain config.

Certbot's webroot renewal configuration retains the challenge directory. A Quorum-only deploy hook may validate Nginx and reload it after renewal; never delete or replace other certificates. Check the existing renewal timer.

## Verify and roll back

On the VPS and externally: check HTTPS `/`, `/login`, `/register`, `/api/session/`, `/staff/login/`; unauthenticated `/api/feed/` must return 401. Exercise registration, CSRF, topic preferences, logout and mobile routes locally. Check cookies are Secure/HttpOnly, production DEBUG is disabled, both service ports are loopback-only, and existing project HTTP status/container state remains unchanged. Readiness pages report pending integrations, never invented health.

Rollback: stop only Quorum services, restore the previous release symlink and backed-up portal database if migration rollback is necessary, then start only Quorum services. For first-install removal, disable only those two units and remove only the Quorum vhost, validating Nginx before reload. Retain private data/certificates pending human decision. Never prune Docker or alter firewall/SSH.

The first-install commands are captured in `install-release.sh`. It refuses occupied ports, existing Quorum releases/units and any vhost other than the exact isolated bootstrap. Run only after uploading the release, provisioning the dedicated user/venv/private environment, and obtaining the certificate. Updates require database backup and an explicit release switch; the first-install script intentionally refuses to guess.

## Decisions

2026-10-26 · rcc00n / Codex · Hosted portal CI uses Ubuntu 24.04's preinstalled Google Chrome through the existing executable override; absence fails the job, and all authenticated suites still run. Why: repeated Playwright OS/font installation stalls on the Ubuntu package mirror prevented tests from starting. Official support: https://playwright.dev/docs/browsers and https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md. This changes tooling acquisition, not test expectations.

2026-10-26 · rcc00n / Codex · Teammate SSH keys require exact SHA256 verification and additive atomic installation with a private backup; `install-ssh-key.py` targets an existing dedicated account by default and grants no sudo itself. Why: a fingerprint cannot authenticate a user, and provisioning must preserve the owner's existing access. Actual login must be confirmed from the teammate's private-key holder.

2026-10-24 · rcc00n / Codex · Package only a clean commit and a successful source-bound external build receipt; export tracked portal/deploy files and reject private runtime paths. Why: stale builds must not inherit a newer revision label, and untracked local data must never enter a release archive. `QUORUM_WEB_BUILD` selects the reviewed build; older builds without `.quorum-build.json` require rebuilding. This adds no deployment authority.

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Standalone local Next build, isolated Node 22 binary and Python venv, dedicated system user and loopback-only systemd services | VPS already hosts projects; avoid changing shared runtimes or building under limited memory |
| 2026-10-22 | rcc00n / Codex | Public staff static files in `/opt/quorum/static`; private SQLite in mode-750 `/var/lib/quorum` | Nginx can read assets without gaining access to auth data |
| 2026-10-22 | rcc00n / Codex | HSTS applies to this host; subdomain inclusion and browser preload remain opt-in | Do not assert TLS policy for uninspected future subdomains |
| 2026-10-23 | rcc00n / Codex | Existing-deployment upgrade with private backups, additive-only dependencies, no migrations and automatic code/static rollback | Make independently tested website improvements deployable while retaining users, old runtime compatibility and unrelated workloads |

Optional reviewed catalog export (definitions, not ingestion or reasoning results):

```bash
python3 deploy/export-catalog.py origin/data-collection ~/.local/share/quorum/portal-catalog.json
# Review revision/counts, then upload to /etc/quorum/catalog.json, root:quorum mode 640.
# Configure QUORUM_CATALOG_PATH; catalog changes must track an explicitly reviewed team revision.
```

`build-web.sh` refuses existing build directories without its ownership marker and refuses repository/ancestor destinations. It reuses dependencies when the lockfile matches. `package-release.py` refuses existing release directories and packages only standalone assets and portal/deploy source; secrets and runtime data are excluded.

Snapshot implementation and unapproved transport: [portal-owned proposal](../docs/SNAPSHOT_PROPOSAL.md). Release gates: [checklist](../docs/RELEASE_CHECKLIST.md); workstream evidence: [inventory](../docs/IMPLEMENTATION_STATUS.md). No production snapshot publisher is enabled.

## Guarded upgrades of this existing deployment

Use `upgrade-release.py`, **not** the first-install script. Package a clean tested commit, upload/extract to a new root-controlled `/opt/quorum/releases/<label>` and inspect it before running:

```bash
# On the VPS, after upload/extraction:
python3 /opt/quorum/releases/<label>/deploy/upgrade-release.py /opt/quorum/releases/<label>
python3 /opt/quorum/releases/<label>/deploy/upgrade-release.py /opt/quorum/releases/<label> --apply
```

Plan mode is read-only. Apply requires the recognized current release, active Quorum services/loopback ports, private production environment, disabled snapshot root/publication, disk/RAM headroom and unchanged old dependency pins. It creates private integrity-checked SQLite backups before any installation, adds only missing pinned distributions without replacing old ones, runs production checks and rejects any pending migration. It then stops only Quorum, takes a final consistent auth backup/fingerprint, backs up static files, collects static, atomically switches the release and starts only those two services. HTTPS and unchanged auth/preferences/container start identities are verified. A bounded health failure switches back and restores static assets. No DB is automatically restored because migrations are forbidden and concurrent user writes must survive. Additive packages may remain installed; the old release's pins remain intact. No Nginx/SSH/firewall/Docker configuration changes occur. Real authenticated post-release browser checks remain a separate release gate.

For an operator rollback, read the private `rollback.json`, verify the old release exists, stop only `quorum-api` and `quorum-web`, atomically select that previous release and start those two units. Restore the saved static tree if assets changed. Keep the current auth database; restore a backup only after explicit diagnosis/authorization of a data issue. Recheck HTTPS and authenticated routes. The upgrade path refuses migrations rather than guessing a reverse migration.

Build receipt version 2 binds both reviewed web source and compiled standalone/static bytes. Rebuild older receipts before packaging. Linked artifacts are rejected: use an external build directory with locally installed dependencies rather than a `node_modules` symlink. A matching receipt is a local integrity check, not owner review or deployment authorization.
