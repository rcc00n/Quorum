"""Stable identifiers. A rerun of the same day produces the same ids when the inputs are the same."""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


def _h(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def event_id(topic_id: str, edition_date: str, document_ids: list[int]) -> str:
    return _h(topic_id, edition_date, ",".join(str(i) for i in sorted(document_ids)))


def claim_id(event: str, text: str) -> str:
    norm = _WS.sub(" ", text.strip().lower().rstrip("."))
    return _h(event, norm)


def run_id(topic_id: str, edition_date: str, attempt: int = 1) -> str:
    return f"{edition_date}-{topic_id}-{attempt}"
