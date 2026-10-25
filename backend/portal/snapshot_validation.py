"""Portal-owned proposal validation. This does not verify the truth of source material."""

import ipaddress
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator, FormatChecker

MAX_BYTES = 2 * 1024 * 1024
VERSION = "quorum.portal.snapshot.v1-proposal"
SCHEMA = json.loads(
    (Path(__file__).parent / "schemas/analysis-v1.schema.json").read_text()
)
FORMATS = FormatChecker()


def schema_fields(node):
    if not isinstance(node, dict):
        return set()
    result = set(node.get("properties", {}))
    for value in node.values():
        if isinstance(value, dict):
            result.update(schema_fields(value))
        elif isinstance(value, list):
            for item in value:
                result.update(schema_fields(item))
    return result


SAFE_FIELDS = schema_fields(SCHEMA)


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


@FORMATS.checks("public-domain")
def domain(value):
    return isinstance(value, str) and public_host(value)


@FORMATS.checks("public-url")
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


@FORMATS.checks("edition-date")
def edition_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


@FORMATS.checks("utc-timestamp")
def timestamp(value):
    try:
        return (
            isinstance(value, str)
            and value.endswith("Z")
            and datetime.fromisoformat(value[:-1] + "+00:00")
            .utcoffset()
            .total_seconds()
            == 0
        )
    except (ValueError, AttributeError):
        return False


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMATS)


def unique(rows):
    keys = [r["id"] for r in rows]
    require(len(keys) == len(set(keys)), "duplicate_id")
    return {r["id"]: r for r in rows}


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


def validate_snapshot(payload):
    bounded_structure(payload)
    # Report schema locations, never jsonschema's value-echoing message/instance.
    issues = []
    for error in VALIDATOR.iter_errors(payload):
        path = "/" + "/".join(
            str(v) if isinstance(v, int) or str(v) in SAFE_FIELDS else "*"
            for v in error.absolute_path
        )
        issues.append(
            {
                "code": "schema_" + error.validator,
                "path": path,
                "schema_path": "/" + "/".join(map(str, error.absolute_schema_path)),
            }
        )
        if len(issues) == 20:
            break
    if issues:
        raise SnapshotError("invalid_snapshot_schema", issues)

    topics = unique(payload["topics"])
    sources = unique(payload["sources"])
    events = unique(payload["events"])
    require(
        instant(payload["expires_at"]) > instant(payload["generated_at"]),
        "invalid_expiry",
    )
    require(payload["parent_revision"] != payload["revision"], "self_parent_revision")
    for s in sources.values():
        require(
            s["audience"] is None
            or (
                s["audience_source_url"] is not None and s["audience_as_of"] is not None
            ),
            "missing_audience_provenance",
        )
        for mode in ("allsides", "mbfc", "adfontes"):
            require(
                s[mode] is None or s["rating_provenance"][mode] is not None,
                "missing_rating_provenance",
            )
    for e in events.values():
        require(
            e["topic_id"] in topics and e["date"] == payload["edition"],
            "invalid_event_reference",
        )
        require(
            len(e["source_ids"]) == len(set(e["source_ids"]))
            and set(e["source_ids"]) <= sources.keys(),
            "invalid_source_reference",
        )
        a = e["analysis"]
        docs = unique(a["documents"])
        claims = unique(a["claims"])
        unique(a["trace"])
        for d in docs.values():
            require(d["source_id"] in e["source_ids"], "invalid_document_source")
            require(
                instant(d["fetched_at"]) <= instant(payload["generated_at"])
                and (
                    d["published_at"] is None
                    or instant(d["published_at"]) <= instant(payload["generated_at"])
                ),
                "future_document",
            )
        for claim in claims.values():
            for v in (claim["primary_verification"], claim["independent_verification"]):
                require(
                    (v["status"] == "not_run") == (v["checked_at"] is None),
                    "invalid_verification_time",
                )
                require(
                    v["status"] == "not_run" or bool(v["summary"]),
                    "missing_verification_summary",
                )
                if v["checked_at"]:
                    require(
                        instant(v["checked_at"]) <= instant(payload["generated_at"]),
                        "future_verification",
                    )
            for citation in claim["supporting"] + claim["contradicting"]:
                require(citation["document_id"] in docs, "invalid_evidence_reference")
                doc = docs[citation["document_id"]]
                require(doc["access_level"] != 3, "coverage_only_evidence")
                start, end = citation["char_start"], citation["char_end"]
                require((start is None) == (end is None), "invalid_quote_offsets")
                if citation["quote"] is not None:
                    require(
                        citation["content_hash_at_quote"] is not None,
                        "missing_quote_hash",
                    )
                    require(
                        start is not None
                        and end > start
                        and end - start == len(citation["quote"]),
                        "invalid_quote_offsets",
                    )
                else:
                    require(start is None, "offsets_without_quote")
            if claim["status"] == "attributed":
                require(claim["attribution"] is not None, "missing_attribution")
            if claim["status"] == "established":
                require(
                    bool(claim["supporting"])
                    and claim["primary_verification"]["status"] == "confirmed"
                    and claim["independent_verification"]["status"] == "confirmed"
                    and claim["disagreement"] == "none"
                    and not claim["contradicting"],
                    "unsupported_established_claim",
                )
                supporting = [docs[c["document_id"]] for c in claim["supporting"]]
                require(
                    any(d["kind"] == "official" and d["primary"] for d in supporting)
                    or len(
                        {
                            sources[d["source_id"]]["independence_group"]
                            for d in supporting
                        }
                    )
                    >= 2,
                    "insufficient_independent_support",
                )
            if claim["disagreement"] == "present":
                require(
                    claim["status"] in ("disputed", "unknown"),
                    "unresolved_disagreement",
                )
        for frame in a["frames"]:
            require(
                frame["document_id"] in docs
                and frame["source_id"] == docs[frame["document_id"]]["source_id"],
                "invalid_frame_reference",
            )
            require(
                set(frame["emphasized_claim_ids"]) <= claims.keys(),
                "invalid_claim_reference",
            )
            require(
                docs[frame["document_id"]]["access_level"] != 3, "coverage_only_framing"
            )
        for step in a["trace"]:
            require(
                set(step["evidence_refs"]) <= docs.keys(), "invalid_trace_reference"
            )
            require(
                instant(step["timestamp"]) <= instant(payload["generated_at"]),
                "future_trace",
            )
        for correction in a["corrections"]:
            require(
                instant(correction["timestamp"]) <= instant(payload["generated_at"]),
                "future_correction",
            )
            require(
                correction["previous_revision"] != payload["revision"],
                "self_correction",
            )
            require(
                correction["replacement_claim_id"] is None
                or correction["replacement_claim_id"] in claims,
                "invalid_correction_reference",
            )
        coverage = a["coverage"]
        covered = coverage["covered_source_ids"]
        eligible = coverage["eligible_source_ids"]
        require(
            len(covered) == len(set(covered)) and set(covered) <= set(e["source_ids"]),
            "invalid_coverage_reference",
        )
        require(
            eligible is None
            or len(eligible) == len(set(eligible))
            and set(covered) <= set(eligible) <= sources.keys(),
            "invalid_coverage_denominator",
        )
        count = coverage["publication_count"]
        confirm = coverage["independent_confirmation_count"]
        require(count is None or count >= len(covered), "invalid_publication_count")
        require(
            confirm is None
            or confirm <= len({sources[s]["independence_group"] for s in covered}),
            "invalid_confirmation_count",
        )
    for digest in payload["digests"]:
        require(
            digest["topic_id"] in topics and digest["date"] == payload["edition"],
            "invalid_digest_reference",
        )
    for error in payload["errors"]:
        require(
            error["event_id"] is None or error["event_id"] in events,
            "invalid_error_reference",
        )
    require(
        not payload["errors"] or payload["completeness"] == "partial",
        "unreported_partial_result",
    )
    return payload


def parse_snapshot(raw):
    require(len(raw) <= MAX_BYTES, "payload_too_large")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                SnapshotError("non_finite_number")
            ),
        )
    except SnapshotError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise SnapshotError("invalid_json") from None
    return validate_snapshot(payload)
