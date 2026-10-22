"""RSS collector for outlets: title + lead from the feed, body fetched only for the hash at level 1.

Level is decided per source: sources.access_level_default, lowered to 2 when robots.txt disallows the page.
"""
from __future__ import annotations

import logging
import re
from html import unescape

import feedparser

from collectors.common import Doc, Fetcher, matches_topic, parse_dt, upsert_document

log = logging.getLogger("collectors.rss")
_TAGS = re.compile(r"<[^>]+>")


def _strip(html: str | None) -> str | None:
    if not html:
        return None
    text = " ".join(unescape(_TAGS.sub(" ", html)).split())
    return text or None


def _body_text(html: str) -> str:
    """Crude article text: paragraphs only. Used for the hash, never stored."""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.I | re.S)
    return " ".join(filter(None, (_strip(p) for p in paras)))[:4000]


def collect_source(conn, fetcher: Fetcher, source: dict, topic: dict | None) -> dict:
    """Walk every feed of one source. Returns counters."""
    stats = {"seen": 0, "matched": 0, "inserted": 0, "level2": 0}
    terms = topic["query_terms"] if topic else []
    for feed_url in source["rss_urls"]:
        resp = fetcher.get(feed_url, respect_robots=False)  # feeds are published for machines
        if resp is None:
            continue
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries:
            stats["seen"] += 1
            title = _strip(entry.get("title")) or ""
            lead = _strip(entry.get("summary") or entry.get("description"))
            link = entry.get("link")
            if not title or not link:
                continue
            if terms and not matches_topic(f"{title} {lead or ''}", terms):
                continue
            stats["matched"] += 1
            byline = entry.get("author")
            published = parse_dt(entry.get("published") or entry.get("updated"))
            level = int(source["access_level_default"])
            body = None
            if level == 1:
                page = fetcher.get(link)
                if page is None:
                    level = 2
                    stats["level2"] += 1
                else:
                    body = _body_text(page.text)
            doc = Doc(
                source_id=source["id"], topic_id=topic["id"] if topic else None, url=link, title=title, lead=lead,
                byline=byline, published_at=published, access_level=level, lang=source["lang"], body_for_hash=body,
            )
            if upsert_document(conn, doc) is not None:
                stats["inserted"] += 1
    log.info("%s: %s", source["id"], stats)
    return stats
