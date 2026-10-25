"""Stance prompt split and repeated-question dedupe (2026-10-24, after two live runs).

The official-document paragraph lives only in prompts/stance_document.md and is used only for an official law,
order, vote or ruling (research.stance_task); within one node run for one event an identical stance question is
asked once (research.stance_question). Dry run; the model is a recorder in place of llm.json_task.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quorum_reasoning import dryrun, llm
from quorum_reasoning.nodes import adjudicate, fact_check, research
from quorum_reasoning.rules.confirmation import independent_support
from quorum_reasoning.state import Claim, DocRef, Event, initial_state
from quorum_reasoning.tools.corpus import OFFICIAL_ID_OFFSET

PROMPTS = Path(research.__file__).resolve().parent.parent / "prompts"
PARAGRAPH = "When `source_kind` is `official` and `doc_type` is `law`, `order`, `vote` or `ruling`"
TOPIC, DAY = "russia-ukraine-war", "2026-10-22"
TEXT = "The Senate passed the aid bill 68-30 on Tuesday. More follows here."
CLAIM = "The Senate passed the aid bill 68-30 on Tuesday"


def doc(doc_id: int, source: str, *, kind: str = "outlet", official: bool = False, doc_type: str | None = None, text: str = TEXT) -> DocRef:
    d = DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind=kind, flank=None, tier=None,
               url=f"https://example.org/{source}/{doc_id}", title="Aid bill passed", lead="", published_at="2026-10-21T12:00:00Z",
               access_level=1, wire_origin=None, text=text)
    if official:
        d["official"], d["doc_type"] = True, doc_type
    return d


def event(eid: str, doc_ids: list[int]) -> Event:
    return Event(id=eid, document_ids=doc_ids, headline="x", standfirst="", rubric=None, above_bar=False, rank=None, needs_review=False,
                 article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


def claim(cid: str, eid: str, origin: int, text: str = CLAIM) -> Claim:
    return Claim(id=cid, event_id=eid, text=text, kind="number", origin_document_id=origin, evidence=[],
                 verifier_status=None, verifier_reason="", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")


def recorder(answer: str | None = None):
    """A json_task that records (task, source) and answers `answer`, or delegates to the dry-run twin of the task."""
    calls: list[tuple[str, str]] = []

    def json_task(task, payload, **kw):
        calls.append((task, payload["source"]))
        return {"stance": answer, "reason": "test"} if answer else getattr(dryrun, task)(payload)

    return json_task, calls


def _state(documents: list[DocRef], claims: list[Claim], event_doc_ids: list[int]):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = documents
    st["events"] = [event("ev1", event_doc_ids)]
    st["claims"] = {c["id"]: c for c in claims}
    return st


# --- the prompt files ---------------------------------------------------------------------------------------------

def test_paragraph_only_in_the_document_prompt_and_otherwise_identical():
    plain = (PROMPTS / "stance.md").read_text(encoding="utf-8")
    document = (PROMPTS / "stance_document.md").read_text(encoding="utf-8")
    assert plain.count(PARAGRAPH) == 0
    assert document.count(PARAGRAPH) == 1
    assert "is their words too: answer `statement`, not `contradicts`." in document  # the denial sentence moved with it
    lines = document.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(PARAGRAPH))
    assert lines[i + 1] == ""
    assert "\n".join(lines[:i] + lines[i + 2:]) == "\n".join(plain.splitlines())


def test_prompt_is_loaded_by_task_name():
    assert llm._prompt("stance_document") == (PROMPTS / "stance_document.md").read_text(encoding="utf-8")
    assert dryrun.stance_document is dryrun.stance


# --- the task choice ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", ["law", "order", "vote", "ruling"])
def test_official_document_types_get_the_document_prompt(doc_type):
    assert research.stance_task(doc(OFFICIAL_ID_OFFSET + 1, "congress-gov", kind="official", official=True, doc_type=doc_type)) == "stance_document"


@pytest.mark.parametrize("d", [
    doc(OFFICIAL_ID_OFFSET + 2, "whitehouse", kind="official", official=True, doc_type="release"),
    doc(OFFICIAL_ID_OFFSET + 3, "whitehouse", kind="official", official=True, doc_type="statement"),
    doc(4, "cnn"),
    doc(5, "cnn", doc_type="law"),  # a doc_type on a non-official row does not count
])
def test_everything_else_gets_the_plain_prompt(d):
    assert research.stance_task(d) == "stance"


def test_research_issues_the_document_prompt_only_for_an_official_law(monkeypatch):
    law = doc(OFFICIAL_ID_OFFSET + 10, "congress-gov", kind="official", official=True, doc_type="law")
    release = doc(OFFICIAL_ID_OFFSET + 11, "whitehouse", kind="official", official=True, doc_type="release")
    origin, outlet = doc(1, "origin"), doc(2, "reuters")
    json_task, calls = recorder()
    monkeypatch.setattr(llm, "json_task", json_task)
    research.run(_state([law, release, origin, outlet], [claim("c1", "ev1", 1)], [law["id"], release["id"], 1, 2]))
    assert len(calls) == 3
    assert dict((src, task) for task, src in calls) == {"congress-gov": "stance_document", "whitehouse": "stance", "reuters": "stance"}


def test_fact_check_issues_the_document_prompt_only_for_an_official_law(monkeypatch):
    law = doc(OFFICIAL_ID_OFFSET + 10, "congress-gov", kind="official", official=True, doc_type="law")
    release = doc(OFFICIAL_ID_OFFSET + 11, "whitehouse", kind="official", official=True, doc_type="release")
    json_task, calls = recorder()
    monkeypatch.setattr(llm, "json_task", json_task)
    fact_check.run(_state([law, release, doc(1, "origin"), doc(2, "reuters")], [claim("c1", "ev1", 1)], [1, 2]))
    assert len(calls) == 3
    assert dict((src, task) for task, src in calls) == {"congress-gov": "stance_document", "whitehouse": "stance", "reuters": "stance"}


# --- repeated questions -------------------------------------------------------------------------------------------

def _same_source_twice():
    # two documents of one source yield the same passage; the claim's origin is a third source (excluded from its own pool)
    return [doc(1, "origin"), doc(2, "cnn"), doc(3, "cnn")]


def test_research_asks_a_repeated_question_once_and_keeps_a_row_per_document(monkeypatch):
    json_task, calls = recorder("supports")
    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state(_same_source_twice(), [claim("c1", "ev1", 1)], [1, 2, 3]))
    rows = out["claims"]["c1"]["evidence"]
    assert len(calls) == 1
    assert sorted(ev["document_id"] for ev in rows) == [2, 3] and {ev["stance"] for ev in rows} == {"supports"}
    assert independent_support(rows) == {"cnn"}, "the same source and passage count once"
    assert "(1 repeated questions skipped)" in out["steps"][0]["decision"]


def test_fact_check_asks_a_repeated_question_once(monkeypatch):
    json_task, calls = recorder("supports")
    monkeypatch.setattr(llm, "json_task", json_task)
    out = fact_check.run(_state(_same_source_twice(), [claim("c1", "ev1", 1)], [1, 2, 3]))
    c = out["claims"]["c1"]
    assert len(calls) == 1 and len(c["evidence"]) == 2
    assert c["fact_checker_judged"] == 2, "a reused answer is a judgement the fact-checker made"
    assert "(1 repeated questions skipped)" in out["steps"][0]["decision"]


def test_a_repeated_neutral_answer_is_skipped_silently(monkeypatch):
    json_task, calls = recorder("neutral")
    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state(_same_source_twice(), [claim("c1", "ev1", 1)], [1, 2, 3]))
    assert len(calls) == 1 and out["claims"]["c1"]["evidence"] == []


def test_two_claims_with_identical_text_share_one_question(monkeypatch):
    json_task, calls = recorder("supports")
    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state([doc(1, "origin"), doc(2, "cnn")], [claim("c1", "ev1", 1), claim("c2", "ev1", 1)], [1, 2]))
    assert len(calls) == 1
    assert all(len(out["claims"][cid]["evidence"]) == 1 for cid in ("c1", "c2"))


def test_a_different_source_or_doc_type_is_a_different_question(monkeypatch):
    json_task, calls = recorder("supports")
    monkeypatch.setattr(llm, "json_task", json_task)
    docs = [doc(1, "origin"), doc(2, "cnn"), doc(3, "reuters"),
            doc(OFFICIAL_ID_OFFSET + 4, "congress-gov", kind="official", official=True, doc_type="law"),
            doc(OFFICIAL_ID_OFFSET + 5, "congress-gov", kind="official", official=True, doc_type="release")]
    research.run(_state(docs, [claim("c1", "ev1", 1)], [d["id"] for d in docs]))
    assert len(calls) == 4


def test_a_failed_question_is_asked_again(monkeypatch):
    calls = {"n": 0}

    def json_task(task, payload, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Error code: 429 - Too Many Requests")
        return {"stance": "supports", "reason": "test"}

    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state(_same_source_twice(), [claim("c1", "ev1", 1)], [1, 2, 3]))
    assert calls["n"] == 2 and len(out["claims"]["c1"]["evidence"]) == 1


def test_a_claim_answered_from_the_cache_with_one_failure_is_still_double_checked(monkeypatch):
    """Skeptic probe: two identical claims, calls 1 and 4 fail. c2's only own call (the re-asked failed question)
    fails again and its other two answers come from the cache; it must not read as "not double-checked"."""
    calls = {"n": 0}

    def json_task(task, payload, **kw):
        calls["n"] += 1
        if calls["n"] in (1, 4):
            raise RuntimeError("Error code: 429 - Too Many Requests")
        return {"stance": "supports", "reason": "test"}

    monkeypatch.setattr(llm, "json_task", json_task)
    docs = [doc(1, "origin"), doc(2, "cnn"), doc(3, "reuters"), doc(4, "afp")]
    st = _state(docs, [claim("c1", "ev1", 1), claim("c2", "ev1", 1)], [1, 2, 3, 4])
    out = fact_check.run(st)
    assert calls["n"] == 4
    c2 = out["claims"]["c2"]
    assert len(c2["evidence"]) == 2 and c2["fact_checker_status"] == "confirmed" and c2["fact_checker_judged"] == 2
    for c in out["claims"].values():
        c["verifier_status"] = "confirmed"
    st["claims"] = out["claims"]
    final = adjudicate.run(st)["claims"]["c2"]
    assert final["final_status"] == "confirmed"
    assert "not double-checked" not in final["adjudication"]
