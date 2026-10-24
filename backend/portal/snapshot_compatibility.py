"""Read-only portal compatibility report, not reasoning schema ownership or publication."""

from datetime import datetime, timezone
from .snapshot_validation import SnapshotError, parse_snapshot, instant, VERSION
from .snapshot_projection import project

HINTS = {
    "schema_required": "Supply required fields; inspect required[] at schema_path (missing names are not echoed).",
    "schema_additionalProperties": "Remove unsupported fields or agree an explicit versioned mapping.",
    "schema_format": "Use the declared date, UTC timestamp, revision/domain or public HTTP(S) URL format.",
    "schema_type": "Use the declared type; unknown values must be explicit null only where allowed.",
    "schema_const": "Use the portal proposal version, or agree and implement a mapping.",
    "schema_enum": "Use an enumerated status/access/action value from the schema.",
    "invalid_event_reference": "Match event topic_id to topics and date to envelope edition.",
    "invalid_evidence_reference": "Every citation document_id must resolve inside its event analysis.",
    "unsupported_established_claim": "Established requires supporting evidence, confirmed primary/independent reviews and no unresolved contradiction.",
    "insufficient_independent_support": "Supply primary official support or at least two genuinely independent groups; reprints are not independent.",
    "missing_audience_provenance": "Supply audience_source_url and audience_as_of, or keep audience null.",
    "missing_rating_provenance": "Supply each available rating's provenance URL, or keep that rating null.",
    "coverage_only_evidence": "Access level 3 permits coverage only; do not cite inaccessible text as evidence.",
    "coverage_only_framing": "Access level 3 cannot substantiate framing analysis.",
    "missing_attribution": "Name the speaker for an attributed claim.",
    "unresolved_disagreement": "An unresolved verifier disagreement must remain disputed or unknown.",
    "invalid_quote_offsets": "Use matching Unicode code-point start/end offsets, end-exclusive, for the exact quote text.",
    "missing_quote_hash": "Supply content_hash_at_quote for the exact source text representation.",
    "duplicate_id": "Keep IDs unique within each topic/source/event/document/claim/trace collection.",
    "unreported_partial_result": "Mark completeness partial when supplying processing errors.",
    "unsafe_public_content": "Remove credentials/private material; export only public-safe summaries.",
    "candidate_file_unreadable": "Supply a readable regular file, without symlinks or hardlinks.",
    "payload_too_large": "Keep the UTF-8 JSON envelope within 2 MiB.",
}


def compatibility_report(raw=None, error=None):
    report = {
        "report_version": "quorum.portal.compatibility.v1",
        "compatible": False,
        "target_schema": VERSION,
        "published": False,
        "issues": [],
        "warnings": [],
    }
    try:
        if error:
            raise error
        payload = parse_snapshot(raw)
        snapshot = project(
            payload,
            {
                "status": (
                    "partial" if payload["completeness"] == "partial" else "available"
                )
            },
        )
        # Serialize the actual projection, including numeric/null and UTF-8 compatibility.
        import json

        json.dumps(snapshot, allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(snapshot["events"]) != len(payload["events"]):
            raise SnapshotError("projection_incompatible")
        report.update(
            compatible=True,
            counts={
                k: len(snapshot[k]) for k in ("topics", "sources", "events", "digests")
            },
        )
        if payload["mode"] == "demo":
            report["warnings"].append("demo_only_not_live_integration")
        if instant(payload["expires_at"]) <= datetime.now(timezone.utc):
            report["warnings"].append("expired_not_publishable_as_current")
        if payload["completeness"] == "partial":
            report["warnings"].append("partial_analysis")
        if any(e["analysis"]["corrections"] for e in payload["events"]):
            report["warnings"].append(
                "correction_history_requires_store_validation_at_publish"
            )
        report["warnings"].append(
            "compatibility_does_not_verify_truth_or_publication_authorization"
        )
    except SnapshotError as exc:
        report["issues"] = [
            {
                **issue,
                "hint": HINTS.get(
                    issue["code"],
                    "Correct this invariant using snapshot_validation.py and the linked proposal schema; no input values are echoed.",
                ),
            }
            for issue in exc.issues
        ]
    except OSError:
        report["issues"] = [
            {
                "code": "candidate_file_unreadable",
                "path": "/",
                "hint": HINTS["candidate_file_unreadable"],
            }
        ]
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        report["issues"] = [
            {
                "code": "projection_incompatible",
                "path": "/",
                "hint": "The validated result could not be serialized as the portal view model; review the mapping.",
            }
        ]
    return report
