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

STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have he her his i if in into is it its me my no nor not of
    on or our over she so than that the their them then there these they this those to under up us was we were
    what when where which while who will with within without you your about after against all also any around
    before between both during each more most news other some such through very via""".split()
)


def _clean(text: Any) -> str:
    s = str(text or "").replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
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
    plurals, then its significant single words and their plurals; each one passes `normalize_term`.
    """
    text = _clean(phrase)
    words = [re.sub(r"'s$", "", w, flags=re.IGNORECASE) for w in _WORD.findall(text)]  # "Biden's" -> "Biden"
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
        if _significant(w):
            candidates += [w, plural(w)]
    terms, _ = clean_terms([c for c in candidates if c])
    if not terms and normalize_term(text) is None and TERM_MIN_CHARS <= len(text) <= TERM_MAX_CHARS and _TERM_CHARS.match(text):
        terms = [text.lower()]  # a phrase of short words only ("tax"): keep it whole rather than return nothing
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
# match: name | slug | headline for existing (and for a retired-topic needs_review); source: derive | model | fallback
# for a proposed row; order: 1-based insert order of a new row in rows.sql; key_mismatch: the contract's key when the
# web app sent a different one.
MAPPING_FIELDS = ("index", "key", "text", "count", "status", "topic_id", "name", "terms", "conflicts", "reason",
                  "match", "source", "order", "key_mismatch")
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a live batch (no --dry-run) makes at most this many model calls;
# the requests beyond it are needs_review with a "deferred" reason and are proposed again on the next batch. Why: one
# fast-lane call per new topic, and the per-account budget rules (README › Run it) need a bound a web form cannot set.
MAX_MODEL_CALLS = 25
WITHHELD = "[withheld]"
_COLLECTION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")  # collectors/schema.sql topics.id CHECK; tools/corpus.py --topic


def request_key(text: Any) -> str:
    """The normalised request key: the contract shared with the web app (docs/DECISIONS.md › Daily editions for users).

    1. lowercase, Unicode NFKD, drop every combining mark (general category M), lowercase again;
    2. delete a full stop that stands between two letters ("U.S." -> "us", "e.g." -> "eg");
    3. tokens = maximal runs of letters and digits (categories L and N); everything else separates tokens;
    4. drop KEY_STOPWORDS; 5. the unique tokens, sorted by code point, joined by single spaces.

    "war in Ukraine" and "Ukraine war" give "ukraine war"; "U.S. tariffs on China!" gives "china tariffs us". The same
    in the web app (JavaScript):

        const STOP = new Set("a about an and at by for from in into of on or over s the to vs with news".split(" "));
        const requestKey = t => [...new Set((String(t ?? "").toLowerCase().normalize("NFKD").replace(/\\p{M}/gu, "")
          .toLowerCase().replace(/(?<=\\p{L})\\.(?=\\p{L})/gu, "").match(/[\\p{L}\\p{N}]+/gu) || [])
          .filter(w => !STOP.has(w)))].sort().join(" ");

    (`sort()` compares UTF-16 units, which equals code-point order unless the text has astral-plane letters.)
    """
    s = unicodedata.normalize("NFKD", str(text if text is not None else "").lower())
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M")).lower()
    s = "".join(c for i, c in enumerate(s) if not (c == "." and 0 < i < len(s) - 1 and s[i - 1].isalpha() and s[i + 1].isalpha()))
    tokens: set[str] = set()
    cur: list[str] = []
    for c in s + " ":
        if unicodedata.category(c)[0] in "LN":
            cur.append(c)
        elif cur:
            tokens.add("".join(cur))
            cur = []
    return " ".join(sorted(t for t in tokens if t not in KEY_STOPWORDS))


_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_URL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\."
    r"(?:com|org|net|gov|edu|mil|int|io|co|ai|app|dev|info|biz|news|ly|me|tv|us|uk|ru|ua|de|fr|eu|ca|au|cn|jp|in|xyz)\b"
)
_HANDLE_RE = re.compile(r"(?<![\w.])@\w{2,}")
_PHONE_RE = re.compile(
    r"\+\d[\d\s().-]{6,}\d"  # international: +44 20 7946 0958
    r"|(?<!\d)\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"  # North American: (555) 123-4567, 555.123.4567, 5551234567
    r"|(?<![\d.-])\d{3}[.-]\d{4}(?![\d.-])"  # local: 555-1234 (not "2026-2027", not "100 2026")
)
_MARKUP_RE = re.compile(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def check_request(text: Any) -> tuple[str, bool]:
    """("", False) for an acceptable typed topic, else (why, withheld): the checks the web app must run before it
    stores a request, and that the batch repeats. `withheld` is true when the text may carry personal data (an
    e-mail address, a URL, an @handle, a phone number), so outputs must not echo it.

    Order: not text, over 25 × REQUEST_MAX_CHARS raw (not scanned, withheld), empty, e-mail, URL, @handle, phone,
    markup (`<`, `>`) or control characters, over REQUEST_MAX_CHARS code points after collapsing whitespace (JS:
    `[...text].length`), no letter at all, nothing left after `request_key`.
    """
    if not isinstance(text, str):
        return "not text", False
    if len(text) > 25 * REQUEST_MAX_CHARS:  # not scanned at all; withheld because nobody looked at what it holds
        return f"longer than {REQUEST_MAX_CHARS} characters ({len(_clean(text))})", True
    cleaned = _clean(text)
    if not cleaned:
        return "empty", False
    for pattern, why in ((_EMAIL_RE, "contains an e-mail address"), (_URL_RE, "contains a URL"),
                         (_HANDLE_RE, "contains an @handle"), (_PHONE_RE, "contains a phone number")):
        if pattern.search(cleaned):
            return why, True
    if _MARKUP_RE.search(text):
        return "contains markup or control characters", False
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
    return ordered, "collection order: created_at, id"


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): existing topics are read with the widest column list Zetaris
# accepts: (id, name, query_terms, active, created_at), then without created_at, then without active (every topic then
# taken as active; report.txt says which). Why: on the rehearsal registration the five-column SELECT returned HTTP 400
# while the documented three-column one worked; registering or refreshing Zetaris tables is not this command's job.
_TOPIC_COLUMNS = ("id, name, query_terms, active, created_at", "id, name, query_terms, active", "id, name, query_terms")
TOPIC_READ_LIMIT = 1000


def read_topics(run_sql: Callable[[str, int], list[dict[str, Any]]] | None = None) -> tuple[list[dict[str, Any]], str]:
    """(topics in collection order, note): the existing rows of collection's `topics` table through Zetaris
    (`<ZETARIS_COLLECTION_DB>.topics`, read-only SQL). Raises RuntimeError when no query succeeds."""
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
        topics = [t for t in (normalise_topic(r) for r in rows or []) if t is not None]
        topics, order_note = order_topics(topics)
        notes = [f"Zetaris {table} ({cols})", order_note]
        if "active" not in cols:
            notes.append("`active` not exposed: every topic taken as active")
        if len(rows or []) >= TOPIC_READ_LIMIT:
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


def _free_slug(slug: str, taken: set[str]) -> str:
    """The slug, or slug-2, slug-3, … when an existing or earlier row holds it (ids are never reused or overwritten).

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a taken id gets a numeric suffix rather than failing the request.
    Why: the request's words already differ from that topic's name and slug (the key check ran first), so it is a
    different topic that happens to slug alike; collection's id rule allows the extra segment."""
    base = slug if _COLLECTION_ID.match(slug or "") else slug_for(slug or "")
    if base not in taken:
        return base
    stem = base[:60].rstrip("-")
    for n in range(2, 1000):
        if f"{stem}-{n}" not in taken:
            return f"{stem}-{n}"
    return "topic-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]  # pragma: no cover - 998 namesakes


def _existing(t: dict[str, Any], match: str, reason: str) -> dict[str, Any]:
    return {"status": "existing", "match": match, "topic_id": t["id"], "name": t["name"], "terms": list(t["terms"]),
            "conflicts": [], "reason": reason + (" (a new row of this batch)" if t.get("batch") else "")}


def _resolve_one(key: str, text: str, known: list[dict[str, Any]], taken: set[str], propose: Callable[[str], dict[str, Any]] | None) -> dict[str, Any]:
    """One distinct request against the topics known so far (collection order, this batch's new rows last)."""
    # 1. The same words as a topic's name or slug: that topic (Issue #2 6405180457: match typed text against names first).
    for t in known:
        if key in (t["name_key"], t["slug_key"]):
            how = "name" if key == t["name_key"] else "slug"
            if t["active"]:
                return _existing(t, how, f"same words as the {how} of {t['id']}")
            return {**_existing(t, how, ""), "status": "needs_review",
                    "reason": f"same words as the {how} of retired topic {t['id']} (active = false); reactivating it is the operator's call"}
    # 2. A headline that says what the reader typed would be collected under an existing topic: that topic.
    for t in known:
        hits = [term for term in t["terms"] if _occurs(term, text)] if t["active"] else []
        if hits:
            return _existing(t, "headline", f"a headline saying {text!r} is collected under {t['id']} (term {hits[0]!r}): "
                             "one topic per document, the older topic first")
    # 3. A new row: the proposed terms minus every term that overlaps an active topic's term.
    if propose is None:
        return {"status": "needs_review", "match": None, "topic_id": None, "name": None, "terms": [], "conflicts": [],
                "reason": f"deferred: this batch reached its cap of {MAX_MODEL_CALLS} model calls; run the batch again"}
    row = propose(text)
    slug = _free_slug(str(row.get("slug") or ""), taken)
    kept: list[str] = []
    conflicts: list[dict[str, str]] = []
    for term in row.get("terms") or []:
        flags = [{"term": term, "topic_id": t["id"], "topic_term": other, "relation": rel}
                 for t in known if t["active"] for other in t["terms"] if (rel := term_relation(term, other))]
        if flags:
            conflicts += flags
        else:
            kept.append(term)
    out = {"match": None, "topic_id": slug, "name": str(row.get("name") or text)[:NAME_MAX_CHARS], "terms": kept,
           "conflicts": conflicts, "source": row.get("source")}
    if not kept:
        return {**out, "status": "needs_review", "reason": "every proposed term overlaps a term of an existing topic"}
    if not any(_occurs(term, text) for term in kept):
        return {**out, "status": "needs_review",
                "reason": f"without the overlapping terms no term would collect a headline saying {text!r}"}
    known.append(_view({"id": slug, "name": out["name"], "terms": kept, "active": True, "created_at": None}, batch=True))
    taken.add(slug)
    dropped = len({c["term"] for c in conflicts})
    return {**out, "status": "new",
            "reason": f"no existing topic covers these words; {len(kept)} terms" + (f", {dropped} overlapping dropped" if dropped else "")}


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
    base: dict[str, Any] = {"index": index, "key": web_key if web_key is not None else key,
                            "text": _clean(text) if isinstance(text, str) else None, "count": count}
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
                     max_proposals: int | None = None) -> list[dict[str, Any]]:
    """The mapping for a batch of typed requests, one result per entry in input order.

    Requests with the same key are resolved once (most-requested first, then input order) and share the result;
    each new row joins the known topics, so a later request in the batch can match it. `propose(text)` gives the row
    for a new topic (slug, name, terms, source): `derive` on a dry run, `suggest` live. `max_proposals` caps the calls.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): distinct keys are resolved by total count, highest first, ties in
    input order, and new rows are inserted in that order. Why: collection gives a shared document to the oldest topic,
    so the most-requested topic of a batch should be the one that is inserted first.
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
        outcome = _resolve_one(key, infos[groups[key][0]]["text"], known, taken, counted if allowed else None)
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
    """rows.sql: one insert-only statement per new row, in collection order, with the order rule stated on top."""
    new: dict[str, dict[str, Any]] = {}
    for r in sorted((r for r in results if r["status"] == "new"), key=lambda r: r["order"]):
        new.setdefault(r["topic_id"], r)
    lines = [
        "-- Quorum topic intake: new rows for collection's `topics` table" + (f" ({header})" if header else "") + ".",
        "-- Run in this order with autocommit (psql's default; no BEGIN/COMMIT), so each row gets its own created_at.",
        "-- Collection order is created_at, then id: these rows come after every existing active topic, and a document",
        "-- that also matches an older topic stays with the older one (collectors/README.md › Topics).",
        "-- ON CONFLICT (id) DO NOTHING RETURNING id: an id that already exists is left untouched and returns no row.",
    ]
    if not new:
        lines.append("-- no new topics in this batch")
    for n, r in enumerate(new.values(), 1):
        lines.append(f"-- {n}. {r['name']} (requests: {sum(x['count'] for x in results if x.get('topic_id') == r['topic_id'] and x['status'] == 'new')})")
        lines.append(to_sql({"slug": r["topic_id"], "name": r["name"], "terms": r["terms"]}))
    return "\n".join(lines) + "\n"


def report_text(results: list[dict[str, Any]], *, source_note: str, dry_run: bool, existing_count: int) -> str:
    counts = {s: sum(1 for r in results if r["status"] == s) for s in INTAKE_STATUSES}
    distinct = len({request_key(r["text"]) for r in results if r["status"] != "rejected"})
    lines = [
        "Quorum topic intake",
        f"generated:  {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"mode:       {'dry run (derive, no model call)' if dry_run else 'live (suggest: one fast-lane call per new topic)'}",
        f"existing:   {existing_count} topics; {source_note}",
        f"requests:   {len(results)} entries, {distinct} distinct",
        "status:     " + ", ".join(f"{s} {counts[s]}" for s in INTAKE_STATUSES),
    ]
    if dry_run:
        lines.append("note:       dry-run terms are the phrase's own words and naive plurals (derive); single generic words "
                     "over-collect, so prefer a live batch for rows that will be applied")
    lines.append("")
    for r in results:
        target = f"{r['topic_id']} ({r['name']})" if r.get("topic_id") else "-"
        lines.append(f"[{r['index']:>3}] {r['status']:<12} {r['text']!r} x{r['count']} -> {target}")
        lines.append(f"      {r['reason']}")
        if r["status"] in ("new", "needs_review") and r.get("terms"):
            lines.append("      terms: " + ", ".join(r["terms"]))
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
        propose: Callable[[str], dict[str, Any]] = lambda text: {**derive(text), "source": "derive"}  # noqa: E731
        cap = None
    else:
        propose = lambda text: suggest(text, dry_run=None, language_hint=args.language)  # noqa: E731
        cap = MAX_MODEL_CALLS
    results = resolve_requests(entries, existing, propose=propose, max_proposals=cap)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mapping.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (out / "rows.sql").write_text(rows_sql(results, header=f"{stamp}, {'dry run' if args.dry_run else 'live'}"), encoding="utf-8")
    report = report_text(results, source_note=source_note, dry_run=bool(args.dry_run), existing_count=len(existing))
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
