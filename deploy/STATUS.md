# Portal deployment — 2026-10-22

Live: https://quorum.raccncode.com · Control: https://quorum.raccncode.com/staff/

- Isolated systemd services: `quorum-web` on `127.0.0.1:3017`, `quorum-api` on `127.0.0.1:8017`. Existing Nginx terminates HTTPS; only the new Quorum vhost was added. Existing Docker workloads retained their prior state.
- SQLite auth/preferences live privately in `/var/lib/quorum`; static assets in `/opt/quorum/static`; private configuration in `/etc/quorum/portal.env`. No inference or data workers deployed.
- Certificate issued successfully; Certbot renewal and Quorum-only Nginx deploy hook configured. HTTP redirects to HTTPS. Nginx validated before every reload; pre-existing unrelated duplicate-server-name warnings were preserved.
- Verified from the target VPS: public pages, session endpoint, staff login and static assets return 200; unauthenticated feed returns 401. External Chromium checks exercised registration, actual topic selection/persistence, profile saving, logout and auth redirects at desktop/mobile sizes; no page errors or horizontal overflow.
- Next production build/typecheck passed. Thirteen Django tests, system check and migration drift check passed. Rating/missing-data/link tests and explicitly labelled fictional event UI checks passed. Staff login, overview, users/add, topics, sources, status and integrations were inspected locally at desktop/mobile sizes.
- Production deployment check reports two intentional opt-in HSTS warnings (subdomain inclusion and preload), documented in deployment decisions. Standard Django checks report no issues. Required repository doctor/verify scripts ran without inference: environment readiness remains BLOCKED on registry/provider credentials and Zetaris runtime prerequisites; no operational integration is claimed.

Catalog: 1 topic and 19 source definitions, read-only export from `data-collection` commit `46b0d00a962960891a320b18f41ed64cfd649119`. Ratings/audience remain unavailable where the registry is blank. This is a provenance-labelled registry snapshot, not a live data connection. Published events/digests remain empty.

Initial remaining items: agree the reasoning contract, connect authorized Zetaris reads/status telemetry, and provision real administrators. Administrator provisioning was completed in the follow-up below; no credentials are seeded by source or migrations. Temporary browser-test accounts from the original deployment were removed after verification.

Screenshots are outside the public repository at `~/.local/share/quorum/portal-screenshots/` (landing/dashboard desktop/mobile and staff login/overview/mobile); repository safety checks prohibit committing binary artifacts.

## Account and email follow-up

2026-10-22 · rcc00n / Codex · Explicitly authorized production account provisioning.

- Confirmed production `DJANGO_DEBUG=0` and `/var/lib/quorum/portal.sqlite3` before mutation. Inspection found zero pre-existing users. Created an integrity-checked SQLite backup under the private production backup directory (directory 700, file 600).
- Provisioned exactly the eight requested accounts: four active staff superusers and four active regular users. Generated distinct cryptographically secure passwords longer than 24 characters, stored only through Django password hashing; email fields remain blank. The operation uses exact usernames and updates only those accounts if repeated. No unrelated account was changed.
- Transferred credentials over encrypted SCP to `~/.local/share/quorum/private/initial-accounts.txt` on local WSL (directory 700, file 600), then removed the production plaintext transfer file. No passwords, credentials, backups or private configuration are in Git.
- All eight accounts authenticated against production HTTPS. Browser checks verified every dashboard, admin access for all four superusers, staff denial for all four regular users, Secure/HttpOnly session cookies and logout. The final database audit verified exact role flags, Django password hashes, unchanged pre-existing accounts and removal of the plaintext transfer file.
- No application code, auth flows, service configuration, Nginx hosts, DNS records or unrelated workloads changed. No service restart was required. Production HTTPS home and login checks passed.

**Email: unavailable (not configured or delivery-verified).** The Quorum service environment contains no mail provider/SMTP configuration or credentials. Quorum-scoped local configuration and available connected tools expose no authorized DNS management credentials or delivery-test mailbox. Public DNS queries identified Google-managed authoritative nameservers, but do not grant DNS write access. There were no MX/TXT answers for the Quorum subdomain or DMARC TXT answer at the time of inspection; existing routing was not changed. Other projects' credentials were neither inspected nor reused.

Evaluated [Resend's free plan](https://resend.com/pricing), [authenticated API access](https://resend.com/docs/dashboard/api-keys/introduction) and [sender-domain verification](https://resend.com/docs/dashboard/domains/introduction). The provider can support a low-volume zero-cost setup, but no authorized account/API access, DNS write capability or approved mailbox was available to complete registration, verification and actual delivery without user participation. No account was registered with an invented identity, no subscription was purchased, no email was sent, and no MX records were changed. Brevo was considered as an alternative; its public pricing page did not expose readable plan details in this inspection, and no authorized Brevo credentials were present either.

Registration/login remain unchanged. Email verification, reset endpoints and associated frontend pages were intentionally not implemented or deployed, as required when authenticated delivery cannot be proven. A successful provider API acceptance alone would not satisfy the delivery gate.

Repository doctor/verify scripts were rerun without inference; sponsor readiness remains blocked on existing registry/provider credentials and runtime prerequisites. These blockers do not affect the verified production account flows.
