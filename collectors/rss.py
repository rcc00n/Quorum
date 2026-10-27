"""RSS collector for outlets: title + lead from the feed, body fetched only for the hash at level 1.

Level is decided per source: sources.access_level_default, lowered to 2 when robots.txt disallows the page.
"""
from __future__ import annotations

import logging
import re
from html import unescape

import feedparser

from collectors.common import Doc, Fetcher, extract_text, first_topic_match, parse_dt, upsert_document, upsert_official_doc

log = logging.getLogger("collectors.rss")
_TAGS = re.compile(r"<[^>]+>")


def _strip(html: str | None) -> str | None:
    if not html:
        return None
    text = " ".join(unescape(_TAGS.sub(" ", html)).split())
    return text or None


def _body_text(html: str) -> str:
    """Article text for the hash, never stored. Same extractor as fetch_text so hashes agree across time."""
    return extract_text(html)


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


def collect_official_feed(conn, fetcher: Fetcher, source: dict, topics: list[dict], store_only: str | None = None) -> dict:
    """RSS of a government body (whitehouse.gov, defense.gov, state.gov): press releases, briefings, transcripts.

    `topics` is the ordered list of active topics (load_topics); each feed is walked once and every entry is stored
    under the first topic that matches it (first_topic_match in common.py; decision: README › Decisions, 2026-10-25).

    DECISION(2026-10-23, Anastasia/Claude Code): these go to official_docs with doc_type 'release' (the body's own
    words), never to documents, and the page text is stored in full (public domain). Why: DECISIONS.md › Principles
    — an official statement is a statement, not media coverage and not an establishing document; reasoning's
    confirmation rule reads doc_type verbatim, and 'release' never confirms.
    """
    stats = {"seen": 0, "matched": 0, "inserted": 0, "by_topic": {t["id"]: 0 for t in topics}}
    for feed_url in source["rss_urls"]:
        resp = fetcher.get(feed_url, respect_robots=False)
        if resp is None:
            continue
        for entry in _entries(resp.content):
            stats["seen"] += 1
            title = _strip(entry.get("title")) or ""
            lead = _strip(entry.get("summary") or entry.get("description"))
            link = entry.get("link")
            if not title or not link:
                continue
            topic, _match = first_topic_match(title, lead, topics)
            if topic is None or (store_only is not None and topic["id"] != store_only):
                continue  # store_only: a single-topic pass (run.py --topic) keeps the loop's ownership rule
            stats["matched"] += 1
            page = fetcher.get(link)
            text = extract_text(page.text) if page is not None else ""
            if not text:
                # DECISION(2026-10-24, Anastasia/Claude Code): a release whose page cannot be fetched this pass (robots.txt,
                # timeout, 5xx) or yields no paragraph text is skipped, not stored with the feed summary as its text.
                # Why: ON CONFLICT (url) replaces full_text, so the fallback overwrote a stored page text with a short
                # summary on the next transient failure; the same skip rule as collect_source. A body whose robots.txt
                # denies the bot therefore produces no official_docs rows (whitehouse.gov and defense.gov allow it).
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue
            if upsert_official_doc(conn, source_id=source["id"], topic_id=topic["id"], url=link,
                                   doc_type="release", doc_number=None, title=title, full_text=text,
                                   signed_at=None, published_at=parse_dt(entry.get("published") or entry.get("updated"))):
                stats["inserted"] += 1
                stats["by_topic"][topic["id"]] += 1
    log.info("%s (official): %s", source["id"], stats)
    return stats


def collect_source(conn, fetcher: Fetcher, source: dict, topics: list[dict], store_only: str | None = None) -> dict:
    """Walk every feed of one source once, matching every active topic. Returns counters.

    `topics` is the ordered list from load_topics; an entry goes to the first topic that matches it (first_topic_match
    in common.py; decision: README › Decisions, 2026-10-25) and is skipped when none does. `store_only` (run.py
    --topic) stores only the entries that topic wins; the others are skipped, never re-owned.
    """
    stats = {"seen": 0, "matched": 0, "inserted": 0, "level2": 0, "by_topic": {t["id"]: 0 for t in topics}}
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
            topic, match = first_topic_match(title, lead, topics)
            if topic is None or (store_only is not None and topic["id"] != store_only):
                continue  # store_only: a single-topic pass (run.py --topic) keeps the loop's ownership rule
            stats["matched"] += 1
            byline = entry.get("author")
            published = parse_dt(entry.get("published") or entry.get("updated"))
            level = int(source["access_level_default"])
            body = None
            link = fetcher.resolve(link)  # Google News wrapper -> publisher URL, so documents.url is the real one
            if level == 1:
                if not fetcher.allowed(link):
                    level = 2  # robots.txt disallows the page: title + lead only, by the access-level rule
                    stats["level2"] += 1
                else:
                    page = fetcher.get(link)
                    if page is None:
                        # DECISION(2026-10-24, Anastasia/Claude Code): a transient fetch failure (timeout, 5xx) on a
                        # level-1 source skips the item for this pass instead of downgrading it to level 2. Why: the
                        # hash at level 2 omits the body, so a downgrade produced a new row with supersedes_id and the
                        # next successful fetch collided with the original hash (the 2026-10-24 crash loop). The item
                        # is in the feed again next pass; only robots.txt decides level 2.
                        stats["skipped"] = stats.get("skipped", 0) + 1
                        continue
                    body = _body_text(page.text)
            doc = Doc(
                source_id=source["id"], topic_id=topic["id"], url=link, title=title, lead=lead,
                byline=byline, published_at=published, access_level=level, lang=source["lang"], body_for_hash=body,
                topic_match=match,
            )
            if upsert_document(conn, doc) is not None:
                stats["inserted"] += 1
                stats["by_topic"][topic["id"]] += 1
    log.info("%s: %s", source["id"], stats)
    return stats
