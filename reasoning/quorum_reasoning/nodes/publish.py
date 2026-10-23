"""publish: the snapshot of docs/ARCHITECTURE.md § 8 for one topic and edition day, plus the topic summary.

The snapshot is built from state only; storing and versioning it (analysis.snapshots) is the store's job
and is not part of this node. `status` is "partial" when any node recorded an error, "empty" when no story
crossed the bar, "ok" otherwise. The adapter must not turn a failed pull into an empty edition.
"""

from __future__ import annotations

import math

from .. import config, llm
from ..state import Claim, Event, RunState
from ..trace import finish, step

SCHEMA_VERSION = "1.0"


def reading_minutes(e: Event) -> int:
    words = len(e["standfirst"].split()) + sum(len(b["text"].split()) for b in e["article"])
    return max(1, math.ceil(words / 200))


def claim_view(c: Claim) -> dict:
    return {
        "id": c["id"],
        "text": c["text"],
        "kind": c["kind"],
        "speaker": c.get("speaker"),
        "status": c["final_status"],
        "verifier": c["verifier_status"],
        "fact_checker": c["fact_checker_status"],
        "reason": c["adjudication"] if c["final_status"] == "disputed" else c["verifier_reason"],
        "evidence": [
            {
                "stance": ev["stance"],
                "quote": ev["quote"],
                "title": ev["title"],
                "url": ev["url"],
                "independence_group": ev["independence_group"],
                "found_by": ev["found_by"],
                "is_document": ev["is_document"],
            }
            for ev in c["evidence"]
        ],
    }


def story_view(state: RunState, e: Event) -> dict:
    claims = [c for c in state["claims"].values() if c["event_id"] == e["id"]]
    by_id = {d["id"]: d for d in state["documents"]}
    return {
        "event_id": e["id"],
        "rank": e["rank"],
        "headline": e["headline"],
        "standfirst": e["standfirst"],
        "reading_minutes": reading_minutes(e),
        "rubric": e["rubric"],
        "photo": None,  # photo tool not built yet; see docs/DECISIONS.md › Stories as articles for the licence rule
        "article": e["article"],
        "claims": [claim_view(c) for c in claims],
        "spectrum": e["framing"],
        "sources": [{"title": by_id[i]["source_name"], "url": by_id[i]["url"]} for i in e["document_ids"] if i in by_id],
        "needs_review": e["needs_review"],
        "review_reason": e["review_reason"],
        "critic_notes": e["critic_notes"],
        "drafts": e["drafts"],
        "trace_ref": f"runs/{state['run_id']}/events/{e['id']}",
    }


def run(state: RunState) -> dict:
    stories = sorted((e for e in state["events"] if e["above_bar"]), key=lambda e: e["rank"] or 0)
    with step(state, "publish", model=llm.model_name()) as s:
        payload = {
            "topic_id": state["topic_id"],
            "edition_date": state["edition_date"],
            "events": len(state["events"]),
            "above_bar": len(stories),
            "needs_review": sum(1 for e in state["events"] if e["needs_review"]),
            "headlines": [e["headline"] for e in stories],
            "sources_missing": [],
        }
        try:
            summary = llm.json_task("summary", payload, dry_run=state["dry_run"]).get("summary", "")
        except Exception as exc:  # noqa: BLE001
            summary = f"{len(stories)} of {len(state['events'])} events crossed the bar today."
            s.reason = f"summary model call failed: {str(exc)[:120]}; fallback text"
        errors = state.get("errors", [])
        status = "partial" if errors else ("empty" if not stories else "ok")
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "topic_id": state["topic_id"],
            "edition_date": state["edition_date"],
            "run_id": state["run_id"],
            "version": 1,  # the store assigns the real version on insert
            "status": status,
            "bar": {"threshold": config.get("impact_bar", "threshold", 6), "confirmation_min": config.get("impact_bar", "confirmation_min", 1)},
            "summary": summary,
            "sources_missing": [],  # filled once plan can compare the sources table with the day's corpus
            "stories": [story_view(state, e) for e in stories],
            "roundup": state["roundup"] or {"empty_day": not stories, "count": 0, "groups": []},
            "errors": list(errors),
            "trace": list(state.get("steps", [])) + [],
        }
        s.decision = f"snapshot {status}: {len(stories)} stories, roundup of {snapshot['roundup']['count']}"
        s.reason = s.reason or "built from state; the store versions it"
    rec = finish(state, s)
    snapshot["trace"].append(rec)
    return {"snapshot": snapshot, "summary": summary, "steps": [rec]}
