"""Guardian Open Platform collector (free key, full text allowed for non-commercial use).

Docs: https://open-platform.theguardian.com/documentation/search
"""
from __future__ import annotations

import logging

from collectors.common import Doc, Fetcher, env, parse_dt, upsert_document

log = logging.getLogger("collectors.guardian")
API = "https://content.guardianapis.com/search"


# DECISION(2026-10-22, Anastasia/Claude): one page of 50, US-facing sections only. Why: the corpus is US-centred;
# two pages of Guardian outweighed every US outlet combined in the first live run (100 vs 2–3 each).
def collect(conn, fetcher: Fetcher, topic: dict, *, pages: int = 1) -> dict:
    key = env("GUARDIAN_API_KEY")
    stats = {"seen": 0, "inserted": 0}
    if not key:
        log.warning("GUARDIAN_API_KEY missing; skipping Guardian")
        return stats
    query = " OR ".join(f'"{t}"' if " " in t else t for t in topic["query_terms"])
    for page in range(1, pages + 1):
        resp = fetcher.get(
            API, respect_robots=False,
            params={"q": query, "section": "us-news", "order-by": "newest", "page-size": 50,
                    "page": page, "show-fields": "trailText,byline,bodyText"},
            headers={"api-key": key},  # header, not query string: keeps the key out of URLs and logs
        )
        if resp is None:
            break
        payload = resp.json().get("response", {})
        for item in payload.get("results", []):
            stats["seen"] += 1
            fields = item.get("fields", {})
            doc = Doc(
                source_id="guardian", topic_id=topic["id"], url=item["webUrl"], title=item["webTitle"],
                lead=fields.get("trailText"), byline=fields.get("byline"),
                published_at=parse_dt(item.get("webPublicationDate")), access_level=1,
                body_for_hash=fields.get("bodyText"),
            )
            if upsert_document(conn, doc) is not None:
                stats["inserted"] += 1
        if page >= int(payload.get("pages", 1)):
            break
    log.info("guardian: %s", stats)
    return stats
