"""The file store (work item E2) and research round 2 over the previous edition days (E4), 2026-10-24.

Dry run, no network. The store is exercised on a tmp root; the previous-day documents are injected through a
fake Zetaris SQL (the corpus loader's two statements, answered per window) and through a synthetic state.
"""

from __future__ import annotations

import json

import pytest

from quorum_reasoning import config, graph, store
from quorum_reasoning.nodes import cluster, frame, research
from quorum_reasoning.state import Claim, DocRef, Event, initial_state
from quorum_reasoning.tools import corpus

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


# --- E2: immutable versions, published_at set by the store ------------------------------------------------


def test_store_versions_are_immutable_and_increment(tmp_path):
    snap = {"topic_id": TOPIC, "edition_date": DAY, "version": 1, "published_at": None, "run_id": "r1", "status": "ok", "stories": [], "provenance": {"fictional": True}}
    p1, v1 = store.publish(dict(snap), tmp_path)
    p2, v2 = store.publish(dict(snap), tmp_path)
    assert (v1, v2) == (1, 2) and p1.name == "v1.json" and p2.name == "v2.json"
    first, second = json.loads(p1.read_text(encoding="utf-8")), json.loads(p2.read_text(encoding="utf-8"))
    assert first["version"] == 1 and second["version"] == 2
    assert first["published_at"] and first["published_at"].endswith("Z") and second["published_at"] >= first["published_at"]
    latest = json.loads((tmp_path / TOPIC / DAY / "latest.json").read_text(encoding="utf-8"))
    assert latest["version"] == 2
    assert store.versions(tmp_path, TOPIC, DAY) == [1, 2]
    assert store.load(tmp_path, TOPIC, DAY)["version"] == 2 and store.load(tmp_path, TOPIC, DAY, 1)["version"] == 1
    rows = store.listing(tmp_path)
    assert [r["version"] for r in rows] == [1, 2] and all(len(r["sha256"]) == 64 for r in rows)
    with pytest.raises(FileNotFoundError):
        store.load(tmp_path, TOPIC, "2026-01-01")


def test_cli_run_stores_a_version_and_show_prints_it(tmp_path, capsys):
    from quorum_reasoning import run as run_cli

    assert run_cli.main(["--dry-run", "--quiet", "--out", str(tmp_path)]) == 0
    assert run_cli.main(["--dry-run", "--quiet", "--out", str(tmp_path)]) == 0
    assert store.versions(tmp_path, TOPIC, DAY) == [1, 2]
    assert run_cli.main(["--show", "--topic", TOPIC, "--date", DAY, "--version", "1", "--out", str(tmp_path)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["version"] == 1 and shown["published_at"] is not None and shown["schema_version"] == "1.0"
    assert run_cli.main(["--list", "--out", str(tmp_path)]) == 0
    assert "v1.json" not in capsys.readouterr().out.split("\n")[0]  # a table, not paths, on the header line
    assert run_cli.main(["--show", "--topic", TOPIC, "--date", "2026-01-01", "--out", str(tmp_path)]) == 2


# --- E4: previous edition days are evidence only -------------------------------------------------------------


def _row(doc_id: int, source: str, published: str, title: str, lead: str, kind: str = "outlet", group: str | None = None):
    return {"id": str(doc_id), "source_id": source, "source_name": source, "independence_group": group or source, "kind": kind, "flank": None, "tier": None,
            "url": f"https://example.org/{source}/{doc_id}", "canonical_url": f"https://example.org/{source}/{doc_id}", "title": title, "lead": lead,
            "published_at": published, "fetched_at": published, "access_level": "2", "wire_origin": None, "supersedes_id": None, "content_hash": "ab" * 32}


def test_loader_reads_the_previous_windows_and_marks_them(monkeypatch):
    monkeypatch.setitem(config.load()["research"], "previous_days", 2)
    seen = []

    def fake_run_sql(sql, limit):
        seen.append(sql)
        if "official_docs" in sql:
            return []
        if "2026-10-21T09:30:00Z' AND d.published_at < TIMESTAMP '2026-10-22T09:30:00Z'" in sql:
            return [_row(10, "cnn", "2026-10-21 20:00:00.0", "Aid bill signed", "Today's lead.")]
        if "2026-10-19T09:30:00Z' AND d.published_at < TIMESTAMP '2026-10-21T09:30:00Z'" in sql:
            return [_row(5, "npr", "2026-10-20 12:00:00.0", "Senate passes aid bill", "Earlier lead.")]
        raise AssertionError(sql)

    monkeypatch.setattr(corpus, "_run_sql", fake_run_sql)
    docs = corpus.load_documents(TOPIC, DAY, corpus="zetaris")
    by_id = {d["id"]: d for d in docs}
    assert set(by_id) == {10, 5} and by_id[5]["from_previous_day"] is True and "from_previous_day" not in by_id[10]
    assert len(seen) == 4  # two statements per window, two windows
    assert corpus._previous_window(DAY, 2) == ("2026-10-19T09:30:00Z", "2026-10-21T09:30:00Z")


def _doc(doc_id: int, source: str, text: str, *, previous: bool = False, flank="left", tier="major") -> DocRef:
    d = DocRef(id=doc_id, source_id=source, source_name=source, independence_group=source, kind="outlet", flank=flank, tier=tier,
               url=f"https://example.org/{source}/{doc_id}", title=text.split(".")[0], lead="", published_at="2026-10-21T12:00:00Z", access_level=1, wire_origin=None, text=text)
    if previous:
        d["from_previous_day"] = True
    return d


def test_previous_day_documents_form_no_event_count_no_coverage_but_give_evidence_in_round_2():
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    today = _doc(1, "cnn", "The Senate passed the aid bill 68-30 on Tuesday. More follows.")
    earlier = _doc(2, "npr", "The Senate passed the aid bill 68-30 on Tuesday, NPR reported.", previous=True, flank="left", tier="major")
    st["documents"] = [today, earlier]
    out = cluster.run(st)
    assert len(out["events"]) == 1 and out["events"][0]["document_ids"] == [1]
    assert "1 earlier-day documents held for evidence only" in out["steps"][0]["decision"]
    ev: Event = out["events"][0]
    assert frame.coverage(st["documents"], ev["document_ids"]) == {"major_left": [1, 1], "minor_left": [0, 0], "major_right": [0, 0], "minor_right": [0, 0], "center": [0, 0]}
    st["events"] = out["events"]
    claim = Claim(id="c1", event_id=ev["id"], text="The Senate passed the aid bill 68-30", kind="number", origin_document_id=1, evidence=[],
                  verifier_status=None, verifier_reason="", fact_checker_status=None, fact_checker_reason="", final_status=None, adjudication="")
    st["claims"] = {"c1": claim}
    st["research_rounds"] = {ev["id"]: 1}  # round 1 done: round 2 widens
    r = research.run(st)
    rows = r["claims"]["c1"]["evidence"]
    assert rows and rows[0]["document_id"] == 2 and rows[0]["from_previous_day"] is True and rows[0]["stance"] == "supports"
    assert "1 earlier-day documents" in r["steps"][0]["reason"]


def test_fixture_days_carry_no_previous_day_documents_so_the_dry_run_is_unchanged():
    st = graph.run_local(TOPIC, DAY, dry_run=True)
    assert not any(d.get("from_previous_day") for d in st["documents"])
    assert all(ev["from_previous_day"] is False for s in st["snapshot"]["stories"] for c in s["claims"] for ev in c["evidence"])
