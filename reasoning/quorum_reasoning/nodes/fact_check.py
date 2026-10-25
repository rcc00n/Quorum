"""fact_check: a blind second verdict per claim.

The fact-checker sees the claim texts and the corpus, nothing the researcher or the verifier produced. It
has the same access to the documents (same levels, same robots rules), picks its own passages, asks the
model for stance under its own prompt (prompts/stance.md, or stance_document.md for an official law, order,
vote or ruling; role fact_checker: look for reasons the claim could be wrong) and applies the same confirmation
rule to its own evidence. Its evidence rows carry found_by="fact_checker" so the snapshot shows both chains side by side. Route "fact_checker" in
config/reasoning.toml may point at a different provider when the rules allow. The model's stance answer is
untrusted: only the four allowed stance words are accepted, anything else counts as neutral; the same two relevance
guards as research apply (research.relevant before the call, research.judged_stance after it).
"""

from __future__ import annotations

from collections import Counter

from .. import llm
from ..rules.confirmation import origin_group, verdict
from ..rules.impact_bar import POINT_RANGES, cannot_reach_bar, judged_points, threshold
from ..state import RunState, StepError
from ..tools.fetch_text import fetch_result
from ..trace import finish, step
from .research import (
    already_seen, evidence_from, excluded_note, judged_stance, rank_candidates, relevance_note, relevant, stance_payload,
    stance_question, stance_task, stance_window, topic_frequent,
)


def run(state: RunState) -> dict:
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    docs = [d for d in state["documents"] if not d.get("superseded")]  # retracted text is not evidence
    by_id = {d["id"]: d for d in state["documents"]}
    steps, errors = [], []
    for e in state["events"]:
        event_claims = [c for c in claims.values() if c["event_id"] == e["id"]]
        if not event_claims:
            continue
        # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): an event that cannot reach the impact bar gets no blind
        # fact-check (no model call); its claims are marked skipped and unverified by the fact-checker. Why: see
        # docs/DECISIONS.md › Selecting major news (bar gate, 2026-10-24).
        if cannot_reach_bar(e["rubric"]):
            with step(state, "fact_check", event_id=e["id"]) as s:
                why = f"({judged_points(e['rubric'])} + {POINT_RANGES['confirmation'][1]} < {threshold()})"
                for c in event_claims:
                    c["fact_checker_status"] = "unverified"
                    c["fact_checker_reason"] = f"skipped: event cannot reach the impact bar {why}; not double-checked"
                    c["fact_check_skipped"] = True
                s.decision = f"skipped: event cannot reach the impact bar; {len(event_claims)} claims not double-checked"
                s.reason = f"judged points plus the maximum confirmation score fall short of the threshold {why}"
            steps.append(finish(state, s))
            continue
        with step(state, "fact_check", event_id=e["id"], model=llm.model_name("fact_checker")) as s:
            counts: Counter[str] = Counter()
            found = 0
            failed: list[str] = []
            # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a failed stance call skips that one passage and the
            # loop goes on; the claim's verdict comes from the passages that were judged, and the event's trace row and
            # one StepError carry the failure count. Why: on the first genuine run one HTTP 429 aborted the whole
            # event's fact-check, 155 of 189 claims were marked "fact-checker failed; treated as unverified", and
            # every disagreement that produced was an artifact of the error path, not of the evidence.
            judged_calls = 0
            asked: dict[tuple, str] = {}  # this event's stance answers by question (decision at research.stance_question)
            repeats = 0
            irrelevant = ungrounded = off_fact = 0  # the relevance guards (decisions at research.relevant, untrusted.checked_stance, untrusted.off_fact)
            frequent, n_docs = topic_frequent(state)
            live = not llm.is_dry_run(state["dry_run"])
            for c in event_claims:
                failed_before = len(failed)
                judged_before = judged_calls
                pool = [d for d in docs if not (d["id"] == c["origin_document_id"] and not d.get("official")) and not already_seen(c, d, "fact_checker")]
                # the fact-checker has the researcher's access to the whole corpus; the same code ranking bounds its calls
                for d in rank_candidates(c["text"], pool, dry_run=state["dry_run"]):
                    fetched = fetch_result(d, dry_run=state["dry_run"])
                    before, passage, after = stance_window(c["text"], fetched)
                    if not passage:
                        continue
                    if not relevant(c["text"], passage):  # not asked, so not judged
                        irrelevant += 1
                        continue
                    question = stance_question("fact_checker", c["text"], passage, d, (before, after))
                    if question in asked:
                        stance = asked[question]
                        repeats += 1
                        # a reused answer is a judgement the fact-checker made, so it counts as judged for this claim;
                        # otherwise a claim answered only from the cache plus one failed call would read as "not
                        # double-checked" in adjudicate (judged 0 with failures)
                        judged_calls += 1
                    else:
                        try:
                            ans = llm.json_task(
                                stance_task(d),  # decision at research.stance_task
                                stance_payload(c["text"], before, passage, after, d, "fact_checker"),
                                dry_run=state["dry_run"],
                                which="fact_checker",
                            )
                        except Exception as exc:  # noqa: BLE001 — one passage lost, the claim and the event go on
                            failed.append(f"{type(exc).__name__}: {str(exc)[:80]}")
                            continue  # a failed question is not remembered: a repeat of it is asked again
                        judged_calls += 1
                        stance, why = judged_stance(ans, c["text"], passage, frequent, live=live, context=(before, after))
                        ungrounded += why == "ungrounded"
                        off_fact += why == "off-fact"
                        asked[question] = stance
                    if stance == "neutral":
                        continue
                    c["evidence"] = c["evidence"] + [evidence_from(d, passage, stance, "fact_checker", fetched)]
                    found += 1
                own = [ev for ev in c["evidence"] if ev["found_by"] == "fact_checker"]
                status, reason = verdict(own, origin_group(c, by_id))
                lost = len(failed) - failed_before
                judged = judged_calls - judged_before
                c["fact_checker_status"] = status
                c["fact_checker_reason"] = reason + (f" ({lost} stance call(s) failed for this claim)" if lost else "")
                c["fact_checker_judged"] = judged  # 0 with failures = unavailable, not a verdict (adjudicate reads it)
                counts[status] += 1
            s.decision = f"{counts['confirmed']} confirmed, {counts['disputed']} disputed, {counts['unverified']} unverified from {found} own passages" + (f"; {len(failed)} stance calls failed" if failed else "") + (f" ({repeats} repeated questions skipped)" if repeats else "") + relevance_note(irrelevant, ungrounded, off_fact)
            s.reason = "blind: own passages and own stance calls, nothing from the researcher or the verifier" + excluded_note(frequent, n_docs, [c["text"] for c in event_claims]) + (f"; failures: {failed[0]}" if failed else "")
            if failed:
                errors.append(StepError(node="fact_check", event_id=e["id"], message=f"{len(failed)} stance call(s) failed, passages skipped: {failed[0]}"))
        steps.append(finish(state, s))
    return {"claims": claims, "steps": steps, "errors": errors}
