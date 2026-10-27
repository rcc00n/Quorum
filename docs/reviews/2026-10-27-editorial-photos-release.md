# Reviewed lead-photo release, 27 October 2026 UTC

WEB-MEDIA-01, owner rcc00n / Codex. Canonical coordination:
[Issue #2](https://github.com/rcc00n/Quorum/issues/2). The teammates supplied and installed the
news editions; this work adds reviewed presentation images without collecting or reasoning again.
Scope and operation: [DECISIONS › Photos](../DECISIONS.md) and
[backend README › Curated lead photos](../../backend/README.md#curated-lead-photos).

## Complete photo coverage and quality follow-up — WEB-MEDIA-02

DEPLOYED: `20261027-photo-coverage-r2`, release-master `a9e1edee3a849c5e66ac4409c032b58a6e5fe0a3`.
This follow-up supersedes the earlier seven-photo coverage limitation; the older release record remains historical.

Follow-up source `0499866d51a65c549d3a644a6a039e24278714ca`, normal #93/#95 → integration → #94.
Production `20261027-photo-coverage-r2`, source-bound archive 23,635,748 bytes / 2,699 members,
SHA256 `af3cfd1d24cc8e1cd39dbcb63ab478160184a2c16a750c0279db14f22723e757`.
The prior photo-coverage-r1 archive was staged/read-only planned, never deployed or relabelled.
The accepted Also today #85/#92 is retained.

The final private ten-entry manifest
`2520cc6168946b7fe81ecba48bd341245317f0c968aaaef66f829eca46c27c30`
covers all nine 27-Oct stories and the one retained 26-Oct story. Five earlier non-Starlink entries are
unchanged. Both blurry orbital-video stills are replaced with a sharp 1920 × 1441 terminal photograph.
The two ceasefire slots and the historical legal story are filled; the AI quiet day and roundup rows do
not claim to be photographed stories. No model call, data collection or original-edition rewrite.

| Image and source | Credit / licence | Delivered size / slots |
| --- | --- | --- |
| [Starlink terminal in Ternopil region, 24 November 2022](https://commons.wikimedia.org/wiki/File:Starlink_antenna_on_the_ground.jpg) | Odapresste; CC-BY-SA-4.0 | 1920 × 1441 / 2 Starlink stories |
| [Kherson and the Antonivskyi Bridge, September 2006](https://commons.wikimedia.org/wiki/File:View_of_Kherson_and_Antonovskiy_bridge,_2006.jpg) | Uaquantum; public domain | 1920 × 1280 / local ceasefire story, explicitly before the war |
| [Melania Trump at the U.S. State Department, 24 March 2026](https://commons.wikimedia.org/wiki/File:Melania_Trump_delivers_remarks_at_the_Fostering_the_Future_Together_Global_Coalition_Summit_March_24,_2026_(55166795974).jpg) | Andrea Hanks / The White House; public domain | 1920 × 1052 / other ceasefire story, explicitly a file photo |
| [U.S. Supreme Court, 1 June 2024](https://commons.wikimedia.org/wiki/File:Exterior_of_Supreme_Court_Building_20240601.jpg) | 颐园居; CC-BY-SA-4.0 | 1920 × 1280 historical story; 960 × 640 illustrative landing example |

Actual Commons metadata/file pages, source/date/author/licence, MIME and visual contents were checked.
The first ten-entry manifest `f30b5a94…da8be` passed loading tests, but visual review rejected an
eyes-only portrait crop in the existing 2:1 frame. The final wide official photo corrects that without
changing the story frame or adding a focal-point schema. Superseded manifest copies remain private.

The landing example keeps its card, text band and palette. Its photo is explicitly illustrative and
dated, with source/author/licence links; it does not purport to be current news. Bright floor pixels
required a small existing-band adjustment: 64% ink with 80% white small metadata gives minimum
contrast 6.71:1 for the white title and 5.00:1 for the metadata against a pure-white photograph.
The source-tally hero and all news/trace fixtures are unchanged. Module decision: web/README.md.

Exact-source CI 40582820952 (688d17d) and 40583940467 (0499866): portal/combined-python PASS.
[Exact final release CI 40584490207](https://github.com/rcc00n/Quorum/actions/runs/40584490207): both jobs PASS.
Clean final build/typecheck/receipt/archive checks PASS; existing full
isolated Django/Next/Chromium suite PASS before the CSS-only contrast adjustment, and final-source
hosted CI runs the regressions again. Actual final-package photo, attribution, licence, four widths
(1440/768/390/320), no page errors/overflow/failed static assets/API calls PASS. Initial extra preview
mistakenly ran unpackaged standalone without static assets; correcting the harness to the actual
package resolves its unstyled overflow. Visual captures wait for hydration and the existing reveal.

Genuine production login/logout/anonymous401 and all ten final story images/source/licence/captions,
Home nine-of-nine at 1440/390 PASS before the landing cutover. After the cutover, public landing
image/label/source/licence/final contrast passes at all four widths,
with no failed static assets, page errors, overflow or API calls. Home nine-of-nine photos load again at
1440/390; native Starlink width is 1920 pixels, all ten current/history API photo bindings match, and
login/logout/anonymous401 pass. The historical story's actual 1920px photo/caption/source/licence
also passes at both 1440/390 after cutover. Settled public-photo-only captures visually inspected.
Target checksum/path/type/extraction, current ten-photo binding validation and guarded read-only
plan PASS. Guarded Quorum-only apply PASS; private backup `upgrade-20261027T211430Z`, rollback target
`20261027-also-today-r1`. No migrations or dependency additions. This follow-up did not repeat the
previous release's actual rollback rehearsal; it does not claim that rehearsal as new evidence.
Existing judge session/preferences and exact pre-existing event payloads/photos survive the actual
code switch and service restarts. All 15 account/credential/profile records (normal login timestamps
excluded), preferences, 15 original/sidecar/meta files with ownership/modes/hashes, SSH/environment and
all 24 original container identities/start times are preserved. SQLite OK, services active, reader on,
proposal publisher off; final HTTPS200/TLS0. A strict whole-container-list comparison initially differed:
one additional container started at 21:15:03Z after cutover and disappeared before a read-only inspect
could identify it. No original container changed; this work issued no Docker start/stop operation.
A fresh final aggregate comparison returns the exact 24-container baseline and all other preserved values.

Doctor: 10 PASS / 0 FAIL / 5 BLOCKED / 1 NOT_TESTED (local gh/default-branch probe, WSL command,
Docker access and sponsor headroom checks; no daemon/resource change). Connected GitHub confirms the
actual master/merges; uname confirms WSL2. Verify offline: 5 PASS / 0 FAIL / 1 BLOCKED (live sponsor
integration intentionally not exercised). No provider acceptance or submission claim.

Rollback: private guarded code/static record points to `20261027-also-today-r1`; this retains the
independent private ten-photo manifest. Media rollback uses the existing expected-current-hash command
with an immutable reviewed manifest. No database restoration or original edition rewrite is needed.
The image host remains an external dependency; invalid/unavailable media preserves readable news.

The earlier WEB-MEDIA-01 record below is historical. Its two-unreviewed-photo limitation and earlier
seven-entry manifest are superseded by this ten-story coverage, without altering the original evidence.


## Earlier WEB-MEDIA-01 release (historical)

## Source and artifact

DEPLOYED: `20261027-editorial-photos-r2`, actual source
`169b0fc744e8dac8225c2f3e198712d858d110c1`. Normal source/integration/release PRs:
[#86](https://github.com/rcc00n/Quorum/pull/86),
[#87](https://github.com/rcc00n/Quorum/pull/87),
[#88](https://github.com/rcc00n/Quorum/pull/88),
[#89](https://github.com/rcc00n/Quorum/pull/89).
Release-master `3e1299c2b52194ebbe7b41679e9cdbbac8631bfd` contains the same runtime changes.
Later documentation does not relabel the compiled release.

Source-bound clean archive: 23,636,399 bytes, 2,699 validated regular file/directory members,
SHA256 `a4e33bf439769e09759f331c155d1b6af7b0661b8df7c4c7333f5dbbb7b1ff28`.
Local/target checksum, path/type, build receipt and guarded read-only plan passed.
The separately published private manifest has seven exact installed-story bindings, SHA256
`b03c03bc5ec1f848a14429b5f3438bd736bc3b4f6313bffb655c084237fffdbb`.
No manifest, original news payload, account data or credentials are committed here.

## Published pictures

Four distinct real images fill seven story cards and their pages across immigration, tariffs and
Russia–Ukraine. Each source's actual image, author, date, licence, MIME/size and visual contents were
checked. The four delivered files total 911,860 bytes. Captions describe the image and identify file
images rather than presenting an old photograph as a picture of today's incident.

| Image and source | Credit / licence | Published slots |
| --- | --- | --- |
| [Ilhan Omar's official portrait, 3 December 2018](https://commons.wikimedia.org/wiki/File:Ilhan_Omar,_official_portrait,_116th_Congress_(square).jpg) | Kristie Boyd / U.S. House Office of Photography; public domain | 2 immigration stories |
| [ICE officer beside a removal aircraft, 7 December 2017](https://commons.wikimedia.org/wiki/File:ICE_agent_stands_by_aircraft_for_removal_flight.jpg) | U.S. Immigration and Customs Enforcement; public domain | 1 immigration story |
| [South Carolina State House, 20 January 2018](https://commons.wikimedia.org/wiki/File:2018_South_Carolina_State_House_(cropped).jpg) | Farragutful; crop by SVTCobra; CC-BY-SA-4.0 | 1 immigration and 1 tariffs story |
| [Starlink mission, 24 May 2019](https://commons.wikimedia.org/wiki/File:Starlink_Mission_(47926144123).jpg) | Official SpaceX Photos; CC0-1.0 | 2 Russia–Ukraine stories |

The other two ceasefire stories have no reviewed photo. The AI-regulation edition is a quiet day with
no story photo to fill. No generated news image, unlicensed agency image or automatic photo search is
presented as verified. A new photo can be reviewed and installed without a web rebuild or model call;
a new edition version requires fresh exact bindings.

## Tests and real integration

- Backend: full portal suite 103 tests, PASS with five existing skips; focused 20-test reader/media suite
  PASS. Exact snapshot/topic/date/event matching, unsafe metadata, atomic archive/stale-writer/rollback,
  missing/bad manifest, anonymous access and preservation of synthetic installed originals are covered.
- Frontend: clean build/typecheck and photo origin/spoof guards PASS. The isolated Django/Next/Chromium
  boundary PASS, including a labelled DEMO test: rejected prose remains hidden, claims remain readable,
  and the existing credited/licensed photo appears at 1440/390 with an intercepted fictional SVG.
- Exact source/final CI: [R1 source](https://github.com/rcc00n/Quorum/actions/runs/40573712041),
  [R1 release](https://github.com/rcc00n/Quorum/actions/runs/40574271628),
  [R2 source](https://github.com/rcc00n/Quorum/actions/runs/40577208480),
  [R2 release](https://github.com/rcc00n/Quorum/actions/runs/40578036570): portal and combined-python PASS.
- Final runtime-source public-index scan: 489 files PASS. An earlier synthetic negative test contained
  a literal credential-shaped URL that the scanner correctly rejected. Follow-up `9a1d6e0` constructs
  the fictional value in the test; scanner rules are unchanged and no real credential was involved.
- Doctor and verify offline each report 5 PASS / 0 FAIL / 1 BLOCKED. Live sponsor/provider integration
  was not exercised; no inference, duplicate collection or provider spending occurred for this work.
- Genuine production UI login/logout, anonymous feed 401, all seven actual story photos and seven Home
  card photos load at 1440/390. Captions, alt text, source/author and licence links match the reviewed
  metadata. No page errors or horizontal overflow. Public-photo-only captures visually inspected.
  The parsed authenticated reasoning payload remains deeply equal before/after viewing;
  `reasoning.photo` stays null while the derived presentation article receives the reviewed photo.

The initial R1 live check caught an integration gap: the claims-only reader had no photo slot.
The manifest was paused before acceptance. R2 reuses `StoryPhoto` in that branch without changing
`storyReadable`, prose, claims, review flags or the owner's Also today UI. A later acceptance attempt
caught a harness selector error (`a.tb-card` instead of the actual card anchor); the corrected external
check passes all seven, without a further product change. Neither failed attempt is counted as acceptance.

## Preservation and actual rollback

The guarded R2 apply made private backup `upgrade-20261027T203406Z`. Actual Quorum-only code/static
rollback to `20261027-editorial-photos-r1` and guarded reapply passed; reapply backup
`upgrade-20261027T204403Z`. The manifest was safely paused during that rehearsal, then the same seven
reviewed bindings were explicitly reactivated as the `quorum` service user with 0700 directories and
0600 files. Immutable manifest copies and expected-current hashes preserve the media rollback path.

An existing judge session, preferences and every pre-existing event payload including its photo survived
the actual rollback/reapply and restarts. Final private aggregate comparisons preserve all 15 existing
users/credential/profile records (ordinary login timestamps excluded), preference rows, all 15 installed
original/sidecar/metadata files with ownership/modes/hashes, SSH/private environment and all 24 unrelated
container identities/start times. SQLite integrity OK; both Quorum services active; reader enabled and
proposal publisher disabled. Final public HTTPS 200 / TLS verify 0.

Immediate media-only rollback: restore a previously reviewed manifest through the documented command,
or remove `DATA_DIR/editorial-photos/current.json` to return to the existing no-photo presentation.
Code/static rollback uses the private guarded release record. No database restoration or original-edition
rewrite is needed. R1 lacks the claims-only photo fix, so pause the manifest before choosing that target.

## Handoff and limits

The four 27-Oct editions are installed by their owners: immigration 4 stories / 33 roundup;
Russia–Ukraine 4 / 15; tariffs 1 / 7; AI-regulation 0 / 12. The prior 26-Oct edition is retained.
These counts describe the installed data, not newly executed processing by Codex.
Anastasia's Also today PR #85 remains a separate release; its source must retain this media code.
Her reported real-data spectrum tilt assertion is separate and is not certified by these photo checks.
Full sponsor/recall/submission gates remain with the owners.

All agents' current-work authorization is recorded by normal #83/#84 merges, master
`acecc58d7e44afb7a4cf9f4fb1a6d0ce751244dc`, and
[the explicit tracker notice](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6451782872).
