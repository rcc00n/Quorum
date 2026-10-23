"""score_importance: the model judges three rubric points per event with a one-line rationale each.

Confirmation points are not judged here: `adjudicate` computes them from the verified claims and only then
applies the bar and the cap (rules/impact_bar.py). The three judged points are stored now so the trace shows
what the model thought before any evidence was gathered. The model's answer is untrusted: points that are
not integers count as 0 (build_rubric clamps the ranges), a failed call scores the event 0 and records the
error — the fail-safe direction is below the bar, never above it.
"""

from __future__ import annotations

from typing import Any

from .. import llm, untrusted
from ..rules.impact_bar import build_rubric
from ..state import DocRef, RunState, StepError
from ..trace import finish, step


def _docs(state: RunState, ids_: list[int]) -> list[DocRef]:
    by_id = {d["id"]: d for d in state["documents"]}
    return [by_id[i] for i in ids_ if i in by_id]


def _point(ans: dict[str, Any], name: str) -> int:
    try:
        return int(ans.get(name, 0))
    except (TypeError, ValueError):
        return 0


def _rationale(ans: dict[str, Any]) -> dict[str, str]:
    r = ans.get("rationale")
    if not isinstance(r, dict):
        return {}
    return {str(k): untrusted.clip(v, untrusted.CAP_LABEL) for k, v in r.items()}


def run(state: RunState) -> dict:
    events = [dict(e) for e in state["events"]]
    steps, errors = [], []
    for e in events:
        with step(state, "score_importance", event_id=e["id"], model=llm.model_name()) as s:
            docs = _docs(state, e["document_ids"])
            try:
                ans = llm.json_task(
                    "rubric",
                    {
                        "headline": untrusted.clip(e["headline"], untrusted.CAP_HEADLINE),
                        "documents": [
                            {
                                "id": d["id"],
                                "title": untrusted.clip(d["title"], untrusted.CAP_TITLE),
                                "lead": untrusted.clip(d["lead"], untrusted.CAP_LEAD),
                                "official": bool(d.get("official")),
                                "doc_type": d.get("doc_type"),
                            }
                            for d in docs
                        ],
                    },
                    dry_run=state["dry_run"],
                )
                e["rubric"] = build_rubric(_point(ans, "legal_force"), _point(ans, "reach"), _point(ans, "irreversibility"), 0, _rationale(ans))
                r = e["rubric"]
                s.decision = f"legal_force {r['legal_force']}, reach {r['reach']}, irreversibility {r['irreversibility']} (confirmation pending)"
                s.reason = "; ".join(f"{k}: {v}" for k, v in r["rationale"].items())
            except Exception as exc:  # noqa: BLE001 — a failed score is 0 points, below the bar, never above it
                errors.append(StepError(node="score_importance", event_id=e["id"], message=str(exc)[:300]))
                e["rubric"] = build_rubric(0, 0, 0, 0, {})
                s.decision = "failed; scored 0 on all judged points"
                s.reason = str(exc)[:200]
        steps.append(finish(state, s))
    return {"events": events, "steps": steps, "errors": errors}
