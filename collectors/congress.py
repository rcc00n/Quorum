"""Congress.gov collector: bills matching the topic, with their latest action and summary. Free api.data.gov key.

Docs: https://api.congress.gov/
Bill text and roll-call votes are public domain; stored as official_docs with doc_type 'law' (enacted) or 'release'
(introduced / in committee), because an unpassed bill is a statement of intent, not an adopted document.
"""
from __future__ import annotations

import logging

from collectors.common import Fetcher, env, parse_dt, upsert_official_doc

log = logging.getLogger("collectors.congress")
API = "https://api.congress.gov/v3"
CONGRESS = 119  # 2025–2026


def _doc_type(latest_action: str) -> str:
    text = (latest_action or "").lower()
    if "became public law" in text or "signed by president" in text:
        return "law"
    if "passed" in text or "agreed to" in text:
        return "vote"
    return "release"


def collect(conn, fetcher: Fetcher, topic: dict, *, limit: int = 50) -> dict:
    key = env("CONGRESS_API_KEY")
    stats = {"seen": 0, "inserted": 0}
    if not key:
        log.warning("CONGRESS_API_KEY missing; skipping Congress.gov")
        return stats
    # The v3 API has no full-text search; we list recent bills and filter titles by topic terms.
    resp = fetcher.get(f"{API}/bill/{CONGRESS}", respect_robots=False,
                       params={"api_key": key, "limit": limit, "sort": "updateDate+desc", "format": "json"})
    if resp is None:
        return stats
    terms = [t.lower() for t in topic["query_terms"]]
    for bill in resp.json().get("bills", []):
        title = bill.get("title", "")
        if not any(t in title.lower() for t in terms):
            continue
        stats["seen"] += 1
        number = f'{bill["type"]}{bill["number"]}'
        detail = fetcher.get(f'{API}/bill/{CONGRESS}/{bill["type"].lower()}/{bill["number"]}',
                             respect_robots=False, params={"api_key": key, "format": "json"})
        latest = bill.get("latestAction", {})
        summary = ""
        if detail is not None:
            summaries = fetcher.get(f'{API}/bill/{CONGRESS}/{bill["type"].lower()}/{bill["number"]}/summaries',
                                    respect_robots=False, params={"api_key": key, "format": "json"})
            if summaries is not None:
                items = summaries.json().get("summaries", [])
                if items:
                    summary = items[-1].get("text", "")
        full_text = f'{title}\n\nLatest action ({latest.get("actionDate")}): {latest.get("text")}\n\n{summary}'
        url = f'https://www.congress.gov/bill/{CONGRESS}th-congress/{bill["type"].lower()}/{bill["number"]}'
        inserted = upsert_official_doc(
            conn, source_id="congress-gov", topic_id=topic["id"], url=url,
            doc_type=_doc_type(latest.get("text", "")), doc_number=number, title=title, full_text=full_text,
            signed_at=None, published_at=parse_dt(latest.get("actionDate")),
        )
        stats["inserted"] += int(inserted)
    log.info("congress: %s", stats)
    return stats
