"""Function words in text.stems and the boilerplate filter on passage selection (2026-10-25 pre-merge check).

No model, no I/O: text helpers and one research node run with a stub model.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import llm, text
from quorum_reasoning.nodes import research
from quorum_reasoning.state import Claim, DocRef, Event, initial_state

# --- function words ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word", "about more than who which been other also after before over under into from with their there these those would could should said says".split())
def test_function_words_are_not_stems(word):
    assert text.stems(f"{word} Kharkiv") == {"kharkiv"}


def test_about_no_longer_crowds_the_topic_frequent_stems():
    docs = [f"About the {w} talks" for w in ("ceasefire", "grain", "prisoner", "energy")] + ["Ceasefire about grain"]
    assert "about" not in text.frequent_stems(docs, k=2)


def test_tokens_are_unchanged():
    # containment, grounded_in and the stance_min_overlap guard use tokens, which keep function words
    assert {"about", "their", "said"} <= text.tokens("They said it was about their town")


# --- boilerplate -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sentence", [
    "Photograph: Alex Wong/Getty Images View image in fullscreen Senators met on Tuesday.",
    "Photo: Reuters",
    "Image: supplied",
    "Kyiv after the strike, Andrew Harnik/Getty Images",
    "A rescuer in Kharkiv. Getty Images",
    "View image in fullscreen",
    "Read more",
    "Related: Ukraine war live",
    "Sign up to First Edition, our free daily newsletter",
    "Skip past newsletter promotion",
    "Advertisement",
])
def test_each_pattern_is_filtered(sentence):
    assert text.is_boilerplate(sentence)


@pytest.mark.parametrize("sentence", [
    "The photographer Alex Wong, who works for Getty Images, was in Kyiv when the drones struck.",
    "Officials said the image of the strike was verified.",
    "Related talks resumed in Geneva on Monday.",  # "Related" without a colon is prose
])
def test_prose_is_not_filtered(sentence):
    assert not text.is_boilerplate(sentence)


CLAIM = "Russian drones struck the Kyiv power station on Tuesday night"
CAPTION_FIRST = (
    "Russian drones struck the Kyiv power station on Tuesday night, Photograph: Alex Wong/Getty Images. "
    "Officials said Russian drones struck a Kyiv power station on Tuesday. More follows."
)


def test_best_passage_skips_a_caption_that_scores_highest():
    first = CAPTION_FIRST.split(". ")[0] + "."
    assert text.is_boilerplate(first)
    assert text.best_passage(CLAIM, CAPTION_FIRST) == "Officials said Russian drones struck a Kyiv power station on Tuesday."
    before, passage, after = text.passage_window(CLAIM, CAPTION_FIRST, 2)
    assert before == "" and after == "More follows.", "boilerplate is not context either"


def _doc(doc_id: int, source: str, body: str) -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{source}/{doc_id}", title="t", lead="", published_at="2026-10-21T12:00:00Z",
                  access_level=1, wire_origin=None, text=body)


def test_offsets_of_a_quote_after_a_filtered_caption(monkeypatch):
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "route_configured", lambda: True)
    monkeypatch.setattr(llm, "json_task", lambda task, payload, **kw: {"stance": "supports", "reason": "x", "supporting_span": "Russian drones struck"})
    st = initial_state("t", "russia-ukraine-war", "2026-10-22", dry_run=False)
    st["documents"] = [_doc(1, "origin", "Russian drones struck the Kyiv power station on Tuesday night."), _doc(2, "guardian", CAPTION_FIRST)]
    st["events"] = [Event(id="ev1", document_ids=[1, 2], headline="x", standfirst="", rubric=None, above_bar=False, rank=None, needs_review=False,
                          article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")]
    st["claims"] = {"c1": Claim(id="c1", event_id="ev1", text=CLAIM, kind="fact", origin_document_id=1, evidence=[], verifier_status=None,
                                verifier_reason="", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")}
    (ev,) = research.run(st)["claims"]["c1"]["evidence"]
    assert ev["quote"] == "Officials said Russian drones struck a Kyiv power station on Tuesday."
    assert CAPTION_FIRST[ev["char_start"]:ev["char_end"]] == ev["quote"]


@pytest.mark.parametrize("prose", [
    "Advertisement spending fell 5% after the sanctions.",
    "Advertisements for the draft appeared in Kyiv.",
    "Sign up for the army rose 20% in October, the ministry said.",
    "Read more broadly, the decree bans exports of grain.",
])
def test_prose_that_starts_like_a_ui_label_is_not_boilerplate(prose):
    from quorum_reasoning.text import is_boilerplate

    assert not is_boilerplate(prose)


@pytest.mark.parametrize("line", ["Advertisement", "Read more", "Related: Ukraine war latest", "Skip past newsletter promotion", "Sign up to First Edition, our free daily newsletter", "Photograph: Alex Wong/Getty Images"])
def test_whole_ui_lines_are_boilerplate(line):
    from quorum_reasoning.text import is_boilerplate

    assert is_boilerplate(line)
