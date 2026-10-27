# Quorum web backend

Django 5.2 LTS, session authentication, Unfold-based **Quorum Control**. This database owns only auth, sessions, preferences and login attempts. It never opens collector tables. Architecture: [approved clarification](../docs/DECISIONS.md#stack-and-work-blocks).

[Web Integration: Start Here](../docs/TEAM_HANDOFF.md) indexes architecture, current contracts, testing and owner notifications.

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

## Curated lead photos

`editorial_photos.py` attaches separately reviewed lead-photo
metadata to the installed reader's optional article presentation, only after the original/sidecar/install
triplet validates and the exact snapshot SHA256 + topic/date/event matches. Canonical scope/licences:
docs/DECISIONS.md › Stories as articles › Photos. No network/model call, original rewrite or producer contract.

The private `DATA_DIR/editorial-photos/current.json` contains schema `quorum.editorial-photos.v1`,
`reviewed_by`, timezone-aware `reviewed_at`, and `entries`; each has `topic_id`, `edition_date`,
`snapshot_sha256`, `event_id`, and `photo` (`url`, `source_url`, `license_url`, `license`, `credit`,
`caption`, `rights_confirmed: true`). HTTPS origins and licence values match the existing frontend guard.
Verify the actual image's licence, author, subject/date and loading before marking it reviewed; a file photo's
caption must say so. No photo is preferable to a misleading image. Real manifests/assets stay outside Git.

`manage.py editorial_photos --file <private.json> --sha256 <hash>` validates exact installed bindings and
reports the current manifest SHA256 (or `none`). Add `--install --expected-current <reported hash|none>`
to atomically publish as the Quorum service account; stale writers are refused. Root 0700, files 0600.
Each manifest's exact bytes are also saved under `<sha256>.json`; rollback republishes a previous reviewed
manifest with the current expected hash. Removing `current.json` disables all curated photos. A new edition
version cannot inherit an old photo by its title. Invalid/unavailable media retains readable news and the
existing placeholder; reader/auth/publication rules and all original edition bytes stay unchanged.

## Web API

The operator-assigned Django group `Quorum public demo` marks an intentionally public, non-staff
shared reader. Profile/password/preference POSTs return 403 for that group; session/profile/feed GETs,
login and logout remain available. No new API fields, schema or permission grants. Give the dedicated
account the four demo topics before publishing its credentials; never publish an existing private judge
or staff password. Canonical authorization: docs/DECISIONS.md › User account and interface.

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
| preview/reasoning | GET | Development-only, authenticated localhost/DEBUG/opt-in gates; optional `date`/`version`; never ordinary feed or publication |

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

Reasoning 1.0 editions for signed-in readers: `reasoning_snapshot --file … --sha256 … --sidecar … --sidecar-sha256 … --producer-commit … --install` copies an accepted edition into `QUORUM_REASONING_EDITIONS_ROOT/<topic>/<date>/v<N>.json` with its sidecar and an install record (mode 0600; a version is never overwritten); `--allow-fictional` works in DEBUG only, for a rehearsal with the bundled sample. The producer's config is read with `git show <commit>:reasoning/config/reasoning.toml`, so run `git fetch origin` first (reasoning pushes every producer commit before handing files over); on a release without `.git`, pass `--producer-config <reasoning.toml>` with the matching file instead. Each edition row of the feed carries the preview's honesty labels (`provisional`, `corpus_as_of_utc`, `edition_window_utc`, `warnings`) and every roundup line keeps the producer's `label`, `line_source` and `needs_review`; `publication.provisional` is true when any edition of the day is, with `publication.corpus_as_of_utc` the earliest capture time among those editions; an event page narrows both to the event's own edition. The acceptance report and the install record say where the producer's config came from (`config_source`: git or file). With `QUORUM_ENABLE_REASONING_READER=1`, `/api/feed/` and `/api/events/<id>/` answer from the installed editions of a date before the proposal store, for signed-in users only; nothing changes for anonymous visitors or while the flag is off. See `portal/reasoning_editions.py`.

## Decisions

2026-10-27 · rcc00n / Codex · WEB-PUBLIC-DEMO-01: group-marked shared readers cannot mutate
profile, password or preferences; enforce on the server, with the existing 403 error displayed by the
portal. Why: Vadim explicitly requested one public demo login/password, and a visitor must not be able
to change the shared access or feed. Normal accounts and their API behavior are preserved.

2026-10-27 · rcc00n / Codex · WEB-MEDIA-01: reviewed lead photos live in an atomic private manifest,
bound to exact accepted snapshot SHA256/topic/date/event; immutable manifest copies and expected-current
hashes protect rollback/concurrent operators. Missing/invalid media preserves readable news; no model call
or original/sidecar/metadata rewrite. Why: Vadim requested real images while teammates already process the
topics. Operation: › Curated lead photos; canonical scope: docs/DECISIONS.md › Stories as articles › Photos.

2026-10-26 · rcc00n / Codex · The installed reader honors producer expires_at as a stale publication notice while retaining original content. Why: installation time must not reset a recorded freshness deadline; existing frontend stale handling remains applicable.

2026-10-26 · rcc00n / Codex · Installed event projections add `reasoning_context` with exact edition trace/roundup/date/version and the story ID/title index. Why: preserve real investigation/evidence navigation without fabricating structured analysis or returning duplicated full stories. Canonical upstream output remains unchanged.

2026-10-26 · rcc00n / Codex · The reasoning installer sets root, topic and date directories to 0700 and rejects linked edition directories; files stay 0600. Why: private immutable editions must retain their permissions when installed into an existing hierarchy under the service user.

2026-10-26 · rcc00n / Codex · Installed-reader responses require the original snapshot, bound sidecar and matching install-record hashes/identity; a broken installed day reports an error instead of pending, and fictional installs are served only in DEBUG. Why: file loss or replacement must not bypass acceptance or make a production demo fixture appear as genuine news. This is storage integrity, not independent execution or source verification.

2026-10-24 · rcc00n / Codex · Optional local `QUORUM_REASONING_PREVIEW_SIDECAR` binds snapshot hash, edition, run, status and window before exposing only provisional/capture/hash metadata. Why: genuine provisional output needs visible corpus limits without exporting private sidecar paths or changing strict production ingestion. This verifies the binding, not execution or row-manifest truth. Exact-byte historical v3 ledger handling is documented at `reasoning_preview.envelope` call; all other ledger checks remain strict.

2026-10-24 · rcc00n / Codex · Opt-in reasoning previews join validated catalog metadata in the portal projection, leaving the original reasoning JSON and publication gates unchanged. Identity policy is canonical in `catalog_sources.bind_sources`; dates absent from the registry stay null. Why: real source ratings need exact identity and attribution without changing the owner snapshot contract.

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-23 | rcc00n / Codex | Local preview labels follow the producer fictional flag; collected-corpus declarations remain unverified, deterministic stand-ins are explicit, and all inputs remain unpublished | Permit honest inspection of real local corpus experiments without granting publication authority; source/quote provenance gaps remain visible |
| 2026-10-23 | rcc00n / Codex | Accept canonical reasoning 0224ca6 optional quote identity/access/version bindings, third-review declarations, fallback-summary marker, by_headline booleans, model/title line_source and up to 12 text/reason extraction audit rows per trace step | Preserve current owner output unchanged with strict field checks (exclusive identity namespaces, nullable Unicode ranges/hash/timestamps); declarations and a false headline-only flag never establish independently verified source text |
| 2026-10-23 | rcc00n / Codex | Development reasoning consumer preserves optional fact-checker/model-call provenance and upstream `context` claims; counts are integers 0–100000, answered-by maps have at most 100 nonempty model keys with positive counts, and supplied totals/error counts must agree | Accept the original NVIDIA fixture result without weakening unknown-field/reference checks or treating declarations as publication authority; bounds limit untrusted ledgers, and old canonical fixtures remain supported |
| 2026-10-23 | rcc00n / Codex, explicit compatibility authorization | Require the current canonical 1.0 envelope in the development consumer, validate UTC/calendar-window semantics, retain declarations without publication authority, and redact arbitrary partial-error messages | Support all three upstream fixtures without exporting private logs or weakening the strict production schema |
| 2026-10-22 | rcc00n / Codex | Reasoning-owned canonical 1.0 consumer in a separate gated localhost preview; production validator/store/adapter unchanged | Support the actual fictional sample without fabricating collector provenance or enabling publication |
| 2026-10-22 | rcc00n / Codex | Unfold 0.81 with branded pages; superuser-only account management; read-only preferences/source views | Reuse Django security while preventing staff self-escalation and cross-workstream writes |
| 2026-10-22 | rcc00n / Codex | Optional external catalog export pinned to collector commit, with provenance; live events/digests remain empty | Enable real preference selection and source inspection before runtime integration, without duplicating team registry data in this branch |
| 2026-10-22 | rcc00n / Codex | Pinned jsonschema with explicit format checks; private local immutable snapshot store and CLI, opt-in publication | Validate the portal-owned proposal without exposing ingestion or giving processing access to auth data; team transport/schema approval remains required |
| 2026-10-23 | rcc00n / Codex | Bounded value-free schema diagnostics and read-only compatibility report; configured catalog failures remain errors | Give upstream owners useful local feedback without leaking payloads or converting outages into empty successful editions |


Snapshot implementation and unapproved transport: [portal-owned proposal](../docs/SNAPSHOT_PROPOSAL.md). Release gates: [checklist](../docs/RELEASE_CHECKLIST.md); workstream evidence: [inventory](../docs/IMPLEMENTATION_STATUS.md). No production snapshot publisher is enabled.

Read-only **internal portal proposal** compatibility: `portal_snapshot validate --file /path/to/candidate.json`. The [canonical handoff](../docs/PORTAL_INTEGRATION.md#read-only-compatibility-command) specifies the JSON report, exit codes and limits. It checks the same production validator/projection without creating a snapshot store or touching auth records.

Canonical reasoning 1.0 **FICTIONAL local preview** and exact sample pin: [integration handoff](../docs/PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview). Start with `node web/tests/boundary.cjs --reasoning --serve` after the external Next build; this isolates local test auth and keeps the production publisher unused. `--reasoning` without `--serve` runs the real HTTP/browser acceptance suite. Neither command accesses production credentials.

Read-only genuine-file acceptance (no catalog, auth writes, inference or publication):

```bash
python backend/manage.py reasoning_snapshot --file <private-original.json> --sha256 <owner-full-sha256> \
  --sidecar <private-original.sidecar.json> --sidecar-sha256 <owner-full-sidecar-sha256> \
  --producer-commit <full-producer-commit>
```

The JSON report separates `compatible` from `metadata_valid`. A config discrepancy exits nonzero; even matching metadata keeps `execution_verified`, `source_text_verified` and `published` false. It never rewrites inputs. Optional local tests take `QUORUM_TEST_GENUINE_SNAPSHOT`; CI skips those two private-original tests and uses synthetic negative cases instead.

2026-10-26 · Anastasia / Claude Code (Vadim's and Yelysei's agreement given privately via Anastasia) · The reasoning preview adapter (`reasoning_preview.py`, `present_reasoning`) also hands each story's article to the portal as the presentation model `event.article` (paragraph kinds fact/context/statement/not_confirmed with claim ids, `reading_minutes`; the photo stays withheld). It still invents no `analysis`: no document ids, hashes, offsets or review times (the existing test keeps asserting that); the story page reads the claims from `event.reasoning`. Test: `test_reasoning_article.py`. Why: the story page (web/DESIGN.md › Decisions) renders only an article the writer wrote, and the preview is the only path that carries one until the projection maps it.

### Historical v4 editorial hold

The exact original closed-v4 hash has a preview advisory and acceptance hold for
its owner-disclosed impact contradiction. Producer score and claims are unchanged;
the advisory does not bypass JSON, provenance or publisher validation. The raw
artifact and independent D5/ledger verification remain necessary. The existing
warning array carries this local editorial disclosure; no producer contract changes.

The original closed-v4 sidecar uses a different historical format. Its exact
SHA-pinned bytes can bind only the exact original snapshot for a private preview;
unknown/mutated closed-format sidecars fail. Edition end is shown as a boundary,
never invented as a corpus capture timestamp. Its config hashes are truncated:
local Git hashes are reported independently, and full metadata acceptance remains
blocked along with impact review. The production publisher is unchanged.


2026-10-25 · rcc00n / Codex · Closed v5/v6 private preview sidecars are bound only to their exact original SHA-256 pairs, as v4 was; no generic closed-sidecar format is enabled. Why: inspect the current owner handoff without weakening original-file binding, production validation, execution checks or the historical v4 impact hold. `QUORUM_TEST_CLOSED_HANDOFF_DIR` enables the private-original pair tests locally; hosted CI skips them explicitly.


The read-only acceptance command compares both complete LF and CRLF config hashes for the closed v5/v6 sidecars. Successful `metadata_valid` still leaves execution/source verification and publication false. Historical v4 keeps its incomplete original-sidecar diagnostic and impact hold; a separately supplied attestation never silently edits or overrides the original metadata.

2026-10-26 · Anastasia / Claude Code (covering Vadim's items this week at Yelysei's request, Issue #2 comment 6426106426; Vadim's recorded decisions stand) · Login-only reader for installed reasoning 1.0 editions (`portal/reasoning_editions.py`): opt-in by `QUORUM_ENABLE_REASONING_READER=1` and `QUORUM_REASONING_EDITIONS_ROOT`, filled only by `reasoning_snapshot --install` after a clean acceptance; the feed presents each edition exactly as the DEBUG preview does (`present_reasoning`), one `editions` row per topic, a day is `partial` only when every edition read for it is partial, roundup lines carry no event link, `status` is `demo` for fictional files, `publication.revision` is `editions-<date>`. The proposal store, the preview and the rule that anonymous visitors see no publication are unchanged. Why: the store takes only the proposal format, the preview is loopback-only, and the judges need a login that shows the real editions before the deadline (agreed in Issue #2: Yelysei 6411653104, Anastasia 6411408519).

2026-10-27 · Anastasia / Claude Code · Consistency check of the edition output path (`anastasia/edition-path-consistency`, after master's acceptance, reader tests and installed-edition browser check ran on the real 26 October edition and the fictional sample): `reasoning_editions.py` appends a producer's recorded failure to the feed's `errors` in the API's shape (`code` = `reasoning_<node>`, or `reasoning_error` for an older plain-string row, which the parser still accepts; `message` as redacted by the preview; `event_id`) with the edition's `topic_id`, and its own "could not be read" row carries the topic too, so one topic's partial or unreadable edition no longer cancels another topic's quiet day; `completion` follows the preview's rule and counts a declared `sources_missing`; the roundup STATUS map names all six producer labels (three map to claim statuses, three are `unknown` on purpose). `fixtures/reasoning-demo/snapshot.sample.sidecar.json` + `producer-config.sample.toml` hold the bytes the producer's `build_sidecar` + `serialize` write for the bundled (fictional) sample (its CLI refuses a fictional snapshot and hashes the real `reasoning.toml`): `test_reasoning_sidecar.py` binds them, `test_reasoning_acceptance.py` accepts them with `--producer-config`, and reasoning's own `tests/test_portal_sidecar_fixture.py` regenerates them, so a change to the producer's builder or to the portal's binding fails a test before a hand-over. The portal suite does not load the script: a release archive ships `backend/` and `deploy/` only, and the VPS upgrade runs this suite there (review of 0c130c2). Why: the installed path had no test in the producer's exact shape, and the API's error rows lacked `code` and a topic. The edition status files (`QUORUM_STATUS_ROOT`, `reasoning_status`, DECISIONS › Daily editions) still have no portal consumer: NOT_STARTED, reported in Issue #2.
