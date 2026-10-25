#!/usr/bin/env python3
"""Register the collectors' Postgres in Zetaris over REST, one statement at a time, using agent/tools_zetaris.py.

    python3 collectors/zetaris/register.py           # create datasource + register tables + show checks
    python3 collectors/zetaris/register.py --check   # only the SHOW / SELECT checks

Needs ZETARIS_REST_URL, ZETARIS_ORG_ID, ZETARIS_API_KEY in .env (see .env.example). Prints no credentials.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.tools_zetaris import run_sql  # noqa: E402

CREATE = (
    'CREATE DATASOURCE QUORUM_COLLECT DESCRIBE BY "Quorum data-collection block" OPTIONS ('
    'jdbcdriver "org.postgresql.Driver", '
    'jdbcurl "jdbc:postgresql://host.docker.internal:5433/quorum", '
    'username "quorum", password "quorum", fetchsize "1000")'
)
REGISTER = "REGISTER DATASOURCE TABLES ('sources', 'topics', 'documents', 'official_docs', 'quotes', 'coverage') FROM QUORUM_COLLECT"
CHECKS = [
    "SHOW DATASOURCES",
    "SHOW DATASOURCE TABLES QUORUM_COLLECT",
    "SELECT source_id, title, access_level FROM QUORUM_COLLECT.documents ORDER BY published_at DESC LIMIT 5",
    "SELECT count(*) AS official_docs FROM QUORUM_COLLECT.official_docs",
]


def run(label: str, sql: str) -> bool:
    try:
        rows = run_sql(sql, limit=20)
        print(f"OK    {label}: {json.dumps(rows[:5], default=str)[:400]}")
        return True
    except Exception as exc:  # the helper withholds response bodies on purpose
        print(f"FAIL  {label}: {exc}")
        return False


def main() -> int:
    ok = True
    if "--check" not in sys.argv:
        ok &= run("create datasource", CREATE)
        ok &= run("register tables", REGISTER)
    for sql in CHECKS:
        ok &= run(sql.split(" FROM ")[-1][:40] if sql.startswith("SELECT") else sql, sql)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
