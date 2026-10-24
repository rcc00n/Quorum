"""End-to-end dry run on the fixture day, plus the escalation path on a synthetic state.

The dry run spends no credits: every model task is answered by dryrun.py. What is asserted is the shape of
the run — the loops fire, the trace shows them, the snapshot matches docs/ARCHITECTURE.md § 8 — not the
wording of any article.
"""

from __future__ import annotations

import os

import pytest

from quorum_reasoning import graph
from quorum_reasoning.nodes import adjudicate, escalate
from quorum_reasoning.rules.impact_bar import build_rubric
from quorum_reasoning.state import initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


@pytest.fixture(scope="module")
def state():
    os.environ["QUORUM_DRY_RUN"] = "1"
    return graph.run_local(TOPIC, DAY, dry_run=True)


def steps(state, node: str, event_id: str | None = "any"):
    return [s for s in state["steps"] if s["node"] == node and (event_id == "any" or s["event_id"] == event_id)]


def test_every_node_left_a_trace_row(state):
    nodes = {s["node"] for s in state["steps"]}
    assert {"plan", "cluster", "score_importance", "extract_claims", "research", "verify", "fact_check", "adjudicate", "review_disputed", "frame", "write", "critique", "roundup", "publish"} <= nodes
    for s in state["steps"]:
        assert s["decision"], s


def test_clustering_finds_the_four_events(state):
    members = sorted(sorted(e["document_ids"]) for e in state["events"])
    assert members == [[101, 102, 103, 104, 105, 106, 107, 114], [108, 109], [110], [111, 112, 113]]


def test_verify_sends_thin_claims_back_to_research(state):
    second_rounds = [s for s in steps(state, "research") if s["iteration"] == 2]
    assert second_rounds, "no event got a second research round"
    for s in second_rounds:
        assert "widened" in s["reason"]
    assert max(state["research_rounds"].values()) == 2
    assert any(s["iteration"] == 2 for s in steps(state, "verify"))


def test_fact_checker_is_blind_and_disagreements_go_to_the_third_reviewer(state):
    claims = list(state["claims"].values())
    assert all(c["fact_checker_status"] for c in claims)
    disagreed = [c for c in claims if c["verifier_status"] != c["fact_checker_status"]]
    assert disagreed, "the dry run should produce at least one verifier/fact-checker disagreement"
    for c in disagreed:
        assert "verifier says" in c["adjudication"]
        assert c["review_passes"] == 1 and c["resolved_by"] in ("reviewer", "dispute")
        if c["resolved_by"] == "reviewer":
            assert c["final_status"] == c["reviewer_status"] in (c["verifier_status"], c["fact_checker_status"])
            assert c["reviewer_quote"] and any(c["reviewer_quote"] in ev["quote"] for ev in c["evidence"])
        else:
            assert c["final_status"] == "disputed"
    review_steps = steps(state, "review_disputed")
    assert len([s for s in review_steps if s["event_id"]]) == len(disagreed)
    # the fixture's one disagreement is a retrieval difference (the fact-checker found nothing): resolved, all three verdicts kept
    assert any(c["resolved_by"] == "reviewer" for c in disagreed)


def test_signed_documents_confirm_and_statements_do_not(state):
    by_text = {c["text"]: c for c in state["claims"].values()}
    law = by_text["The Act appropriates funds over two fiscal years for air-defense interceptors, artillery ammunition and spare parts for vehicles in service"]
    assert law["final_status"] == "confirmed" and any(ev["is_document"] for ev in law["evidence"])
    release = by_text["Deliveries will begin within weeks"]
    assert release["kind"] == "statement" and release["final_status"] == "unverified"
    assert all(ev["stance"] == "statement" for ev in release["evidence"])
    contradicted = by_text["the first shipments are expected within three weeks"]
    assert any(ev["stance"] == "contradicts" and ev["title"] == "Reuters" for ev in contradicted["evidence"])


def test_bar_and_cap(state):
    above = [e for e in state["events"] if e["above_bar"]]
    assert [e["rank"] for e in above] == [1, 2]
    assert {tuple(sorted(e["document_ids"]))[0] for e in above} == {101, 111}
    below = [e for e in state["events"] if not e["above_bar"]]
    assert {e["rubric"]["total"] for e in below} <= {0, 1, 2, 3, 4, 5}
    assert all(e["rubric"]["confirmation"] >= 1 for e in above)


def test_critic_rejects_the_planted_violation_then_approves(state):
    for e in (e for e in state["events"] if e["above_bar"]):
        crit = steps(state, "critique", e["id"])
        assert [s["iteration"] for s in crit] == [1, 2]
        assert "sweeping" in crit[0]["reason"] and "approved" in crit[1]["decision"]
        assert e["drafts"] == 2 and e["critic_status"] == "approved" and not e["needs_review"]
        assert [v["critic_status"] for v in e["versions"]] == ["rejected", "approved"]


def test_articles_follow_the_block_rules(state):
    order = ["fact", "context", "statements", "not_confirmed"]
    for e in (e for e in state["events"] if e["above_bar"]):
        kinds = [b["kind"] for b in e["article"]]
        assert kinds == sorted(kinds, key=order.index)
        for b in e["article"]:
            if b["kind"] in ("fact", "context"):
                assert b["sources"] and all(state["claims"][cid]["final_status"] == "confirmed" for cid in b["claim_ids"])
            if b["kind"] == "statements":
                assert b["text"].startswith("What follows are statements")


def test_snapshot_matches_the_contract(state):
    snap = state["snapshot"]
    assert snap["schema_version"] == "1.0" and snap["status"] == "ok"
    assert {"topic_id", "edition_date", "run_id", "version", "bar", "summary", "sources_missing", "stories", "roundup", "trace"} <= set(snap)
    assert [s["rank"] for s in snap["stories"]] == [1, 2]
    story = snap["stories"][0]
    assert {"event_id", "headline", "standfirst", "reading_minutes", "rubric", "photo", "article", "claims", "spectrum", "needs_review", "trace_ref"} <= set(story)
    assert set(story["spectrum"]["coverage"]) == {"major_left", "minor_left", "major_right", "minor_right", "center"}
    assert story["spectrum"]["coverage"]["minor_left"] == [0, 0]  # the fixture has no minor-left outlet
    assert snap["roundup"]["count"] == 2 and snap["roundup"]["empty_day"] is False
    for group in snap["roundup"]["groups"]:
        for item in group["items"]:
            assert item["line"] and item["sources"] and item["status"]
    assert snap["errors"] == []
    assert len(snap["trace"]) == len(state["steps"])


def test_run_is_deterministic():
    again = graph.run_local(TOPIC, DAY, dry_run=True, attempt=2)
    first = graph.run_local(TOPIC, DAY, dry_run=True, attempt=3)
    strip = lambda snap: {k: v for k, v in snap.items() if k not in ("run_id", "trace", "generated_at")}  # noqa: E731 — generated_at is wall-clock
    a, b = strip(again["snapshot"]), strip(first["snapshot"])
    a["stories"] = [{k: v for k, v in s.items() if k != "trace_ref"} for s in a["stories"]]
    b["stories"] = [{k: v for k, v in s.items() if k != "trace_ref"} for s in b["stories"]]
    assert a == b


def test_escalation_when_points_cross_the_bar_without_a_confirmed_claim():
    """Synthetic: one event scores 2+2+2 on points, its only claim is supported by one group → confirmation 1,
    total 7, above the threshold — but nothing is confirmed, so it must be escalated, not published."""
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["events"] = [
        {
            "id": "ev1", "document_ids": [1], "headline": "x", "standfirst": "", "rubric": build_rubric(2, 2, 2, 0, {}),
            "above_bar": False, "rank": None, "needs_review": False, "article": [], "drafts": 0, "versions": [],
            "critic_status": None, "critic_notes": "", "framing": {}, "review_reason": "",
        }
    ]
    st["claims"] = {
        "c1": {
            "id": "c1", "event_id": "ev1", "text": "x", "kind": "fact", "origin_document_id": 1,
            "evidence": [{"quote": "", "document_id": 2, "official_doc_id": None, "independence_group": "reuters", "stance": "supports",
                          "found_by": "researcher", "url": "", "title": "Reuters", "is_document": False}],
            "verifier_status": "unverified", "verifier_reason": "", "fact_checker_status": "unverified", "fact_checker_reason": "",
            "final_status": None, "adjudication": "",
        }
    }
    out = adjudicate.run(st)
    e = out["events"][0]
    assert e["rubric"]["total"] == 7 and e["needs_review"] and not e["above_bar"]
    assert adjudicate.route({**st, **out}) == "escalate"
    esc = escalate.run({**st, **out})
    assert esc["steps"][0]["event_id"] == "ev1" and "reported, not confirmed" in esc["steps"][0]["decision"]


def test_graph_draws_itself():
    m = graph.mermaid()
    for node in ("plan", "verify", "research", "fact_check", "adjudicate", "review_disputed", "escalate", "critique", "write", "roundup", "publish"):
        assert node in m
