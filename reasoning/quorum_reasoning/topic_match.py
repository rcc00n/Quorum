"""Collection's topic matcher, and the official-document seed rule built on it (2026-10-26).

`matches_topic`, `topic_match_of` and `first_topic_match` are copies of collectors/common.py (branch
data-collection, 2026-10-25): a term matches when it occurs as a whole word, case-insensitively (`\\b` on both sides
of the escaped, lower-cased term; Unicode word characters count, so "Zürich" and "Молдова" match as words).
tests/test_official_seed.py pins the same results on shared vectors and compares them with collectors.common when
that package can be imported; change both sides together.

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): copied, not imported from collectors.common. Why: reasoning runs
where the collectors package cannot be imported (tools/fetch_text.py keeps a fallback for the same reason), and the
seed rule must give the same verdict as collection's own gate on any machine; a copy pinned by test vectors is the
smallest dependency. The rule itself is in docs/DECISIONS.md › Sources (official documents: seed rule).
"""

from __future__ import annotations

import ast
import html
import json
import re
from typing import Any, Iterable

from .state import DocRef

# ------------------------------------------------- collection's matcher, copied ----


def matches_topic(text: str, query_terms: Iterable[str]) -> bool:
    """Case-insensitive whole-word match of any term. Cheap gate before any fetch."""
    haystack = (text or "").lower()
    for term in query_terms:
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", haystack):
            return True
    return False


def topic_match_of(title: str, lead: str | None, query_terms: Iterable[str]) -> str | None:
    """'title' when a term is in the headline, 'lead' when only in the summary, else None (documents.topic_match)."""
    terms = list(query_terms)
    if matches_topic(title, terms):
        return "title"
    if lead and matches_topic(lead, terms):
        return "lead"
    return None


def first_topic_match(title: str, lead: str | None, topics: list[dict]) -> tuple[dict, str] | tuple[None, None]:
    """The first topic in list order whose terms match, with where it matched: (topic, 'title' | 'lead')."""
    for topic in topics:
        match = topic_match_of(title, lead, topic["query_terms"])
        if match:
            return topic, match
    return None, None


# ------------------------------------------------------- query_terms parsing ----


def _pg_array(text: str) -> list[str | None] | None:
    """A one-dimensional Postgres array literal (`{a,"b c",NULL}`) as a list; None when it is not one."""
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1]
    out: list[str | None] = []
    i, n = 0, len(body)
    if not body.strip():
        return out
    while i <= n:
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i < n and body[i] == '"':
            i += 1
            buf = []
            while i < n and body[i] != '"':
                if body[i] == "\\" and i + 1 < n:
                    i += 1
                buf.append(body[i])
                i += 1
            if i >= n:
                return None  # unterminated quote
            i += 1
            while i < n and body[i] in " \t\r\n":
                i += 1
            out.append("".join(buf))
        else:
            j = i
            while j < n and body[j] != ",":
                if body[j] in '{}"':
                    return None  # nested array or a stray quote: not a text[] we can read
                j += 1
            raw = body[i:j].strip()
            if not raw:
                return None  # an empty unquoted element is not valid array syntax
            out.append(None if raw.upper() == "NULL" else raw)
            i = j
        if i >= n:
            break
        if body[i] != ",":
            return None
        i += 1
        if i >= n:
            return None  # trailing comma
    return out


def parse_query_terms(value: Any) -> list[str] | None:
    """`topics.query_terms` as delivered: a list, or a string (Zetaris returns every column as one: the Postgres array
    literal `{Ukraine,"trade war"}`; a JSON or Python list literal is accepted too). Terms are stripped and empty ones
    dropped, as collection's `load_topics` does. None when the value is missing or cannot be read; [] when it is an
    empty array."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        items: list[Any] | None = list(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s or s == "None":
            return None
        items = _pg_array(s)
        if items is None and s.startswith("["):
            try:
                items = json.loads(s)
            except ValueError:
                try:
                    items = ast.literal_eval(s)
                except (ValueError, SyntaxError):
                    items = None
            if not isinstance(items, (list, tuple)):
                items = None
    else:
        items = None
    if items is None:
        return None
    if any(t is not None and not isinstance(t, str) for t in items):
        return None
    return [t.strip() for t in items if t and t.strip()]


# --------------------------------------------------- official-document abstract ----

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAGS = re.compile(r"<[^>]+>")
# The Federal Register's own abstract: the paragraph after "SUMMARY:", up to a blank line or the next caps heading
# ("DATES:", "ADDRESSES:", "FOR FURTHER INFORMATION CONTACT:").
_SUMMARY = re.compile(r"^[ \t]*SUMMARY:[ \t]*(.+?)(?=\n[ \t]*\n|\n[ \t]*[A-Z][A-Z .,'/&()-]{2,60}:|\Z)", re.M | re.S)
# The Federal Register's page header ends with the "[FR Doc No: ...]" line; separator rules are runs of - or =.
_FR_HEADER_END = re.compile(r"^\s*\[FR Doc No:[^\]\n]*\]\s*$", re.M)
_RULE = re.compile(r"[-=]{5,}")
LEAD_MAX = 600  # collection's cap on documents.lead (collectors/common.py LEAD_MAX)
ABSTRACT_MAX = 4000  # a safety bound on the SUMMARY paragraph; Federal Register summaries run to ~2 000 characters


def official_abstract(text: str | None) -> str:
    """The abstract of an official document, for the seed rule: its "SUMMARY:" paragraph when it has one (Federal
    Register rules, proposed rules and notices), else its first LEAD_MAX characters after the Federal Register page
    header, if any (a presidential document's opening; a bill's title, latest action and the start of its summary; a
    White House release's opening). Tags are stripped, entities unescaped and whitespace collapsed, as collection's
    `clean_field` does for a lead, so a term broken over a line still matches.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): reasoning derives the abstract from `official_docs.full_text`.
    Why: official_docs stores no abstract column and the corpus SQL delivers `lead` empty for official rows; the
    Federal Register API's `abstract` field is the document's SUMMARY paragraph, so the same text is recovered from the
    raw text collection stored. The first-600-characters fallback mirrors collection's lead cap.
    """
    if not text:
        return ""
    cleaned = html.unescape(_TAGS.sub(" ", _CONTROL.sub("", text)))
    m = _SUMMARY.search(cleaned)
    if m:
        return " ".join(m.group(1).split())[:ABSTRACT_MAX]
    header = _FR_HEADER_END.search(cleaned[:2000])
    body = cleaned[header.end():] if header else cleaned
    return " ".join(_RULE.sub(" ", body).split())[:LEAD_MAX]


# ------------------------------------------------------------- the seed rule ----


def official_seed_match(doc: DocRef, terms: list[str] | None) -> str | None:
    """'title' or 'lead' (the abstract) where a term of the run's topic matches the official document; None when
    neither carries one, or when the topic's terms are unknown (None or empty: nothing can match)."""
    if not terms:
        return None
    return topic_match_of(doc.get("title") or "", doc.get("lead") or official_abstract(doc.get("text")), terms)


def official_seed_flags(docs: list[DocRef], terms: list[str] | None) -> tuple[list[DocRef], dict[str, int]]:
    """The documents with the seed rule applied to every official document of the edition window: `seed_match`
    ('title' | 'lead' | None) and `evidence_only` (True when nothing matched: research round 2 and the fact-checker
    may still use it, but it starts no event and is never a roundup item by itself). Earlier-day documents are left
    as they are (never an event anyway). Returns copies, never the caller's dicts, and the counts for the trace."""
    out: list[DocRef] = []
    counts = {"official": 0, "title": 0, "lead": 0, "evidence_only": 0}
    for d in docs:
        if not d.get("official") or d.get("from_previous_day"):
            out.append(d)
            continue
        ref: DocRef = dict(d)  # type: ignore[assignment]
        match = official_seed_match(ref, terms)
        ref["seed_match"] = match
        ref["evidence_only"] = match is None
        counts["official"] += 1
        counts[match or "evidence_only"] += 1
        out.append(ref)
    return out, counts
