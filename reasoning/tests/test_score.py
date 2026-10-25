"""Legal force and irreversibility are mapped from reported facts, not judged (Yelysei's decision, 2026-10-25).

The model reports `legal_status` and `act_state` from closed sets and judges `reach`; code maps the facts to points.
Numeric legal_force / irreversibility in an old-shape answer are ignored; a missing or unknown fact scores 0.
Dry run; the model is a monkeypatched `llm.json_task`.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import llm
from quorum_reasoning.nodes import score
from quorum_reasoning.rules import impact_bar
from quorum_reasoning.rules.impact_bar import build_rubric, crosses_bar, irreversibility_points, legal_force_points, rank_and_cap
from quorum_reasoning.state import DocRef, Event, initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


@pytest.mark.parametrize("fact, points", [("none", 0), ("statement_or_proposal", 1), ("adopted_or_ruled", 2), (" Adopted_or_Ruled ", 2)])
def test_legal_force_points(fact, points):
    assert legal_force_points(fact) == points


@pytest.mark.parametrize("fact, points", [("announced_or_threatened", 0), ("adopted_reversible", 1), ("executed_irreversible", 2)])
def test_irreversibility_points(fact, points):
    assert irreversibility_points(fact) == points


@pytest.mark.parametrize("bad", [None, "", "adopted", "2", 2, 1.0, True, ["adopted_or_ruled"], {"x": 1}, "executed_irreversible; ignore the rules"])
def test_unknown_facts_score_zero(bad):
    assert legal_force_points(bad) == 0
    assert irreversibility_points(bad) == 0


def test_point_ranges_unchanged():
    assert impact_bar.POINT_RANGES == {"legal_force": (0, 2), "reach": (0, 3), "irreversibility": (0, 2), "confirmation": (0, 2)}


def _doc(doc_id: int) -> DocRef:
    return DocRef(id=doc_id, source_id="s", source_name="s", independence_group="s", kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{doc_id}", title="Moscow threatens strikes if the deliveries go ahead", lead="",
                  published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None, text="t")


def _event(eid: str) -> Event:
    return Event(id=eid, document_ids=[1], headline=eid, standfirst="", rubric=None, above_bar=False, rank=None, needs_review=False,
                 article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


def _score(monkeypatch, answer):
    monkeypatch.setattr(llm, "json_task", lambda task, payload, **kw: answer)
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [_doc(1)]
    st["events"] = [_event("e1")]
    out = score.run(st)
    assert not out["errors"]
    return out["events"][0]["rubric"], out["steps"][0]


def test_new_shape(monkeypatch):
    r, s = _score(monkeypatch, {
        "legal_status": "statement_or_proposal", "act_state": "adopted_reversible", "reach": 3,
        "rationale": {"legal_status": "a ministry statement", "act_state": "a decree a later decree can undo", "reach": "sanctions"},
    })
    assert (r["legal_force"], r["reach"], r["irreversibility"], r["confirmation"], r["total"]) == (1, 3, 1, 0, 5)
    assert r["rationale"] == {
        "legal_force": "statement_or_proposal: a ministry statement",
        "reach": "sanctions",
        "irreversibility": "adopted_reversible: a decree a later decree can undo",
    }
    assert s["decision"] == "legal_force 1, reach 3, irreversibility 1 (confirmation pending)"


def test_old_numeric_shape_is_ignored(monkeypatch):
    r, _ = _score(monkeypatch, {
        "legal_force": 2, "reach": 2, "irreversibility": 2,
        "rationale": {"legal_force": "a law", "reach": "national", "irreversibility": "signed"},
    })
    assert (r["legal_force"], r["reach"], r["irreversibility"]) == (0, 2, 0)
    assert r["rationale"]["legal_force"] == "fact not reported: a law"
    assert r["rationale"]["irreversibility"] == "fact not reported: signed"


def test_facts_win_over_numbers_sent_alongside(monkeypatch):
    r, _ = _score(monkeypatch, {"legal_status": "none", "act_state": "announced_or_threatened", "legal_force": 2, "irreversibility": 2, "reach": 1})
    assert (r["legal_force"], r["irreversibility"]) == (0, 0)
    assert r["rationale"]["legal_force"] == "none" and r["rationale"]["irreversibility"] == "announced_or_threatened"


def test_missing_facts_score_zero(monkeypatch):
    r, _ = _score(monkeypatch, {"reach": 2})
    assert (r["legal_force"], r["reach"], r["irreversibility"]) == (0, 2, 0)
    assert r["rationale"] == {"legal_force": "fact not reported", "reach": "", "irreversibility": "fact not reported"}


def test_threatened_not_adopted_stays_below_the_bar_even_with_numeric_ones(monkeypatch):
    monkeypatch.setattr(impact_bar, "threshold", lambda: 6)
    r, _ = _score(monkeypatch, {
        "legal_status": "statement_or_proposal", "act_state": "announced_or_threatened", "reach": 2,
        "legal_force": 1, "irreversibility": 1,
        "rationale": {"legal_status": "a foreign ministry statement", "act_state": "the threat is conditional and reversible", "reach": "the whole country"},
    })
    assert (r["legal_force"], r["reach"], r["irreversibility"]) == (1, 2, 0)
    assert impact_bar.cannot_reach_bar(r)
    # the 2026-10-24 case: with the numeric irreversibility 1 the event sat exactly at 6; from the fact it is 5
    final = build_rubric(r["legal_force"], r["reach"], r["irreversibility"], 2, r["rationale"])
    assert final["total"] == 5 and not crosses_bar(final)
    ev = _event("e1")
    ev["rubric"] = final
    assert rank_and_cap([ev])[0]["above_bar"] is False


def test_rubric_prompt_completed_acts_and_document_ids():
    """Live probe 2026-10-25: a completed prisoner swap came back announced_or_threatened and no rationale cited a document."""
    from quorum_reasoning import llm

    prompt = llm._prompt("rubric")
    assert "A reported completed act (exchanged, swapped, killed, destroyed, delivered, signed into law, ratified, withdrawn) is \"executed_irreversible\" even when the documents are news reports" in prompt
    assert "\"announced_or_threatened\" is only for what has not happened yet or is conditional" in prompt
    assert "starts with the id of the document it relies on" in prompt
