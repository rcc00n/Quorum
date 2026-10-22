"""Portal-owned view model. No reasoning or collector schema is asserted here."""

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


class DataAdapter(Protocol):
    def snapshot(self, day: str, topic: str) -> PortalSnapshot: ...
class PendingAdapter:
    def snapshot(self, day: str = "", topic: str = "") -> PortalSnapshot:
        return {
            "status": "pending",
            "topics": [],
            "sources": [],
            "events": [],
            "digests": [],
        }


adapter: DataAdapter = PendingAdapter()
