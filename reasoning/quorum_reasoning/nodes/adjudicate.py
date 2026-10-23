"""adjudicate: final status per claim, confirmation points per event, then the bar and the cap. No model call.

Two blind verdicts per claim: agreement is final, disagreement is shown as disputed. The event's
confirmation points come from its best-supported claim (2 for a document or two independent groups, 1 for
one group, 0 otherwise). An event that crosses the bar on points but has no confirmed claim at all is not a
story: it is flagged for review and routed to `escalate`, which hands it to the roundup.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from ..rules.confirmation import adjudicate as adjudicate_rule
from ..rules.confirmation import has_document_support, independent_support
from ..rules.impact_bar import build_rubric, confirmation_points, crosses_bar, rank_and_cap
from ..state import Claim, Event, RunState
from ..trace import finish, step


def event_confirmation(claims: list[Claim]) -> tuple[int, int]:
    """(confirmation points, number of confirmed claims) for one event."""
    best_groups = max((len(independent_support(c["evidence"])) for c in claims), default=0)
    any_document = any(has_document_support(c["evidence"]) for c in claims)
    confirmed = sum(1 for c in claims if c["final_status"] == "confirmed")
    return confirmation_points(best_groups, any_document), confirmed


def run(state: RunState) -> dict:
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    events: list[Event] = [dict(e) for e in state["events"]]  # type: ignore[misc]
    steps = []
    for e in events:
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        with step(state, "adjudicate", event_id=e["id"]) as s:
            counts: Counter[str] = Counter()
            disagreements = 0
            for c in event_claims:
                v = c["verifier_status"] or "unverified"
                f = c["fact_checker_status"] or "unverified"
                final, why = adjudicate_rule(v, f)
                c["final_status"] = final
                c["adjudication"] = why
                counts[final] += 1
                disagreements += v != f
            points, confirmed = event_confirmation(event_claims)
            r = e["rubric"] or build_rubric(0, 0, 0, 0, {})
            e["rubric"] = build_rubric(r["legal_force"], r["reach"], r["irreversibility"], points, r["rationale"])
            e["rubric"]["rationale"]["confirmation"] = {
                2: "a signed document or two independent groups behind a claim",
                1: "one independent group behind the best-supported claim",
                0: "no independent support",
            }[points]
            if crosses_bar(e["rubric"]) and confirmed == 0 and event_claims:
                e["needs_review"] = True
                e["review_reason"] = "crosses the bar on points but no claim is confirmed after all research rounds"
            s.decision = (
                f"{counts['confirmed']} confirmed, {counts['disputed']} disputed, {counts['unverified']} unverified; "
                f"{disagreements} disagreement(s); rubric total {e['rubric']['total']} (confirmation {points})"
            )
            s.reason = e["review_reason"] or ("above the bar" if crosses_bar(e["rubric"]) else "below the bar")
        steps.append(finish(state, s))
    ordered = rank_and_cap(events)
    above = [e for e in ordered if e["above_bar"]]
    with step(state, "adjudicate") as s:
        s.decision = f"{len(above)} of {len(ordered)} events above the bar; {sum(e['needs_review'] for e in ordered)} flagged for review"
        s.reason = "bar and cap from config/reasoning.toml (see docs/DECISIONS.md › Selecting major news)"
    steps.append(finish(state, s))
    return {"claims": claims, "events": ordered, "steps": steps}


def route(state: RunState) -> Literal["escalate", "frame"]:
    return "escalate" if any(e["needs_review"] and not e["above_bar"] for e in state["events"]) else "frame"
