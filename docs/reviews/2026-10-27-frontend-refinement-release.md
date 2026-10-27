# Frontend refinement release — 27 October 2026 UTC

Owner: Vadim / rcc00n / Codex. Canonical coordination: [Issue #2](https://github.com/rcc00n/Quorum/issues/2).

**DEPLOYED:** `20261027-paperclip-r1`, source `b938a121a13816fbceead90af7aca96487c324c3`, selected by `/opt/quorum/current` on https://quorum.raccncode.com. Code is identical to the web/backend/deploy tree of release-master `41aa9d058e1a05bf417283884aa03789a725e3f7`. The package keeps its actual source revision; later evidence-only documentation does not relabel its bytes.

## Scope and independent release boundaries

| Feature | Release / source | Verified rollback target |
| --- | --- | --- |
| WEB-VISUAL-HIERARCHY-01: readable Impact and landing evidence emphasis; Next history-state fix | `20261027-hierarchy-r1` / `21fa464ed5bca2f74ef73451e9789473c078a27e` | `20261027-reader-r3` |
| WEB-EDITION-NAV-01 / WEB-AUTH-RETURN-01: date/topic URLs, day/recovery controls, exact sign-in return | `20261027-edition-r1` / `06cdb4d223df761b6db127c00d547884b98937d9` | `20261027-hierarchy-r1` |
| WEB-PAPERCLIP-POLISH-01: framed reader/search/date instruments, restrained surface/selected states | `20261027-paperclip-r1` / `b938a121a13816fbceead90af7aca96487c324c3` | `20261027-edition-r1` |

Normal merges: [#53](https://github.com/rcc00n/Quorum/pull/53), [#54](https://github.com/rcc00n/Quorum/pull/54), [#55](https://github.com/rcc00n/Quorum/pull/55), then [#56 into master](https://github.com/rcc00n/Quorum/pull/56). #53 has Anastasia's formal look approval. The human explicitly authorized checked #54/current polish deployment without another approval; see [Session release authorization](../DECISIONS.md#shared-development-coordination). #52 remains separate and is not included.

The [Paperclip reference adaptation](../../web/DESIGN.md#instrument-refinement) retains Quorum's paper/ink/umber palette, type, hero/page grid, cards, content, status labels and source semantics. No dependency, backend/API/data/provider change. Existing processing/publication limits in [LIVE_RELEASE.md](../../deploy/LIVE_RELEASE.md) remain; UI polish is not sponsor or fresh-edition certification.

## Verification

- Source-bound production builds/typechecks and v2 source/artifact receipts passed for each independent archive. Archive member/path/type/private-file checks and target SHA/size checks passed before extraction.
- Green source CI: [hierarchy 40459422898](https://github.com/rcc00n/Quorum/actions/runs/40459422898), [combined navigation 40463473375](https://github.com/rcc00n/Quorum/actions/runs/40463473375), [polish 40464297410](https://github.com/rcc00n/Quorum/actions/runs/40464297410). Final [release CI 40464625303](https://github.com/rcc00n/Quorum/actions/runs/40464625303): portal/Chromium and combined-python both successful.
- Complete local real Django/Next/Chromium regressions passed, including source modes, keyboard/reduced motion, source/provenance/Impact equality, reader/search, auth/admin, date/topic refresh/Back/Forward and exact sign-in return. Public/FICTIONAL before/after at 1440/390/320 were inspected without page errors or page overflow. Local genuine-edition checks used the already approved original/accepted copy and four-topic/40-source catalog; no new production edition export was needed.
- Each guarded target-host release ran isolated Django tests, production checks and migration checks, then private consistent backups and Quorum-only cutover. No migrations or new distributions were installed.
- Each separate release passed actual public authenticated HTTPS/Chromium checks against the approved unchanged original: one story, 19 roundup entries, all 174 trace decisions, evidence/reviewer/source links, four rating modes, 1440/768/390 layouts and no page errors. Navigation additionally passed actual dated History, changed-date refresh/Back and exact story/date/revision/pane continuation after sign-in. Final polish additionally passed computed palette, framed tabs and search-surface checks.
- Actual code/static rollback and guarded reapply passed for **all three** rows above. A pre-existing judge session, exact feed and preferences survived each rollback/reapply and both service restarts. No database backup was restored.
- Final preservation fingerprints match the preflight: all 11 account/credential/profile records (excluding normal login timestamps), preferences, installed edition bytes/metadata/ownership/modes, root SSH and private environment. All 24 unrelated container identities/start times match. Both Quorum services active; SQLite integrity OK; reader enabled and proposal publisher disabled. Final external HTTPS 200, TLS verification 0.
- Staged secret/path/size checks passed. Doctor/verify offline each: 5 PASS, 0 FAIL, 1 BLOCKED (live integration intentionally untested); no inference request or extra infrastructure purchase.

## Artifact and rollback evidence

| Archive | Bytes | SHA256 |
| --- | ---: | --- |
| hierarchy-r1 | 23,579,177 | `507071e1fb6a1e3217b2c9d5196d6c1562e1753652766115901f80f5a8975606` |
| edition-r1 | 23,574,199 | `162b78f7a62b7ae1ab0a0298fb740eaed44032be40e2383df05ecdaf62dfbd59` |
| paperclip-r1 | 23,578,263 | `3cd44ed4b26cc99fde8cfe9ae3f3e0a51aa10d24a899f13b8ce1459138351152` |

Private rollback records are under `/var/lib/quorum/backups/upgrade-*/rollback.json`; actual rehearsal reports under `/var/lib/quorum/backups/paperclip-release-20261027/`. Reapply backups: hierarchy `upgrade-20261027T070715Z`, edition `upgrade-20261027T071002Z`, polish `upgrade-20261027T071322Z`. Original source/sidecar bindings remain those in LIVE_RELEASE.md.

The latest visual feature can be reversed to `20261027-edition-r1` using the [guarded rollback procedure](../../deploy/README.md#guarded-upgrades-of-this-existing-deployment), preserving the auth database and installed editions. To remove an earlier feature while retaining later ones, revert that feature's own commit in a new owner PR, retain decision history, rebuild/check and release normally; do not force-push or edit live assets. The polish is isolated by one stylesheet import. Archives and preceding releases remain retained.
