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
from ..rules.confirmation import has_document_support, independent_support, origin_group
from ..rules.impact_bar import build_rubric, confirmation_points, crosses_bar, rank_and_cap
from ..state import Claim, Event, RunState
from ..trace import finish, step


def event_confirmation(claims: list[Claim], documents_by_id: dict) -> tuple[int, int]:
    """(confirmation points, number of confirmed claims) for one event. The origin outlet's group counts
    next to at least one other, same as the claim rule (DECISIONS.md log, 2026-10-24)."""
    best_groups = max((len(independent_support(c["evidence"], origin_group(c, documents_by_id))) for c in claims), default=0)
    any_document = any(has_document_support(c["evidence"]) for c in claims)
    confirmed = sum(1 for c in claims if c["final_status"] == "confirmed")
    return confirmation_points(best_groups, any_document), confirmed


NO_CONFIRMED_CLAIM = "crosses the bar on points but no claim is confirmed after all research rounds"


def score_event(e: Event, event_claims: list[Claim], by_id: dict) -> tuple[int, int]:
    """Confirmation points and the review flag for one event, from its claims' final statuses and evidence.
    Returns (points, confirmed claims). Called by `adjudicate` and again by `review_disputed`, whose resolved
    claims change the confirmed count."""
    points, confirmed = event_confirmation(event_claims, by_id)
    r = e["rubric"] or build_rubric(0, 0, 0, 0, {})
    e["rubric"] = build_rubric(r["legal_force"], r["reach"], r["irreversibility"], points, r["rationale"])
    e["rubric"]["rationale"]["confirmation"] = {
        2: "a signed document or two independent groups behind a claim",
        1: "one independent group behind the best-supported claim",
        0: "no independent support",
    }[points]
    if crosses_bar(e["rubric"]) and confirmed == 0 and event_claims:
        e["needs_review"] = True
        e["review_reason"] = NO_CONFIRMED_CLAIM
    elif e["review_reason"] == NO_CONFIRMED_CLAIM:
        e["needs_review"] = False  # a resolved claim lifted the flag this node set; other flags are not ours to clear
        e["review_reason"] = ""
    return points, confirmed


def apply_bar(events: list[Event], claims: dict[str, Claim], by_id: dict) -> list[Event]:
    """Scores every event from the current claim statuses and applies the bar and the cap. Returns the ordered events."""
    for e in events:
        score_event(e, [c for c in claims.values() if c["event_id"] == e["id"]], by_id)
    return rank_and_cap(events)


def run(state: RunState) -> dict:
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    events: list[Event] = [dict(e) for e in state["events"]]  # type: ignore[misc]
    by_id = {d["id"]: d for d in state["documents"]}
    steps = []
    for e in events:
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        with step(state, "adjudicate", event_id=e["id"]) as s:
            counts: Counter[str] = Counter()
            disagreements = 0
            for c in event_claims:
                v = c["verifier_status"] or "unverified"
                f = c["fact_checker_status"] or "unverified"
                if c.get("fact_check_skipped"):
                    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a claim of an event that cannot reach the bar
                    # keeps the verifier's verdict, says it was not double-checked, gets no `resolved_by` and is no
                    # disagreement. Why: see docs/DECISIONS.md › Selecting major news (bar gate, 2026-10-24).
                    c["final_status"] = c["verifier_status"] or "unverified"
                    c["adjudication"] = "fact-check skipped: event cannot reach the impact bar; the verifier's verdict stands, not double-checked"
                    c.pop("resolved_by", None)
                    counts[c["final_status"]] += 1
                    continue
                unavailable = c.get("fact_checker_judged") == 0 and "failed" in c.get("fact_checker_reason", "")
                if unavailable:
                    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): when the fact-checker judged no passage at all
                    # (every call failed), the claim is "not double-checked": final status `unverified`, not `disputed`,
                    # and it is not sent to the reviewer. Why: a failure is not a verdict; `disputed` would read as a
                    # contradiction and cost a reviewer call on the same failing route; `confirmed` without the blind
                    # check would break the independent-fact-checker principle. Fails toward unverified.
                    final, why = "unverified", f"not double-checked: the fact-checker judged no passage ({c['fact_checker_reason'][:80]}); the verifier said {v}"
                    c["resolved_by"] = "dispute"
                else:
                    final, why = adjudicate_rule(v, f)
                    c["resolved_by"] = "agreement" if v == f else "dispute"  # the third pass may change this to "reviewer"
                c["final_status"] = final
                c["adjudication"] = why
                counts[final] += 1
                disagreements += (v != f) and not unavailable
            points, _ = score_event(e, event_claims, by_id)
            s.decision = (
                f"{counts['confirmed']} confirmed, {counts['disputed']} disputed, {counts['unverified']} unverified; "
                f"{disagreements} disagreement(s); rubric total {e['rubric']['total']} (confirmation {points})"
            )
            s.reason = e["review_reason"] or ("above the bar" if crosses_bar(e["rubric"]) else "below the bar")
            if disagreements:
                s.reason += f"; {disagreements} disagreement(s) go to the third blind reviewer"
        steps.append(finish(state, s))
    ordered = rank_and_cap(events)
    above = [e for e in ordered if e["above_bar"]]
    with step(state, "adjudicate") as s:
        s.decision = f"{len(above)} of {len(ordered)} events above the bar; {sum(e['needs_review'] for e in ordered)} flagged for review"
        s.reason = "bar and cap from config/reasoning.toml (see docs/DECISIONS.md › Selecting major news)"
    steps.append(finish(state, s))
    return {"claims": claims, "events": ordered, "steps": steps}


def route(state: RunState) -> Literal["review_disputed", "escalate", "frame"]:
    """Disagreements go to the third blind reviewer first; the bar is re-applied there before escalate/frame."""
    from .review_disputed import pending  # local import: review_disputed imports apply_bar from this module

    if pending(state):
        return "review_disputed"
    return "escalate" if any(e["needs_review"] and not e["above_bar"] for e in state["events"]) else "frame"
