# Public demo reader release, 27 October 2026 UTC

WEB-PUBLIC-DEMO-01, rcc00n / Codex. Vadim explicitly chose one publicly shared demo login/password
for the repository's About; this is deliberate public access, not disclosure of a private judge account.
Canonical scope: DECISIONS.md › User account and interface › Public demo access amendment.

DEPLOYED: `20261027-public-demo-r1`, actual source `c181296bdea797c953dcb4541315afdc2bcc2cfe`.
Normal #101/#102 merges, release-master `59029f83b582e5840ebdc11d45ad2801abb6f863`.
The accepted Also today r2, photos and README #100 are retained. No UI, API-field, schema, migration,
dependency, reasoning or source-data change. Group-marked public readers cannot POST profile/password/
preferences; ordinary readers keep the existing behavior. Login/logout and reading remain available.

Clean source-bound archive: 23,635,071 bytes, 2,699 validated members,
SHA256 `9d6572617fd6612cfe06194e283abe680fa57c6b43d2992a4452d5f105c43948`.
Build/typecheck, receipt/source/path/type/checksum and target read-only plan PASS. Exact source CI
[40600810959](https://github.com/rcc00n/Quorum/actions/runs/40600810959) and final release CI
[40601159230](https://github.com/rcc00n/Quorum/actions/runs/40601159230): portal/combined-python PASS.
104 local portal tests PASS with 5 existing skips; all 490 source indexed files pass the security scan.
Doctor and verify readiness limits remain separate; no provider call or sponsor/submission certification.

Guarded Quorum-only apply PASS, private backup `upgrade-20261027T232204Z`, previous release
`20261027-also-today-r2`. Existing judge session/preferences and exact event/photo payloads survive
the switch/restarts. All 15 original users/preferences, 15 edition original/sidecar/meta files, SSH,
environment and 24 original container identities/start times remain intact. A temporary 25th container
in the preliminary baseline ended independently; the original 24 are unchanged. No Docker mutation.

After the guard was active, the operator created only the new ordinary non-staff `quorum-demo` user,
in the permission-free `Quorum public demo` group, with the four demo topics. The creation transaction
compared every original account/profile/password hash and preference row before/after and preserved
them exactly. Final count: 16 users; SQLite OK, both services active, reader on, publisher off.

Actual new-account acceptance PASS: UI login to the explicitly dated 27-Oct board, 9 stories / 4 topics,
all 9 photographs at 1440/390 without overflow, evidence and investigation trace, profile/password/topic
POSTs all 403 with unchanged state, staff access denied, visible read-only error and logout. No existing
private credential was published. HTTPS 200 / TLS verify 0.

The repository Website is `https://quorum.raccncode.com/`. About now has a dated demo login link and
the dedicated public credentials, verified by a fresh GitHub API read. The browser-confirmed public
account can be used by everyone; personal settings require a separate registered account.

Rollback precaution: **deactivate only the dedicated public demo account before returning to code that
lacks the mutation guard**, and remove its public credentials from About while unavailable. Otherwise
old code would allow visitors to change the shared password. Preserve every private account and edition;
no database restoration is needed. Reactivate only after the guard is restored and verified. This small
follow-up records the guarded rollback target; it does not claim a new actual rollback rehearsal.
