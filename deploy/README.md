# Isolated VPS deployment

Target: `quorum.raccncode.com` / `144.202.24.190`. Existing Nginx hosts and Docker workloads must remain untouched. Remote data/processing integration is described in the canonical [portal handoff](../docs/PORTAL_INTEGRATION.md#transport-proposal--not-implemented-or-approved); its transport is still a proposal. Only Quorum services may be restarted. No inference, collectors, data workers or Zetaris run here.

## Build and package locally

```bash
bash deploy/build-web.sh
python3 deploy/package-release.py <unique-release-label>
scp ~/.local/share/quorum/<unique-release-label>.tar.gz root@144.202.24.190:/opt/quorum/
# On VPS: tar -xzf /opt/quorum/<unique-release-label>.tar.gz -C /opt/quorum/releases
# After the gates below: bash /opt/quorum/releases/<unique-release-label>/deploy/install-release.sh /opt/quorum/releases/<unique-release-label>
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
```

Install `backend/requirements.txt` in the isolated venv, load the private environment without printing it, then run `manage.py migrate`, `check --deploy`, `collectstatic --noinput`, and optionally `createsuperuser` interactively. Source/migrations create no default administrator. The authorized production account provisioning is recorded in [status](STATUS.md#account-and-email-follow-up). Keep auth database backups private and take one before every subsequent migration. Stop only Quorum API briefly for a consistent SQLite copy, or use SQLite's backup API.

## First installation gates

Inspect `free -m`, `df -h`, `ss -ltn`, existing Nginx configs, services, certificate names and containers first. Ports 3017 and 8017 must be unused; application servers bind loopback. Preserve supplied runtime configuration of other projects. Upload the two service files to `/etc/systemd/system/`; they cap memory/CPU and run as the dedicated user.

For a new domain, create only `/etc/nginx/conf.d/quorum.conf`, initially serving `/.well-known/acme-challenge/` from existing `/var/www/certbot` and returning 503 elsewhere. Run `nginx -t` **before** reload. With DNS confirmed, run existing Certbot with `certonly --webroot -w /var/www/certbot -d quorum.raccncode.com` (never `--nginx`, which could rewrite hosts). Then replace only the Quorum bootstrap config with `quorum.nginx.conf`, validate, reload, and start/enable only `quorum-api` and `quorum-web`. Inspect existing configuration before subsequent updates; never overwrite an unrelated or unrecognized domain config.

Certbot's webroot renewal configuration retains the challenge directory. A Quorum-only deploy hook may validate Nginx and reload it after renewal; never delete or replace other certificates. Check the existing renewal timer.

## Verify and roll back

On the VPS and externally: check HTTPS `/`, `/login`, `/register`, `/api/session/`, `/staff/login/`; unauthenticated `/api/feed/` must return 401. Exercise registration, CSRF, topic preferences, logout and mobile routes locally. Check cookies are Secure/HttpOnly, production DEBUG is disabled, both service ports are loopback-only, and existing project HTTP status/container state remains unchanged. Readiness pages report pending integrations, never invented health.

Rollback: stop only Quorum services, restore the previous release symlink and backed-up portal database if migration rollback is necessary, then start only Quorum services. For first-install removal, disable only those two units and remove only the Quorum vhost, validating Nginx before reload. Retain private data/certificates pending human decision. Never prune Docker or alter firewall/SSH.

The first-install commands are captured in `install-release.sh`. It refuses occupied ports, existing Quorum releases/units and any vhost other than the exact isolated bootstrap. Run only after uploading the release, provisioning the dedicated user/venv/private environment, and obtaining the certificate. Updates require database backup and an explicit release switch; the first-install script intentionally refuses to guess.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Standalone local Next build, isolated Node 22 binary and Python venv, dedicated system user and loopback-only systemd services | VPS already hosts projects; avoid changing shared runtimes or building under limited memory |
| 2026-10-22 | rcc00n / Codex | Public staff static files in `/opt/quorum/static`; private SQLite in mode-750 `/var/lib/quorum` | Nginx can read assets without gaining access to auth data |
| 2026-10-22 | rcc00n / Codex | HSTS applies to this host; subdomain inclusion and browser preload remain opt-in | Do not assert TLS policy for uninspected future subdomains |

Optional reviewed catalog export (definitions, not ingestion or reasoning results):

```bash
python3 deploy/export-catalog.py origin/data-collection ~/.local/share/quorum/portal-catalog.json
# Review revision/counts, then upload to /etc/quorum/catalog.json, root:quorum mode 640.
# Configure QUORUM_CATALOG_PATH; catalog changes must track an explicitly reviewed team revision.
```

`build-web.sh` refuses existing build directories without its ownership marker and refuses repository/ancestor destinations. It reuses dependencies when the lockfile matches. `package-release.py` refuses existing release directories and packages only standalone assets and portal/deploy source; secrets and runtime data are excluded.

Snapshot implementation and unapproved transport: [portal-owned proposal](../docs/SNAPSHOT_PROPOSAL.md). Release gates: [checklist](../docs/RELEASE_CHECKLIST.md); workstream evidence: [inventory](../docs/IMPLEMENTATION_STATUS.md). No production snapshot publisher is enabled.
