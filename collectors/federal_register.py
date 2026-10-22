"""Federal Register collector: presidential documents, rules and notices matching the topic. No key needed.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
Documents are public domain; full text is stored (docs/DECISIONS.md › Sources).
"""
from __future__ import annotations

import logging

from collectors.common import Fetcher, parse_dt, upsert_official_doc

log = logging.getLogger("collectors.federal_register")
API = "https://www.federalregister.gov/api/v1/documents.json"

# DECISION(2026-10-22, Anastasia/Claude): presidential documents map to 'order', rules to 'law', notices to 'release'.
# Why: DECISIONS.md treats an adopted document as fact and an agency statement as a statement; notices are the latter.
_TYPE_MAP = {"PRESDOCU": "order", "RULE": "law", "PRORULE": "release", "NOTICE": "release"}


def collect(conn, fetcher: Fetcher, topic: dict, *, per_page: int = 50) -> dict:
    stats = {"seen": 0, "inserted": 0}
    term = " | ".join(topic["query_terms"])  # FR search supports OR with '|'
    resp = fetcher.get(
        API, respect_robots=False,
        params={"conditions[term]": term, "order": "newest", "per_page": per_page,
                "fields[]": ["document_number", "title", "type", "abstract", "html_url", "raw_text_url",
                              "publication_date", "signing_date", "agencies"]},
    )
    if resp is None:
        return stats
    for item in resp.json().get("results", []):
        stats["seen"] += 1
        text = item.get("abstract") or ""
        raw = item.get("raw_text_url")
        if raw:
            body = fetcher.get(raw, respect_robots=False)
            if body is not None:
                text = body.text
        inserted = upsert_official_doc(
            conn, source_id="federal-register", topic_id=topic["id"], url=item["html_url"],
            doc_type=_TYPE_MAP.get(item.get("type", "").upper().replace(" ", ""), "release"),
            doc_number=item.get("document_number"), title=item["title"], full_text=text,
            signed_at=parse_dt(item.get("signing_date")), published_at=parse_dt(item.get("publication_date")),
        )
        stats["inserted"] += int(inserted)
    log.info("federal_register: %s", stats)
    return stats
