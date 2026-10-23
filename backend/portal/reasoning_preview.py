"""Reasoning 1.0 presentation adapter. DEV/fictional only; never calls the publisher."""

import hashlib
import json
import re
from copy import deepcopy
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
SAMPLE_REVISION = "8a4d453e0ab1f1338abcf77c5eac62d18d9ec2d6"
MISSING = [
    "original document/source IDs",
    "collector content hashes and document versions",
    "Unicode quote offsets and verified quote hashes",
    "achieved access levels and retrieval timestamps",
    "review actor IDs and timestamps",
    "freshness/publication timestamps",
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


def parse_reasoning(raw):
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
        ],
        ["bar", "errors", "trace"],
    )
    fail(p["schema_version"] == "1.0", "unsupported_reasoning_version")
    identifier(p["topic_id"])
    identifier(p["run_id"])
    fail(edition_date(p["edition_date"]), "invalid_reasoning_date")
    fail(type(p["version"]) is int and p["version"] > 0)
    fail(p["status"] in ("ok", "partial", "empty"))
    text(p["summary"])
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
                ["kind", "speaker"],
            )
            identifier(c["id"])
            fail(c["id"] not in claims, "duplicate_reasoning_claim")
            claims[c["id"]] = c
            for key in ("text", "reason"):
                text(c[key])
            for key in ("status", "verifier", "fact_checker"):
                fail(c[key] in ("confirmed", "disputed", "unverified"))
            if "kind" in c:
                fail(c["kind"] in ("fact", "statement", "number"))
            if "speaker" in c:
                text(c["speaker"], True)
            for e in rows(c["evidence"]):
                obj(
                    e,
                    ["stance", "quote", "title", "url", "independence_group"],
                    ["found_by", "is_document", "quote_id"],
                )
                fail(e["stance"] in ("supports", "contradicts", "neutral", "statement"))
                for key in ("quote", "title", "independence_group"):
                    text(e[key])
                fail(public_url(e["url"]), "unsafe_reasoning_url")
                if "found_by" in e:
                    fail(e["found_by"] in ("researcher", "verifier", "fact_checker"))
                if "is_document" in e:
                    fail(type(e["is_document"]) is bool)
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
            ["rating_mode", "left", "right", "note", "coverage", "interpretations"],
            ["outlets"],
        )
        fail(spectrum["rating_mode"] in ("average", "allsides", "mbfc", "adfontes"))
        text(spectrum["note"])
        for side in ("left", "right"):
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
            obj(item, ["event_id", "line", "status", "sources"], ["needs_review"])
            identifier(item["event_id"])
            fail(item["event_id"] not in event_ids, "duplicate_reasoning_event")
            event_ids.add(item["event_id"])
            item_count += 1
            text(item["line"])
            text(item["status"])
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
        text(step["model"], True)
        fail(type(step["duration_ms"]) in (int, float) and step["duration_ms"] >= 0)
    for error in rows(p.get("errors", [])):
        # Error shapes are not fully specified yet; don't forward arbitrary objects/private logs.
        fail(isinstance(error, str), "unsupported_reasoning_error_shape")
        text(error)
    return p


def present_reasoning(raw):
    p = parse_reasoning(raw)
    state = (
        "partial"
        if p["status"] == "partial" or p.get("errors") or p["sources_missing"]
        else "available"
    )
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
        catalog_revision=None,
        topics=[dict(id=p["topic_id"], name=p["topic_id"])],
        sources=list(source_rows.values()),
        events=events,
        digests=[
            dict(date=p["edition_date"], topic_id=p["topic_id"], summary=p["summary"])
        ],
        reasoning=deepcopy(p),
        preview=dict(
            schema_version="1.0",
            status=state,
            published=False,
            sha256=hashlib.sha256(raw).hexdigest(),
            missing_provenance=MISSING,
            warnings=[
                "FICTIONAL data; links and quotations are illustrative, not verified news.",
                "No publication/freshness timestamps supplied. No expiry is inferred.",
                "Sample topic differs from collector ukraine-aid; no automatic remapping.",
                "Trace order is array order, not a fabricated timestamp sequence.",
            ],
        ),
    )


def load_preview(path=None):
    return present_reasoning(read_bounded(Path(path) if path else SAMPLE))
