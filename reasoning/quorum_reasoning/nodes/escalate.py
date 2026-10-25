"""escalate: events that crossed the bar on points without a single confirmed claim.

They are not published as stories and not dropped: the roundup carries them as "reported, not confirmed"
with the review flag, and the trace shows why. A human can change the verdict later; the graph never
guesses its way past a zero.
"""

from __future__ import annotations

from ..state import RunState
from ..trace import finish, step


def run(state: RunState) -> dict:
    steps = []
    for e in state["events"]:
        if not (e["needs_review"] and not e["above_bar"]):
            continue
        with step(state, "escalate", event_id=e["id"]) as s:
            s.decision = "moved to the roundup as 'reported, not confirmed'; flagged for review"
            s.reason = e["review_reason"]
        steps.append(finish(state, s))
    return {"steps": steps}
