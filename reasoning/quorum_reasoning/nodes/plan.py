"""plan: load the day's corpus through Zetaris and set the research budget. No model call.

Also the only node that normalises the input: a run started from Studio may give just topic_id, edition_date
and dry_run, so every other key gets its empty value here and later nodes can index the state directly.
"""

from __future__ import annotations

from .. import config, ids, llm
from ..state import RunState
from ..tools.corpus import load_documents
from ..trace import finish, step


def run(state: RunState) -> dict:
    topic_id = state.get("topic_id") or ""
    edition_date = state.get("edition_date") or ""
    if not topic_id or not edition_date:
        raise ValueError("a run needs topic_id (e.g. russia-ukraine-war) and edition_date (YYYY-MM-DD); set dry_run=true to spend no credits")
    dry_run = bool(state.get("dry_run", False))
    corpus = state.get("corpus") or ("fixture" if dry_run else "zetaris")
    if corpus not in ("fixture", "zetaris"):
        raise ValueError(f"corpus must be fixture or zetaris, got {corpus!r}")
    with step(state, "plan") as s:
        docs = state.get("documents") or load_documents(topic_id, edition_date, corpus=corpus)
        official = sum(1 for d in docs if d.get("official"))
        sources = sorted({d["source_id"] for d in docs})
        rounds = config.get("loops", "research_rounds_max", 2)
        model_mode = "stand-ins (dry run)" if llm.is_dry_run(dry_run) else f"live, {llm.model_name()}"
        s.decision = f"{len(docs)} documents from {len(sources)} sources, {official} official; research budget {rounds} rounds per event"
        s.reason = f"corpus: {corpus}, edition window ending 05:30 America/New_York; model: {model_mode}; every event gets the same budget"
    return {
        "run_id": state.get("run_id") or ids.run_id(topic_id, edition_date),
        "dry_run": dry_run,
        "corpus": corpus,
        "documents": docs,
        "events": [],
        "claims": {},
        "research_rounds": {},
        "roundup": None,
        "summary": "",
        "snapshot": None,
        "steps": [finish(state, s)],
    }
