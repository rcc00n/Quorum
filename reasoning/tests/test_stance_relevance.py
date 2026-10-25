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
    json_task, calls = stub({"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
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


@pytest.mark.parametrize("stance", ["statement"])
def test_statement_needs_no_span(live_path, monkeypatch, stance):
    json_task, _ = stub({"stance": stance, "reason": "x"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = research.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]))
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == [stance]
    assert "ungrounded" not in out["steps"][0]["decision"]


def _c(span, passage=DENIAL, claim=CLAIM, **kw):
    return untrusted.checked_stance({"stance": "contradicts", "contradicted_span": span}, passage, claim, **kw)


def test_checked_stance_unit():
    assert untrusted.checked_stance({"stance": "supports"}, "anything", CLAIM) == ("neutral", True)  # no supporting_span
    assert untrusted.checked_stance({"stance": "supports"}, "anything", CLAIM, require_span=False) == ("supports", False)  # stand-in
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


TROOPS = "Russia withdrew troops from Kherson on Monday"
TROOPS_DENIAL = "Officials said Russia did not withdraw troops from Kherson, a procedural step only, the ministry added."


@pytest.mark.parametrize("span, passage, claim, kept", [
    ("killed 31", "Officials said 5 were killed 31 wounded.", "The strike killed 31 people", True),
    ("did not withdraw troops", TROOPS_DENIAL, TROOPS, True),
    ("didn't withdraw troops", "Russia didn't withdraw troops.", TROOPS, True),
    ("troops left on Sunday", "The troops left on Sunday, officials said.", TROOPS, True),
    ("Trump said Tuesday", "Trump said Tuesday that talks go on.", "Zelensky met Macron in Paris", False),
    ("a procedural step only", TROOPS_DENIAL, TROOPS, False),
    ("Russia did withdraw some troops", "Russia did withdraw some troops, not all.", TROOPS, True),
    ("the talks ended in Geneva today", "Officials said the talks ended in Geneva today.", TROOPS, False),
    ("Getty Images", "Andrew Harnik/Getty Images", CLAIM, False),
    ("No", "No, the troops stayed.", TROOPS, False),
    ("night", DENIAL, CLAIM, False),
    ("More follows", DENIAL, CLAIM, False),
], ids=["number-2w", "negation-4w", "contraction", "weekday", "date-no-shared-stem", "4w-no-marker", "5w-clause",
        "6w-no-shared-stem", "caption", "one-word-no", "one-word-claim-word", "2w-off-claim"])
def test_span_length_rule(span, passage, claim, kept):
    assert untrusted.span_in(span, passage), "every case is grounded: only the length and claim rules decide"
    assert _c(span, passage, claim) == (("contradicts", False) if kept else ("neutral", True))


def test_span_thresholds_are_named():
    assert (untrusted.SPAN_MIN_WORDS, untrusted.SPAN_SHORT_MIN_WORDS) == (5, 2)
    assert {"not", "never", "denied"} <= untrusted.SPAN_NEGATIONS and {"tuesday", "october"} <= untrusted.SPAN_DATE_WORDS


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
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", CAPTION_TEXT)]))
    (ev,) = out["claims"]["c1"]["evidence"]
    assert ev["quote"] == "Meanwhile, Russian drones struck the Kyiv power station on Tuesday night."
    assert CAPTION_TEXT[ev["char_start"]:ev["char_end"]] == ev["quote"]


def test_may_and_march_are_not_date_markers():
    """'troops may withdraw' is a 3-word span with no number, date or negation: neutral; 'on March 3' still passes on the digit."""
    from quorum_reasoning import untrusted

    assert "may" not in untrusted.SPAN_DATE_WORDS and "march" not in untrusted.SPAN_DATE_WORDS
    passage = "Officials said troops may withdraw from Kursk on March 3 after talks."
    claim = "Soldiers will withdraw from Kursk on March 5."  # one composition stem shared (withdraw): no composition pass
    short = untrusted.checked_stance({"stance": "contradicts", "contradicted_span": "troops may withdraw"}, passage, claim)
    dated = untrusted.checked_stance({"stance": "contradicts", "contradicted_span": "on March 3"}, passage, claim)
    assert short[0] == "neutral" and dated[0] == "contradicts"


# --- fact composition and the day check (untrusted.off_fact) ------------------------------------------------------

def test_frequent_stems_top_k_and_share():
    docs = ["Trump Ukraine talks", "Trump Ukraine aid", "Trump sanctions Russia", "Trump Russia oil", "Ukraine drones"]
    assert text.frequent_stems(docs, k=2, share=0.9) == {"trump", "ukraine"}  # df 4 and 3; ties never reach k here
    assert text.frequent_stems(docs, k=0, share=0.3) == {"trump", "ukraine", "russia"}  # df/5 > 0.3
    assert text.frequent_stems(["beta alpha", "alpha beta"], k=1, share=1.0) == {"alpha"}, "ties break alphabetically"
    assert text.frequent_stems([], k=5) == set()


def test_fact_composition_and_coverage():
    frequent = {"trump"}
    claim = "Trump signed the diesel export waiver"
    assert text.fact_composition(claim, frequent) == {"sign", "diesel", "export", "waiver"}
    assert text.composition_coverage(claim, "Trump signed a waiver on diesel.", frequent) == (0.75, 3)
    assert text.composition_coverage(claim, "Trump spoke in Ohio.", frequent) == (0.0, 0)
    # everything frequent: the claim keeps its full stem set (fallback), so it stays contradictable
    assert text.composition_coverage("Trump spoke", "Trump spoke", {"trump", "spoke"}) == (1.0, 2)


def test_off_fact_coverage_and_two_stem_floor():
    frequent = {"trump"}
    claim = "Trump signed the diesel export waiver"
    assert untrusted.off_fact(claim, "Trump did not sign the diesel export waiver.", "did not sign", frequent, 0.4) is None
    assert untrusted.off_fact(claim, "Trump told Ramaswamy to keep running ads, not sign.", "not sign", frequent, 0.4) == "off-fact"
    # a one-stem claim can never reach the two-stem floor, whatever the share
    assert untrusted.off_fact("Zelensky", "Zelensky never", "Zelensky never", set(), 0.0) == "off-fact"
    # "Trump waived" minus {trump} would leave one stem: it keeps its full set and the floor is reachable
    assert untrusted.off_fact("Trump waived", "Trump never waived it", "never waived", frequent, 0.0) is None
    assert untrusted.off_fact(claim, "Trump signed the waiver", "x", frequent, 0.75) == "off-fact"  # 2 of 4 = 0.5 < 0.75
    assert untrusted.off_fact(claim, "Trump signed the waiver", "x", frequent, 0.5) is None


@pytest.mark.parametrize("claim_d, passage_d, span, verdict", [
    ("on Tuesday", "on Monday", "the drones did not strike", "different day"),
    ("on October 21", "on 22 Oct", "the drones did not strike", "different day"),
    ("on Tuesday, October 21", "on Monday, October 21", "the drones did not strike", None),  # one stated date matches
    ("on Tuesday", "on October 22", "the drones did not strike", None),  # different kinds: nothing comparable
    ("", "on Monday", "the drones did not strike", None),  # the claim states no date
    ("on Tuesday", "on Monday", "on Monday", None),  # the span carries the date: a date contradiction
], ids=["weekday", "month-day", "one-matches", "kinds-differ", "claim-undated", "span-is-the-date"])
def test_different_day(claim_d, passage_d, span, verdict):
    claim = f"Russian drones struck the Kyiv power station {claim_d}"
    passage = f"Officials said Russian drones struck the Kyiv power station {passage_d}."
    assert untrusted.off_fact(claim, passage, span, set(), 0.4) == verdict


def test_stated_dates():
    assert text.stated_dates("On October 22nd and 5 Oct., Tuesday; Sept. 3; May 2026") == {
        "day": {"10-22", "10-5", "9-3"}, "weekday": {"tuesday"}}


# --- the context window and the title in the payload ------------------------------------------------------------

LONG = "One intro. Two intro. Three intro. Russian drones struck the Kyiv power station on Tuesday night. After one. After two. After three."


def test_passage_window_two_sentences_each_side_and_edges():
    assert research.STANCE_CONTEXT_SENTENCES == 2
    before, passage, after = text.passage_window(CLAIM, LONG, 2)
    assert (before, after) == ("Two intro. Three intro.", "After one. After two.")
    assert passage.startswith("Russian drones")
    assert text.passage_window(CLAIM, ON_TOPIC, 2) == ("", ON_TOPIC.split(" More")[0], "More follows.")
    assert text.passage_window(CLAIM, "Nothing shared here.", 2) == ("", "", "")
    assert text.best_passage(CLAIM, LONG) == passage


@pytest.mark.parametrize("node", NODES)
def test_both_nodes_send_the_window_and_the_title(live_path, monkeypatch, node):
    payloads: list[dict] = []

    def json_task(task, payload, **kw):
        payloads.append(payload)
        return {"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"}

    monkeypatch.setattr(llm, "json_task", json_task)
    d = doc(2, "cnn", LONG)
    d["title"] = "Kyiv power station hit " + "x" * 400
    node.run(_state([doc(1, "origin", ON_TOPIC), d]))
    (p,) = payloads
    assert (p["context_before"], p["context_after"]) == ("Two intro. Three intro.", "After one. After two.")
    assert p["title"] == untrusted.clip(d["title"], untrusted.CAP_TITLE) and len(p["title"]) == untrusted.CAP_TITLE
    assert set(p) == {"claim", "passage", "context_before", "context_after", "title", "source", "source_kind", "doc_type", "role"}


def test_context_is_part_of_the_question():
    d = doc(2, "cnn", LONG)
    assert research.stance_question("researcher", CLAIM, "p", d, ("a", "b")) != research.stance_question("researcher", CLAIM, "p", d, ("a", "c"))


@pytest.mark.parametrize("node", NODES)
def test_an_off_fact_contradiction_becomes_neutral_and_is_counted(live_path, monkeypatch, node):
    # grounded, long enough, shares "kyiv" with the claim, but covers 2 of 8 composition stems (< 0.4)
    passage = "The Kyiv mayor said the night bus service did not resume."
    json_task, _ = stub({"stance": "contradicts", "reason": "x", "contradicted_span": "the night bus service did not resume"})
    monkeypatch.setattr(llm, "json_task", json_task)
    monkeypatch.setattr(config, "get", lambda section, key, default=None: {"stance_min_overlap": 0.0, "stance_coverage": 0.4}.get(key, default) if section == "research" else default)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", passage)]))
    assert out["claims"]["c1"]["evidence"] == []
    assert "; 1 contradictions off-fact" in out["steps"][0]["decision"]
    assert "ungrounded" not in out["steps"][0]["decision"]


def test_coverage_threshold_is_configured():
    assert config.get("research", "stance_coverage") == 0.4


def test_excluded_stems_are_named_in_the_reason(live_path, monkeypatch):
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
    monkeypatch.setattr(llm, "json_task", json_task)
    monkeypatch.setattr(research, "STANCE_FREQUENT_MIN_DOCS", 2)
    docs = [doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]
    for d in docs:
        d["title"] = "Kyiv strike"
    out = research.run(_state(docs))
    assert "topic-frequent stems excluded from fact compositions: kyiv, strike" in out["steps"][0]["reason"]


# --- the small-corpus guard (research.STANCE_FREQUENT_MIN_DOCS) ---------------------------------------------------

def _docs(n: int) -> list[DocRef]:
    out = [doc(i, f"s{i}", ON_TOPIC) for i in range(1, n + 1)]
    for d in out:
        d["title"] = "Kyiv strike"
    return out


def test_frequent_exclusion_is_off_below_thirty_documents():
    assert research.STANCE_FREQUENT_MIN_DOCS == 30
    assert research.topic_frequent(_state(_docs(29))) == (set(), 29)
    assert research.excluded_note(set(), 29) == "; topic-frequent exclusion off (29 documents)"


def test_frequent_exclusion_is_on_at_thirty_documents():
    frequent, n = research.topic_frequent(_state(_docs(30)))
    assert n == 30 and frequent == {"kyiv", "strike"}
    assert research.excluded_note(frequent, n) == "; topic-frequent stems excluded from fact compositions: kyiv, strike"


def test_small_day_reason_says_the_exclusion_is_off(live_path, monkeypatch):
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = fact_check.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]))
    assert "; topic-frequent exclusion off (2 documents)" in out["steps"][0]["reason"]


# --- coverage over the context window, and the short-span threshold ----------------------------------------------

KILLED_CLAIM = "Russian drones killed 31 civilians in the Kharkiv market strike on Tuesday"
KILLED_PASSAGE = "Officials said 5 were killed."
KILLED_BEFORE = "Russian drones hit the Kharkiv market on Tuesday."
KILLED_AFTER = "The strike wounded civilians nearby."


def test_coverage_uses_the_context_window():
    # the passage alone covers 1 composition stem (kill); with its neighbours it covers drone, kharkiv, market, strike, civilian, ...
    assert untrusted.off_fact(KILLED_CLAIM, KILLED_PASSAGE, "5 were killed", set(), 0.25) == "off-fact"
    assert untrusted.off_fact(KILLED_CLAIM, KILLED_PASSAGE, "5 were killed", set(), 0.25, f"{KILLED_BEFORE} {KILLED_AFTER}") is None
    # a caption-like neighbourhood from another story does not help
    assert untrusted.off_fact(KILLED_CLAIM, KILLED_PASSAGE, "5 were killed", set(), 0.25, "Photo: Getty Images. Shares closed higher.") == "off-fact"


def test_short_and_clause_thresholds(monkeypatch):
    assert config.get("research", "stance_coverage_short") == 0.25
    assert research.stance_coverage("5 were killed") == 0.25
    assert research.stance_coverage("officials said that five people were killed") == 0.4
    assert untrusted.is_short_span("did not sign") and not untrusted.is_short_span("the minister did not sign it")


def test_window_coverage_between_the_thresholds_keeps_a_short_span_only():
    # 9 composition stems; passage + context cover 3 (kharkiv, market, kill): 0.33, between 0.25 and 0.4
    claim = "Russian drones killed 31 civilians in the Kharkiv market strike on Tuesday night"
    passage = "In Kharkiv, 5 were killed at the market, said officials, who gave no other details at all."
    ctx = ("Officials gave a briefing.", "More details later.")
    short = {"stance": "contradicts", "contradicted_span": "5 were killed"}
    clause = {"stance": "contradicts", "contradicted_span": "5 were killed at the market"}
    assert research.judged_stance(short, claim, passage, set(), live=True, context=ctx) == ("contradicts", None)
    assert research.judged_stance(clause, claim, passage, set(), live=True, context=ctx) == ("neutral", "off-fact")


@pytest.mark.parametrize("node", NODES)
def test_nodes_measure_coverage_over_the_window(live_path, monkeypatch, node):
    # the passage is the best sentence by shared words (killed, the: 2; the next sentence ties at 2 and comes later),
    # covers one composition stem alone, and the sentence after it names the drones, the strike, Kharkiv and the market
    text_ = "Officials said 5 were killed in the attack. Russian drone strikes hit Kharkiv markets. More later."
    json_task, _ = stub({"stance": "contradicts", "reason": "x", "contradicted_span": "5 were killed"})
    monkeypatch.setattr(llm, "json_task", json_task)
    monkeypatch.setattr(research, "relevant", lambda claim, passage: True)
    st = _state([doc(1, "origin", KILLED_CLAIM), doc(2, "reuters", text_)])
    st["claims"]["c1"]["text"] = KILLED_CLAIM
    assert untrusted.off_fact(KILLED_CLAIM, "Officials said 5 were killed in the attack.", "5 were killed", set(), 0.25) == "off-fact"
    out = node.run(st)
    assert [ev["stance"] for ev in out["claims"]["c1"]["evidence"]] == ["contradicts"]
    assert "off-fact" not in out["steps"][0]["decision"]


def test_dry_run_stand_in_is_exempt_from_the_fact_check():
    off = "The Kyiv mayor said the night bus service did not resume."
    assert research.judged_stance({"stance": "contradicts"}, CLAIM, off, set(), live=False) == ("contradicts", None)
    assert research.judged_stance({"stance": "contradicts", "contradicted_span": "the night bus service did not resume"}, CLAIM, off, set(), live=True) == ("neutral", "off-fact")


# --- final round: clipped context, short-span date exception, full-stem fallback ---------------------------------

def test_clip_end_keeps_the_end():
    assert untrusted.clip_end("short", 10) == "short"
    out = untrusted.clip_end("A" * 50 + " next to the passage.", 20)
    assert len(out) == 20 and out.startswith("… ") and out.endswith("to the passage.")


def test_payload_context_before_keeps_its_end_after_keeps_its_start():
    far, near = "Far sentence " + "x" * 2000 + ".", "Near sentence before."
    d = doc(2, "cnn", "t")
    p = research.stance_payload(CLAIM, f"{far} {near}", "P.", "First after. " + "y" * 2000, d, "researcher")
    assert len(p["context_before"]) == untrusted.CAP_PASSAGE and p["context_before"].endswith(near) and p["context_before"].startswith("… ")
    assert len(p["context_after"]) == untrusted.CAP_PASSAGE and p["context_after"].startswith("First after.") and p["context_after"].endswith(" …")


def test_coverage_uses_the_clipped_context_only():
    # the claim's stems sit in the part of context_after that the clip cuts away: they must not count
    claim = "Russian drones struck the Kharkiv market"
    after = "Filler words. " + "z " * 800 + "Russian drones struck the Kharkiv market."
    span = {"stance": "contradicts", "contradicted_span": "officials said nothing was struck there"}
    passage = "Officials said nothing was struck there, the mayor said."
    assert research.judged_stance(span, claim, passage, set(), live=True, context=("", after)) == ("neutral", "off-fact")
    near = ("Russian drones struck the Kharkiv market. ", "")
    assert research.judged_stance(span, claim, passage, set(), live=True, context=near) == ("contradicts", None)


def test_date_exception_applies_to_short_spans_only():
    claim = "A Russian strike killed 7 people in Kharkiv on Tuesday"
    passage = "A strike on Monday killed 7 in Kharkiv, officials said."
    assert untrusted.off_fact(claim, passage, "on Monday", set(), 0.25) is None  # short date span: a date contradiction
    assert untrusted.off_fact(claim, passage, "a strike on Monday killed 7 in Kharkiv", set(), 0.4) == "different day"
    ans = {"stance": "contradicts", "contradicted_span": "a strike on Monday killed 7 in Kharkiv"}
    assert research.judged_stance(ans, claim, passage, set(), live=True) == ("neutral", "off-fact")
    # end to end a bare "on Monday" shares no stem with the claim and fails the span rule first; a short date span with a
    # claim word passes both rules
    ans_short = {"stance": "contradicts", "contradicted_span": "strike on Monday"}
    assert research.judged_stance(ans_short, claim, passage, set(), live=True) == ("contradicts", None)


def test_full_stem_fallback_and_its_note():
    frequent = {"trump", "zelensky", "met"}
    assert text.keeps_full_stems("Trump met Zelensky", frequent)
    assert text.fact_composition("Trump met Zelensky", frequent) == {"trump", "met", "zelensky"}
    assert not text.keeps_full_stems("Trump met Zelensky in Paris on aid", frequent)  # pari(s), aid remain
    assert text.fact_composition("Trump met Zelensky in Paris on aid", frequent) == {"pari", "aid"}  # stemmed
    assert not text.keeps_full_stems("Putin", frequent), "nothing excluded: no fallback to report"
    note = research.excluded_note(frequent, 40, ["Trump met Zelensky", "Trump met Zelensky in Paris on aid", "Zelensky met Trump"])
    assert note.endswith("; 2 claims kept their full stem set")
    assert research.excluded_note(frequent, 40, ["Trump met Zelensky in Paris on aid"]) == "; topic-frequent stems excluded from fact compositions: met, trump, zelensky"


def test_full_stem_note_in_the_step_reason(live_path, monkeypatch):
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
    monkeypatch.setattr(llm, "json_task", json_task)
    monkeypatch.setattr(research, "STANCE_FREQUENT_MIN_DOCS", 2)
    docs = [doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]
    for d in docs:
        d["title"], d["lead"] = "Russian drones struck Kyiv", ""
    st = _state(docs)
    st["claims"]["c1"]["text"] = "Russian drones struck Kyiv"
    out = research.run(st)
    assert "; 1 claims kept their full stem set" in out["steps"][0]["reason"]


# --- supporting span (live probe, 2026-10-25) and short spans by fact composition ---------------------------------

@pytest.mark.parametrize("span, kept", [
    ("Russian drones struck the Kyiv power station", True),
    ("struck", False),  # one composition stem (2026-10-25: 2 composition stems whatever the length)
    ("Russian  DRONES struck", True),
    (None, False),
    ("", False),
    ("the satellite service was restored", False),  # not in the passage
    ("officials said", False),  # in the passage, no fact-composition stem of the claim
], ids=["clause", "one-word", "normalised", "missing", "empty", "not-in-passage", "off-claim"])
def test_supporting_span_rule(span, kept):
    ans = {"stance": "supports"} | ({} if span is None else {"supporting_span": span})
    assert untrusted.checked_stance(ans, ON_TOPIC, CLAIM) == (("supports", False) if kept else ("neutral", True))


def test_supporting_span_uses_the_fact_composition_with_its_fallback():
    claim = "Trump spoke with Zelensky about Starlink"
    passage = "Trump spoke with Zelensky on Monday, officials said."
    frequent = {"trump", "zelensky", "spoke"}
    # composition {starlink} (two stems left would be needed for the fallback: here one remains, so full set is used)
    assert text.fact_composition(claim, frequent) == text.stems(claim)
    ans = {"stance": "supports", "supporting_span": "Trump spoke with Zelensky"}
    assert untrusted.checked_stance(ans, passage, claim, frequent=frequent) == ("supports", False)
    claim2 = "Trump spoke with Zelensky about Starlink satellite outages"
    assert untrusted.checked_stance(ans, passage, claim2, frequent=frequent) == ("neutral", True), "only frequent names shared"


@pytest.mark.parametrize("node", NODES)
def test_an_ungrounded_support_is_counted(live_path, monkeypatch, node):
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "More follows"})
    monkeypatch.setattr(llm, "json_task", json_task)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "cnn", ON_TOPIC)]))
    assert out["claims"]["c1"]["evidence"] == []
    assert "; 1 supports ungrounded" in out["steps"][0]["decision"]
    assert "contradictions ungrounded" not in out["steps"][0]["decision"]


def test_dry_run_stand_in_support_is_exempt():
    ans = dryrun.stance({"claim": CLAIM, "passage": ON_TOPIC, "role": "researcher", "source_kind": "outlet"})
    assert ans["stance"] == "supports" and "supporting_span" not in ans
    assert research.judged_stance(ans, CLAIM, ON_TOPIC, set(), live=False) == ("supports", None)


@pytest.mark.parametrize("span, passage, claim, kept", [
    ("still experiencing restrictions", "Soldiers said they were still experiencing restrictions on Starlink.",
     "Starlink restrictions for Ukrainian soldiers ended and service is back to normal", True),  # marker "still"
    ("Starlink restrictions remain", "Starlink restrictions remain in place, soldiers said.",
     "Starlink restrictions on Ukrainian units were lifted", True),
    ("no longer working", "The terminals are no longer working, soldiers said.", "Starlink terminals at the front work again", True),
    ("terminals at the front", "Soldiers said terminals at the front lost signal.", "Starlink terminals at the front work again", True),  # 2 composition stems
    ("terminals lost signal", "Soldiers said terminals lost signal.", "Starlink terminals at the front work again", False),  # 1 stem, no marker
], ids=["still", "remain", "no-longer", "two-composition-stems", "one-stem-no-marker"])
def test_short_span_markers_and_composition(span, passage, claim, kept):
    ans = {"stance": "contradicts", "contradicted_span": span}
    assert untrusted.checked_stance(ans, passage, claim) == (("contradicts", False) if kept else ("neutral", True))


def test_bare_longer_is_not_a_negation_marker():
    from quorum_reasoning import untrusted

    assert "longer" not in untrusted.SPAN_NEGATIONS and "no" in untrusted.SPAN_NEGATIONS


# --- supports under the fact-composition rule (D5 of snapshot v5, owner's decision 2026-10-25) ---------------------

@pytest.mark.parametrize("span, claim, kept", [
    ("drones struck", CLAIM, True),  # 2 composition stems, short
    ("struck", CLAIM, False),  # 1 stem, short
    ("officials said the station was hit", CLAIM, False),  # a 5+ word clause sharing 1 stem no longer passes (2026-10-25)
    ("officials said it was hit", CLAIM, False),  # 5+ words, no composition stem
    ("the station", CLAIM, False),  # short, 1 stem
    ("officials said Russian drones hit the station", CLAIM, True),  # clause, 3 stems
], ids=["short-two-stems", "short-one-stem", "clause-one-stem", "clause-no-stem", "short-one-stem-2", "clause-three-stems"])
def test_supporting_span_needs_two_stems(span, claim, kept):
    assert untrusted.span_supports_claim(span, claim) is kept


def test_support_threshold_is_named():
    assert untrusted.SUPPORT_SPAN_STEMS_MIN == 2


def test_a_support_off_the_fact_becomes_neutral():
    # the span is grounded and shares 2 composition stems (kyiv, station), but passage + context cover 2 of 8 (< 0.4)
    passage = "The Kyiv station manager said tickets would be refunded next week."
    ans = {"stance": "supports", "supporting_span": "The Kyiv station manager said tickets would be refunded"}
    assert untrusted.checked_stance(ans, passage, CLAIM) == ("supports", False)
    assert research.judged_stance(ans, CLAIM, passage, set(), live=True) == ("neutral", "support off-fact")
    # the same span with a context window that names the drones, the strike and the power station stays
    ctx = ("Russian drones struck a power station overnight.", "The strike came on Tuesday night.")
    assert research.judged_stance(ans, CLAIM, passage, set(), live=True, context=ctx) == ("supports", None)


def test_support_uses_the_short_bar_for_a_short_span(monkeypatch):
    # 9 composition stems; passage + context cover 3 (kharkiv, market, kill): 0.33, between 0.25 and 0.4
    claim = "Russian drones killed 31 civilians in the Kharkiv market strike on Tuesday night"
    passage = "In Kharkiv, people were killed at the market, said officials, who gave no other details at all."
    ctx = ("Officials gave a briefing.", "More details later.")
    short = {"stance": "supports", "supporting_span": "killed at the market"}  # 4 words, 2 stems
    clause = {"stance": "supports", "supporting_span": "people were killed at the market"}
    assert research.judged_stance(short, claim, passage, set(), live=True, context=ctx) == ("supports", None)
    assert research.judged_stance(clause, claim, passage, set(), live=True, context=ctx) == ("neutral", "support off-fact")


def test_support_two_stem_floor_and_full_stem_fallback():
    claim = "Trump met Zelensky"
    frequent = {"trump", "zelensky"}
    assert text.fact_composition(claim, frequent) == text.stems(claim)  # fallback: full stem set
    ans = {"stance": "supports", "supporting_span": "Trump met Zelensky"}
    assert research.judged_stance(ans, claim, "Trump met Zelensky in Kyiv.", frequent, live=True) == ("supports", None)
    # one of three stems in a short span: the span rule already rejects it
    assert research.judged_stance({"stance": "supports", "supporting_span": "Trump"}, claim, "Trump spoke.", frequent, live=True) == ("neutral", "support ungrounded")


def test_support_date_rule_has_no_short_span_exception():
    claim = "The Kharkiv market strike on Tuesday killed 5"
    passage = "Officials said the Kharkiv market strike on Monday killed 5."
    sup = {"stance": "supports", "supporting_span": "market strike on Monday"}  # short, 2 composition stems, a date
    con = {"stance": "contradicts", "contradicted_span": "market strike on Monday"}
    assert research.judged_stance(con, claim, passage, set(), live=True) == ("contradicts", None)  # the date is the contradiction
    assert research.judged_stance(sup, claim, passage, set(), live=True) == ("neutral", "support off-fact")
    assert untrusted.off_fact(claim, passage, "market strike on Monday", set(), 0.25, stance="supports") == "different day"
    assert untrusted.off_fact(claim, passage, "market strike on Monday", set(), 0.25) is None


def test_dry_run_stand_in_support_is_exempt_from_the_fact_check():
    off = "The Kyiv station manager said tickets would be refunded next week."
    assert research.judged_stance({"stance": "supports"}, CLAIM, off, set(), live=False) == ("supports", None)


@pytest.mark.parametrize("node", NODES)
def test_an_off_fact_support_is_counted_separately(live_path, monkeypatch, node):
    passage = "The Kyiv station manager said tickets would be refunded next week."
    json_task, _ = stub({"stance": "supports", "reason": "x", "supporting_span": "The Kyiv station manager said tickets would be refunded"})
    monkeypatch.setattr(llm, "json_task", json_task)
    monkeypatch.setattr(research, "relevant", lambda claim, passage: True)
    out = node.run(_state([doc(1, "origin", ON_TOPIC), doc(2, "reuters", passage)]))
    assert out["claims"]["c1"]["evidence"] == []
    decision = out["steps"][0]["decision"]
    assert "; 1 supports off-fact" in decision
    assert "supports ungrounded" not in decision and "contradictions off-fact" not in decision


def test_relevance_note_names_supports_off_fact():
    assert research.relevance_note(0, 0, 0, 1, 2) == "; 1 supports ungrounded, 2 supports off-fact"


@pytest.mark.parametrize("claim, passage, span, ctx", [
    # synthetic analogues of the D5 noise on snapshot v5 (2026-10-25); none may confirm its claim
    ("Tucker Carlson has broken with Donald Trump largely over the war in Iran",
     "Trump has been upset with Zelensky over Ukraine's attacks on Russian refineries.",
     "Trump has been upset with Zelensky over Ukraine's attacks on Russian refineries", ("", "")),
    ("French police reported looting of shops in Paris after the riots",
     "Looters took goods from shops in Kyiv after the strike, residents said.",
     "Looters took goods from shops in Kyiv", ("Russian missiles hit the city centre overnight.", "")),
    ("AfD's 2025 election programme calls for lifting sanctions on Russia",
     "Trump suspended sanctions against Russia and allowed it to sell more oil.",
     "suspended sanctions against Russia and allowed it to sell more oil", ("", "")),
    ("The color revolutions that destabilized nations abroad are now being organised at home",
     "The president asked Musk, whose company operates Starshield, to restore the service.",
     "The president asked Musk, whose company operates Starshield", ("", "")),
], ids=["carlson-refinery", "looting-kyiv", "afd-trump", "color-revolutions-starshield"])
def test_d5_style_noise_no_longer_supports(claim, passage, span, ctx):
    ans = {"stance": "supports", "supporting_span": span}
    stance, why = research.judged_stance(ans, claim, passage, {"trump", "russia", "ukraine", "president"}, live=True, context=ctx)
    assert stance == "neutral" and why in ("support ungrounded", "support off-fact")


def test_weak_words_are_not_stems():
    for w in "just come came day days also new like make made take took get got way time year years week weeks month months today yesterday tomorrow back still people says said say told".split():
        assert text.stems(w) == set(), w
    assert "still" in untrusted.SPAN_NEGATIONS  # still a short-span marker for contradictions


def test_midterms_shape_weak_stem_overlap_is_not_support():
    # synthetic analogue of the attempt-6 row: the passage shares only weak words and "midterms" with the claim
    claim = "The charges come just 10 days before the midterms."
    passage = ("These include allowing Russia to export diesel to global markets, just days before the midterms, "
               "a move critics called a gift to Moscow.")
    ans = {"stance": "supports", "supporting_span": "allowing Russia to export diesel to global markets, just days before the midterms"}
    assert text.fact_composition(claim, set()) == {"charg", "midterm"}
    assert research.judged_stance(ans, claim, passage, set(), live=True) == ("neutral", "support ungrounded")
