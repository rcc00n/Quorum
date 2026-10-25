"""verify: the confirmation rule applied to the researcher's evidence. No model call.

Sets `verifier_status` per claim and decides whether the graph loops back to `research`: it does when any
claim of an event is still thin (no document, fewer than two independent groups) and that event has a
research round left. The loop is bounded by loops.research_rounds_max in config/reasoning.toml.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from .. import config
from ..rules.confirmation import is_thin, origin_group, verdict
from ..state import Claim, RunState
from ..trace import finish, iteration_of, step


def own_evidence(claim: Claim) -> list:
    """What the verifier is allowed to see: the researcher's and its own findings, never the fact-checker's."""
    return [ev for ev in claim["evidence"] if ev["found_by"] in ("researcher", "verifier")]


def thin_events(state: RunState) -> list[str]:
    """Events with at least one thin claim and a research round left."""
    max_rounds = config.get("loops", "research_rounds_max", 2)
    by_id = {d["id"]: d for d in state["documents"]}
    out = []
    for e in state["events"]:
        if state["research_rounds"].get(e["id"], 0) >= max_rounds:
            continue
        claims = [c for c in state["claims"].values() if c["event_id"] == e["id"]]
        if any(is_thin(own_evidence(c), origin_group(c, by_id)) for c in claims):
            out.append(e["id"])
    return out


def run(state: RunState) -> dict:
    max_rounds = config.get("loops", "research_rounds_max", 2)
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    by_id = {d["id"]: d for d in state["documents"]}
    steps = []
    for e in state["events"]:
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        if not event_claims:
            continue
        used = state["research_rounds"].get(e["id"], 0)
        if used < iteration_of(state, "verify", e["id"]):
            continue  # nothing new was researched for this event since its last verdict
        with step(state, "verify", event_id=e["id"]) as s:
            counts: Counter[str] = Counter()
            thin = 0
            for c in event_claims:
                origin = origin_group(c, by_id)
                status, reason = verdict(own_evidence(c), origin)
                c["verifier_status"] = status
                c["verifier_reason"] = reason
                counts[status] += 1
                thin += is_thin(own_evidence(c), origin)
            s.decision = f"{counts['confirmed']} confirmed, {counts['disputed']} disputed, {counts['unverified']} unverified; {thin} thin"
            if thin and used < max_rounds:
                s.reason = f"thin claims and {max_rounds - used} research round(s) left: back to research"
            elif thin:
                s.reason = "thin claims but the research budget is spent: on to the fact-checker"
            else:
                s.reason = "every claim has a document or two independent groups: on to the fact-checker"
        steps.append(finish(state, s))
    return {"claims": claims, "steps": steps}


def route(state: RunState) -> Literal["research", "fact_check"]:
    return "research" if thin_events(state) else "fact_check"
