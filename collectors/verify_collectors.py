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
HERE = Path(__file__).resolve().parent

REQUIRED_TABLES = ("sources", "topics", "documents", "official_docs", "quotes", "coverage")
# DECISION(2026-10-22, Yelysei/Claude): PASS needs recent rows from >=3 sources and >=1 official doc,
# so a single working feed cannot make the block look operational. Why: AGENTS.md forbids mocks as integrations.
MIN_SOURCES_RECENT = 3
RECENT_MINUTES = 30

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
    except Exception as exc:  # connection or query failure; body withheld
        emit("BLOCKED", "collectors database", f"{type(exc).__name__}; details withheld")
        return
    if n_sources >= MIN_SOURCES_RECENT and n_official >= 1:
        emit("PASS", "collectors freshness", f"{n_sources} sources in the last {RECENT_MINUTES} min; {n_official} official docs")
    else:
        emit("FAIL", "collectors freshness", f"{n_sources} sources in the last {RECENT_MINUTES} min (need {MIN_SOURCES_RECENT}); {n_official} official docs (need 1)")


def main() -> int:
    load_env()
    check_csv()
    check_database()
    for key in ("GUARDIAN_API_KEY", "CONGRESS_API_KEY"):
        emit("PASS" if os.environ.get(key, "").strip() else "BLOCKED", key, "present" if os.environ.get(key, "").strip() else "missing; that source will run at a lower access level")
    return exit_code()


if __name__ == "__main__":
    sys.exit(main())
