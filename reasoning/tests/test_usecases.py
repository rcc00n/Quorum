"""Use-case walkthroughs (review 2026-10-23, workstream D): one fixture day per product scenario.

Each test runs the whole graph in dry run on a fictional fixture day built so the deterministic
stand-ins (dryrun.py) drive the scenario, and asserts the behaviour DECISIONS.md and
docs/ARCHITECTURE.md define. Where those documents do not define the behaviour the test is marked
xfail with the open question; see docs/reviews/2026-10-23-reasoning-review.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quorum_reasoning import graph
from quorum_reasoning.nodes import plan as plan_node
from quorum_reasoning.state import DocRef

USECASES = Path(__file__).resolve().parent.parent / "quorum_reasoning" / "fixtures" / "usecases"


def run_day(monkeypatch, name: str):
    """Runs the graph over one use-case day through the real fixture loader (QUORUM_FIXTURE), so loader
    behaviour such as the superseded marking is part of what these tests cover."""
    data = json.loads((USECASES / f"{name}.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("QUORUM_FIXTURE", f"usecases/{name}")
    os.environ["QUORUM_DRY_RUN"] = "1"
    return graph.run_local(data["topic_id"], data["edition_date"], dry_run=True)


def event_claims(state, event_id):
    return [c for c in state["claims"].values() if c["event_id"] == event_id]


def roundup_items(state):
    return [item for group in state["snapshot"]["roundup"]["groups"] for item in group["items"]]


# 1. Quiet day — DECISIONS.md › Selecting major news: "No minimum", the roundup carries every event.
def test_quiet_day_is_stated_plainly_and_roundup_carries_everything(monkeypatch):
    state = run_day(monkeypatch, "quiet_day")
    assert not any(e["above_bar"] for e in state["events"])
    snap = state["snapshot"]
    assert snap["status"] == "empty"
    assert snap["stories"] == []
    assert snap["roundup"]["empty_day"] is True
    assert snap["roundup"]["count"] == len(state["events"]) == 3
    assert "No story crossed the bar" in snap["summary"]


# 2. Breaking event with contradictory reports — DECISIONS.md › Principles for handling facts:
# supporting and contradicting evidence both exist → disputed, and the page shows both chains.
def test_contradictory_reports_end_disputed_with_both_chains_visible(monkeypatch):
    state = run_day(monkeypatch, "disputed_breaking")
    assert len(state["events"]) == 1
    stories = state["snapshot"]["stories"]
    assert len(stories) == 1, "the event scores 2 reach + 2 irreversibility + 2 confirmation = 6: above the bar"
    claims = stories[0]["claims"]
    disputed = [c for c in claims if c["status"] == "disputed"]
    assert disputed, "the destruction claim must end disputed"
    for c in disputed:
        stances = {ev["stance"] for ev in c["evidence"]}
        assert {"supports", "contradicts"} <= stances, "both chains must be visible"
        finders = {ev["found_by"] for ev in c["evidence"]}
        assert {"researcher", "fact_checker"} <= finders, "both the verifier's and the fact-checker's chains are kept"
    confirmed = [c for c in claims if c["status"] == "confirmed"]
    assert confirmed, "the uncontradicted restoration claim is confirmed by two independent groups"


# 3. Level-2/level-3 coverage only — DECISIONS.md › Sources: paywalled sources participate at level 2
# (headline and lead); level 3 is coverage only. Two independent leads still confirm.
def test_leads_alone_confirm_and_level3_contributes_no_evidence(monkeypatch):
    state = run_day(monkeypatch, "leads_only")
    assert len(state["events"]) == 1
    claims = list(state["claims"].values())
    confirmed = [c for c in claims if c["final_status"] == "confirmed"]
    assert confirmed, "two independent level-2 leads must confirm the claim"
    for c in claims:
        for ev in c["evidence"]:
            assert ev["independence_group"] != "ap", "a level-3 source has no readable text and cannot be evidence"
    e = state["events"][0]
    assert 9304 in e["document_ids"], "the level-3 document still counts as coverage of the event"
    items = roundup_items(state)
    assert items and items[0]["status"] == "confirmed"


# 4. Single-source scoop — DECISIONS.md › Selecting major news: confirmation is a gate (never a story)
# and the roundup status vocabulary is confirmed / disputed / statements only / single source.
def test_scoop_never_crosses_bar(monkeypatch):
    state = run_day(monkeypatch, "single_source_scoop")
    e = state["events"][0]
    assert e["rubric"]["confirmation"] == 0
    assert not e["above_bar"]
    assert state["snapshot"]["stories"] == []


def test_scoop_roundup_status_is_single_source(monkeypatch):
    """Fails on HEAD: status_label answers "unverified", a label DECISIONS.md does not define.
    Finding D4; the proposed fix (ws_d/changes.diff) labels an event whose documents all share one
    independence group "single source"."""
    state = run_day(monkeypatch, "single_source_scoop")
    items = roundup_items(state)
    assert len(items) == 1
    assert items[0]["status"] == "single source"


# 5. Retraction within the day — collectors/schema.sql sets documents.supersedes_id on a re-fetch
# with a changed hash. Neither DECISIONS.md nor ARCHITECTURE.md says what reasoning does with it,
# and the code never reads it: question for Yelysei (review report, D5).
def test_retraction_correction_at_least_blocks_confirmation(monkeypatch):
    state = run_day(monkeypatch, "retraction")
    by_text = {c["text"]: c for c in state["claims"].values()}
    wrong = by_text["Odesa port bridge collapse killed four workers"]
    assert wrong["final_status"] != "confirmed", "the correction must at least keep the retracted figure unconfirmed"
    assert any(ev["stance"] == "contradicts" for ev in wrong["evidence"])


def test_retraction_superseded_document_is_not_evidence(monkeypatch):
    """D3, decided 2026-10-24 (DECISIONS.md log): a superseded document stays in spread but is excluded
    from evidence, confirmation and extraction."""
    state = run_day(monkeypatch, "retraction")
    for c in state["claims"].values():
        assert c["origin_document_id"] != 9501, "a claim must not originate from retracted text"
        for ev in c["evidence"]:
            assert ev["document_id"] != 9501, "a document superseded within the day should not support a claim"
    assert any(9501 in e["document_ids"] for e in state["events"]), "the superseded publication still counts for spread"


def test_roundup_label_disputed_exists():
    """D2: DECISIONS.md › Selecting major news lists the roundup status "disputed"; status_label must be
    able to return it. Unit-level since 2026-10-24: under the origin-group rule the retraction fixture's
    event escalates ("Reported, not confirmed" outranks "Disputed"), which is its own test above."""
    from quorum_reasoning.nodes.roundup import GROUP_ORDER, status_label

    assert "Disputed" in GROUP_ORDER
    e = {"needs_review": False}
    claim = {"final_status": "disputed", "kind": "fact", "evidence": []}
    docs = [
        {"independence_group": "cnn", "wire_origin": None},
        {"independence_group": "npr", "wire_origin": None},
    ]
    assert status_label(e, [claim], docs) == "Disputed"


# 6. Official release with no independent coverage — DECISIONS.md › Principles for handling facts:
# a release is the party's words, never evidence for its own content.
def test_release_without_coverage_stays_statements_only(monkeypatch):
    state = run_day(monkeypatch, "statements_only")
    e = state["events"][0]
    claims = event_claims(state, e["id"])
    assert claims and all(c["kind"] == "statement" for c in claims)
    assert all(c["final_status"] == "unverified" for c in claims)
    for c in claims:
        assert all(ev["stance"] == "statement" for ev in c["evidence"]), "a release supports nothing, not even itself"
    assert e["rubric"]["legal_force"] == 1, "a release is an official statement (1), not an adopted document (2)"
    assert not e["above_bar"]
    items = roundup_items(state)
    assert items[0]["status"] == "statements only"


# 7. Two events, same actor, same day — clustering must keep them apart (DECISIONS.md › MVP scope:
# grouping of publications about one event, not about one actor).
def test_same_actor_two_events_stay_apart(monkeypatch):
    state = run_day(monkeypatch, "same_actor")
    members = sorted(sorted(e["document_ids"]) for e in state["events"])
    assert members == [[9701, 9702], [9703, 9704]]


# 8. More than ten events above the bar — DECISIONS.md › Selecting major news: up to ten a day,
# ordered by total then confirmation; the rest go to the roundup.
def test_cap_keeps_ten_ordered_by_total_then_confirmation(monkeypatch):
    state = run_day(monkeypatch, "cap_overflow")
    assert len(state["events"]) == 12
    above = [e for e in state["events"] if e["above_bar"]]
    assert len(above) == 10
    above.sort(key=lambda e: e["rank"])
    assert [e["rank"] for e in above] == list(range(1, 11))
    totals = [e["rubric"]["total"] for e in above]
    assert totals == sorted(totals, reverse=True)
    assert totals[:3] == [8, 8, 8]
    dropped = [e for e in state["events"] if not e["above_bar"]]
    assert len(dropped) == 2
    assert all(e["rubric"]["total"] == 6 for e in dropped), "the cap drops the lowest-scored events that still cross the bar"
    assert all(e["rubric"]["total"] >= 6 and e["rubric"]["confirmation"] >= 1 for e in dropped), "they crossed the bar; only the cap excluded them"
    assert state["snapshot"]["roundup"]["count"] == 2
