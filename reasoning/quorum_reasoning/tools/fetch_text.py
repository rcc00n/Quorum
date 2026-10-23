"""Article text at analysis time. Never stored: the caller keeps only verbatim quotes with offsets.

Honours the document's access level (1 = full text allowed, 2 = headline and lead only, 3 = nothing) and
robots.txt, with the same honest user agent the collectors use (COLLECTOR_USER_AGENT in .env). A document that
carries `text` (official rows, fixture rows) is read from it without any fetch.
"""

from __future__ import annotations

import os
import re
import urllib.robotparser
from functools import lru_cache
from html import unescape
from urllib.parse import urlsplit

import requests

from ..state import DocRef

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


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


def fetch_text(doc: DocRef, *, dry_run: bool, max_chars: int = 20000) -> str | None:
    """Returns the text reasoning may read for this document, or None when nothing beyond the lead is allowed.

    A document that carries `text` (official documents; fixture documents) is read from it, so the fixture corpus
    works with a live model too. Collection never stores outlet text, so live documents always go through the
    access-level and robots checks below. `dry_run` means: never touch the network.
    """
    if doc.get("text") and (doc.get("official") or doc["access_level"] == 1):
        return doc["text"]
    if doc["access_level"] >= 3:
        return None
    if doc["access_level"] == 2:
        return doc["lead"] or None
    if dry_run:
        return doc["lead"] or None
    if not allowed(doc["url"]):
        return doc["lead"] or None
    try:
        resp = requests.get(doc["url"], headers={"User-Agent": _user_agent()}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return doc["lead"] or None
    text = _WS.sub(" ", unescape(_TAG.sub(" ", resp.text)))
    return text[:max_chars]


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Character offsets of a verbatim quote, or None. Offsets are code-point based, end-exclusive."""
    i = text.find(quote)
    return (i, i + len(quote)) if i >= 0 else None
