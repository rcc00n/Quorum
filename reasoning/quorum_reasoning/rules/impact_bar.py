"""Impact bar (DECISIONS.md › Selecting major news). `reach` is judged by the model; legal force and irreversibility are
mapped here from facts the model reports; confirmation, the sum, the gate and the cap are code."""

from __future__ import annotations

from .. import config
from ..state import Event, Rubric

POINT_RANGES = {"legal_force": (0, 2), "reach": (0, 3), "irreversibility": (0, 2), "confirmation": (0, 2)}


# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the model reports closed-set facts (legal_status, act_state) and
# these tables map them to the legal_force and irreversibility points; an unknown or missing fact scores 0. Why: on the
# 2026-10-24 run a model-judged irreversibility of 1 contradicted its own rationale ("conditional and reversible", 0)
# and put the day's only story exactly at the threshold; a fact is checkable, a free point is not. Failing toward 0
# keeps an unreadable answer below the bar, never above it.
LEGAL_STATUS_POINTS = {"none": 0, "statement_or_proposal": 1, "adopted_or_ruled": 2}
ACT_STATE_POINTS = {"announced_or_threatened": 0, "adopted_reversible": 1, "executed_irreversible": 2}


def fact_value(value: object, allowed: dict[str, int]) -> str | None:
    """The closed-set fact as reported (case and surrounding spaces ignored), or None when it is missing or not in the set."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in allowed else None


def legal_force_points(legal_status: object) -> int:
    v = fact_value(legal_status, LEGAL_STATUS_POINTS)
    return LEGAL_STATUS_POINTS[v] if v else 0


def irreversibility_points(act_state: object) -> int:
    v = fact_value(act_state, ACT_STATE_POINTS)
    return ACT_STATE_POINTS[v] if v else 0


def clamp_points(name: str, value: int) -> int:
    lo, hi = POINT_RANGES[name]
    return max(lo, min(hi, int(value)))


def build_rubric(legal_force: int, reach: int, irreversibility: int, confirmation: int, rationale: dict[str, str]) -> Rubric:
    r = Rubric(
        legal_force=clamp_points("legal_force", legal_force),
        reach=clamp_points("reach", reach),
        irreversibility=clamp_points("irreversibility", irreversibility),
        confirmation=clamp_points("confirmation", confirmation),
        total=0,
        rationale=dict(rationale),
    )
    r["total"] = r["legal_force"] + r["reach"] + r["irreversibility"] + r["confirmation"]
    return r


def confirmation_points(independent_groups: int, has_document: bool) -> int:
    if has_document or independent_groups >= 2:
        return 2
    if independent_groups == 1:
        return 1
    return 0


def crosses_bar(rubric: Rubric) -> bool:
    return rubric["total"] >= config.get("impact_bar", "threshold", 6) and rubric["confirmation"] >= config.get(
        "impact_bar", "confirmation_min", 1
    )


def threshold() -> int:
    return int(config.get("impact_bar", "threshold", 6))


def judged_points(rubric: Rubric) -> int:
    """The three points the model judges before any evidence (everything but confirmation)."""
    return rubric["legal_force"] + rubric["reach"] + rubric["irreversibility"]


def cannot_reach_bar(rubric: Rubric | None) -> bool:
    """True when the judged points plus the best possible confirmation score still fall short of the threshold:
    the event cannot become a story whatever the evidence shows (DECISIONS.md › Selecting major news, bar gate).
    No rubric means no score yet, and an unscored event is never gated."""
    if not rubric:
        return False
    return judged_points(rubric) + POINT_RANGES["confirmation"][1] < threshold()


def rank_and_cap(events: list[Event]) -> list[Event]:
    """Marks `above_bar` and `rank`. Up to cap_per_day stories; no minimum. Returns the events, ordered."""
    cap = config.get("impact_bar", "cap_per_day", 10)
    ordered = sorted(
        events,
        key=lambda e: (-(e["rubric"]["total"] if e["rubric"] else -1), -(e["rubric"]["confirmation"] if e["rubric"] else -1), e["id"]),
    )
    rank = 0
    for e in ordered:
        if e["rubric"] and crosses_bar(e["rubric"]) and rank < cap and not e["needs_review"]:
            rank += 1
            e["above_bar"] = True
            e["rank"] = rank
        else:
            e["above_bar"] = False
            e["rank"] = None
    return ordered
