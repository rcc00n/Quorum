"""The Quorum reasoning graph (docs/ARCHITECTURE.md § 5).

Nodes are plain functions returning partial state; loops are conditional edges. `graph` is compiled without
a checkpointer because `langgraph dev` (Studio) supplies its own; `run_local` compiles with an in-memory
one for the CLI and the tests. Every node appends to `steps`, so a run's trace is in the final state.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import config, ids
from .nodes import adjudicate, cluster, critique, escalate, extract, fact_check, frame, plan, publish, research, roundup, score, verify, write
from .state import RunInput, RunState, run_input


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
    b.add_conditional_edges("adjudicate", adjudicate.route, {"escalate": "escalate", "frame": "frame"})
    b.add_edge("escalate", "frame")
    b.add_edge("frame", "write")
    b.add_edge("write", "critique")
    b.add_conditional_edges("critique", critique.route, {"write": "write", "roundup": "roundup"})
    b.add_edge("roundup", "publish")
    b.add_edge("publish", END)
    return b


builder = build()
graph = builder.compile()  # what langgraph.json points at


def run_local(topic_id: str, edition_date: str, *, dry_run: bool, attempt: int = 1) -> RunState:
    """One full run with an in-memory checkpointer. Returns the final state (snapshot included)."""
    app = builder.compile(checkpointer=InMemorySaver())
    rid = ids.run_id(topic_id, edition_date, attempt)
    cfg = {"configurable": {"thread_id": rid}, "recursion_limit": int(config.get("loops", "recursion_limit", 60))}
    return app.invoke(run_input(topic_id, edition_date, dry_run=dry_run, run_id=rid), cfg)  # type: ignore[return-value]


def mermaid() -> str:
    """The diagram in docs/ARCHITECTURE.md § 5 is regenerated from this, so the document never drifts from the code."""
    return graph.get_graph().draw_mermaid()
