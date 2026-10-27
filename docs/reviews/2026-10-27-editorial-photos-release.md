# Reviewed lead-photo release, 27 October 2026 UTC

WEB-MEDIA-01, owner rcc00n / Codex. Canonical coordination:
[Issue #2](https://github.com/rcc00n/Quorum/issues/2). The teammates supplied and installed the
news editions; this work adds reviewed presentation images without collecting or reasoning again.
Scope and operation: [DECISIONS › Photos](../DECISIONS.md) and
[backend README › Curated lead photos](../../backend/README.md#curated-lead-photos).

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
