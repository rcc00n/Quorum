"""extract_claims: atomic checkable claims per event, each tied to the document it came from.

Text is read at analysis time through tools.fetch_text and not kept; only the claim text and the origin id are.
The model's output is untrusted (it read hostile text): a claim is kept only when its origin id names a
document of this event and its words are found in that document (untrusted.grounded_in; near-match is
accepted, invented text is not), and at most CLAIMS_PER_EVENT_MAX claims are kept per event.
"""

from __future__ import annotations

from .. import ids, llm, untrusted
from ..state import Claim, RunState, StepError
from ..tools.fetch_text import fetch_text
from ..trace import finish, step

_KINDS = {"fact", "statement", "number", "context"}


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    claims: dict[str, Claim] = dict(state["claims"])
    steps, errors = [], []
    for e in state["events"]:
        with step(state, "extract_claims", event_id=e["id"], model=llm.model_name()) as s:
            payload_docs = []
            doc_texts: dict[int, str] = {}
            for did in e["document_ids"]:
                d = by_id[did]
                if d["access_level"] >= 3 and not d.get("official"):
                    continue  # level 3 is the fact of coverage only: no text, no lead, no claims from it
                text = fetch_text(d, dry_run=state["dry_run"])
                clipped = untrusted.clip(text or "", untrusted.CAP_TEXT)
                doc_texts[did] = " ".join(p for p in (d["title"], d["lead"], clipped) if p)  # ground against what the model saw
                payload_docs.append(
                    {
                        "id": d["id"],
                        "title": untrusted.clip(d["title"], untrusted.CAP_TITLE),
                        "lead": untrusted.clip(d["lead"], untrusted.CAP_LEAD),
                        "text": clipped,
                        "source": d["source_name"],
                        "official": bool(d.get("official")),
                        "doc_type": d.get("doc_type"),
                    }
                )
            n = 0
            dropped: list[dict] = []
            try:
                ans = llm.json_task("extract_claims", {"event_id": e["id"], "documents": payload_docs}, dry_run=state["dry_run"])
                for c in ans.get("claims", [])[: untrusted.CLAIMS_PER_EVENT_MAX]:
                    text_c = untrusted.clip(str(c.get("text") or "").strip(), untrusted.CAP_CLAIM)
                    origin = c.get("origin_document_id")
                    if isinstance(origin, str) and origin.isdigit():
                        origin = int(origin)
                    # model-returned ids and text are checked against the state: the origin must be a document
                    # of this event, and the claim's words must be found in it
                    if origin not in doc_texts or not untrusted.grounded_in(text_c, doc_texts[origin]):
                        dropped.append({"text": text_c, "reason": "origin not a document of this event" if origin not in doc_texts else "text not found in its origin document"})
                        continue
                    cid = ids.claim_id(e["id"], text_c)
                    if cid in claims:
                        continue
                    kind = c.get("kind", "fact")
                    claims[cid] = Claim(
                        id=cid,
                        event_id=e["id"],
                        text=text_c,
                        kind=kind if kind in _KINDS else "fact",
                        origin_document_id=origin,
                        speaker=untrusted.clip(c.get("speaker"), untrusted.CAP_SPEAKER) or None,
                        evidence=[],
                        verifier_status=None,
                        verifier_reason="",
                        fact_checker_status=None,
                        fact_checker_reason="",
                        final_status=None,
                        adjudication="",
                    )
                    n += 1
                s.decision = f"{n} claims extracted" + (f"; {len(dropped)} dropped: origin or text not found in the document" if dropped else "")
                if dropped:
                    s.detail = dropped  # kept for audit in the per-event trace (decided 2026-10-24)
                s.reason = f"from {len(payload_docs)} documents; level-2 sources contribute leads only, level-3 nothing"
            except Exception as exc:  # noqa: BLE001 — one event's extraction must not kill the run; the trace shows it
                errors.append(StepError(node="extract_claims", event_id=e["id"], message=str(exc)[:300]))
                s.decision = f"failed after {n} claims"
                s.reason = str(exc)[:200]
        steps.append(finish(state, s))
    return {"claims": claims, "steps": steps, "errors": errors}
