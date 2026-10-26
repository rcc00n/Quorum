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
# The Federal Register's plain text sets every page break, "[[Page N]]", between blank lines, also inside a paragraph:
# the marker goes together with the blank lines around it, so the paragraph it cut reads on as one.
_PAGE_BREAK = re.compile(r"\n[ \t]*\n[ \t]*\[\[Page \d+\]\][ \t]*\n(?:[ \t]*\n)*")
_PAGE_MARK = re.compile(r"\[\[Page \d+\]\]")
# The enacting clause that opens an executive order or a memorandum ("By the authority vested in me as President by the
# Constitution and the laws of the United States of America, including ... section 301 of title 3, United States Code,
# it is hereby ordered:"): statutes cited as authority, not what the order does. Up to its colon, inside one paragraph.
_AUTHORITY = re.compile(r"\bBy the authority vested in me\b(?:(?!\n[ \t]*\n)[^:]){0,1500}:", re.I)
FEDERAL_REGISTER = "federal-register"  # collectors/sources.csv id of the Federal Register
LEAD_MAX = 600  # collection's cap on documents.lead (collectors/common.py LEAD_MAX)
ABSTRACT_MAX = 4000  # a safety bound on the SUMMARY paragraph; Federal Register summaries run to ~2 000 characters


def official_abstract(text: str | None, source_id: str | None = None) -> str:
    """The abstract of an official document, for the seed rule: its "SUMMARY:" paragraph when it has one (Federal
    Register rules, proposed rules and notices). A Federal Register document without one (source `federal-register`,
    or a text carrying the Federal Register page header) has no abstract: "" (presidential documents, Sunshine Act and
    filing notices). Any other document's abstract is its first LEAD_MAX characters (a bill's title, latest action and
    the start of its summary; a White House release's opening), an executive order's enacting clause left out. Tags
    are stripped, entities unescaped, page-break markers removed and whitespace collapsed, as collection's
    `clean_field` does for a lead, so a term broken over a line or a page still matches.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): reasoning derives the abstract from `official_docs.full_text`.
    Why: official_docs stores no abstract column and the corpus SQL delivers `lead` empty for official rows; the
    Federal Register API's `abstract` field is the document's SUMMARY paragraph, so the same text is recovered from the
    raw text collection stored. The first-600-characters fallback mirrors collection's lead cap.
    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; review round 1): page-break markers are removed with the blank
    lines around them before the SUMMARY is read; a Federal Register document without a SUMMARY is matched on its title
    alone; the "By the authority vested in me ...:" clause is dropped from the fallback. Why: a SUMMARY crossing a page
    break was cut mid-sentence (official_docs 6108 lost "southern border"); the API's abstract is null for those
    documents, and their first 600 characters are the issue's cover page (titles of the other documents in the same
    Part), an order's enacting clause ("section 301 of title 3" seeded tariffs-trade-war-china) or a meeting agenda
    ("Fiscal Year 2027" seeded federal-budget-shutdown). See docs/DECISIONS.md › Sources (official documents: seed rule).
    """
    if not text:
        return ""
    cleaned = html.unescape(_TAGS.sub(" ", _CONTROL.sub("", text)))
    cleaned = _PAGE_MARK.sub(" ", _PAGE_BREAK.sub("\n", cleaned))
    m = _SUMMARY.search(cleaned)
    if m:
        return " ".join(m.group(1).split())[:ABSTRACT_MAX]
    if source_id == FEDERAL_REGISTER or _FR_HEADER_END.search(cleaned[:2000]):
        return ""
    body = _AUTHORITY.sub(" ", cleaned)
    return " ".join(_RULE.sub(" ", body).split())[:LEAD_MAX]


# ------------------------------------------------------------- the seed rule ----


def official_seed_match(doc: DocRef, terms: list[str] | None) -> str | None:
    """'title' or 'lead' (the abstract) where a term of the run's topic matches the official document; None when
    neither carries one, or when the topic's terms are unknown (None or empty: nothing can match)."""
    if not terms:
        return None
    lead = doc.get("lead") or official_abstract(doc.get("text"), doc.get("source_id"))
    return topic_match_of(doc.get("title") or "", lead, terms)


def official_seed_flags(docs: list[DocRef], terms: list[str] | None) -> tuple[list[DocRef], dict[str, int]]:
    """The documents with the seed rule applied to every official document of the edition window: `seed_match`
    ('title' | 'lead' | None) and `evidence_only` (True when nothing matched: research round 2 and the fact-checker
    may still use it, and it may join an event a seed document started, but it starts no event and is never a roundup
    item by itself; nodes/cluster.py). Earlier-day documents are left as they are (never an event anyway). Returns
    copies, never the caller's dicts, and the counts for the trace."""
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
