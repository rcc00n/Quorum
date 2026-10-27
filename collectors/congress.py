"""Congress.gov collector: bills on the topic, with their latest action and summary. Free api.data.gov key.

The v3 API (https://api.congress.gov/) has no keyword search, so discovery pages through the most recently updated
bills of the current Congress and filters titles by topic terms; the API then supplies latest action and summary.

Bill records are public domain; stored as official_docs with doc_type 'law' (enacted), 'vote' (passed a chamber)
or 'release' (introduced / in committee), because an unpassed bill is a statement of intent, not an adopted document.
"""
from __future__ import annotations

import logging
from collectors.common import Fetcher, claimed_by_older, env, parse_dt, upsert_official_doc

log = logging.getLogger("collectors.congress")
API = "https://api.congress.gov/v3"
CONGRESS = 119  # 2025–2026
# Congress.gov URL slug -> API bill type
_TYPES = {"house-bill": "hr", "senate-bill": "s", "house-resolution": "hres", "senate-resolution": "sres",
          "house-joint-resolution": "hjres", "senate-joint-resolution": "sjres",
          "house-concurrent-resolution": "hconres", "senate-concurrent-resolution": "sconres"}


def _doc_type(latest_action: str) -> str:
    """Map a bill's latest action to the schema's doc_type.

    DECISION(2026-10-23, Anastasia/Claude Code): 'law' only when enacted ("Became Public Law" / "Signed by
    President"); 'vote' when a chamber passed or agreed to it — the fact established is that the vote happened
    with that outcome, not that the bill is law; everything else (introduced, referred, reported) is 'release',
    i.e. a statement of intent. Why: reasoning's confirmation rule treats law|order|vote|ruling as establishing
    documents and statement|release as words (DECISIONS.md › Principles); an unpassed bill must not confirm.
    """
    text = (latest_action or "").lower()
    if "became public law" in text or "signed by president" in text:
        return "law"
    if "passed" in text or "agreed to" in text:
        return "vote"
    return "release"


def _discover(fetcher: Fetcher, topic: dict, key: str, *, pages: int = 4, page_size: int = 250) -> set[tuple[int, str, int]]:
    """(congress, type, number) triples whose title matches a topic term, scanning the most recently updated bills.

    The v3 API has no keyword search, so we page through /bill/{congress} sorted by update date and filter titles.
    pages*page_size = 1000 most recently updated bills per pass.
    """
    terms = [t.lower() for t in topic["query_terms"]]
    found: set[tuple[int, str, int]] = set()
    for page in range(pages):
        resp = fetcher.get(f"{API}/bill/{CONGRESS}", respect_robots=False,
                           params={"api_key": key, "limit": page_size, "offset": page * page_size,
                                   "sort": "updateDate+desc", "format": "json"})
        if resp is None:
            break
        bills = resp.json().get("bills", [])
        for bill in bills:
            if any(t in (bill.get("title") or "").lower() for t in terms):
                found.add((CONGRESS, bill["type"].lower(), int(bill["number"])))
        if len(bills) < page_size:
            break
    return found


def collect(conn, fetcher: Fetcher, topic: dict, *, older_topics: list[dict] | None = None) -> dict:
    key = env("CONGRESS_API_KEY")
    stats = {"seen": 0, "inserted": 0}
    if not key:
        log.warning("CONGRESS_API_KEY missing; skipping Congress.gov")
        return stats
    for congress, btype, number in sorted(_discover(fetcher, topic, key)):
        stats["seen"] += 1
        base = f"{API}/bill/{congress}/{btype}/{number}"
        detail = fetcher.get(base, respect_robots=False, params={"api_key": key, "format": "json"})
        if detail is None:
            continue
        bill = detail.json().get("bill", {})
        title = bill.get("title") or f"{btype.upper()}{number}"
        if claimed_by_older(title, None, older_topics):
            stats["older_topic"] = stats.get("older_topic", 0) + 1  # run.py --topic: an older topic owns it
            continue
        latest = bill.get("latestAction", {})
        summary = ""
        summaries = fetcher.get(f"{base}/summaries", respect_robots=False, params={"api_key": key, "format": "json"})
        if summaries is not None:
            items = summaries.json().get("summaries", [])
            if items:
                summary = items[-1].get("text", "")
        full_text = f'{title}\n\nLatest action ({latest.get("actionDate")}): {latest.get("text")}\n\n{summary}'
        slug = next(k for k, v in _TYPES.items() if v == btype)
        url = f"https://www.congress.gov/bill/{congress}th-congress/{slug}/{number}"
        inserted = upsert_official_doc(
            conn, source_id="congress-gov", topic_id=topic["id"], url=url, doc_type=_doc_type(latest.get("text", "")),
            doc_number=f"{btype.upper()}{number}", title=title, full_text=full_text, signed_at=None,
            published_at=parse_dt(latest.get("actionDate")),
        )
        stats["inserted"] += int(inserted)
    log.info("congress: %s", stats)
    return stats
