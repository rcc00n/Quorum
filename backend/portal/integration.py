"""Portal view model; read-only catalog definitions do not establish live integration."""

import json
import os
from pathlib import Path
from typing import TypedDict, Protocol


class Topic(TypedDict):
    id: str
    name: str


class SnapshotExtensions(TypedDict, total=False):
    publication: dict
    errors: list[dict]


class PortalSnapshot(SnapshotExtensions):
    status: str
    topics: list[Topic]
    sources: list[dict]
    events: list[dict]
    digests: list[dict]
    catalog_revision: str | None


class DataAdapter(Protocol):
    def snapshot(
        self, day: str = "", topic: str = "", revision: str | None = None
    ) -> PortalSnapshot: ...

    def event(
        self, event_id: str, day: str = "", revision: str | None = None
    ) -> PortalSnapshot: ...


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


class PublishedAdapter:
    def snapshot(self, day: str = "", topic: str = "", revision: str | None = None):
        from .snapshot_store import SnapshotStore
        from .snapshot_projection import project

        catalog = CatalogAdapter().snapshot()
        payload, publication = SnapshotStore().read(day, revision)
        if payload:
            result = project(payload, publication, topic)
            result["catalog_revision"] = catalog["catalog_revision"]
            return result
        catalog["publication"] = publication
        if publication["status"] == "error":
            catalog["status"] = "error"
        return catalog

    def event(self, event_id: str, day: str = "", revision: str | None = None):
        from .snapshot_store import SnapshotStore

        if day or revision:
            result = self.snapshot(day, revision=revision)
        else:
            store = SnapshotStore()
            heads = {}
            days = []
            if store.root:
                try:
                    heads = store.heads()
                    days = sorted(heads, reverse=True)
                except (ValueError, OSError):
                    pass
            result = self.snapshot()
            for edition in days:
                try:
                    revision_id = heads[edition]
                    import json
                    from .snapshot_store import read_bounded

                    metadata = json.loads(
                        read_bounded(
                            store.root / "revisions" / f"{revision_id}.meta.json", 65536
                        )
                    )
                    if event_id not in metadata.get("event_ids", []):
                        continue
                    candidate = self.snapshot(edition)
                    if any(e["id"] == event_id for e in candidate["events"]):
                        result = candidate
                        break
                except (ValueError, OSError, KeyError, TypeError):
                    continue
        result["events"] = [e for e in result["events"] if e["id"] == event_id]
        return result


adapter: DataAdapter = PublishedAdapter()
