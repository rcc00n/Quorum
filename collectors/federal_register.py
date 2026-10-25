"""Federal Register collector: presidential documents, rules and notices matching the topic. No key needed.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
Documents are public domain; full text is stored (docs/DECISIONS.md › Sources).
"""
from __future__ import annotations

import logging

from collectors.common import Fetcher, parse_dt, upsert_official_doc

log = logging.getLogger("collectors.federal_register")
API = "https://www.federalregister.gov/api/v1/documents.json"

# DECISION(2026-10-22, Anastasia/Claude; confirmed 2026-10-23 against reasoning rules/confirmation.py): Federal
# Register types map PRESDOCU (executive orders, proclamations, memoranda) -> 'order', RULE (final rules) -> 'law',
# PRORULE (proposed rules) and NOTICE -> 'release'. Why: only adopted instruments establish facts; a proposed rule or
# a notice is the agency's statement. Values are exactly the schema's enum, which reasoning reads verbatim.
# DECISION(2026-10-24, Anastasia/Claude Code): the map is keyed by the labels the API returns in results ("Presidential
# Document", "Rule", "Proposed Rule", "Notice"; upper-cased, spaces removed), with the filter codes kept as aliases.
# Why: documents.json returns the label, not the code (federalregister-api-core: es_entry_search_result.rb#type ->
# entry.rb ENTRY_TYPES); keyed by codes alone, every presidential document fell through to 'release' and could never
# confirm (live 2026-10-24: 41 release + 9 law, 0 order). Rows stored before this fix keep 'release' until the same
# URL is re-collected (upsert_official_doc refreshes doc_type since the same date).
_TYPE_MAP = {"PRESIDENTIALDOCUMENT": "order", "PRESDOCU": "order", "RULE": "law",
             "PROPOSEDRULE": "release", "PRORULE": "release", "NOTICE": "release"}


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
        raw = item.get("raw_text_url")
        if raw:
            body = fetcher.get(raw, respect_robots=False)
            if body is None:
                # DECISION(2026-10-24, Anastasia/Claude Code): when the raw-text fetch fails this pass, skip the document
                # instead of storing the abstract as full_text. Why: ON CONFLICT (url) replaces full_text, so the fallback
                # overwrote a stored full text with the abstract on a transient failure and broke quote offsets; same
                # rule as rss.collect_official_feed. The abstract is used only for documents without a raw_text_url.
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue
            text = body.text
        else:
            text = item.get("abstract") or ""
        if not text:
            stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        inserted = upsert_official_doc(
            conn, source_id="federal-register", topic_id=topic["id"], url=item["html_url"],
            doc_type=_TYPE_MAP.get((item.get("type") or "").upper().replace(" ", ""), "release"),
            doc_number=item.get("document_number"), title=item["title"], full_text=text,
            signed_at=parse_dt(item.get("signing_date")), published_at=parse_dt(item.get("publication_date")),
        )
        stats["inserted"] += int(inserted)
    log.info("federal_register: %s", stats)
    return stats
