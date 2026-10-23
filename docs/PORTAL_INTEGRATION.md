# Portal integration handoff

Reviewed 2026-10-22 against the portal code and `origin/data-collection` at `46b0d00a962960891a320b18f41ed64cfd649119`. Fetch before comparing contracts; the pinned [collector schema](https://github.com/rcc00n/Quorum/blob/46b0d00a962960891a320b18f41ed64cfd649119/collectors/schema.sql) is authoritative for its tables. Collector files are not merged into this branch.

**Current state:** Django sessions/preferences and the portal work. `CatalogAdapter` can expose an operator-configured local export of topic/source definitions; production events and digests remain empty/pending. Production release `20261023-web-portals-09f5325` includes the tested, disabled-by-default `PublishedAdapter` with strict validation and rich presentation; see the [snapshot proposal](SNAPSHOT_PROPOSAL.md). This export is not a live Zetaris connection. No approved agent API, result transport, ingestion endpoint or operational processing integration exists. Fictional examples below are documentation/test data only.

## Shared architecture and ownership

```text
External processing infrastructure                         Website-only VPS
Collectors → Postgres registered in Zetaris ─┐
Official REST data registered in Zetaris ────┼→ Reasoning → [transport TBD]
                                            │                 ↓
                           Nemotron via Meterless       Django DataAdapter
                                                         ↓ GET /api/feed/
                                                    Same-origin Next.js UI

Django auth/preferences SQLite is separate from all collector/reasoning storage.
```

Data architecture, evidence principles and rating formulas remain in [DECISIONS.md](DECISIONS.md). Processing and inference stay outside the VPS; only Next.js, lightweight Django and portal SQLite belong there. Integration must retain genuine Zetaris data access and Meterless/Nemotron use. See [official requirements and evidence limits](RULES_CHECK.md).

### Existing web boundary

- `backend/portal/views.py:feed` handles authenticated `GET /api/feed/?date=2026-10-22&topic=topic-id`. Missing `date` uses the server's current date; missing `topic` becomes `""`. Invalid dates return JSON 400; no session returns JSON 401. Success is the snapshot object itself, with `Cache-Control: no-store`.
- It calls `backend/portal/integration.py:adapter.snapshot(day, topic)`. `DataAdapter` declares `snapshot(day: str = "", topic: str = "", revision: str | None = None) -> PortalSnapshot`; `PublishedAdapter` is the default and delegates to the catalog while no snapshot root is configured. The concrete `CatalogAdapter` defaults both arguments to `""`; preferences and staff views also call `snapshot()` without arguments. A replacement must support these catalog calls or deliberately update their callers.
- No user/tenant context is passed into the adapter. Topic preferences are stored by Django and used for UI filtering, not upstream scheduling. A cross-workstream topic-selection synchronization contract is still needed. Client-side topic filters are not authorization for private data.
- The web branch adds authenticated `GET /api/events/<event-id>/?date=YYYY-MM-DD&revision=<id>` and optional `revision` on feed. Event lookup without a date finds the latest indexed matching event; immutable revision links are supported. Absent events return an empty event list, not invented analysis. Invalid date/revision returns 400, unauthenticated access 401, writes 405. No polling/pagination or event ranking is implemented. These additions are shipped and HTTPS/authenticated pending responses verified; actual upstream results remain blocked.

### Sessions and CSRF

Browser requests stay on the website origin. Nginx routes `/` to Next.js, `/api/` and `/staff/` to Django; development rewrites serve the same purpose. GET `/api/session/` returns `{user, csrfToken}`. Send `X-CSRFToken` and session cookies for every POST, including login/register; login rotates the token. Session/CSRF cookies are HttpOnly and Secure in production. No JWT/localStorage mechanism is used. GET feed needs a session but no CSRF header. [Backend setup and endpoint inventory](../backend/README.md#web-api) remain canonical for auth operations.

Processing services must not impersonate a browser, reuse human admin credentials, write Django auth tables or bypass CSRF to publish results. Machine-to-machine authorization is a separate, undecided interface.

## Anastasia — data collection

Read these before integration:

1. `AGENTS.md`, `docs/DECISIONS.md` (Sources, Principles, Spectrum ratings), this handoff.
2. On `origin/data-collection`: `collectors/README.md`, `collectors/schema.sql`, `collectors/common.py`, `collectors/run.py`, `collectors/sources.csv`, `collectors/verify_collectors.py`, `collectors/zetaris/01_register_postgres.sql`, `collectors/zetaris/02_federal_register_rest.sql`.
3. On `feature/web-portals`: `deploy/export-catalog.py`, `backend/portal/integration.py`, `web/lib/api.ts`, `docs/SPONSOR_SETUP.md` and `deploy/README.md`.

Use `git show origin/data-collection:collectors/schema.sql` to inspect without switching/merging branches. Do not run schema/collector commands on the website VPS.

### Storage, publication and handoff

The SQL defines **six** existing tables; the collector README's introductory count of five omits `topics`. Collection owns their schemas. Do not recreate them as Django migrations or repurpose the portal database.

| Existing table | Ownership and handoff |
| --- | --- |
| `sources` | Registry loaded from `sources.csv`: IDs, names, domains, kind, tier, independence group, nullable normalized ratings/audience and audience provenance, feed/access metadata. |
| `topics` | IDs/names/query terms; `collectors/run.py:TOPICS` currently supplies definitions until topic synchronization is agreed. |
| `documents` | Collector-written publications: source/topic IDs, URL/canonical URL, title/lead/byline, UTC timestamps, language, access level, content hash, wire origin/version and superseded version ID. No stored article full text. |
| `official_docs` | Collector-written official documents: source/topic IDs, URL, document type/number, title, full text, signed/published/fetched timestamps and language. Official text does not automatically verify every external-world claim in it. |
| `quotes` | Collection-owned schema, reasoning-written rows. Exactly one document/official-document reference, reasoning claim ID, verbatim text, offsets, content hash and verification timestamp. |
| `coverage` | Schema belongs to collection; publication/event association requires reasoning's event IDs. Rows retain each publication. `counted_in_confirmation` distinguishes independent confirmation from wire reprints; agree the writer/coordinator with reasoning. |

The collector runtime upserts topics and publications into its Postgres. On authorized processing infrastructure, register that database in Zetaris using `collectors/zetaris/01_register_postgres.sql` and actual private connection values. The script proposes `QUORUM_COLLECT.public.documents`; its host/port are examples, not a verified endpoint or permission to expose Postgres. The official-bundle port may differ. Validate with real returned rows, not a query receipt.

`02_federal_register_rest.sql` proposes a live Federal Register REST table and cross-source SQL; option names must be checked against the installed bundle. It is not evidence that this connector has run. Preserve the bundle's default services and preflight/verification gates. Do not move them to the website VPS.

Give reasoning stable source/topic/document IDs, original URLs, versions/hashes and timestamps through the agreed Zetaris views. Reasoning clusters events, assigns event/claim IDs and produces conclusions; collection must not invent those fields. Repeated wire coverage counts for spread but not multiple independent confirmations. Honor access levels: full-text retrieval only when permitted; level 2 uses headline/lead; level 3 is coverage-only and cannot substantiate article analysis. Retain exact quote verification and original source references upstream.

### Portal-facing mapping

| Portal consumes today | Collector origin / limitation |
| --- | --- |
| `Topic.id`, `Topic.name` | `topics.id/name` (current catalog exporter reads `TOPICS` definitions). Query terms are not sent to the browser. |
| `Source.id/name/domain/audience/allsides/mbfc/adfontes` | Same registry fields. Current external catalog exports definitions, not live database rows or ingestion health. |
| Evidence link `{title, url}` | Future adapter must resolve original document/official-document/quote provenance from reasoning output. No direct document feed is currently rendered. |
| Events, importance, claims, coverage narratives, digests | Not provided by collector tables alone; require reasoning and adapter mapping. |

Use JSON `null` for missing ratings/audience, never zero or a guessed ideological position. Collection ratings are already normalized: do not normalize twice. Formulas/cohorts are canonical in DECISIONS.md. Audience must be a finite positive estimate if supplied; otherwise null. Preserve `audience_source_url`, rating attribution, estimate date where known, access levels, hashes and query/run provenance upstream through the optional source extensions below. The legacy catalog export still strips these fields; the proposed snapshot preserves them.

`deploy/export-catalog.py` is an optional read-only bridge: it reads a reviewed Git revision without executing collector code and writes definitions outside the repository. It carries the revision into `catalog_revision`. Deployment/setup commands live in [deploy/README.md](../deploy/README.md). This does not synchronize preferences or establish an operational integration. No direct writes to Django's auth/preferences/session database are permitted from collectors.

## Yelysei — reasoning

Read these before integration:

1. `AGENTS.md`, `docs/DECISIONS.md` (Principles, Selecting major news, Spectrum ratings), this handoff and `docs/RULES_CHECK.md`.
2. On `origin/data-collection`: `collectors/README.md`, `collectors/schema.sql`, `collectors/common.py`, `collectors/zetaris/01_register_postgres.sql`; coordinate retrieval/quote verification with Anastasia.
3. On `feature/web-portals`: `web/lib/api.ts`, `web/components/portal.tsx`, `backend/portal/integration.py`, `backend/portal/views.py`, `backend/portal/tests.py`, `agent/tools_zetaris.py`, `smoke_test.py`, `deploy/README.md`, `web/lib/analysis.ts`, `backend/portal/schemas/analysis-v1.schema.json`, `backend/portal/snapshot_validation.py`, `backend/portal/snapshot_store.py`, `backend/portal/snapshot_projection.py`, `backend/portal/test_snapshots.py` and `docs/SNAPSHOT_PROPOSAL.md`.
4. Inspect your current `origin/yelysei/agents` contracts before implementing a bridge; this document does not assert an existing reasoning service or output schema.

### Exact current TypeScript view model

`web/lib/api.ts` is the executable source of truth. The following inventory describes the **current portal**, not an approved agent API. Every field below is required unless explicitly optional; array elements must have all their required fields.

| Type | Exact fields |
| --- | --- |
| `User` | `username: string`, `name: string`, `email: string`, `topics: string[]`, `is_staff: boolean`; owned by Django, not reasoning output. |
| `Topic` | `id: string`, `name: string` |
| `Source` | `id: string`, `name: string`, `domain: string`, `audience: number \| null`, `allsides: number \| null`, `mbfc: number \| null`, `adfontes: number \| null` |
| `Evidence` | `text: string`, `explanation: string`, `sources: {title: string; url: string}[]` |
| `Event` | `id: string`, `topic_id: string`, `date: string`, `title: string`, `summary: string`, `importance: {label: string; explanation: string} \| null`, `established: Evidence[]`, `statements: Evidence[]`, `disputed: Evidence[]`, `unknown: Evidence[]`, `coverage: Evidence[]`, `sources: Source[]` |
| `Snapshot` | `status: string`, `topics: Topic[]`, `sources: Source[]`, `events: Event[]`, `digests: {date: string; topic_id: string; summary: string}[]`, optional `catalog_revision?: string \| null` |

Optional extensions: `Event.analysis?: StructuredAnalysis`; `Snapshot.publication?: Publication`, `errors?: {code: string; message: string; event_id: string | null}[]`; Source optionally carries `kind`, `tier`, `independence_group`, `audience_source_url`, `audience_as_of`, `rating_provenance`. Exact extension fields/unions are in [analysis.ts](../web/lib/analysis.ts) and [api.ts](../web/lib/api.ts); exact proposal envelope and a full JSON fixture are linked from [SNAPSHOT_PROPOSAL.md](SNAPSHOT_PROPOSAL.md). Legacy responses/examples remain supported.

The Python `PortalSnapshot` requires `catalog_revision` (nullable) and uses `list[dict]` for sources/events/digests; those loose annotations are not full validation. CatalogAdapter always includes the revision field. Proposed date convention: `YYYY-MM-DD` editions with an explicitly agreed timezone; do not silently derive a day from publication timestamps without agreement.

### How output is displayed

- Dashboard filters events by edition date and selected topic IDs. Topic pages filter by date/topic; both render the first ten returned matching events. Upstream ordering therefore controls prominence; there is no client-side importance calculation. `importance.label/explanation` are displayed when supplied; numeric importance/rubric fields are not modeled yet.
- Event detail renders `title/summary`, then `established` (“What is established”), `statements` (“Attributed statements”), `disputed`, `unknown`, and `coverage` (“Coverage differences”). Each entry displays `text`, then `explanation`, with source-title links. Empty arrays show “No information supplied,” not confirmation or a count of zero findings.
- Put attribution directly into statement text/explanation: identify who said what and when. Disputed entries should explain competing claims and link both sides; unknown entries explain the evidence gap. Established entries require actual supporting evidence under the agreed principles. A signed document establishes adoption/content; its assertions about the world remain attributed unless verified.
- Evidence URLs must point to original publications/documents, not an invented citation or provider receipt. The UI admits absolute HTTP(S) links only and uses safe external-link attributes. Prefer HTTPS. Retrieval services must additionally enforce outbound-host/SSRF policy; this browser check is not a server-side network safety boundary.
- `Event.sources` supplies the event spectrum; `Snapshot.sources` supplies the topic spectrum. Pass the intended, explicitly scoped source set; do not confuse the full registry with proven event coverage. Nullable ratings render as unrated. Audience scatter appears only with a rating, positive audience and provenance URL. No model-assigned ideological scores or guessed cohort denominators.
- History filters digests by edition and optional topic; elsewhere it filters by followed topics and displays the first digest as latest. Return ordering matters; newest-first and ranked-event ordering need upstream agreement.
- `status: "demo"` triggers a visible fictional-data banner; `"pending"` indicates the unconnected state. Errors receive “Data unavailable”; other supplied values retain the source-data label. The optional `publication` extension now displays pending/available/partial/stale/error and fallback metadata; upstream freshness/expiry policy still needs agreement. No status string establishes verification.

### JSON examples — shape checks only

An empty pending response (also valid when no catalog is configured):

```json
{
  "status": "pending",
  "catalog_revision": null,
  "topics": [],
  "sources": [],
  "events": [],
  "digests": []
}
```

Fictional demonstration of all display buckets, matching the current types. The placeholder URL is not evidence. Never load this as real published news or count it as an integration pass.

```json
{
  "status": "demo",
  "catalog_revision": null,
  "topics": [{"id": "demo-topic", "name": "DEMO — fictional topic"}],
  "sources": [{
    "id": "demo-source", "name": "DEMO — fictional source", "domain": "example.com",
    "audience": null, "allsides": null, "mbfc": null, "adfontes": null
  }],
  "events": [{
    "id": "demo-event", "topic_id": "demo-topic", "date": "2026-10-22",
    "title": "DEMO — fictional analysis layout", "summary": "Not a news report or verified finding.",
    "importance": null,
    "established": [{
      "text": "DEMO — an evidence-supported conclusion would appear here.",
      "explanation": "Illustrative structure only; no actual conclusion is asserted.",
      "sources": [{"title": "DEMO placeholder, not evidence", "url": "https://example.com/demo-document"}]
    }],
    "statements": [{
      "text": "DEMO — a named speaker's attributed statement.",
      "explanation": "Include the real speaker, context and original publication when integrated.",
      "sources": []
    }],
    "disputed": [{
      "text": "DEMO — conflicting claims.", "explanation": "Explain the contradiction and cite each original.", "sources": []
    }],
    "unknown": [{
      "text": "DEMO — an unresolved question.", "explanation": "Describe what evidence is missing.", "sources": []
    }],
    "coverage": [{
      "text": "DEMO — coverage comparison.", "explanation": "Real comparisons need publication examples and known cohort denominators.", "sources": []
    }],
    "sources": [{
      "id": "demo-source", "name": "DEMO — fictional source", "domain": "example.com",
      "audience": null, "allsides": null, "mbfc": null, "adfontes": null
    }]
  }],
  "digests": [{"date": "2026-10-22", "topic_id": "demo-topic", "summary": "DEMO — fictional daily digest."}]
}
```

`importance`, when present, must be an object with exactly the current required `label` and `explanation` strings. Do not invent an importance score just to populate it.

## Validation, secure transport and agreement points

### Existing checks versus required integration work

CatalogAdapter validates topic/source identifiers and types, finite normalized ratings, positive audience and a string catalog revision; it strips non-view-model registry fields. Unconfigured catalog returns pending; an explicitly configured but missing/unreadable/invalid catalog returns ERROR with a safe diagnostic. It does not validate full event/evidence/digest output because it never produces those records. TypeScript types are compile-time only: `feed()` trusts returned JSON at runtime.

**Implemented locally, still requiring upstream alignment:** the disabled snapshot path validates these structures; see [runtime limits and safety semantics](SNAPSHOT_PROPOSAL.md). The catalog path now preserves configured-access/validation failures as ERROR. **Required before live integration:** validate the entire upstream envelope server-side, enforce size/time limits, unique stable IDs, existing topic/source references, edition dates, all required arrays/nulls and safe URLs. Preserve attribution, raw provenance and version relationships without leaking credentials. Decide whether malformed records reject an edition or yield an explicitly partial result. Network failures/non-2xx show the portal's retry/error state; empty editions and absent analyses have empty states. A live adapter must not silently convert an outage into a successful empty edition or fall back to fictional fixtures.

### Transport proposal — not implemented or approved

Prefer a narrowly scoped read-only adapter on the VPS pulling published results over authenticated HTTPS from authorized remote infrastructure, with a private network/tunnel where appropriate. Keep processing databases and Zetaris private. Do not expose database ports or unauthenticated ingest routes. If an SSH tunnel is chosen, use a dedicated restricted key, verified host keys and loopback binding; do not change global SSH/firewall configuration. No credential belongs in the browser, Git, logs or other projects' environments.

Team approval must settle the actual endpoint, least-privilege credentials, network path, TLS identity, bounded queries/timeouts and secret rotation. The local atomic snapshot validator/store is now implemented and tested; the restricted uploader and cross-team authorization are not. The preferred restricted SSH/SFTP staging design and the remaining pull alternative are specified in [SNAPSHOT_PROPOSAL.md](SNAPSHOT_PROPOSAL.md). The catalog exporter is not a reasoning-result channel. No processing service receives direct write access to `/var/lib/quorum` auth data. Deploy only the adapter/website changes with a restricted backup and the existing isolated [deployment procedure](../deploy/README.md); no AI inference, collectors or Zetaris workloads may run on the VPS.

### Still undecided — agree before coding the live bridge

1. Reasoning-owned output schema/version and transport; Zetaris views versus published reasoning snapshots. Portal types remain a presentation target, never an already-approved agent API.
2. Stable event/claim IDs, event corrections/merges, result revisions, quote offsets/hashes and reasoning trace references. Legacy Evidence cannot encode these; the optional structured proposal can, pending upstream agreement.
3. Publication access levels (“by headline”/coverage-only), verification timestamps, raw rating/audience provenance, independent confirmation versus spread, and cohort denominators. The optional proposal models these; legacy fields alone remain insufficient.
4. Edition timezone, ranking/importance rubric, topic/event source scope, digest order and retention/history completeness. The first-ten UI rule is not an upstream ranking implementation.
5. Topic preference synchronization into the collector schedule, shared-catalog ownership and private/tenant authorization if needed.
6. Status/freshness/partial/outage semantics and admin telemetry. No fabricated health/ingestion status may fill these gaps.

## Minimal real end-to-end acceptance

Run on authorized processing infrastructure and the isolated website; never infer success from mocks, prepared SQL or the catalog snapshot.

1. Collect a real permitted publication/official document. Record its source/topic/document IDs, URL, timestamp, access level and version/hash; prove the stored row exists without printing credentials.
2. Query that row through authenticated Zetaris and verify returned values. Where claiming federation, execute the actual second connector/cross-source query too. Keep schema/DDL unchanged unless its owner explicitly approves.
3. Explicitly opt in to an authorized Meterless/Nemotron request. Produce one traceable real event with the agreed reasoning output, source links and evidence checks; investigate contradictions rather than manufacturing an established result. Record the actual model/route and outcome, with secrets redacted. Routine checks never spend inference credits.
4. Through the approved transport and adapter, request an authenticated `/api/feed/` edition and compare original IDs, summaries, ordering, evidence URLs, null ratings and digest with the upstream result. Unauthenticated access must remain 401; CSRF-invalid preference/login mutations must remain forbidden.
5. Verify selected-topic/date history, event deep links and four spectrum modes in the browser, including unrated sources, unavailable audience, empty/unknown/disputed sections and responsive layouts. Separate actual observations from fictional UI tests.
6. Test invalid payloads, upstream timeout/auth failure, stale/partial behavior and unauthorized machine access. No secret leakage, fallback news, changed collector schemas or auth-database writes. Keep a concise redacted run record tied to data/code revisions and the [official rules evidence](RULES_CHECK.md).

Local regression commands (not live integration evidence):

```bash
python3 -m unittest discover -s scripts -p 'test_checks.py'
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py test portal
node web/tests/ratings.cjs
./scripts/doctor.sh
./scripts/verify-all.sh  # no inference; real missing credentials remain BLOCKED
```

## Compatibility review — integration-readiness milestone

Read-only review on 2026-10-23 UTC: `origin/data-collection@09890a0` and `origin/yelysei/agents@49e6d1f`. Collector runtime/source mix has advanced; schema ownership is unchanged. The reasoning branch still has no concrete structured result JSON, event/claim generator, verification output or correction/trace API. No real candidate was available to validate. Collector README reports local Postgres/mock-feed checks; that is not evidence of genuine Zetaris or Nemotron execution. Production catalog remains the previously reviewed `46b0d00` export; this review does not silently replace it.

| Upstream field / available structure | Portal proposal field | Status | Required transformation | Missing information | Owner |
| --- | --- | --- | --- | --- | --- |
| `topics.id/name`, `run.py:TOPICS` | `topics[].id/name`, `event.topic_id` | Available definitions | Preserve IDs; export reviewed registry | Preference→schedule sync | Anastasia + Vadim |
| `sources.id/name/domain/kind/tier/independence_group` | Same named source fields | Available schema | Preserve registry IDs; null tier for unclassified sources | Run-level registry revision | Anastasia |
| Normalized `allsides/mbfc/adfontes`, nullable audience + `audience_source_url` | Same fields + `rating_provenance`, `audience_as_of` | Partial | Preserve nulls; do not normalize twice; keep ratings/audience null until required provenance is supplied | Per-rating URLs and audience estimate date absent from SQL | Anastasia |
| `documents.id` BIGSERIAL / `official_docs.id` BIGSERIAL | `analysis.documents[].id` string | Needs mapping | **Proposal:** prefix table namespace (`document:` / `official:`) to avoid numeric ID collisions; agree before use | Global identity/export convention | Anastasia + Yelysei |
| `documents.url/canonical_url/title/source_id/published_at/fetched_at/access_level` | Document `url/title/source_id/published_at/fetched_at/access_level` | Available schema | Original publisher URL, UTC `Z`; preserve level 2 headline/lead and level 3 coverage-only | Which original/canonical URL is authoritative | Anastasia |
| `documents.content_hash/supersedes_id` | Document `content_hash/revision` | Partial | Preserve hash; agree version identifier from immutable collector row | `content_hash` is SHA-256 of title + newline + lead + newline + first 2000 body characters at fetch; not full article hash | Anastasia |
| `official_docs.full_text`, no hash column | Official document hash + `primary` | Needs agreement | Derive/export a documented exact text hash without altering collector schema; authority/primary status must be justified | Canonical encoding/normalization and primary flag | Anastasia + Yelysei |
| `quotes.claim_id/quote_text/char_start/char_end/content_hash_at_quote/verified_at` | Claim ID; citation quote/offsets/hash | Schema only | Preserve exact text and hash; resolve exactly one document/official reference | Actual rows; Unicode code points vs bytes/UTF-16, exact hashed text, verified timestamp export | Yelysei + Anastasia |
| `coverage.event_id/source_id/document_id/counted_in_confirmation`, `wire_origin` | Event IDs, covered sources, publication count, independent count | Schema only | Preserve publications for spread; deduplicate actual independence, including wire origin | Actual event assignments, eligible source set and grouping rule per run | Yelysei + Anastasia |
| No concrete reasoning JSON | `events[].id`, `analysis.claims[].id/status/attribution/supporting/contradicting` | BLOCKED | Map the reasoning-owned output after agreement | One real structured result with stable IDs and original evidence | Yelysei |
| No verifier/trace/correction output | Primary/independent verification, disagreement, trace, corrections | BLOCKED | Public-safe summaries only; immutable prior revision references | Reviewer independence, outcome meanings, trace actors and correction semantics | Yelysei |
| No published edition envelope/digest | Edition/run/revision/generated/expiry/completeness/errors/digests | BLOCKED | Agree timezone/order/expiry; no inferred operational health | Actual envelope, source revision and partial/failure policy | Yelysei + Vadim |

**Exact sample requested:** one real event with stable event/claim/topic/source/document IDs, original URLs, collector hashes/versions/access/times, at least one attributed claim, established/disputed/unknown outcomes where genuinely supported, primary and independent review summaries, explicit null ratings/audience, public-safe trace, edition/run/generated/expiry/source revision, completeness/errors and digest ordering. Include a second immutable revision referencing a genuinely corrected/retracted prior claim, or explicitly state that no correction exists. Do not manufacture disputed findings to fill the example. Supply the reasoning-owned schema/version alongside it; the portal proposal is only a compatibility target.

### Read-only compatibility command

```bash
DJANGO_DEBUG=1 ~/.local/share/quorum/portal-venv/bin/python backend/manage.py portal_snapshot validate --file /path/to/candidate.json
```

Exit 0 means structurally compatible and serializable through the portal projection; exit 1 means incompatible/unreadable. JSON stdout is `quorum.portal.compatibility.v1`, with `compatible`, `target_schema`, `published:false`, bounded `issues` and `warnings`, plus collection counts on success. Example diagnostic:

```json
{"report_version":"quorum.portal.compatibility.v1","compatible":false,"target_schema":"quorum.portal.snapshot.v1-proposal","published":false,"issues":[{"code":"schema_format","path":"/edition","schema_path":"/properties/edition/format","hint":"Use the declared date, UTC timestamp, revision/domain or public HTTP(S) URL format."}],"warnings":[]}
```

Schema errors locate safe JSON pointers and schema keywords; semantic errors give stable invariant codes and corrective hints. No candidate values, unknown property names, original text or secrets are echoed. At most 20 shape issues are returned per run. Fix shape errors before semantic validation. No active head/audit/auth mutation, publication flag, model call or snapshot root is needed. Expired compatible candidates are explicitly warned as not publishable as current; correction history requires the actual private store at publication. This does not prove truth, authorized delivery, upstream schema ownership or full privacy review. See [proposal](SNAPSHOT_PROPOSAL.md) and [checks](PORTAL_VERIFICATION.md).

### Product compatibility options — team approval required

The reasoning branch proposes an absolute impact bar (initially 6/9 with confirmation ≥1), a maximum of ten rather than a target, quiet-day explanations, article prose with spectrum/evidence appendices, licensed photos/credits and an “Also today” roundup. These changes are not merged/adopted here. Existing event ordering and `importance.label/explanation` can display an upstream-approved rubric without calculating it in the portal. A future short article can keep stable event URLs and link to the existing Evidence Explorer; structured paragraphs and licensed image metadata would need agreed extensions. A roundup could use a new explicit view model, rather than pretending the existing digest summary already expresses ranked below-threshold events. Agree threshold/calibration, quiet-day vs missing-data semantics, article source references, image licenses and roundup shape before implementation. Preserve current editorial palette/auth ownership; reconcile branch decisions in the canonical decision log through the team process.

## Concurrent reasoning contract update — reviewed before final handoff

During release verification, reasoning advanced to `f3a32ec` and PR #3 was merged into master `c3cc5ac`. Read-only review of `docs/ARCHITECTURE.md` section 8 now provides a **documented proposed JSON shape**, not an executed result or running endpoint. This supersedes the earlier review's absence of a written output example; no genuine sample/result exists yet. The illustrative JSON was extracted outside Git and checked with the new read-only tool: it is incompatible with the portal proposal (expected version/required-field/extra-field diagnostics), and was not published. Placeholder URLs/values are not real evidence.

| Upstream documented field | Portal field | Status | Required transformation / missing information | Owner |
| --- | --- | --- | --- | --- |
| `schema_version: "1.0"`, `topic_id`, `edition_date`, integer `version` | Portal schema constant, topics, edition, revision/parent_revision | Different proposals | Agree explicit versioned mapper; topic+edition+version namespace and parent rules. Store heads currently key by edition, while upstream publishes per topic: agree aggregation or per-topic indexing before live writes. | Yelysei + Vadim |
| `stories[].event_id/headline/standfirst/rank` | Event id/title/summary, array ordering | Mappable after agreement | Preserve IDs/order; IDs hash topic/day/document cluster, so cluster changes require merge/alias/correction behavior. | Yelysei |
| `claims[].id/status/verifier/fact_checker/reason` | Claim status, two structured verification records, disagreement/attribution | Partial | `confirmed→established` only with full evidence/invariants; `unverified→unknown` is a proposed mapping. Flat verdicts omit checked_at, actors and separate review summaries. Statements need explicit speaker/context. | Yelysei |
| Evidence stance/quote/url/independence_group/quote_id | Supporting/contradicting document citations | Missing metadata | Resolve quote/document IDs, original source IDs, hashes, access, timestamps and Unicode offsets; do not substitute quote_id for a document hash. | Yelysei + Anastasia |
| Article fact/context/statements/not_confirmed blocks | Legacy evidence buckets; optional future prose | Needs semantic review | **Never automatically promote context blocks to established facts.** Resolve each block's claim IDs/status and attribution; disputed and unknown must remain distinct. | Yelysei + Vadim |
| `spectrum.left/right`, cohort counts, interpretation labels | Per-source frames and covered/eligible IDs | Insufficient source scope | Cohort summaries cannot silently become individual outlet frames. Need actual source membership, original document examples and denominator/independence provenance. | Yelysei + Anastasia |
| `trace_ref` | Structured public-safe trace events | Missing export | Agree authenticated trace resolution and public-safe timestamps/action/actor/evidence/outcome; raw run_steps inputs/prompts cannot be exposed. | Yelysei |
| `status: ok/partial/empty`, sources_missing | Publication AVAILABLE/PARTIAL/STALE/PENDING/ERROR | Needs explicit mapping | A completed quiet day (`empty`) is not missing processing (`PENDING`). Missing generated/expiry/published/source revision fields prevent freshness mapping. Failed pulls stay ERROR. | Yelysei + Vadim |
| Summary, bar/rubric, roundup, photo, needs_review | Digest/importance; future article/roundup/media models | Extensions needed | Preserve review flags; require license/credit/source verification. Agree below-bar ordering and approved UI changes; do not discard new fields silently. | Team |
| No correction envelope | Prior/replacement claims and immutable corrections | BLOCKED | Supply a second real revision or explicit no-correction result; define replacement/deletion/cluster changes. | Yelysei |

Reasoning now proposes bearer-protected snapshot GET endpoints through a loopback SSH tunnel, with version caching. They are documented **proposals, not operational or jointly authorized transport**. No endpoint was called, token created, tunnel configured or publishing enabled. Compare this pull option with staging/SFTP before team approval.

Master now contains the impact-bar/article/roundup amendments, while this isolated web branch retains its prior decision history. No new product behavior was implemented to choose between them. A reviewed reconciliation must happen on the web branch under team-approved scope. **PR #1 currently conflicts with the concurrently updated master.** This session did not merge/rebase/cherry-pick master or any teammate branch; resolving that history is outside the user's strict branch-isolation authorization. The verified production code remains `09f5325`.
