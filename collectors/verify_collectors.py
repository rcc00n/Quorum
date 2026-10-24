#!/usr/bin/env python3
"""Readiness check for the data-collection block.

Statuses follow scripts/checks.py: PASS, FAIL, BLOCKED, NOT_TESTED.
Exit code: 0 pass, 1 failure, 2 blocked or untested.
No provider inference and no network calls to news sites: only the local database.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent

REQUIRED_TABLES = ("sources", "topics", "documents", "official_docs", "quotes", "coverage")
# DECISION(2026-10-22, Yelysei/Claude): PASS needs recent rows from >=3 sources and >=1 official doc,
# so a single working feed cannot make the block look operational. Why: AGENTS.md forbids mocks as integrations.
MIN_SOURCES_RECENT = 3
RECENT_MINUTES = 30

# Contract invariants with reasoning (yelysei/agents, rules/confirmation.py, nodes/research.py, state.py, tools/corpus.py).
# DECISION(2026-10-24, Anastasia/Claude Code): these are checked here, in the collectors' own verifier, and FAIL the
# block when broken. Why: reasoning uses lower(wire_origin) *as* the independence group, reads doc_type verbatim
# against its enum, and queries one topic id; a rename on either side would silently break confirmation.
WIRE_VALUES = ("AP", "Reuters", "AFP")                     # documents.wire_origin CHECK in schema.sql
DOC_TYPES = {"law", "order", "vote", "ruling", "statement", "release"}  # official_docs.doc_type CHECK; reasoning state.py
OUTLET_REQUIRED = ("flank", "tier", "independence_group")  # corpus.py reads s.flank, s.tier, s.kind, s.independence_group

seen: set[str] = set()


def emit(status: str, name: str, detail: str) -> None:
    seen.add(status)
    print(f"{status:<10} {name}: {detail}")


def exit_code() -> int:
    if "FAIL" in seen:
        return 1
    if seen & {"BLOCKED", "NOT_TESTED"}:
        return 2
    return 0


def load_env() -> None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def check_csv() -> None:
    path = HERE / "sources.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        emit("FAIL", "sources.csv", "duplicate ids")
        return
    missing_group = [r["id"] for r in rows if not r["independence_group"]]
    if missing_group:
        emit("FAIL", "sources.csv", f"independence_group empty for {', '.join(missing_group)}")
        return
    unrated = sum(1 for r in rows if r["kind"] == "outlet" and not any((r["allsides"], r["mbfc"], r["adfontes"])))
    emit("PASS", "sources.csv", f"{len(rows)} sources; {unrated} outlets still without ratings (source-audit task)")
    # Provenance: a figure without its source URL, or a rated row without ratings_checked_at, is not a figure we can
    # show (schema.sql DECISION 2026-10-24). Mapped values must be inside [-1, 1] (docs/DECISIONS.md › Spectrum ratings).
    bad: list[str] = []
    for r in rows:
        for col, url in (("allsides", "allsides_source_url"), ("mbfc", "mbfc_source_url"), ("adfontes", "adfontes_source_url"), ("audience", "audience_source_url")):
            if r.get(col) and not r.get(url):
                bad.append(f"{r['id']}.{col} without {url}")
            if col != "audience" and r.get(col) and not -1.0 <= float(r[col]) <= 1.0:
                bad.append(f"{r['id']}.{col}={r[col]} outside [-1, 1]")
        if any((r["allsides"], r["mbfc"], r["adfontes"], r["audience"])) and not r.get("ratings_checked_at"):
            bad.append(f"{r['id']} rated but ratings_checked_at empty")
    if bad:
        emit("FAIL", "ratings provenance", "; ".join(bad[:8]) + (" …" if len(bad) > 8 else ""))
    else:
        rated = sum(1 for r in rows if any((r["allsides"], r["mbfc"], r["adfontes"])))
        emit("PASS", "ratings provenance", f"{rated} rated rows, every figure cites a source URL and a check date")
    # Invariant 1 (registry side): every wire value, lowercased, is exactly one agency row's independence_group.
    agency_groups = {r["independence_group"] for r in rows if r["kind"] == "agency"}
    expected = {w.lower() for w in WIRE_VALUES}
    if agency_groups != expected:
        emit("FAIL", "wire_origin invariant", f"agency independence_group {sorted(agency_groups)} != lower(wire_origin) {sorted(expected)}")
    else:
        emit("PASS", "wire_origin invariant", f"agency rows {sorted(agency_groups)} equal lower({'|'.join(WIRE_VALUES)})")
    # corpus.py needs flank, tier and independence_group for every outlet row it joins. A center outlet may have no
    # tier: docs/DECISIONS.md › Sources places WSJ "center, outside cohorts", so an empty tier there is the decision,
    # not a gap.
    incomplete = [r["id"] for r in rows if r["kind"] == "outlet"
                  and not all(r[k] for k in OUTLET_REQUIRED if not (k == "tier" and r["flank"] == "center"))]
    if incomplete:
        emit("FAIL", "outlet registry", f"flank/tier/independence_group missing for {', '.join(incomplete)}")
    else:
        emit("PASS", "outlet registry", f"{sum(1 for r in rows if r['kind'] == 'outlet')} outlets have flank, tier and independence_group")


def check_database() -> None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        emit("BLOCKED", "collectors database", "DATABASE_URL missing from .env or .env.local")
        return
    try:
        import psycopg  # type: ignore
    except ImportError:
        emit("BLOCKED", "collectors database", "psycopg not installed (pip install psycopg[binary])")
        return
    try:
        with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            present = {row[0] for row in cur.fetchall()}
            missing = [t for t in REQUIRED_TABLES if t not in present]
            if missing:
                emit("FAIL", "collectors schema", f"missing tables: {', '.join(missing)}; apply collectors/schema.sql")
                return
            emit("PASS", "collectors schema", "all six tables present")
            cur.execute(
                "SELECT count(DISTINCT source_id) FROM documents WHERE fetched_at > now() - make_interval(mins => %s)",
                (RECENT_MINUTES,),
            )
            n_sources = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM official_docs")
            n_official = cur.fetchone()[0]
            check_invariants(cur)
    except Exception as exc:  # connection or query failure; body withheld
        emit("BLOCKED", "collectors database", f"{type(exc).__name__}; details withheld")
        return
    if n_sources >= MIN_SOURCES_RECENT and n_official >= 1:
        emit("PASS", "collectors freshness", f"{n_sources} sources in the last {RECENT_MINUTES} min; {n_official} official docs")
    else:
        emit("FAIL", "collectors freshness", f"{n_sources} sources in the last {RECENT_MINUTES} min (need {MIN_SOURCES_RECENT}); {n_official} official docs (need 1)")


def check_invariants(cur) -> None:
    """Live-corpus side of the reasoning contract (collectors/HANDOFF.md § 4). Runs inside check_database's cursor."""
    # Invariant 1 (data side): lower(wire_origin) of every marked row is an agency row's independence_group.
    cur.execute(
        "SELECT DISTINCT d.wire_origin FROM documents d WHERE d.wire_origin IS NOT NULL "
        "AND lower(d.wire_origin) NOT IN (SELECT independence_group FROM sources WHERE kind = 'agency')"
    )
    orphans = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT count(*) FROM documents WHERE wire_origin IS NOT NULL")
    n_wire = cur.fetchone()[0]
    if orphans:
        emit("FAIL", "wire_origin rows", f"values with no agency row: {orphans}")
    else:
        emit("PASS", "wire_origin rows", f"{n_wire} marked rows, every lower(wire_origin) is an agency independence_group")
    # Invariant 2: doc_type values are a subset of the enum reasoning reads (state.py).
    cur.execute("SELECT DISTINCT doc_type FROM official_docs")
    found = {row[0] for row in cur.fetchall()}
    if found - DOC_TYPES:
        emit("FAIL", "doc_type enum", f"unknown values {sorted(found - DOC_TYPES)}")
    else:
        emit("PASS", "doc_type enum", f"values in use {sorted(found)} ⊆ {sorted(DOC_TYPES)}")
    # Invariant 3: exactly one topic id across documents and official_docs, and it is the one run.py collects.
    cur.execute("SELECT DISTINCT topic_id FROM documents UNION SELECT DISTINCT topic_id FROM official_docs")
    topics = {row[0] for row in cur.fetchall()}
    try:
        from collectors.run import TOPICS  # type: ignore
        expected = set(TOPICS)
    except Exception:
        expected = None
    if len(topics) != 1 or (expected is not None and topics != expected):
        emit("FAIL", "topic id", f"topic ids in data {sorted(map(str, topics))}; run.py collects {sorted(expected) if expected else '?'}")
    else:
        emit("PASS", "topic id", f"single topic id {next(iter(topics))} in documents and official_docs")


def main() -> int:
    load_env()
    check_csv()
    check_database()
    for key in ("GUARDIAN_API_KEY", "CONGRESS_API_KEY"):
        emit("PASS" if os.environ.get(key, "").strip() else "BLOCKED", key, "present" if os.environ.get(key, "").strip() else "missing; that source will run at a lower access level")
    return exit_code()


if __name__ == "__main__":
    sys.exit(main())
