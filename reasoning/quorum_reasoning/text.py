"""Small text helpers shared by nodes and dry-run stand-ins. No model, no I/O."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
# A sentence ends at . ! or ? followed by whitespace and a capital letter or quote, unless the period closes a
# one-letter abbreviation (H.R. 4521, U.S. Senate) or a common title (Mr. Smith, No. 5).
_SENT = re.compile(
    r"(?<![A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bNo\.)(?<!\bSt\.)(?<!\bLt\.)(?<!\bJr\.)(?<!\bSr\.)"
    r"(?<!\bGen\.)(?<!\bSen\.)(?<!\bRep\.)(?<!\bGov\.)(?<!\bCol\.)(?<!\bMaj\.)(?<!\bAdm\.)(?<!\bProf\.)(?<!\bMrs\.)"
    r"(?<=[.!?])\s+(?=[A-Z\"'“‘(])"
)


# A line break (one or more, with any surrounding whitespace) always ends a sentence.
_LINES = re.compile(r"\s*\n\s*")


def sentences(text: str) -> list[str]:
    """The sentences of `text`: each line split at sentence ends (abbreviation-aware, _SENT); a newline is a hard
    boundary. Every sentence is a verbatim substring of `text` (stripped), so a quote cut from one is found in it.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a newline ends a sentence. Why: a photo credit line glued to
    the next paragraph ("…/Getty Images", blank line, "Meanwhile, …") became one passage; in the 2026-10-24 run-3/5
    journals 37 stance rows whose passage starts with such a caption came back `contradicts` (D5).
    """
    return [s.strip() for line in _LINES.split(text or "") for s in _SENT.split(line) if s.strip()]


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
    # the prefix is cut from `text` itself, not re-joined, so the quote stays verbatim when sentences are separated
    # by a newline or several spaces (a newline is a sentence boundary, see sentences)
    out, pos = "", 0
    for sent in sentences(text):
        end = text.find(sent, pos) + len(sent)
        if end > limit:
            break
        out, pos = text[:end], end
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


def passage_window(claim_text: str, text: str, n: int) -> tuple[str, str, str]:
    """(before, passage, after): the sentence of `text` sharing the most words with the claim (the first on a tie;
    empty when nothing is shared) and up to `n` sentences on each side, joined by a space; empty at the edges."""
    sents = sentences(text)
    cw = tokens(claim_text)
    best, best_score = -1, 0
    for i, sent in enumerate(sents):
        score = len(cw & tokens(sent))
        if score > best_score:
            best, best_score = i, score
    if best < 0:
        return "", "", ""
    return " ".join(sents[max(0, best - n) : best]), sents[best], " ".join(sents[best + 1 : best + 1 + n])


def best_passage(claim_text: str, text: str) -> str:
    """The sentence of `text` that shares the most words with the claim; empty when nothing is shared."""
    return passage_window(claim_text, text, 0)[1]


def frequent_stems(texts: list[str], k: int = 5, share: float = 0.3) -> set[str]:
    """The topic's most common stems: the top `k` by document frequency over `texts` (ties broken alphabetically)
    plus every stem found in more than `share` of them. Deterministic for the same texts."""
    from collections import Counter

    df = Counter(s for t in texts for s in stems(t))
    top = {s for s, _ in sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))[:k]}
    return top | {s for s, c in df.items() if texts and c / len(texts) > share}


COMPOSITION_MIN = 2  # the composition floor (untrusted.COMPOSITION_STEMS_MIN is the same number of covered stems)


def keeps_full_stems(claim_text: str, frequent: set[str]) -> bool:
    """True when excluding the topic's frequent stems would leave the claim fewer than COMPOSITION_MIN stems while
    excluding something; such a claim keeps its full stem set (fact_composition)."""
    full = stems(claim_text)
    return bool(full & frequent) and len(full - frequent) < COMPOSITION_MIN


def fact_composition(claim_text: str, frequent: set[str]) -> set[str]:
    """The claim's significant stems minus the topic's most common ones: what makes this fact this fact. When fewer
    than COMPOSITION_MIN stems would remain, the full stem set (keeps_full_stems).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a claim made of frequent names ("Trump met Zelensky") keeps
    its full stem set instead of an empty composition. Why: such a claim must still be contradictable; with the
    exclusion it could never reach the 2-stem floor. Owner's decision (Yelysei, 2026-10-25).
    """
    full = stems(claim_text)
    return full if keeps_full_stems(claim_text, frequent) else full - frequent


def composition_coverage(claim_text: str, passage: str, frequent: set[str]) -> tuple[float, int]:
    """(share, count) of the claim's fact composition found among the passage's stems; (0.0, 0) for an empty composition."""
    comp = fact_composition(claim_text, frequent)
    if not comp:
        return 0.0, 0
    hit = len(comp & stems(passage))
    return hit / len(comp), hit


_MONTH_NUM = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+{_DAY}\b|\b{_DAY}\s+(?:of\s+)?{_MONTH}(?![a-z])", re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)


def stated_dates(text: str) -> dict[str, set[str]]:
    """Explicit dates in `text` by kind: "day" ("10-22" for October 22 / 22 Oct) and "weekday" ("tuesday").
    A month alone or a bare number is not a date here."""
    days = set()
    for m in _MONTH_DAY.finditer(text or ""):
        month, day = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        if 1 <= int(day) <= 31:
            days.add(f"{_MONTH_NUM[month.lower()[:3]]}-{int(day)}")
    return {"day": days, "weekday": {w.lower() for w in _WEEKDAY.findall(text or "")}}


def different_day(claim_text: str, passage: str) -> bool:
    """True when both sides state a date of the same kind, those dates differ, and no stated date of any kind matches."""
    a, b = stated_dates(claim_text), stated_dates(passage)
    both = [k for k in a if a[k] and b[k]]
    return bool(both) and not any(a[k] & b[k] for k in both)
