# Sources and motion release — 27 October 2026 UTC

Owner: Vadim / Codex. Feature `WEB-SPECTRUM-MOTION-01`, branch
`feature/web-spectrum-motion`. Canonical coordination remains [Issue #2](https://github.com/rcc00n/Quorum/issues/2).
This records the frontend release; the [original edition and infrastructure evidence](LIVE_RELEASE.md)
remains historical and its upstream limitations still apply.

## Exact deployment

- Live page: https://quorum.raccncode.com/sources (sign-in required).
- Landing: https://quorum.raccncode.com
- Production source: `6f16bd7feda9a8e3c1c105ddd3510b2dce9d27fa`.
- Release: `/opt/quorum/releases/20261027-spectrum-r1`, selected by `/opt/quorum/current`.
- Archive SHA256: `8c2582aa2c33b2dd901cc01109a0cf065907355f4fa64b90a8ec9090318e2f18`.
- Archive: 23,482,356 bytes, 2,691 regular-file/directory members; no links, private environment or database files.
- Build receipt v2 validates both the identical reviewed web source and compiled standalone/static bytes.
- Merges: [#44, frontend → integration](https://github.com/rcc00n/Quorum/pull/44),
  [#45, integration → master](https://github.com/rcc00n/Quorum/pull/45), normal merge commits.
- Hosting: existing Vultr VPS `144.202.24.190`; **$0 additional monthly infrastructure**.
  No AWS move, purchase, new dependencies or inference request.

## Result and verification

Sources exposes the complete registry, not an event's coverage. The actual catalog has 40 sources;
34 have eligible ratings and cited positive audience estimates in the checked modes. Political position
uses the existing normalization/formulas; audience uses a logarithmic axis. Unknown ratings are omitted,
and supplied zero audience remains inspectable without being plotted. Selection shows the actual source,
score, audience attribution and reporting-date availability. The existing provenance ledger remains available.

The chart adds pointer depth, crosshair/selection and mode transitions. Landing/workspace sections reveal
on entry, with shallow depth on existing reading surfaces. Keyboard arrows/Home/End, reduced motion and
an unavailable-IntersectionObserver fallback are covered. No full no-JavaScript capability is claimed.

Verified for this release:

- Clean production build/typecheck, numeric geometry/ratings and real HTTP/API/TypeScript/browser regressions.
- Source CI [40448361243](https://github.com/rcc00n/Quorum/actions/runs/40448361243) and final release CI
  [40448679597](https://github.com/rcc00n/Quorum/actions/runs/40448679597): both combined-python and portal/Chrome jobs passed.
- Isolated genuine installed-edition test, then actual public HTTPS judge UI login/logout; anonymous Sources
  redirects to login and feed/event APIs return 401. Ordinary judge staff access and CSRF rejection remain enforced.
- Exact original story/evidence/reviewer content, 19 roundup entries and all 174 trace decisions through production;
  all four rating modes, chart/API values, keyboard, pointer depth and reduced motion pass.
- Public landing reveal/depth and observer fallback pass. Desktop/tablet/mobile at 1440/768/390 have no horizontal
  overflow. Final desktop/mobile Sources screenshots were visually inspected; no browser page errors observed.
- Both Quorum services restarted: existing judge session, four topic preferences and exact real feed/edition persist.
- Final HTTPS 200 with TLS verification result 0; both services active, loopback bindings preserved, SQLite integrity OK.

## Backup, rollback and preservation

The reviewed upgrade guard ran target-host isolated Django tests and production/migration checks before switching.
No migrations ran. Initial private backup: `/var/lib/quorum/backups/upgrade-20261027T041819Z`.
An actual previous-code/static rollback to `20261027-live-r3` passed HTTPS/auth/container checks without restoring
the database. Guarded reapply passed with backup `/var/lib/quorum/backups/upgrade-20261027T041953Z`.
Private rollback evidence is under `/var/lib/quorum/backups/live-release-20261027/spectrum-rollback-rehearsal.json`.

All 11 accounts present at this release's preflight survived the guarded cutovers; login timestamps may change
normally. Original snapshot/sidecar hashes remain exactly those in LIVE_RELEASE.md, with quorum-owned 0700/0600
edition directories/files. Reader remains enabled and proposal publication disabled. Owner root SSH is byte-identical
to its backup. All 24 unrelated container identities/start times match the preflight baseline. Only Quorum units
were restarted; existing Nginx, global runtimes, secrets, owner intake and producer cache were preserved.

## Commits and handoff

| Commit | Independent change |
| --- | --- |
| `9336b68` | Interactive source spectrum, exact geometry, provenance and focused tests |
| `efc418a` | Preserve supplied zero audience outside the logarithmic plot |
| `5d5d13b` | Accessible section reveals and reading-surface depth |
| `48616f3` | Authenticated Sources route/navigation and canonical navigation decision |

**Anastasia:** spectrum release is DEPLOYED; merge your separate polish PR after this release, against updated
integration. Landing-only `.lp-spectrum` responsive work is agreed. The native 27-Oct acceptance/install plan is unchanged.

**Yelysei:** this release changes only the portal; continue the agreed genuine 27-Oct Nightshift/H-MEM run and original-file
handoff. No new processing execution or sponsor certification is claimed by the UI.

**Vadim:** use the existing private judge credentials. GO for the verified Sources/26-Oct provisional-edition experience;
fresh 27-Oct editions, full sponsor/recall certification and human submission remain separate open gates in Issue #2.
