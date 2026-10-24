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

from .. import config
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


def previous_days() -> int:
    return max(0, int(config.get("research", "previous_days", 0) or 0))


def _previous_window(edition_date: str, days: int) -> tuple[str, str]:
    """The `days` edition windows before this edition's window, as one UTC interval [start, end)."""
    start, _ = _edition_window(edition_date)
    earlier, _ = _edition_window((date.fromisoformat(edition_date) - timedelta(days=days)).isoformat())
    return earlier, start


def sql_pair(topic_id: str, start: str, end: str, db: str | None = None) -> tuple[str, str]:
    """The two statements the corpus runs for one UTC window: documents joined with sources, official documents
    joined with sources. collectors/zetaris/evidence.py keeps a copy of these; change both together."""
    db = db or _zetaris_db()
    docs_sql = f"""
        SELECT d.id, d.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               d.url, d.canonical_url, d.title, d.lead, d.published_at, d.fetched_at, d.access_level, d.wire_origin,
               d.supersedes_id, d.content_hash
        FROM {db}.documents d
        JOIN {db}.sources s ON s.id = d.source_id
        WHERE d.topic_id = '{topic_id}'
          AND d.published_at >= TIMESTAMP '{start}' AND d.published_at < TIMESTAMP '{end}'
        ORDER BY d.published_at DESC
    """
    official_sql = f"""
        SELECT o.id, o.source_id, s.name AS source_name, s.independence_group, s.kind, s.flank, s.tier,
               o.url, o.title, '' AS lead, COALESCE(o.signed_at, o.published_at) AS published_at, o.fetched_at,
               1 AS access_level, NULL AS wire_origin, o.doc_type, o.full_text AS text
        FROM {db}.official_docs o
        JOIN {db}.sources s ON s.id = o.source_id
        WHERE o.topic_id = '{topic_id}'
          AND COALESCE(o.signed_at, o.published_at) >= TIMESTAMP '{start}'
          AND COALESCE(o.signed_at, o.published_at) < TIMESTAMP '{end}'
    """
    return docs_sql, official_sql


def _load_window(topic_id: str, start: str, end: str, *, previous: bool) -> list[DocRef]:
    docs_sql, official_sql = sql_pair(topic_id, start, end)
    out: list[DocRef] = []
    rows = list(_run_sql(docs_sql, limit=500 if not previous else 1500))
    # A correction re-fetch (collectors/schema.sql: supersedes_id) replaces the row it supersedes. The
    # superseded row stays in the corpus marked `superseded` — it counts for spread and coverage, never as
    # evidence or an extraction origin (decided 2026-10-24, DECISIONS.md log; supersedes the 2026-10-23
    # drop-the-row rule, see README.md › Decisions).
    superseded = {int(r["supersedes_id"]) for r in rows if r.get("supersedes_id") not in (None, "", "None")}
    for row in rows:
        ref = _docref(row, official=False)
        if int(row["id"]) in superseded:
            ref["superseded"] = True
        if previous:
            ref["from_previous_day"] = True
        out.append(ref)
    for row in _run_sql(official_sql, limit=200 if not previous else 600):
        ref = _docref(row, official=True)
        if previous:
            ref["from_previous_day"] = True
        out.append(ref)
    return out


def load_documents(topic_id: str, edition_date: str, *, corpus: str = "fixture") -> list[DocRef]:
    """`corpus` is "fixture" (the bundled sample day, no network) or "zetaris" (the day's documents through Lightning SQL).

    With `research.previous_days` > 0 the Zetaris corpus also carries the documents of the previous edition
    windows, marked `from_previous_day` (evidence for research round 2 only; see config/reasoning.toml).
    A supersede chain that crosses the window boundary is resolved on the combined set.
    """
    if not _TOPIC_ID.match(topic_id):
        raise ValueError(f"topic_id must be a slug like russia-ukraine-war, got {topic_id!r}")
    date.fromisoformat(edition_date)  # raises on a malformed date before anything reaches SQL
    if corpus == "fixture":
        return load_fixture(topic_id, edition_date)
    if corpus != "zetaris":
        raise ValueError(f"unknown corpus {corpus!r}")
    start, end = _edition_window(edition_date)
    out = _load_window(topic_id, start, end, previous=False)
    days = previous_days()
    if days:
        p_start, p_end = _previous_window(edition_date, days)
        today_ids = {d["id"] for d in out}
        # the windows are disjoint, so an id seen in both can only be the same row answered twice: keep today's
        out += [d for d in _load_window(topic_id, p_start, p_end, previous=True) if d["id"] not in today_ids]
    doc_ids = [d["id"] for d in out]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("duplicate document ids in the day's corpus after namespacing; refusing to run on a corrupt corpus")
    check_wire_groups(out)
    return out


# The three wire agencies collectors/schema.sql allows in documents.wire_origin, lower-cased: the registry's
# agency rows carry exactly these as independence_group (collectors/README.md › wire_origin).
WIRE_GROUPS_BY_SCHEMA = {"ap", "reuters", "afp"}


def check_wire_groups(docs: list[DocRef]) -> None:
    """Aborts the run when a document's `wire_origin`, lower-cased, is not an agency's independence group.

    Reasoning uses `wire_origin.lower()` as the independence group of a reprint (rules/confirmation.py,
    nodes/research.py), so a value with no agency behind it would make a reprint its own "independent" group
    and could confirm a claim by one wire story. Accepted: the schema's three values, and any agency group
    present in the loaded corpus. The sources registry itself is not loaded yet (work item E3 will load it and
    tighten this to the registry); until then the schema enum is the floor. Same invariant as
    `collectors/verify_collectors.py` on the collection side (answer to Anastasia's question 1, 2026-10-24).
    """
    agency_groups = {d["independence_group"] for d in docs if d["kind"] == "agency"} | WIRE_GROUPS_BY_SCHEMA
    bad = sorted({str(d["wire_origin"]) for d in docs if d.get("wire_origin") and str(d["wire_origin"]).strip().lower() not in agency_groups})
    if bad:
        raise ValueError(
            f"wire_origin value(s) {bad} do not name an agency independence group ({sorted(agency_groups)}); "
            "a reprint would count as its own independent source — fix collection or the registry before running"
        )


def _iso_utc(value) -> str:
    """Normalises a timestamp Zetaris returns as a string to ISO 8601 UTC (`…T…Z`, whole seconds).

    DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): Zetaris delivers every column as a string, timestamps
    as `2026-10-24 01:09:20.0` or `2026-10-24 00:43:54.633` (space separator, fractional seconds, no zone);
    they are stored TIMESTAMPTZ and read back in UTC, so a zone-less value is taken as UTC. Why: the state
    documents `published_at` as ISO 8601 UTC, `cluster` and `frame` sort on the string, and the portal
    validates `Z` timestamps; Anastasia's real Zetaris result (collectors/zetaris/evidence/, 2026-10-24) shows
    the raw shape.
    """
    if value is None or value == "" or value == "None":
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("T", " ")
        if s.endswith("Z"):
            s = s[:-1]
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return str(value)  # unknown shape: left as delivered rather than invented
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text_or_none(value) -> str | None:
    return None if value in (None, "", "None") else str(value)


def _docref(row: dict, *, official: bool) -> DocRef:
    """One Zetaris row as a DocRef. Every value arrives as a string (ids, levels, timestamps, NULL as None or
    "None"): ids and levels are cast, timestamps normalised by `_iso_utc`, empty strings become None."""
    ref = DocRef(
        id=int(row["id"]) + (OFFICIAL_ID_OFFSET if official else 0),
        source_id=str(row["source_id"]),
        source_name=str(row.get("source_name") or row["source_id"]),
        independence_group=str(row.get("independence_group") or row["source_id"]),
        kind=str(row.get("kind") or ("official" if official else "outlet")),
        flank=_text_or_none(row.get("flank")),
        tier=_text_or_none(row.get("tier")),
        url=str(row["url"]),
        title=str(row.get("title") or ""),
        lead=str(_text_or_none(row.get("lead")) or ""),
        published_at=_iso_utc(row.get("published_at")),
        access_level=int(row.get("access_level") or (1 if official else 3)),
        wire_origin=_text_or_none(row.get("wire_origin")),
    )
    if row.get("canonical_url") not in (None, "", "None"):
        ref["canonical_url"] = str(row["canonical_url"])
    if row.get("content_hash") not in (None, "", "None"):
        ref["content_hash"] = str(row["content_hash"])
    if row.get("fetched_at") not in (None, "", "None"):
        ref["fetched_at"] = _iso_utc(row["fetched_at"])
    if official:
        ref["official"] = True
        ref["doc_type"] = _text_or_none(row.get("doc_type"))
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
    superseded_ids = {d["supersedes_id"] for d in docs if d.get("supersedes_id")}
    out: list[DocRef] = []
    for d in docs:
        ref = DocRef(**{k: v for k, v in d.items() if k not in ("topic_id", "supersedes_id")})
        if d["id"] in superseded_ids:
            ref["superseded"] = True  # spread and coverage only, never evidence (same rule as load_documents)
        out.append(ref)  # a fixture document may carry from_previous_day itself (evidence only, like the Zetaris path)
    check_wire_groups(out)
    return out
