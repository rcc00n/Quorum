"""Red-team tests for the confirmation rules and the impact bar (review 2026-10-23, workstream A).

Each test carries a finding id (A1, A2, ...) in its docstring; the findings table is in
docs/reviews/2026-10-23-reasoning-review.md. Tests asserting behaviour the code already has are
regression tests and say so. Tests for found bugs assert the correct behaviour per the recorded rules
(DECISIONS.md › Principles for handling facts, ARCHITECTURE.md § 6) and fail until the fix is applied.
All content is fictional. No model, no network: dry run only.
"""

from __future__ import annotations

import pytest

from quorum_reasoning.nodes import cluster, research
from quorum_reasoning.rules import confirmation, impact_bar
from quorum_reasoning.state import Claim, DocRef, Event, initial_state
from quorum_reasoning.tools import corpus

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


def make_doc(
    doc_id: int,
    source_id: str,
    *,
    group: str | None = None,
    kind: str = "outlet",
    title: str = "",
    lead: str = "",
    text: str | None = None,
    wire_origin: str | None = None,
    official: bool = False,
    doc_type: str | None = None,
    access_level: int = 1,
) -> DocRef:
    d = DocRef(
        id=doc_id,
        source_id=source_id,
        source_name=source_id,
        independence_group=group or source_id,
        kind="official" if official else kind,
        flank=None,
        tier=None,
        url=f"https://example.org/{source_id}/{doc_id}",
        title=title,
        lead=lead,
        published_at="2026-10-21T12:00:00Z",
        access_level=access_level,
        wire_origin=wire_origin,
    )
    if official:
        d["official"] = True
        d["doc_type"] = doc_type
    if text is not None:
        d["text"] = text
    return d


def make_event(event_id: str, document_ids: list[int]) -> Event:
    return Event(
        id=event_id,
        document_ids=document_ids,
        headline="x",
        standfirst="",
        rubric=None,
        above_bar=False,
        rank=None,
        needs_review=False,
        article=[],
        drafts=0,
        versions=[],
        critic_status=None,
        critic_notes="",
        framing={},
        review_reason="",
    )


def make_claim(cid: str, event_id: str, text: str, origin: int | None) -> Claim:
    return Claim(
        id=cid,
        event_id=event_id,
        text=text,
        kind="fact",
        origin_document_id=origin,
        evidence=[],
        verifier_status=None,
        verifier_reason="",
        fact_checker_status=None,
        fact_checker_reason="",
        final_status=None,
        adjudication="",
    )


def state_with(docs: list[DocRef], events: list[Event], claims: dict[str, Claim]):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = docs
    st["events"] = events
    st["claims"] = claims
    return st


# --- A1: wire reprints must share the wire's independence group -----------------------------------------


def test_a1_wire_reprint_carries_the_wire_independence_group():
    """A1. A reprint with wire_origin set is the wire's story: its evidence row must carry the wire's
    independence group, or one wire story counts as two confirmations (DECISIONS: ten reprints of one
    wire story are one piece of evidence)."""
    reprint = make_doc(3, "cnn", wire_origin="AP", text="The convoy reached the depot.")
    ev = research.evidence_from(reprint, "The convoy reached the depot.", "supports", "researcher")
    assert ev["independence_group"] == "ap"


def test_a1_wire_plus_its_reprint_do_not_confirm():
    """A1. AP's own story plus a CNN reprint of it is one independent group, not two: unverified."""
    ap = make_doc(1, "ap", kind="agency", text="The convoy reached the depot.")
    reprint = make_doc(3, "cnn", wire_origin="AP", text="The convoy reached the depot.")
    evs = [
        research.evidence_from(ap, "The convoy reached the depot.", "supports", "researcher"),
        research.evidence_from(reprint, "The convoy reached the depot.", "supports", "researcher"),
    ]
    status, _ = confirmation.verdict(evs)
    assert status == "unverified"


# --- A2: documents and official_docs ids are separate namespaces ----------------------------------------


def _rows_with_colliding_ids(sql: str, limit: int):
    base = {
        "source_name": None,
        "flank": None,
        "tier": None,
        "lead": "",
        "published_at": "2026-10-21T12:00:00Z",
        "wire_origin": None,
    }
    if "official_docs" in sql:
        return [
            {
                **base,
                "id": 7,
                "source_id": "congress-gov",
                "independence_group": "us-gov",
                "kind": "official",
                "url": "https://www.congress.gov/bill/1",
                "title": "An act (fictional)",
                "access_level": 1,
                "doc_type": "law",
                "text": "The act appropriates funds.",
            }
        ]
    return [
        {
            **base,
            "id": 7,
            "source_id": "cnn",
            "independence_group": "cnn",
            "kind": "outlet",
            "url": "https://example.org/cnn/7",
            "title": "An act appropriates funds (fictional)",
            "access_level": 1,
        }
    ]


def test_a2_live_corpus_keeps_document_and_official_ids_apart(monkeypatch):
    """A2. documents.id and official_docs.id are independent sequences in Postgres; both start at 1.
    Loaded into one DocRef.id space they collide, and every by-id lookup (score, extract, the origin
    skip in research) silently picks the wrong document. The corpus must namespace them."""
    monkeypatch.setattr(corpus, "_run_sql", _rows_with_colliding_ids)
    docs = corpus.load_documents(TOPIC, DAY, corpus="zetaris")
    ids = [d["id"] for d in docs]
    assert len(set(ids)) == len(ids), f"colliding ids in the loaded corpus: {ids}"


def test_a2_official_evidence_keeps_the_database_id(monkeypatch):
    """A2. With the namespace applied, an evidence row's official_doc_id must still be the database id,
    so analysis.evidence rows keep pointing at real official_docs rows."""
    monkeypatch.setattr(corpus, "_run_sql", _rows_with_colliding_ids)
    docs = corpus.load_documents(TOPIC, DAY, corpus="zetaris")
    official = next(d for d in docs if d.get("official"))
    ev = research.evidence_from(official, "The act appropriates funds.", "supports", "researcher")
    assert ev["official_doc_id"] == 7
    assert ev["is_document"] is True


# --- A8: a correction (supersedes_id) must retire the version it replaces -------------------------------


def _rows_with_correction(sql: str, limit: int):
    if "official_docs" in sql:
        return []
    base = {
        "source_name": "Example Wire",
        "flank": None,
        "tier": None,
        "published_at": "2026-10-21T12:00:00Z",
        "wire_origin": None,
        "access_level": 1,
        "source_id": "example",
        "independence_group": "example",
        "kind": "agency",
    }
    return [
        {
            **base,
            "id": 21,
            "url": "https://example.org/a",
            "title": "Strike hit the plant, officials say",
            "lead": "First version.",
            "supersedes_id": None,
        },
        {
            **base,
            "id": 22,
            "url": "https://example.org/a",
            "title": "Correction: strike missed the plant",
            "lead": "Corrected version.",
            "supersedes_id": 21,
        },
    ]


def test_a8_superseded_document_is_not_part_of_the_corpus(monkeypatch):
    """A8. collectors/schema.sql sets supersedes_id when a re-fetch found changed content: the new row
    replaces the old one. Reasoning must read only the current version, or a claim keeps being
    supported by text its own outlet has already corrected within the same day."""
    monkeypatch.setattr(corpus, "_run_sql", _rows_with_correction)
    docs = corpus.load_documents(TOPIC, DAY, corpus="zetaris")
    ids = [d["id"] for d in docs]
    assert 22 in ids and 21 not in ids


# --- A9: a stored quote must not be cut mid-sentence -----------------------------------------------------


def test_a9_quote_is_whole_sentences_not_a_character_cut():
    """A9. The evidence quote is what the page shows as justification. A fixed character cut can drop
    the second half of a sentence ("... the convoy did" and the "not cross" tail gone). The stored
    quote must end on a sentence boundary when the passage is longer than the cap."""
    s1 = "Monitors tracked the convoy for several hours through the checkpoint area on Monday morning."
    s2 = (
        "After comparing the vehicle counts with the crossing logs kept by the border service and the "
        "railway operator over the whole of the previous week, the monitors concluded that the convoy did "
        "not cross the border."
    )
    passage = s1 + " " + s2
    assert len(passage) > 300  # the cap in research.evidence_from
    doc = make_doc(5, "npr", text=passage)
    ev = research.evidence_from(doc, passage, "supports", "researcher")
    assert ev["quote"] == s1, "quote was cut mid-sentence"


# --- A3/A4: official releases and statements never establish facts (regression) --------------------------


def test_a3_official_release_support_becomes_a_statement():
    """A3 (regression; code already defends). An official release that 'supports' a claim is the
    interested party's words: the stance is downgraded to statement and never confirms."""
    release = make_doc(9, "whitehouse", group="us-gov", official=True, doc_type="release", text="Deliveries begin within weeks.")
    ev = research.evidence_from(release, "Deliveries begin within weeks.", "supports", "researcher")
    assert ev["stance"] == "statement"
    assert ev["is_document"] is False
    assert confirmation.verdict([ev])[0] == "unverified"


def test_a4_only_adopted_document_types_establish():
    """A4 (regression; code already defends). law/order/vote/ruling establish; statement/release/None
    do not, whatever the stance."""
    for doc_type, expected in (("law", True), ("order", True), ("vote", True), ("ruling", True), ("statement", False), ("release", False), (None, False)):
        d = make_doc(9, "congress-gov", group="us-gov", official=True, doc_type=doc_type, text="x")
        ev = research.evidence_from(d, "x", "supports", "researcher")
        assert ev["is_document"] is expected, doc_type


# --- A5: a claim does not confirm itself (regression) ----------------------------------------------------


def test_a5_origin_document_is_not_its_own_evidence():
    """A5 (regression; code already defends). The outlet document a claim was extracted from is skipped
    by research; a claim cannot support itself with its own article."""
    origin = make_doc(1, "fox-news", text="The depot was hit by three missiles overnight.")
    unrelated = make_doc(2, "cnn", text="Weather delayed flights across the region on Sunday.")
    e = make_event("ev1", [1, 2])
    c = make_claim("c1", "ev1", "The depot was hit by three missiles overnight", origin=1)
    st = state_with([origin, unrelated], [e], {"c1": c})
    out = research.run(st)
    evid = out["claims"]["c1"]["evidence"]
    assert not any(ev["document_id"] == 1 for ev in evid), "origin document used as its own evidence"
    assert confirmation.verdict(evid)[0] == "unverified"


def test_a5_official_release_origin_cannot_confirm_its_own_claim():
    """A5 (regression; code already defends). A claim extracted from an official release and 'found' in
    the same release gets stance statement, not supports — the release is not evidence for itself."""
    release = make_doc(9, "whitehouse", group="us-gov", official=True, doc_type="release", text="Deliveries will begin within weeks.")
    e = make_event("ev1", [9])
    c = make_claim("c1", "ev1", "Deliveries will begin within weeks", origin=9)
    st = state_with([release], [e], {"c1": c})
    out = research.run(st)
    evid = out["claims"]["c1"]["evidence"]
    assert not any(ev["stance"] == "supports" for ev in evid)
    assert confirmation.verdict(evid)[0] == "unverified"


# --- A6: the cap never trades a confirmed story for a flagged one (regression) ---------------------------


def test_a6_flagged_events_do_not_consume_cap_slots():
    """A6 (regression; code already defends). A needs_review event, however high its total, takes no
    rank slot; with 11 confirmed stories and the cap at 10, exactly the 10 best confirmed are shown."""

    def ev(i: int, total: tuple[int, int, int, int], review: bool = False):
        return {"id": f"e{i:02d}", "rubric": impact_bar.build_rubric(*total, {}), "above_bar": False, "rank": None, "needs_review": review}

    flagged = ev(0, (2, 3, 2, 2), review=True)  # total 9, flagged: crosses on points, nothing confirmed
    confirmed = [ev(i, (2, 2, 2, 2)) for i in range(1, 11)]  # ten events, total 8
    last = ev(11, (2, 2, 1, 2))  # total 7: the one the cap drops
    ordered = impact_bar.rank_and_cap([flagged, *confirmed, last])
    above = [e["id"] for e in ordered if e["above_bar"]]
    assert "e00" not in above
    assert len(above) == 10
    assert "e11" not in above  # dropped by the cap, not displaced by the flagged event
    assert [e["rank"] for e in ordered if e["above_bar"]] == list(range(1, 11))


# --- A7: transitive title merges chain unrelated documents into one event --------------------------------


@pytest.mark.xfail(
    reason="A7: union-find merges every pair above the similarity threshold transitively; a bridge title chains "
    "two documents with zero shared words into one event, and research round 1 then searches both for every "
    "claim of the event. Fixing this changes the recorded clustering decision (nodes/cluster.py): proposal in "
    "docs/reviews/2026-10-23-reasoning-review.md.",
    strict=True,
)
def test_a7_bridge_title_must_not_chain_unrelated_documents():
    """A7. sim(T1,T2) and sim(T2,T3) are above the threshold, sim(T1,T3) is 0: T1 and T3 still end up in
    one event, so a claim from T1's document can be 'confirmed' by T3's unrelated document."""
    d1 = make_doc(1, "fox-news", title="Senate panel approves interceptor funding")
    d2 = make_doc(2, "cnn", title="Senate panel approves grain corridor inspections")
    d3 = make_doc(3, "npr", title="Grain corridor inspections resume Monday")
    assert cluster.similarity(cluster._terms(d1), cluster._terms(d3)) == 0.0
    st = state_with([d1, d2, d3], [], {})
    out = cluster.run(st)
    together = [e for e in out["events"] if {1, 3} <= set(e["document_ids"])]
    assert not together, "documents with zero title overlap share an event via a bridge title"


# --- A11: the verdict is order-independent and contradiction alone is unverified (regression) ------------


def test_a11_contradiction_is_order_independent():
    """A11 (regression; code already defends). The verdict reads all evidence: a contradiction is not
    lost when it arrives before the supports, and support+contradiction is disputed in any order."""
    sup_a = research.evidence_from(make_doc(1, "ap", kind="agency", text="x"), "x", "supports", "researcher")
    sup_b = research.evidence_from(make_doc(2, "npr", text="x"), "x", "supports", "researcher")
    con = research.evidence_from(make_doc(3, "guardian", text="x"), "x", "contradicts", "researcher")
    assert confirmation.verdict([con, sup_a, sup_b])[0] == "disputed"
    assert confirmation.verdict([sup_a, sup_b, con])[0] == "disputed"
    assert confirmation.verdict([sup_a, con])[0] == "disputed"


def test_a11_contradiction_alone_is_unverified_not_disputed():
    """A11 (regression; documents the recorded rule). DECISIONS: disputed needs supporting and
    contradicting evidence, or a verifier/fact-checker disagreement. Contradiction with no support
    stays unverified."""
    con = research.evidence_from(make_doc(3, "guardian", text="x"), "x", "contradicts", "researcher")
    assert confirmation.verdict([con])[0] == "unverified"


def test_a12_edition_window_follows_new_york_dst():
    """A12: the 05:30 America/New_York cut must move with DST, or documents published between 09:30Z
    and 10:30Z after 2026-11-01 fall between two editions and never enter any corpus."""
    from quorum_reasoning.tools.corpus import _edition_window

    assert _edition_window("2026-10-22") == ("2026-10-21T09:30:00Z", "2026-10-22T09:30:00Z")  # EDT
    assert _edition_window("2026-12-01") == ("2026-11-30T10:30:00Z", "2026-12-01T10:30:00Z")  # EST
    # the transition day is a 25-hour local day; its window covers both offsets with no gap
    assert _edition_window("2026-11-01") == ("2026-10-31T09:30:00Z", "2026-11-01T10:30:00Z")
    assert _edition_window("2026-11-02")[0] == "2026-11-01T10:30:00Z"
