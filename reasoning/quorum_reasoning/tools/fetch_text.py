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

import os
import re
import sys
import urllib.robotparser
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

import requests

from ..state import DocRef

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_cache: dict[str, str | None] = {}
_collectors_import_error: str | None = None


def _collectors_fetch():
    """collectors.common.fetch_text, or None when the package or its dependencies are missing."""
    global _collectors_import_error
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from collectors.common import fetch_text as collectors_fetch_text  # type: ignore

        return collectors_fetch_text
    except Exception as exc:  # noqa: BLE001 — ImportError, or a dependency the collectors need (httpx, psycopg)
        _collectors_import_error = f"{type(exc).__name__}: {exc}"
        return None


def fetcher_name() -> str:
    """For the trace: which fetcher a live run uses."""
    if _collectors_fetch() is not None:
        return "collectors.common.fetch_text"
    return f"fallback fetcher (collectors not importable: {_collectors_import_error})"


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


def _fallback_fetch(doc: DocRef, max_chars: int) -> str | None:
    if not allowed(doc["url"]):
        return None
    try:
        resp = requests.get(doc["url"], headers={"User-Agent": _user_agent()}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return _WS.sub(" ", unescape(_TAG.sub(" ", resp.text)))[:max_chars]


def _live_fetch(doc: DocRef, max_chars: int) -> str | None:
    """Full text of a level-1 document, or None when robots.txt or the site refuse. Cached per run by URL."""
    url = doc["url"]
    if url in _cache:
        return _cache[url]
    collectors_fetch_text = _collectors_fetch()
    text: str | None
    if collectors_fetch_text is not None:
        fetched = collectors_fetch_text(url, title=doc["title"], lead=doc["lead"] or None)
        text = fetched.text[:max_chars] if fetched.access_level == 1 and fetched.text else None
    else:
        text = _fallback_fetch(doc, max_chars)
    _cache[url] = text
    return text


def fetch_text(doc: DocRef, *, dry_run: bool, max_chars: int = 20000) -> str | None:
    """Returns the text reasoning may read for this document, or None when nothing beyond the lead is allowed.

    A document that carries `text` (official documents; fixture documents) is read from it, so the fixture corpus
    works with a live model too. Collection never stores outlet text, so live documents always go through the
    access-level check and the collectors' fetcher. `dry_run` means: never touch the network.
    """
    if doc.get("text") and (doc.get("official") or doc["access_level"] == 1):
        return doc["text"]
    if doc["access_level"] >= 3:
        return None
    if doc["access_level"] == 2:
        return doc["lead"] or None
    if dry_run:
        return doc["lead"] or None
    return _live_fetch(doc, max_chars) or doc["lead"] or None


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Character offsets of a verbatim quote, or None. Offsets are code-point based, end-exclusive."""
    i = text.find(quote)
    return (i, i + len(quote)) if i >= 0 else None
