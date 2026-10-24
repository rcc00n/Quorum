"""critique: the writing rules applied to the latest draft. Rule-based; no model call in this version.

Approves, or rejects with the violations (block, rule, offending text) that the writer must fix and nothing
more. The loop back to `write` is bounded by loops.drafts_max: a story still rejected at the last draft is
published with the critic's notes attached and `needs_review` set. It is not dropped and not approved.
"""

from __future__ import annotations

from typing import Literal

from .. import config
from ..rules.writing_rules import check_article, check_text
from ..state import Event, RunState
from ..trace import finish, step


def sanitise_article(blocks: list, claims: dict) -> list:
    """The article as it may be published when the writer's last draft is still rejected (flagged `needs_review`).

    DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a story published with the critic's notes attached keeps its
    text, but no sentence is presented as a fact without a confirmed claim behind it: unknown or foreign claim ids are
    dropped everywhere; a `fact`/`context` block whose ids are not all confirmed non-statement claims becomes a
    `not_confirmed` block (its sources dropped); blocks of unknown kind are dropped; the fixed order is restored.
    Why: ARCHITECTURE § 5 says such a story is published flagged, not dropped; § 6 says a fact block contains only
    confirmed claims, and the portal's parser rejects the whole edition otherwise (review finding, 2026-10-24).
    """
    order = ["fact", "context", "statements", "not_confirmed"]
    out = []
    for b in blocks:
        if b.get("kind") not in order:
            continue
        ids = [cid for cid in b.get("claim_ids", []) if cid in claims]
        kind = b["kind"]
        sources = b.get("sources", [])
        if kind in ("fact", "context") and (not ids or any(claims[cid]["final_status"] != "confirmed" or claims[cid].get("kind") == "statement" for cid in ids)):
            kind, sources = "not_confirmed", []
        out.append({**b, "kind": kind, "claim_ids": ids, "sources": sources})
    return sorted(out, key=lambda b: order.index(b["kind"]))


def pending(e: Event) -> bool:
    return e["above_bar"] and e["drafts"] > 0 and e["critic_status"] is None


def run(state: RunState) -> dict:
    drafts_max = config.get("loops", "drafts_max", 3)
    events = [dict(e) for e in state["events"]]
    steps = []
    for e in events:
        if not pending(e):
            continue
        with step(state, "critique", event_id=e["id"]) as s:
            own = {cid: c for cid, c in state["claims"].items() if c["event_id"] == e["id"]}  # a block may cite this event's claims only
            violations = check_text("headline", e["headline"]) + check_text("standfirst", e["standfirst"]) + check_article(e["article"], own)
            if not e["article"]:
                violations.append("article: no blocks")
            e["critic_status"] = "approved" if not violations else "rejected"
            e["critic_notes"] = "" if not violations else "; ".join(violations)
            if e["versions"]:
                e["versions"][-1] = {**e["versions"][-1], "critic_status": e["critic_status"], "critic_notes": e["critic_notes"]}
            if violations and e["drafts"] >= drafts_max:
                e["needs_review"] = True
                e["review_reason"] = f"draft {e['drafts']} still rejected: {e['critic_notes'][:200]}"
                e["article"] = sanitise_article(e["article"], own)
            s.decision = f"draft {e['drafts']} {e['critic_status']}" + (f": {len(violations)} violation(s)" if violations else "")
            if not violations:
                s.reason = "order, attribution, sourcing and wording rules all hold"
            elif e["drafts"] >= drafts_max:
                s.reason = f"{violations[0]}; drafts exhausted, published with notes and flagged for review"
            else:
                s.reason = f"{violations[0]}; back to the writer"
        steps.append(finish(state, s))
    return {"events": events, "steps": steps}


def route(state: RunState) -> Literal["write", "roundup"]:
    drafts_max = config.get("loops", "drafts_max", 3)
    for e in state["events"]:
        if e["above_bar"] and e["critic_status"] == "rejected" and e["drafts"] < drafts_max:
            return "write"
    return "roundup"
