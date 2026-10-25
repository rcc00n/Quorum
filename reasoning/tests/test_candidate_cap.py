"""The code-side bound on stance calls (config research.candidates_per_claim, 2026-10-24): research round 2 and the
fact-checker judge at most N documents per claim, ranked by shared words with the claim's best passage. Dry run.
"""

from __future__ import annotations

from quorum_reasoning import config
from quorum_reasoning.nodes import research
from quorum_reasoning.state import DocRef


def doc(doc_id: int, text: str, published: str = "2026-10-21T12:00:00Z") -> DocRef:
    return DocRef(id=doc_id, source_id=f"s{doc_id}", source_name=f"s{doc_id}", independence_group=f"s{doc_id}", kind="outlet", flank=None, tier=None,
                  url=f"https://example.org/{doc_id}", title=text.split(".")[0], lead="", published_at=published, access_level=1, wire_origin=None, text=text)


CLAIM = "The Senate passed the aid bill for interceptors on Tuesday"


def test_ranking_prefers_shared_words_then_recency_and_drops_unrelated_documents():
    docs = [
        doc(1, "Weather was mild across all plains. Nothing else happened."),  # shares no word with the claim
        doc(2, "The Senate passed the aid bill on Tuesday, lawmakers said.", "2026-10-21T10:00:00Z"),
        doc(3, "The Senate passed the aid bill for interceptors on Tuesday after a long debate.", "2026-10-21T09:00:00Z"),
        doc(4, "The Senate passed the aid bill on Tuesday.", "2026-10-21T11:00:00Z"),
    ]
    ranked = research.rank_candidates(CLAIM, docs, dry_run=True, cap=0)
    assert [d["id"] for d in ranked] == [3, 4, 2], "most shared words first, newer first on a tie; the unrelated document is dropped"
    assert [d["id"] for d in research.rank_candidates(CLAIM, docs, dry_run=True, cap=2)] == [3, 4]


def test_default_cap_comes_from_config_and_bounds_the_pool():
    cap = int(config.get("research", "candidates_per_claim", 0))
    assert cap > 0
    docs = [doc(i, f"The Senate passed the aid bill on Tuesday, report {i}.") for i in range(1, cap + 6)]
    assert len(research.rank_candidates(CLAIM, docs, dry_run=True)) == cap
