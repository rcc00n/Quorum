"""plan: load the day's corpus through Zetaris and set the research budget. No model call.

Also the only node that normalises the input: a run started from Studio may give just topic_id, edition_date
and dry_run, so every other key gets its empty value here and later nodes can index the state directly.
"""

from __future__ import annotations

from .. import config, ids, llm
from ..state import DocRef, RunState, StepError
from ..tools import corpus as corpus_tools
from ..tools.corpus import load_documents
from ..tools.fetch_text import clear_cache, fetcher_name
from ..topic_match import official_seed_flags
from ..trace import finish, step


def apply_seed_rule(docs: list[DocRef], topic_id: str, corpus: str) -> tuple[list[DocRef], str, str, list[StepError]]:
    """The official-document seed rule (docs/DECISIONS.md › Sources): (documents, decision suffix, reason suffix,
    errors). On the Zetaris corpus an official document of the edition window seeds an event only when a term of the
    run's topic matches its title or abstract (topic_match.official_seed_flags); otherwise it is marked
    `evidence_only`. The topic's terms are read once, and only when the window holds an official document."""
    official = [d for d in docs if d.get("official") and not d.get("from_previous_day")]
    if not official:
        return docs, "", "", []
    if corpus != "zetaris":
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the fixture corpus keeps the behaviour before the seed
        # rule: every official document may seed an event, and none is marked evidence-only. Why: the fixture days are
        # hand-made, carry no topics row, and their official documents are on-topic by construction; the tests and the
        # committed dry-run samples rest on them.
        return docs, f"; official documents: {len(official)} total, all seed-eligible (fixture corpus: seed rule not applied)", "", []
    terms, why, failed = corpus_tools.load_topic_terms(topic_id)
    docs, counts = official_seed_flags(docs, terms)
    seeds = counts["title"] + counts["lead"]
    decision = (
        f"; official documents: {counts['official']} total, {seeds} seed-eligible (title {counts['title']} / abstract {counts['lead']}), "
        f"{counts['evidence_only']} evidence only"
        + (" (no topic term in title or abstract)" if terms else f" (topic terms unavailable: {why}; no official document seeds an event)")
    )
    reason = f"; official seed rule: a term of the topic in the title or abstract, whole word, any case ({why})"
    errors = [StepError(node="plan", event_id=None, message=f"{why}: no official document seeds an event today")] if failed else []
    return docs, decision, reason, errors


def run(state: RunState) -> dict:
    topic_id = state.get("topic_id") or ""
    edition_date = state.get("edition_date") or ""
    if not topic_id or not edition_date:
        raise ValueError("a run needs topic_id (e.g. russia-ukraine-war) and edition_date (YYYY-MM-DD); set dry_run=true to spend no credits")
    dry_run = bool(state.get("dry_run", False))
    corpus = state.get("corpus") or ("fixture" if dry_run else "zetaris")
    if corpus not in ("fixture", "zetaris"):
        raise ValueError(f"corpus must be fixture or zetaris, got {corpus!r}")
    clear_cache()  # article texts live for one run only
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the ledger is per run; it is kept when run.py loaded this run
    # id's journal (`llm.journal_loaded_for`), whatever run_id the rows carry, because a seeded journal (--seed-journal)
    # legitimately holds an earlier attempt's rows. Why: the old row-stamp check wiped a seeded ledger and its replay
    # queues at the first node, so attempt 4 of 2026-10-24 paid again for calls it should have replayed.
    if llm.journal_loaded_for != state.get("run_id") and (not llm.calls or not all(c.get("run_id") == state.get("run_id") for c in llm.calls)):
        llm.reset_calls()
    with step(state, "plan") as s:
        docs = state.get("documents") or load_documents(topic_id, edition_date, corpus=corpus)
        docs, seed_decision, seed_reason, errors = apply_seed_rule(docs, topic_id, corpus)
        today_all = [d for d in docs if not d.get("from_previous_day")]
        today = [d for d in today_all if not d.get("superseded")]
        folded = len(today_all) - len(today)
        earlier = len(docs) - len(today_all)
        official = sum(1 for d in today if d.get("official"))
        sources = sorted({d["source_id"] for d in today})
        rounds = config.get("loops", "research_rounds_max", 2)
        model_mode = "stand-ins (dry run)" if llm.is_dry_run(dry_run) else f"live, {llm.model_name()}"
        # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): documents.topic_match (title | lead | body) is counted here
        # and carried on DocRef, never used to drop a document. Why: DECISIONS.md › Selecting major news says candidates
        # are all events in the corpus and no decision allows a relevance filter; the first real day measures the
        # noise (events whose terms matched only the lead or body) before anyone decides on one. Anastasia's ask 3.
        # Amended 2026-10-26 (Yelysei): official documents now have a seed rule (apply_seed_rule, DECISIONS.md › Sources);
        # it decides which may start an event, it drops none, and outlet documents are still never filtered.
        matched = {k: sum(1 for d in today if d.get("topic_match") == k) for k in ("title", "lead", "body")}
        s.decision = (
            f"{len(today)} documents from {len(sources)} sources, {official} official"
            + seed_decision
            + (f"; {folded} superseded versions folded into their chains (counted once)" if folded else "")
            + (f"; {earlier} earlier-day documents for evidence only" if earlier else "")
            + (f"; topic terms matched in title {matched['title']} / lead only {matched['lead']} / body only {matched['body']}" if any(matched.values()) else "")
            + f"; research budget {rounds} rounds per event"
        )
        s.reason = f"corpus: {corpus}, edition window ending 05:30 America/New_York; model: {model_mode}; every event gets the same budget"
        if corpus == "zetaris":
            s.reason += f"; article text via {fetcher_name()}"
        s.reason += seed_reason
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
        "errors": errors,
    }
