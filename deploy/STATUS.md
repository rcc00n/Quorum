# Portal deployment — 2026-10-22

Live: https://quorum.raccncode.com · Control: https://quorum.raccncode.com/staff/

- Isolated systemd services: `quorum-web` on `127.0.0.1:3017`, `quorum-api` on `127.0.0.1:8017`. Existing Nginx terminates HTTPS; only the new Quorum vhost was added. Existing Docker workloads retained their prior state.
- SQLite auth/preferences live privately in `/var/lib/quorum`; static assets in `/opt/quorum/static`; private configuration in `/etc/quorum/portal.env`. No inference or data workers deployed.
- Certificate issued successfully; Certbot renewal and Quorum-only Nginx deploy hook configured. HTTP redirects to HTTPS. Nginx validated before every reload; pre-existing unrelated duplicate-server-name warnings were preserved.
- Verified from the target VPS: public pages, session endpoint, staff login and static assets return 200; unauthenticated feed returns 401. External Chromium checks exercised registration, actual topic selection/persistence, profile saving, logout and auth redirects at desktop/mobile sizes; no page errors or horizontal overflow.
- Next production build/typecheck passed. Thirteen Django tests, system check and migration drift check passed. Rating/missing-data/link tests and explicitly labelled fictional event UI checks passed. Staff login, overview, users/add, topics, sources, status and integrations were inspected locally at desktop/mobile sizes.
- Production deployment check reports two intentional opt-in HSTS warnings (subdomain inclusion and preload), documented in deployment decisions. Standard Django checks report no issues. Required repository doctor/verify scripts ran without inference: environment readiness remains BLOCKED on registry/provider credentials and Zetaris runtime prerequisites; no operational integration is claimed.

Catalog: 1 topic and 19 source definitions, read-only export from `data-collection` commit `46b0d00a962960891a320b18f41ed64cfd649119`. Ratings/audience remain unavailable where the registry is blank. This is a provenance-labelled registry snapshot, not a live data connection. Published events/digests remain empty.

Remaining: agree the reasoning contract and connect authorized Zetaris reads/status telemetry. Provision the first real administrator interactively with Django `createsuperuser` under the private production environment (see deployment README); no default administrator/password is seeded. Temporary production browser-test accounts are removed after verification.

Screenshots are outside the public repository at `~/.local/share/quorum/portal-screenshots/` (landing/dashboard desktop/mobile and staff login/overview/mobile); repository safety checks prohibit committing binary artifacts.
