"""Confirmation rule (DECISIONS.md › Principles for handling facts).

A claim is confirmed by a signed/adopted official document, or by supporting evidence from at least two
different independence groups — where the origin document's own group counts as one of the two when the
origin is an agency or an outlet, never an interested party's statement (decided 2026-10-24; DECISIONS.md
log). Reprints of one wire story share an independence group and count once. Statements by interested
parties are never evidence for their own content.
"""

from __future__ import annotations

from ..state import Claim, ClaimStatus, DocRef, Evidence

DOCUMENT_TYPES_THAT_ESTABLISH = {"law", "order", "vote", "ruling"}

ORIGIN_KINDS_THAT_COUNT = {"agency", "outlet"}


def origin_group(claim: Claim, documents_by_id: dict[int, DocRef]) -> str | None:
    """The independence group the claim's origin document contributes, or None.

    Only an agency or an outlet counts (an official body or an attributed-only military source asserting
    its own claim is the party's words); a wire reprint contributes the wire's group, same as
    research.evidence_from; a superseded document contributes nothing.
    """
    if claim.get("kind") == "statement":
        return None  # the outlet reported that the words were said; that is not evidence for their content
    doc = documents_by_id.get(claim["origin_document_id"] or -1)
    if not doc or doc.get("official") or doc.get("superseded") or doc["kind"] not in ORIGIN_KINDS_THAT_COUNT:
        return None
    return (doc.get("wire_origin") or "").strip().lower() or doc["independence_group"]


def independent_support(evidence: list[Evidence], origin: str | None = None) -> set[str]:
    groups = {e["independence_group"] for e in evidence if e["stance"] == "supports" and e["independence_group"]}
    if origin and groups - {origin}:
        groups.add(origin)  # the origin counts only alongside at least one other group: it cannot confirm alone
    return groups


def has_document_support(evidence: list[Evidence]) -> bool:
    return any(e["stance"] == "supports" and e["is_document"] for e in evidence)


def has_contradiction(evidence: list[Evidence]) -> bool:
    return any(e["stance"] == "contradicts" for e in evidence)


def verdict(evidence: list[Evidence], origin: str | None = None) -> tuple[ClaimStatus, str]:
    """Status by the rule, with a one-line reason the trace and the page can show.

    `origin` is the group the claim's origin document contributes (rules/confirmation.origin_group); it
    counts toward the two only next to at least one other group — the origin plus one other confirms.
    """
    groups = independent_support(evidence, origin)
    contradicted = has_contradiction(evidence)
    if has_document_support(evidence):
        if contradicted:
            return "disputed", "a signed document supports it but another source contradicts it"
        return "confirmed", "stated in a signed or adopted official document"
    if len(groups) >= 2:
        named = ", ".join(sorted(groups)) + (f" (the origin outlet, {origin}, counts as one)" if origin in groups else "")
        if contradicted:
            return "disputed", f"supported by {len(groups)} independent groups but contradicted by another source"
        return "confirmed", f"supported by {len(groups)} independent groups: {named}"
    if contradicted and groups:
        return "disputed", "one source supports it and another contradicts it"
    if len(groups) == 1:
        return "unverified", f"one independent group only ({next(iter(groups))}); needs a second or a document"
    if contradicted:
        return "unverified", "no source supports it and at least one contradicts it"
    return "unverified", "no supporting evidence beyond statements"


def is_thin(evidence: list[Evidence], origin: str | None = None) -> bool:
    """True when another research round could still change the verdict."""
    return not has_document_support(evidence) and len(independent_support(evidence, origin)) < 2


def adjudicate(verifier: ClaimStatus, fact_checker: ClaimStatus) -> tuple[ClaimStatus, str]:
    """Two blind verdicts. Agreement is final; disagreement is shown as disputed, never resolved by guessing."""
    if verifier == fact_checker:
        return verifier, "verifier and fact-checker agree"
    return "disputed", f"verifier says {verifier}, fact-checker says {fact_checker}"
