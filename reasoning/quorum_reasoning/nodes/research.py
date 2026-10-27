"""research: find supporting and contradicting passages for each claim.

Round 1 searches the event's own documents. Round 2 (requested by `verify` for thin claims) widens to every
document of the day and all official documents. Stance per passage is a model judgment; which passages
exist, which groups they belong to and how many rounds run are code. The model's stance answer is untrusted:
only the four allowed stance words are accepted, anything else counts as neutral (untrusted.valid_stance), and a
`contradicts` without a verbatim `contradicted_span` counts as neutral (untrusted.checked_stance). A passage that
carries too little of the claim is not asked about at all (relevant).
"""

from __future__ import annotations

from .. import config, llm, untrusted
from ..rules.confirmation import DOCUMENT_TYPES_THAT_ESTABLISH, is_thin, origin_group
from ..state import Claim, DocRef, Evidence, RunState, StepError
from ..text import best_passage, clip_sentences, containment, frequent_stems, keeps_full_stems, passage_window, tokens
from ..tools import memory
from ..tools.corpus import OFFICIAL_ID_OFFSET
from ..tools.fetch_text import FetchResult, fetch_result, find_quote
from ..trace import finish, step


def already_seen(claim: Claim, doc: DocRef, found_by: str) -> bool:
    key = "official_doc_id" if doc.get("official") else "document_id"
    db_id = doc["id"] - OFFICIAL_ID_OFFSET if doc.get("official") and doc["id"] >= OFFICIAL_ID_OFFSET else doc["id"]  # evidence rows keep the database id
    return any(ev[key] == db_id and ev["found_by"] == found_by for ev in claim["evidence"])


def stance_task(doc: DocRef) -> str:
    """The prompt a stance call on this document uses: `stance_document` for an official law, order, vote or ruling
    (the extra paragraph on what such a document establishes), `stance` for everything else."""
    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): the official-document paragraph lives only in
    # prompts/stance_document.md, chosen here per document; prompts/stance.md no longer carries it. Why: it cost ~165
    # input tokens per copy on every stance call (two copies since e2b9a81), and in 1772 stance calls over two live
    # runs no passage came from a law/order/vote/ruling, so it never applied.
    return "stance_document" if doc.get("official") and doc.get("doc_type") in DOCUMENT_TYPES_THAT_ESTABLISH else "stance"


def relevant(claim_text: str, passage: str) -> bool:
    """True when the passage carries at least `research.stance_min_overlap` of the claim's tokens (text.containment):
    the pre-call guard both stance nodes apply before asking the model."""
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): no stance call for a passage that holds less than
    # research.stance_min_overlap (0.15) of the claim's tokens; the step decision counts the skips. A cost guard: at
    # 0.15 it loses 8 of 222 supports (3.6%), removes 24 contradicts and saves 110 of 2 606 calls (4%) on the
    # 2026-10-24 run-3/5 journals, while 0.25 cost 11% of supports and the D5 noise mostly survived it; the noise
    # guard is the post-call span check (untrusted.checked_stance). Numbers in config/reasoning.toml.
    return containment(claim_text, passage) >= float(config.get("research", "stance_min_overlap", 0.0) or 0.0)


def stance_question(role: str, claim_text: str, passage: str, doc: DocRef, context: tuple[str, str] = ("", "")) -> tuple:
    """The identity of one stance question within a node run: who asks, about which claim, which passage, from which
    source. doc_type and the official flag are part of it because they pick the prompt (stance_task) and the payload."""
    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): within one node run for one event, a stance question already
    # asked (same role, claim text, passage text, source_id, doc_type, official flag) is not asked again; the earlier
    # answer is reused (in fact_check it counts as judged for the claim), and evidence_from still builds one row per
    # document. Why: ~1.7% of stance calls on two live runs were exact
    # repeats (two documents yielding the same passage, or two claims with identical text); verdicts count independence
    # groups, not rows, so the second row of the same source never counts twice.
    # the context window and the title are in the payload, so they are part of the question (decision at STANCE_CONTEXT_SENTENCES)
    return (role, claim_text, passage, doc["source_id"], doc.get("doc_type"), bool(doc.get("official")), context, doc.get("title") or "")


def bind_quote(ev: Evidence, doc: DocRef, fetched: FetchResult | None) -> Evidence:
    """Ties the evidence row to the text its quote was cut from: offsets, hash at quote time, achieved access,
    fetch time, and whether the page changed since collection (work item A5; what Vadim asked for in
    PORTAL_INTEGRATION.md: code-point [start, end) offsets, version/hash binding, achieved access)."""
    if fetched is None:
        return ev
    span = find_quote(fetched.quote_text, ev["quote"])
    ev["char_start"], ev["char_end"] = span if span else (None, None)
    ev["content_hash_at_quote"] = fetched.content_hash
    ev["access_achieved"] = fetched.access_achieved
    ev["fetched_at"] = fetched.fetched_at
    stored = doc.get("content_hash")
    comparable = bool(stored and fetched.content_hash) and not (doc["access_level"] == 1 and fetched.access_achieved == 2)  # a lead-only fallback hashes no body
    ev["hash_mismatch"] = (stored != fetched.content_hash) if comparable else None
    return ev


# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the stance payload carries the document title and
# STANCE_CONTEXT_SENTENCES sentences before and after the passage (context_before, context_after; each side clipped to
# CAP_PASSAGE, empty at the edges), only so the model can tell whether the passage is about the same event as the
# claim; the span must still come from the passage. Why: D5 (2026-10-24 canonical run): a lone sentence hides which
# of an article's several events it belongs to. Owner's decision (Yelysei, 2026-10-25), two sentences per side.
# Token cost estimate in reasoning/README.md › Decisions.
STANCE_CONTEXT_SENTENCES = 2


def stance_window(claim_text: str, fetched: FetchResult | None) -> tuple[str, str, str]:
    """(before, passage, after) for a stance call: text.passage_window over the fetched text."""
    return passage_window(claim_text, (fetched.text if fetched else None) or "", STANCE_CONTEXT_SENTENCES)


def clipped_context(before: str, after: str) -> tuple[str, str]:
    """The context window as the payload carries it: `before` keeps its end (the sentence next to the passage),
    `after` its start; each side at most CAP_PASSAGE characters. off_fact measures coverage over exactly these."""
    return untrusted.clip_end(before, untrusted.CAP_PASSAGE), untrusted.clip(after, untrusted.CAP_PASSAGE)


def stance_payload(claim_text: str, before: str, passage: str, after: str, doc: DocRef, role: str) -> dict:
    """The payload of one stance call; research and fact_check send the same shape."""
    before, after = clipped_context(before, after)
    return {
        "claim": untrusted.clip(claim_text, untrusted.CAP_CLAIM),
        "passage": untrusted.clip(passage, untrusted.CAP_PASSAGE),
        "context_before": before,
        "context_after": after,
        "title": untrusted.clip(doc.get("title") or "", untrusted.CAP_TITLE),
        "source": doc["source_name"],
        "source_kind": doc["kind"],
        "doc_type": doc.get("doc_type"),
        "role": role,
    }


# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): topic-frequent stems are excluded from fact compositions only
# when the run has at least STANCE_FREQUENT_MIN_DOCS documents; below that nothing is excluded and the step reason
# says so. Why: on the fixture days (6-10 documents) the "most frequent" stems were the main story's own words
# ("aid, bill, law, sign"), so a real contradiction of that story would have read as off-fact. Owner's decision
# (Yelysei, 2026-10-25).
STANCE_FREQUENT_MIN_DOCS = 30


def topic_frequent(state: RunState) -> tuple[set[str], int]:
    """(stems, document count): the run's most common stems (text.frequent_stems over every document's title and
    lead), excluded from a claim's fact composition (untrusted.off_fact); empty below STANCE_FREQUENT_MIN_DOCS."""
    texts = [f"{d.get('title') or ''} {d.get('lead') or ''}" for d in state["documents"]]
    return (frequent_stems(texts) if len(texts) >= STANCE_FREQUENT_MIN_DOCS else set()), len(texts)


def stance_coverage(span: object) -> float:
    """The fact-composition share a `contradicts` or `supports` needs: research.stance_coverage for a clause,
    research.stance_coverage_short for a short span (untrusted.is_short_span; a short span reaching here already
    carries a number, date or negation or shares 2 composition stems: untrusted.span_contradicts_claim,
    untrusted.span_supports_claim)."""
    key = "stance_coverage_short" if untrusted.is_short_span(span) else "stance_coverage"
    return float(config.get("research", key, 0.0) or 0.0)


def judged_stance(ans: object, claim_text: str, passage: str, frequent: set[str], *, live: bool, context: tuple[str, str] = ("", "")) -> tuple[str, str | None]:
    """The stance after the post-call guards and, when downgraded, why: "ungrounded" or "support ungrounded"
    (untrusted.checked_stance), or "off-fact" / "support off-fact" (untrusted.off_fact over the passage and its
    context window: the fact composition is not covered, or another stated day). `live` is False when the dry-run
    stand-in answered (llm.is_dry_run): it writes no span, and its contradictions and supports stay."""
    asked_stance = untrusted.valid_stance(ans.get("stance") if isinstance(ans, dict) else None)
    stance, downgraded = untrusted.checked_stance(ans, passage, claim_text, require_span=live, frequent=frequent)
    if downgraded:
        return "neutral", ("support ungrounded" if asked_stance == "supports" else "ungrounded")
    if stance in ("contradicts", "supports") and live:
        span = ans.get("contradicted_span" if stance == "contradicts" else "supporting_span") if isinstance(ans, dict) else None
        if untrusted.off_fact(claim_text, passage, span, frequent, stance_coverage(span), " ".join(clipped_context(*context)), stance=stance):
            return "neutral", ("off-fact" if stance == "contradicts" else "support off-fact")
    return stance, None


def excluded_note(frequent: set[str], n_docs: int, claim_texts: list[str] | tuple = ()) -> str:
    """The step-reason suffix naming the stems excluded from fact compositions, or saying the exclusion is off, and
    how many of the event's claims kept their full stem set (text.keeps_full_stems)."""
    if n_docs < STANCE_FREQUENT_MIN_DOCS:
        return f"; topic-frequent exclusion off ({n_docs} documents)"
    if not frequent:
        return ""
    kept = sum(1 for t in claim_texts if keeps_full_stems(t, frequent))
    return f"; topic-frequent stems excluded from fact compositions: {', '.join(sorted(frequent))}" + (f"; {kept} claims kept their full stem set" if kept else "")


def relevance_note(irrelevant: int, ungrounded: int, off_fact: int = 0, supports_ungrounded: int = 0, supports_off_fact: int = 0) -> str:
    """The step-decision suffix counting the relevance guards; empty when none fired."""
    parts = (
        ([f"{irrelevant} passages below relevance"] if irrelevant else [])
        + ([f"{ungrounded} contradictions ungrounded"] if ungrounded else [])
        + ([f"{off_fact} contradictions off-fact"] if off_fact else [])
        + ([f"{supports_ungrounded} supports ungrounded"] if supports_ungrounded else [])
        + ([f"{supports_off_fact} supports off-fact"] if supports_off_fact else [])
    )
    return f"; {', '.join(parts)}" if parts else ""


def evidence_from(doc: DocRef, passage: str, stance: str, found_by: str, fetched: FetchResult | None = None) -> Evidence:
    is_doc = bool(doc.get("official")) and doc.get("doc_type") in DOCUMENT_TYPES_THAT_ESTABLISH
    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): an official release/statement and an attributed-only
    # military source (DECISIONS › Sources: ISW, DeepState, Oryx "presented as statements with the author named")
    # are the party's words in both directions: `supports` and `contradicts` become `statement`. Why: a ministry's
    # denial turned two independent confirmations into `disputed` (review finding, 2026-10-24); DECISIONS ›
    # Principles says a party's words are a statement, never evidence for or against their own content.
    if ((doc.get("official") and not is_doc) or doc["kind"] == "military") and stance in ("supports", "contradicts"):
        stance = "statement"
    # A reprint carries the wire's independence group: ten reprints of one wire story are one piece of
    # evidence (DECISIONS.md › Principles for handling facts). wire_origin is 'AP'/'Reuters'/'AFP' in
    # collectors/schema.sql; independence groups are lower-case slugs.
    group = (doc.get("wire_origin") or "").strip().lower() or doc["independence_group"]
    # Official ids are namespaced above OFFICIAL_ID_OFFSET (tools/corpus.py); the evidence row keeps the
    # database id so analysis.evidence rows point at real official_docs rows.
    db_id = doc["id"] - OFFICIAL_ID_OFFSET if doc.get("official") and doc["id"] >= OFFICIAL_ID_OFFSET else doc["id"]
    ev = Evidence(
        quote=clip_sentences(passage, 300),
        document_id=None if doc.get("official") else doc["id"],
        official_doc_id=db_id if doc.get("official") else None,
        source_id=doc["source_id"],
        independence_group=group,
        stance=stance,  # type: ignore[typeddict-item]
        found_by=found_by,
        url=doc["url"],
        title=doc["source_name"],
        is_document=is_doc,
    )
    if not doc.get("official") and (doc["access_level"] == 2 or (fetched is not None and fetched.access_achieved == 2)):
        ev["by_headline"] = True  # DECISIONS.md › Sources: paywalled sources participate at level 2, marked "by headline"
    if doc.get("from_previous_day"):
        ev["from_previous_day"] = True
    return bind_quote(ev, doc, fetched)


def _candidates(state: RunState, event_doc_ids: list[int], round_no: int) -> list[DocRef]:
    docs = [d for d in state["documents"] if not d.get("superseded")]  # retracted text is not evidence; it still counts for spread
    if round_no <= 1:
        return [d for d in docs if d["id"] in event_doc_ids]
    # round 2: the rest of the day, official documents and the previous edition days (config research.previous_days)
    return [d for d in docs if d["id"] not in event_doc_ids]


def rank_candidates(claim_text: str, docs: list[DocRef], *, dry_run: bool, cap: int | None = None) -> list[DocRef]:
    """The documents worth a stance call for this claim: those whose best passage shares the most words with it,
    at most `research.candidates_per_claim` (0 = all), ties broken by publication time (newest first). Documents
    with no shared word are dropped (their best passage is empty: nothing to judge). Code only, no model call;
    the ranking is the engineering bound recorded in config/reasoning.toml."""
    cap = int(config.get("research", "candidates_per_claim", 0) or 0) if cap is None else cap
    cw = tokens(claim_text)
    scored = []
    for d in docs:
        fetched = fetch_result(d, dry_run=dry_run)
        passage = best_passage(claim_text, (fetched.text if fetched else None) or "")
        if not passage:
            continue
        scored.append((len(cw & tokens(passage)), d["published_at"], d))
    ordered = sorted(scored, key=lambda t: (t[0], t[1]), reverse=True)  # most shared words first, then the newest
    out = [d for _, _, d in ordered]
    return out[:cap] if cap > 0 else out


def run(state: RunState) -> dict:
    max_rounds = config.get("loops", "research_rounds_max", 2)
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    rounds = dict(state["research_rounds"])
    steps, errors = [], []
    for e in state["events"]:
        used = rounds.get(e["id"], 0)
        if used >= max_rounds:
            continue
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        if not event_claims:
            continue
        by_id = {d["id"]: d for d in state["documents"]}
        if used >= 1 and not any(is_thin(c["evidence"], origin_group(c, by_id)) for c in event_claims):
            continue  # nothing thin: no second round for this event
        round_no = used + 1
        targets = event_claims if round_no == 1 else [c for c in event_claims if is_thin(c["evidence"], origin_group(c, by_id))]
        with step(state, "research", event_id=e["id"], model=llm.model_name()) as s:
            found = 0
            failed_public: list[str] = []
            failed: list[str] = []  # one failed stance call skips one passage, never the event (decision in nodes/fact_check.py)
            asked: dict[tuple, str] = {}  # this event's stance answers by question (decision at stance_question)
            repeats = 0
            irrelevant = ungrounded = off_fact = supports_ungrounded = supports_off_fact = 0  # the relevance guards (decisions at relevant, untrusted.checked_stance, untrusted.off_fact)
            frequent, n_docs = topic_frequent(state)
            live = not llm.is_dry_run(state["dry_run"])  # the stand-in answers whenever llm.is_dry_run
            for c in targets:
                pool = [d for d in _candidates(state, e["document_ids"], round_no) if not (d["id"] == c["origin_document_id"] and not d.get("official")) and not already_seen(c, d, "researcher")]
                # round 1 judges every document of the event; round 2 ranks the wider corpus and keeps the top candidates
                candidates = pool if round_no <= 1 else rank_candidates(c["text"], pool, dry_run=state["dry_run"], cap=0 if memory.enabled(state) else None)
                if round_no > 1 and memory.enabled(state):
                    candidates, memory_steps, memory_errors = memory.prioritize(state | {"steps": state.get("steps", []) + steps}, e["id"], c["text"], candidates)
                    steps.extend(memory_steps); errors.extend(memory_errors)
                    cap = int(config.get("research", "candidates_per_claim", 0) or 0)
                    if cap > 0: candidates = candidates[:cap]
                for d in candidates:
                    fetched = fetch_result(d, dry_run=state["dry_run"])
                    before, passage, after = stance_window(c["text"], fetched)
                    if not passage:
                        continue
                    if not relevant(c["text"], passage):
                        irrelevant += 1
                        continue
                    question = stance_question("researcher", c["text"], passage, d, (before, after))
                    if question in asked:
                        stance = asked[question]
                        repeats += 1
                    else:
                        try:
                            ans = llm.json_task(
                                stance_task(d),
                                stance_payload(c["text"], before, passage, after, d, "researcher"),
                                dry_run=state["dry_run"],
                            )
                        except Exception as exc:  # noqa: BLE001
                            failed.append(f"{type(exc).__name__}: {str(exc)[:80]}")
                            failed_public.append(untrusted.public_failure(exc))
                            continue  # a failed question is not remembered: a repeat of it is asked again
                        stance, why = judged_stance(ans, c["text"], passage, frequent, live=live, context=(before, after))
                        ungrounded += why == "ungrounded"
                        off_fact += why == "off-fact"
                        supports_ungrounded += why == "support ungrounded"
                        supports_off_fact += why == "support off-fact"
                        asked[question] = stance
                    if stance == "neutral":
                        continue
                    c["evidence"] = c["evidence"] + [evidence_from(d, passage, stance, "researcher", fetched)]
                    found += 1
            s.decision = f"round {round_no}: {found} passages with a stance for {len(targets)} claims" + (f"; {len(failed)} stance calls failed" if failed else "") + (f" ({repeats} repeated questions skipped)" if repeats else "") + relevance_note(irrelevant, ungrounded, off_fact, supports_ungrounded, supports_off_fact)
            earlier = sum(1 for d in _candidates(state, e["document_ids"], round_no) if d.get("from_previous_day"))
            s.reason = ("event documents only" if round_no == 1 else f"widened to the rest of the day, official documents and {earlier} earlier-day documents for thin claims") + excluded_note(frequent, n_docs, [c["text"] for c in targets]) + ("; " + failed_public[0] if failed else "")
            if failed:
                errors.append(StepError(node="research", event_id=e["id"], message=f"round {round_no}: {len(failed)} stance call(s) failed, passages skipped: {failed[0]}"))
            rounds[e["id"]] = round_no
        steps.append(finish(state, s))
    return {"claims": claims, "research_rounds": rounds, "steps": steps, "errors": errors}
