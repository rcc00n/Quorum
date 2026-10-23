"""score_importance: the model judges three rubric points per event with a one-line rationale each.

Confirmation points are not judged here: `adjudicate` computes them from the verified claims and only then
applies the bar and the cap (rules/impact_bar.py). The three judged points are stored now so the trace shows
what the model thought before any evidence was gathered.
"""

from __future__ import annotations

from .. import llm
from ..rules.impact_bar import build_rubric
from ..state import DocRef, RunState
from ..trace import finish, step


def _docs(state: RunState, ids_: list[int]) -> list[DocRef]:
    by_id = {d["id"]: d for d in state["documents"]}
    return [by_id[i] for i in ids_ if i in by_id]


def run(state: RunState) -> dict:
    events = [dict(e) for e in state["events"]]
    steps = []
    for e in events:
        with step(state, "score_importance", event_id=e["id"], model=llm.model_name()) as s:
            docs = _docs(state, e["document_ids"])
            ans = llm.json_task(
                "rubric",
                {
                    "headline": e["headline"],
                    "documents": [
                        {"id": d["id"], "title": d["title"], "lead": d["lead"], "official": bool(d.get("official")), "doc_type": d.get("doc_type")}
                        for d in docs
                    ],
                },
                dry_run=state["dry_run"],
            )
            e["rubric"] = build_rubric(
                ans.get("legal_force", 0), ans.get("reach", 0), ans.get("irreversibility", 0), 0, ans.get("rationale", {})
            )
            r = e["rubric"]
            s.decision = f"legal_force {r['legal_force']}, reach {r['reach']}, irreversibility {r['irreversibility']} (confirmation pending)"
            s.reason = "; ".join(f"{k}: {v}" for k, v in r["rationale"].items())
        steps.append(finish(state, s))
    return {"events": events, "steps": steps}
