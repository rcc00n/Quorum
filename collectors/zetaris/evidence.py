#!/usr/bin/env python3
"""Reproducible, sanitized evidence of a real Zetaris query over the collected corpus.

    python3 collectors/zetaris/evidence.py --topic russia-ukraine-war --date 2026-10-23

Runs, through the authenticated Zetaris REST route (agent/tools_zetaris.py), the SAME two statements that
reasoning's tools/corpus.py builds for one topic and edition day (window ending 05:30 America/New_York), then
writes collectors/zetaris/evidence/<topic>_<date>.json with:
  - the exact SQL, the datasource name, branch/commit, schema hash, run time (UTC)
  - per-source counts and access-level / wire_origin breakdowns
  - a sample of documents and official docs: id, source_id, published_at, access_level, wire_origin,
    supersedes_id, content_hash, url, and the first 80 characters of the title
No article text, no lead, no credentials, no response bodies on error. Safe to commit (AGENTS.md § 3, § 7).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.tools_zetaris import run_sql  # noqa: E402

DB = "QUORUM_COLLECT"


def edition_window(edition_date: str) -> tuple[str, str]:
    """Identical to reasoning/quorum_reasoning/tools/corpus.py::_edition_window (yelysei/agents)."""
    tz = ZoneInfo("America/New_York")
    d = date.fromisoformat(edition_date)
    cut = time(5, 30)
    end = datetime.combine(d, cut, tz).astimezone(timezone.utc)
    start = datetime.combine(d - timedelta(days=1), cut, tz).astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def previous_window(edition_date: str) -> tuple[str, str]:
    """The two edition windows before `edition_date`, as one span (reasoning's research round 2 corpus,
    yelysei/agents@0224ca6; those rows are evidence only, never events, spread or coverage)."""
    d = date.fromisoformat(edition_date)
    start, _ = edition_window((d - timedelta(days=2)).isoformat())
    _, end = edition_window((d - timedelta(days=1)).isoformat())
    return start, end


def sql_pair(topic: str, start: str, end: str) -> tuple[str, str]:
    """The two statements reasoning runs (yelysei/agents@0224ca6, tools/corpus.py), verbatim except that official_docs
    omits full_text here (sanitized) and d.lead is not selected. Reasoning runs the same pair a second time over the
    previous two edition windows (research round 2); evidence.py reports that window too, see previous_window()."""
    docs = f"""SELECT d.id, d.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
       d.url, d.canonical_url, d.title, d.published_at, d.fetched_at, d.access_level, d.wire_origin,
       d.supersedes_id, d.content_hash
FROM {DB}.documents d
JOIN {DB}.sources s ON s.id = d.source_id
WHERE d.topic_id = '{topic}'
  AND d.published_at >= TIMESTAMP '{start}' AND d.published_at < TIMESTAMP '{end}'
ORDER BY d.published_at DESC"""
    official = f"""SELECT o.id, o.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
       o.url, o.title, o.doc_type, o.doc_number, COALESCE(o.signed_at, o.published_at) AS published_at, o.fetched_at,
       length(o.full_text) AS full_text_chars
FROM {DB}.official_docs o
JOIN {DB}.sources s ON s.id = o.source_id
WHERE o.topic_id = '{topic}'
  AND COALESCE(o.signed_at, o.published_at) >= TIMESTAMP '{start}'
  AND COALESCE(o.signed_at, o.published_at) < TIMESTAMP '{end}'
ORDER BY published_at DESC"""
    return docs, official


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def sanitize_doc(r: dict) -> dict:
    return {
        "id": r.get("id"), "source_id": r.get("source_id"), "independence_group": r.get("independence_group"),
        "flank": r.get("flank"), "tier": r.get("tier"), "published_at": str(r.get("published_at")),
        "access_level": r.get("access_level"), "wire_origin": r.get("wire_origin"),
        "supersedes_id": r.get("supersedes_id"), "content_hash": r.get("content_hash"),
        "url": r.get("url"), "title_80": (r.get("title") or "")[:80],
    }


def sanitize_official(r: dict) -> dict:
    return {
        "id": r.get("id"), "source_id": r.get("source_id"), "doc_type": r.get("doc_type"),
        "doc_number": r.get("doc_number"), "published_at": str(r.get("published_at")),
        "full_text_chars": r.get("full_text_chars"), "url": r.get("url"), "title_80": (r.get("title") or "")[:80],
    }


def breakdown(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        k = str(r.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="russia-ukraine-war")
    ap.add_argument("--date", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--limit", type=int, default=2000)
    args = ap.parse_args()

    start, end = edition_window(args.date)
    docs_sql, official_sql = sql_pair(args.topic, start, end)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = run_sql(docs_sql, limit=args.limit)
    official = run_sql(official_sql, limit=args.limit)
    p_start, p_end = previous_window(args.date)
    prev_docs_sql, prev_official_sql = sql_pair(args.topic, p_start, p_end)
    prev_docs = run_sql(prev_docs_sql, limit=args.limit)
    prev_official = run_sql(prev_official_sql, limit=args.limit)

    schema_hash = hashlib.sha256((ROOT / "collectors" / "schema.sql").read_bytes()).hexdigest()[:16]
    out = {
        "evidence_for": "Issue #2 — authorized Zetaris query over the collected corpus (data-collection block)",
        "run_at_utc": run_at,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "commit": git("rev-parse", "--short", "HEAD"),
        "schema_sha256_16": schema_hash, "datasource": DB, "route": "Zetaris REST /sql-editor/sqls/run via agent/tools_zetaris.py",
        "topic_id": args.topic, "edition_date": args.date, "window_utc": [start, end],
        "sql": {"documents": docs_sql, "official_docs": official_sql},
        "documents": {
            "count": len(docs),
            "by_source": breakdown(docs, "source_id"), "by_access_level": breakdown(docs, "access_level"),
            "by_wire_origin": breakdown(docs, "wire_origin"), "by_flank": breakdown(docs, "flank"),
            "sample": [sanitize_doc(r) for r in docs[: args.sample]],
        },
        "official_docs": {
            "count": len(official), "by_source": breakdown(official, "source_id"), "by_doc_type": breakdown(official, "doc_type"),
            "sample": [sanitize_official(r) for r in official[: args.sample]],
        },
        "previous_windows": {
            "window_utc": [p_start, p_end], "purpose": "reasoning research round 2 only (never events, spread or coverage)",
            "documents": len(prev_docs), "documents_by_source": breakdown(prev_docs, "source_id"), "official_docs": len(prev_official),
        },
        "sanitization": "no lead, no article/official text, no credentials; titles truncated to 80 chars",
    }
    dest = ROOT / "collectors" / "zetaris" / "evidence" / f"{args.topic}_{args.date}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(f"documents={len(docs)} official_docs={len(official)} window={start}..{end}")
    print(f"previous windows: documents={len(prev_docs)} official_docs={len(prev_official)} window={p_start}..{p_end}")
    print(f"written {dest.relative_to(ROOT)}")
    return 0 if docs or official else 1


if __name__ == "__main__":
    sys.exit(main())
