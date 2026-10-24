"""Quote binding, fetch provenance and Zetaris value typing (work items A5, A6, B1.1, B1.6; 2026-10-24).

Dry run only, no network. The Zetaris rows are the string shapes from Anastasia's real result
(collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json on data-collection@c4fcd69): every column a
string, timestamps `2026-10-24 01:09:20.0`, ids `"217"`, levels `"1"`, NULL as None.
"""

from __future__ import annotations

import json
import os
import sys
import types

import pytest

from quorum_reasoning import graph
from quorum_reasoning.nodes import research
from quorum_reasoning.state import DocRef
from quorum_reasoning.tools import corpus, fetch_text

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


def make_doc(doc_id: int, **over) -> DocRef:
    base = dict(
        id=doc_id, source_id="cnn", source_name="CNN", independence_group="cnn", kind="outlet", flank="left", tier="major",
        url=f"https://example.org/{doc_id}", title="The Senate passed the bill 68-30", lead="Officials said deliveries start soon. The vote was 68-30.",
        published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None,
    )
    base.update(over)
    return DocRef(**base)  # type: ignore[typeddict-item]


# --- A5: every evidence row is bound to the text it was cut from ----------------------------------------


@pytest.fixture(scope="module")
def state():
    os.environ["QUORUM_DRY_RUN"] = "1"
    return graph.run_local(TOPIC, DAY, dry_run=True)


def test_every_evidence_row_has_offsets_that_resolve_to_its_quote(state):
    by_id = {d["id"]: d for d in state["documents"]}
    rows = [ev for c in state["claims"].values() for ev in c["evidence"]]
    assert rows
    for ev in rows:
        did = ev["document_id"] if ev["document_id"] is not None else ev["official_doc_id"]
        doc = by_id.get(did) or by_id[did + corpus.OFFICIAL_ID_OFFSET]  # fixture official ids are not namespaced; Zetaris ones are
        fetched = fetch_text.fetch_result(doc, dry_run=True)
        assert fetched is not None
        assert ev["char_start"] is not None and ev["char_end"] > ev["char_start"], ev
        assert fetched.quote_text[ev["char_start"] : ev["char_end"]] == ev["quote"]  # verify_quote's rule, code points
        assert ev["content_hash_at_quote"] == fetched.content_hash and len(ev["content_hash_at_quote"]) == 64
        assert ev["access_achieved"] == (2 if ev.get("by_headline") else 1)
        assert ev["source_id"] == doc["source_id"]
        assert ev["hash_mismatch"] is None  # fixture rows carry no stored content_hash to compare


def test_level_two_offsets_index_title_newline_lead():
    doc = make_doc(5, access_level=2)
    fetched = fetch_text.fetch_result(doc, dry_run=True)
    assert fetched.access_achieved == 2 and fetched.quote_text == doc["title"] + "\n" + doc["lead"]
    ev = research.evidence_from(doc, "The vote was 68-30.", "supports", "researcher", fetched)
    assert ev["by_headline"] is True
    assert fetched.quote_text[ev["char_start"] : ev["char_end"]] == "The vote was 68-30."
    assert ev["content_hash_at_quote"] == fetch_text.content_hash(doc["title"], doc["lead"], None)


def test_content_hash_matches_the_collectors_formula():
    # collectors/common.py::content_hash: sha256(title + "\n" + lead + "\n" + body[:2000]); the level-2 hash omits the body
    import hashlib

    title, lead, body = "T", "L", "b" * 3000
    assert fetch_text.content_hash(title, lead, body) == hashlib.sha256(("T\nL\n" + "b" * 2000).encode()).hexdigest()
    assert fetch_text.content_hash(title, None, None) == hashlib.sha256("T\n\n".encode()).hexdigest()


def test_hash_mismatch_is_flagged_when_the_page_changed_since_collection():
    doc = make_doc(7, text="The Senate passed the bill 68-30. More text here.", content_hash="0" * 64, fetched_at="2026-10-21T13:00:00Z")
    fetched = fetch_text.fetch_result(doc, dry_run=True)
    ev = research.evidence_from(doc, "The Senate passed the bill 68-30.", "supports", "researcher", fetched)
    assert ev["hash_mismatch"] is True and ev["fetched_at"] == "2026-10-21T13:00:00Z"
    same = make_doc(8, text=doc["text"], content_hash=fetched.content_hash)
    ev2 = research.evidence_from(same, "The Senate passed the bill 68-30.", "supports", "researcher", fetch_text.fetch_result(same, dry_run=True))
    assert ev2["hash_mismatch"] is False


def test_quote_not_found_verbatim_leaves_offsets_null_not_invented():
    doc = make_doc(9, text="Something else entirely.")
    fetched = fetch_text.fetch_result(doc, dry_run=True)
    ev = research.evidence_from(doc, "A sentence that is not in the text.", "supports", "researcher", fetched)
    assert ev["char_start"] is None and ev["char_end"] is None


def test_snapshot_exports_the_binding(state):
    rows = [ev for s in state["snapshot"]["stories"] for c in s["claims"] for ev in c["evidence"]]
    assert rows
    for ev in rows:
        assert {"source_id", "document_id", "official_doc_id", "char_start", "char_end", "content_hash_at_quote", "access_achieved", "fetched_at", "hash_mismatch"} <= set(ev)
        assert (ev["document_id"] is None) != (ev["official_doc_id"] is None)


def test_collectors_path_env_points_the_shared_fetcher_at_a_checkout(tmp_path, monkeypatch):
    """QUORUM_COLLECTORS_PATH names a read-only checkout of data-collection: its `collectors` package becomes
    the fetcher instead of the fallback, which is never acceptable for evidence."""
    pkg = tmp_path / "collectors"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "common.py").write_text("def fetch_text(url, *, title='', lead=None, fetcher=None):\n    raise AssertionError('not called in this test')\n", encoding="utf-8")
    for name in [n for n in sys.modules if n == "collectors" or n.startswith("collectors.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setenv("QUORUM_COLLECTORS_PATH", str(tmp_path))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(tmp_path)])
    assert fetch_text.fetcher_name() == fetch_text.COLLECTORS_FETCHER
    assert fetch_text.using_shared_fetcher()
    for name in [n for n in sys.modules if n == "collectors" or n.startswith("collectors.")]:
        monkeypatch.delitem(sys.modules, name)


# --- A6: Zetaris returns strings -----------------------------------------------------------------------

ZETARIS_ROWS = [
    {"id": "217", "source_id": "guardian", "source_name": "The Guardian", "independence_group": "guardian", "kind": "outlet", "flank": "left", "tier": "major",
     "url": "https://www.theguardian.com/us-news/live/2026/oct/23/x", "canonical_url": "https://www.theguardian.com/us-news/live/2026/oct/23/x", "title": "Ramaswamy accuses Acton", "lead": "Lead text.",
     "published_at": "2026-10-24 01:09:20.0", "fetched_at": "2026-10-24 01:10:00.512", "access_level": "1", "wire_origin": None, "supersedes_id": "154", "content_hash": "92682389321ad3e442eb975662f0f428e653f2c7a22d3c0773e40a07a34d565b"},
    {"id": "180", "source_id": "reuters", "source_name": "Reuters", "independence_group": "reuters", "kind": "agency", "flank": None, "tier": None,
     "url": "https://www.reuters.com/business/x", "canonical_url": "https://www.reuters.com/business/x", "title": "US has for years asked Musk", "lead": None,
     "published_at": "2026-10-24 00:43:54.633", "fetched_at": "2026-10-24 00:45:00.0", "access_level": "2", "wire_origin": None, "supersedes_id": None, "content_hash": "efff94d168724f84ba6517814a708217ae469a7b026a48a711a29629485a91b0"},
    {"id": "154", "source_id": "guardian", "source_name": "The Guardian", "independence_group": "guardian", "kind": "outlet", "flank": "left", "tier": "major",
     "url": "https://www.theguardian.com/us-news/live/2026/oct/23/x", "canonical_url": "https://www.theguardian.com/us-news/live/2026/oct/23/x", "title": "Ramaswamy accuses Acton", "lead": "Lead text.",
     "published_at": "2026-10-24 00:04:43.0", "fetched_at": "2026-10-24 00:05:00.0", "access_level": "1", "wire_origin": None, "supersedes_id": "136", "content_hash": "3fe83aa45b85895f624d60a641fddc6c29607739543afa29cb3e949c23e9f2a4"},
    {"id": "140", "source_id": "ny-post", "source_name": "New York Post", "independence_group": "ny-post", "kind": "outlet", "flank": "right", "tier": "major",
     "url": "https://nypost.com/x", "canonical_url": "https://nypost.com/x", "title": "Reprint", "lead": "WASHINGTON (AP) — text.",
     "published_at": "2026-10-23 22:21:18.0", "fetched_at": "2026-10-23 22:22:00.0", "access_level": "1", "wire_origin": "AP", "supersedes_id": None, "content_hash": "841cae30a31a74a7efcdd98a579aab7827eea29412d7b49cfd073ae2cc95ec3e"},
]
OFFICIAL_ROWS = [
    {"id": "1990", "source_id": "whitehouse", "source_name": "The White House", "independence_group": "us-gov", "kind": "official", "flank": None, "tier": None,
     "url": "https://www.whitehouse.gov/briefings-statements/2026/10/x/", "title": "First Lady Melania Trump Secures Ceasefire", "lead": "",
     "published_at": "2026-10-23 13:16:54.0", "fetched_at": "2026-10-23 13:20:00.0", "access_level": "1", "wire_origin": None, "doc_type": "release", "text": "Full text of the release."},
]


def test_docref_casts_and_normalises_zetaris_strings():
    ref = corpus._docref(ZETARIS_ROWS[0], official=False)
    assert ref["id"] == 217 and isinstance(ref["id"], int)
    assert ref["access_level"] == 1 and isinstance(ref["access_level"], int)
    assert ref["published_at"] == "2026-10-24T01:09:20Z"
    assert ref["fetched_at"] == "2026-10-24T01:10:00Z"
    assert ref["content_hash"] == ZETARIS_ROWS[0]["content_hash"] and ref["canonical_url"] == ZETARIS_ROWS[0]["canonical_url"]
    reuters = corpus._docref(ZETARIS_ROWS[1], official=False)
    assert reuters["published_at"] == "2026-10-24T00:43:54Z" and reuters["lead"] == "" and reuters["flank"] is None
    official = corpus._docref(OFFICIAL_ROWS[0], official=True)
    assert official["id"] == 1990 + corpus.OFFICIAL_ID_OFFSET and official["published_at"] == "2026-10-23T13:16:54Z" and official["doc_type"] == "release"
    # already-ISO values and datetime objects pass through unchanged in meaning
    assert corpus._iso_utc("2026-10-24T01:09:20Z") == "2026-10-24T01:09:20Z"
    assert corpus._iso_utc("2026-10-24T01:09:20+02:00") == "2026-10-23T23:09:20Z"


def test_load_documents_over_zetaris_strings_marks_the_supersede_chain(monkeypatch):
    calls = []

    def fake_run_sql(sql, limit):
        calls.append(sql)
        return list(OFFICIAL_ROWS) if "official_docs" in sql else list(ZETARIS_ROWS)

    monkeypatch.setattr(corpus, "_run_sql", fake_run_sql)
    docs = corpus.load_documents("russia-ukraine-war", "2026-10-24", corpus="zetaris")
    by_id = {d["id"]: d for d in docs}
    assert by_id[154]["superseded"] is True and "superseded" not in by_id[217] and "superseded" not in by_id[180]
    assert sorted(d["id"] for d in docs) == [140, 154, 180, 217, 1990 + corpus.OFFICIAL_ID_OFFSET]
    assert sorted(docs[:4], key=lambda d: d["published_at"], reverse=True)[0]["id"] == 217  # ISO strings sort chronologically
    assert any("d.content_hash" in sql and "d.canonical_url" in sql and "d.fetched_at" in sql for sql in calls)
    assert any("o.fetched_at" in sql for sql in calls)


# --- B1.1: wire_origin must name an agency group --------------------------------------------------------


def test_unknown_wire_origin_aborts_the_run():
    docs = [make_doc(1, wire_origin="Bloomberg")]
    with pytest.raises(ValueError, match="Bloomberg"):
        corpus.check_wire_groups(docs)


def test_schema_wire_values_pass_even_without_the_agency_row_today():
    corpus.check_wire_groups([make_doc(1, wire_origin="AP"), make_doc(2, wire_origin="Reuters"), make_doc(3, wire_origin="AFP")])
    corpus.check_wire_groups([make_doc(4, source_id="tass", independence_group="tass", kind="agency"), make_doc(5, wire_origin="TASS")])


# --- B1.6: the edition window Anastasia's evidence.py reproduces --------------------------------------


def test_edition_window_matches_the_collection_evidence_file():
    assert corpus._edition_window("2026-10-24") == ("2026-10-23T09:30:00Z", "2026-10-24T09:30:00Z")  # window_utc in her evidence
    assert corpus._edition_window("2026-10-23") == ("2026-10-22T09:30:00Z", "2026-10-23T09:30:00Z")
    assert corpus._edition_window("2026-11-01") == ("2026-10-31T09:30:00Z", "2026-11-01T10:30:00Z")  # DST ends 2026-11-01 02:00 local: a 25-hour window
    assert corpus._edition_window("2026-11-02") == ("2026-11-01T10:30:00Z", "2026-11-02T10:30:00Z")
