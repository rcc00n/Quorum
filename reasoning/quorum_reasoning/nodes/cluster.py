"""cluster: group the day's documents into events.

Similarity is cosine over the title's word set, computed in code. Pairs above the threshold merge; pairs in
the borderline band just below it are put to the model, which sees the two titles and leads and answers
whether they describe one event. Everything else stays apart. Event ids are stable hashes of the member
documents. The model's answer is untrusted: only a JSON boolean true merges; a failed call or any other
value leaves the pair apart (the fail-safe direction: unmerged events are two roundup lines, a wrong merge
pollutes confirmation).

DECISION(2026-10-22, Yelysei Shkirpan/Claude Code): titles only, binary bag of words, no IDF. Why: leads
differ per outlet (each picks its own angle) and dilute the signal, and in a single-topic corpus IDF
punishes exactly the words that define an event because every document of that event shares them. The
model judges the borderline band, so the code only needs to be safe, not clever.
"""

from __future__ import annotations

import math
import re

from .. import config, ids, llm, untrusted
from ..state import DocRef, Event, RunState, StepError
from ..trace import finish, step

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "the a an and or of to in on for by with at from as is are was were be been into that this it its after before over under say says said".split()
)


def _terms(doc: DocRef) -> set[str]:
    return {t for t in _WORD.findall(doc["title"].lower()) if t not in _STOP and len(t) > 1}


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


class _UF:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> None:
        self.p[self.find(i)] = self.find(j)


def _headline(members: list[DocRef]) -> str:
    order = {"agency": 0, "official": 1, "outlet": 2, "military": 3}
    best = sorted(members, key=lambda d: (order.get(d["kind"], 9), d["published_at"]))[0]
    return best["title"]


def run(state: RunState) -> dict:
    docs = state["documents"]
    threshold = config.get("clustering", "similarity_threshold", 0.5)
    band = config.get("clustering", "borderline_band", 0.25)
    model_asked = 0
    model_merged = 0
    errors: list[StepError] = []
    with step(state, "cluster", model=llm.model_name()) as s:
        terms = [_terms(d) for d in docs]
        uf = _UF(len(docs))
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                sim = similarity(terms[i], terms[j])
                if sim >= threshold:
                    uf.union(i, j)
                elif sim >= threshold - band and uf.find(i) != uf.find(j):
                    model_asked += 1
                    try:
                        ans = llm.json_task(
                            "merge_confirm",
                            {
                                "a": {
                                    "title": untrusted.clip(docs[i]["title"], untrusted.CAP_TITLE),
                                    "lead": untrusted.clip(docs[i]["lead"], untrusted.CAP_LEAD),
                                    "source": docs[i]["source_name"],
                                },
                                "b": {
                                    "title": untrusted.clip(docs[j]["title"], untrusted.CAP_TITLE),
                                    "lead": untrusted.clip(docs[j]["lead"], untrusted.CAP_LEAD),
                                    "source": docs[j]["source_name"],
                                },
                                "similarity": round(sim, 3),
                            },
                            dry_run=state["dry_run"],
                        )
                        same = ans.get("same_event") is True  # only a JSON boolean merges; "false" and other strings are truthy
                    except Exception as exc:  # noqa: BLE001 — a failed call leaves the pair apart
                        errors.append(StepError(node="cluster", event_id=None, message=str(exc)[:300]))
                        same = False
                    if same:
                        model_merged += 1
                        uf.union(i, j)
        groups: dict[int, list[DocRef]] = {}
        for i, d in enumerate(docs):
            groups.setdefault(uf.find(i), []).append(d)
        events: list[Event] = []
        for members in groups.values():
            members.sort(key=lambda d: d["published_at"])
            events.append(
                Event(
                    id=ids.event_id(state["topic_id"], state["edition_date"], [d["id"] for d in members]),
                    document_ids=[d["id"] for d in members],
                    headline=_headline(members),
                    standfirst="",
                    rubric=None,
                    above_bar=False,
                    rank=None,
                    needs_review=False,
                    article=[],
                    drafts=0,
                    versions=[],
                    critic_status=None,
                    critic_notes="",
                    framing={},
                    review_reason="",
                )
            )
        events.sort(key=lambda e: -len(e["document_ids"]))
        s.decision = f"{len(events)} events from {len(docs)} documents; model asked on {model_asked} borderline pairs, merged {model_merged}"
        s.reason = f"title cosine >= {threshold} merges; band {band} below it goes to the model"
    return {"events": events, "steps": [finish(state, s)], "errors": errors}
