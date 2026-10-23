"""The day's corpus for one topic, read through Zetaris. In dry run, from the bundled fixture.

Zetaris side (collectors/zetaris/01_register_postgres.sql): the collection Postgres is registered as the
Lightning database QUORUM_COLLECT, so the tables are QUORUM_COLLECT.public.documents and friends. Override the
database name with ZETARIS_COLLECTION_DB if yours differs.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from ..state import DocRef

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# documents.id and official_docs.id are independent Postgres sequences; both start at 1. Loaded into the
# one DocRef.id space they collide, and every by-id lookup (score, extract, the origin skip in research)
# silently picks the wrong document. Official rows are therefore namespaced above this offset; evidence
# rows map back to the database id (nodes/research.evidence_from).
OFFICIAL_ID_OFFSET = 1_000_000_000


def _zetaris_db() -> str:
    return os.getenv("ZETARIS_COLLECTION_DB", "QUORUM_COLLECT")


def _run_sql(sql: str, limit: int):
    """Uses the repo's agent/tools_zetaris.py (read-only Lightning SQL over the REST API)."""
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from agent.tools_zetaris import run_sql  # type: ignore

    return run_sql(sql, limit=limit)


def _edition_window(edition_date: str) -> tuple[str, str]:
    """24 hours ending at 05:30 America/New_York on the edition day, expressed in UTC (DECISIONS: cut at 05:30, out by 08:00)."""
    d = date.fromisoformat(edition_date)
    # 05:30 New York is 09:30 UTC during EDT (Oct) and 10:30 UTC during EST; keep it simple and explicit.
    end = f"{d.isoformat()}T09:30:00Z"
    start = f"{(d - timedelta(days=1)).isoformat()}T09:30:00Z"
    return start, end


_TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def load_documents(topic_id: str, edition_date: str, *, dry_run: bool) -> list[DocRef]:
    if not _TOPIC_ID.match(topic_id):
        raise ValueError(f"topic_id must be a slug like russia-ukraine-war, got {topic_id!r}")
    date.fromisoformat(edition_date)  # raises on a malformed date before anything reaches SQL
    if dry_run:
        return load_fixture(topic_id, edition_date)
    db = _zetaris_db()
    start, end = _edition_window(edition_date)
    docs_sql = f"""
        SELECT d.id, d.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               d.url, d.title, d.lead, d.published_at, d.access_level, d.wire_origin, d.supersedes_id
        FROM {db}.public.documents d
        JOIN {db}.public.sources s ON s.id = d.source_id
        WHERE d.topic_id = '{topic_id}'
          AND d.published_at >= TIMESTAMP '{start}' AND d.published_at < TIMESTAMP '{end}'
        ORDER BY d.published_at DESC
    """
    official_sql = f"""
        SELECT o.id, o.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               o.url, o.title, '' AS lead, COALESCE(o.signed_at, o.published_at) AS published_at, 1 AS access_level,
               NULL AS wire_origin, o.doc_type, o.full_text AS text
        FROM {db}.public.official_docs o
        JOIN {db}.public.sources s ON s.id = o.source_id
        WHERE o.topic_id = '{topic_id}'
          AND COALESCE(o.signed_at, o.published_at) >= TIMESTAMP '{start}'
          AND COALESCE(o.signed_at, o.published_at) < TIMESTAMP '{end}'
    """
    out: list[DocRef] = []
    rows = list(_run_sql(docs_sql, limit=500))
    # A correction re-fetch (collectors/schema.sql: supersedes_id) replaces the row it supersedes: only
    # the current version of a document takes part in the day, or retracted text keeps feeding evidence.
    superseded = {int(r["supersedes_id"]) for r in rows if r.get("supersedes_id")}
    for row in rows:
        if int(row["id"]) in superseded:
            continue
        out.append(_docref(row, official=False))
    for row in _run_sql(official_sql, limit=200):
        out.append(_docref(row, official=True))
    doc_ids = [d["id"] for d in out]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("duplicate document ids in the day's corpus after namespacing; refusing to run on a corrupt corpus")
    return out


def _docref(row: dict, *, official: bool) -> DocRef:
    ref = DocRef(
        id=int(row["id"]) + (OFFICIAL_ID_OFFSET if official else 0),
        source_id=str(row["source_id"]),
        source_name=str(row.get("source_name") or row["source_id"]),
        independence_group=str(row.get("independence_group") or row["source_id"]),
        kind=str(row.get("kind") or ("official" if official else "outlet")),
        flank=row.get("flank"),
        tier=row.get("tier"),
        url=str(row["url"]),
        title=str(row.get("title") or ""),
        lead=str(row.get("lead") or ""),
        published_at=str(row.get("published_at") or ""),
        access_level=int(row.get("access_level") or (1 if official else 3)),
        wire_origin=row.get("wire_origin"),
    )
    if official:
        ref["official"] = True
        ref["doc_type"] = row.get("doc_type")
        ref["text"] = row.get("text")
    return ref


def load_fixture(topic_id: str, edition_date: str) -> list[DocRef]:
    path = _FIXTURES / "sample_day.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    docs = [d for d in data["documents"] if d.get("topic_id", topic_id) == topic_id]
    return [DocRef(**{k: v for k, v in d.items() if k != "topic_id"}) for d in docs]
