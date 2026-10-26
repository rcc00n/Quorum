"""Write the provisional sidecar the portal needs to accept a new (non-closed) edition.

    cd reasoning
    python scripts/edition_sidecar.py --snapshot snapshots/_private/<topic>/<date>/v<N>.json \
        --corpus-as-of 2026-10-26T10:30Z --producer-commit <full 40-hex commit> [--out <path>] [--repo <git dir>]

Writes, next to each other and each atomically (temporary file + replace):

    <out>                 the sidecar (default <snapshot>.sidecar.json), UTF-8, stable key order, LF
    <out>.sha256          "<sha256>  <sidecar file name>"
    <snapshot>.sha256     "<sha256>  <snapshot file name>"

The three are replaced in one at a time. If a replace fails after another went through, the files this run replaced
in are removed and the refusal names them and anything left from an earlier run; it says "nothing written" only when
no file was replaced.

The hand-over for one edition is then the snapshot file, its sidecar, both sha256 values and the producer commit:
what the portal's read-only `python manage.py reasoning_snapshot --file --sha256 --sidecar --sidecar-sha256
--producer-commit` validates and `portal_snapshot publish` installs once the gate is open (Issue #2 6411686793,
6412178189). The portal resolves the producer commit in its own checkout, so that commit must be reachable there.

The shape is the provisional ("preview") binding of master's `backend/portal/reasoning_preview.py ›
bind_preview_sidecar`, as Anastasia read it (Issue #2 6411686793):

    {"snapshot": {"sha256", "topic_id", "edition_date", "version", "run_id", "status", "bytes"},
     "provisional": true, "corpus_as_of_utc": "YYYY-MM-DDTHH:MM[:SS]Z", "edition_window_utc": [start, end],
     "producer": {"commit": <40 hex>, "config_sha256": <sha256 of git show <commit>:reasoning/config/reasoning.toml>}}

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): reasoning writes only this provisional form, never the closed
form (`snapshot.sha256_file_bytes`, `producer.commit_of_the_publishing_process`, the LF/CRLF config pair), and refuses
(exit 2, nothing written) unless `validate_sidecar` passes: a re-implementation of every check of master's
`bind_preview_sidecar` and `reasoning_snapshot` (genuine model output: `fictional` false, a model other than
stand-ins, `model_calls` > 0; producer commit and config hash; the editorial hold on the v4 run) plus all of the
`parse_reasoning` that `reasoning_snapshot` runs through `present_reasoning`: the snapshot envelope re-implemented
with explanations (strict JSON, identity fields, timestamps, edition window, provenance counts), then story, claim,
evidence, article, spectrum, roundup, trace and error content through a verbatim copy of master's `parse_reasoning`
(section "portal copy" below). Why: the portal accepts a non-closed edition only with a hash-bound provisional
sidecar; the closed form binds three historical pairs only and attests a closed edition, which a new run cannot
claim. A sidecar that would fail in the portal is refused here, where it is cheap.

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `corpus_as_of_utc` is the time of the post-cut dump the run read
(agreed in Issue #2 6412178189). A time after the window end is clamped to min(window.end, generated_at) and said so
on stderr; a time before window.start is refused (that dump cannot hold the edition's documents), and so is a time
after the snapshot's `generated_at` (the run cannot have read a dump that did not exist yet: the input is wrong).
Why: a post-cut dump holds the whole window, so its window end is the honest capture bound the portal accepts
(start <= capture <= min(end, generated_at)); clamping an earlier or a later-than-generation time would invent one.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = "reasoning/config/reasoning.toml"

# Mirrored from master's backend/portal (snapshot_validation.py, reasoning_preview.py, reasoning_snapshot.py).
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 25
HISTORICAL_V3_SHA256 = "c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30"
GENUINE_V4_SHA256 = "ef231a4f0797c1128869ed5bd69d4d2869771766f634e754aa02dbf375756d79"
HELD_RUN_ID = "2026-10-24-russia-ukraine-war-5"
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+]00:00)")
CAPTURE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}")
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
COMMIT_PREFIX = re.compile(r"^([0-9a-f]{7,40})(?:\s|$)")
SHA256 = re.compile(r"[0-9a-f]{64}")
UNSAFE_CONTENT = re.compile(r"-----BEGIN .*PRIVATE KEY|(?:gh[pousr]_|nvapi-)[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_.-]{20,}")
TOP_REQUIRED = (
    "schema_version", "topic_id", "edition_date", "run_id", "version", "status", "summary", "sources_missing",
    "stories", "roundup", "generated_at", "published_at", "expires_at", "edition_timezone", "window", "provenance",
)
TOP_OPTIONAL = ("bar", "errors", "trace", "summary_source")
PROVENANCE_REQUIRED = ("corpus", "model", "fictional")
PROVENANCE_OPTIONAL = ("fact_checker_model", "model_calls", "answered_by", "model_errors")
IDENTITY_KEYS = ("topic_id", "edition_date", "version", "run_id", "status")
CUT = time(5, 30)

# The provisional form this tool writes, in this order (our contract: exactly these keys, nothing else).
SIDECAR_KEYS = ("snapshot", "provisional", "corpus_as_of_utc", "edition_window_utc", "producer")
BINDING_KEYS = ("sha256",) + IDENTITY_KEYS + ("bytes",)
PRODUCER_KEYS = ("commit", "config_sha256")
CLOSED_FORM_KEYS = ("sha256_file_bytes", "commit_of_the_publishing_process")


class SidecarError(Exception):
    """A refusal: `code` is the portal's code where one exists, `message` says what to fix, `outcome` what is on
    disk afterwards. Never carries secrets."""

    def __init__(self, code: str, message: str = "", outcome: str = "nothing written") -> None:
        super().__init__(code)
        self.code = code
        self.message = message or code
        self.outcome = outcome


def _require(ok: object, code: str, message: str = "") -> None:
    if not ok:
        raise SidecarError(code, message)


# ---------------------------------------------------------------- portal mirrors: parsing and the snapshot envelope


def strict_json(raw: bytes, what: str) -> Any:
    """`parse_preview_json`: size bound, duplicate keys and non-finite numbers refused, nesting and content bounded."""
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"{what} is larger than {MAX_BYTES} bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key", f"{what} repeats a JSON key")
            result[key] = value
        return result

    def non_finite(_: str) -> Any:
        raise SidecarError("non_finite_number", f"{what} holds NaN or Infinity")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=non_finite)
    except SidecarError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise SidecarError("invalid_reasoning_json", f"{what} is not valid UTF-8 JSON") from None
    _bounded(value, what)
    return value


def _bounded(value: Any, what: str, depth: int = 0) -> None:
    """`bounded_structure`: depth <= 25, finite floats, no key-, token- or private-key-like strings."""
    _require(depth <= MAX_DEPTH, "excessive_nesting", f"{what} nests deeper than {MAX_DEPTH}")
    if isinstance(value, float):
        _require(math.isfinite(value), "non_finite_number", f"{what} holds a non-finite number")
    if isinstance(value, str):
        _require(not UNSAFE_CONTENT.search(value), "unsafe_public_content", f"{what} holds a key- or token-like string")
    if isinstance(value, dict):
        for child in value.values():
            _bounded(child, what, depth + 1)
    if isinstance(value, list):
        for child in value:
            _bounded(child, what, depth + 1)


def utc_timestamp(value: Any) -> datetime:
    """The portal's `timestamp`: seconds required, optional fraction, Z or +00:00 only."""
    _require(isinstance(value, str) and TIMESTAMP.fullmatch(value), "invalid_reasoning_timestamp",
             f"timestamp {value!r} is not YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SidecarError("invalid_reasoning_timestamp", f"timestamp {value!r} is not a real instant") from None


def _text(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 20000


def _keys(value: Any, required: tuple[str, ...], optional: tuple[str, ...], what: str) -> None:
    _require(isinstance(value, dict), "invalid_reasoning_1_0", f"{what} is not a JSON object")
    missing = [k for k in required if k not in value]
    _require(not missing, "missing_reasoning_field", f"{what} lacks {', '.join(missing)}")
    extra = sorted(set(value) - set(required) - set(optional))
    _require(not extra, "unsupported_reasoning_field", f"{what} has unsupported fields {', '.join(extra)}")


def _edition_date_ok(value: Any) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


# ---------------------------------------------------------------- portal copy: master's parse_reasoning, verbatim
#
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the snapshot content checks are a verbatim copy of master
# 1444e7c's `parse_reasoning` and every function it calls (backend/portal/reasoning_preview.py and
# snapshot_validation.py), not a re-implementation: only full-line comments and the jsonschema format decorators are
# dropped; the portal's DECISION notes on these lines stay canonical there. `present_reasoning`, which
# `reasoning_snapshot` runs, adds nothing that can fail for a snapshot `parse_reasoning` accepts (error redaction,
# sorting, display rows). Why: those are about 360 lines of story, claim, evidence, article, spectrum, roundup, trace
# and error rules; a copy that tests/test_edition_sidecar.py pins to origin/master by AST equality refuses exactly
# what the portal rejects and fails the suite when the portal changes, where a rewrite would drift unnoticed.
# Review round 1: four synthetic snapshots the portal rejects got a sidecar while only the envelope was checked.
# Names are the portal's; this tool's own helpers are prefixed (`_require`, `utc_timestamp`, `strict_json`).


class SnapshotError(ValueError):
    """Public-safe diagnostics only; never include rejected payload values."""

    def __init__(self, code, issues=None):
        super().__init__(code)
        self.issues = issues or [{"code": code, "path": "/"}]


def require(condition, code):
    if not condition:
        raise SnapshotError(code)


def public_host(host):
    if (
        not host
        or host.lower() in ("localhost",)
        or host.lower().endswith((".localhost", ".local", ".internal"))
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return bool(
            re.fullmatch(
                r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
                host,
            )
        )


def public_url(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        u = urlsplit(value)
        return (
            u.scheme in ("https", "http")
            and public_host(u.hostname)
            and not u.username
            and not u.password
            and u.port in (None, 80, 443)
        )
    except ValueError:
        return False


def edition_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def bounded_structure(value, depth=0):
    require(depth <= 25, "excessive_nesting")
    if isinstance(value, float):
        require(math.isfinite(value), "non_finite_number")
    if isinstance(value, str):
        require(
            not re.search(
                r"-----BEGIN .*PRIVATE KEY|(?:gh[pousr]_|nvapi-)[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_.-]{20,}",
                value,
            ),
            "unsafe_public_content",
        )
    if isinstance(value, dict):
        for child in value.values():
            bounded_structure(child, depth + 1)
    if isinstance(value, list):
        for child in value:
            bounded_structure(child, depth + 1)


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
    expected_end = datetime.combine(day, time(5, 30), zone)
    try:
        expected_start = datetime.combine(day - timedelta(days=1), time(5, 30), zone)
    except OverflowError:
        raise SnapshotError("invalid_reasoning_date") from None
    fail(start == expected_start and end == expected_end, "inconsistent_edition_window")
    fail(expires > end, "expiry_before_edition_end")
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

PORTAL_REJECTS = "the portal's parse_reasoning rejects the snapshot"
CONTENT_HINTS = {
    "invalid_reasoning_1_0": "a field has the wrong type, value or length (the portal does not name the field)",
    "missing_reasoning_field": "a story, claim, evidence, article, spectrum, roundup, trace or error object lacks a "
                               "required field",
    "unsupported_reasoning_field": "a story, claim, evidence, article, spectrum, roundup, trace or error object has a "
                                   "field the portal does not accept",
    "invalid_reasoning_id": "an event, claim, source or error node id is not a portal identifier",
    "invalid_reasoning_timestamp": "an evidence fetched_at is not YYYY-MM-DDTHH:MM:SS[.ffffff]Z",
    "duplicate_reasoning_event": "an event_id appears twice across stories and roundup items",
    "invalid_reasoning_rank": "a story rank is not a positive integer or repeats",
    "unsafe_reasoning_url": "a source, evidence, photo, framing or outlet URL is not a public http(s) URL on port "
                            "80 or 443",
    "invalid_impact_total": "a rubric total is not the sum of its four scores",
    "duplicate_reasoning_claim": "a claim id repeats within a story",
    "invalid_article_claim_reference": "an article block cites a claim id its story does not have",
    "unsafe_fact_claim_reference": "a fact block cites no claim, an unconfirmed claim or a statement",
    "unsourced_article_context": "a context block has no sources",
    "missing_completed_framing": "a story of a run that is not partial lacks spectrum left, right or note",
    "invalid_cohort_counts": "a spectrum coverage pair is not [n, total] with 0 <= n <= total",
    "invalid_roundup_count": "roundup.count differs from the number of roundup items",
    "invalid_empty_snapshot": "status is empty but the snapshot has stories",
    "invalid_quiet_day": "roundup.empty_day is true but the snapshot has stories",
    "invalid_trace_event_reference": "a trace row names an event_id that is neither a story nor a roundup item",
    "invalid_error_event_reference": "an error names an event_id that is neither a story nor a roundup item",
    "conflicting_document_source": "one document id is joined to two different source ids",
}


def portal_content(raw: bytes) -> None:
    """Runs the portal copy above; a rejection becomes a SidecarError with the portal's code and a hint."""
    try:
        parse_reasoning(raw)
    except SnapshotError as exc:
        code = str(exc)
        hint = CONTENT_HINTS.get(code, "see parse_reasoning in master's backend/portal/reasoning_preview.py")
        raise SidecarError(code, f"{PORTAL_REJECTS} ({code}): {hint}") from None
    except (ValueError, TypeError, KeyError):  # the portal command's catch-all code
        raise SidecarError("acceptance_input_unavailable_or_invalid", f"{PORTAL_REJECTS}: unreadable content") from None


def check_snapshot(raw: bytes) -> dict[str, Any]:
    """All of the portal's `parse_reasoning`: first the envelope the sidecar binds (identity, timestamps, window,
    provenance), re-implemented so a refusal says what to fix, then the portal copy for everything else."""
    p = strict_json(raw, "snapshot")
    _keys(p, TOP_REQUIRED, TOP_OPTIONAL, "snapshot")
    _require(p["schema_version"] == "1.0", "unsupported_reasoning_version", "snapshot schema_version is not 1.0")
    for key in ("topic_id", "run_id"):
        _require(isinstance(p[key], str) and IDENTIFIER.fullmatch(p[key]), "invalid_reasoning_id",
                 f"snapshot {key} is not a portal identifier")
    _require(_edition_date_ok(p["edition_date"]), "invalid_reasoning_date", "snapshot edition_date is not YYYY-MM-DD")
    generated = utc_timestamp(p["generated_at"])
    expires = utc_timestamp(p["expires_at"])
    if p["published_at"] is not None:
        _require(utc_timestamp(p["published_at"]) >= generated, "publication_before_generation",
                 "snapshot published_at precedes generated_at")
    _require(_text(p["edition_timezone"]), "invalid_reasoning_1_0", "snapshot edition_timezone is not text")
    try:
        zone = ZoneInfo(p["edition_timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise SidecarError("invalid_edition_timezone", "snapshot edition_timezone is not a known zone") from None
    _keys(p["window"], ("start", "end"), (), "snapshot window")
    start, end = utc_timestamp(p["window"]["start"]), utc_timestamp(p["window"]["end"])
    day = datetime.strptime(p["edition_date"], "%Y-%m-%d").date()
    expected_end = datetime.combine(day, CUT, zone)
    try:
        expected_start = datetime.combine(day - timedelta(days=1), CUT, zone)
    except OverflowError:
        raise SidecarError("invalid_reasoning_date", "snapshot edition_date has no previous day") from None
    _require(start == expected_start and end == expected_end, "inconsistent_edition_window",
             "snapshot window is not 05:30 to 05:30 local in edition_timezone")
    _require(expires > end, "expiry_before_edition_end", "snapshot expires_at is not after the window end")
    prov = p["provenance"]
    _keys(prov, PROVENANCE_REQUIRED, PROVENANCE_OPTIONAL, "snapshot provenance")
    for key in ("corpus", "model"):
        _require(_text(prov[key]), "invalid_reasoning_1_0", f"provenance {key} is not text")
        _require(prov[key], "missing_reasoning_provenance", f"provenance {key} is empty")
    _require(type(prov["fictional"]) is bool, "invalid_reasoning_1_0", "provenance fictional is not a boolean")
    if "fact_checker_model" in prov:
        _require(_text(prov["fact_checker_model"]), "invalid_reasoning_1_0", "provenance fact_checker_model is not text")
        _require(prov["fact_checker_model"], "missing_reasoning_provenance", "provenance fact_checker_model is empty")
    for key in ("model_calls", "model_errors"):
        if key in prov:
            _require(type(prov[key]) is int and 0 <= prov[key] <= 100000, "invalid_model_call_count",
                     f"provenance {key} is not an integer 0..100000")
    if "answered_by" in prov:
        answered = prov["answered_by"]
        _require(isinstance(answered, dict) and len(answered) <= 100, "invalid_answered_by",
                 "provenance answered_by is not an object of at most 100 models")
        for model, count in answered.items():
            _require(_text(model) and model and type(count) is int and 0 < count <= 100000, "invalid_answered_by",
                     "provenance answered_by holds an empty model or a count outside 1..100000")
        if "model_calls" in prov:
            _require(sum(answered.values()) == prov["model_calls"], "inconsistent_model_call_count",
                     "provenance answered_by does not sum to model_calls")
        if "model_errors" in prov:
            _require(answered.get("error", 0) == prov["model_errors"]
                     or (hashlib.sha256(raw).hexdigest() == HISTORICAL_V3_SHA256
                         and answered.get("error") == 61 and prov["model_errors"] == 63),
                     "inconsistent_model_error_count", "provenance answered_by.error differs from model_errors")
    if "model_calls" in prov and "model_errors" in prov:
        _require(prov["model_errors"] <= prov["model_calls"], "inconsistent_model_error_count",
                 "provenance model_errors exceeds model_calls")
    _require(type(p["version"]) is int and p["version"] > 0, "invalid_reasoning_1_0", "snapshot version is not a positive integer")
    _require(p["status"] in ("ok", "partial", "empty"), "invalid_reasoning_1_0", "snapshot status is not ok, partial or empty")
    portal_content(raw)  # stories, claims, evidence, articles, spectrum, roundup, trace, errors, document joins
    return p


def genuine_problem(p: dict[str, Any]) -> str | None:
    """`reasoning_snapshot`'s precondition: genuine model output, not a fixture and not stand-ins, with calls."""
    prov = p["provenance"]
    if prov["fictional"] is not False:
        return "the snapshot is fictional (a fixture corpus): only a run on the collected corpus gets a sidecar"
    if prov["model"] == "stand-ins":
        return "the snapshot was answered by stand-ins (a dry run): only a live model run gets a sidecar"
    if not prov.get("model_calls", 0) > 0:
        return "the snapshot records no model call (provenance.model_calls missing or 0)"
    return None


def capture_time(value: Any) -> datetime:
    """The sidecar's capture format, `YYYY-MM-DDTHH:MM[:SS]Z`, as the portal parses it."""
    _require(isinstance(value, str) and CAPTURE.fullmatch(value), "invalid_sidecar",
             f"corpus time {value!r} is not YYYY-MM-DDTHH:MM[:SS]Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SidecarError("invalid_sidecar", f"corpus time {value!r} is not a real instant") from None


# ---------------------------------------------------------------- files and git


def read_snapshot_file(path: Path) -> bytes:
    """`read_bounded`: a regular file, not a link, one hard link only, at most MAX_BYTES."""
    try:
        info = os.lstat(path)
    except OSError:
        raise SidecarError("snapshot_unreadable", f"snapshot {path} does not exist or cannot be read") from None
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe_snapshot_file",
             f"snapshot {path} is not a regular file with a single link (a symlink, directory or hard link)")
    _require(info.st_size <= MAX_BYTES, "payload_too_large", f"snapshot {path} is larger than {MAX_BYTES} bytes")
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise SidecarError("snapshot_unreadable", f"snapshot {path} cannot be read") from None
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"snapshot {path} is larger than {MAX_BYTES} bytes")
    return raw


def _git(repo: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def commit_known(repo: Path, commit: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{commit}^{{commit}}") is not None


def config_sha256_at(repo: Path, commit: str) -> str | None:
    """sha256 of the config blob exactly as the portal reads it: `git show <commit>:reasoning/config/reasoning.toml`."""
    blob = _git(repo, "show", f"{commit}:{CONFIG_PATH}")
    return None if blob is None else hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------- the sidecar


def resolve_corpus_as_of(value: str, p: dict[str, Any]) -> tuple[str, str | None]:
    """(corpus_as_of_utc, a note for stderr or None). See the second DECISION in the module docstring."""
    captured = capture_time(value)
    start, end = utc_timestamp(p["window"]["start"]), utc_timestamp(p["window"]["end"])
    generated = utc_timestamp(p["generated_at"])
    _require(captured >= start, "corpus_before_window",
             f"corpus time {value} is before the edition window start {p['window']['start']}: "
             "that dump cannot hold this edition's documents")
    _require(captured <= generated, "corpus_after_generation",
             f"corpus time {value} is after the snapshot's generated_at {p['generated_at']}: "
             "the run cannot have read that dump; pass the time of the dump the run read")
    if captured <= end:
        return value, None
    # whole seconds, floored: the capture format has no fraction, and a floor never passes the bound
    clamped = min(end, generated).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = (f"corpus time {value} is after the edition window end {p['window']['end']}; corpus_as_of_utc "
            f"clamped to min(window.end, generated_at) = {clamped}")
    return clamped, note


def build_sidecar(snapshot_raw: bytes, p: dict[str, Any], corpus_as_of_utc: str, producer_commit: str,
                  config_sha256: str) -> dict[str, Any]:
    """The provisional sidecar, keys in the order of SIDECAR_KEYS / BINDING_KEYS / PRODUCER_KEYS."""
    binding = {"sha256": hashlib.sha256(snapshot_raw).hexdigest()}
    binding.update((key, p[key]) for key in IDENTITY_KEYS)  # values (and so JSON types) taken from the snapshot itself
    binding["bytes"] = len(snapshot_raw)
    return {
        "snapshot": binding,
        "provisional": True,
        "corpus_as_of_utc": corpus_as_of_utc,
        "edition_window_utc": [p["window"]["start"], p["window"]["end"]],
        "producer": {"commit": producer_commit, "config_sha256": config_sha256},
    }


def serialize(sidecar: dict[str, Any]) -> bytes:
    return (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_sidecar(sidecar: bytes | dict[str, Any], snapshot_path: Path | str, producer_commit: str,
                     repo: Path | str = REPO) -> dict[str, Any]:
    """Re-implements the portal's acceptance checks for a provisional sidecar; raises SidecarError on the first failure.

    Order and codes follow master's `reasoning_snapshot.Command.handle` and `bind_preview_sidecar` (inside the latter
    the portal reports every failure as `invalid_sidecar`; the inner code is kept here because it says what to fix).
    Checks marked "ours" are this tool's own contract on top of the portal's: exactly the provisional keys, `bytes`
    present, `provisional` true, the full commit, the commit present in the repository. Returns the two hashes.
    """
    repo = Path(repo)
    # reasoning_snapshot: the producer commit is full 40 hex; both files are bounded regular files
    _require(isinstance(producer_commit, str) and FULL_COMMIT.fullmatch(producer_commit),
             "expected_full_producer_commit_required", "the producer commit must be the full 40-hex lowercase commit")
    snapshot_raw = read_snapshot_file(Path(snapshot_path))
    raw = sidecar if isinstance(sidecar, (bytes, bytearray)) else serialize(sidecar)
    raw = bytes(raw)
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"sidecar is larger than {MAX_BYTES} bytes")
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    # present_reasoning(raw) -> parse_reasoning: the whole snapshot (envelope, then the portal copy for content)
    p = check_snapshot(snapshot_raw)
    # bind_preview_sidecar
    s = strict_json(raw, "sidecar")
    try:
        _require(isinstance(s, dict), "invalid_sidecar", "sidecar is not a JSON object")
        closed = [k for k in CLOSED_FORM_KEYS if isinstance(s.get("snapshot"), dict) and k in s["snapshot"]
                  or isinstance(s.get("producer"), dict) and k in s["producer"]]
        _require(not closed, "closed_form_not_produced",
                 f"sidecar carries closed-form keys {', '.join(closed)}: reasoning writes the provisional form only")
        binding = s["snapshot"]
        _require(isinstance(binding, dict), "invalid_sidecar", "sidecar snapshot is not an object")
        _require(binding["sha256"] == snapshot_sha256, "sidecar_snapshot_mismatch",
                 "sidecar snapshot.sha256 is not the sha256 of the snapshot file")
        for key in IDENTITY_KEYS:
            expected = p[key]
            _require(type(binding[key]) is type(expected) and binding[key] == expected, "sidecar_snapshot_mismatch",
                     f"sidecar snapshot.{key} differs from the snapshot's own {key} (value or JSON type)")
        _require("bytes" in binding, "sidecar_size_mismatch", "sidecar snapshot.bytes is missing")  # ours
        _require(type(binding["bytes"]) is int and binding["bytes"] == len(snapshot_raw), "sidecar_size_mismatch",
                 "sidecar snapshot.bytes is not the snapshot file size")
        _require(type(s["provisional"]) is bool, "invalid_sidecar", "sidecar provisional is not a boolean")
        snapshot_provisional = True if snapshot_sha256 == HISTORICAL_V3_SHA256 else None
        _require(snapshot_provisional is not True or s["provisional"], "sidecar_provisional_mismatch",
                 "the snapshot is provisional, so the sidecar must say provisional true")
        _require(s["provisional"] is True, "provisional_required", "this tool writes provisional sidecars only")  # ours
        captured = capture_time(s["corpus_as_of_utc"])
        bound = min(utc_timestamp(p["window"]["end"]), utc_timestamp(p["generated_at"]))
        _require(utc_timestamp(p["window"]["start"]) <= captured <= bound, "sidecar_capture_outside_window",
                 "sidecar corpus_as_of_utc is not between window.start and min(window.end, generated_at)")
        _require(s["edition_window_utc"] == [p["window"][k] for k in ("start", "end")], "sidecar_window_mismatch",
                 "sidecar edition_window_utc is not [window.start, window.end] verbatim")
        # ours: exactly the provisional keys, nothing private or extra
        for value, keys, what in ((s, SIDECAR_KEYS, "sidecar"), (binding, BINDING_KEYS, "sidecar snapshot"),
                                  (s.get("producer"), PRODUCER_KEYS, "sidecar producer")):
            _require(isinstance(value, dict) and list(value) == list(keys), "unexpected_sidecar_field",
                     f"{what} keys are not exactly {', '.join(keys)} in that order")
        # reasoning_snapshot: genuine model output
        problem = genuine_problem(p)
        _require(problem is None, "genuine_model_output_required", problem or "")
        # reasoning_snapshot: producer commit and config (non-closed branch)
        producer = s["producer"]
        prefix = COMMIT_PREFIX.match(producer["commit"])
        _require(prefix is not None and producer_commit.startswith(prefix[1]), "producer_commit_mismatch",
                 "sidecar producer.commit is not a prefix of the producer commit")
        _require(producer["commit"] == producer_commit, "producer_commit_mismatch",
                 "sidecar producer.commit is not the full producer commit")  # ours
        declared = producer["config_sha256"]
        _require(isinstance(declared, str) and SHA256.fullmatch(declared), "invalid_config_sha256",
                 "sidecar producer.config_sha256 is not 64 lowercase hex")
        _require(commit_known(repo, producer_commit), "producer_commit_unknown",
                 f"commit {producer_commit} is not in the repository at {repo}")  # ours
        actual = config_sha256_at(repo, producer_commit)
        _require(actual is not None, "producer_config_unavailable",
                 f"{CONFIG_PATH} does not exist at commit {producer_commit}")
        _require(actual == declared, "producer_config_mismatch",
                 f"sidecar producer.config_sha256 is not the sha256 of {CONFIG_PATH} at {producer_commit}")
        # reasoning_snapshot: artifact_review_issues (the editorial hold on the original v4)
        _require(not (snapshot_sha256 == GENUINE_V4_SHA256 or p["run_id"] == HELD_RUN_ID), "impact_score_review_required",
                 "this snapshot is under the portal's editorial impact hold")
    except (KeyError, TypeError, ValueError):
        raise SidecarError("invalid_sidecar", "sidecar lacks a required field or holds a wrong type") from None
    return {"snapshot_sha256": snapshot_sha256, "sidecar_sha256": hashlib.sha256(raw).hexdigest()}


# ---------------------------------------------------------------- writing


def _same(a: Path, b: Path) -> bool:
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): paths that differ only in letter case count as the same file
    # on every platform (casefold, not os.path.normcase). Why: NTFS and APFS are case-insensitive but normcase folds
    # case on Windows only, so on a Mac `--out V1.JSON` would replace the snapshot v1.json; refusing a case variant
    # on Linux costs nothing. abspath already gives Windows paths one separator.
    return os.path.abspath(a).casefold() == os.path.abspath(b).casefold()


def write_atomically(files: list[tuple[Path, bytes]], replaced: list[Path] | None = None) -> None:
    """Every file goes to a temporary file in its own directory first; only when all exist are they replaced in,
    one at a time. Each destination is appended to `replaced` right after its replace, so that the caller knows what
    a failure part-way left on disk."""
    replaced = [] if replaced is None else replaced
    temps: list[tuple[str, Path]] = []
    try:
        for path, data in files:
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
            temps.append((tmp, path))
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for tmp, path in temps:
            os.replace(tmp, path)
            replaced.append(path)
    finally:
        for tmp, _ in temps:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _remove(path: Path) -> bool:
    """Deletes one file this tool wrote; True when it is gone afterwards."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


def _undo_write(replaced: list[Path], targets: list[Path]) -> str:
    """Removes the files this run already replaced in and says what is on disk afterwards: what was removed, what
    could not be removed, and which files of an earlier run are left without the set they belonged to."""
    removed = [path for path in replaced if _remove(path)]
    left = [path for path in replaced if path not in removed]
    earlier = [path for path in targets if path not in replaced and path.exists()]
    parts = []
    if removed:
        parts.append(f"the files it wrote were removed: {', '.join(map(str, removed))}")
    if left:
        parts.append(f"delete {', '.join(map(str, left))} before any hand-over")
    if earlier:
        parts.append(f"left from an earlier run without the files they belonged to: {', '.join(map(str, earlier))}; "
                     "delete them before any hand-over")
    return "; ".join(parts)


def hash_line(data: bytes, name: str) -> bytes:
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")


def make(snapshot: Path, corpus_as_of: str, producer_commit: str, out: Path | None, repo: Path) -> dict[str, Any]:
    """Checks every precondition, builds and validates the sidecar, then writes the three files. Raises SidecarError."""
    _require(isinstance(producer_commit, str) and FULL_COMMIT.fullmatch(producer_commit),
             "expected_full_producer_commit_required",
             f"--producer-commit {producer_commit!r} is not a full 40-hex lowercase commit")
    raw = read_snapshot_file(snapshot)
    p = check_snapshot(raw)
    problem = genuine_problem(p)
    _require(problem is None, "genuine_model_output_required", problem or "")
    _require(commit_known(repo, producer_commit), "producer_commit_unknown",
             f"commit {producer_commit} is not in the repository at {repo}")
    config_sha256 = config_sha256_at(repo, producer_commit)
    _require(config_sha256 is not None, "producer_config_unavailable",
             f"{CONFIG_PATH} does not exist at commit {producer_commit}")
    corpus_as_of_utc, note = resolve_corpus_as_of(corpus_as_of, p)
    out = Path(out) if out else snapshot.with_name(snapshot.name + ".sidecar.json")
    out_hash = out.with_name(out.name + ".sha256")
    snapshot_hash = snapshot.with_name(snapshot.name + ".sha256")
    paths = [snapshot, out, out_hash, snapshot_hash]
    _require(all(not _same(a, b) for i, a in enumerate(paths) for b in paths[i + 1:]), "out_path_conflict",
             f"--out {out} would overwrite the snapshot or a hash file")
    _require(out.parent.is_dir(), "out_dir_missing", f"the directory of --out {out} does not exist")
    data = serialize(build_sidecar(raw, p, corpus_as_of_utc, producer_commit, config_sha256))
    hashes = validate_sidecar(data, snapshot, producer_commit, repo)
    _require(read_snapshot_file(snapshot) == raw, "snapshot_changed", f"snapshot {snapshot} changed while it was read")
    targets = [out, out_hash, snapshot_hash]
    replaced: list[Path] = []
    try:
        write_atomically([(out, data), (out_hash, hash_line(data, out.name)), (snapshot_hash, hash_line(raw, snapshot.name))],
                         replaced)
    except OSError as exc:
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a replace that fails after an earlier one went through
        # removes the files this run replaced in and names them, any it could not remove and any left from an earlier
        # run; "nothing written" is said only when no replace happened. Why: the three files are replaced one at a
        # time (no filesystem replaces a set at once; on Windows a target held open fails), and a new sidecar beside
        # an old .sha256 must never be reported as an intact set.
        raise SidecarError("write_failed", f"could not write the sidecar files: {exc.strerror or type(exc).__name__}",
                           _undo_write(replaced, targets) if replaced else "nothing written") from None
    try:
        on_disk = hashlib.sha256(out.read_bytes()).hexdigest()
    except OSError:
        on_disk = None
    if on_disk != hashes["sidecar_sha256"]:
        # the three files are already replaced in: remove them, so a refusal never leaves a hand-over set behind
        raise SidecarError("write_failed", f"sidecar {out} on disk differs from the validated bytes",
                           _undo_write(replaced, targets))
    return {**hashes, "sidecar": out, "sidecar_hash_file": out_hash, "snapshot_hash_file": snapshot_hash,
            "corpus_as_of_utc": corpus_as_of_utc, "note": note}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", required=True, type=Path, help="the snapshot file the run wrote")
    parser.add_argument("--corpus-as-of", required=True,
                        help="time of the post-cut dump the run read, YYYY-MM-DDTHH:MM[:SS]Z")
    parser.add_argument("--producer-commit", required=True, help="the full 40-hex commit the run was produced by")
    parser.add_argument("--out", type=Path, help="sidecar path (default <snapshot>.sidecar.json)")
    parser.add_argument("--repo", type=Path, default=REPO, help="git checkout holding the commit (default: this one)")
    args = parser.parse_args(argv)
    try:
        result = make(args.snapshot, args.corpus_as_of, args.producer_commit, args.out, args.repo)
    except SidecarError as exc:
        print(f"edition_sidecar: refused ({exc.code}): {exc.message}; {exc.outcome}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:  # the portal's catch-all code, no payload values
        print(f"edition_sidecar: refused (acceptance_input_unavailable_or_invalid): {type(exc).__name__}; "
              "nothing written", file=sys.stderr)
        return 2
    if result["note"]:
        print(f"edition_sidecar: {result['note']}", file=sys.stderr)
    print(f"sidecar {result['sidecar']}  sha256 {result['sidecar_sha256']}")
    print(f"snapshot {args.snapshot}  sha256 {result['snapshot_sha256']}")
    print(f"corpus_as_of_utc {result['corpus_as_of_utc']}  producer {args.producer_commit}")
    print("portal check: python manage.py reasoning_snapshot --file <snapshot> --sha256 <snapshot sha256> "
          "--sidecar <sidecar> --sidecar-sha256 <sidecar sha256> --producer-commit <producer>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
