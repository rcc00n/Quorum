"""roundup: one line per event below the bar, with its sources and its evidence status.

The model writes the line from the event's headline and lead; the status label, the grouping and the order
are code. Groups are by evidence status (DECISIONS.md › Selecting major news: the roundup says what was
reported and how well it is supported, nothing more). `empty_day` is true when no story crossed the bar.
"""

from __future__ import annotations

from .. import llm, untrusted
from ..rules.confirmation import independent_support
from ..rules.writing_rules import check_text
from ..state import Claim, DocRef, Event, RunState, StepError
from ..trace import finish, step

GROUP_ORDER = ["Reported, not confirmed", "Confirmed", "Disputed", "Single source", "Statements only", "Unverified"]


def status_label(e: Event, claims: list[Claim], docs: list[DocRef]) -> str:
    """DECISIONS.md › Selecting major news names the statuses: confirmed, disputed, statements only,
    single source (plus "reported, not confirmed" for escalated events). Review 2026-10-23 (D1, D2):
    a disputed claim must show as disputed, and an event covered by one independence group is a
    single source even when no claim gathered evidence (a scoop's own text is not evidence). A wire
    reprint counts in the wire's group here too (same rule as research.evidence_from).

    Order: needs_review → "Statements only" (every claim is a statement) → "Disputed" (any disputed
    claim, statements included) → "Confirmed" (any confirmed non-statement claim) → "Single source" → "Unverified".
    An event with a disputed claim therefore shows "Disputed" even when another of its claims is confirmed."""
    if e["needs_review"]:
        return "Reported, not confirmed"
    if claims and all(c["kind"] == "statement" for c in claims):
        return "Statements only"  # confirmed that the words were said is still only statements (review finding, 2026-10-24)
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): "Disputed" is tested before "Confirmed". Why: the docstring
    # (review 2026-10-23, D1) says a disputed claim must show as disputed, but "Confirmed" came first, so on snapshot
    # v5 (D5 check, 2026-10-25) events d2b63868e7ce and b039413e13cd read "Confirmed" while holding disputed claims.
    # A disputed statement counts too (DECISIONS: "unverified" means no confirmed or disputed claim); an event made only
    # of statements is still "Statements only" above.
    if any(c["final_status"] == "disputed" for c in claims):
        return "Disputed"
    if any(c["final_status"] == "confirmed" and c["kind"] != "statement" for c in claims):
        return "Confirmed"
    groups = {(d.get("wire_origin") or "").strip().lower() or d["independence_group"] for d in docs}
    if len(groups) == 1 or any(len(independent_support(c["evidence"])) == 1 for c in claims):
        return "Single source"
    return "Unverified"


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    items = []
    errors = []
    below = [e for e in state["events"] if not e["above_bar"]]
    with step(state, "roundup", model=llm.model_name()) as s:
        for e in below:
            claims = [c for c in state["claims"].values() if c["event_id"] == e["id"]]
            docs = [by_id[i] for i in e["document_ids"] if i in by_id]
            lead = next((d["lead"] for d in docs if d["lead"]), "")
            label = status_label(e, claims, docs)
            line_source = "model"  # a raw title is only the fallback, marked so the page can tell (B10, decided 2026-10-24)
            try:
                ans = llm.json_task(
                    "roundup_line",
                    {"headline": untrusted.clip(e["headline"], untrusted.CAP_HEADLINE), "lead": untrusted.clip(lead, untrusted.CAP_LEAD), "status": label},
                    dry_run=state["dry_run"],
                )
                line = untrusted.clip(ans.get("line", ""), untrusted.CAP_LINE)
                if check_text("line", line) or not line.strip():
                    line = e["headline"].rstrip(".") + "."  # the headline is the safe fallback; the critic's rules apply here too
                    line_source = "title"
            except Exception as exc:  # noqa: BLE001
                errors.append(StepError(node="roundup", event_id=e["id"], message=str(exc)[:300]))
                line = e["headline"].rstrip(".") + "."
                line_source = "title"
            items.append(
                {
                    "event_id": e["id"],
                    "line": line,
                    "line_source": line_source,
                    "status": label.lower(),
                    "group": label,
                    "needs_review": e["needs_review"],
                    "rubric_total": e["rubric"]["total"] if e["rubric"] else 0,
                    "sources": [{"title": d["source_name"], "url": d["url"]} for d in docs],
                }
            )
        items.sort(key=lambda i: (-i["rubric_total"], i["event_id"]))
        groups = [
            {"name": name, "items": [{k: v for k, v in i.items() if k not in ("group", "rubric_total")} for i in items if i["group"] == name]}
            for name in GROUP_ORDER
        ]
        groups = [g for g in groups if g["items"]]
        empty_day = not any(e["above_bar"] for e in state["events"])
        roundup = {"empty_day": empty_day, "count": len(items), "groups": groups}
        s.decision = f"{len(items)} events in {len(groups)} group(s); empty day: {empty_day}"
        s.reason = "everything below the bar, ordered by rubric total; lines from the model, labels from code"
    return {"roundup": roundup, "steps": [finish(state, s)], "errors": errors}
