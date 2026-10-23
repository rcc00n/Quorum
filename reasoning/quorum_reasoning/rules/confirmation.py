"""Confirmation rule (DECISIONS.md › Principles for handling facts).

A claim is confirmed by a signed/adopted official document, or by supporting evidence from at least two
different independence groups. Reprints of one wire story share an independence group and count once.
Statements by interested parties are never evidence for their own content.
"""

from __future__ import annotations

from ..state import ClaimStatus, Evidence

DOCUMENT_TYPES_THAT_ESTABLISH = {"law", "order", "vote", "ruling"}


def independent_support(evidence: list[Evidence]) -> set[str]:
    return {e["independence_group"] for e in evidence if e["stance"] == "supports" and e["independence_group"]}


def has_document_support(evidence: list[Evidence]) -> bool:
    return any(e["stance"] == "supports" and e["is_document"] for e in evidence)


def has_contradiction(evidence: list[Evidence]) -> bool:
    return any(e["stance"] == "contradicts" for e in evidence)


def verdict(evidence: list[Evidence]) -> tuple[ClaimStatus, str]:
    """Status by the rule, with a one-line reason the trace and the page can show."""
    groups = independent_support(evidence)
    contradicted = has_contradiction(evidence)
    if has_document_support(evidence):
        if contradicted:
            return "disputed", "a signed document supports it but another source contradicts it"
        return "confirmed", "stated in a signed or adopted official document"
    if len(groups) >= 2:
        if contradicted:
            return "disputed", f"supported by {len(groups)} independent groups but contradicted by another source"
        return "confirmed", f"supported by {len(groups)} independent groups: {', '.join(sorted(groups))}"
    if contradicted and groups:
        return "disputed", "one source supports it and another contradicts it"
    if len(groups) == 1:
        return "unverified", f"one independent group only ({next(iter(groups))}); needs a second or a document"
    return "unverified", "no supporting evidence beyond statements"


def is_thin(evidence: list[Evidence]) -> bool:
    """True when another research round could still change the verdict."""
    return not has_document_support(evidence) and len(independent_support(evidence)) < 2


def adjudicate(verifier: ClaimStatus, fact_checker: ClaimStatus) -> tuple[ClaimStatus, str]:
    """Two blind verdicts. Agreement is final; disagreement is shown as disputed, never resolved by guessing."""
    if verifier == fact_checker:
        return verifier, "verifier and fact-checker agree"
    return "disputed", f"verifier says {verifier}, fact-checker says {fact_checker}"
