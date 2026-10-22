"""Portal view model; read-only catalog definitions do not establish live integration."""

import json
import os
from pathlib import Path
from typing import TypedDict, Protocol


class Topic(TypedDict):
    id: str
    name: str


class PortalSnapshot(TypedDict):
    status: str
    topics: list[Topic]
    sources: list[dict]
    events: list[dict]
    digests: list[dict]
    catalog_revision: str | None


class DataAdapter(Protocol):
    def snapshot(self, day: str, topic: str) -> PortalSnapshot: ...


class CatalogAdapter:
    def snapshot(self, day: str = "", topic: str = "") -> PortalSnapshot:
        snapshot: PortalSnapshot = {
            "status": "pending",
            "topics": [],
            "sources": [],
            "events": [],
            "digests": [],
            "catalog_revision": None,
        }
        path = os.getenv("QUORUM_CATALOG_PATH")
        if not path:
            return snapshot
        # Only an operator-configured local export is accepted. No provider request or inference.
        try:
            catalog = json.loads(Path(path).read_text())
            topics = catalog["topics"]
            sources = catalog["sources"]
            if not isinstance(topics, list) or not isinstance(sources, list):
                raise ValueError()
            for item in topics:
                if not all(
                    isinstance(item.get(k), str) and item[k] for k in ("id", "name")
                ):
                    raise ValueError()
            for source in sources:
                if not all(
                    isinstance(source.get(k), str) and source[k]
                    for k in ("id", "name", "domain")
                ):
                    raise ValueError()
                for key in ("allsides", "mbfc", "adfontes"):
                    score = source.get(key)
                    if score is not None and (
                        type(score) not in (int, float) or not -1 <= score <= 1
                    ):
                        raise ValueError()
                audience = source.get("audience")
                if audience is not None and (
                    type(audience) not in (int, float)
                    or not 0 < audience < float("inf")
                ):
                    raise ValueError()
            if not isinstance(catalog.get("revision"), str):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # Invalid/missing catalog is unavailable, never replaced by a demo fixture.
            return snapshot
        snapshot.update(
            topics=[{key: t[key] for key in ("id", "name")} for t in topics],
            sources=[
                {
                    key: s.get(key)
                    for key in (
                        "id",
                        "name",
                        "domain",
                        "allsides",
                        "mbfc",
                        "adfontes",
                        "audience",
                    )
                }
                for s in sources
            ],
            catalog_revision=catalog["revision"],
        )
        return snapshot


adapter: DataAdapter = CatalogAdapter()
