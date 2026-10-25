"""review_disputed: a third blind pass over claims the verifier and the fact-checker disagree on.

Entered only when `adjudicate` left at least one claim `disputed` because of a *disagreement* (verifier says
X, fact-checker says Y). A claim both checkers call disputed is a genuine evidence contradiction and is not
reviewed. The reviewer sees the claim and both evidence chains as data — quotes, stances, independence
groups, document flags — and the two verdict labels it must choose between; not the checkers' reasons, not
the corpus, no fetching, no new evidence. One pass per claim (`loops.review_disputed_max`), never repeated.

Code validates the answer (DECISIONS.md › Principles for handling facts, decided 2026-10-24): the verdict must
be one of the two blind verdicts or `disputed`; the decisive quote must be found in the cited evidence row; and
`confirmed` is accepted only when the cited chain itself satisfies the confirmation rule — the reviewer picks
which chain to trust, the rule still decides what that chain proves. An invalid answer leaves the claim
disputed with "third review invalid" in the adjudication. All three verdicts stay on the claim and in the
snapshot (`reviewer_status`, `reviewer_reason`, `reviewer_quote`, `resolved_by`). The bar and the cap are then
re-applied, because a resolved claim changes an event's confirmed count.
"""

from __future__ import annotations

from typing import Any, Literal

from .. import config, llm, untrusted
from ..rules.confirmation import origin_group, verdict
from ..state import Claim, Evidence, RunState, StepError
from ..text import containment
from ..trace import finish, step
from .adjudicate import apply_bar

CHAINS = ("verifier", "fact_checker")


def chain_evidence(claim: Claim, chain: str) -> list[Evidence]:
    if chain == "verifier":
        return [ev for ev in claim["evidence"] if ev["found_by"] in ("researcher", "verifier")]
    return [ev for ev in claim["evidence"] if ev["found_by"] == "fact_checker"]


def is_disagreement(claim: Claim) -> bool:
    """A disputed final status that comes from the two checkers disagreeing, not from both calling it disputed."""
    v, f = claim.get("verifier_status"), claim.get("fact_checker_status")
    return claim.get("final_status") == "disputed" and v is not None and f is not None and v != f


def pending(state: RunState) -> list[Claim]:
    max_passes = int(config.get("loops", "review_disputed_max", 1))
    # a claim whose fact-check was skipped by the bar gate has no second verdict to reconcile (see nodes/adjudicate.py)
    return [c for c in state["claims"].values() if is_disagreement(c) and not c.get("fact_check_skipped") and c.get("review_passes", 0) < max_passes]


def _chain_payload(rows: list[Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "index": i,
            "quote": untrusted.clip(ev["quote"], untrusted.CAP_PASSAGE),
            "stance": ev["stance"],
            "source": untrusted.clip(ev["title"], untrusted.CAP_TITLE),
            "independence_group": ev["independence_group"],
            "is_document": ev["is_document"],
            "by_headline": bool(ev.get("by_headline")),
        }
        for i, ev in enumerate(rows)
    ]


def payload_for(claim: Claim) -> dict[str, Any]:
    return {
        "claim": untrusted.clip(claim["text"], untrusted.CAP_CLAIM),
        "kind": claim["kind"],
        "speaker": claim.get("speaker"),
        "verifier": {"verdict": claim["verifier_status"], "evidence": _chain_payload(chain_evidence(claim, "verifier"))},
        "fact_checker": {"verdict": claim["fact_checker_status"], "evidence": _chain_payload(chain_evidence(claim, "fact_checker"))},
        "allowed_verdicts": sorted({claim["verifier_status"], claim["fact_checker_status"], "disputed"}),  # type: ignore[arg-type]
    }


def validate(claim: Claim, ans: dict[str, Any], origin: str | None) -> tuple[str | None, str, str, str]:
    """(accepted verdict or None, reason, decisive quote, why invalid). Code gates every part of the answer."""
    allowed = {claim["verifier_status"], claim["fact_checker_status"], "disputed"}
    reviewer_verdict = ans.get("verdict")
    reason = untrusted.clip(ans.get("reason", ""), untrusted.CAP_LABEL)
    quote = untrusted.clip(ans.get("decisive_quote", ""), untrusted.CAP_PASSAGE)
    if reviewer_verdict not in allowed:
        return None, reason, quote, f"verdict {reviewer_verdict!r} is not one of the two blind verdicts or disputed"
    if reviewer_verdict == "disputed":
        return "disputed", reason, quote, ""
    chain = ans.get("decisive_chain")
    if chain not in CHAINS:
        return None, reason, quote, f"decisive_chain {chain!r} is not verifier or fact_checker"
    rows = chain_evidence(claim, chain)
    idx = ans.get("decisive_index")
    if not isinstance(idx, int) or not 0 <= idx < len(rows):
        return None, reason, quote, f"decisive_index {idx!r} names no evidence row of the {chain} chain"
    cited = rows[idx]["quote"]
    if not quote.strip() or not (quote.strip().lower() in cited.lower() or containment(quote, cited) >= untrusted.GROUNDING_MIN):
        return None, reason, quote, "decisive quote not found in the cited evidence row"
    # The reviewer may side with a chain; the confirmation rule still decides what that chain proves. This gate
    # comes first so an overturn to confirmed is always named for what it is.
    rule_status, _ = verdict(rows, origin)
    if reviewer_verdict == "confirmed" and rule_status != "confirmed":
        return None, reason, quote, f"sided with the {chain} chain for confirmed, but that chain is {rule_status} under the confirmation rule"
    if reviewer_verdict == "confirmed" and any(ev["stance"] == "contradicts" for ev in claim["evidence"]):
        return None, reason, quote, "cannot confirm: the other chain holds a contradicting passage (supporting and contradicting evidence both exist → disputed)"
    if reviewer_verdict != claim[f"{chain}_status"]:  # type: ignore[literal-required]
        return None, reason, quote, f"verdict {reviewer_verdict} does not match the cited {chain} chain's verdict"
    return reviewer_verdict, reason, quote, ""


def run(state: RunState) -> dict:
    claims = {cid: dict(c) for cid, c in state["claims"].items()}
    by_id = {d["id"]: d for d in state["documents"]}
    steps, errors = [], []
    reviewed = 0
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the node reviews exactly the claims `pending()` names, the
    # same predicate the router uses, so a claim excluded there (the bar gate's `fact_check_skipped`) is never reviewed
    # here. Why: attempt 3 of 2026-10-24 reviewed 41 gated claims on the large model because this loop re-derived the
    # selection without the marker; one predicate, one place.
    to_review = {c["id"] for c in pending(state)}
    for cid, c in claims.items():
        if cid not in to_review:
            continue
        c["review_passes"] = c.get("review_passes", 0) + 1
        reviewed += 1
        with step(state, "review_disputed", event_id=c["event_id"], model=llm.model_name("reviewer")) as s:
            try:
                ans = llm.json_task("review_disputed", payload_for(c), dry_run=state["dry_run"], which="reviewer")
                accepted, reason, quote, why_invalid = validate(c, ans, origin_group(c, by_id))
            except Exception as exc:  # noqa: BLE001 — a failed pass keeps the dispute; the trace shows it
                errors.append(StepError(node="review_disputed", event_id=c["event_id"], message=str(exc)[:300]))
                accepted, reason, quote, why_invalid = None, "", "", untrusted.public_failure(exc)
            c["reviewer_reason"] = reason
            c["reviewer_quote"] = quote
            if accepted is None:
                c["reviewer_status"] = None
                c["resolved_by"] = "dispute"
                c["adjudication"] = f"{c['adjudication']}; third review invalid: {why_invalid}"
                s.decision = "kept disputed: third pass invalid"
                s.reason = why_invalid
            elif accepted == "disputed":
                c["reviewer_status"] = "disputed"
                c["resolved_by"] = "dispute"
                c["adjudication"] = f"{c['adjudication']}; third reviewer kept the dispute"
                s.decision = "kept disputed"
                s.reason = reason or "the reviewer found neither chain decisive"
            else:
                sided = "verifier" if accepted == c["verifier_status"] else "fact-checker"
                c["reviewer_status"] = accepted
                c["final_status"] = accepted
                c["resolved_by"] = "reviewer"
                c["adjudication"] = f"{c['adjudication']}; third reviewer sided with the {sided}: {accepted}"
                s.decision = f"sided with the {sided}: {accepted}"
                s.reason = reason or "decisive quote found in the cited chain"
        steps.append(finish(state, s))
    events = state["events"]
    if reviewed:
        events = apply_bar([dict(e) for e in state["events"]], claims, by_id)  # type: ignore[misc]
        with step(state, "review_disputed") as s:
            above = sum(1 for e in events if e["above_bar"])
            s.decision = f"{reviewed} disagreement(s) reviewed; bar re-applied: {above} of {len(events)} events above, {sum(e['needs_review'] for e in events)} flagged"
            s.reason = "a resolved claim changes an event's confirmed count; the rule and the cap are code"
        steps.append(finish(state, s))
    return {"claims": claims, "events": events, "steps": steps, "errors": errors}


def route(state: RunState) -> Literal["escalate", "frame"]:
    return "escalate" if any(e["needs_review"] and not e["above_bar"] for e in state["events"]) else "frame"
