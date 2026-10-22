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
| feed | GET | `?date=YYYY-MM-DD&topic=id`; portal snapshot |

Unauthenticated protected endpoints return 401, invalid input 400, rate limits 429. Registration, portal login and staff login share 20 attempts/address/15 minutes stored in SQLite. Behind the supplied Nginx config, only the loopback proxy's overwritten `X-Real-IP` is trusted. Staff login retains Django's CSRF-protected login form. Add edge limits before scaling beyond this small deployment. Purge expired sessions with `clearsessions`; periodically remove old AuthAttempt rows. This is a small deployment, not a distributed auth service.

## Integration boundary — pending, not operational

`portal/integration.py:DataAdapter.snapshot(day, topic)` is the sole read-only seam. It currently returns `status: pending` and empty collections. Wire it to authorized Zetaris access after credentials, reachability and schema mapping are approved. No direct collector DB connection, provider call, or inferred reasoning contract exists.

Available on `data-collection`: `sources` (normalized nullable ratings, audience, independence group), `topics`, `documents` (title, lead, URLs, timestamps, access level; no full text), `official_docs`, `quotes`, `coverage`. Do not create or migrate these tables here.

Reasoning must supply event grouping/IDs, date and topic membership, neutral summaries, importance with rubric/explanation, established facts, attributed statements, disputes, unknowns, evidence links and verification explanations, coverage differences and daily digests. Confirm the upstream contract with Yelysei before implementing a live adapter. Frontend types are a **portal view model**, not an authoritative reasoning API. The adapter must validate incoming values, filter by authorized query, preserve attribution/access levels, and avoid sending secrets. Collection ratings are already normalized; never normalize them twice.

## Control and checks

`/staff/`: branded overview, users, topic preferences (read-only), sources (read-only), system status and integration readiness. Any active staff account can open Control. Model permissions protect preference inspection. Only superusers may manage accounts or staff permissions, preventing delegated privilege escalation. Provision the first superuser interactively; none is seeded.

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py check
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py makemigrations --check --dry-run
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py test portal
```

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | rcc00n / Codex | Unfold 0.81 with branded pages; superuser-only account management; read-only preferences/source views | Reuse Django security while preventing staff self-escalation and cross-workstream writes |
