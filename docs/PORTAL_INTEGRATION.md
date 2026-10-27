# Portal integration handoff

Start with [Web Integration: Start Here](TEAM_HANDOFF.md). Owner: Vadim (@rcc00n); authorized web branch `feature/web-portals`. Shared status/notifications: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). This is the current web boundary guide, not a competing reasoning specification. Historical reviews remain in Git and [verification history](PORTAL_VERIFICATION.md).

## Inspected contracts and evidence states

Historical read-only review pins (superseded for current implementation status by the daily-editions update below):

- Reasoning `origin/yelysei/agents@6ea82434d0f06cefb51f5536732ceac68e9780ef`: **canonical reasoning 1.0**, [ARCHITECTURE §8](https://github.com/rcc00n/Quorum/blob/6ea82434d0f06cefb51f5536732ceac68e9780ef/docs/ARCHITECTURE.md#8-output-contract-for-the-portal), `reasoning/quorum_reasoning/{nodes/publish.py,tools/corpus.py,tools/fetch_text.py,state.py}`, three `docs/examples/snapshot.*.json` samples. Fetch before integrating a later revision.
- Collection `origin/data-collection@18fb009b4b36e995e765563203edbf742475a20b`: `collectors/schema.sql`, `common.py`, `run.py`, `README.md`, `sources.csv`, `zetaris/01_register_postgres.sql`.
- Master `c3cc5ac4a65855769ab48e36a1d59d5cc1ae261d`: AGENTS.md and DECISIONS.md. The newer reasoning branch documents `russia-ukraine-war`; inspected collector `TOPICS` still contains `ukraine-aid`. Do not silently alias them or describe the reasoning branch's newer topic decision as already merged into master.

**TESTED** means local deterministic fixtures passed; **DEPLOYED** requires intended-environment verification; **INTEGRATED** requires actual cooperating external components. **BLOCKED** names an unmet dependency. **PROPOSED** labels an interface option, not an AGENTS.md completion state. The website/auth/catalog are deployed at the release recorded in [deploy/STATUS.md](../deploy/STATUS.md). The reasoning 1.0 consumer is TESTED, development-only, **not INTEGRATED or DEPLOYED**. No actual sponsor run is established by these samples or by `fictional:false`.

## Shared architecture and ownership

```text
Anastasia: collectors → separate PostgreSQL → Zetaris QUORUM_COLLECT tables
                                              ↓
Yelysei: LangGraph → Meterless/Nemotron → reasoning 1.0 snapshot
                                              ↓ [production bridge/transport PROPOSED]
Vadim: validated presentation → Django DataAdapter → same-origin Next.js
       separate portal SQLite: auth, sessions, preferences, login abuse limits
```

Next.js owns reading/navigation, responsive UI and view models. Django owns authentication, permissions, CSRF, API, adapters, strict portal validation/store and Quorum Control. Neither collector nor reasoning may write the portal auth DB. No inference, collectors, PostgreSQL/Zetaris cluster or workers belong on the current website VPS. Sponsor integration requirements remain in [rules evidence](RULES_CHECK.md); fixtures cannot satisfy them.

### Existing web boundary

`GET /api/feed/?date=YYYY-MM-DD&topic=id&revision=id` requires a Django session. Missing date uses server day; missing topic is `""`. Invalid date/revision is 400; unauthenticated is 401; writes are 405. The response is a `Snapshot`, `Cache-Control: no-store`. Configured read failures remain ERROR. `GET /api/events/<id>/?date=...&revision=...` resolves stable event/revision links; without date it finds the latest indexed event. Absent results are never fabricated.

`backend/portal/integration.py` defines `DataAdapter.snapshot(day: str = "", topic: str = "", revision: str | None = None) -> PortalSnapshot`. Preferences/Control also call `snapshot()` for catalogs. The default `PublishedAdapter` uses `CatalogAdapter` while snapshot storage is unconfigured. `CatalogAdapter` reads an explicitly reviewed external export, **not live Zetaris**. No tenant/user is passed into the adapter; UI topic selection is not authorization. Daily-edition semantics are now approved in [DECISIONS.md → Daily editions for users](DECISIONS.md#daily-editions-for-users-topics-delivery-time-where-runs-execute); delivery-time storage/release gating and a safe topic-write bridge are not implemented.

Same-origin Nginx routes `/` to Next.js, `/api/` and `/staff/` to Django, static staff assets separately. `GET /api/session/` supplies `{user, csrfToken}`; all POSTs, including login/register/logout, send cookies plus `X-CSRFToken`. Login rotates the token. Production cookies are Secure/HttpOnly; no JWT/localStorage. GETs require sessions but no CSRF header. [Backend endpoint inventory](../backend/README.md#web-api) is canonical. Machine authorization is separate and unapproved; never reuse human admin sessions to publish.

## Anastasia — collection handoff

Collection owns **six** tables: `sources`, `topics`, `documents`, `official_docs`, `quotes`, `coverage`. Do not recreate/migrate them in Django. Runtime upserts topics/source publications into its Postgres; the registered Zetaris namespace is **`QUORUM_COLLECT.<table>`**, not an assumed `.public` layer. Registration/query scripts and any reported live evidence belong to Anastasia. This web milestone made no sponsor requests.

| Table/data | Reasoning/portal handoff |
| --- | --- |
| sources/topics | Stable registry IDs/names, domain, kind/tier, independence, nullable normalized ratings/audience and provenance; collector query terms stay upstream |
| documents | Original/canonical URL, source/topic ID, title/lead/byline, published/fetched dates, achieved access, content hash, version, supersedes_id, wire_origin |
| official_docs | Separate official ID namespace, source/topic/URL, document type/number, text and signed/published/fetched dates; official assertions are still attributed |
| quotes | Collection-owned schema; reasoning supplies claim link, document OR official-document ID, verbatim quote, offsets, version hash and verification time |
| coverage | Publication/event mapping, each publication retained, counted_in_confirmation; agree writer with reasoning, do not manufacture independent confirmations |

Use **`collectors.common.fetch_text(url, title=..., lead=...)`** and `verify_quote(text, quote, char_start, char_end)`. Offsets index the exact returned Python Unicode string in **code points**, start-inclusive/end-exclusive (not UTF-8 bytes or JavaScript UTF-16). The portal never re-extracts HTML. `documents.content_hash`/`FetchedText.content_hash` use SHA-256 of UTF-8 `title + "\n" + lead + "\n" + body[:2000]` under `common.content_hash`; they are **not full-body SHA-256**. Preserve the actual representation/hash/version at quotation time. Do not equate this fingerprint with a full quoted-text hash; binding the exact extraction to reproducible quote verification still needs export/agreement.

Access **1**: permitted full text retrieved for analysis, not stored in documents. **2**: headline/lead only; disclose that limit, no inferred full-article framing. **3**: publication coverage only; cannot support claims/framing. Use achieved fetch level, not a configured registry preference. Reprints share original independence/wire provenance: multiple publications count for reach, not multiple confirmations. Reviewer independence is separate from original-source independence.

Ratings and audience remain JSON `null` when absent, never guessed or zero-filled. Do not normalize twice; [DECISIONS.md → Spectrum ratings](DECISIONS.md#spectrum-ratings) owns formulas/thresholds. Preserve rating provider attribution and audience source/date. `deploy/export-catalog.py` reads reviewed definitions without executing collector code; production catalog updates require Vadim's release process. It does not prove collection health or synchronize selected topics.

## Yelysei — reasoning mapping

Canonical output belongs to Yelysei's §8 and code above. The portal consumer is `backend/portal/reasoning_preview.py`; TypeScript consumer types are `web/lib/reasoning.ts`. **Internal** production proposal `quorum.portal.snapshot.v1-proposal` belongs to Vadim and is documented only in [SNAPSHOT_PROPOSAL.md](SNAPSHOT_PROPOSAL.md) plus its executable schema. A production mapping between the two remains unapproved. Never treat UI types as an already approved agent API.

### Exact portal presentation fields

Executable definitions: [api.ts](../web/lib/api.ts), [analysis.ts](../web/lib/analysis.ts), [editorial.ts](../web/lib/editorial.ts), [reasoning.ts](../web/lib/reasoning.ts). Required core fields:

| Type | Fields |
| --- | --- |
| User (Django-owned) | username, name, email, topics, is_staff |
| Topic | id, name |
| Source | id, name, domain, audience, allsides, mbfc, adfontes; the last four are nullable |
| Evidence | text, explanation, sources: `{title,url}[]` |
| Event | id, topic_id, date, title, summary, importance: `{label,explanation}` or null, established/statements/disputed/unknown/coverage: Evidence[], sources: Source[] |
| Snapshot | status, topics, sources, events, digests: `{date,topic_id,summary}[]`; catalog_revision optional/nullable in TS, always returned by adapters |

Optional extensions: Source kind/tier/independence_group, rating_provenance, audience_source_url/as_of; Event analysis/article/reasoning; Snapshot publication/errors/editions/reasoning/preview. Follow the linked types for exact nested unions, optionality and bounds, rather than duplicating them as an upstream schema. Core pending JSON example: `{"status":"pending","catalog_revision":null,"topics":[],"sources":[],"events":[],"digests":[]}`. Full JSON examples that match the actual reasoning consumer are the three pinned [fixture files](../backend/portal/fixtures/reasoning-demo/README.md).

### Reasoning 1.0 fictional development preview

The development consumer also accepts the runtime's optional `provenance.fact_checker_model`, `model_calls`, `answered_by` and `model_errors`, and claim `kind: context`. It preserves model IDs, counts and context statuses verbatim. The backend module decision owns validation bounds; supplied totals must agree, unknown fields and invalid references still fail. The preview shows these as **reported** provenance, never independent provider verification. A contradictory producer summary remains unchanged and visible.

The first real NVIDIA model execution used a FICTIONAL fixture corpus, not real collected news: [run evidence and original hash](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6376895532). [Nightshift routing evidence](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6376996285) separately proves tiny Runtime requests, including explicit Ultra selection; it does not prove Verify duty or a Meterless Engine feature. Neither result closes the real-corpus/provenance/transport gates below. Use the [external snapshot acceptance command](PORTAL_VERIFICATION.md#external-real-model-fixture-acceptance) to test the saved original locally without replacing canonical fixtures.

The current envelope requires schema_version/topic_id/edition_date/run_id/version/status/summary/sources_missing/stories/roundup plus **generated_at, published_at (nullable), expires_at, edition_timezone, window.start/end, provenance.corpus/model/fictional**. `bar`, `errors`, `trace` remain optional. Unknown fields are rejected explicitly; notify before adding fields. No competing upstream JSON schema is introduced.

| Upstream | Portal presentation / transformation | Status / owner action |
| --- | --- | --- |
| topic_id, edition_date, run_id, version | Retained exactly; event topic/day and preview/history links use them | Supplied; topic registry mismatch needs Anastasia/Yelysei agreement |
| generated_at, published_at, expires_at | UTC RFC3339 validation, retained; non-null publication cannot precede generation; expiry must follow window end | Supplied; null is **unpublished**, not missing generated/expiry metadata |
| edition_timezone + window | Validate IANA zone and local calendar 05:30 boundaries; UTC intervals may be 23/25 hours at DST | Supplied/fixed upstream; no forced 24-hour arithmetic |
| provenance.corpus/model/fictional | Retained, shown as declarations; all preview output still labelled fictional/unverified | Supplied; independent model/corpus axes do not prove genuine run |
| stories[].event_id, claims[].id, article.claim_ids | Exact IDs and resolved references; no invented collector identifiers | Supplied for fixture; identity across reclustering/revisions unresolved |
| rank, headline, standfirst, reading_minutes, rubric | Upstream order, maximum ten without padding; article title/prose, exact impact rationale | Supplied |
| article fact/context/statements/not_confirmed | Claim-linked prose and source anchors; context remains context, statements remain attributed. Since 2026-10-26 the preview also emits it as `event.article` (kind `statements` → `statement`), so the portal's story page lays it out; no analysis is invented | Supplied; never promote context to established merely because §8's illustrative mapping suggests it |
| claims status/verifier/fact_checker/reason/evidence | confirmed → established unless statement; disputed → disputed; unverified → unknown; statement kind → attributed statements | Supplied; do not infer truth from a reported assertion |
| found_by, stance, is_document, independence_group | Paired primary/independent review chains, exact quotes and original URLs; no invented reviewer rounds/times | Supplied for fixture, not genuine provenance |
| spectrum.coverage, interpretations, outlets, left/right/note | Exact numerator/denominator grid and structural membership, framing appendix; four rating modes retain unavailable ratings | Supplied; partial frame failures may omit left/right/note while counts remain |
| roundup.empty_day/count/groups | Grouped Also today, stable item IDs/links/status/sources | Supplied: main/partial 2 items, one group; empty fixture 3 items |
| trace node/iteration/event_id/decision/reason/model/duration_ms | Array-order recorded timeline, stage/event filters and observed same-event return loops; zero durations/null models retained | 45 steps main/partial, 29 empty; no invented timestamps, causality or private thoughts |
| errors `{node,event_id,message}` | Validate shape/reference; retain node/event; expose only allowlisted `model route returned HTTP 4xx/5xx`, otherwise generic withheld detail | Supplied; legacy strings accepted but similarly redacted; raw logs never forwarded |
| photo | Optional/null; credit/license/caption/URL checks; preview withholds non-null photos until independently verified rights/source record; production rights confirmation still required | All samples null; no photo rights verified |

Preview `Source.id` is the original URL used only as a presentation key, **not** a collector source ID; ratings/audience remain null. Digest summary uses the supplied topic summary. Source/article/claim references retain original URLs and IDs without replacing them with fabricated provenance.

`preview.published` is always false, outer status always `demo`, even if input claims `fictional:false` or supplies published_at. `expiry_hint` distinguishes `expired` versus `within_hint` using the supplied timestamp; historical reruns may be generated after expiry and remain expired. It is not publication authorization. No timestamps, ratings, review metadata or corrections are inferred.

The parser is bounded (2 MiB/depth25, finite numbers, no duplicate keys), strict about IDs/references/URLs/claims/rubric/cohort pairs, and rejects unsupported fields. The UI escapes text and uses checked original links; no unsafe HTML rendering. The server does not fetch evidence URLs. Producers must still approve all public prose/trace; pattern rejection is not a guarantee that arbitrary text contains no confidential information.

API path **`GET /api/preview/reasoning/`** is separate from normal feed/store. It requires session + DEBUG + `QUORUM_ENABLE_REASONING_PREVIEW=1` + localhost + nonproduction DATA_DIR; file override `QUORUM_REASONING_PREVIEW_FILE`. Invalid/missing file returns generic 422 with no filename/content; missing requested edition/version returns 404; no silent sample fallback. Fixture hashes are file identities, not evidence hashes.

Preview commands and three-fixture acceptance: [verification](PORTAL_VERIFICATION.md#current-reproducible-checks). The production validator intentionally rejects all three files.

**Login-only reader for installed editions (2026-10-26).** Installed reasoning 1.0 editions reach signed-in readers through the normal `GET /api/feed/` and `GET /api/events/<id>/` when `QUORUM_ENABLE_REASONING_READER=1` and `QUORUM_REASONING_EDITIONS_ROOT` is set: `manage.py reasoning_snapshot … --install` copies an accepted file, its sidecar and an install record into `<root>/<topic>/<date>/v<N>.*` (versions immutable). The feed presents each edition with the preview's `present_reasoning`, so the labels, claim buckets and the `reasoning` block are the preview's; it adds one `editions` row per topic (completion, quiet day, summary, the preview's honesty labels `provisional` / `corpus_as_of_utc` / `edition_window_utc` / `warnings`, roundup lines without event links that keep the producer's `label`, `line_source` and `needs_review`) and a `publication` with revision `editions-<date>`, `mode` live or demo, `provisional` when any edition of the day is, `installed_at` beside `published_at`. On a release without `.git`, `reasoning_snapshot --producer-config <reasoning.toml>` hashes the producer's config from that file. The proposal store, `portal_snapshot` and the DEBUG preview are unchanged; anonymous visitors still see nothing. Decision and layout: `backend/portal/reasoning_editions.py`; log row in [DECISIONS.md](DECISIONS.md).

## Publication states, revisions and safe trace

| State | Meaning |
| --- | --- |
| AVAILABLE | Validated genuinely published production analysis; reasoning ok can map here only through the approved bridge |
| PARTIAL | Usable incomplete result with explicit gaps; reasoning partial/errors/sources_missing retain partial semantics |
| STALE | Retained analysis beyond supplied expiry; never current news. Preview exposes expiry separately from demo availability |
| PENDING | No completed published result; absent configuration/edition is never a quiet day |
| ERROR | Real retrieval/processing/validation failure; never convert to successful empty output |

Reasoning `empty` with completed `roundup.empty_day` is a quiet selection, not no run. Preview labels it a **fictional recorded completion**, never live publication. Normal feed continues honest pending/error/stale behavior. Explicit revision links must not silently load different results.

Reasoning versions are immutable reruns; the integrated file store assigns the next per-topic/day version and publication timestamp. Its document supersedes_id filtering is implemented, but a claim-level correction/retraction/alias record is not exported. Portal internal revisions/parents/corrections/rollback are already tested; no automatic conversion of reasoning version to portal revision is agreed. Reasoning event hashes include cluster document membership, so do not promise unchanged IDs after reclustering. Public trace must contain only reviewed node/iteration/event/decision/reason/model/duration fields: never prompts, private chain-of-thought, internal conversations, credentials or raw failure logs. No fabricated review times.

## Historical contract audit — retained, superseded by current gates below

This table records the old inspected pins, not new requests to the owners. IDs, quote bindings, catalog ratings and the canonical topic slug have since been integrated; do not repeat completed work from this historical inventory.

| Exact requirement | Actual supplied state | Responsible owner / next action |
| --- | --- | --- |
| Registry source ID + document_id OR official_doc_id on each evidence item; quote_id | Internal reasoning state has separate numeric doc IDs (official DocRef internally namespaced); current claim_view/sample export omits document IDs/source IDs/quote IDs | Yelysei export original collector references; Anastasia confirm registry joins, no fabricated URL IDs |
| content_hash formula/version, document version/supersedes_id, exact extraction reference, quote text hash if distinct, char_start/char_end, verified_at | Collector formulas/code-point/exclusive-end semantics confirmed; returned FetchedText metadata not fully carried into published evidence | Anastasia define reproducible version/hash binding; Yelysei retain/export quote verification records |
| achieved access_level/fetched_at, wire_origin, source independence_group | Collectors supply; independence groups present in sample; original document access/wire/retrieval metadata absent in snapshot | Both upstream owners preserve document-level provenance; level2/3 restrictions in real evidence |
| review actor, decision, reason, reviewed_at, independent-review linkage | Verdicts/reasons/found_by supplied; no per-review actor IDs or timestamps | Yelysei export public-safe review records; no synthetic timestamps |
| corpus/model run evidence, query/run provenance, fetcher identity | Corpus SQL now QUORUM_COLLECT; preferred extractor now delegates common.fetch_text; fallback independent extractor still exists; CLI model/corpus axes separate; envelope declarations supplied | Yelysei/Anastasia provide actual authorized returned rows/model route evidence and prove shared extractor used; no fallback as publication-grade quote proof |
| topic/edition policy | New metadata/DST local window supplied; collector ukraine-aid versus reasoning russia-ukraine-war unresolved at inspected pins | All owners confirm one registry ID and migration/alias for existing preferences, no silent renaming |
| event/claim continuity, merged/retracted identities, revision parent/corrections | Hash IDs/version supplied; collector supersession recognized; no cross-version correction envelope | Yelysei + Vadim agree explicit semantics and provide two genuine revisions/correction example |
| source rating/audience provenance, eligible cohort registry, missing-source failures | Fixture cohort pairs/outlets supplied; original ratings/audience null; sources_missing runtime still initialized empty | Anastasia/Yelysei supply actual eligible set/provenance and failures rather than interpreting empty list as perfect health |
| generated/published/expires, time zone/window | **Now supplied**; published_at null until a store publishes. UTC validation/expiry display tested | No longer a missing-envelope blocker; production bridge must verify actual publication and retain expiry |
| transport, scoped auth, bridge, retention, preference scheduling | Proposed only; no endpoint/service credential or production bridge operational | All three approve before Vadim activates anything |

### Historical transport proposal — endpoint deferred

Historical transport proposal, superseded for the hackathon by the private immutable file + full SHA-256 + producer-commit handover agreed in DECISIONS.md (2026-10-24): bearer-protected GET `/snapshots/{topic_id}/{edition_date}` and `/latest` over an SSH tunnel bound to loopback, cached by version. The portal's earlier staged SSH/SFTP plus local publisher is also historical. Any future production bridge still requires agreement on size/time limits, replay/version/freshness/error policy, secret rotation and narrow OS access. Never expose PostgreSQL or unauthenticated ingestion, reuse user passwords, write Django auth data or allow upload identities to alter head/code/private config. Vadim alone handles approved portal deployment. No machine credentials or transport are created by this milestone.

### Minimal real end-to-end acceptance

Anastasia supplies one permitted actual article and official document via authenticated Zetaris with original IDs/versions/quotes/access/wire provenance. Yelysei supplies one genuine Meterless/Nemotron run over that corpus with independent review, public trace, partial/failure behavior and a corrected second revision. Declare model/corpus separately; live inference over fixture data remains fictional, stand-ins over Zetaris remain dry. Vadim first validates/maps locally, checks authenticated Django/API/TypeScript/UI across article/evidence/cohorts/timeline/history, tests bad references/access2/3/duplicates/missing ratings/expiry/outage/rollback, then records actual evidence in Issue #2. Fixture suite establishes compatibility only. Production stays disabled until approval and release gates pass.

## Read-only compatibility command

For the **internal portal proposal**, run:

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py portal_snapshot validate --file /path/to/candidate.json
```

This uses existing production validation/projection, no publisher/auth writes/inference. JSON report contains `report_version`, `compatible`, `target_schema`, `published:false`, `issues` (safe code/path/schema_path/hint, no candidate values), `warnings` and successful `counts`; success exit0, invalid nonzero. Exact report examples/tests: `backend/portal/management/commands/portal_snapshot.py`, `backend/portal/test_snapshots.py` and `snapshot_compatibility.py`. It does **not** accept raw reasoning 1.0. Validate that consumer via `parse_reasoning`/`load_preview` and the local real-HTTP workflow; never mislabel a successful preview as publication-grade validation.

## Files to read before integration

**All agents:** latest master AGENTS.md + DECISIONS.md, Issue #2, [Start Here/notification protocol](TEAM_HANDOFF.md), this guide, current verification/release checklist.

**Anastasia:** own collectors README/schema/common/run/sources/zetaris registration SQL; reasoning/quorum_reasoning/{tools/corpus.py,tools/fetch_text.py,nodes/publish.py}; web deploy/export-catalog.py, backend/portal/integration.py, web/lib/api.ts. No collector code on the website VPS.

**Yelysei:** own ARCHITECTURE §8/examples and reasoning/quorum_reasoning/{state.py,nodes/publish.py}; collector common.py/schema.sql; backend/portal/reasoning_preview.py, snapshot_validation.py, snapshot_projection.py, snapshot_store.py, integration.py; web/lib/reasoning.ts, api.ts, analysis.ts; canonical internal [snapshot proposal](SNAPSHOT_PROPOSAL.md).

**Vadim:** all above boundaries plus backend/README.md, web/README.md, deploy/README.md/STATUS.md, docs/PORTAL_VERIFICATION.md and RELEASE_CHECKLIST.md. [Notify affected owners](TEAM_HANDOFF.md#interface-change-notification-protocol) when portal acceptance/API/frontend dependencies change; no silent mandatory upstream requirements.

### Collected-corpus local experiment compatibility

The same gated, authenticated development preview accepts producer-declared `fictional: false` snapshots while keeping `published: false`. Its labels distinguish collected-corpus declarations, deterministic stand-ins and recorded model output; none grants publication authority. Current canonical 0224ca6 optional source/document identities, nullable quote offsets/hash/access/fetch bindings, third-review declarations, `summary_source`, `by_headline`, `line_source` and bounded extraction audit `detail` are retained. These are producer declarations; source text is absent, so this preview does not independently verify quote binding. See [backend decisions](../backend/README.md#decisions). A false headline-only flag does not prove successful body extraction. Real corpus stand-in browser acceptance proves the data path and presentation only; an aborted live graph has no snapshot to display.

## Daily-editions integration update — 2026-10-25

Canonical product decision: [Daily editions for users](DECISIONS.md#daily-editions-for-users-topics-delivery-time-where-runs-execute). This section records implementation boundaries, not another product decision.

- Collection PRs #12/#14/#15 are integrated. Active rows in the collection `topics` table are authoritative; seed insertion never overwrites them, retirement uses `active = false`, and rows are never deleted. Exact schema/term/order semantics remain in `collectors/README.md › Topics` and `collectors/schema.sql`.
- Current Django preferences select from the reviewed catalog export. They do not create collection topics, store a delivery time, or start processing. The portal auth database remains separate from collection data. A new topic-write bridge needs scoped authorization and an agreed transport; do not expose Postgres or put collection/model credentials on the public web host.
- Reasoning's `topic_terms` is an owner-machine function/CLI. Its suggestions need visible user curation; the public web application must not invoke a paid model or reasoning subprocess. PR #16 contains later topic normalization fixes and night reasoning rules, explicitly held for owner confirmation.
- The owner reports six live topics and a measured approximately 29-minute collection pass / 45-minute cycle. The 15-minute sleep is not a pickup guarantee. New-topic copy must disclose that the first full edition needs accumulated coverage; no deadline or completed edition may be promised merely from topic creation.
- Delivery time means local display time for an already-produced edition, not a processing trigger. Timezone storage, same-day/history behavior, and the safe topic-write bridge remain implementation/integration work; no scheduler or publisher was enabled by this update.
- Latest owner handoff is v6, superseding v5. Both original-file bundles and the separate v4 execution/impact attestation are absent from the inspected local handoff directories at this checkpoint. Their reported existence is not independent acceptance. Retain the original historical v4 publication hold until the separate evidence is available and reviewed.

Follow-up evidence and exact tests belong in Issue #2 and PORTAL_VERIFICATION.md.

### Current production gates

| Boundary | Current evidence / exact remaining dependency |
| --- | --- |
| Contract and catalog | Snapshot §8, canonical topic slug, source/document identity namespaces, quote offsets/hash/access fields and sourced four-mode registry are implemented and locally tested. Existing collection work is accepted; no duplicate export/collection task is requested. |
| New editions | The owner reports v6 as current. Original bytes, sidecar, separate attestation and D5 must be available locally before independent acceptance; no retrospective rewriting of historical files. |
| Public failure privacy | PR #9 implements the owner findings and regenerated examples; outstanding CHANGES_REQUESTED review must be rechecked before merge. |
| Reasoning night decisions | PR #16 has green offline tests but an explicit owner-confirmation hold. Route receipts do not resolve Nightshift prior-answer injection into blind verification. |
| Topic writes and delivery | Product semantics are decided; scoped topic-write transport, suggestion curation and local delivery-time implementation remain unbuilt. Current web preferences select an exported catalog only. |
| Production release | No public publisher/ingest is enabled. Approved bridge/auth, target-host security/restore/rollback and explicit release authorization remain necessary. A code checkpoint on master does not certify production or sponsor acceptance. |
