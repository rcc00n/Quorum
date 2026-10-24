"""The impact bar gates the expensive checks (docs/DECISIONS.md › Selecting major news, bar gate, 2026-10-24).

An event whose three judged points plus the maximum confirmation score fall short of the threshold gets no blind
fact-check and no reviewer: its claims keep the verifier's verdict, "not double-checked", with no `resolved_by`.
Dry run; the fact-checker's model is a recorder that delegates to the dry-run stand-in.
"""

from __future__ import annotations

import pytest

from quorum_reasoning import dryrun, llm
from quorum_reasoning.nodes import adjudicate, fact_check, publish, review_disputed, roundup
from quorum_reasoning.rules import impact_bar
from quorum_reasoning.rules.impact_bar import build_rubric, cannot_reach_bar
from quorum_reasoning.state import Claim, DocRef, Event, initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"
TEXT = "The Senate passed the aid bill 68-30 on Tuesday. More follows here."


def doc(doc_id: int, source: str, text: str = TEXT) -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{source}/{doc_id}", title="t", lead="", published_at="2026-10-21T12:00:00Z",
                  access_level=1, wire_origin=None, text=text)


def event(eid: str, doc_ids: list[int], points: tuple[int, int, int]) -> Event:
    return Event(id=eid, document_ids=doc_ids, headline=eid, standfirst="", rubric=build_rubric(*points, 0, {}), above_bar=False, rank=None,
                 needs_review=False, article=[], drafts=0, versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


def claim(cid: str, eid: str, origin: int, text: str, verifier: str) -> Claim:
    return Claim(id=cid, event_id=eid, text=text, kind="number", origin_document_id=origin, evidence=[],
                 verifier_status=verifier, verifier_reason="v", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")


# --- the rule -----------------------------------------------------------------------------------------------------

@pytest.fixture
def threshold_6(monkeypatch):
    monkeypatch.setattr(impact_bar, "threshold", lambda: 6)


@pytest.mark.parametrize("points, gated", [((1, 1, 1), True), ((2, 1, 1), False), ((1, 1, 0), True), ((2, 2, 1), False), ((0, 0, 0), True)])
def test_cannot_reach_bar(threshold_6, points, gated):
    assert cannot_reach_bar(build_rubric(*points, 0, {})) is gated


def test_confirmation_given_by_evidence_does_not_change_the_gate(threshold_6):
    assert cannot_reach_bar(build_rubric(1, 1, 1, 2, {})) is True  # only the judged points count; confirmation is assumed at its maximum


def test_no_rubric_never_gates(threshold_6):
    assert cannot_reach_bar(None) is False


def test_the_maximum_confirmation_comes_from_point_ranges(threshold_6, monkeypatch):
    monkeypatch.setitem(impact_bar.POINT_RANGES, "confirmation", (0, 3))
    assert cannot_reach_bar({"legal_force": 1, "reach": 1, "irreversibility": 1, "confirmation": 0, "total": 3, "rationale": {}}) is False


# --- the nodes ----------------------------------------------------------------------------------------------------

GATED_CONFIRMED = "The ministry closed the border crossing on Monday"
GATED_DISPUTED = "The ministry reopened the border crossing on Monday"
NORMAL = "The Senate passed the aid bill 68-30 on Tuesday"


@pytest.fixture
def run_through(monkeypatch, threshold_6):
    asked: list[str] = []

    def json_task(task, payload, **kw):
        asked.append(payload["claim"])
        return getattr(dryrun, task)(payload)

    monkeypatch.setattr(llm, "json_task", json_task)
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    border = "The ministry closed the border crossing on Monday. The ministry reopened the border crossing on Monday."
    st["documents"] = [doc(1, "cnn", border), doc(2, "reuters", border), doc(3, "origin"), doc(4, "ap"), doc(5, "afp")]
    st["events"] = [event("gated", [1, 2], (1, 1, 0)), event("normal", [3, 4, 5], (2, 2, 1))]
    st["claims"] = {
        "g1": claim("g1", "gated", 1, GATED_CONFIRMED, "confirmed"),
        "g2": claim("g2", "gated", 1, GATED_DISPUTED, "disputed"),
        "n1": claim("n1", "normal", 3, NORMAL, "unverified"),
    }
    out = fact_check.run(st)
    st["claims"], st["steps"] = out["claims"], out["steps"]
    out = adjudicate.run(st)
    st["claims"], st["events"], st["steps"] = out["claims"], out["events"], st["steps"] + out["steps"]
    return st, out, asked


def test_fact_check_makes_no_call_for_a_gated_event(run_through):
    st, _, asked = run_through
    assert asked and set(asked) == {NORMAL}
    for cid in ("g1", "g2"):
        c = st["claims"][cid]
        assert c["fact_checker_status"] == "unverified" and c["fact_check_skipped"] is True
        assert c["fact_checker_reason"] == "skipped: event cannot reach the impact bar (2 + 2 < 6); not double-checked"
        assert not [ev for ev in c["evidence"] if ev["found_by"] == "fact_checker"]
    assert "fact_check_skipped" not in st["claims"]["n1"]
    gated_step = next(s for s in st["steps"] if s["node"] == "fact_check" and s["event_id"] == "gated")
    assert gated_step["decision"] == "skipped: event cannot reach the impact bar; 2 claims not double-checked"


def test_adjudicate_keeps_the_verifier_verdict_without_resolved_by(run_through):
    st, _, _ = run_through
    for cid, status in (("g1", "confirmed"), ("g2", "disputed")):
        c = st["claims"][cid]
        assert c["final_status"] == status
        assert c["adjudication"] == "fact-check skipped: event cannot reach the impact bar; the verifier's verdict stands, not double-checked"
        assert "resolved_by" not in c
    assert st["claims"]["n1"]["resolved_by"] in ("agreement", "dispute")
    gated_step = next(s for s in st["steps"] if s["node"] == "adjudicate" and s["event_id"] == "gated")
    assert "0 disagreement(s)" in gated_step["decision"]


def test_review_disputed_does_not_take_gated_claims(run_through):
    st, _, _ = run_through
    assert all(c["event_id"] != "gated" for c in review_disputed.pending(st))
    assert review_disputed.is_disagreement(st["claims"]["g2"]), "it would have been a disagreement without the gate"


def test_publish_omits_resolved_by_and_the_marker_for_a_gated_claim(run_through):
    st, _, _ = run_through
    gated = publish.claim_view(st["claims"]["g1"])
    assert gated["fact_checker"] == "unverified" and gated["status"] == "confirmed"
    assert "resolved_by" not in gated and "fact_check_skipped" not in gated
    normal = publish.claim_view(st["claims"]["n1"])
    assert normal["resolved_by"] in ("agreement", "dispute") and "fact_check_skipped" not in normal
    assert set(gated) == set(normal) - {"resolved_by"}, "no new keys on an exported claim"


def test_roundup_label_follows_the_verifier_verdict(run_through):
    st, _, _ = run_through
    e = next(e for e in st["events"] if e["id"] == "gated")
    assert not e["above_bar"]
    claims = [c for c in st["claims"].values() if c["event_id"] == "gated"]
    docs = [d for d in st["documents"] if d["id"] in e["document_ids"]]
    assert roundup.status_label(e, claims, docs) == "Confirmed"
    only_disputed = [c for c in claims if c["id"] == "g2"]
    assert roundup.status_label(e, only_disputed, docs) == "Disputed"
