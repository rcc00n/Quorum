"""Writing rules the critic enforces (DECISIONS.md › Stories as articles). Returns violations; the writer fixes only those."""

from __future__ import annotations

import re

from .. import config
from ..state import ArticleBlock, Claim

ORDER = ["fact", "context", "statements", "not_confirmed"]


def _forbidden_words() -> list[str]:
    return [w.lower() for w in config.get("writing", "forbidden_words", [])]


def _attribution_verbs() -> list[str]:
    return [v.lower() for v in config.get("writing", "attribution_verbs", [])]


def check_article(blocks: list[ArticleBlock], claims: dict[str, Claim]) -> list[str]:
    """Each violation is one line: block index, rule, the offending text. Empty list = approved."""
    violations: list[str] = []
    forbidden = _forbidden_words()
    verbs = _attribution_verbs()

    # Order is fixed: facts, context, statements, not confirmed. Missing kinds and repeated kinds are allowed;
    # a block of an earlier kind after a later one is not.
    seen = [b["kind"] for b in blocks]
    unknown = [k for k in seen if k not in ORDER]
    if unknown:
        violations.append(f"order: unknown block kind(s) {unknown}")
    elif seen != sorted(seen, key=ORDER.index):
        violations.append(f"order: blocks must follow {ORDER}, got {seen}")

    for i, b in enumerate(blocks):
        text = b["text"].strip()
        low = text.lower()
        if not text:
            violations.append(f"block {i} ({b['kind']}): empty")
            continue
        for w in forbidden:
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                violations.append(f"block {i} ({b['kind']}): forbidden wording '{w}'")
        if b["kind"] in ("fact", "context"):
            if not b["claim_ids"]:
                violations.append(f"block {i} ({b['kind']}): no claim behind the sentence")
            for cid in b["claim_ids"]:
                c = claims.get(cid)
                if c is None:
                    violations.append(f"block {i} ({b['kind']}): unknown claim {cid}")
                elif c["final_status"] != "confirmed":
                    violations.append(f"block {i} ({b['kind']}): claim {cid} is {c['final_status']}, not confirmed")
            if not b["sources"]:
                violations.append(f"block {i} ({b['kind']}): no source after the sentence")
        if b["kind"] == "statements":
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
            for s in sentences:
                sl = s.lower()
                if sl.startswith("what follows"):
                    continue
                if not any(v in sl for v in verbs):
                    violations.append(f"block {i} (statements): statement without attribution: '{s[:60]}'")
        if b["kind"] == "not_confirmed":
            for cid in b["claim_ids"]:
                c = claims.get(cid)
                if c is not None and c["final_status"] == "confirmed":
                    violations.append(f"block {i} (not_confirmed): claim {cid} is confirmed, does not belong here")
    return violations


def check_text(label: str, text: str) -> list[str]:
    """Forbidden wording in a free-text field (headline, standfirst, roundup line)."""
    low = (text or "").lower()
    return [f"{label}: forbidden wording '{w}'" for w in _forbidden_words() if re.search(r"\b" + re.escape(w) + r"\b", low)]


def check_headline(headline: str) -> list[str]:
    return check_text("headline", headline)
