"""score_importance: per event the model reports two facts (legal_status, act_state) and judges `reach`, each with a
one-line rationale; code maps the facts to the legal_force and irreversibility points (rules/impact_bar.py).

Confirmation points are not judged here: `adjudicate` computes them from the verified claims and only then
applies the bar and the cap (rules/impact_bar.py). The three pre-evidence points are stored now so the trace shows
what the model reported before any evidence was gathered. The model's answer is untrusted: a `reach` that is not
an integer counts as 0 (build_rubric clamps the ranges), a missing or unknown fact counts as 0, numeric legal_force /
irreversibility in an old-shape answer are ignored, and a failed call scores the event 0 and records the
error — the fail-safe direction is below the bar, never above it. A reply that is not a JSON object, or carries
neither fact field, is unusable: scored as before and recorded as an error (decision at unusable_reason).
"""

from __future__ import annotations

from typing import Any

from .. import llm, untrusted
from ..rules.impact_bar import ACT_STATE_POINTS, LEGAL_STATUS_POINTS, build_rubric, fact_value
from ..state import DocRef, Rubric, RunState, StepError
from ..trace import finish, step


def _docs(state: RunState, ids_: list[int]) -> list[DocRef]:
    by_id = {d["id"]: d for d in state["documents"]}
    return [by_id[i] for i in ids_ if i in by_id]


def _point(ans: dict[str, Any], name: str) -> int:
    try:
        return int(ans.get(name, 0))
    except (TypeError, ValueError):
        return 0


def _why(ans: dict[str, Any], *keys: str) -> str:
    r = ans.get("rationale")
    if not isinstance(r, dict):
        return ""
    for k in keys:
        if r.get(k) not in (None, ""):
            return untrusted.clip(r[k], untrusted.CAP_LABEL)
    return ""


def _fact(ans: dict[str, Any], field: str, allowed: dict[str, int], *why_keys: str) -> tuple[int, str]:
    """The point mapped from a reported fact, and the rationale prefixed by that fact (or by "fact not reported")."""
    fact = fact_value(ans.get(field), allowed)
    why = _why(ans, field, *why_keys)
    head = fact if fact else "fact not reported"
    return (allowed[fact] if fact else 0), (f"{head}: {why}" if why else head)


FACT_FIELDS = ("legal_status", "act_state")


def unusable_reason(ans: Any) -> str | None:
    """Why a rubric reply cannot be scored at all, or None when it can (a reply with a fact field present but an
    unrecognised value is usable: that fact scores 0 as "fact not reported", without an error).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a reply that is not a JSON object, or has neither
    `legal_status` nor `act_state`, is recorded as a StepError ("rubric reply unusable: <reason>") so the run reads
    `partial`; the score is what it was before (0 for both facts). Why: on snapshot v5 (D5 check, 2026-10-25) event
    b80e3c63fb60's rubric reply was malformed JSON and was recorded as "fact not reported", score 0, no error, and the
    run stayed `ok`: a judged 0 and a lost answer looked the same. Owner's decision (Yelysei, 2026-10-25).
    """
    if not isinstance(ans, dict):
        return f"not a JSON object ({type(ans).__name__})"
    if not any(k in ans for k in FACT_FIELDS):
        return "no legal_status or act_state field"
    return None


def _rubric(ans: dict[str, Any]) -> Rubric:
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): legal_force and irreversibility come from the reported facts
    # only; numeric legal_force / irreversibility in the answer are ignored. Why: a free point contradicted its own
    # rationale on the 2026-10-24 run (see rules/impact_bar.py). The rationale keys stay legal_force / reach /
    # irreversibility, the shape the portal reads.
    legal, legal_why = _fact(ans, "legal_status", LEGAL_STATUS_POINTS, "legal_force")
    irr, irr_why = _fact(ans, "act_state", ACT_STATE_POINTS, "irreversibility")
    rationale = {"legal_force": legal_why, "reach": _why(ans, "reach"), "irreversibility": irr_why}
    return build_rubric(legal, _point(ans, "reach"), irr, 0, rationale)


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
                unusable = unusable_reason(ans)
                e["rubric"] = _rubric(ans) if isinstance(ans, dict) else build_rubric(0, 0, 0, 0, {})
                r = e["rubric"]
                s.decision = f"legal_force {r['legal_force']}, reach {r['reach']}, irreversibility {r['irreversibility']} (confirmation pending)"
                s.reason = "; ".join(f"{k}: {v}" for k, v in r["rationale"].items())
                if unusable:
                    errors.append(StepError(node="score_importance", event_id=e["id"], message=f"rubric reply unusable: {unusable}"))
                    s.decision += f"; rubric reply unusable: {unusable}"
            except Exception as exc:  # noqa: BLE001 — a failed score is 0 points, below the bar, never above it
                errors.append(StepError(node="score_importance", event_id=e["id"], message=str(exc)[:300]))
                e["rubric"] = build_rubric(0, 0, 0, 0, {})
                s.decision = "failed; scored 0 on all judged points"
                s.reason = str(exc)[:200]
        steps.append(finish(state, s))
    return {"events": events, "steps": steps, "errors": errors}
