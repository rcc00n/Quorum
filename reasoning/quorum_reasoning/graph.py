"""The Quorum reasoning graph (docs/ARCHITECTURE.md § 5).

Nodes are plain functions returning partial state; loops are conditional edges. `graph` is compiled without
a checkpointer because `langgraph dev` (Studio) supplies its own; `run_local` compiles with an in-memory
one for the CLI and the tests. Every node appends to `steps`, so a run's trace is in the final state.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import config, ids
from .nodes import adjudicate, cluster, critique, escalate, extract, fact_check, frame, plan, publish, research, review_disputed, roundup, score, verify, write
from pathlib import Path
from typing import Callable

from .state import RunInput, RunState, StepRecord, run_input


def build() -> StateGraph:
    b = StateGraph(RunState, input_schema=RunInput)  # Studio's input form shows RunInput only
    b.add_node("plan", plan.run)
    b.add_node("cluster", cluster.run)
    b.add_node("score_importance", score.run)
    b.add_node("extract_claims", extract.run)
    b.add_node("research", research.run)
    b.add_node("verify", verify.run)
    b.add_node("fact_check", fact_check.run)
    b.add_node("adjudicate", adjudicate.run)
    b.add_node("review_disputed", review_disputed.run)
    b.add_node("escalate", escalate.run)
    b.add_node("frame", frame.run)
    b.add_node("write", write.run)
    b.add_node("critique", critique.run)
    b.add_node("roundup", roundup.run)
    b.add_node("publish", publish.run)

    b.add_edge(START, "plan")
    b.add_edge("plan", "cluster")
    b.add_edge("cluster", "score_importance")
    b.add_edge("score_importance", "extract_claims")
    b.add_edge("extract_claims", "research")
    b.add_edge("research", "verify")
    b.add_conditional_edges("verify", verify.route, {"research": "research", "fact_check": "fact_check"})
    b.add_edge("fact_check", "adjudicate")
    b.add_conditional_edges("adjudicate", adjudicate.route, {"review_disputed": "review_disputed", "escalate": "escalate", "frame": "frame"})
    b.add_conditional_edges("review_disputed", review_disputed.route, {"escalate": "escalate", "frame": "frame"})
    b.add_edge("escalate", "frame")
    b.add_edge("frame", "write")
    b.add_edge("write", "critique")
    b.add_conditional_edges("critique", critique.route, {"write": "write", "roundup": "roundup"})
    b.add_edge("roundup", "publish")
    b.add_edge("publish", END)
    return b


builder = build()
graph = builder.compile()  # what langgraph.json points at


def _checkpointer(checkpoint_path: str | None):
    """In-memory for tests, the dry run and Studio; SQLite when a path is given (the live run's durable checkpoint).

    DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a live run checkpoints every node into a SQLite file under
    the output directory and can be resumed (`run.py --resume`) from the last completed node with the same
    run_id. Why: the first genuine corpus run is ~1 400–2 500 model calls over 1.5–2.5 hours; Vadim's independent
    Zetaris-backed attempt (Issue #2, FULL-REAL-01) lost 172 completed tasks when request 173 failed, because the
    in-memory state could not be resumed. The in-memory saver stays the default so dry runs and tests change nothing.
    """
    if not checkpoint_path:
        return InMemorySaver()
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver  # optional dependency: langgraph-checkpoint-sqlite

    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(checkpoint_path, check_same_thread=False))


def run_local(
    topic_id: str,
    edition_date: str,
    *,
    dry_run: bool,
    corpus: str | None = None,
    attempt: int = 1,
    on_step: Callable[[StepRecord], None] | None = None,
    checkpoint_path: str | None = None,
    resume: bool = False,
) -> RunState:
    """One full run. Returns the final state (snapshot included).

    Two independent axes: `dry_run` (model stand-ins or live calls) and `corpus` (fixture or zetaris; default
    follows dry_run). Live model on the fixture corpus is how prompts are tried before collection has data.
    With `on_step`, every trace row is handed over as soon as its node finishes (the CLI prints progress).
    With `checkpoint_path`, every node is checkpointed into that SQLite file; `resume=True` continues the thread
    `run_id(topic, date, attempt)` from its last completed node instead of starting over (nothing to resume is an
    error, a finished thread returns its final state without running anything).
    """
    app = builder.compile(checkpointer=_checkpointer(checkpoint_path))
    rid = ids.run_id(topic_id, edition_date, attempt)
    cfg = {"configurable": {"thread_id": rid}, "recursion_limit": int(config.get("loops", "recursion_limit", 60))}
    if resume:
        if not checkpoint_path:
            raise ValueError("resume needs a checkpoint path")
        snapshot = app.get_state(cfg)
        if not snapshot.values:
            raise ValueError(f"nothing to resume: no checkpoint for run {rid} in {checkpoint_path}")
        if not snapshot.next:
            return snapshot.values  # type: ignore[return-value]  # the thread already finished
        inp = None  # continue from the last checkpoint
    else:
        if checkpoint_path and app.get_state(cfg).values:
            raise ValueError(f"run {rid} already has a checkpoint in {checkpoint_path}: pass --resume to continue it, or --attempt N+1 for a fresh run")
        inp = run_input(topic_id, edition_date, dry_run=dry_run, corpus=corpus, run_id=rid)
    if on_step is None:
        return app.invoke(inp, cfg)  # type: ignore[return-value]
    for update in app.stream(inp, cfg, stream_mode="updates"):
        for delta in update.values():
            for rec in (delta or {}).get("steps") or []:
                on_step(rec)
    return app.get_state(cfg).values  # type: ignore[return-value]


def mermaid() -> str:
    """The diagram in docs/ARCHITECTURE.md § 5 is regenerated from this, so the document never drifts from the code."""
    return graph.get_graph().draw_mermaid()
