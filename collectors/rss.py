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


_SITEMAP_URL = re.compile(r"<url>(.*?)</url>", re.S)


def _entries(content: bytes) -> list[dict]:
    """RSS/Atom via feedparser; Google news-sitemap XML (Reuters) via a small regex parser."""
    parsed = feedparser.parse(content)
    if parsed.entries:
        return [dict(e) for e in parsed.entries]
    text = content.decode("utf-8", "replace")
    if "<urlset" not in text:
        return []
    out = []
    for block in _SITEMAP_URL.findall(text):
        loc = re.search(r"<loc>(.*?)</loc>", block, re.S)
        title = re.search(r"<news:title>(.*?)</news:title>", block, re.S)
        date = re.search(r"<news:publication_date>(.*?)</news:publication_date>", block, re.S)
        if loc and title:
            out.append({"link": loc.group(1).strip(), "title": unescape(title.group(1).strip()),
                        "summary": None, "author": None, "published": date.group(1).strip() if date else None})
    return out


def collect_source(conn, fetcher: Fetcher, source: dict, topic: dict | None) -> dict:
    """Walk every feed of one source. Returns counters."""
    stats = {"seen": 0, "matched": 0, "inserted": 0, "level2": 0}
    terms = topic["query_terms"] if topic else []
    for feed_url in source["rss_urls"]:
        resp = fetcher.get(feed_url, respect_robots=False)  # feeds are published for machines
        if resp is None:
            continue
        for entry in _entries(resp.content):
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
            link = fetcher.resolve(link)  # Google News wrapper -> publisher URL, so documents.url is the real one
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
