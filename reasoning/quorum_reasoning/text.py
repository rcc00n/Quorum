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


def clip_sentences(text: str, limit: int) -> str:
    """The longest prefix of whole sentences within `limit` characters.

    DECISION(2026-10-23, Yelysei Shkirpan/Claude Code): a stored quote never ends mid-sentence. Why: a
    character cut can drop the half of a sentence that reverses its meaning ("... the convoy did" with
    "not cross" gone); only when a single sentence exceeds the limit does a word-boundary cut apply.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    out = ""
    for sent in sentences(text):
        candidate = (out + " " + sent).strip()
        if len(candidate) > limit:
            break
        out = candidate
    if out:
        return out
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


_SUFFIXES = ("ingly", "edly", "ings", "ing", "ions", "ion", "ies", "es", "ed", "ly", "s")


def stem(token: str) -> str:
    """A light suffix stripper: signs/signed/signing -> sign, inspections -> inspect, talks -> talk.

    A filter aid for grouping, never a judge (reasoning/README.md › Decisions, clustering 2026-10-24):
    it only widens matches between inflections; the model decides borderline pairs.
    """
    t = token.lower()
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: len(t) - len(suf)]
    return t


_STEM_STOP = {
    stem(w)
    for w in (
        "the and for into onto under over between after before during from with that this these those its "
        "are was were has have had will would can could says said say new also not when where while"
    ).split()
}


def stems(text: str) -> set[str]:
    """Stemmed significant tokens of `text`: `tokens` minus function words, each suffix-stripped."""
    return {stem(t) for t in tokens(text)} - _STEM_STOP


def overlap_coefficient(a: set[str], b: set[str]) -> float:
    """|a ∩ b| / min(|a|, |b|): 1.0 when the smaller set is contained in the larger."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def best_passage(claim_text: str, text: str) -> str:
    """The sentence of `text` that shares the most words with the claim; empty when nothing is shared."""
    cw = tokens(claim_text)
    best, best_score = "", 0
    for sent in sentences(text):
        score = len(cw & tokens(sent))
        if score > best_score:
            best, best_score = sent, score
    return best
