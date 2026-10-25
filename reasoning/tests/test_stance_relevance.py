"""Relevance guards around the stance call (2026-10-25, after the D5 finding on the 2026-10-24 canonical run).

Before the call: a passage holding less than research.stance_min_overlap of the claim's tokens is not asked about
(research.relevant). After it: a `contradicts` whose `contradicted_span` is missing or not in the passage becomes
neutral (untrusted.checked_stance). Both are counted in the step decision. The model is a stub in place of
llm.json_task; documents carry text, so nothing touches the network.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import config, dryrun, llm, text, untrusted
from quorum_reasoning.nodes import fact_check, research
from quorum_reasoning.state import Claim, DocRef, Event, initial_state

CLAIM = "Russian drones struck the Kyiv power station on Tuesday night"
ON_TOPIC = "Russian drones struck the Kyiv power station on Tuesday night, officials said. More follows."
DENIAL = "Russian drones did not strike the Kyiv power station on Tuesday night. More follows."
OFF_TOPIC = "Andrew Harnik/Getty Images. The senator spoke about diesel exports at a rally in Ohio."


def doc(doc_id: int, source: str, text: str) -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{source}/{doc_id}", title="t", lead="", published_at="2026-10-21T12:00:00Z",
                  access_level=1, wire_origin=None, text=text)


def _state(documents: list[DocRef], *, dry_run: bool = False):
    st = initial_state("t", "russia-ukraine-war", "2026-10-22", dry_run=dry_run)
    st["documents"] = documents
    st["events"] = [Event(id="ev1", document_ids=[d["id"] for d in documents], headline="x", standfirst="", rubric=None, above_bar=False,
                          rank=None, needs_review=False, article=[], drafts=0, versions=[], critic_status=None, critic_notes="",
                          framing={}, review_reason="")]
    st["claims"] = {"c1": Claim(id="c1", event_id="ev1", text=CLAIM, kind="fact", origin_document_id=1, evidence=[], verifier_status=None,
                                verifier_reason="", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")}
    return st


@pytest.fixture
def live_path(monkeypatch):
    """The answering path is the model, not the stand-in: no QUORUM_DRY_RUN and a configured route (llm.is_dry_run)."""
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "route_configured", lambda: True)


def stub(reply: dict):
    calls: list[str] = []

    def json_task(task, payload, **kw):
        calls.append(payload["passage"])
        return dict(reply)

    return json_task, calls


NODES = [pytest.param(research, id="research"), pytest.param(fact_check, id="fact_check")]


# --- pre-call guard -----------------------------------------------------------------------------------------------

def test_threshold_is_configured():
    assert config.get("research", "stance_min_overlap") == 0.15


@pytest.mark.parametrize("node", NODES)
def test_a_low_overlap_passage_is_not_asked_and_is_counted(live_path, monkeypatch, node):
    json_task, calls = stub({"stance": "supports", "reason": "x"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC), doc(3, "wapo", OFF_TOPIC)]))
    assert len(calls) == 1 and calls[0].startswith("Russian drones")
    assert [ev["document_id"] for ev in out["claims"]["c1"]["evidence"]] == [2]
    assert "; 1 passages below relevance" in out["steps"][0]["decision"]


def test_relevant_reads_the_threshold(monkeypatch):
    assert research.relevant(CLAIM, ON_TOPIC)
    assert not research.relevant(CLAIM, "A mayor spoke in Kyiv.")  # 1 of 9 tokens
    monkeypatch.setattr(config, "get", lambda section, key, default=None: 0.0 if key == "stance_min_overlap" else default)
    assert research.relevant(CLAIM, "A mayor spoke in Kyiv.")


# --- post-call guard ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("node", NODES)
def test_a_grounded_contradiction_stays(live_path, monkeypatch, node):
    json_task, _ = stub({"stance": "contradicts", "reason": "x", "contradicted_span": "Russian  drones DID NOT strike the Kyiv power station"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", DENIAL)]))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == ["contradicts"]
    assert "ungrounded" not in out["steps"][0]["decision"]


@pytest.mark.parametrize("node", NODES)
@pytest.mark.parametrize("span", [None, "", "the station was untouched", 42, "More follows", "night"], ids=["missing", "empty", "not-in-passage", "not-a-string", "off-claim", "one-word"])
def test_an_ungrounded_contradiction_becomes_neutral_and_is_counted(live_path, monkeypatch, node, span):
    reply = {"stance": "contradicts", "reason": "x"} | ({} if span is None else {"contradicted_span": span})
    json_task, calls = stub(reply)
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", DENIAL), doc(3, "reuters", DENIAL)]))  # one source twice: one question
    assert len(calls) == 1, "the downgraded answer is what a repeated question reuses"
    assert out["claims"]["c1"]["evidence"] == []
    assert "; 1 contradictions ungrounded" in out["steps"][0]["decision"]


@pytest.mark.parametrize("stance", ["supports", "statement"])
def test_supports_and_statement_need_no_span(live_path, monkeypatch, stance):
    json_task, _ = stub({"stance": stance, "reason": "x"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == [stance]
    assert "ungrounded" not in out["steps"][0]["decision"]


def _c(span, passage=DENIAL, claim=CLAIM, **kw):
    return untrusted.checked_stance({"stance": "contradicts", "contradicted_span": span}, passage, claim, **kw)


def test_checked_stance_unit():
    assert untrusted.checked_stance({"stance": "supports"}, "anything", CLAIM) == ("supports", False)
    assert untrusted.checked_stance({"stance": "bogus"}, "anything", CLAIM) == ("neutral", False)
    assert untrusted.checked_stance(None, "anything", CLAIM) == ("neutral", False)
    assert _c("“did not strike the Kyiv power station”") == ("contradicts", False)
    assert _c("did not strike") == ("neutral", True), "strike vs struck: no shared stem (irregular verbs are a known gap)"
    assert _c("...", "Yes... no.") == ("neutral", True)
    assert untrusted.checked_stance({"stance": "contradicts"}, DENIAL, CLAIM) == ("neutral", True)
    assert untrusted.checked_stance({"stance": "contradicts"}, DENIAL, CLAIM, require_span=False) == ("contradicts", False)
    # require_span=False exempts only a missing span; a span the reply does give is still checked
    assert _c("invented words", require_span=False) == ("neutral", True)


def test_span_is_a_whole_word_run():
    assert not untrusted.span_in("war", "A warning was issued.")
    assert not untrusted.span_in("ties", "The casualties rose.")
    assert not untrusted.span_in("drones did strike", DENIAL)  # words present, not as a contiguous run
    assert untrusted.span_in("did not strike the Kyiv power station", DENIAL)
    assert untrusted.span_in("Russian drones did not strike the Kyiv power station on Tuesday night.", DENIAL)


@pytest.mark.parametrize("span, passage", [
    ("it’s false", "He said it's false."),
    ("“no strike”", 'He said "no strike" on Tuesday.'),
    ("«no strike»", 'He said "no strike" on Tuesday.'),
    ("Kyiv—Odesa strike", "The Kyiv-Odesa strike did not happen."),
    ("Kyiv – Odesa strike", "The Kyiv - Odesa strike did not happen."),
    ("no strike...", "There was no strike… officials said."),
    ("NO   STRIKE,", "there was no strike"),
], ids=["apostrophe", "curly-quotes", "guillemets", "em-dash", "en-dash", "ellipsis", "case-space-punct"])
def test_span_typography_variants_match(span, passage):
    assert untrusted.span_in(span, passage)


def test_span_must_have_two_words_and_touch_the_claim():
    assert _c("did not strike the Kyiv power station") == ("contradicts", False)
    assert _c("drones did not strike") == ("contradicts", False)  # shares the stem drone
    assert _c("night") == ("neutral", True), "one word, even a claim word"
    assert _c("More follows") == ("neutral", True), "grounded, two words, nothing of the claim"
    assert _c("Getty Images", "Andrew Harnik/Getty Images") == ("neutral", True)
    assert _c("killed 31", "Officials said 5 were killed 31 wounded.", "The strike killed 31 people") == ("contradicts", False), "short words count"


# --- the dry-run stand-in -----------------------------------------------------------------------------------------

def test_dry_run_stand_in_still_parses_and_keeps_its_contradictions():
    ans = dryrun.stance({"claim": CLAIM, "passage": DENIAL, "role": "researcher", "source_kind": "outlet"})
    assert ans["stance"] == "contradicts" and "contradicted_span" not in ans
    assert untrusted.checked_stance(ans, DENIAL, CLAIM, require_span=False) == ("contradicts", False)


def test_dry_run_node_keeps_the_stand_in_contradiction():
    out = research.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", DENIAL)], dry_run=True))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == ["contradicts"]


def test_stand_in_forced_by_the_environment_keeps_its_contradiction(monkeypatch):
    """--model dry sets QUORUM_DRY_RUN=1 (run.py); a state built with dry_run=False is still answered by the stand-in
    (llm.is_dry_run), so the span exemption follows the answering path, not the state flag."""
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    out = research.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", DENIAL)], dry_run=False))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == ["contradicts"]


def test_no_route_means_stand_in_and_keeps_its_contradiction(monkeypatch):
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "route_configured", lambda: False)
    out = fact_check.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", DENIAL)], dry_run=False))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == ["contradicts"]


# --- newline is a sentence boundary (text.sentences) --------------------------------------------------------------

CAPTION_TEXT = "Andrew Harnik/Getty Images\n\nMeanwhile, Russian drones struck the Kyiv power station on Tuesday night. The U.S. Senate met."


def test_a_caption_line_is_its_own_sentence():
    assert text.sentences("Andrew Harnik/Getty Images\n\nMeanwhile, Ukraine said the strike hit Kyiv.") == [
        "Andrew Harnik/Getty Images", "Meanwhile, Ukraine said the strike hit Kyiv."]
    assert text.sentences("One line \r\n  \n second line. Lt. Gen. Smith spoke. U.S. Senate.") == [
        "One line", "second line.", "Lt. Gen. Smith spoke.", "U.S. Senate."]  # abbreviations still do not end a sentence


def test_best_passage_drops_the_caption():
    assert text.best_passage(CLAIM, CAPTION_TEXT) == "Meanwhile, Russian drones struck the Kyiv power station on Tuesday night."


def test_clip_sentences_stays_verbatim_across_a_newline():
    src = "First sentence here.\n\nSecond sentence here. Third " + "word " * 80
    assert text.clip_sentences(src, 60) == "First sentence here.\n\nSecond sentence here."
    assert text.clip_sentences(src, 60) in src



@pytest.mark.parametrize("node", NODES)
def test_quote_after_the_split_is_found_at_its_offsets(live_path, monkeypatch, node):
    json_task, _ = stub({"stance": "supports", "reason": "x"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", CAPTION_TEXT)]))
    (ev,) = out["claims"]["c1"]["evidence"]
    assert ev["quote"] == "Meanwhile, Russian drones struck the Kyiv power station on Tuesday night."
    assert CAPTION_TEXT[ev["char_start"]:ev["char_end"]] == ev["quote"]
