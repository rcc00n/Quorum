"""Article text at analysis time. Never stored: the caller keeps only verbatim quotes with offsets.

The fetch itself is the collection block's `collectors.common.fetch_text` (robots.txt, per-domain delay, the
shared paragraph extractor, `content_hash` with the collectors' formula, code-point offsets): one fetcher for
the whole project, so a quote reasoning records can be verified against the same text later. This module adds
what reasoning needs around it: the document's access level (1 = full text allowed, 2 = headline and lead
only, 3 = nothing), the `text` passthrough for official and fixture documents, a per-run cache so one URL is
fetched once per run, and a fallback fetcher for environments where the collectors package cannot be imported.

DECISION(2026-10-23, Yelysei Shkirpan/Claude Code): delegate to collectors.common.fetch_text; keep the own
fetcher only as a fallback that the trace names. Why: two extractors give two texts and two hashes for one
URL, and quotes cut from one cannot be verified against the other (raised by Vadim in PORTAL_INTEGRATION.md).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

import requests

from ..state import DocRef

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_cache: dict[str, "FetchResult"] = {}
_collectors_import_error: str | None = None

COLLECTORS_FETCHER = "collectors.common.fetch_text"


@dataclass
class FetchResult:
    """What one document yields for reading and for quote binding.

    `text` is what reasoning may read (full text at level 1, the lead at level 2, nothing at level 3);
    `quote_text` is the string evidence offsets index into (the fetched article text or the official full text
    at level 1, `title + "\n" + lead` at level 2), and `content_hash` is the collectors' formula over it at
    fetch time. `fetcher` names where the text came from: the shared collectors fetcher, the document row
    itself (`corpus`: official full_text or a fixture's text), the lead only (`lead`), or the fallback fetcher.
    """

    text: str | None
    quote_text: str
    content_hash: str | None
    access_achieved: int  # 1 or 2 (3 never yields a result)
    fetched_at: str | None  # ISO 8601 UTC
    fetcher: str


def content_hash(title: str, lead: str | None, text: str | None) -> str:
    """The collectors' content-hash formula (collectors/common.py::content_hash): sha256 of UTF-8
    `title + "\n" + lead + "\n" + body[:2000]`. Reimplemented here, byte for byte, so official and fixture
    documents (whose text the corpus row carries) get a hash in the same space as `documents.content_hash`;
    the live path takes the hash from `FetchedText` itself and never recomputes it."""
    blob = (title or "") + "\n" + (lead or "") + "\n" + (text or "")[:2000]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _collectors_fetch():
    """collectors.common.fetch_text, or None when the package or its dependencies are missing.

    `collectors/` lives on the data-collection branch until the branches merge; QUORUM_COLLECTORS_PATH may name
    a read-only checkout of that branch (its repository root) so a live run on another branch still uses the one
    shared fetcher instead of the fallback, which is never acceptable for evidence (collectors/HANDOFF.md § 4.5).
    """
    global _collectors_import_error
    repo_root = Path(__file__).resolve().parents[3]
    for candidate in (os.getenv("QUORUM_COLLECTORS_PATH", "").strip(), str(repo_root)):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
    try:
        from collectors.common import fetch_text as collectors_fetch_text  # type: ignore

        return collectors_fetch_text
    except Exception as exc:  # noqa: BLE001 — ImportError, or a dependency the collectors need (httpx, psycopg)
        _collectors_import_error = f"{type(exc).__name__}: {exc}"
        return None


def fetcher_name() -> str:
    """For the trace: which fetcher a live run uses."""
    if _collectors_fetch() is not None:
        return COLLECTORS_FETCHER
    return f"fallback fetcher (collectors not importable: {_collectors_import_error}; set QUORUM_COLLECTORS_PATH)"


def using_shared_fetcher() -> bool:
    return _collectors_fetch() is not None


def clear_cache() -> None:
    """Called by `plan` at the start of a run: texts are kept for one run only, never across runs."""
    _cache.clear()


def _user_agent() -> str:
    return os.getenv("COLLECTOR_USER_AGENT", "QuorumBot/0.1 (+mailto:team@example.org)")


@lru_cache(maxsize=256)
def _robots(domain: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"https://{domain}/robots.txt")
    try:
        rp.read()
    except Exception:  # noqa: BLE001 — unreadable robots.txt: be conservative below
        rp.disallow_all = True
    return rp


def allowed(url: str) -> bool:
    domain = urlsplit(url).netloc
    return _robots(domain).can_fetch(_user_agent(), url)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fallback_fetch(doc: DocRef) -> str | None:
    if not allowed(doc["url"]):
        return None
    try:
        resp = requests.get(doc["url"], headers={"User-Agent": _user_agent()}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return _WS.sub(" ", unescape(_TAG.sub(" ", resp.text)))


def _lead_result(doc: DocRef, fetcher: str) -> FetchResult:
    """Headline and lead only: offsets index `title + "\n" + lead`, the hash is the collectors' level-2 hash."""
    lead = doc["lead"] or ""
    return FetchResult(
        text=lead or None,
        quote_text=doc["title"] + "\n" + lead,
        content_hash=content_hash(doc["title"], lead or None, None),
        access_achieved=2,
        fetched_at=doc.get("fetched_at"),
        fetcher=fetcher,
    )


def _live_fetch(doc: DocRef) -> FetchResult:
    """Full text of a level-1 document through the shared fetcher (or the fallback), cached per run by URL.
    When robots.txt or the site refuse, the result drops to level 2 (headline and lead), the way
    `collectors.common.fetch_text` reports it."""
    url = doc["url"]
    if url in _cache:
        return _cache[url]
    collectors_fetch_text = _collectors_fetch()
    if collectors_fetch_text is not None:
        fetched = collectors_fetch_text(url, title=doc["title"], lead=doc["lead"] or None)
        when = fetched.fetched_at
        when_s = when.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if hasattr(when, "astimezone") else _now()
        if fetched.access_level == 1 and fetched.text:
            result = FetchResult(text=fetched.text, quote_text=fetched.text, content_hash=fetched.content_hash, access_achieved=1, fetched_at=when_s, fetcher=COLLECTORS_FETCHER)
        else:
            result = _lead_result(doc, COLLECTORS_FETCHER)
            result.fetched_at = when_s
    else:
        text = _fallback_fetch(doc)
        if text:
            result = FetchResult(text=text, quote_text=text, content_hash=content_hash(doc["title"], doc["lead"] or None, text), access_achieved=1, fetched_at=_now(), fetcher="fallback")
        else:
            result = _lead_result(doc, "fallback")
            result.fetched_at = _now()
    _cache[url] = result
    return result


def fetch_result(doc: DocRef, *, dry_run: bool, max_chars: int = 20000) -> FetchResult | None:
    """The text reasoning may read for this document plus what binds a quote to it, or None at level 3.

    A document that carries `text` (official documents; fixture documents) is read from it, so the fixture corpus
    works with a live model too; its hash is the collectors' formula over that text and `fetched_at` is the row's
    own (collection stored the text). Collection never stores outlet text, so live level-1 documents go through
    the shared fetcher. `dry_run` means: never touch the network — a level-1 document without text yields its
    lead at level 2. `max_chars` bounds `text` only; offsets index `quote_text`, of which `text` is a prefix.
    """
    if doc.get("text") and (doc.get("official") or doc["access_level"] == 1):
        text = doc["text"]
        return FetchResult(
            text=text[:max_chars],
            quote_text=text,
            content_hash=content_hash(doc["title"], doc["lead"] or None, text),
            access_achieved=1,
            fetched_at=doc.get("fetched_at"),
            fetcher="corpus",
        )
    if doc["access_level"] >= 3:
        return None
    if doc["access_level"] == 2 or dry_run:
        return _lead_result(doc, "lead")
    result = _live_fetch(doc)
    if result.text and len(result.text) > max_chars:
        return FetchResult(result.text[:max_chars], result.quote_text, result.content_hash, result.access_achieved, result.fetched_at, result.fetcher)
    return result


def fetch_text(doc: DocRef, *, dry_run: bool, max_chars: int = 20000) -> str | None:
    """The text reasoning may read for this document, or None when nothing is allowed (see `fetch_result`)."""
    result = fetch_result(doc, dry_run=dry_run, max_chars=max_chars)
    return result.text if result else None


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Character offsets of a verbatim quote, or None. Offsets are code-point based, end-exclusive — the
    convention of `collectors.common.verify_quote` (Python `str` indexes, not UTF-8 bytes or UTF-16 units)."""
    i = text.find(quote)
    return (i, i + len(quote)) if i >= 0 else None
