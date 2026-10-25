"""Reasoning 1.0 presentation adapter. Unpublished development only; never calls the publisher."""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from urllib.parse import urlsplit
from .snapshot_validation import (
    MAX_BYTES,
    SnapshotError,
    require,
    bounded_structure,
    edition_date,
    public_url,
)
from .snapshot_store import read_bounded

SAMPLE = Path(__file__).parent / "fixtures/reasoning-demo/snapshot.sample.json"
HISTORICAL_V3_SHA256 = "c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30"
GENUINE_V4_SIDECAR_SHA256 = "f55c3304afd92b9f763ddb04357f3ec0c7a8860e9ee3ddcf63b69a4bcff7c6d0"
GENUINE_V4_SHA256 = "ef231a4f0797c1128869ed5bd69d4d2869771766f634e754aa02dbf375756d79"


def artifact_review_issues(sha256, run_id=None):
    # DECISION(2026-10-25, rcc00n/Codex): retain an editorial hold for the original v4 hash or its known run identity.
    # Why: conditional/reversible rationale conflicts with irreversibility 1; do not rescore producer output.
    return ["impact_score_review_required"] if sha256 == GENUINE_V4_SHA256 or run_id == "2026-10-24-russia-ukraine-war-5" else []


def artifact_review_notices(sha256, run_id=None):
    if not artifact_review_issues(sha256, run_id):
        return []
    return [
        "IMPACT REVIEW PENDING: producer score 6 is preserved. The owner reports a conditional and "
        "reversible irreversibility rationale; assigning 0 instead of 1 would yield 5, below the story "
        "threshold of 6. This story has not passed independent impact review. Publication is blocked.",
        "Ledger scope: the owner reports 1674 recorded calls include replayed and unused rows from "
        "earlier attempts, including 6 errors. These are not current-attempt spending or failure totals. "
        "Original execution receipts and the D5 source-verification report require separate acceptance.",
    ]


SAMPLE_REVISION = "6ea82434d0f06cefb51f5536732ceac68e9780ef"
MISSING = [
    "original document/source IDs",
    "collector content hashes and document versions",
    "Unicode quote offsets and verified quote hashes",
    "achieved access levels and retrieval timestamps",
    "review actor IDs and timestamps",
    "correction history",
]


def fail(ok, code="invalid_reasoning_1_0"):
    require(ok, code)


def text(value, nullable=False):
    fail((nullable and value is None) or isinstance(value, str) and len(value) <= 20000)


def rows(value, limit=500):
    fail(isinstance(value, list) and len(value) <= limit)
    return value


def obj(value, required, optional=()):
    fail(isinstance(value, dict))
    fail(set(required) <= value.keys(), "missing_reasoning_field")
    fail(value.keys() <= set(required) | set(optional), "unsupported_reasoning_field")


def quote_binding(e):
    # DECISION(2026-10-23, rcc00n/Codex): validate optional owner 0224ca6 quote bindings
    # as declarations only. Why: source text is absent, so offsets cannot be independently verified here.
    if "source_id" in e and e["source_id"] is not None:
        identifier(e["source_id"])
    if "document_id" in e or "official_doc_id" in e:
        fail("document_id" in e and "official_doc_id" in e)
        ids = [e["document_id"], e["official_doc_id"]]
        fail(sum(v is not None for v in ids) == 1)
        fail(all(v is None or type(v) is int and v > 0 for v in ids))
    if "char_start" in e or "char_end" in e:
        fail("char_start" in e and "char_end" in e)
        a, b = e["char_start"], e["char_end"]
        fail(a is None and b is None or type(a) is int and type(b) is int and 0 <= a < b and b - a == len(e["quote"]))
    if "content_hash_at_quote" in e:
        value = e["content_hash_at_quote"]
        fail(value is None or isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    if "access_achieved" in e:
        value = e["access_achieved"]
        fail(value is None or type(value) is int and value in (1, 2))
    if e.get("fetched_at") is not None:
        timestamp(e["fetched_at"])
    for key in ("hash_mismatch", "from_previous_day"):
        if key in e:
            fail(type(e[key]) is bool or key == "hash_mismatch" and e[key] is None)


def identifier(value):
    fail(
        isinstance(value, str)
        and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", value)),
        "invalid_reasoning_id",
    )


def source(value):
    obj(value, ["title", "url"], ["quote", "quote_id"])
    text(value["title"])
    fail(public_url(value["url"]), "unsafe_reasoning_url")
    if "quote" in value:
        text(value["quote"], True)
    if "quote_id" in value:
        fail(type(value["quote_id"]) in (str, int) or value["quote_id"] is None)


def timestamp(value):
    fail(
        isinstance(value, str)
        and bool(
            re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+]00:00)",
                value,
            )
        ),
        "invalid_reasoning_timestamp",
    )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SnapshotError("invalid_reasoning_timestamp") from None


def envelope(p, *, raw_sha256=None):
    generated = timestamp(p["generated_at"])
    expires = timestamp(p["expires_at"])
    published = p["published_at"]
    if published is not None:
        fail(timestamp(published) >= generated, "publication_before_generation")
    text(p["edition_timezone"])
    try:
        zone = ZoneInfo(p["edition_timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise SnapshotError("invalid_edition_timezone") from None
    obj(p["window"], ["start", "end"])
    start, end = (timestamp(p["window"][key]) for key in ("start", "end"))
    day = datetime.strptime(p["edition_date"], "%Y-%m-%d").date()
    # Local calendar boundaries: DST editions are 23/25 hours, not always 24.
    expected_end = datetime.combine(day, time(5, 30), zone)
    try:
        expected_start = datetime.combine(day - timedelta(days=1), time(5, 30), zone)
    except OverflowError:
        raise SnapshotError("invalid_reasoning_date") from None
    fail(start == expected_start and end == expected_end, "inconsistent_edition_window")
    fail(expires > end, "expiry_before_edition_end")
    # Historical reruns may be generated after expiry. Never manufacture freshness.
    obj(
        p["provenance"],
        ["corpus", "model", "fictional"],
        ["fact_checker_model", "model_calls", "answered_by", "model_errors"],
    )
    for key in ("corpus", "model"):
        text(p["provenance"][key])
        fail(bool(p["provenance"][key]), "missing_reasoning_provenance")
    fail(type(p["provenance"]["fictional"]) is bool)
    provenance = p["provenance"]
    if "fact_checker_model" in provenance:
        text(provenance["fact_checker_model"])
        fail(bool(provenance["fact_checker_model"]), "missing_reasoning_provenance")
    for key in ("model_calls", "model_errors"):
        if key in provenance:
            fail(
                type(provenance[key]) is int and 0 <= provenance[key] <= 100000,
                "invalid_model_call_count",
            )
    if "answered_by" in provenance:
        answered = provenance["answered_by"]
        fail(isinstance(answered, dict) and len(answered) <= 100, "invalid_answered_by")
        for model, count in answered.items():
            text(model)
            fail(
                bool(model) and type(count) is int and 0 < count <= 100000,
                "invalid_answered_by",
            )
        if "model_calls" in provenance:
            fail(
                sum(answered.values()) == provenance["model_calls"],
                "inconsistent_model_call_count",
            )
        if "model_errors" in provenance:
            fail(
                answered.get("error", 0) == provenance["model_errors"]
                or (raw_sha256 == HISTORICAL_V3_SHA256
                    and answered.get("error") == 61 and provenance["model_errors"] == 63),
                "inconsistent_model_error_count",
            )
    if "model_calls" in provenance and "model_errors" in provenance:
        fail(
            provenance["model_errors"] <= provenance["model_calls"],
            "inconsistent_model_error_count",
        )


def public_error(error):
    # Raw failure messages may contain private logs, URLs or credentials. Export
    # only this documented non-sensitive diagnostic; everything else is withheld.
    message = error if isinstance(error, str) else error["message"]
    safe = (
        message
        if re.fullmatch(r"model route returned HTTP [45]\d{2}", message)
        else "Recorded upstream failure; internal details withheld."
    )
    return safe if isinstance(error, str) else {**error, "message": safe}


# DECISION(2026-10-24, rcc00n/Codex): sidecars use the snapshot's strict JSON parser.
# Why: duplicate keys and non-finite values cannot have two interpretations at this boundary.
def parse_preview_json(raw):
    fail(len(raw) <= MAX_BYTES, "payload_too_large")

    def pairs(items):
        result = {}
        for key, value in items:
            fail(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    try:
        p = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                SnapshotError("non_finite_number")
            ),
        )
    except SnapshotError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise SnapshotError("invalid_reasoning_json") from None
    bounded_structure(p)
    return p


def parse_reasoning(raw):
    p = parse_preview_json(raw)
    obj(
        p,
        [
            "schema_version",
            "topic_id",
            "edition_date",
            "run_id",
            "version",
            "status",
            "summary",
            "sources_missing",
            "stories",
            "roundup",
            "generated_at",
            "published_at",
            "expires_at",
            "edition_timezone",
            "window",
            "provenance",
        ],
        ["bar", "errors", "trace", "summary_source"],
    )
    fail(p["schema_version"] == "1.0", "unsupported_reasoning_version")
    identifier(p["topic_id"])
    identifier(p["run_id"])
    fail(edition_date(p["edition_date"]), "invalid_reasoning_date")
    # DECISION(2026-10-24, rcc00n/Codex): only the original provisional v3 bytes may
    # retain 61 transport errors / 63 total errors (two invalid JSON replies). Why: preserve history without relaxing new ledgers.
    envelope(p, raw_sha256=hashlib.sha256(raw).hexdigest())
    fail(type(p["version"]) is int and p["version"] > 0)
    fail(p["status"] in ("ok", "partial", "empty"))
    text(p["summary"])
    if "summary_source" in p:
        fail(p["summary_source"] in ("model", "fallback"))
        if p["summary_source"] == "fallback":
            fail(p["status"] == "partial" and bool(p.get("errors")))
    for missing in rows(p["sources_missing"]):
        text(missing)
    if "bar" in p:
        obj(p["bar"], ["threshold", "confirmation_min"])
        fail(all(type(v) is int and v >= 0 for v in p["bar"].values()))
    event_ids = set()
    ranks = set()
    for s in rows(p["stories"], 10):
        obj(
            s,
            [
                "event_id",
                "rank",
                "headline",
                "standfirst",
                "reading_minutes",
                "rubric",
                "photo",
                "article",
                "claims",
                "spectrum",
                "needs_review",
                "trace_ref",
            ],
            ["sources", "critic_notes", "review_reason", "drafts"],
        )
        identifier(s["event_id"])
        fail(s["event_id"] not in event_ids, "duplicate_reasoning_event")
        event_ids.add(s["event_id"])
        fail(
            type(s["rank"]) is int and s["rank"] > 0 and s["rank"] not in ranks,
            "invalid_reasoning_rank",
        )
        ranks.add(s["rank"])
        for key in ("headline", "standfirst", "trace_ref"):
            text(s[key])
        fail(type(s["reading_minutes"]) is int and 0 < s["reading_minutes"] <= 120)
        fail(type(s["needs_review"]) is bool)
        for key in ("critic_notes", "review_reason"):
            if key in s:
                text(s[key], True)
        if "drafts" in s:
            fail(type(s["drafts"]) is int and s["drafts"] >= 0)
        if s["photo"] is not None:
            obj(
                s["photo"],
                ["url", "credit", "license", "caption"],
                ["source_url", "license_url"],
            )
            for key, value in s["photo"].items():
                text(value)
                if key.endswith("url"):
                    fail(public_url(value), "unsafe_reasoning_url")
        rubric = s["rubric"]
        obj(
            rubric,
            [
                "legal_force",
                "reach",
                "irreversibility",
                "confirmation",
                "total",
                "rationale",
            ],
        )
        for key, maximum in [
            ("legal_force", 2),
            ("reach", 3),
            ("irreversibility", 2),
            ("confirmation", 2),
            ("total", 9),
        ]:
            fail(type(rubric[key]) is int and 0 <= rubric[key] <= maximum)
        fail(
            rubric["total"]
            == sum(
                rubric[k]
                for k in ("legal_force", "reach", "irreversibility", "confirmation")
            ),
            "invalid_impact_total",
        )
        fail(isinstance(rubric["rationale"], dict))
        fail(
            rubric["rationale"].keys()
            <= {"legal_force", "reach", "irreversibility", "confirmation"}
        )
        for value in rubric["rationale"].values():
            text(value)
        claims = {}
        for c in rows(s["claims"]):
            obj(
                c,
                [
                    "id",
                    "text",
                    "status",
                    "verifier",
                    "fact_checker",
                    "reason",
                    "evidence",
                ],
                ["kind", "speaker", "reviewer_status", "reviewer_reason", "reviewer_quote", "resolved_by"],
            )
            identifier(c["id"])
            fail(c["id"] not in claims, "duplicate_reasoning_claim")
            claims[c["id"]] = c
            for key in ("text", "reason"):
                text(c[key])
            for key in ("status", "verifier", "fact_checker"):
                fail(c[key] in ("confirmed", "disputed", "unverified"))
            if "reviewer_status" in c:
                fail(c["reviewer_status"] is None or c["reviewer_status"] in ("confirmed", "disputed", "unverified"))
            for key in ("reviewer_reason", "reviewer_quote"):
                if key in c:
                    text(c[key])
            if "resolved_by" in c:
                fail(c["resolved_by"] in ("agreement", "reviewer", "dispute"))
                if c["resolved_by"] == "reviewer":
                    fail(c.get("reviewer_status") == c["status"])
            if "kind" in c:
                fail(c["kind"] in ("fact", "statement", "number", "context"))
            if "speaker" in c:
                text(c["speaker"], True)
            for e in rows(c["evidence"]):
                obj(
                    e,
                    ["stance", "quote", "title", "url", "independence_group"],
                    ["found_by", "is_document", "quote_id", "by_headline",
                     "source_id", "document_id", "official_doc_id", "char_start", "char_end",
                     "content_hash_at_quote", "access_achieved", "fetched_at", "hash_mismatch", "from_previous_day"],
                )
                fail(e["stance"] in ("supports", "contradicts", "neutral", "statement"))
                for key in ("quote", "title", "independence_group"):
                    text(e[key])
                fail(public_url(e["url"]), "unsafe_reasoning_url")
                if "found_by" in e:
                    fail(e["found_by"] in ("researcher", "verifier", "fact_checker"))
                if "is_document" in e:
                    fail(type(e["is_document"]) is bool)
                if "by_headline" in e:
                    fail(type(e["by_headline"]) is bool)
                quote_binding(e)
                if "quote_id" in e:
                    fail(type(e["quote_id"]) in (str, int) or e["quote_id"] is None)
        for block in rows(s["article"]):
            obj(block, ["kind", "text", "claim_ids", "sources"])
            fail(block["kind"] in ("fact", "context", "statements", "not_confirmed"))
            text(block["text"])
            refs = rows(block["claim_ids"])
            fail(
                all(isinstance(ref, str) and ref in claims for ref in refs),
                "invalid_article_claim_reference",
            )
            if block["kind"] == "fact":
                fail(
                    bool(refs)
                    and all(
                        claims[ref]["status"] == "confirmed"
                        and claims[ref].get("kind") != "statement"
                        for ref in refs
                    ),
                    "unsafe_fact_claim_reference",
                )
            if block["kind"] == "context":
                fail(bool(block["sources"]), "unsourced_article_context")
            for value in rows(block["sources"]):
                source(value)
        for value in rows(s.get("sources", [])):
            source(value)
        spectrum = s["spectrum"]
        obj(
            spectrum,
            ["rating_mode", "coverage", "interpretations"],
            ["left", "right", "note", "outlets"],
        )
        fail(spectrum["rating_mode"] in ("average", "allsides", "mbfc", "adfontes"))
        fail(
            p["status"] == "partial" or {"left", "right", "note"} <= spectrum.keys(),
            "missing_completed_framing",
        )
        if "note" in spectrum:
            text(spectrum["note"])
        for side in ("left", "right"):
            if side not in spectrum:
                continue
            obj(spectrum[side], ["highlights", "omits", "wording", "example_url"])
            for key, value in spectrum[side].items():
                text(value)
            fail(
                not spectrum[side]["example_url"]
                or public_url(spectrum[side]["example_url"]),
                "unsafe_reasoning_url",
            )
        fail(
            isinstance(spectrum["coverage"], dict)
            and spectrum["coverage"].keys()
            <= {"major_left", "major_right", "minor_left", "minor_right", "center"}
        )
        for pair in spectrum["coverage"].values():
            fail(
                isinstance(pair, list)
                and len(pair) == 2
                and all(type(v) is int and v >= 0 for v in pair)
                and pair[0] <= pair[1],
                "invalid_cohort_counts",
            )
        for item in rows(spectrum["interpretations"]):
            obj(item, ["label", "outlets", "mostly"])
            text(item["label"])
            text(item["mostly"])
            fail(type(item["outlets"]) is int and item["outlets"] >= 0)
        for item in rows(spectrum.get("outlets", [])):
            obj(
                item,
                [
                    "source",
                    "cohort",
                    "flank",
                    "url",
                    "highlights",
                    "omits",
                    "wording",
                    "interpretation_label",
                ],
            )
            for value in item.values():
                text(value)
            fail(
                item["cohort"]
                in ("major_left", "major_right", "minor_left", "minor_right", "center")
            )
            fail(item["flank"] in ("left", "right", "center"))
            fail(public_url(item["url"]), "unsafe_reasoning_url")
    roundup = p["roundup"]
    obj(roundup, ["empty_day", "count", "groups"])
    fail(
        type(roundup["empty_day"]) is bool
        and type(roundup["count"]) is int
        and roundup["count"] >= 0
    )
    item_count = 0
    for group in rows(roundup["groups"]):
        obj(group, ["name", "items"])
        text(group["name"])
        for item in rows(group["items"]):
            obj(item, ["event_id", "line", "status", "sources"], ["needs_review", "line_source"])
            identifier(item["event_id"])
            fail(item["event_id"] not in event_ids, "duplicate_reasoning_event")
            event_ids.add(item["event_id"])
            item_count += 1
            text(item["line"])
            text(item["status"])
            if "line_source" in item:
                fail(item["line_source"] in ("model", "title"))
            if "needs_review" in item:
                fail(type(item["needs_review"]) is bool)
            for value in rows(item["sources"]):
                source(value)
    fail(item_count == roundup["count"], "invalid_roundup_count")
    fail(p["status"] != "empty" or not p["stories"], "invalid_empty_snapshot")
    fail(not roundup["empty_day"] or not p["stories"], "invalid_quiet_day")
    for step in rows(p.get("trace", []), 2000):
        obj(
            step,
            [
                "node",
                "iteration",
                "event_id",
                "decision",
                "reason",
                "model",
                "duration_ms",
            ],
            ["detail"],
        )
        text(step["node"])
        fail(type(step["iteration"]) is int and step["iteration"] >= 1)
        fail(
            step["event_id"] is None
            or isinstance(step["event_id"], str)
            and step["event_id"] in event_ids,
            "invalid_trace_event_reference",
        )
        for key in ("decision", "reason"):
            text(step[key])
        if "detail" in step:
            for detail in rows(step["detail"], 12):
                obj(detail, ["text", "reason"])
                text(detail["text"])
                text(detail["reason"])
        text(step["model"], True)
        fail(type(step["duration_ms"]) in (int, float) and step["duration_ms"] >= 0)
    for error in rows(p.get("errors", [])):
        if isinstance(error, str):
            text(error)  # Older public error strings remain readable, with redaction.
        else:
            obj(error, ["node", "event_id", "message"])
            identifier(error["node"])
            fail(
                error["event_id"] is None
                or isinstance(error["event_id"], str)
                and error["event_id"] in event_ids,
                "invalid_error_event_reference",
            )
            text(error["message"])
    # DECISION(2026-10-24, rcc00n/Codex): document identity owns one source across an edition.
    # Why: article and official numeric IDs use separate namespaces, but conflicting source joins must fail.
    document_sources = {}
    for story in p["stories"]:
        for claim in story["claims"]:
            for evidence in claim["evidence"]:
                source_id = evidence.get("source_id")
                for namespace in ("document_id", "official_doc_id"):
                    doc_id = evidence.get(namespace)
                    if doc_id is not None and source_id:
                        key = (namespace, doc_id)
                        fail(document_sources.get(key, source_id) == source_id, "conflicting_document_source")
                        document_sources[key] = source_id
    return p


def present_reasoning(raw, *, now=None, catalog=None):
    p = parse_reasoning(raw)
    if "errors" in p:
        p["errors"] = [public_error(e) for e in p["errors"]]
    now = now or datetime.now(timezone.utc)
    state = (
        "partial"
        if p["status"] == "partial" or p.get("errors") or p["sources_missing"]
        else "available"
    )
    missing_provenance = list(MISSING)
    evidence = [e for story in p["stories"] for claim in story["claims"] for e in claim["evidence"]]
    if evidence and all(e.get("source_id") and (e.get("document_id") is not None or e.get("official_doc_id") is not None) for e in evidence):
        missing_provenance.remove("original document/source IDs")
    if evidence and all(e.get("access_achieved") is not None and e.get("fetched_at") is not None for e in evidence):
        missing_provenance.remove("achieved access levels and retrieval timestamps")
    from .catalog_sources import bind_sources
    resolve = bind_sources(p, catalog["sources"]) if catalog else lambda value: None
    events = []
    source_rows = {}
    for s in sorted(p["stories"], key=lambda s: s["rank"]):
        sources = []
        for value in s.get("sources", []):
            # URL is a presentation key, not an invented collector/source ID.
            row = dict(
                id=value["url"],
                name=value["title"],
                domain=urlsplit(value["url"]).hostname,
                audience=None,
                allsides=None,
                mbfc=None,
                adfontes=None,
            )
            bound = resolve(value)
            if bound:
                row = dict(bound)
            if not any(s["id"] == row["id"] for s in sources):
                sources.append(row)
            source_rows[row["id"]] = row
        event = dict(
            id=s["event_id"],
            topic_id=p["topic_id"],
            date=p["edition_date"],
            title=s["headline"],
            summary=s["standfirst"],
            importance=dict(
                label=f"Impact {s['rubric']['total']} / 9",
                explanation=" · ".join(
                    f"{k}: {v}" for k, v in s["rubric"]["rationale"].items()
                ),
            ),
            sources=sources,
            reasoning=deepcopy(s),
            established=[],
            statements=[],
            disputed=[],
            unknown=[],
            coverage=[],
        )
        for c in s["claims"]:
            bucket = (
                "statements"
                if c.get("kind") == "statement"
                else {
                    "confirmed": "established",
                    "disputed": "disputed",
                    "unverified": "unknown",
                }[c["status"]]
            )
            event[bucket].append(
                dict(
                    text=c["text"],
                    explanation=c["reason"],
                    sources=[
                        dict(title=e["title"], url=e["url"]) for e in c["evidence"]
                    ],
                )
            )
        events.append(event)
    return dict(
        status="demo",
        catalog_revision=catalog["catalog_revision"] if catalog else None,
        topics=[dict(id=p["topic_id"], name=p["topic_id"])],
        sources=catalog["sources"] if catalog else list(source_rows.values()),
        events=events,
        digests=[
            dict(date=p["edition_date"], topic_id=p["topic_id"], summary=p["summary"])
        ],
        reasoning=deepcopy(p),
        preview=dict(
            schema_version="1.0",
            status=state,
            published=False,
            expiry_hint=(
                "expired" if now >= timestamp(p["expires_at"]) else "within_hint"
            ),
            sha256=hashlib.sha256(raw).hexdigest(),
            # DECISION(2026-10-24, rcc00n/Codex): the pinned provisional artifact stays labelled without a sidecar.
            # Why: missing metadata must not erase a known corpus limitation.
            provisional=True if hashlib.sha256(raw).hexdigest() == HISTORICAL_V3_SHA256 else None,
            missing_provenance=missing_provenance,
            warnings=artifact_review_notices(hashlib.sha256(raw).hexdigest(), p["run_id"]) + [
                (
                    "FICTIONAL data; links and quotations are illustrative, not verified news."
                    if p["provenance"]["fictional"]
                    else "Producer-declared collected corpus; this preview does not independently verify source provenance. "
                    + (
                        "Deterministic stand-ins; no AI verification."
                        if p["provenance"]["model"] == "stand-ins"
                        else "Recorded model output; not publication-approved."
                    )
                ),
                "Unpublished preview. Reported timestamps and provenance do not prove publication or a genuine sponsor run.",
                "Trace order is array order, not a fabricated timestamp sequence.",
            ],
        ),
    )


def load_preview(path=None):
    import os
    from .integration import CatalogAdapter
    catalog = CatalogAdapter().snapshot()
    fail(catalog["status"] != "error", "catalog_unavailable")
    snapshot_raw = read_bounded(Path(path) if path else SAMPLE)
    result = present_reasoning(snapshot_raw, catalog=catalog if catalog["catalog_revision"] else None)
    sidecar_path = os.getenv("QUORUM_REASONING_PREVIEW_SIDECAR")
    if sidecar_path:
        bind_preview_sidecar(read_bounded(Path(sidecar_path)), snapshot_raw, result)
    return result


def bind_closed_v4_sidecar(raw, snapshot_raw, result, sidecar):
    # DECISION(2026-10-25, rcc00n/Codex): support only the pinned historical closed-v4 sidecar bytes.
    # Why: this producer format omits full config hashes; display binding must not imply full acceptance.
    fail(hashlib.sha256(raw).hexdigest() == GENUINE_V4_SIDECAR_SHA256, "unsupported_closed_sidecar")
    fail(hashlib.sha256(snapshot_raw).hexdigest() == GENUINE_V4_SHA256, "sidecar_snapshot_mismatch")
    binding, run, p = sidecar['snapshot'], sidecar['run'], result['reasoning']
    fail(binding['sha256_file_bytes'] == result['preview']['sha256'], 'sidecar_snapshot_mismatch')
    fail(type(binding['size_bytes']) is int and binding['size_bytes'] == len(snapshot_raw), 'sidecar_size_mismatch')
    for key, expected in dict(status=p['status'], stories=len(p['stories']), roundup=p['roundup']['count'],
                              errors=len(p.get('errors', [])), published_at=p['published_at']).items():
        fail(type(binding[key]) is type(expected) and binding[key] == expected, 'sidecar_snapshot_mismatch')
    fail(sidecar['provisional'] is False and run['run_id'] == p['run_id'], 'sidecar_snapshot_mismatch')
    fail(sidecar['corpus']['edition_window_utc'] == [p['window'][k] for k in ('start', 'end')], 'sidecar_window_mismatch')
    for key in ('model_calls', 'model_errors', 'answered_by'):
        fail(run[key] == p['provenance'][key], 'sidecar_snapshot_mismatch')
    result['preview']['provisional'] = False
    result['preview']['corpus_binding'] = dict(provisional=False, closed_edition=True,
        edition_window_end_utc=p['window']['end'], sidecar_sha256=hashlib.sha256(raw).hexdigest())
    return result


def bind_preview_sidecar(raw, snapshot_raw, result):
    try:
        sidecar = parse_preview_json(raw)
        fail(isinstance(sidecar, dict), "invalid_sidecar")
        if isinstance(sidecar.get('snapshot'), dict) and 'sha256_file_bytes' in sidecar['snapshot']:
            return bind_closed_v4_sidecar(raw, snapshot_raw, result, sidecar)
        binding = sidecar["snapshot"]
        fail(isinstance(binding, dict), "invalid_sidecar")
        fail(binding["sha256"] == result["preview"]["sha256"], "sidecar_snapshot_mismatch")
        for key in ("topic_id", "edition_date", "version", "run_id", "status"):
            expected = result["reasoning"][key]
            fail(type(binding[key]) is type(expected) and binding[key] == expected, "sidecar_snapshot_mismatch")
        if "bytes" in binding:
            fail(type(binding["bytes"]) is int and binding["bytes"] == len(snapshot_raw), "sidecar_size_mismatch")
        fail(type(sidecar["provisional"]) is bool, "invalid_sidecar")
        fail(result["preview"]["provisional"] is not True or sidecar["provisional"], "sidecar_provisional_mismatch")
        capture = sidecar["corpus_as_of_utc"]
        fail(isinstance(capture, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z", capture)), "invalid_sidecar")
        captured_at = datetime.fromisoformat(capture.replace("Z", "+00:00"))
        # DECISION(2026-10-24, rcc00n/Codex): capture must fit the declared edition and precede generation.
        # Why: a bound hash alone cannot validate contradictory provisional chronology.
        fail(timestamp(result["reasoning"]["window"]["start"]) <= captured_at
             <= min(timestamp(result["reasoning"]["window"]["end"]), timestamp(result["reasoning"]["generated_at"])), "sidecar_capture_outside_window")
        fail(sidecar["edition_window_utc"] == [result["reasoning"]["window"][key] for key in ("start", "end")], "sidecar_window_mismatch")
    except (ValueError, TypeError, KeyError):
        raise SnapshotError("invalid_sidecar") from None
    # Expose only bounded display metadata; private paths, logs and producer prose stay private.
    result["preview"]["provisional"] = sidecar["provisional"]
    result["preview"]["corpus_binding"] = dict(provisional=sidecar["provisional"], corpus_as_of_utc=capture, sidecar_sha256=hashlib.sha256(raw).hexdigest())
    return result
