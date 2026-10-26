"""frame: how each outlet frames a story above the bar, plus cohort coverage counts.

The model labels one outlet's document at a time (highlights, omits, wording, interpretation label). Cohort
shares are counted in code from the day's corpus: for each cohort, how many of its sources covered the event
out of how many published anything on the topic today. Cohorts follow DECISIONS.md › Spectrum ratings and
cohorts: major/minor × left/right, plus center; agencies and official sources are not a cohort. The model's
labels are untrusted free text built from untrusted titles and leads: they are bounded before they reach the
snapshot.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .. import llm, untrusted
from ..state import DocRef, RunState, StepError
from ..trace import finish, step
from ..tools import memory

COHORTS = ("major_left", "minor_left", "major_right", "minor_right", "center")


def cohort_of(doc: DocRef) -> str | None:
    if doc["kind"] != "outlet":
        return None
    flank, tier = doc.get("flank"), doc.get("tier")
    if flank in ("left", "right"):
        return f"{tier or 'minor'}_{flank}"
    return "center"


def coverage(all_docs: list[DocRef], event_doc_ids: list[int]) -> dict[str, list[int]]:
    """{cohort: [sources that covered the event, sources of that cohort active today]}"""
    active: dict[str, set[str]] = defaultdict(set)
    covered: dict[str, set[str]] = defaultdict(set)
    members = set(event_doc_ids)
    for d in all_docs:
        c = cohort_of(d)
        if c is None or d.get("from_previous_day") or d.get("superseded"):
            continue  # an earlier day's publication is evidence, not today's coverage; a superseded version is its chain's newest row
        active[c].add(d["source_id"])
        if d["id"] in members:
            covered[c].add(d["source_id"])
    return {c: [len(covered[c]), len(active[c])] for c in COHORTS}


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    events = [dict(e) for e in state["events"]]
    steps, errors = [], []
    for e in events:
        if not e["above_bar"]:
            continue
        with step(state, "frame", event_id=e["id"], model=llm.model_name()) as s:
            outlets = []
            failed: list[str] = []
            try:
                for did in e["document_ids"]:
                    d = by_id[did]
                    if cohort_of(d) is None:
                        continue
                    try:
                        ans = llm.json_task(
                            "frame",
                            {
                                "documents": [{"title": untrusted.clip(d["title"], untrusted.CAP_TITLE), "lead": untrusted.clip(d["lead"], untrusted.CAP_LEAD)}],
                                "source": d["source_name"],
                                "flank": d.get("flank"),
                                "tier": d.get("tier"),
                            },
                            dry_run=state["dry_run"],
                        )
                    except Exception as exc:  # noqa: BLE001 — one outlet unlabelled, the others keep their labels
                        failed.append(f"{d['source_name']}: {untrusted.public_failure(exc)}")
                        continue
                    if not isinstance(ans, dict):
                        failed.append(f"{d['source_name']}: no object")
                        continue
                    outlets.append(
                        {
                            "source": d["source_name"],
                            "cohort": cohort_of(d),
                            "flank": d.get("flank") or "center",
                            "url": d["url"],
                            "highlights": untrusted.clip(ans.get("highlights", ""), untrusted.CAP_LABEL),
                            "omits": untrusted.clip(ans.get("omits", ""), untrusted.CAP_LABEL),
                            "wording": untrusted.clip(ans.get("wording", ""), untrusted.CAP_LABEL),
                            "interpretation_label": untrusted.clip(ans.get("interpretation_label", ""), untrusted.CAP_LABEL),
                        }
                    )
                labels: Counter[str] = Counter(o["interpretation_label"] for o in outlets if o["interpretation_label"])
                by_label_flank: dict[str, Counter[str]] = defaultdict(Counter)
                for o in outlets:
                    by_label_flank[o["interpretation_label"]][o["flank"]] += 1
                # both sides are always present (ARCHITECTURE § 8; the portal parser requires them on a completed frame):
                # a flank no outlet covered is empty strings, which is itself the finding
                sides = {flank: {"highlights": "", "omits": "", "wording": "", "example_url": ""} for flank in ("left", "right")}
                for flank in ("left", "right"):
                    side = [o for o in outlets if o["flank"] == flank]
                    side.sort(key=lambda o: 0 if o["cohort"].startswith("major") else 1)
                    if side:
                        sides[flank] = {k: side[0][k] for k in ("highlights", "omits", "wording")} | {"example_url": side[0]["url"]}
                e["framing"] = {
                    "rating_mode": "average",  # the flank on each source row is the averaged rating; other modes need the sources table
                    **sides,
                    "note": "",
                    "coverage": coverage(state["documents"], e["document_ids"]),
                    "interpretations": [
                        {"label": label, "outlets": n, "mostly": by_label_flank[label].most_common(1)[0][0]} for label, n in labels.most_common()
                    ],
                    "outlets": outlets,
                }
                s.decision = f"{len(outlets)} outlets labelled; {len(labels)} interpretation(s)" + (f"; {len(failed)} outlet call(s) failed" if failed else "")
                s.reason = "labels per outlet from the model; cohort shares counted in code" + (f"; failures: {failed[0]}" if failed else "")
                if failed:
                    errors.append(StepError(node="frame", event_id=e["id"], message=f"{len(failed)} outlet framing call(s) failed: {failed[0]}"))
            except Exception as exc:  # noqa: BLE001
                errors.append(StepError(node="frame", event_id=e["id"], message=str(exc)[:300]))
                e["framing"] = {"rating_mode": "average", "coverage": coverage(state["documents"], e["document_ids"]), "interpretations": [], "outlets": outlets}
                s.decision = "failed; coverage counts only"
                s.reason = untrusted.public_failure(exc)
        steps.append(finish(state, s))
    memory_steps, memory_errors = memory.remember(state | {"steps": state.get("steps", []) + steps}, events)
    return {"events": events, "steps": steps + memory_steps, "errors": errors + memory_errors}
