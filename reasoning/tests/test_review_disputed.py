"""The third blind reviewer for disagreed claims (DECISIONS.md log 2026-10-24; work item E1).

Synthetic states, dry run, no network. What is asserted is the code gate around the model's answer: the
verdict must be one of the two blind verdicts or disputed, the decisive quote must be found in the cited
evidence row, `confirmed` needs the cited chain to satisfy the confirmation rule, one pass per claim, and the
bar is re-applied after a resolution. The model's own judgment is simulated by monkeypatching `llm.json_task`.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import graph, llm
from quorum_reasoning.nodes import adjudicate, review_disputed
from quorum_reasoning.rules.impact_bar import build_rubric
from quorum_reasoning.state import Claim, DocRef, Event, Evidence, initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


def doc(doc_id: int, source: str, kind: str = "outlet") -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind=kind, flank=None, tier=None,
                  url=f"https://example.org/{source}/{doc_id}", title="t", lead="", published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None)


def ev(stance: str, group: str, found_by: str, quote: str, document: bool = False) -> Evidence:
    return Evidence(quote=quote, document_id=None if document else 2, official_doc_id=1 if document else None, source_id=group, independence_group=group,
                    stance=stance, found_by=found_by, url=f"https://example.org/{group}", title=group, is_document=document)  # type: ignore[typeddict-item]


def event(eid: str, doc_ids: list[int], rubric) -> Event:
    return Event(id=eid, document_ids=doc_ids, headline="x", standfirst="", rubric=rubric, above_bar=False, rank=None, needs_review=False,
                 article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


def claim(cid: str, eid: str, verifier: str, fact_checker: str, evidence: list[Evidence], kind: str = "fact") -> Claim:
    return Claim(id=cid, event_id=eid, text="The convoy crossed the border on Monday", kind=kind, origin_document_id=1, evidence=evidence,
                 verifier_status=verifier, verifier_reason="v", fact_checker_status=fact_checker, fact_checker_reason="f", final_status=None, adjudication="")  # type: ignore[typeddict-item]


def state_with(claims: list[Claim], rubric=None):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [doc(1, "origin-outlet"), doc(2, "reuters", "agency"), doc(3, "afp", "agency")]
    st["events"] = [event("ev1", [1, 2, 3], rubric or build_rubric(2, 2, 2, 0, {}))]
    st["claims"] = {c["id"]: c for c in claims}
    out = adjudicate.run(st)
    return {**st, **out}


SUPPORT_A = ev("supports", "reuters", "researcher", "The convoy crossed the border on Monday, Reuters reported from the scene.")
SUPPORT_B = ev("supports", "afp", "researcher", "AFP correspondents saw the convoy cross the border on Monday.")
CONTRA = ev("contradicts", "afp", "fact_checker", "The convoy did not cross the border; it turned back on Monday.")


def answer(**fields):
    base = {"verdict": "disputed", "decisive_chain": None, "decisive_index": None, "decisive_quote": "", "reason": "test"}
    base.update(fields)
    return base


def with_answer(monkeypatch, ans):
    monkeypatch.setattr(llm, "json_task", lambda task, payload, **kw: ans if task == "review_disputed" else pytest.fail(task))


# --- routing --------------------------------------------------------------------------------------------


def test_only_disagreements_are_reviewed_and_agreed_disputes_are_not():
    both_disputed = claim("c1", "ev1", "disputed", "disputed", [SUPPORT_A, CONTRA])
    agreed = claim("c2", "ev1", "unverified", "unverified", [])
    disagreed = claim("c3", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])
    st = state_with([both_disputed, agreed, disagreed])
    assert [c["id"] for c in review_disputed.pending(st)] == ["c3"]
    assert adjudicate.route(st) == "review_disputed"
    st_none = state_with([both_disputed, agreed])
    assert adjudicate.route(st_none) in ("escalate", "frame")


# --- the gate -------------------------------------------------------------------------------------------


def test_reviewer_sides_with_the_verifier_when_the_quote_is_found(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])
    with_answer(monkeypatch, answer(verdict="confirmed", decisive_chain="verifier", decisive_index=0, decisive_quote="Reuters reported from the scene"))
    out = review_disputed.run(st)
    c = out["claims"]["c1"]
    assert c["final_status"] == "confirmed" and c["reviewer_status"] == "confirmed" and c["resolved_by"] == "reviewer"
    assert c["verifier_status"] == "confirmed" and c["fact_checker_status"] == "unverified"  # both blind verdicts kept
    assert "sided with the verifier" in c["adjudication"] and c["review_passes"] == 1
    assert [s["decision"] for s in out["steps"] if s["event_id"] == "ev1"] == ["sided with the verifier: confirmed"]
    e = out["events"][0]
    assert e["above_bar"] and not e["needs_review"], "a resolved claim lifts the no-confirmed-claim flag and the bar is re-applied"


def test_overturn_to_confirmed_is_blocked_when_the_cited_chain_does_not_satisfy_the_rule(monkeypatch):
    # the fact-checker's chain holds one group only (a statement-kind claim, so the origin outlet adds no group);
    # its own verdict was unverified, the verifier's chain has two groups and was confirmed
    one_group = ev("supports", "reuters", "fact_checker", "Reuters saw the convoy cross on Monday.")
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B, one_group], kind="statement")])
    with_answer(monkeypatch, answer(verdict="confirmed", decisive_chain="fact_checker", decisive_index=0, decisive_quote="saw the convoy cross on Monday"))
    out = review_disputed.run(st)
    c = out["claims"]["c1"]
    assert c["final_status"] == "disputed" and c["reviewer_status"] is None and c["resolved_by"] == "dispute"
    assert "third review invalid" in c["adjudication"] and "confirmation rule" in c["adjudication"]


def test_quote_not_found_in_the_cited_row_keeps_the_dispute(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])
    with_answer(monkeypatch, answer(verdict="confirmed", decisive_chain="verifier", decisive_index=0, decisive_quote="an invented sentence that appears nowhere"))
    c = review_disputed.run(st)["claims"]["c1"]
    assert c["final_status"] == "disputed" and c["reviewer_status"] is None
    assert "decisive quote not found" in c["adjudication"]


def test_a_third_outcome_is_rejected(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])
    with_answer(monkeypatch, answer(verdict="probably true", decisive_chain="verifier", decisive_index=0, decisive_quote="Reuters reported"))
    c = review_disputed.run(st)["claims"]["c1"]
    assert c["final_status"] == "disputed" and "not one of the two blind verdicts" in c["adjudication"]


def test_reviewer_may_keep_the_dispute(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])
    with_answer(monkeypatch, answer(verdict="disputed", reason="the two chains describe different convoys"))
    out = review_disputed.run(st)
    c = out["claims"]["c1"]
    assert c["final_status"] == "disputed" and c["reviewer_status"] == "disputed" and c["resolved_by"] == "dispute"
    assert c["reviewer_reason"] == "the two chains describe different convoys"


def test_one_pass_per_claim_never_repeated(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])
    with_answer(monkeypatch, answer(verdict="disputed"))
    out = review_disputed.run(st)
    again = {**st, **out}
    assert review_disputed.pending(again) == []
    assert adjudicate.route(again) in ("escalate", "frame")
    assert review_disputed.run(again)["steps"] == []


def test_failed_model_call_keeps_the_dispute_and_records_the_error(monkeypatch):
    st = state_with([claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])])

    def boom(task, payload, **kw):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(llm, "json_task", boom)
    out = review_disputed.run(st)
    assert out["claims"]["c1"]["final_status"] == "disputed" and out["errors"][0]["node"] == "review_disputed"


def test_reviewer_sees_chains_as_data_not_the_checkers_reasons():
    c = claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B])
    p = review_disputed.payload_for(c)
    assert set(p) == {"claim", "kind", "speaker", "verifier", "fact_checker", "allowed_verdicts"}
    assert set(p["verifier"]) == {"verdict", "evidence"} and "reason" not in str(p)
    assert sorted(p["allowed_verdicts"]) == ["confirmed", "disputed", "unverified"]
    assert p["verifier"]["evidence"][0]["quote"] == SUPPORT_A["quote"] and p["fact_checker"]["evidence"] == []


# --- dry-run twin: the fixture's disagreement is a retrieval difference -----------------------------------


def test_dry_run_twin_resolves_retrieval_differences_and_keeps_contradictions():
    from quorum_reasoning import dryrun

    retrieval = review_disputed.payload_for(claim("c1", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B]))
    ans = dryrun.review_disputed(retrieval)
    assert ans["verdict"] == "confirmed" and ans["decisive_chain"] == "verifier" and ans["decisive_quote"] == SUPPORT_A["quote"]
    contradiction = review_disputed.payload_for(claim("c2", "ev1", "confirmed", "unverified", [SUPPORT_A, SUPPORT_B, CONTRA]))
    assert dryrun.review_disputed(contradiction)["verdict"] == "disputed"


def test_snapshot_carries_all_three_verdicts():
    st = graph.run_local(TOPIC, DAY, dry_run=True)
    views = [c for s in st["snapshot"]["stories"] for c in s["claims"]]
    assert views and all({"verifier", "fact_checker", "reviewer_status", "reviewer_reason", "reviewer_quote", "resolved_by"} <= set(v) for v in views)
    reviewed = [v for v in views if v["resolved_by"] == "reviewer"]
    assert reviewed and all(v["reviewer_status"] == v["status"] and v["reviewer_quote"] for v in reviewed)
    assert all(v["resolved_by"] == "agreement" for v in views if v["verifier"] == v["fact_checker"])
