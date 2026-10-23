"""Small text helpers shared by nodes and dry-run stand-ins. No model, no I/O."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
# A sentence ends at . ! or ? followed by whitespace and a capital letter or quote, unless the period closes a
# one-letter abbreviation (H.R. 4521, U.S. Senate) or a common title (Mr. Smith, No. 5).
_SENT = re.compile(r"(?<![A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bNo\.)(?<!\bSt\.)(?<=[.!?])\s+(?=[A-Z\"'“‘(])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s.strip()]


def tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if len(t) > 2}


def overlap(a: str, b: str) -> float:
    """Jaccard overlap of the two token sets."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def containment(claim: str, passage: str) -> float:
    """Share of the claim's tokens that appear in the passage."""
    tc, tp = tokens(claim), tokens(passage)
    if not tc:
        return 0.0
    return len(tc & tp) / len(tc)


def best_passage(claim_text: str, text: str) -> str:
    """The sentence of `text` that shares the most words with the claim; empty when nothing is shared."""
    cw = tokens(claim_text)
    best, best_score = "", 0
    for sent in sentences(text):
        score = len(cw & tokens(sent))
        if score > best_score:
            best, best_score = sent, score
    return best
