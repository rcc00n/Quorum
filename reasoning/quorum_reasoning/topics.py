"""Free-text topic → collection terms: the words → terms step behind a topic the reader types.

The web app writes a `topics` row (id = slug, name, query_terms) that the collection block reads; this module
supplies the row. One fast-lane model call (`prompts/topic_terms.md`) proposes slug, name and terms; code
validates them against collection's matching rules (collectors/README.md › Topics: whole words,
case-insensitive, no stemming, plurals listed explicitly) and falls back to a deterministic row built from the
phrase itself when the call fails or the reply is unusable.

    python -m quorum_reasoning.topics --suggest "climate policy and carbon tax" [--json] [--sql] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from typing import Any

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
    """The upsert collection's `ensure_topic` runs (collectors/common.py: topics(id TEXT, name TEXT, query_terms TEXT[]))."""
    terms = ", ".join(_sql_str(t) for t in row.get("terms") or [])
    array = f"ARRAY[{terms}]" if terms else "ARRAY[]::text[]"
    return (
        f"INSERT INTO topics (id, name, query_terms) VALUES ({_sql_str(row['slug'])}, {_sql_str(row['name'])}, {array}) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, query_terms = EXCLUDED.query_terms;"
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Suggest collection terms for a free-text topic (one fast-lane model call).")
    ap.add_argument("--suggest", required=True, metavar="PHRASE", help="the topic as the reader typed it")
    ap.add_argument("--language", default=None, help="optional language hint passed to the model")
    ap.add_argument("--json", action="store_true", help="print the row as JSON")
    ap.add_argument("--sql", action="store_true", help="print the INSERT … ON CONFLICT upsert for the topics table")
    ap.add_argument("--dry-run", action="store_true", help="answer with the deterministic stand-in; no model call")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # a non-English phrase on a Windows console
    except (AttributeError, ValueError):
        pass
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
