"""The trace. Every node records one StepRecord per execution; loops show as the same node with a higher iteration.

The in-state list is what Studio and the tests see. When ANALYSIS_DATABASE_URL is set, the same rows are
upserted into analysis.run_steps (store.py). Writes are idempotent per (run_id, node, iteration, event_id).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from .state import RunState, StepRecord


class Step:
    """Collects the fields of one trace row while a node runs."""

    def __init__(self, node: str, *, event_id: str | None = None, model: str | None = None) -> None:
        self.node = node
        self.event_id = event_id
        self.model = model
        self.decision = ""
        self.reason = ""
        self.detail: list[dict] | None = None  # audit rows the decision summarises (e.g. extract's dropped claims)
        self._started = time.perf_counter()

    def record(self) -> StepRecord:
        rec = StepRecord(
            node=self.node,
            iteration=0,  # set by `finish`
            event_id=self.event_id,
            decision=self.decision,
            reason=self.reason,
            model=self.model,
            duration_ms=int((time.perf_counter() - self._started) * 1000),
        )
        if self.detail:
            rec["detail"] = self.detail
        return rec


def iteration_of(state: RunState, node: str, event_id: str | None = None) -> int:
    """1 for the first execution of a node (per event when event_id is given), 2 for the first loop back."""
    prior = [s for s in state.get("steps", []) if s["node"] == node and s["event_id"] == event_id]
    return len(prior) + 1


@contextmanager
def step(state: RunState, node: str, *, event_id: str | None = None, model: str | None = None) -> Iterator[Step]:
    """Usage: with step(state, "verify") as s: ...; s.decision = "..."; s.reason = "..." — the caller appends s.finish(state)."""
    s = Step(node, event_id=event_id, model=model)
    yield s


def finish(state: RunState, s: Step) -> StepRecord:
    rec = s.record()
    rec["iteration"] = iteration_of(state, s.node, s.event_id)
    return rec
