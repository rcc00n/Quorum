"""Free-text topic → collection terms: the words → terms step behind a topic the reader types.

The web app writes a `topics` row (id = slug, name, query_terms) that the collection block reads; this module
supplies the row. One fast-lane model call (`prompts/topic_terms.md`) proposes slug, name and terms; code
validates them against collection's matching rules (collectors/README.md › Topics: whole words,
case-insensitive, no stemming, plurals listed explicitly) and falls back to a deterministic row built from the
phrase itself when the call fails or the reply is unusable.

    python -m quorum_reasoning.topics --suggest "climate policy and carbon tax" [--json] [--sql] [--dry-run]

Typed-topic intake (docs/DECISIONS.md › Daily editions for users): the web app keeps what readers type as requests
{key, text, count} (the key is `request_key`, a contract shared with the web) and never calls a model; the operator
turns a batch into mapping.json (each request → an existing topic, a new row, needs_review or rejected), rows.sql
(the new rows, insert-only) and report.txt, reading the existing topics through Zetaris:

    python -m quorum_reasoning.topics --from-requests requests.json --out DIR [--dry-run] [--existing topics.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import llm

# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): topics are free text, so a model call turns the reader's
# phrase into slug, name and 10-15 whole-word terms, and code re-checks every term against collection's
# matching rules; on a failed call or an invalid reply a deterministic row is built from the phrase (`source:
# fallback` with its `reason`), and `suggest` never raises. Why: owner's decision (Issue #2, "topics are free
# text"); collection matches whole words with no stemming, so plurals and names must be listed; a topic must
# always be creatable, even when the model route is down.

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){1,3}$")
MAX_TERMS = 20
TERM_MIN_CHARS, TERM_MAX_CHARS = 2, 40
MIN_WORD_LETTERS = 4  # a single word shorter than this is dropped unless it is an uppercase acronym
NAME_MAX_CHARS = 80

# letters (any script), digits, spaces, hyphens, apostrophes; must start and end with a letter or digit
_TERM_CHARS = re.compile(r"^[^\W_](?:[^\W_]|[ '\-])*[^\W_]$|^[^\W_]$")
_ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?")
_DERIVE_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?(?:-[^\W_]+(?:'[^\W_]+)?)*")  # _WORD, hyphenated parts kept together

STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have he her his i if in into is it its me my no nor not of
    on or our over she so than that the their them then there these they this those to under up us was we were
    what when where which while who will with within without you your about after against all also any around
    before between both during each more most news other some such through very via""".split()
)


def _strip_format(s: str) -> str:
    """`s` without format characters (Unicode category Cf: soft hyphen, zero-width space and joiners, bidi controls,
    BOM). Pasted web text carries them invisibly; kept, they split a word in two ("Ukr\\u00adaine") or reorder a name.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): deleted, not rejected, before keying, checking and deriving.
    Why: soft hyphens and zero-width spaces are common in text copied from web pages, and the reader cannot see them."""
    return "".join(c for c in s if unicodedata.category(c) != "Cf")


def _clean(text: Any) -> str:
    s = _strip_format(str(text or "")).replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def _ascii(word: str) -> str:
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode("ascii").lower()


def normalize_term(raw: Any) -> str | None:
    """The term as collection should store it, or None when it breaks a rule.

    Lowercase except acronym words (all uppercase, 2-6 characters); 2-40 characters; letters, digits, spaces,
    hyphens and apostrophes only; not a stopword; a single word needs 4 letters unless it is an acronym; an
    acronym that is also a stopword (`US`, `IT`) is dropped, since collection matches case-insensitively.
    """
    term = _clean(raw)
    if not (TERM_MIN_CHARS <= len(term) <= TERM_MAX_CHARS) or not _TERM_CHARS.match(term):
        return None
    words = term.split(" ")
    out = [w if _ACRONYM.match(w) else w.lower() for w in words]
    if all(w.lower() in STOPWORDS for w in out):
        return None
    if len(out) == 1:
        w = out[0]
        if _ACRONYM.match(w):
            return None if w.lower() in STOPWORDS else w
        if sum(c.isalpha() for c in w) < MIN_WORD_LETTERS:
            return None
    return " ".join(out)


def clean_terms(raw: Any) -> tuple[list[str], list[str]]:
    """(kept, dropped): normalised, deduplicated case-insensitively, at most MAX_TERMS kept."""
    items = raw if isinstance(raw, list) else []
    kept: list[str] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for item in items:
        term = normalize_term(item) if isinstance(item, str) else None
        if term is None:
            dropped.append(str(item)[:60])
            continue
        if term.lower() in seen:
            continue
        if len(kept) >= MAX_TERMS:
            dropped.append(term)
            continue
        seen.add(term.lower())
        kept.append(term)
    return kept, dropped


def plural(word: str) -> str | None:
    """Naive English plural of the last word: +es after ss/x/z/ch/sh, y → ies after a consonant, else +s.
    None for an acronym, or when the last word already ends in a single s (taken as plural: "tariffs")."""
    head, _, last = word.rpartition(" ")
    low = last.lower()
    if _ACRONYM.match(last) or (low.endswith("s") and not low.endswith("ss")):
        return None
    if re.search(r"(ss|x|z|ch|sh)$", low):
        last += "es"
    elif re.search(r"[^aeiou]y$", low):
        last = last[:-1] + "ies"
    else:
        last += "s"
    return f"{head} {last}" if head else last


def _significant(word: str) -> bool:
    return word.lower() not in STOPWORDS and (sum(c.isalpha() for c in word) >= MIN_WORD_LETTERS or bool(_ACRONYM.match(word)))


def slug_for(phrase: str) -> str:
    """2-4 ASCII words of the phrase joined by hyphens; one word gets `-news`; none gets `topic-<hash>`."""
    words = [_ascii(w) for w in _WORD.findall(_clean(phrase)) if w.lower() not in STOPWORDS]
    words = [re.sub(r"[^a-z0-9]", "", w) for w in words]
    words = [w for w in words if w][:4]
    if len(words) == 1:
        words.append("news")
    if not words:
        return "topic-" + hashlib.sha256(_clean(phrase).encode("utf-8")).hexdigest()[:8]
    return "-".join(words)


def derive(phrase: str) -> dict[str, Any]:
    """The deterministic row for a phrase (the fallback, and the dry-run stand-in's answer).

    Terms: the phrase's runs of words between stopwords when they are 2-3 words long ("carbon tax"), their
    plurals, then its significant single words and their plurals; each one passes `normalize_term`. The phrase is
    taken in NFKC form, and a hyphenated word stays whole ("K-pop"), its significant parts added as single words.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): NFKC
    first, and hyphenated words kept whole. Why: collection matches lowercase whole words with no normalisation, so a
    full-width term never matches an ASCII headline, and "K-pop" split into "k pop" never matches "K-pop".
    """
    text = _clean(unicodedata.normalize("NFKC", _clean(phrase)))
    words = [re.sub(r"'s$", "", w, flags=re.IGNORECASE) for w in _DERIVE_WORD.findall(text)]  # "Biden's" -> "Biden"
    runs: list[list[str]] = [[]]
    for w in words:
        if w.lower() in STOPWORDS:
            runs.append([])
        else:
            runs[-1].append(w)
    candidates: list[str] = []
    for run in runs:
        if 2 <= len(run) <= 3:
            candidates += [" ".join(run), plural(" ".join(run))]
    for w in words:
        for part in [w, *w.split("-")] if "-" in w else [w]:
            if _significant(part):
                candidates += [part, plural(part)]
    terms, _ = clean_terms([c for c in candidates if c])
    if not terms and TERM_MIN_CHARS <= len(text) <= TERM_MAX_CHARS and _TERM_CHARS.match(text):
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a phrase with no significant word is kept whole, as
        # `normalize_term` gives it when that is a valid term ("Me Too" -> "me too"), else lowercased ("tax"). Why: the
        # old condition kept it only when it was NOT a valid term, so "Me Too" got no term at all; the intake still
        # refuses a whole phrase that breaks the term rules ("us", "may": `_resolve_one`, too generic).
        terms = [normalize_term(text) or text.lower()]
    name = " ".join(w if _ACRONYM.match(w) or w.lower() in STOPWORDS else w[:1].upper() + w[1:] for w in text.split(" "))
    if name:
        name = name[:1].upper() + name[1:]
    return {
        "slug": slug_for(text),
        "name": name[:NAME_MAX_CHARS] or "Untitled topic",
        "terms": terms,
        "notes": "terms are the phrase's own words and naive plurals; synonyms, names and spellings it does not contain are missed",
    }


def validate(reply: Any) -> tuple[dict[str, Any] | None, str]:
    """(row, "") for a usable model reply, (None, why) otherwise."""
    if not isinstance(reply, dict):
        return None, "reply is not a JSON object"
    name = _clean(reply.get("name"))[:NAME_MAX_CHARS]
    if not name:
        return None, "empty name"
    slug = _clean(reply.get("slug")).lower()
    slug_note = ""
    if not SLUG_RE.match(slug):
        # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a bad slug never discards the model's terms; the slug is
        # rebuilt by code from the name (the same rule the fallback uses). Why: the first live use rejected three of
        # four replies for five-word slugs and fell back to naive terms ("federals", "chinas") although the terms were good.
        slug_note = f"slug rebuilt by code (model gave {slug[:60]!r})"
        slug = slug_for(name) if SLUG_RE.match(slug_for(name)) else slug_for(_clean(reply.get("slug")) or name)
        if not SLUG_RE.match(slug):
            return None, f"invalid slug {slug[:60]!r}"
    terms, dropped = clean_terms(reply.get("terms"))
    if not terms:
        return None, "no usable terms"
    notes = _clean(reply.get("notes"))[:300]
    row = {"slug": slug, "name": name, "terms": terms, "notes": (notes + ("; " if notes and slug_note else "") + slug_note)[:400]}
    if dropped:
        row["dropped"] = dropped
    return row, ""


def suggest(phrase: str, *, dry_run: bool | None = None, language_hint: str | None = None) -> dict[str, Any]:
    """Slug, name and terms for a free-text topic; never raises.

    `source` is "model" (validated reply; `dry_run` true when the dry-run stand-in answered) or "fallback" (with
    `reason`). `dry_run=None` follows the environment like run.py: QUORUM_DRY_RUN=1 or no route means dry.
    """
    text = _clean(phrase)
    try:
        dry = llm.is_dry_run(bool(dry_run))
    except Exception:
        dry = True
    try:
        payload: dict[str, Any] = {"phrase": text}
        if language_hint:
            payload["language_hint"] = _clean(language_hint)[:40]
        reply = llm.json_task("topic_terms", payload, dry_run=dry)
        row, why = validate(reply)
    except (Exception, llm.RateLimitAbort) as exc:  # a failed call, a reply without JSON, a drained route (RateLimitAbort is a BaseException): the topic is still creatable
        row, why = None, f"model call failed: {type(exc).__name__}: {str(exc)[:120]}"
    if row is not None:
        return {**row, "source": "model", "dry_run": dry}
    try:
        out = derive(text)
    except Exception as exc:  # pragma: no cover - derive is pure; this is the last line of "never raises"
        out = {"slug": "topic-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], "name": text[:NAME_MAX_CHARS], "terms": [], "notes": ""}
        why += f"; fallback failed: {type(exc).__name__}"
    return {**out, "source": "fallback", "reason": why, "dry_run": dry}


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def to_sql(row: dict[str, Any]) -> str:
    """The insert for collection's `topics` table (collectors/schema.sql: id, name, query_terms TEXT[]; created_at and
    active take their defaults). It never changes an existing row: `ON CONFLICT (id) DO NOTHING RETURNING id` returns
    the id when the row was inserted and no row when the id was already there, so the caller can tell the two apart.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): insert-only, never an upsert. Why: "Russia Ukraine war" slugs
    to the seed's id `russia-ukraine-war`, and the old `DO UPDATE` would have replaced the seed's name and terms with
    a reader's words; changing an existing topic's terms is a deliberate UPDATE by its owner (collectors/common.py
    `ensure_topic` made the same choice for the seed).
    """
    terms = ", ".join(_sql_str(t) for t in row.get("terms") or [])
    array = f"ARRAY[{terms}]" if terms else "ARRAY[]::text[]"
    return (
        f"INSERT INTO topics (id, name, query_terms) VALUES ({_sql_str(row['slug'])}, {_sql_str(row['name'])}, {array}) "
        "ON CONFLICT (id) DO NOTHING RETURNING id;"
    )


def _readable(row: dict[str, Any]) -> str:
    lines = [
        f"slug:   {row['slug']}",
        f"name:   {row['name']}",
        f"source: {row['source']}" + (" (dry-run stand-in)" if row.get("dry_run") and row["source"] == "model" else ""),
    ]
    if row.get("reason"):
        lines.append(f"reason: {row['reason']}")
    lines.append(f"terms:  {len(row['terms'])}")
    lines += [f"  - {t}" for t in row["terms"]]
    if row.get("dropped"):
        lines.append("dropped: " + ", ".join(row["dropped"]))
    if row.get("notes"):
        lines.append(f"notes:  {row['notes']}")
    return "\n".join(lines)


# ------------------------------------------------------------------ intake ----
#
# The rules below are the project's (docs/DECISIONS.md › Daily editions for users: the request key, insert-only rows,
# the overlap rule, input validation); module notes in reasoning/README.md › Decisions.

REQUEST_MAX_CHARS = 80
KEY_STOPWORDS = frozenset("a about an and at by for from in into of on or over s the to vs with news".split())
INTAKE_STATUSES = ("existing", "new", "needs_review", "rejected")
# mapping.json: one object per request entry, every field present (null when it does not apply), in this order.
# match: name | slug | headline for existing, and for a needs_review that names an existing topic (a retired one, or
# one that covers the words while collection gives the headline to an older topic); source: derive | model |
# dry-run stand-in | fallback for a proposed row; order: 1-based insert order of a new row in rows.sql; key_mismatch:
# the contract's key when the web app sent a different one; caution: for a proposed row whose terms derive built from
# the phrase (dry run, dry-run stand-in, fallback), why to review it before applying (`_caution`).
MAPPING_FIELDS = ("index", "key", "text", "count", "status", "topic_id", "name", "terms", "conflicts", "reason",
                  "match", "source", "order", "key_mismatch", "caution")
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a live batch (no --dry-run, and a model route configured) makes
# at most this many model calls; the requests beyond it are needs_review with a "deferred" reason and are proposed
# again on the next batch. Why: one fast-lane call per new topic, and the per-account budget rules (README › Run it)
# need a bound a web form cannot set. A batch whose environment is dry makes no call and has no cap.
MAX_MODEL_CALLS = 25
WITHHELD = "[withheld]"
_COLLECTION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")  # collectors/schema.sql topics.id CHECK; tools/corpus.py --topic
ID_BASE_MAX = 60  # a new id's base, so that a "-999" suffix still fits collection's 64 characters


# The combining-diacritics blocks: Combining Diacritical Marks, … Extended, … Supplement, … for Symbols, Combining Half
# Marks. Only these are folded by the key; the vowel signs of Indic and Thai scripts (also category M) are kept.
_DIACRITICS = ((0x0300, 0x036F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF), (0x20D0, 0x20FF), (0xFE20, 0xFE2F))


def _diacritic(c: str) -> bool:
    return any(lo <= ord(c) <= hi for lo, hi in _DIACRITICS)


def request_key(text: Any) -> str:
    r"""The normalised request key: the contract shared with the web app (docs/DECISIONS.md › Daily editions for users).

    0. delete every format character (general category Cf: soft hyphen, zero-width space, bidi controls, BOM);
    1. lowercase, Unicode NFKD, delete the combining diacritics (U+0300-036F, U+1AB0-1AFF, U+1DC0-1DFF, U+20D0-20FF,
       U+FE20-FE2F), lowercase again;
    2. delete a full stop that stands between two letters ("U.S." -> "us", "e.g." -> "eg");
    3. tokens = maximal runs of letters, marks and digits (categories L, M and N); everything else separates tokens;
    4. drop KEY_STOPWORDS; 5. the unique tokens, sorted by code point, joined by single spaces.

    "war in Ukraine" and "Ukraine war" give "ukraine war"; "U.S. tariffs on China!" gives "china tariffs us"; "चीन"
    (China) and "चना" (chickpea) keep their vowel signs and stay apart. The same in the web app (JavaScript):

        const STOP = new Set("a about an and at by for from in into of on or over s the to vs with news".split(" "));
        const requestKey = t => [...new Set((String(t ?? "").replace(/\p{Cf}/gu, "").toLowerCase().normalize("NFKD")
          .replace(/[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]/gu, "").toLowerCase()
          .replace(/(?<=\p{L})\.(?=\p{L})/gu, "").match(/[\p{L}\p{M}\p{N}]+/gu) || [])
          .filter(w => !STOP.has(w)))].sort().join(" ");

    (`sort()` compares UTF-16 units, which equals code-point order unless the text has astral-plane letters. The
    docstring is a raw string so that the source shows the JavaScript exactly as it must be copied.)

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): only the
    combining diacritics are folded, not every combining mark, and marks count as word characters. Why: deleting all
    of category M removed the vowel signs of Devanagari and Thai, so "चीन" (China) and "चना" (chickpea) shared a key
    and were resolved as one request; Latin, Greek and Cyrillic accents are all in the folded blocks.
    """
    s = unicodedata.normalize("NFKD", _strip_format(str(text if text is not None else "")).lower())
    s = "".join(c for c in s if not _diacritic(c)).lower()
    s = "".join(c for i, c in enumerate(s) if not (c == "." and 0 < i < len(s) - 1 and s[i - 1].isalpha() and s[i + 1].isalpha()))
    tokens: set[str] = set()
    cur: list[str] = []
    for c in s + " ":
        if unicodedata.category(c)[0] in "LMN":
            cur.append(c)
        elif cur:
            tokens.add("".join(cur))
            cur = []
    return " ".join(sorted(t for t in tokens if t not in KEY_STOPWORDS))


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): any "@" is rejected and withheld (an e-mail address is any
# word@word, a dotted domain not required; every other "@" counts as a handle), and a dotted name followed by "/" or
# ending in a common TLD is a URL. Why: "john@localhost" and "janedoe.blog" passed the narrower patterns and became
# public topic names; a typed topic never needs an "@".
_EMAIL_RE = re.compile(r"[\w.%+-]+@[\w-]+")
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): host labels
# are letters and digits of any script, a TLD of 2+ letters in any script counts when a "/" follows it, and the
# ideographic full stops count as dots (`_scan_form`). Why: "jаnedoe.com/profile" (a Cyrillic "а"), "münchen.de/news",
# "пример.рф/ivan-petrov" and "example。com/jane" passed the ASCII-only patterns and became public topic names.
_HOST = r"(?:[^\W_]|-)+(?:\.(?:[^\W_]|-)+)*"
_URL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.|\b" + _HOST + r"\."
    r"(?:com|org|net|gov|edu|mil|int|io|co|ai|app|dev|info|biz|news|ly|me|tv|us|uk|ru|ua|de|fr|eu|ca|au|cn|jp|in|xyz"
    r"|blog|shop|store|online|site|website|live|top|club|tech|space|cloud|page|link|wiki|media|email|pro|art|life"
    r"|world|today)\b"
    r"|\b" + _HOST + r"\.[^\W\d_](?:[^\W_]|-)+/"  # any dotted name followed by a path: "janedoe.foo/post", "пример.рф/x"
)
_DOTS = {0x3002: ".", 0xFF0E: ".", 0xFF61: "."}  # ideographic, full-width and half-width ideographic full stops
_PHONE_RE = re.compile(
    r"\+\d[\d\s().-]{6,}\d"  # international: +44 20 7946 0958
    r"|(?<!\d)\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"  # North American: (555) 123-4567, 555.123.4567, 5551234567
    r"|(?<![\d.-])\d{3}[.-]\d{4}(?![\d.-])"  # local: 555-1234 (not "2026-2027", not "100 2026")
)
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): before the
# phone patterns run, every dash-like character (category Pd, and U+2212 minus), "/" and "_" become "-", and a run of
# digits and separators (space . - ( )) that holds 9 or more digits in 2 or more groups (this group condition superseded
# 2026-10-26, closing round 2: below) is also a phone number. Why:
# "555‑123‑4567" (a non-breaking hyphen), "555−123−4567", "555/123/4567" and "0170 1234567" passed the ASCII-only,
# North-American-shaped patterns; "2024-2025" (8 digits) and "Boeing 737-800" stay acceptable.
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 2, to confirm by Yelysei): a run of
# digits and separators that holds 9 or more digits is a phone number whatever its number of groups. Why:
# "call 07911123456", "Jane 447911123456" and "Ivan 123456789", phone numbers typed without separators, became public
# topic names; a typed topic hardly ever holds 9 digits in a row ("$1000000000" was already rejected as North American).
_PHONE_RUN = re.compile(r"\d[\d\s().-]*\d")
PHONE_MIN_DIGITS = 9


def _phone_form(scan: str) -> str:
    return "".join("-" if unicodedata.category(c) == "Pd" or c in "\u2212/_" else c for c in scan)


def _has_phone(scan: str) -> bool:
    form = _phone_form(scan)
    if _PHONE_RE.search(form):
        return True
    return any(len(re.findall(r"\d", run)) >= PHONE_MIN_DIGITS for run in _PHONE_RUN.findall(form))


def _scan_form(cleaned: str) -> str:
    """The form the personal-data patterns scan: NFKC (a full-width "＠" is "@"), the ideographic full stops as dots."""
    return unicodedata.normalize("NFKC", cleaned).translate(_DOTS)


def _personal_data(scan: str) -> str:
    """Why `scan` (a `_scan_form`) may carry personal data: an e-mail address, a URL, an "@" (a handle), a phone
    number; "" when none of them is there."""
    for pattern, why in ((_EMAIL_RE, "contains an e-mail address"), (_URL_RE, "contains a URL")):
        if pattern.search(scan):
            return why
    if "@" in scan:
        return "contains an @handle"
    if _has_phone(scan):
        return "contains a phone number"
    return ""


_MARKUP_RE = re.compile(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")  # markup, C0 controls but tab/newline/return, DEL, C1
_UNUSABLE = frozenset(("Co", "Cs", "Cn"))  # private use, unpaired surrogate, unassigned


def _echo(text: str) -> str:
    """Text safe to write into mapping.json and report.txt: controls, private-use, unpaired surrogates (which UTF-8
    cannot encode) and unassigned code points become U+FFFD."""
    return "".join("\ufffd" if unicodedata.category(c) in _UNUSABLE or unicodedata.category(c) == "Cc" else c for c in text)


def check_request(text: Any) -> tuple[str, bool]:
    """("", False) for an acceptable typed topic, else (why, withheld): the checks the web app must run before it
    stores a request, and that the batch repeats. `withheld` is true when the text may carry personal data (an
    e-mail address, a URL, an "@", a phone number), so outputs must not echo it.

    Format characters (Cf) are deleted first (`_strip_format`), and the personal-data patterns scan the NFKC form with
    the ideographic full stops as dots (`_scan_form`), so a zero-width space, a full-width "＠" or "example。com" hides
    nothing; host labels may be in any script, and dash-like characters, "/" and "_" separate phone digits (`_has_phone`).
    Order: not text, over 25 × REQUEST_MAX_CHARS raw (not scanned, withheld), empty, e-mail, URL, any other "@" (a
    handle), phone (all four `_personal_data`, so that a text of digits alone is withheld before "no letters"), markup
    (`<`, `>`, also in the NFKC form: full-width "＜") or control characters (C0 but tab, newline and return; DEL; C1),
    private-use, unpaired-surrogate or unassigned code points (Co, Cs, Cn), over REQUEST_MAX_CHARS code points after
    collapsing whitespace (JS: `[...text].length`), no letter at all, nothing left after `request_key`.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): markup is
    also looked for in the NFKC form. Why: the intake now matches and derives from the NFKC form of the text
    (`resolve_requests`), and "＜script＞" would otherwise become a topic named "<Script>".
    """
    if not isinstance(text, str):
        return "not text", False
    if len(text) > 25 * REQUEST_MAX_CHARS:  # not scanned at all; withheld because nobody looked at what it holds
        return f"longer than {REQUEST_MAX_CHARS} characters ({len(_clean(text))})", True
    cleaned = _clean(text)
    if not cleaned:
        return "empty", False
    scan = _scan_form(cleaned)
    personal = _personal_data(scan)
    if personal:
        return personal, True
    if _MARKUP_RE.search(text) or _MARKUP_RE.search(scan):
        return "contains markup or control characters", False
    if any(unicodedata.category(c) in _UNUSABLE for c in cleaned):
        return "contains private-use, unpaired surrogate or unassigned characters", False
    if len(cleaned) > REQUEST_MAX_CHARS:
        return f"longer than {REQUEST_MAX_CHARS} characters ({len(cleaned)})", False
    if not any(c.isalpha() for c in cleaned):
        return "no letters", False
    if not request_key(cleaned):
        return "nothing left after normalising (only stopwords and punctuation)", False
    return "", False


# ----------------------------------------------------------- existing topics ----


def _pg_array(body: str) -> list[str]:
    """Elements of a one-dimensional Postgres array literal without its braces: `a,"b c","d\\"e",NULL`."""
    out: list[str] = []
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        if body[i] == '"':
            i += 1
            buf: list[str] = []
            while i < n and body[i] != '"':
                if body[i] == "\\" and i + 1 < n:
                    i += 1
                buf.append(body[i])
                i += 1
            item, quoted = "".join(buf), True
            j = body.find(",", i)
            i = n if j < 0 else j
        else:
            j = body.find(",", i)
            j = n if j < 0 else j
            item, quoted = body[i:j], False
            i = j
        i += 1
        item = item.strip()
        if item and (quoted or item.upper() != "NULL"):
            out.append(item)
    return out


def parse_terms(value: Any) -> list[str]:
    """`query_terms` as a list of strings, whatever shape it arrives in: a list (psycopg, a JSON file), a Postgres
    array literal (`{Ukraine,"trade war"}`), the same wrapped in SQL quotes (`'{…}'`, as Zetaris returns TEXT[] as a
    string, with `''` for an apostrophe), or a JSON list in a string. Anything else is split on commas."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    s = str(value).strip()
    if len(s) >= 2 and s[0] == s[-1] == "'":
        s = s[1:-1].replace("''", "'").strip()
    if s.startswith("["):
        try:
            loaded = json.loads(s)
        except ValueError:
            loaded = None
        if isinstance(loaded, list):
            return parse_terms(loaded)
    if s.startswith("{") and s.endswith("}"):
        return _pg_array(s[1:-1])
    return [t.strip().strip('"').strip() for t in s.split(",") if t.strip().strip('"').strip()]


def _parse_active(value: Any) -> bool:
    if value is None:
        return True  # column not exposed, or NULL: collection's default is true
    if isinstance(value, str):
        return value.strip().lower() not in ("f", "false", "0", "no", "n", "off")
    return bool(value)


def normalise_topic(row: dict[str, Any]) -> dict[str, Any] | None:
    """One existing topic as {id, name, terms, active, created_at}; None for a row without an id."""
    low = {str(k).lower(): v for k, v in (row or {}).items()} if isinstance(row, dict) else {}
    topic_id = _clean(low.get("id"))
    if not topic_id:
        return None
    created = low.get("created_at")
    name = re.sub(r"\s+", " ", str(low.get("name") or "")).strip()  # as stored: no dash or quote rewriting
    return {
        "id": topic_id,
        "name": name or topic_id,
        "terms": parse_terms(low.get("query_terms", low.get("terms"))),
        "active": _parse_active(low.get("active")),
        "created_at": None if created is None else str(created),
    }


ORDER_KNOWN = "collection order: created_at, id"  # the note of `order_topics` when the order is collection's own


def order_topics(topics: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Collection order (created_at, then id) when every row has a readable created_at; the given order otherwise."""
    stamps = []
    for t in topics:
        try:
            stamps.append(datetime.fromisoformat(str(t.get("created_at"))))
        except (TypeError, ValueError):
            return topics, "collection order: created_at not available, rows taken in the order returned"
    try:
        ordered = [t for _, _, t in sorted(zip(stamps, [t["id"] for t in topics], topics), key=lambda x: (x[0], x[1]))]
    except TypeError:  # naive and aware timestamps mixed
        return topics, "collection order: created_at not comparable, rows taken in the order returned"
    return ordered, ORDER_KNOWN


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): existing topics are read with the widest column list Zetaris
# accepts: (id, name, query_terms, active, created_at), then without created_at, then without active (every topic then
# taken as active; report.txt says which). Why: on the rehearsal registration the five-column SELECT returned HTTP 400
# while the documented three-column one worked; registering or refreshing Zetaris tables is not this command's job.
_TOPIC_COLUMNS = ("id, name, query_terms, active, created_at", "id, name, query_terms, active", "id, name, query_terms")
TOPIC_READ_LIMIT = 1000


def read_topics(run_sql: Callable[[str, int], list[dict[str, Any]]] | None = None) -> tuple[list[dict[str, Any]], str]:
    """(topics in collection order, note): the existing rows of collection's `topics` table through Zetaris
    (`<ZETARIS_COLLECTION_DB>.topics`, read-only SQL). Raises RuntimeError when no query gives a topic with an id.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): a query that
    succeeds but yields no row with an id counts as failed (the next, narrower query is tried, then RuntimeError: exit 2,
    nothing written), and rows dropped for a missing id are counted in the note. Why: collection always holds its seed
    topic (`ensure_topic` runs on every pass), so zero topics means a misread (an empty or stale registration, a wrong
    ZETARIS_COLLECTION_DB, unnamed `col0..colN` columns), and resolving against it turned rewordings of seeded topics
    into new rows: the two-corpora problem the intake exists to prevent. An explicit `--existing` file may be empty."""
    from .tools import corpus

    runner = run_sql or corpus._run_sql
    table = f"{corpus._zetaris_db()}.topics"
    errors: list[str] = []
    for cols in _TOPIC_COLUMNS:
        try:
            rows = runner(f"SELECT {cols} FROM {table}", TOPIC_READ_LIMIT)
        except Exception as exc:  # an HTTP 400 for a column Zetaris does not expose, a missing route, …
            errors.append(f"[{cols}] {type(exc).__name__}: {str(exc)[:120]}")
            continue
        rows = list(rows or [])
        topics = [t for t in (normalise_topic(r) for r in rows) if t is not None]
        if not topics:
            errors.append(f"[{cols}] {len(rows)} rows, none with an id (an empty or stale registration, a wrong "
                          "ZETARIS_COLLECTION_DB, or unnamed columns); collection always holds its seed topic")
            continue
        topics, order_note = order_topics(topics)
        notes = [f"Zetaris {table} ({cols})", order_note]
        if len(topics) < len(rows):
            notes.append(f"WARNING: {len(rows) - len(topics)} of {len(rows)} rows dropped, no id")
        if "active" not in cols:
            notes.append("`active` not exposed: every topic taken as active")
        if len(rows) >= TOPIC_READ_LIMIT:
            notes.append(f"WARNING: {TOPIC_READ_LIMIT} rows returned, the table may hold more")
        if errors:
            notes.append("wider queries failed: " + "; ".join(errors))
        return topics, "; ".join(notes)
    raise RuntimeError(f"cannot read existing topics through Zetaris {table}: " + "; ".join(errors))


# ------------------------------------------------------------------ matching ----


def _occurs(term: str, text: str) -> bool:
    """collectors/common.py `matches_topic` for one term: a case-insensitive whole-word match in the text."""
    t = (term or "").lower()
    return bool(t.strip()) and re.search(r"\b" + re.escape(t) + r"\b", (text or "").lower()) is not None


def term_relation(term: str, other: str) -> str | None:
    """"equal", "contains" (term holds `other` as whole words), "contained_in", or None when they do not overlap."""
    if term.lower() == other.lower():
        return "equal"
    if _occurs(other, term):
        return "contains"
    if _occurs(term, other):
        return "contained_in"
    return None


def _view(topic: dict[str, Any], *, batch: bool = False) -> dict[str, Any]:
    return {**topic, "name_key": request_key(topic["name"]), "slug_key": request_key(topic["id"]), "batch": batch}


def _id_base(slug: str) -> str:
    """The proposed slug as the base of a new id that holds collection's rule `^[a-z0-9][a-z0-9-]{0,63}$`.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a base over ID_BASE_MAX (60) characters is cut at its last hyphen
    within the limit; when no hyphen is there (one long word), or what is left breaks the rule, the base is
    `topic-<8 hex of the slug>`. Why: collection's CHECK rejects a longer id, while the mapping would report it `new`;
    60 leaves room for the "-999" suffix of a taken id."""
    base = slug if _COLLECTION_ID.match(slug or "") else slug_for(slug or "")
    if len(base) > ID_BASE_MAX:
        head = base[: ID_BASE_MAX + 1]
        base = head.rsplit("-", 1)[0] if "-" in head else ""
    base = base.rstrip("-")
    if not _COLLECTION_ID.match(base):
        base = "topic-" + hashlib.sha256((slug or "").encode("utf-8")).hexdigest()[:8]
    return base


def _free_slug(slug: str, taken: set[str]) -> str:
    """The slug, or slug-2, slug-3, … when an existing or earlier row holds it (ids are never reused or overwritten).

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a taken id gets a numeric suffix rather than failing the request.
    Why: the request's words already differ from that topic's name and slug (the key check ran first), so it is a
    different topic that happens to slug alike; collection's id rule allows the extra segment."""
    base = _id_base(slug)
    if base not in taken:
        return base
    for n in range(2, 1000):
        if f"{base}-{n}" not in taken:
            return f"{base}-{n}"
    return "topic-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]  # pragma: no cover - 998 namesakes


def _existing(t: dict[str, Any], match: str, reason: str) -> dict[str, Any]:
    return {"status": "existing", "match": match, "topic_id": t["id"], "name": t["name"], "terms": list(t["terms"]),
            "conflicts": [], "reason": reason + (" (a new row of this batch)" if t.get("batch") else "")}


def _tid(t: dict[str, Any]) -> str:
    return t["id"] + (" (a new row of this batch)" if t.get("batch") else "")


def _matching(text: str, known: list[dict[str, Any]]) -> list[tuple[dict[str, Any], list[str]]]:
    """What collection does with a headline made of `text`: the active known topics whose terms occur in it, each with
    those terms, in collection order; collectors/common.py `first_topic_match` gives the document to the first one."""
    out = []
    for t in known:
        hits = [term for term in t["terms"] if _occurs(term, text)] if t["active"] else []
        if hits:
            out.append((t, hits))
    return out


def _covers(t: dict[str, Any], hits: list[str], words: set[str]) -> bool:
    """Every word of the request key is in the topic's name, its slug or the terms that matched."""
    return words <= set(t["name_key"].split()) | set(t["slug_key"].split()) | {w for h in hits for w in request_key(h).split()}


def _order_caveat(matching: list[tuple[dict[str, Any], list[str]]], order_known: bool) -> str:
    """The caveat for a reason that names collection's first match when the order of the existing topics is not known
    and two of them match: which one is older, and so keeps the headline, is then a guess."""
    ids = [t["id"] for t, _ in matching if not t.get("batch")]
    if order_known or len(ids) < 2:
        return ""
    return (f"; collection order unknown (created_at not readable, topics taken in the order returned), so which of "
            f"{', '.join(ids)} keeps such a headline is not certain")


DERIVED_SOURCES = ("derive", "dry-run stand-in", "fallback")  # terms that are the phrase's own words (`derive`)
REVIEW_BEFORE_APPLYING = "DO NOT APPLY WITHOUT REVIEW"


def _caution(source: Any, kept: list[str], text: str) -> str | None:
    """mapping.json `caution` of a proposed row whose terms come from derive (dry run, dry-run stand-in, fallback): it
    says so, and names the single-word terms that a phrase of two or more words gave; None for a model's row, and for
    a row that kept no term (nothing to review: it is needs_review anyway).

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): such a row
    keeps its status and terms, but is marked here, in report.txt and in rows.sql (a REVIEW_BEFORE_APPLYING header and
    a note on the row). Why: a single word of a longer phrase collects every headline that says it ("texas" of
    "measles outbreak Texas": 19 rehearsal titles and leads, none about measles; "TODAY" of "THE NEWS TODAY"), and
    derive's term list is Yelysei's decision of 2026-10-25, so dropping or gating those words is his call."""
    if source not in DERIVED_SOURCES or not kept:
        return None
    note = f"terms derived from the phrase's own words ({source}), not chosen by a model: review them before applying"
    singles = [k for k in kept if " " not in k] if len(_DERIVE_WORD.findall(text)) > 1 else []
    if singles:
        note += ("; single words of a longer phrase collect every headline that says them: "
                 + ", ".join(repr(s) for s in singles))
    return note


def _other_numbers(word: str) -> list[str]:
    """The word in its other grammatical number, naively: `plural`, and the word with a final "s", "es" or "ies"→"y"
    removed. Only for a word that ends in an ASCII letter and is neither a stopword nor an acronym."""
    low = word.lower()
    if low in STOPWORDS or _ACRONYM.match(word) or not re.search(r"[a-z]$", low):
        return []
    forms = [plural(word) or ""]
    if re.search(r"[^aeiou]ies$", low):
        forms.append(word[:-3] + "y")
    if low.endswith("es"):
        forms.append(word[:-2])
    if low.endswith("s") and not low.endswith("ss"):
        forms.append(word[:-1])
    return [f for f in dict.fromkeys(forms) if f and f.lower() != low and any(c.isalpha() for c in f)]


def _number_variant_match(texts: list[str], known: list[dict[str, Any]], order_known: bool):
    """The first headline made of a typed text with one word in its other number that collection gives to a known
    topic: (variant, word, form, first match, its terms, caveat), or None.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): matching rule
    (3) also checks the typed text with each word, one at a time, in its other number (`_other_numbers`); a match makes
    the row needs_review naming that topic. Why: collection matches whole words with no stemming, so "ICE raid" next to
    immigration-southern-border's "ICE raids", "Government shutdowns" next to "government shutdown" and "Semiconductor"
    next to "semiconductors" became new rows, and the subject's documents would split between two topics."""
    for text in texts:
        for m in _DERIVE_WORD.finditer(text):
            for form in _other_numbers(m.group(0)):
                variant = text[: m.start()] + form + text[m.end():]
                matching = _matching(variant, known)
                if matching:
                    winner, hits = matching[0]
                    return variant, m.group(0), form, winner, hits, _order_caveat(matching, order_known)
    return None


def _resolve_one(key: str, texts: list[str], known: list[dict[str, Any]], taken: set[str],
                 propose: Callable[[str], dict[str, Any]] | None, *, order_known: bool = True) -> dict[str, Any]:
    """One distinct request against the topics known so far (collection order, this batch's new rows last). `texts`
    are the request's distinct typed texts in NFKC form, most-requested first; each one is checked as a headline, and
    a new row is proposed from the first."""
    # 1. The same words as a topic's name or slug: that topic (Issue #2 6405180457: match typed text against names first).
    for t in known:
        if key in (t["name_key"], t["slug_key"]):
            how = "name" if key == t["name_key"] else "slug"
            if t["active"]:
                return _existing(t, how, f"same words as the {how} of {t['id']}")
            return {**_existing(t, how, ""), "status": "needs_review",
                    "reason": f"same words as the {how} of retired topic {t['id']} (active = false); reactivating it is the operator's call"}
    # 2. Collection gives a headline saying what the reader typed to the first active topic whose terms match it; when
    #    every word of the request is in that topic's name, slug or matching terms: that topic. When only a later
    #    matching topic covers the words, the operator chooses between the two (needs_review).
    #    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review rounds 1 and 2, to confirm by Yelysei):
    #    rule 2 as a whole, the headline match with its coverage condition, checked against collection's own first
    #    match (supersedes the round-1 comment here, which checked any covering topic). Why: one shared term
    #    ("shutdown") sent unrelated requests to another topic's edition, and "AI chips export controls" was mapped to
    #    ai-regulation-export-controls, although collection gives that headline to the older tariffs-trade-war-china.
    words = set(key.split())
    first: tuple[str, dict[str, Any], list[str], str] | None = None  # (text, first match, its terms, caveat)
    later: tuple[str, dict[str, Any], list[str], dict[str, Any], list[str], str] | None = None
    for text in texts:
        matching = _matching(text, known)
        if not matching:
            continue
        (winner, hits), caveat = matching[0], _order_caveat(matching, order_known)
        if _covers(winner, hits, words):
            return _existing(winner, "headline", f"collection gives a headline saying {text!r} to {winner['id']} (term "
                             f"{hits[0]!r}), the first active topic whose terms match it, and every word of the request "
                             "is in its name, slug or matching terms" + caveat)
        first = first or (text, winner, hits, caveat)
        cover = next(((t, h) for t, h in matching[1:] if _covers(t, h, words)), None)
        if later is None and cover is not None:
            later = (text, winner, hits, cover[0], cover[1], caveat)
    if later is not None:
        text, winner, hits, cover, cover_hits, caveat = later
        return {**_existing(cover, "headline", ""), "status": "needs_review",
                "reason": f"every word of the request is in the name, slug or matching terms of {_tid(cover)} (term "
                          f"{cover_hits[0]!r}), but collection gives a headline saying {text!r} to {_tid(winner)} (term "
                          f"{hits[0]!r}), the first active topic whose terms match it; map the request to one of them" + caveat}
    # 3. A new row: the proposed terms that hold the term rules, minus every term that overlaps an active topic's term.
    #    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 1, to confirm by Yelysei): one
    #    shared term alone does not make a request `existing` ("nuclear plant shutdown in Germany" shares only
    #    "shutdown" with federal-budget-shutdown); since review round 2 such a request is needs_review, not new (below).
    if propose is None:
        return {"status": "needs_review", "match": None, "topic_id": None, "name": None, "terms": [], "conflicts": [],
                "reason": f"deferred: this batch reached its cap of {MAX_MODEL_CALLS} model calls; run the batch again"}
    row = propose(texts[0])
    # (c) of the closing-round-3 DECISION at the name check below: a proposed term that may carry personal data is
    # withheld before the term rules (whose "too generic" list is echoed) and the overlap step.
    proposed: list[str] = []
    withheld_terms = 0
    for term in row.get("terms") or []:
        if not (isinstance(term, str) and term.strip()):
            continue
        if _personal_data(_scan_form(_clean(term))):
            withheld_terms += 1
        else:
            proposed.append(term)
    usable: list[str] = []
    generic: list[str] = []
    for term in proposed:
        norm = normalize_term(term)  # derive's whole-phrase fallback ("us", "may") skips it; a model reply does not
        if norm is None:
            generic.append(term)
        elif norm.lower() not in {u.lower() for u in usable}:
            usable.append(norm)
    kept: list[str] = []
    conflicts: list[dict[str, str]] = []
    for term in usable:
        flags = [{"term": term, "topic_id": t["id"], "topic_term": other, "relation": rel}
                 for t in known if t["active"] for other in t["terms"] if (rel := term_relation(term, other))]
        if flags:
            conflicts += flags
        else:
            kept.append(term)
    generic_list = ", ".join(repr(g) for g in generic)
    tail = ""
    if row.get("source") == "fallback" and row.get("reason"):
        tail += f"; terms from the fallback ({row['reason']})"
    name = str(row.get("name") or texts[0])[:NAME_MAX_CHARS]
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 2, to confirm by Yelysei; superseded
    # 2026-10-26 in closing round 3 by the comment below, which widens it to the id and the terms): the proposed
    # name passes `check_request` like the typed text, else derive's name of the typed text replaces it (the reason says
    # so, without the name). Why: `validate` only trims a model's name, so a reply named "<img src=x onerror=…> call
    # jane@x.org" went into mapping.json, report.txt and rows.sql, and from there into collection's public topic name.
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 3, to confirm by Yelysei): what a
    # proposed row (a model's reply on the live path, derive's otherwise) puts into a public output passes the
    # personal-data checks of the typed text. (a) The name passes `check_request`, else derive's name of the typed text
    # replaces it. (b) The id: the proposed slug is scanned with `_personal_data` as it is (a hyphen counts as a phone
    # separator, so "call-jane-555-1234567" is a phone number; reading the hyphens as spaces finds nothing more); when
    # it is flagged, or (a) replaced the name, derive's slug of the typed text is the id, and `topic-<8 hex>` when that
    # is flagged too. (c) A proposed term that `_personal_data` flags is withheld (above). The reason says what was
    # replaced and how many terms were withheld, never their text. Why: `validate` rebuilds an invalid model slug from
    # the model's own name (the common case: 3 of 4 first live replies), and a valid one was never checked, so a name
    # replaced for an e-mail address or a phone number still gave the public id ("jane-doe-example-org",
    # "call-jane-5551234567"), and a term "call jane 5551234567" went into query_terms, mapping.json and report.txt.
    name_why, _ = check_request(name)
    if name_why:
        name = derive(texts[0])["name"]
        tail += f"; model name replaced: {name_why}"
    base = str(row.get("slug") or "")
    slug_why = _personal_data(_scan_form(base))
    if name_why or slug_why:
        base = derive(texts[0])["slug"]
        if _personal_data(_scan_form(base)):
            base = "topic-" + hashlib.sha256(texts[0].encode("utf-8")).hexdigest()[:8]
        tail += (f"; {'model' if row.get('source') == 'model' else 'derived'} slug replaced: "
                 f"{slug_why or 'it may be built from the replaced name'}")
    slug = _free_slug(base, taken)
    if withheld_terms:
        tail += f"; {withheld_terms} proposed term{'s' if withheld_terms != 1 else ''} withheld: may carry personal data"
    out = {"match": None, "topic_id": slug, "name": name, "terms": kept,
           "conflicts": conflicts, "source": row.get("source"), "caution": _caution(row.get("source"), kept, texts[0])}
    if generic and usable:
        tail = f"; too generic, dropped: {generic_list}" + tail

    def review(why: str) -> dict[str, Any]:
        return {**out, "status": "needs_review", "reason": why + tail}

    if not proposed:
        return review("no usable term could be derived from the phrase")
    if not usable:
        return review(f"terms too generic to collect: {generic_list} (a stopword, a single word under 4 letters, or "
                      "another break of the term rules)")
    if not kept:
        return review("every proposed term overlaps a term of an existing topic or of an earlier row of this batch")
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): a row is
    # needs_review, not new, (a) when collection gives a headline made of the typed text to an earlier topic, whatever
    # the proposed terms, or (b) when the overlap dropped a term that the typed text contains and no kept term occurs
    # in the typed text; the operator maps the request to that topic or accepts the row. Supersedes the round-1 rule,
    # which was (b) alone. Why: collection gives a shared document to the earlier topic, so under (a) the row never
    # receives the headlines that say the reader's own words ("Ukraine peace talks" kept "peace" and "talks" and would
    # fill with Gaza and trade talks). A dropped term that the earlier topic holds only inside a longer term ("china"
    # in "china tariffs") does not send the headline there, so with a kept term that matches ("China chess": "chess")
    # the row still collects its subject and stays new.
    lost: dict[str, dict[str, str]] = {}  # dropped term -> its first conflict, for the terms the typed text contains
    for c in conflicts:
        if c["term"] not in lost and any(_occurs(c["term"], t) for t in texts):
            lost[c["term"]] = c
    lost_desc = ", ".join(f"{c['term']!r} ({c['relation']} {c['topic_term']!r} of {c['topic_id']})" for c in lost.values())
    kept_matches = any(_occurs(term, t) for term in kept for t in texts)
    if first is not None:
        text, winner, hits, caveat = first
        return review(f"collection gives a headline saying {text!r} to {_tid(winner)} (term {hits[0]!r}), the first active "
                      "topic whose terms match it, so this row would not receive the headlines that say the request's "
                      f"own words; map the request to {winner['id']} or accept the row"
                      + (f"; dropped as overlapping, though the typed words contain them: {lost_desc}" if lost else "") + caveat)
    variant = _number_variant_match(texts, known, order_known)
    if variant is not None:
        text, word, form, winner, hits, caveat = variant
        return review(f"collection gives a headline saying {text!r} (the typed {word!r} as {form!r}) to {_tid(winner)} "
                      f"(term {hits[0]!r}), the first active topic whose terms match it; collection does not stem, so "
                      f"this row and {winner['id']} would split the documents on the request's subject; map the request "
                      f"to {winner['id']} or accept the row" + caveat)
    if lost and not kept_matches:
        ids = list(dict.fromkeys(c["topic_id"] for c in lost.values()))
        return review(f"the overlap dropped terms that the typed words contain: {lost_desc}; none of the kept terms occurs "
                      f"in a headline saying {texts[0]!r}, so this row would miss its own subject; map the request to "
                      f"{' or '.join(ids)} or accept the row")
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): a row whose
    # terms come from derive (dry run, dry-run stand-in, fallback) needs a kept term that occurs in the typed text, else
    # needs_review. Why: those terms are the phrase's own words by construction, so none matching means derive split
    # the words ("चीन" -> "च न": a vowel sign is not a word character) and the row would collect nothing on its subject;
    # a model's terms may translate or paraphrase the request, so they are exempt.
    if row.get("source") in DERIVED_SOURCES and not kept_matches:
        return review(f"the derived terms would not match the typed words: none of {', '.join(repr(k) for k in kept)} "
                      f"occurs in a headline saying {texts[0]!r}")
    known.append(_view({"id": slug, "name": out["name"], "terms": kept, "active": True, "created_at": None}, batch=True))
    taken.add(slug)
    dropped = len({c["term"] for c in conflicts})
    return {**out, "status": "new", "reason": f"no active topic collects a headline saying {texts[0]!r}; {len(kept)} terms"
            + (f", {dropped} overlapping dropped" if dropped else "") + tail}


def _key_withheld(web_key: str) -> bool:
    """True when the key the web app sent may carry personal data (`_personal_data` on it) or is longer than a typed
    topic may be; only a key that differs from the contract's key of an accepted text is scanned, since that one is
    built from text that passed `check_request`.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed in closing round 1, to confirm by Yelysei): such a key is
    written as WITHHELD in mapping.json and report.txt; `key_mismatch` still gives the contract's key. Why: the web
    app's key is not checked by anyone else, and "john.doe@example.com +1 555 123 4567" was echoed verbatim."""
    if len(web_key) > 25 * REQUEST_MAX_CHARS:  # not scanned at all, as in check_request
        return True
    cleaned = _clean(web_key)
    return len(cleaned) > REQUEST_MAX_CHARS or bool(_personal_data(_scan_form(cleaned)))


def _entry(index: int, raw: Any) -> dict[str, Any]:
    entry = raw if isinstance(raw, dict) else {}
    text = entry.get("text")
    why, withheld = check_request(text) if isinstance(raw, dict) else ("entry is not an object", False)
    try:
        count = max(1, int(entry.get("count") or 1))
    except (TypeError, ValueError):
        count = 1
    web_key = entry.get("key") if isinstance(entry.get("key"), str) else None
    key = "" if why else request_key(_clean(text))
    base: dict[str, Any] = {"index": index, "key": _echo(web_key) if web_key is not None else key,
                            "text": _echo(_clean(text)) if isinstance(text, str) else None, "count": count}
    if web_key is not None and web_key != key and _key_withheld(web_key):
        base["key"] = WITHHELD
    if withheld:
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): text and key that may carry personal data are never echoed
        # into mapping.json or report.txt. Why: those files leave the web app's database; `index` still joins the entry.
        base.update(key=WITHHELD, text=WITHHELD)
    elif why and base["text"] and len(base["text"]) > REQUEST_MAX_CHARS:
        base["text"] = base["text"][:REQUEST_MAX_CHARS] + "…"
    if not why and web_key is not None and web_key != key:
        base["key_mismatch"] = key  # the web app's key differs from the contract: a bug on one side
    return {**base, "_key": key, "_why": why}


def resolve_requests(entries: list[Any], existing: list[dict[str, Any]], *, propose: Callable[[str], dict[str, Any]],
                     max_proposals: int | None = None, order_known: bool = True) -> list[dict[str, Any]]:
    """The mapping for a batch of typed requests, one result per entry in input order.

    Requests with the same key are resolved once (most-requested first, then input order) and share the result;
    each new row joins the known topics, so a later request in the batch can match it. `propose(text)` gives the row
    for a new topic (slug, name, terms, source): `derive` on a dry run, `suggest` live. `max_proposals` caps the calls.
    `order_known` is false when the existing topics' collection order is unknown (no readable created_at); a reason
    that names collection's first match then says so when two existing topics match.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): distinct keys are resolved by total count, highest first, ties in
    input order, and new rows are inserted in that order. Why: collection gives a shared document to the oldest topic,
    so the most-requested topic of a batch should be the one that is inserted first.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; proposed after review round 2, to confirm by Yelysei): a key's
    distinct texts are taken in NFKC form, most-requested first (ties in input order); every one is checked as a
    headline, and a new row is proposed from the first. Why: the key ignores word order and compatibility forms, on
    which the headline match and derive depend, so resolving the first entry's text made the shared result depend on
    input order ("war trade China" listed before "China trade war"; "Ｕｋｒａｉｎｅ war" before "Ukraine war").
    """
    infos = [_entry(i, raw) for i, raw in enumerate(entries)]
    groups: dict[str, list[int]] = {}
    for info in infos:
        if not info["_why"]:
            groups.setdefault(info["_key"], []).append(info["index"])
    order = sorted(groups, key=lambda k: (-sum(infos[i]["count"] for i in groups[k]), groups[k][0]))
    known = [_view(t) for t in existing]
    taken = {t["id"] for t in existing}
    outcomes: dict[str, dict[str, Any]] = {}
    calls = 0
    position = 0

    def counted(text: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return propose(text)

    for key in order:
        allowed = max_proposals is None or calls < max_proposals
        tally: dict[str, int] = {}
        for i in groups[key]:
            text = _clean(unicodedata.normalize("NFKC", infos[i]["text"]))
            tally[text] = tally.get(text, 0) + infos[i]["count"]
        texts = sorted(tally, key=lambda t: -tally[t])  # a stable sort: ties keep input order
        outcome = _resolve_one(key, texts, known, taken, counted if allowed else None, order_known=order_known)
        if outcome["status"] == "new":
            position += 1
            outcome["order"] = position
        outcomes[key] = outcome
    results = []
    for info in infos:
        if info["_why"]:
            outcome = {"status": "rejected", "topic_id": None, "name": None, "terms": [], "conflicts": [], "reason": info["_why"]}
        else:
            outcome = outcomes[info["_key"]]
        merged = {**info, **outcome}
        results.append({field: merged.get(field) for field in MAPPING_FIELDS})
    return results


# ------------------------------------------------------------------- outputs ----


def rows_sql(results: list[dict[str, Any]], *, header: str = "") -> str:
    """rows.sql: one insert-only statement per new row, in collection order, with the order rule stated on top.
    Raises ValueError for an id that breaks collection's id rule (the CHECK on topics.id would reject the insert)."""
    new: dict[str, dict[str, Any]] = {}
    for r in sorted((r for r in results if r["status"] == "new"), key=lambda r: r["order"]):
        if not _COLLECTION_ID.match(str(r["topic_id"] or "")):
            raise ValueError(f"new topic id {str(r['topic_id'])[:80]!r} breaks collection's id rule {_COLLECTION_ID.pattern}")
        new.setdefault(r["topic_id"], r)
    lines = [
        "-- Quorum topic intake: new rows for collection's `topics` table" + (f" ({header})" if header else "") + ".",
        "-- Run in this order with autocommit (psql's default; no BEGIN/COMMIT), so each row gets its own created_at.",
        "-- Collection order is created_at, then id: these rows come after every existing active topic, and a document",
        "-- that also matches an older topic stays with the older one (collectors/README.md › Topics).",
        "-- ON CONFLICT (id) DO NOTHING RETURNING id: an id that already exists is left untouched and returns no row.",
    ]
    derived = [r for r in new.values() if r.get("caution")]
    if derived:  # the DECISION at `_caution`
        lines += [
            f"-- {REVIEW_BEFORE_APPLYING}: {len(derived)} of {len(new)} rows below have terms derived from the phrase's own",
            "-- words (dry run, dry-run stand-in or model fallback), not chosen by a model; a single word of a longer phrase",
            "-- collects every headline that says it. Check each marked row's terms first (mapping.json `caution`).",
        ]
    if not new:
        lines.append("-- no new topics in this batch")
    for n, r in enumerate(new.values(), 1):
        lines.append(f"-- {n}. {r['name']} (requests: {sum(x['count'] for x in results if x.get('topic_id') == r['topic_id'] and x['status'] == 'new')})")
        if r.get("caution"):
            lines.append(f"--    review: {r['caution']}")
        lines.append(to_sql({"slug": r["topic_id"], "name": r["name"], "terms": r["terms"]}))
    return "\n".join(lines) + "\n"


MODE_DRY_RUN = "dry run (derive, no model call)"
MODE_DRY_ENV = ("dry environment (no --dry-run, but QUORUM_DRY_RUN=1 or no model route: suggest answered with its "
                "dry-run stand-in, derive's terms, no model call)")
MODE_LIVE = f"live (suggest: one fast-lane call per new topic, at most {MAX_MODEL_CALLS})"


def report_text(results: list[dict[str, Any]], *, source_note: str, mode: str, existing_count: int) -> str:
    """report.txt. `mode` is MODE_DRY_RUN, MODE_DRY_ENV or MODE_LIVE: how the batch actually resolved, not only its flag."""
    counts = {s: sum(1 for r in results if r["status"] == s) for s in INTAKE_STATUSES}
    distinct = len({request_key(r["text"]) for r in results if r["status"] != "rejected"})
    lines = [
        "Quorum topic intake",
        f"generated:  {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"mode:       {mode}",
        f"existing:   {existing_count} topics; {source_note}",
        f"requests:   {len(results)} entries, {distinct} distinct",
        "status:     " + ", ".join(f"{s} {counts[s]}" for s in INTAKE_STATUSES),
    ]
    if mode != MODE_LIVE:
        lines.append("note:       dry-run terms are the phrase's own words and naive plurals (derive); single generic words "
                     "over-collect, so prefer a live batch for rows that will be applied")
    lines.append("")
    for r in results:
        target = f"{r['topic_id']} ({r['name']})" if r.get("topic_id") else "-"
        lines.append(f"[{r['index']:>3}] {r['status']:<12} {r['text']!r} x{r['count']} -> {target}")
        lines.append(f"      {r['reason']}")
        if r["status"] in ("new", "needs_review") and r.get("terms"):
            lines.append("      terms: " + ", ".join(r["terms"]))
        if r.get("caution"):
            lines.append(f"      caution: {r['caution']}")
        for c in r.get("conflicts") or []:
            lines.append(f"      overlap: {c['term']!r} {c['relation']} {c['topic_term']!r} of {c['topic_id']}")
        if r.get("key_mismatch") is not None:
            lines.append(f"      key mismatch: the web sent {r['key']!r}, the contract gives {r['key_mismatch']!r}")
    return "\n".join(lines) + "\n"


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def intake(args: argparse.Namespace) -> int:
    """--from-requests: read the batch and the existing topics, write mapping.json, rows.sql and report.txt."""
    try:
        entries = _load_json(args.from_requests)
    except (OSError, ValueError) as exc:
        print(f"topics: cannot read {args.from_requests}: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 2
    if not isinstance(entries, list):
        print("topics: the requests file must hold a JSON list of {key, text, count}", file=sys.stderr)
        return 2
    try:
        if args.existing:
            raw = _load_json(args.existing)
            if not isinstance(raw, list):
                raise ValueError("the existing-topics file must hold a JSON list")
            existing, order_note = order_topics([t for t in (normalise_topic(r) for r in raw) if t is not None])
            source_note = f"file {args.existing}; {order_note}"
        else:
            existing, source_note = read_topics()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"topics: existing topics unavailable, nothing written: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 2
    if args.dry_run:
        mode, header = MODE_DRY_RUN, "dry run"
        propose: Callable[[str], dict[str, Any]] = lambda text: {**derive(text), "source": "derive"}  # noqa: E731
        cap = None
    else:
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): without --dry-run the batch resolves the route once, as
        # `suggest` will (llm.is_dry_run); a dry environment is labelled so in report.txt and rows.sql, and its rows
        # carry source "dry-run stand-in", never "model". Why: an operator with no route configured would otherwise
        # apply derive's naive terms believing a model chose them.
        try:
            env_dry = llm.is_dry_run(False)
        except Exception:
            env_dry = True
        mode, header = (MODE_DRY_ENV, "dry environment, stand-in terms") if env_dry else (MODE_LIVE, "live")
        cap = None if env_dry else MAX_MODEL_CALLS

        def propose(text: str) -> dict[str, Any]:
            row = suggest(text, dry_run=None, language_hint=args.language)
            if row.get("source") == "model" and row.get("dry_run"):
                row = {**row, "source": "dry-run stand-in"}
            return row

    results = resolve_requests(entries, existing, propose=propose, max_proposals=cap, order_known=ORDER_KNOWN in source_note)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        sql = rows_sql(results, header=f"{stamp}, {header}")
    except ValueError as exc:  # pragma: no cover - _free_slug keeps every id inside the rule; this is the last check
        print(f"topics: nothing written: {exc}", file=sys.stderr)
        return 2
    mapping = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    report = report_text(results, source_note=source_note, mode=mode, existing_count=len(existing))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mapping.json").write_text(mapping, encoding="utf-8")
    (out / "rows.sql").write_text(sql, encoding="utf-8")
    (out / "report.txt").write_text(report, encoding="utf-8")
    print("\n".join(report.splitlines()[:6]))
    print(f"wrote {out / 'mapping.json'}, {out / 'rows.sql'}, {out / 'report.txt'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collection terms for free-text topics: one phrase (--suggest, one fast-lane "
                                 "model call) or a batch of typed requests (--from-requests).")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--suggest", metavar="PHRASE", help="the topic as the reader typed it")
    what.add_argument("--from-requests", metavar="REQUESTS_JSON", help="a JSON list of {key, text, count} the web app collected")
    ap.add_argument("--out", metavar="DIR", help="--from-requests: where mapping.json, rows.sql and report.txt are written")
    ap.add_argument("--existing", metavar="TOPICS_JSON", help="--from-requests: existing topics from this JSON list instead of Zetaris")
    ap.add_argument("--language", default=None, help="optional language hint passed to the model")
    ap.add_argument("--json", action="store_true", help="--suggest: print the row as JSON")
    ap.add_argument("--sql", action="store_true", help="--suggest: print the insert-only INSERT … ON CONFLICT DO NOTHING for the topics table")
    ap.add_argument("--dry-run", action="store_true", help="answer with the deterministic stand-in (derive); no model call")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # a non-English phrase on a Windows console
    except (AttributeError, ValueError):
        pass
    if args.from_requests is not None:
        if not args.out:
            ap.error("--from-requests needs --out DIR")
        return intake(args)
    row = suggest(args.suggest, dry_run=True if args.dry_run else None, language_hint=args.language)
    if args.json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    elif not args.sql:
        print(_readable(row))
    if args.sql:
        print(to_sql(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
