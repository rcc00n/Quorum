"""The snapshot store: immutable versions per topic and edition day, on the file system.

Layout under the store root (`--out`, default `reasoning/snapshots/`, git-ignored):

    <root>/<topic>/<date>/v<N>.json          one immutable snapshot version (never overwritten)
    <root>/<topic>/<date>/v<N>.ledger.json   the run's private call ledger, beside its version, never inside it
    <root>/<topic>/<date>/latest.json        a copy of the newest version

`publish` assigns `version` = previous + 1 for the same topic-day and sets `published_at` at write time, which is
what docs/ARCHITECTURE.md § 8 promises the portal (versions immutable, `published_at` store-set, null before).

DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): the smallest store that honours § 8 is a directory of JSON
files; the Postgres `analysis` schema of ARCHITECTURE § 4 stays DEFERRED for the hackathon. Why: the portal
consumes one snapshot file plus its SHA-256 (Vadim's `boundary.cjs --reasoning-file`), so a file store is the
whole contract today, versions and `published_at` included; a database adds operations, not evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VERSION = re.compile(r"^v(\d+)\.json$")


def day_dir(root: Path, topic_id: str, edition_date: str) -> Path:
    return Path(root) / topic_id / edition_date


def versions(root: Path, topic_id: str, edition_date: str) -> list[int]:
    d = day_dir(root, topic_id, edition_date)
    if not d.is_dir():
        return []
    found = [int(m.group(1)) for p in d.iterdir() if (m := _VERSION.match(p.name))]
    return sorted(found)


def version_path(root: Path, topic_id: str, edition_date: str, version: int) -> Path:
    return day_dir(root, topic_id, edition_date) / f"v{version}.json"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(snapshot: dict[str, Any], root: Path, *, ledger: list[dict] | None = None) -> tuple[Path, int]:
    """Writes the snapshot as the next version of its topic-day and refreshes latest.json. Returns (path, version).

    The snapshot dict is updated in place (`version`, `published_at`) so the caller prints what was stored.
    An existing version file is never overwritten: the next free number is used even if a gap exists.
    """
    topic_id, edition_date = snapshot["topic_id"], snapshot["edition_date"]
    d = day_dir(root, topic_id, edition_date)
    d.mkdir(parents=True, exist_ok=True)
    existing = versions(root, topic_id, edition_date)
    version = (existing[-1] + 1) if existing else 1
    path = version_path(root, topic_id, edition_date, version)
    assert not path.exists(), path  # versions are immutable by construction
    snapshot["version"] = version
    snapshot["published_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if ledger:
        (d / f"v{version}.ledger.json").write_text(
            json.dumps({"topic_id": topic_id, "edition_date": edition_date, "version": version, "run_id": snapshot.get("run_id"), "calls": ledger}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    shutil.copyfile(path, d / "latest.json")
    return path, version


def load(root: Path, topic_id: str, edition_date: str, version: int | None = None) -> dict[str, Any]:
    """One stored version (the newest when `version` is None). Raises FileNotFoundError when there is none."""
    if version is None:
        found = versions(root, topic_id, edition_date)
        if not found:
            raise FileNotFoundError(f"no snapshot for {topic_id} {edition_date} under {root}")
        version = found[-1]
    path = version_path(root, topic_id, edition_date, version)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def listing(root: Path) -> list[dict[str, Any]]:
    """Every stored version: topic, date, version, status, published_at, sha256 — for `--list`."""
    out: list[dict[str, Any]] = []
    root = Path(root)
    if not root.is_dir():
        return out
    for topic_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for date_dir in sorted(p for p in topic_dir.iterdir() if p.is_dir()):
            for v in versions(root, topic_dir.name, date_dir.name):
                path = version_path(root, topic_dir.name, date_dir.name, v)
                snap = json.loads(path.read_text(encoding="utf-8"))
                out.append(
                    {
                        "topic_id": topic_dir.name,
                        "edition_date": date_dir.name,
                        "version": v,
                        "status": snap.get("status"),
                        "published_at": snap.get("published_at"),
                        "stories": len(snap.get("stories", [])),
                        "fictional": (snap.get("provenance") or {}).get("fictional"),
                        "sha256": sha256_of(path),
                        "path": str(path),
                    }
                )
    return out
