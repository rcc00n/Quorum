"""Durable checkpoint and resume (run.py --resume), the request journal, and the carried topic_match flag (2026-10-24).

Dry run, no network. The checkpoint is a SQLite file in a tmp directory; "resume" is exercised by finishing a run
under a checkpoint and asking to resume it (a finished thread returns its state without running), and by resuming
a thread that has no checkpoint (an error, never a silent fresh start).
"""

from __future__ import annotations

import json
import os

import pytest

from quorum_reasoning import graph, llm, run as run_cli
from quorum_reasoning.tools import corpus

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"


def test_checkpointed_run_finishes_and_a_finished_thread_resumes_without_rerunning(tmp_path):
    os.environ["QUORUM_DRY_RUN"] = "1"
    ck = str(tmp_path / "ck.sqlite")
    seen = []
    st = graph.run_local(TOPIC, DAY, dry_run=True, checkpoint_path=ck, on_step=seen.append, attempt=7)
    assert st["snapshot"]["status"] == "ok" and len(seen) == len(st["steps"]) > 20
    again = []
    st2 = graph.run_local(TOPIC, DAY, dry_run=True, checkpoint_path=ck, on_step=again.append, attempt=7, resume=True)
    assert again == [], "a finished thread must not run any node again"
    assert st2["snapshot"]["run_id"] == st["snapshot"]["run_id"] and len(st2["steps"]) == len(st["steps"])


def test_resume_without_a_checkpoint_is_an_error_not_a_fresh_run(tmp_path):
    with pytest.raises(ValueError, match="nothing to resume"):
        graph.run_local(TOPIC, DAY, dry_run=True, checkpoint_path=str(tmp_path / "empty.sqlite"), resume=True, attempt=9)
    assert run_cli.main(["--dry-run", "--quiet", "--resume", "--attempt", "9", "--out", str(tmp_path)]) == 2


def test_cli_checkpoint_flag_writes_the_sqlite_file(tmp_path):
    assert run_cli.main(["--dry-run", "--quiet", "--checkpoint", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "_checkpoints" / f"{DAY}-{TOPIC}-1.sqlite").is_file()
    assert not (tmp_path / "_journal").exists(), "a dry run makes no live calls, so no journal"


def test_journal_lines_carry_the_payload_and_restore_the_ledger(tmp_path, monkeypatch):
    path = tmp_path / "_journal" / "r.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    llm.reset_calls()
    entry = {"task": "stance", "lane": "default", "route": "r", "served": "nvidia/x", "ms": 3, "attempts": 1, "run_id": "r", "http_status": 200}
    llm._journal(entry, {"claim": "c", "passage": "p"})
    llm._journal({**entry, "task": "summary"}, {"events": 3})
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["payload"] == {"claim": "c", "passage": "p"} and lines[0]["served"] == "nvidia/x"
    llm.reset_calls()
    assert llm.load_journal(path) == 2
    assert len(llm.calls) == 2 and "payload" not in llm.calls[0] and llm.calls[1]["task"] == "summary"
    llm.reset_calls()
    monkeypatch.setattr(llm, "journal_path", None)


def test_topic_match_is_carried_and_counted_never_filtered(monkeypatch):
    from quorum_reasoning.nodes import plan
    from quorum_reasoning.state import initial_state

    row = {"id": "5", "source_id": "cnn", "source_name": "CNN", "independence_group": "cnn", "kind": "outlet", "flank": "left", "tier": "major",
           "url": "https://example.org/5", "canonical_url": "https://example.org/5", "title": "t", "lead": "l", "published_at": "2026-10-24 01:00:00.0",
           "fetched_at": "2026-10-24 01:00:00.0", "access_level": "1", "wire_origin": None, "supersedes_id": None, "content_hash": "ab" * 32, "topic_match": "lead"}
    ref = corpus._docref(row, official=False)
    assert ref["topic_match"] == "lead"
    docs_sql, _ = corpus.sql_pair(TOPIC, "2026-10-23T09:30:00Z", "2026-10-24T09:30:00Z", "QUORUM_COLLECT")
    assert "d.topic_match" in docs_sql
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = [ref, {**ref, "id": 6, "topic_match": "title"}, {**ref, "id": 7, "topic_match": "body"}]
    out = plan.run(st)
    assert len(out["documents"]) == 3, "no document is dropped for where its terms matched"
    assert "topic terms matched in title 1 / lead only 1 / body only 1" in out["steps"][0]["decision"]
