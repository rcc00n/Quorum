"""fact_check: a blind second verdict per claim.

The fact-checker sees the claim texts and the corpus, nothing the researcher or the verifier produced. It
has the same access to the documents (same levels, same robots rules), picks its own passages, asks the
model for stance under its own prompt (prompts/stance.md, role fact_checker: look for reasons the claim could
be wrong) and applies the same confirmation rule to its own evidence. Its evidence rows carry
found_by="fact_checker" so the snapshot shows both chains side by side. Route "fact_checker" in
config/reasoning.toml may point at a different provider when the rules allow. The model's stance answer is
untrusted: only the four allowed stance words are accepted, anything else counts as neutral.
"""

from __future__ import annotations

from collections import Counter

from .. import llm, untrusted
from ..rules.confirmation import origin_group, verdict
from ..state import RunState, StepError
from ..text import best_passage
from ..tools.fetch_text import fetch_result
from ..trace import finish, step
from .research import already_seen, evidence_from, rank_candidates


def run(state: RunState) -> dict:
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    docs = [d for d in state["documents"] if not d.get("superseded")]  # retracted text is not evidence
    by_id = {d["id"]: d for d in state["documents"]}
    steps, errors = [], []
    for e in state["events"]:
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        if not event_claims:
            continue
        with step(state, "fact_check", event_id=e["id"], model=llm.model_name("fact_checker")) as s:
            counts: Counter[str] = Counter()
            found = 0
            try:
                for c in event_claims:
                    pool = [d for d in docs if not (d["id"] == c["origin_document_id"] and not d.get("official")) and not already_seen(c, d, "fact_checker")]
                    # the fact-checker has the researcher's access to the whole corpus; the same code ranking bounds its calls
                    for d in rank_candidates(c["text"], pool, dry_run=state["dry_run"]):
                        fetched = fetch_result(d, dry_run=state["dry_run"])
                        passage = best_passage(c["text"], (fetched.text if fetched else None) or "")
                        if not passage:
                            continue
                        ans = llm.json_task(
                            "stance",
                            {
                                "claim": untrusted.clip(c["text"], untrusted.CAP_CLAIM),
                                "passage": untrusted.clip(passage, untrusted.CAP_PASSAGE),
                                "source": d["source_name"],
                                "source_kind": d["kind"],
                                "doc_type": d.get("doc_type"),
                                "role": "fact_checker",
                            },
                            dry_run=state["dry_run"],
                            which="fact_checker",
                        )
                        stance = untrusted.valid_stance(ans.get("stance"))
                        if stance == "neutral":
                            continue
                        c["evidence"] = c["evidence"] + [evidence_from(d, passage, stance, "fact_checker", fetched)]
                        found += 1
                    own = [ev for ev in c["evidence"] if ev["found_by"] == "fact_checker"]
                    status, reason = verdict(own, origin_group(c, by_id))
                    c["fact_checker_status"] = status
                    c["fact_checker_reason"] = reason
                    counts[status] += 1
                s.decision = f"{counts['confirmed']} confirmed, {counts['disputed']} disputed, {counts['unverified']} unverified from {found} own passages"
                s.reason = "blind: own passages and own stance calls, nothing from the researcher or the verifier"
            except Exception as exc:  # noqa: BLE001
                errors.append(StepError(node="fact_check", event_id=e["id"], message=str(exc)[:300]))
                for c in event_claims:
                    if c["fact_checker_status"] is None:
                        c["fact_checker_status"] = "unverified"
                        c["fact_checker_reason"] = "fact-checker failed; treated as unverified"
                s.decision = "failed; unchecked claims treated as unverified"
                s.reason = str(exc)[:200]
        steps.append(finish(state, s))
    return {"claims": claims, "steps": steps, "errors": errors}
