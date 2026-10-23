# Portal snapshot proposal — not an approved reasoning API

Owner: Vadim, `feature/web-portals`. Yelysei owns reasoning output; Anastasia owns collection/provenance. This is a tested portal implementation and negotiation target, **not an operational processing integration**. The code is shipped in production release `20261023-web-portals-09f5325`, with snapshot root unset and publication disabled. Production publication remains disabled. Track agreement and evidence in [Issue #2](https://github.com/rcc00n/Quorum/issues/2).

## Executable specification

- [JSON Schema](../backend/portal/schemas/analysis-v1.schema.json): `quorum.portal.snapshot.v1-proposal`, strict objects and bounded arrays/strings; all declared properties required, explicit nullable values where permitted.
- [Runtime validator](../backend/portal/snapshot_validation.py): UTF-8 JSON, maximum 2 MiB, maximum depth 25, no duplicate keys/non-finite numbers; exact ISO edition dates and UTC `Z` timestamps; unique IDs and resolved references.
- [Presentation types](../web/lib/analysis.ts) and [projection](../backend/portal/snapshot_projection.py): optional extensions to the existing [portal model](../web/lib/api.ts), not a demand that reasoning adopt these names.
- [Fictional example](../backend/portal/fixtures/analysis-demo.json): complete shape including established/attributed/disputed/unknown claims, supporting/contradicting references, access restrictions, framing and traces. All data is DEMO, ratings/audience are null. Never publish it as live news.

The envelope identifies edition, revision/parent, run, source revision, generated/expiry times, live/demo mode, completeness and explicit processing errors. It carries topic/source definitions, events and digests. Event analysis carries original documents, claims, framing, coverage, public-safe trace and corrections. The schema is canonical for exact fields and bounds; do not copy it into another specification.

Documents preserve original URL, SHA-256, version, source/publication/fetch timestamps, access level and official/primary status. Citation offsets are proposed **Unicode code-point offsets**, end-exclusive, into the exact text represented by `content_hash_at_quote`; agree this with collector quote storage before integration. The portal does not receive article text and cannot independently check quotations/hashes. Level 3 is coverage-only and cannot support evidence or framing. Level 2 remains explicitly headline/lead only. A collector hash and a quote-text hash may refer to different upstream representations; never silently equate them.

Claim status is explicit. Attributed claims require a named speaker. Established claims require supporting evidence, both supplied verifiers confirmed, no unresolved disagreement/contradicting evidence, and primary official support or at least two distinct supplied independence groups. This is structural validation, **not verification of truth**, signer authority or reviewer independence. Official claims about the world remain attributed unless actually verified. Missing evidence is not falsehood. Unknown/null stays unknown; no numerical model confidence is fabricated.

Source ratings are normalized once upstream; non-null ratings require provider provenance, audience requires provenance URL and estimate date. Covered/eligible sources, publications and independent confirmations are separate. Unknown eligible set is null; silence/share cannot then be inferred. Verification times, trace evidence references and correction/replacement references are checked. Corrections must refer to a stored previous revision and a real prior claim for that event.

## Local-only publication

Implemented commands are operator CLI only; there is no HTTP upload endpoint. They do not enable transport or create credentials. After approval, use an isolated OS-owned snapshot directory outside both auth data and the repository. The following demonstrates **local development only**, never production authorization:

```bash
export DJANGO_DEBUG=1
export QUORUM_SNAPSHOT_ROOT="$HOME/.local/share/quorum/snapshot-review"
export QUORUM_ENABLE_SNAPSHOT_PUBLICATION=1
PY="$HOME/.local/share/quorum/portal-venv/bin/python"
"$PY" backend/manage.py portal_snapshot prepare
# Place a reviewed, correctly dated candidate directly in $QUORUM_SNAPSHOT_ROOT/staging/.
# Compute sha256sum privately, then:
"$PY" backend/manage.py portal_snapshot publish --file "$QUORUM_SNAPSHOT_ROOT/staging/candidate.json" --sha256 <actual-sha256>
"$PY" backend/manage.py portal_snapshot status
"$PY" backend/manage.py portal_snapshot rollback --revision <intact-revision>
```

DEMO publication additionally requires DEBUG and explicit `--allow-demo`; production refuses DEMO even if requested. The supplied fixture has fixed dates; expiry rejection is intentional, not a reason to bypass checks.

Storage uses private 700 directories/600 files, regular bounded no-symlink reads, a publication lock, digest checks, immutable revision identifiers, parent compare, fsynced atomic head replacement and previous-head fallback. Re-publishing identical current bytes is idempotent; different content requires a new revision. Explicit unavailable revision links fail honestly rather than substitute another analysis. At most 366 edition heads are indexed; retention/archive policy still needs agreement. Audit records contain safe operation codes, not rejected payloads. Control counts rejection records only in the most recent 64 KiB audit window; this is not an all-time total or upstream service health.

Readers show pending/available/partial/stale/error, original publication metadata and fallback indication. Missing configuration stays catalog-only/pending. The immutable revision permalink remains readable after newer editions; a corrupt current index/revision can use a validated previous head. Older stored revisions can be rolled back even when expired, but remain visibly stale. Keep copies/backups outside auth data; do not delete stored history needed by corrections.

Validation blocks common credential patterns but cannot guarantee arbitrary prose is public-safe. The processing owner must explicitly export reviewed public summaries, never prompts, private chain-of-thought, credentials or raw operational logs. Browser URLs are not server fetch instructions; DNS/redirect/SSRF controls remain the responsibility of any upstream retrieval service.

## Transport and authorization — proposal only

Prefer dedicated SSH/SFTP from authorized processing infrastructure to **staging only**, with host-key verification and a dedicated restricted no-shell identity. A separate local publisher validates and commits heads. The uploader must have no auth DB, service environment, application code, revision-store or head-write permission. Read access for Django can use a separately reviewed OS group arrangement; the current private single-owner local implementation does not provision that multi-user policy. Agree forced command/chroot/path restrictions, key rotation, size/quota limits, replay handling, publisher invocation and audit retention before enabling it. No machine keys, users, global SSH changes or production publisher were created here.

No exposed databases, public unauthenticated ingestion, browser/provider credentials or processing workloads on the website VPS. A pull-over-authenticated-HTTPS adapter remains an alternative requiring the same team approval, strict time/size limits and validation.

## Agreement required

Yelysei: upstream schema, ID lifetime/merges, independent reviewer evidence, safe trace and correction semantics. Anastasia: original/quote hashes and offsets, access levels, independence groups, rating/audience provenance and Zetaris views. All: schema/version negotiation, edition timezone/ranking/expiry, transport permissions, retention, topic preference synchronization and a real end-to-end sample. Reconcile the newer reasoning-branch product decisions (`49e6d1f`: impact bar, maximum ten, article/roundup presentation) with canonical master before changing product behavior. No other owner's decisions were merged or overwritten.
