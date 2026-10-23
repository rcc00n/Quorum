"""write: the article for every story above the bar, from verified claims only.

The writer gets four lists and nothing else: confirmed facts (with their sources), context, statements
(with who said them) and open items (with why they are open). It returns headline, standfirst and the
blocks of DECISIONS.md › Stories as articles. On a second or third draft it also gets the previous draft and
the critic's notes and is told to fix only those. Every draft is kept in `versions`.
"""

from __future__ import annotations

from .. import config, llm
from ..state import Claim, Event, RunState, StepError
from ..trace import finish, step


def claim_sources(c: Claim) -> list[dict]:
    """Sources shown after a sentence: supporting evidence, signed documents first, one per independence group."""
    seen: set[str] = set()
    out = []
    for ev in sorted(c["evidence"], key=lambda ev: (not ev["is_document"], ev["found_by"] != "researcher")):
        if ev["stance"] != "supports" or ev["independence_group"] in seen:
            continue
        seen.add(ev["independence_group"])
        out.append({"title": ev["title"], "url": ev["url"], "quote": ev["quote"]})
    return out


def payload_for(e: Event, claims: list[Claim], documents_by_id: dict) -> dict:
    confirmed, context, statements, open_items = [], [], [], []
    for c in claims:
        origin = documents_by_id.get(c["origin_document_id"])
        if c["kind"] == "statement":
            statements.append(
                {
                    "id": c["id"],
                    "text": c["text"],
                    "who": c.get("speaker") or (origin["source_name"] if origin else "The source"),
                    "status": c["final_status"],
                    "sources": [{"title": origin["source_name"], "url": origin["url"]}] if origin else [],
                }
            )
        elif c["final_status"] == "confirmed":
            (context if c["kind"] == "context" else confirmed).append({"id": c["id"], "text": c["text"], "sources": claim_sources(c)})
        else:
            open_items.append({"id": c["id"], "text": c["text"], "status": c["final_status"], "why": c["adjudication"] if c["final_status"] == "disputed" else c["verifier_reason"]})
    return {
        "draft": e["drafts"] + 1,
        "headline": e["headline"],
        "confirmed": confirmed,
        "context": context,
        "statements": statements,
        "not_confirmed": open_items,
        "previous": e["versions"][-1] if e["versions"] else None,
        "critic_notes": e["critic_notes"],
        "reading_minutes_max": config.get("writing", "reading_minutes_max", 4),
    }


def needs_draft(e: Event) -> bool:
    return e["above_bar"] and e["critic_status"] != "approved" and e["drafts"] < config.get("loops", "drafts_max", 3)


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    events = [dict(e) for e in state["events"]]
    steps, errors = [], []
    for e in events:
        if not needs_draft(e):
            continue
        claims = [c for c in state["claims"].values() if c["event_id"] == e["id"]]
        with step(state, "write", event_id=e["id"], model=llm.model_name()) as s:
            payload = payload_for(e, claims, by_id)
            try:
                ans = llm.json_task("write", payload, dry_run=state["dry_run"])
                e["headline"] = ans.get("headline") or e["headline"]
                e["standfirst"] = ans.get("standfirst", "")
                e["article"] = ans.get("blocks", [])
                e["drafts"] += 1
                e["critic_status"] = None
                e["versions"] = e["versions"] + [
                    {"draft": e["drafts"], "headline": e["headline"], "standfirst": e["standfirst"], "blocks": e["article"], "critic_status": None, "critic_notes": ""}
                ]
                s.decision = f"draft {e['drafts']}: {len(e['article'])} blocks from {len(payload['confirmed'])} confirmed, {len(payload['statements'])} statements, {len(payload['not_confirmed'])} open"
                s.reason = "first draft" if e["drafts"] == 1 else f"rewrite after the critic: {e['versions'][-2]['critic_notes'][:120]}"
            except Exception as exc:  # noqa: BLE001
                errors.append(StepError(node="write", event_id=e["id"], message=str(exc)[:300]))
                e["drafts"] += 1
                e["critic_status"] = None
                s.decision = f"draft {e['drafts']} failed"
                s.reason = str(exc)[:200]
        steps.append(finish(state, s))
    return {"events": events, "steps": steps, "errors": errors}
