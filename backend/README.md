# Quorum web backend

Django 5.2 LTS, session authentication, Unfold-based **Quorum Control**. This database owns only auth, sessions, preferences and login attempts. It never opens collector tables. Architecture: [approved clarification](../docs/DECISIONS.md#stack-and-work-blocks).

## Local setup

```bash
python3 -m venv ~/.local/share/quorum/portal-venv
~/.local/share/quorum/portal-venv/bin/pip install -r backend/requirements.txt
export DJANGO_DEBUG=1
~/.local/share/quorum/portal-venv/bin/python backend/manage.py migrate
~/.local/share/quorum/portal-venv/bin/python backend/manage.py createsuperuser
~/.local/share/quorum/portal-venv/bin/python backend/manage.py runserver 127.0.0.1:8017
```

SQLite and collected static assets default to `~/.local/share/quorum/portal`; override with `QUORUM_PORTAL_DATA`. Production uses `QUORUM_STATIC_ROOT=/opt/quorum/static` so Nginx never needs access to the private data directory. Development uses a process-local random secret unless one is provided; restarting signs users out. Production requires `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_ORIGINS`, HTTPS and `DJANGO_DEBUG=0`. Environment files are not automatically sourced. Use the service environment file in deployment.

## Web API

All JSON; `/api/` is same-origin. GET `/session/` returns `{user, csrfToken}`. Send that token as `X-CSRFToken` for every POST, including login/register. The token rotates after login. HttpOnly session and CSRF cookies; no JWTs. Private responses use `Cache-Control: no-store`.

| Endpoint | Method | Input / result |
| --- | --- | --- |
| session | GET | User or null; CSRF token |
| register, login | POST | `username`, `password`; authenticated user |
| logout | POST | Empty object |
| profile | GET, POST | `name`, `email`; user |
| preferences | POST | `topics: string[]` from the connected catalog |
| password | POST | `old_password`, `new_password1`, `new_password2` |
| feed | GET | `?date=YYYY-MM-DD&topic=id&revision=id`; portal snapshot |
| events/&lt;id&gt; | GET | Optional `date`/`revision`; matching event snapshot (web branch addition) |

Unauthenticated protected endpoints return 401, invalid input 400, rate limits 429. Registration, portal login and staff login share 20 attempts/address/15 minutes stored in SQLite. Behind the supplied Nginx config, only the loopback proxy's overwritten `X-Real-IP` is trusted. Staff login retains Django's CSRF-protected login form. Add edge limits before scaling beyond this small deployment. Purge expired sessions with `clearsessions`; periodically remove old AuthAttempt rows. This is a small deployment, not a distributed auth service.

## Integration boundary — pending, not operational

See the canonical [portal integration handoff](../docs/PORTAL_INTEGRATION.md) for Anastasia/Yelysei instructions, collector ownership, exact presentation fields, examples, security/validation gaps and proposed transport. `portal/integration.py` defines the adapter; `web/lib/api.ts` defines current UI types. The optional external catalog is definitions only; reasoning 1.0 is consumed only in the development preview, and no live processing integration or approved production bridge is claimed. Do not create collector tables in this database.

## Control and checks

`/staff/`: branded overview, users, topic preferences (read-only), sources (read-only), system status and integration readiness. Any active staff account can open Control. Model permissions protect preference inspection. Only superusers may manage accounts or staff permissions, preventing delegated privilege escalation. Source and migrations do not seed accounts or passwords. A separately authorized production operation provisioned four superusers and four regular users; see [deployment status](../deploy/STATUS.md#account-and-email-follow-up). Credentials are held only in a restricted local WSL file.

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py check
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py makemigrations --check --dry-run
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py test portal
```

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Reasoning-owned canonical 1.0 consumer in a separate gated localhost preview; production validator/store/adapter unchanged | Support the actual fictional sample without fabricating collector provenance or enabling publication |
| 2026-10-22 | rcc00n / Codex | Unfold 0.81 with branded pages; superuser-only account management; read-only preferences/source views | Reuse Django security while preventing staff self-escalation and cross-workstream writes |
| 2026-10-22 | rcc00n / Codex | Optional external catalog export pinned to collector commit, with provenance; live events/digests remain empty | Enable real preference selection and source inspection before runtime integration, without duplicating team registry data in this branch |
| 2026-10-22 | rcc00n / Codex | Pinned jsonschema with explicit format checks; private local immutable snapshot store and CLI, opt-in publication | Validate the portal-owned proposal without exposing ingestion or giving processing access to auth data; team transport/schema approval remains required |
| 2026-10-23 | rcc00n / Codex | Bounded value-free schema diagnostics and read-only compatibility report; configured catalog failures remain errors | Give upstream owners useful local feedback without leaking payloads or converting outages into empty successful editions |


Snapshot implementation and unapproved transport: [portal-owned proposal](../docs/SNAPSHOT_PROPOSAL.md). Release gates: [checklist](../docs/RELEASE_CHECKLIST.md); workstream evidence: [inventory](../docs/IMPLEMENTATION_STATUS.md). No production snapshot publisher is enabled.

Read-only upstream compatibility: `portal_snapshot validate --file /path/to/candidate.json`. The [canonical handoff](../docs/PORTAL_INTEGRATION.md#read-only-compatibility-command) specifies the JSON report, exit codes and limits. It checks the same production validator/projection without creating a snapshot store or touching auth records.

Canonical reasoning 1.0 **FICTIONAL local preview** and exact sample pin: [integration handoff](../docs/PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview). Start with `node web/tests/boundary.cjs --reasoning --serve` after the external Next build; this isolates local test auth and keeps the production publisher unused. `--reasoning` without `--serve` runs the real HTTP/browser acceptance suite. Neither command accesses production credentials.
