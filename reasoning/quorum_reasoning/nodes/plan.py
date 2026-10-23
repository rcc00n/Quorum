"""plan: load the day's corpus through Zetaris and set the research budget. No model call.

Also the only node that normalises the input: a run started from Studio may give just topic_id, edition_date
and dry_run, so every other key gets its empty value here and later nodes can index the state directly.
"""

from __future__ import annotations

from .. import config, ids
from ..state import RunState
from ..tools.corpus import load_documents
from ..trace import finish, step


def run(state: RunState) -> dict:
    topic_id = state["topic_id"]
    edition_date = state["edition_date"]
    dry_run = bool(state.get("dry_run", False))
    with step(state, "plan") as s:
        docs = state.get("documents") or load_documents(topic_id, edition_date, dry_run=dry_run)
        official = sum(1 for d in docs if d.get("official"))
        sources = sorted({d["source_id"] for d in docs})
        rounds = config.get("loops", "research_rounds_max", 2)
        s.decision = f"{len(docs)} documents from {len(sources)} sources, {official} official; research budget {rounds} rounds per event"
        s.reason = "corpus is the edition window ending 05:30 America/New_York; every event gets the same budget"
    return {
        "run_id": state.get("run_id") or ids.run_id(topic_id, edition_date),
        "dry_run": dry_run,
        "documents": docs,
        "events": [],
        "claims": {},
        "research_rounds": {},
        "roundup": None,
        "summary": "",
        "snapshot": None,
        "steps": [finish(state, s)],
    }
