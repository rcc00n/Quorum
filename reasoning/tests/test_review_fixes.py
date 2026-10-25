"""Fixes from the 2026-10-24 code review (six reviewers, fourteen verified findings), one test per fix. Dry run."""

from __future__ import annotations

import pytest

from quorum_reasoning import graph, llm, untrusted
from quorum_reasoning.nodes import adjudicate, cluster, critique, extract, frame, research, review_disputed, roundup
from quorum_reasoning.nodes.publish import summary_contradiction
from quorum_reasoning.rules import confirmation, writing_rules
from quorum_reasoning.state import Claim, DocRef, Evidence, Event, initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


def doc(doc_id, source, kind="outlet", **over) -> DocRef:
    d = DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind=kind, flank=over.pop("flank", "left"), tier=over.pop("tier", "major"),
               url=f"https://example.org/{source}/{doc_id}", title="Aid bill passed", lead="Lead.", published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None)
    d.update(over)
    return d


def ev(stance, group, found_by="researcher", document=False) -> Evidence:
    return Evidence(quote="q", document_id=None if document else 2, official_doc_id=1 if document else None, source_id=group, independence_group=group,
                    stance=stance, found_by=found_by, url=f"https://example.org/{group}", title=group, is_document=document)


def claim(cid, eid, kind="fact", status="confirmed", origin=1, evidence=None) -> Claim:
    return Claim(id=cid, event_id=eid, text="x", kind=kind, origin_document_id=origin, evidence=evidence or [], verifier_status=status, verifier_reason="",
                 fact_checker_status=status, fact_checker_reason="", final_status=status, adjudication="")


def event(eid, doc_ids) -> Event:
    return Event(id=eid, document_ids=doc_ids, headline="x", standfirst="", rubric=None, above_bar=True, rank=1, needs_review=False, article=[], drafts=0,
                 versions=[], critic_status=None, critic_notes="", framing={}, review_reason="")


# R1 — a fresh run never continues an existing checkpointed thread
def test_fresh_run_on_an_existing_checkpoint_is_refused(tmp_path):
    ck = str(tmp_path / "ck.sqlite")
    graph.run_local(TOPIC, DAY, dry_run=True, checkpoint_path=ck, attempt=3)
    with pytest.raises(ValueError, match="already has a checkpoint"):
        graph.run_local(TOPIC, DAY, dry_run=True, checkpoint_path=ck, attempt=3)
    from quorum_reasoning import run as run_cli

    assert run_cli.main(["--dry-run", "--quiet", "--checkpoint", "--attempt", "3", "--out", str(tmp_path)]) == 0
    assert run_cli.main(["--dry-run", "--quiet", "--checkpoint", "--attempt", "3", "--out", str(tmp_path)]) == 2


# R2 — a non-string stance is neutral, never a crash
def test_non_string_stance_is_neutral():
    assert untrusted.valid_stance(["supports"]) == "neutral" and untrusted.valid_stance({"v": 1}) == "neutral" and untrusted.valid_stance(None) == "neutral"
    assert untrusted.valid_stance("supports") == "supports"


# R7 — frame always emits both sides; one failed outlet call keeps the others
def test_frame_emits_both_sides_and_survives_one_failed_outlet(monkeypatch):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [doc(1, "fox-news", flank="right"), doc(2, "ny-post", flank="right"), doc(3, "reuters", kind="agency", flank=None, tier=None)]
    st["events"] = [event("ev1", [1, 2, 3])]
    calls = {"n": 0}

    def flaky(task, payload, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429")
        return {"highlights": "h", "omits": "", "wording": "w", "interpretation_label": "a cost"}

    monkeypatch.setattr(llm, "json_task", flaky)
    out = frame.run(st)
    f = out["events"][0]["framing"]
    assert f["left"] == {"highlights": "", "omits": "", "wording": "", "example_url": ""}
    assert f["right"]["example_url"].startswith("https://") and len(f["outlets"]) == 1
    assert out["errors"] and "1 outlet framing call(s) failed" in out["errors"][0]["message"]


# unverified — model-returned source rows carry only the contract's keys
def test_filter_sources_strips_foreign_keys():
    rows = untrusted.filter_sources([{"title": "AP", "url": "https://a", "independence_group": "ap", "quote": "q", "quote_id": 3}, {"title": "x", "url": "https://unknown"}], {"https://a"})
    assert rows == [{"title": "AP", "url": "https://a", "quote": "q", "quote_id": 3}]


# R8 — the critic checks every block's ids against the event's own claims; statements are not facts
def test_critic_rejects_foreign_ids_and_statement_claims_in_fact_blocks():
    own = {"c1": claim("c1", "ev1"), "c2": claim("c2", "ev1", kind="statement")}
    blocks = [
        {"kind": "fact", "text": "Fact.", "claim_ids": ["c2"], "sources": [{"title": "t", "url": "https://x"}]},
        {"kind": "statements", "text": "Officials said so.", "claim_ids": ["c9"], "sources": []},
        {"kind": "not_confirmed", "text": "Not confirmed. Something.", "claim_ids": ["c8"], "sources": []},
    ]
    v = writing_rules.check_article(blocks, own)
    assert any("c2 is a statement" in x for x in v) and any("unknown claim c9" in x for x in v) and any("unknown claim c8" in x for x in v)
    ok = writing_rules.check_article([{"kind": "statements", "text": "The U.S. State Department said talks resume. Lt. Gen. Budanov said 40 drones were launched.", "claim_ids": ["c2"], "sources": []}], own)
    assert ok == [], ok  # abbreviations do not split sentences


# R9 — drafts exhausted: the published article presents no unconfirmed claim as a fact
def test_sanitised_article_demotes_unconfirmed_fact_blocks():
    own = {"c1": claim("c1", "ev1"), "c3": claim("c3", "ev1", status="unverified")}
    blocks = [
        {"kind": "statements", "text": "Said.", "claim_ids": ["c9"], "sources": []},
        {"kind": "fact", "text": "Good fact.", "claim_ids": ["c1"], "sources": [{"title": "t", "url": "https://x"}]},
        {"kind": "fact", "text": "Bad fact.", "claim_ids": ["c3"], "sources": [{"title": "t", "url": "https://x"}]},
        {"kind": "weird", "text": "?", "claim_ids": [], "sources": []},
    ]
    out = critique.sanitise_article(blocks, own)
    assert [b["kind"] for b in out] == ["fact", "statements", "not_confirmed"]
    assert out[0]["claim_ids"] == ["c1"] and out[1]["claim_ids"] == [] and out[2]["sources"] == [] and out[2]["text"] == "Bad fact."


# unverified — summary regex accepts the prompt's own phrasing
@pytest.mark.parametrize("text, above", [("One story out of 17 events crossed the bar today: x.", 1), ("Three of the 17 events crossed the bar.", 3), ("3 stories out of 17 events crossed the bar today.", 3)])
def test_summary_regex_accepts_out_of_phrasing(text, above):
    assert summary_contradiction(text, above) is None
    assert summary_contradiction("Three stories out of 17 events crossed the bar.", 1)


# R12 + military — a party's denial and an attributed-only source are statements in both directions
def test_official_release_and_military_source_never_support_or_contradict():
    release = doc(5, "whitehouse", kind="official", official=True, doc_type="release", flank=None, tier=None)
    isw = doc(6, "isw", kind="military", flank=None, tier=None)
    assert research.evidence_from(release, "The strike did not happen.", "contradicts", "researcher")["stance"] == "statement"
    assert research.evidence_from(isw, "The strike happened.", "supports", "researcher")["stance"] == "statement"
    law = doc(7, "congress-gov", kind="official", official=True, doc_type="law", flank=None, tier=None)
    assert research.evidence_from(law, "The Act appropriates funds.", "supports", "researcher")["stance"] == "supports"


# R11 — a claim the fact-checker could not judge at all is "not double-checked", not disputed
def test_unavailable_fact_checker_gives_unverified_not_disputed_and_no_review():
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [doc(1, "cnn"), doc(2, "reuters", kind="agency")]
    e = event("ev1", [1, 2])
    e["above_bar"] = False
    e["rank"] = None
    st["events"] = [e]
    c = claim("c1", "ev1", status="confirmed", evidence=[ev("supports", "reuters"), ev("supports", "afp")])
    c["fact_checker_status"], c["fact_checker_reason"], c["fact_checker_judged"] = "unverified", "no supporting evidence beyond statements (3 stance call(s) failed for this claim)", 0
    st["claims"] = {"c1": c}
    out = adjudicate.run(st)
    r = out["claims"]["c1"]
    assert r["final_status"] == "unverified" and "not double-checked" in r["adjudication"] and r["resolved_by"] == "dispute"
    assert review_disputed.pending({**st, **out}) == []


# R13 — contradiction-only reason names the contradiction
def test_contradiction_only_reason():
    status, reason = confirmation.verdict([ev("contradicts", "ap"), ev("contradicts", "reuters")])
    assert status == "unverified" and "contradicts" in reason


# unverified — the reviewer may not confirm while any chain contradicts
def test_reviewer_cannot_confirm_over_a_contradiction():
    c = claim("c1", "ev1", status="confirmed", evidence=[ev("supports", "ap"), ev("supports", "cnn"), ev("contradicts", "reuters", found_by="fact_checker")])
    c["fact_checker_status"] = "disputed"
    accepted, _, _, why = review_disputed.validate(c, {"verdict": "confirmed", "decisive_chain": "verifier", "decisive_index": 0, "decisive_quote": "q", "reason": "r"}, None)
    assert accepted is None and "contradicting passage" in why


# R5 — grounding: numbers and negation must agree with the best window
def test_grounding_rejects_renumbered_and_negation_flipped_claims():
    text = "A Russian missile strike killed 5 people in Kharkiv on Monday and wounded 31 others. Kyiv said it would not withdraw troops from Kursk. Russia demanded that Ukraine withdraw troops."
    assert untrusted.grounded_in("A Russian missile strike killed 5 people in Kharkiv", text)
    assert not untrusted.grounded_in("A Russian missile strike killed 31 people in Kharkiv", text)
    assert not untrusted.grounded_in("Kyiv said it would withdraw troops from Kursk", text)
    assert untrusted.grounded_in("Kyiv said it would not withdraw troops from Kursk", text)


# unverified — level-3 documents feed nothing to extraction
def test_extract_skips_level_three_documents(monkeypatch):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [doc(1, "cnn", lead="The Senate passed the bill.", text="The Senate passed the bill."), doc(2, "wapo", access_level=3, lead="Leaked lead text that must not be read.")]
    st["events"] = [event("ev1", [1, 2])]
    seen = {}

    def fake(task, payload, **kw):
        seen["ids"] = [d["id"] for d in payload["documents"]]
        return {"claims": [{"text": "The Senate passed the bill", "kind": "fact", "origin_document_id": 2}]}

    monkeypatch.setattr(llm, "json_task", fake)
    out = extract.run(st)
    assert seen["ids"] == [1] and out["claims"] == {}, "a claim attributed to the level-3 document is dropped: it is not a text source"


# R4 — the merge budget keeps a reserve for the later passes and reports questions it could not ask
def test_cluster_budget_reserve(monkeypatch):
    from quorum_reasoning import config

    monkeypatch.setitem(config.load()["clustering"], "merge_questions_max", 20)
    monkeypatch.setitem(config.load()["clustering"], "key_merge_overlap", 1.1)  # nothing merges in code: every pair is a question
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [doc(i, f"s{i}", title=f"Senate passes aid bill vote {i}", lead=f"Senate aid bill {i}.") for i in range(1, 9)]
    asked = []

    def fake(task, payload, **kw):
        if task == "merge_confirm":
            asked.append(payload.get("mode"))
            return {"same_event": False}
        return {"canonical": payload["title"], "actors": ["senate"], "action": "pass", "object": ["aid bill"], "place": [], "date": None, "numbers": []}

    monkeypatch.setattr(llm, "json_task", fake)
    out = cluster.run(st)
    assert asked.count("pair") == 12, "28 candidate pairs, but pair questions stop at budget (20) minus the reserve (8)"
    assert "budget spent before" in out["steps"][0]["decision"]


# unverified — an event of statements only is labelled so even when the statements were confirmed as said
def test_roundup_statements_only_beats_confirmed():
    e = event("ev1", [1])
    e["needs_review"] = False
    assert roundup.status_label(e, [claim("c1", "ev1", kind="statement", status="confirmed")], [doc(1, "cnn")]) == "Statements only"


def test_roundup_disputed_statement_makes_the_event_disputed():
    # 2026-10-25 (D5 of snapshot v5): Disputed is tested before Confirmed and counts a disputed statement too
    e = event("ev1", [1, 2])
    e["needs_review"] = False
    claims = [claim("c1", "ev1", kind="statement", status="disputed"), claim("c2", "ev1", kind="fact", status="unverified")]
    assert roundup.status_label(e, claims, [doc(1, "cnn"), doc(2, "bbc")]) == "Disputed"
    claims.append(claim("c3", "ev1", kind="fact", status="confirmed"))
    assert roundup.status_label(e, claims, [doc(1, "cnn"), doc(2, "bbc")]) == "Disputed"
    # statements only still comes first, even when one of them is disputed
    only = [claim("c1", "ev1", kind="statement", status="disputed")]
    assert roundup.status_label(e, only, [doc(1, "cnn")]) == "Statements only"


# unverified — hash_mismatch is unknowable when a level-1 page fell back to headline and lead
def test_hash_mismatch_is_null_on_a_lead_fallback():
    from quorum_reasoning.tools.fetch_text import FetchResult

    d = doc(1, "cnn", content_hash="ab" * 32)
    fetched = FetchResult(text="Lead.", quote_text="Aid bill passed\nLead.", content_hash="cd" * 32, access_achieved=2, fetched_at=None, fetcher="lead")
    assert research.evidence_from(d, "Lead.", "supports", "researcher", fetched)["hash_mismatch"] is None


# unverified — already_seen matches official rows by their database id
def test_already_seen_matches_official_rows():
    from quorum_reasoning.tools.corpus import OFFICIAL_ID_OFFSET

    law = doc(OFFICIAL_ID_OFFSET + 7, "congress-gov", kind="official", official=True, doc_type="law")
    c = claim("c1", "ev1", evidence=[research.evidence_from(law, "The Act.", "supports", "researcher")])
    assert c["evidence"][0]["official_doc_id"] == 7 and research.already_seen(c, law, "researcher")
