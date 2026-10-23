"""extract_claims: atomic checkable claims per event, each tied to the document it came from.

Text is read at analysis time through tools.fetch_text and not kept; only the claim text and the origin id are.
"""

from __future__ import annotations

from .. import ids, llm
from ..state import Claim, RunState
from ..tools.fetch_text import fetch_text
from ..trace import finish, step


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    claims: dict[str, Claim] = dict(state["claims"])
    steps = []
    for e in state["events"]:
        with step(state, "extract_claims", event_id=e["id"], model=llm.model_name()) as s:
            payload_docs = []
            for did in e["document_ids"]:
                d = by_id[did]
                text = fetch_text(d, dry_run=state["dry_run"])
                payload_docs.append(
                    {
                        "id": d["id"],
                        "title": d["title"],
                        "lead": d["lead"],
                        "text": (text or "")[:4000],
                        "source": d["source_name"],
                        "official": bool(d.get("official")),
                        "doc_type": d.get("doc_type"),
                    }
                )
            ans = llm.json_task("extract_claims", {"event_id": e["id"], "documents": payload_docs}, dry_run=state["dry_run"])
            n = 0
            for c in ans.get("claims", []):
                cid = ids.claim_id(e["id"], c["text"])
                if cid in claims:
                    continue
                claims[cid] = Claim(
                    id=cid,
                    event_id=e["id"],
                    text=c["text"].strip(),
                    kind=c.get("kind", "fact"),
                    origin_document_id=c.get("origin_document_id"),
                    speaker=c.get("speaker"),
                    evidence=[],
                    verifier_status=None,
                    verifier_reason="",
                    fact_checker_status=None,
                    fact_checker_reason="",
                    final_status=None,
                    adjudication="",
                )
                n += 1
            s.decision = f"{n} claims extracted"
            s.reason = f"from {len(payload_docs)} documents; level-2 sources contribute leads only, level-3 nothing"
        steps.append(finish(state, s))
    return {"claims": claims, "steps": steps}
