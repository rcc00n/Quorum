"""Run read-only Lightning SQL against the local Zetaris REST API."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    for name in (".env", ".env.local"):
        path = _ROOT / name
        if path.is_file():
            load_dotenv(path, override=False)


def _require(name: str) -> str:
    _load_env()
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing from .env or .env.local")
    return value


def _column_names(payload: dict[str, Any]) -> list[str] | None:
    headers = payload.get("headers")
    if isinstance(headers, list) and headers and all(isinstance(item, str) for item in headers):
        return list(headers)
    for key in ("columns", "columnNames", "fields"):
        raw = payload.get(key)
        if isinstance(raw, list) and raw:
            if all(isinstance(item, str) for item in raw):
                return list(raw)
            if all(isinstance(item, dict) for item in raw):
                names = [item.get("name") or item.get("field") for item in raw]
                if all(isinstance(name, str) for name in names):
                    return names
    schema = payload.get("schema")
    if isinstance(schema, list) and schema:
        names = [item.get("name") for item in schema if isinstance(item, dict)]
        if names and all(isinstance(name, str) for name in names):
            return names
    return None


def _normalize_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Zetaris response shape")

    if payload.get("error") or payload.get("errors"):
        raise RuntimeError("Zetaris SQL request failed; response body withheld")

    data = payload.get("data")
    if data is None:
        for key in ("rows", "records", "result"):
            if key in payload:
                data = payload[key]
                break

    if isinstance(data, list):
        if not data:
            return []
        if all(isinstance(row, dict) for row in data):
            return list(data)
        if all(isinstance(row, list) for row in data):
            names = _column_names(payload)
            if not names:
                names = [f"col{i}" for i in range(len(data[0]))]
            return [dict(zip(names, row)) for row in data]

    raise RuntimeError("Zetaris response did not contain tabular rows")


def run_sql(sql: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """Execute one Lightning SQL statement via the sql-editor REST route."""
    statement = sql.strip().rstrip(";")
    if not statement:
        raise ValueError("sql must be a non-empty statement")
    if ";" in statement:
        raise ValueError("exactly one SQL statement per call")

    rest_url = _require("ZETARIS_REST_URL").rstrip("/")
    org_id = _require("ZETARIS_ORG_ID")
    api_key = _require("ZETARIS_API_KEY")

    response = requests.post(
        f"{rest_url}/sql-editor/sqls/run",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Org-ID": org_id,
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        json={
            "queryId": str(uuid.uuid4()),
            "sql": statement,
            "source": "SqlEditor",
            "limit": limit,
        },
        timeout=120,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Zetaris REST HTTP {response.status_code}; body withheld"
        ) from exc

    return _normalize_rows(response.json())


if __name__ == "__main__":
    import json
    import sys

    queries = sys.argv[1:] or ("SELECT 1 AS one", "SHOW LIGHTNING DATABASES")
    for query in queries:
        print(f"-- {query}")
        print(json.dumps(run_sql(query), indent=2, default=str))
