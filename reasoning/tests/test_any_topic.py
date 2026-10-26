"""Any topic a user types must give a dry run that completes with an honest result (2026-10-26): a slug with no
documents in the window, a thin topic, a topic whose name, terms and documents are not ASCII, and a window whose only
documents are official ones the seed rule keeps as evidence. Whole graph, dry stand-ins, Zetaris rows faked as
strings (the shape agent/tools_zetaris.run_sql returns)."""

from __future__ import annotations

import json

import pytest

from quorum_reasoning import graph, topics
from quorum_reasoning.tools import corpus

DAY = "2026-10-26"
START, _END = corpus._edition_window(DAY)


def _row(i: int, src: str, title: str, lead: str = "", *, kind: str = "outlet", flank: str | None = "left") -> dict:
    return {"id": str(i), "source_id": src, "source_name": src.title(), "independence_group": src, "kind": kind, "flank": flank, "tier": "major" if flank else None,
            "url": f"https://example.org/{src}/{i}", "canonical_url": f"https://example.org/{src}/{i}", "title": title, "lead": lead,
            "published_at": "2026-10-25 20:00:00.0", "fetched_at": "2026-10-25 20:05:00.0", "access_level": "2", "wire_origin": None,
            "supersedes_id": None, "content_hash": "ab" * 32, "topic_match": "title"}


def _official(i: int, title: str, text: str, doc_type: str = "release", src: str = "federal-register") -> dict:
    return {**_row(i, src, title, kind="official", flank=None), "doc_type": doc_type, "text": text, "lead": ""}


def _fake_zetaris(monkeypatch, *, topic_row: dict | None, documents: list[dict], official: list[dict]) -> list[str]:
    seen: list[str] = []

    def fake(sql: str, limit: int):
        seen.append(sql)
        if ".topics WHERE id" in sql:
            return [topic_row] if topic_row else []
        if f"TIMESTAMP '{START}'" not in sql:
            return []  # the previous edition windows (research.previous_days) are empty here
        return list(official) if "official_docs" in sql else list(documents)

    monkeypatch.setattr(corpus, "_run_sql", fake)
    return seen


def _run(slug: str) -> dict:
    state = graph.run_local(slug, DAY, dry_run=True, corpus="zetaris")
    return state


def _plan_row(state: dict) -> dict:
    return next(s for s in state["steps"] if s["node"] == "plan")


def _roundup_items(snapshot: dict) -> list[dict]:
    return [i for g in snapshot["roundup"]["groups"] for i in g["items"]]


def test_a_typed_topic_with_no_documents_completes_empty_and_says_zero(monkeypatch):
    slug = topics.slug_for("Mars sample return mission")
    assert slug == "mars-sample-return-mission"
    seen = _fake_zetaris(monkeypatch, topic_row=None, documents=[], official=[])
    state = _run(slug)
    snap = state["snapshot"]
    assert snap["status"] == "empty" and snap["errors"] == [] and snap["stories"] == []
    assert snap["roundup"] == {"empty_day": True, "count": 0, "groups": []}
    assert _plan_row(state)["decision"].startswith("0 documents from 0 sources, 0 official")
    assert not any(".topics" in sql for sql in seen), "no official document: the topic's terms are not read"
    json.dumps(snap, ensure_ascii=False)


def test_a_thin_topic_completes_with_its_two_documents_in_the_roundup(monkeypatch):
    docs = [
        _row(1, "guardian", "UN climate talks stall over finance", "Negotiators failed to agree on emissions targets."),
        _row(2, "foxnews", "Carbon tax plan draws fire", "Critics say the climate levy would raise prices.", flank="right"),
    ]
    _fake_zetaris(monkeypatch, topic_row={"id": "climate-policy", "name": "Climate policy", "query_terms": "{climate,emissions,carbon}"}, documents=docs, official=[])
    state = _run("climate-policy")
    snap = state["snapshot"]
    assert snap["status"] == "empty" and snap["errors"] == []
    assert len(state["events"]) == 2 and snap["roundup"]["count"] == 2
    assert {s["url"] for i in _roundup_items(snap) for s in i["sources"]} == {d["url"] for d in docs}


def test_a_non_ascii_topic_completes_and_the_seed_rule_matches_unicode_words(monkeypatch):
    topic_row = {"id": "moldova-elections", "name": "Выборы в Молдове — Zürich «test»", "query_terms": '{"Молдове","выборы","Zürich"}'}
    docs = [
        _row(1, "cnn", "Выборы в Молдове: партия лидирует", "Подсчёт голосов «продолжается» — ЦИК."),
        _row(2, "foxnews", "Zürich observers report on the Moldova vote", "Beobachter aus Zürich: «fair».", flank="right"),
    ]
    official = [
        _official(7, "Выборы в Молдове: итоги ЦИК", "SUMMARY: ЦИК опубликовала итоги.\n", src="cec-md"),
        _official(8, "Ohio Regulatory Program", "SUMMARY: OSM approves an amendment to the Ohio program.\n", doc_type="law"),
    ]
    _fake_zetaris(monkeypatch, topic_row=topic_row, documents=docs, official=official)
    state = _run("moldova-elections")
    snap = state["snapshot"]
    assert snap["status"] in ("empty", "ok") and snap["errors"] == []
    row = _plan_row(state)
    assert "official documents: 2 total, 1 seed-eligible (title 1 / abstract 0), 1 evidence only (no topic term in title or abstract)" in row["decision"]
    off = corpus.OFFICIAL_ID_OFFSET
    members = {i for e in state["events"] for i in e["document_ids"]}
    assert off + 7 in members and off + 8 not in members
    cited = {s["url"] for i in _roundup_items(snap) for s in i["sources"]}
    assert "https://example.org/federal-register/8" not in cited, "an evidence-only document is never a roundup item or a source of one"
    text = json.dumps(snap, ensure_ascii=False)
    assert "Молдове" in text and json.loads(text)["topic_id"] == "moldova-elections"


def test_a_window_of_off_topic_official_documents_only_has_no_event_and_says_why(monkeypatch):
    official = [
        _official(6117, "Ohio Regulatory Program", "SUMMARY: OSM approves an amendment to the Ohio regulatory program.\n", doc_type="law"),
        _official(6115, "Modernizing the Ability of Consumers To Control Robocalls", "SUMMARY: The Commission seeks comment on robocalls.\n"),
    ]
    terms = '{"artificial intelligence","AI act","export controls",semiconductors}'
    _fake_zetaris(monkeypatch, topic_row={"id": "ai-regulation-export-controls", "name": "AI Regulation", "query_terms": terms}, documents=[], official=official)
    state = _run("ai-regulation-export-controls")
    snap = state["snapshot"]
    assert snap["status"] == "empty" and snap["errors"] == [] and state["events"] == []
    assert snap["roundup"]["count"] == 0
    assert "official documents: 2 total, 0 seed-eligible (title 0 / abstract 0), 2 evidence only" in _plan_row(state)["decision"]
    clustered = next(s for s in state["steps"] if s["node"] == "cluster")
    assert clustered["decision"].startswith(
        "0 events from 0 documents (2 official documents evidence only by the seed rule, see plan: 0 joined an event, 2 in no event; "
        "no seed document in the window, nothing clustered)"
    )


def test_a_topic_without_a_row_seeds_no_official_event_but_its_document_may_join_the_outlet_story(monkeypatch):
    docs = [_row(1, "cnn", "Mars sample return mission faces cuts", "NASA weighs options for the sample return.")]
    official = [_official(9, "Mars Sample Return Program Review", "SUMMARY: NASA reviews the Mars sample return program.\n", src="nasa")]
    _fake_zetaris(monkeypatch, topic_row=None, documents=docs, official=official)
    state = _run("mars-sample-return-mission")
    row = _plan_row(state)
    assert "1 evidence only (topic terms unavailable: no topics row for mars-sample-return-mission; no official document seeds an event)" in row["decision"]
    assert state["snapshot"]["errors"] == [] and len(state["events"]) == 1
    assert state["events"][0]["document_ids"] == [1, corpus.OFFICIAL_ID_OFFSET + 9], "the review joins the outlet's event; it starts none"
    assert state["snapshot"]["roundup"]["count"] == 1
    cluster_row = next(s for s in state["steps"] if s["node"] == "cluster")
    assert "(1 official documents evidence only by the seed rule, see plan: 1 joined an event, 0 in no event)" in cluster_row["decision"]


def test_an_evidence_only_document_alone_on_its_subject_is_no_roundup_item(monkeypatch):
    docs = [_row(1, "cnn", "UN climate talks stall over finance", "Negotiators failed to agree on emissions targets.")]
    official = [_official(9, "Mars Sample Return Program Review", "SUMMARY: NASA reviews the Mars sample return program.\n", src="nasa")]
    _fake_zetaris(monkeypatch, topic_row={"id": "climate-policy", "name": "Climate policy", "query_terms": "{climate,emissions}"}, documents=docs, official=official)
    state = _run("climate-policy")
    assert [e["document_ids"] for e in state["events"]] == [[1]]
    cited = {s["url"] for i in _roundup_items(state["snapshot"]) for s in i["sources"]}
    assert cited == {docs[0]["url"]} and state["snapshot"]["roundup"]["count"] == 1


def test_a_failed_topics_lookup_makes_the_run_partial_not_a_crash(monkeypatch):
    docs = [_row(1, "cnn", "AI chips export controls tightened", "Commerce acts on semiconductors.")]
    official = [_official(10, "Export Controls on AI Chips", "SUMMARY: BIS revises export controls.\n", doc_type="law")]
    seen = _fake_zetaris(monkeypatch, topic_row=None, documents=docs, official=official)

    real = corpus._run_sql

    def failing(sql, limit):
        if ".topics WHERE id" in sql:
            seen.append(sql)
            raise RuntimeError("connection refused")
        return real(sql, limit)

    monkeypatch.setattr(corpus, "_run_sql", failing)
    state = _run("ai-regulation-export-controls")
    snap = state["snapshot"]
    assert snap["status"] == "partial"
    assert any(e["node"] == "plan" and "topics lookup failed (RuntimeError)" in e["message"] for e in snap["errors"])
    assert state["events"] and all(1 in e["document_ids"] for e in state["events"]), "the official document seeds no event of its own"


@pytest.mark.parametrize("phrase", ["Mars sample return mission", "Élections en Côte d’Ivoire", "Выборы в Молдове", "北京"])
def test_typed_phrases_give_slugs_the_corpus_accepts(monkeypatch, phrase):
    slug = topics.slug_for(phrase)
    _fake_zetaris(monkeypatch, topic_row=None, documents=[], official=[])
    assert corpus.load_documents(slug, DAY, corpus="zetaris") == []
    assert corpus.topic_terms_sql(slug).endswith(f"WHERE id = '{slug}'")
