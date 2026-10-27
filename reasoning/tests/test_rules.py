"""Unit tests for the pure rules: confirmation, impact bar, writing rules. No model, no network."""

from __future__ import annotations

from quorum_reasoning.rules import confirmation, impact_bar, writing_rules
from quorum_reasoning.state import Claim, Evidence


def ev(stance: str, group: str, *, document: bool = False, found_by: str = "researcher") -> Evidence:
    return Evidence(
        quote="…",
        document_id=None if document else 1,
        official_doc_id=1 if document else None,
        independence_group=group,
        stance=stance,  # type: ignore[typeddict-item]
        found_by=found_by,
        url="https://example.org",
        title=group,
        is_document=document,
    )


def claim(cid: str, status: str | None, kind: str = "fact") -> Claim:
    return Claim(
        id=cid,
        event_id="e1",
        text=cid,
        kind=kind,
        origin_document_id=1,
        evidence=[],
        verifier_status=None,
        verifier_reason="",
        fact_checker_status=None,
        fact_checker_reason="",
        final_status=status,  # type: ignore[typeddict-item]
        adjudication="",
    )


# --- confirmation -------------------------------------------------------------------------------------


def test_signed_document_confirms_alone():
    status, _ = confirmation.verdict([ev("supports", "us-gov", document=True)])
    assert status == "confirmed"


def test_two_independent_groups_confirm():
    assert confirmation.verdict([ev("supports", "reuters"), ev("supports", "cnn")])[0] == "confirmed"


def test_reprints_of_one_wire_count_once():
    # two outlets carrying the same wire story share an independence group
    assert confirmation.verdict([ev("supports", "reuters"), ev("supports", "reuters")])[0] == "unverified"


def test_statements_are_not_evidence():
    assert confirmation.verdict([ev("statement", "us-gov"), ev("statement", "us-gov")])[0] == "unverified"


def test_support_plus_contradiction_is_disputed():
    assert confirmation.verdict([ev("supports", "reuters"), ev("contradicts", "ap")])[0] == "disputed"
    assert confirmation.verdict([ev("supports", "reuters"), ev("supports", "cnn"), ev("contradicts", "ap")])[0] == "disputed"


def test_thin_means_another_round_could_help():
    assert confirmation.is_thin([ev("supports", "reuters")])
    assert not confirmation.is_thin([ev("supports", "reuters"), ev("supports", "cnn")])
    assert not confirmation.is_thin([ev("supports", "us-gov", document=True)])


def test_adjudication_never_resolves_disagreement_by_guessing():
    assert confirmation.adjudicate("confirmed", "confirmed")[0] == "confirmed"
    assert confirmation.adjudicate("confirmed", "unverified")[0] == "disputed"
    assert confirmation.adjudicate("unverified", "unverified")[0] == "unverified"


# --- impact bar -------------------------------------------------------------------------------------------


def test_bar_needs_total_and_confirmation():
    # The bar is 4 of 9 with confirmation >= 1 since 2026-10-26 (6 until then; DECISIONS › Selecting major news).
    assert impact_bar.threshold() == 4
    assert impact_bar.crosses_bar(impact_bar.build_rubric(2, 2, 2, 2, {}))
    assert impact_bar.crosses_bar(impact_bar.build_rubric(1, 1, 1, 1, {}))  # exactly 4, confirmed once
    assert not impact_bar.crosses_bar(impact_bar.build_rubric(2, 3, 2, 0, {}))  # 7 points but nothing independent
    assert not impact_bar.crosses_bar(impact_bar.build_rubric(1, 1, 0, 1, {}))  # 3 points


def test_points_are_clamped_to_their_ranges():
    r = impact_bar.build_rubric(9, -1, 2, 5, {})
    assert (r["legal_force"], r["reach"], r["irreversibility"], r["confirmation"]) == (2, 0, 2, 2)


def test_confirmation_points():
    assert impact_bar.confirmation_points(0, False) == 0
    assert impact_bar.confirmation_points(1, False) == 1
    assert impact_bar.confirmation_points(2, False) == 2
    assert impact_bar.confirmation_points(0, True) == 2


def test_cap_is_a_maximum_not_a_target():
    def event(i: int, total_points: tuple[int, int, int, int], review: bool = False):
        return {"id": f"e{i}", "rubric": impact_bar.build_rubric(*total_points, {}), "above_bar": False, "rank": None, "needs_review": review}

    events = [event(1, (2, 2, 2, 2)), event(2, (1, 1, 0, 1)), event(3, (2, 3, 2, 2), review=True), event(4, (2, 2, 1, 1))]  # e2: 3 of 9, below the bar of 4
    ordered = impact_bar.rank_and_cap(events)  # type: ignore[arg-type]
    above = [e["id"] for e in ordered if e["above_bar"]]
    assert above == ["e1", "e4"]  # e2 below the bar, e3 flagged for review
    assert [e["rank"] for e in ordered if e["above_bar"]] == [1, 2]


# --- writing rules ------------------------------------------------------------------------------------------


def test_article_order_allows_repeats_but_not_regressions():
    claims = {"c1": claim("c1", "confirmed"), "c2": claim("c2", "confirmed")}
    ok = [
        {"kind": "fact", "text": "A.", "claim_ids": ["c1"], "sources": [{"title": "x", "url": "u"}]},
        {"kind": "fact", "text": "B.", "claim_ids": ["c2"], "sources": [{"title": "x", "url": "u"}]},
        {"kind": "statements", "text": "What follows are statements, not confirmed facts. The ministry said so.", "claim_ids": [], "sources": []},
    ]
    assert writing_rules.check_article(ok, claims) == []  # type: ignore[arg-type]
    bad = [ok[2], ok[0]]
    assert any(v.startswith("order:") for v in writing_rules.check_article(bad, claims))  # type: ignore[arg-type]


def test_fact_block_needs_confirmed_claim_and_source():
    claims = {"c1": claim("c1", "unverified")}
    block = [{"kind": "fact", "text": "A.", "claim_ids": ["c1"], "sources": []}]
    v = writing_rules.check_article(block, claims)  # type: ignore[arg-type]
    assert any("not confirmed" in x for x in v) and any("no source" in x for x in v)


def test_forbidden_wording_and_attribution():
    claims = {"c1": claim("c1", "confirmed")}
    blocks = [
        {"kind": "fact", "text": "A sweeping law was signed.", "claim_ids": ["c1"], "sources": [{"title": "x", "url": "u"}]},
        {"kind": "statements", "text": "What follows are statements, not confirmed facts. Deliveries begin within weeks.", "claim_ids": [], "sources": []},
    ]
    v = writing_rules.check_article(blocks, claims)  # type: ignore[arg-type]
    assert any("forbidden wording 'sweeping'" in x for x in v)
    assert any("without attribution" in x for x in v)
    assert writing_rules.check_headline("Historic aid bill signed") == ["headline: forbidden wording 'historic'"]
    assert writing_rules.check_text("standfirst", "Signed on Tuesday.") == []


def test_not_confirmed_block_rejects_confirmed_claims():
    claims = {"c1": claim("c1", "confirmed")}
    block = [{"kind": "not_confirmed", "text": "Not confirmed. A.", "claim_ids": ["c1"], "sources": []}]
    assert any("does not belong" in x for x in writing_rules.check_article(block, claims))  # type: ignore[arg-type]
