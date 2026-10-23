"""research: find supporting and contradicting passages for each claim.

Round 1 searches the event's own documents. Round 2 (requested by `verify` for thin claims) widens to every
document of the day and all official documents. Stance per passage is a model judgment; which passages
exist, which groups they belong to and how many rounds run are code. The model's stance answer is untrusted:
only the four allowed stance words are accepted, anything else counts as neutral (untrusted.valid_stance).
"""

from __future__ import annotations

from .. import config, llm, untrusted
from ..rules.confirmation import DOCUMENT_TYPES_THAT_ESTABLISH, is_thin
from ..state import Claim, DocRef, Evidence, RunState, StepError
from ..text import best_passage, clip_sentences
from ..tools.corpus import OFFICIAL_ID_OFFSET
from ..tools.fetch_text import fetch_text
from ..trace import finish, step


def already_seen(claim: Claim, doc: DocRef, found_by: str) -> bool:
    key = "official_doc_id" if doc.get("official") else "document_id"
    return any(ev[key] == doc["id"] and ev["found_by"] == found_by for ev in claim["evidence"])


def evidence_from(doc: DocRef, passage: str, stance: str, found_by: str) -> Evidence:
    is_doc = bool(doc.get("official")) and doc.get("doc_type") in DOCUMENT_TYPES_THAT_ESTABLISH
    if doc.get("official") and not is_doc and stance == "supports":
        stance = "statement"  # an official release is the party's words, not evidence for them
    # A reprint carries the wire's independence group: ten reprints of one wire story are one piece of
    # evidence (DECISIONS.md › Principles for handling facts). wire_origin is 'AP'/'Reuters'/'AFP' in
    # collectors/schema.sql; independence groups are lower-case slugs.
    group = (doc.get("wire_origin") or "").strip().lower() or doc["independence_group"]
    # Official ids are namespaced above OFFICIAL_ID_OFFSET (tools/corpus.py); the evidence row keeps the
    # database id so analysis.evidence rows point at real official_docs rows.
    db_id = doc["id"] - OFFICIAL_ID_OFFSET if doc.get("official") and doc["id"] >= OFFICIAL_ID_OFFSET else doc["id"]
    return Evidence(
        quote=clip_sentences(passage, 300),
        document_id=None if doc.get("official") else doc["id"],
        official_doc_id=db_id if doc.get("official") else None,
        independence_group=group,
        stance=stance,  # type: ignore[typeddict-item]
        found_by=found_by,
        url=doc["url"],
        title=doc["source_name"],
        is_document=is_doc,
    )


def _candidates(state: RunState, event_doc_ids: list[int], round_no: int) -> list[DocRef]:
    docs = state["documents"]
    if round_no <= 1:
        return [d for d in docs if d["id"] in event_doc_ids]
    return [d for d in docs if d["id"] not in event_doc_ids]  # round 2: the rest of the day, official documents included


def run(state: RunState) -> dict:
    max_rounds = config.get("loops", "research_rounds_max", 2)
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    rounds = dict(state["research_rounds"])
    steps, errors = [], []
    for e in state["events"]:
        used = rounds.get(e["id"], 0)
        if used >= max_rounds:
            continue
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        if not event_claims:
            continue
        if used >= 1 and not any(is_thin(c["evidence"]) for c in event_claims):
            continue  # nothing thin: no second round for this event
        round_no = used + 1
        targets = event_claims if round_no == 1 else [c for c in event_claims if is_thin(c["evidence"])]
        with step(state, "research", event_id=e["id"], model=llm.model_name()) as s:
            found = 0
            try:
                for c in targets:
                    for d in _candidates(state, e["document_ids"], round_no):
                        if d["id"] == c["origin_document_id"] and not d.get("official"):
                            continue  # a claim does not confirm itself; a signed document does confirm what it says
                        if already_seen(c, d, "researcher"):
                            continue
                        passage = best_passage(c["text"], fetch_text(d, dry_run=state["dry_run"]) or "")
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
                                "role": "researcher",
                            },
                            dry_run=state["dry_run"],
                        )
                        stance = untrusted.valid_stance(ans.get("stance"))
                        if stance == "neutral":
                            continue
                        c["evidence"] = c["evidence"] + [evidence_from(d, passage, stance, "researcher")]
                        found += 1
                s.decision = f"round {round_no}: {found} passages with a stance for {len(targets)} claims"
                s.reason = "event documents only" if round_no == 1 else "widened to the rest of the day and official documents for thin claims"
            except Exception as exc:  # noqa: BLE001 — a failed source must not kill the run; the trace shows it
                errors.append(StepError(node="research", event_id=e["id"], message=str(exc)[:300]))
                s.decision = f"round {round_no}: failed after {found} passages"
                s.reason = str(exc)[:200]
            rounds[e["id"]] = round_no
        steps.append(finish(state, s))
    return {"claims": claims, "research_rounds": rounds, "steps": steps, "errors": errors}
