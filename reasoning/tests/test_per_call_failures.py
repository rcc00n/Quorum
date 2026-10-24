"""A failed model call in research or fact_check skips one passage, never the event (decided 2026-10-24 after the
first genuine run, where one HTTP 429 per event marked 155 of 189 claims "fact-checker failed").

Dry run; the model is simulated by a json_task that raises on chosen calls.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import llm
from quorum_reasoning.nodes import fact_check, research
from quorum_reasoning.state import Claim, DocRef, Event, initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"
TEXT = "The Senate passed the aid bill 68-30 on Tuesday. More follows here."


def doc(doc_id: int, source: str) -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{source}/{doc_id}", title="Aid bill passed", lead="", published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None, text=TEXT)


def event(eid: str, doc_ids: list[int]) -> Event:
    return Event(id=eid, document_ids=doc_ids, headline="x", standfirst="", rubric=None, above_bar=False, rank=None, needs_review=False,
                 article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


def claim(cid: str, eid: str, origin: int) -> Claim:
    return Claim(id=cid, event_id=eid, text="The Senate passed the aid bill 68-30 on Tuesday", kind="number", origin_document_id=origin, evidence=[],
                 verifier_status=None, verifier_reason="", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")


def flaky(fail_on: set[int]):
    calls = {"n": 0}

    def json_task(task, payload, **kw):
        calls["n"] += 1
        if calls["n"] in fail_on:
            raise RuntimeError("Error code: 429 - Too Many Requests")
        return {"stance": "supports", "reason": "test"}

    return json_task, calls


def _state():
    st = initial_state("t", TOPIC, DAY, dry_run=False)
    st["documents"] = [doc(1, "cnn"), doc(2, "reuters"), doc(3, "afp"), doc(4, "npr")]
    st["events"] = [event("ev1", [1, 2, 3, 4])]
    st["claims"] = {"c1": claim("c1", "ev1", 1), "c2": claim("c2", "ev1", 1)}
    return st


def test_fact_check_keeps_going_after_a_failed_call(monkeypatch):
    monkeypatch.setattr(llm, "is_dry_run", lambda flag: False)
    json_task, calls = flaky({2})  # the second stance call of the event fails
    monkeypatch.setattr(llm, "json_task", json_task)
    st = _state()
    out = fact_check.run(st)
    c1, c2 = out["claims"]["c1"], out["claims"]["c2"]
    assert calls["n"] == 6, "every candidate passage was still asked (3 per claim)"
    assert c1["fact_checker_status"] == "confirmed" and c2["fact_checker_status"] == "confirmed"
    assert "1 stance call(s) failed for this claim" in c1["fact_checker_reason"] and "failed" not in c2["fact_checker_reason"]
    assert len(out["errors"]) == 1 and out["errors"][0]["node"] == "fact_check" and "429" in out["errors"][0]["message"]
    assert "1 stance calls failed" in out["steps"][0]["decision"]
    assert not any("fact-checker failed; treated as unverified" in c["fact_checker_reason"] for c in out["claims"].values())


def test_research_keeps_going_after_a_failed_call(monkeypatch):
    monkeypatch.setattr(llm, "is_dry_run", lambda flag: False)
    json_task, calls = flaky({1, 3})
    monkeypatch.setattr(llm, "json_task", json_task)
    st = _state()
    out = research.run(st)
    assert calls["n"] == 6
    rows = [ev for c in out["claims"].values() for ev in c["evidence"]]
    assert len(rows) == 4, "the four successful calls became evidence; the two failed passages were skipped"
    assert len(out["errors"]) == 1 and "2 stance call(s) failed" in out["errors"][0]["message"]
    assert out["research_rounds"]["ev1"] == 1 and "2 stance calls failed" in out["steps"][0]["decision"]


def test_all_calls_failing_leaves_unverified_with_the_count_not_a_blanket_label(monkeypatch):
    monkeypatch.setattr(llm, "is_dry_run", lambda flag: False)
    json_task, _ = flaky(set(range(1, 100)))
    monkeypatch.setattr(llm, "json_task", json_task)
    out = fact_check.run(_state())
    for c in out["claims"].values():
        assert c["fact_checker_status"] == "unverified" and "3 stance call(s) failed for this claim" in c["fact_checker_reason"]
    assert len(out["errors"]) == 1 and "6 stance call(s) failed" in out["errors"][0]["message"]
