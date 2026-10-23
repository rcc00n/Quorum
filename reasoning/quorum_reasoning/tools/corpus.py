"""The day's corpus for one topic: through Zetaris (corpus="zetaris") or from a bundled fixture (corpus="fixture").

Zetaris side (collectors/zetaris/01_register_postgres.sql): the collection Postgres is registered with
`CREATE DATASOURCE QUORUM_COLLECT` and `REGISTER DATASOURCE TABLES (...) FROM QUORUM_COLLECT`, so the tables
are QUORUM_COLLECT.documents and friends — no schema segment. Override the datasource name with
ZETARIS_COLLECTION_DB; set ZETARIS_COLLECTION_SCHEMA only if your registration exposes a schema level.

Fixture side: `fixtures/<name>.json`, name from QUORUM_FIXTURE (default sample_day; use-case days live under
usecases/, e.g. QUORUM_FIXTURE=usecases/quiet_day).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..state import DocRef

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# documents.id and official_docs.id are independent Postgres sequences; both start at 1. Loaded into the
# one DocRef.id space they collide, and every by-id lookup (score, extract, the origin skip in research)
# silently picks the wrong document. Official rows are therefore namespaced above this offset; evidence
# rows map back to the database id (nodes/research.evidence_from).
OFFICIAL_ID_OFFSET = 1_000_000_000


def _zetaris_db() -> str:
    """Table prefix as registered in Lightning: `QUORUM_COLLECT` (tables QUORUM_COLLECT.documents, ...)."""
    db = os.getenv("ZETARIS_COLLECTION_DB", "QUORUM_COLLECT")
    schema = os.getenv("ZETARIS_COLLECTION_SCHEMA", "").strip()
    return f"{db}.{schema}" if schema else db


def _run_sql(sql: str, limit: int):
    """Uses the repo's agent/tools_zetaris.py (read-only Lightning SQL over the REST API)."""
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from agent.tools_zetaris import run_sql  # type: ignore

    return run_sql(sql, limit=limit)


def _edition_window(edition_date: str) -> tuple[str, str]:
    """The window ending at 05:30 America/New_York on the edition day, expressed in UTC.

    DECISION(2026-10-23, Yelysei Shkirpan/Claude Code): the 05:30 cut is converted per date with
    zoneinfo, not a fixed offset. Why: a hardcoded EDT offset (09:30Z) goes wrong when DST ends on
    2026-11-01 — documents published 09:30–10:30Z would fall between two editions; the transition
    day itself is a 25-hour local day and that is the correct window.
    """
    tz = ZoneInfo("America/New_York")
    d = date.fromisoformat(edition_date)
    cut = time(5, 30)
    end = datetime.combine(d, cut, tz).astimezone(timezone.utc)
    start = datetime.combine(d - timedelta(days=1), cut, tz).astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


_TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def load_documents(topic_id: str, edition_date: str, *, corpus: str = "fixture") -> list[DocRef]:
    """`corpus` is "fixture" (the bundled sample day, no network) or "zetaris" (the day's documents through Lightning SQL)."""
    if not _TOPIC_ID.match(topic_id):
        raise ValueError(f"topic_id must be a slug like russia-ukraine-war, got {topic_id!r}")
    date.fromisoformat(edition_date)  # raises on a malformed date before anything reaches SQL
    if corpus == "fixture":
        return load_fixture(topic_id, edition_date)
    if corpus != "zetaris":
        raise ValueError(f"unknown corpus {corpus!r}")
    db = _zetaris_db()
    start, end = _edition_window(edition_date)
    docs_sql = f"""
        SELECT d.id, d.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               d.url, d.title, d.lead, d.published_at, d.access_level, d.wire_origin, d.supersedes_id
        FROM {db}.documents d
        JOIN {db}.sources s ON s.id = d.source_id
        WHERE d.topic_id = '{topic_id}'
          AND d.published_at >= TIMESTAMP '{start}' AND d.published_at < TIMESTAMP '{end}'
        ORDER BY d.published_at DESC
    """
    official_sql = f"""
        SELECT o.id, o.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               o.url, o.title, '' AS lead, COALESCE(o.signed_at, o.published_at) AS published_at, 1 AS access_level,
               NULL AS wire_origin, o.doc_type, o.full_text AS text
        FROM {db}.official_docs o
        JOIN {db}.sources s ON s.id = o.source_id
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


_FIXTURE_NAME = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)?$")


def fixture_name() -> str:
    name = os.getenv("QUORUM_FIXTURE", "sample_day").strip() or "sample_day"
    if not _FIXTURE_NAME.match(name):
        raise ValueError(f"QUORUM_FIXTURE must be a name like sample_day or usecases/quiet_day, got {name!r}")
    return name


def load_fixture(topic_id: str, edition_date: str) -> list[DocRef]:
    """The bundled day named by QUORUM_FIXTURE. The fixture's own topic/date are not checked against the
    arguments: a dry run of any date replays the same day on purpose (deterministic demos and tests)."""
    path = _FIXTURES / f"{fixture_name()}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no fixture {path.name} under {path.parent}; see fixtures/ and fixtures/usecases/")
    data = json.loads(path.read_text(encoding="utf-8"))
    docs = [d for d in data["documents"] if d.get("topic_id", topic_id) == topic_id]
    return [DocRef(**{k: v for k, v in d.items() if k != "topic_id"}) for d in docs]
