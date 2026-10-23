"""Impact bar (DECISIONS.md › Selecting major news). Points are judged by the model; the sum, the gate and the cap are code."""

from __future__ import annotations

from .. import config
from ..state import Event, Rubric

POINT_RANGES = {"legal_force": (0, 2), "reach": (0, 3), "irreversibility": (0, 2), "confirmation": (0, 2)}


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
