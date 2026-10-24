"""Deterministic stand-ins for every model task, used when QUORUM_DRY_RUN=1 or no model key is configured.

They exist so the graph, its loops and its trace can run without credits. They are not clever and they are
not meant to be: each returns the same shape the real task returns (see prompts/<task>.md). One of them
plants a known violation in the first draft of an article (see `write`) so the critic → writer loop is
exercised on every dry run.
"""

from __future__ import annotations

import re
from typing import Any

from .text import containment, overlap, overlap_coefficient, sentences as _sentences, stem, stems

_SAID = re.compile(r"^(?P<who>.{2,60}?)\s+(?P<verb>said|says|announced|claims|claimed)\s+(?:that\s+)?(?P<what>.+)$", re.IGNORECASE)
_ACCORDING = re.compile(r"^(?P<what>.+?),\s+according to\s+(?P<who>.+)$", re.IGNORECASE)

# A small deed lexicon for the deterministic event-key twin. The live model names the action itself; the
# twin only needs the fixture days' verbs, so stems are enough and additions are free.
_DEEDS = {
    stem(v)
    for v in (
        "sign approve adopt pass impose add announce resume visit strike kill attack sanction order vote "
        "retract withdraw agree meet release publish amend void arrive extend suspend ban seize capture "
        "destroy launch open close reject confirm deny appoint resign deliver ship exchange talk"
    ).split()
}
_NUM = re.compile(r"\d[\d,.]*")


def event_key(p: dict[str, Any]) -> dict[str, Any]:
    """Deterministic twin of the event-key extraction: the deed the title names, entities from the rest.

    The action comes from the title alone, as the prompt instructs the live model ("a document that reports
    two distinct happenings gets the key of the one its title names"); body text cannot buy a different deed.
    """
    joined = " ".join(s for s in (p.get("title") or "", p.get("lead") or "", (p.get("text") or "")[:1500]) if s)
    title = (p.get("title") or "").strip()
    action = sorted(stems(title) & _DEEDS)
    entities = sorted(stems(joined) - _DEEDS)
    return {
        "canonical": title or (joined[:120]),
        "actors": [],
        "action": " ".join(action),
        "object": entities,
        "place": [],
        "date": None,
        "numbers": _NUM.findall(title)[:6],
    }


def _key_sets(side: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    """(action stems, entity stems, every stem incl. title and lead) for one side of a merge question."""
    key = side.get("key") or {}
    fields = " ".join(
        str(x)
        for x in (
            [key.get("canonical") or "", key.get("date") or ""]
            + list(key.get("actors") or [])
            + list(key.get("object") or [])
            + list(key.get("place") or [])
            + list(key.get("numbers") or [])
        )
    )
    action = stems(str(key.get("action") or "")) & _DEEDS  # the key's named deed only; other fields cannot buy one
    entities = stems(fields) - _DEEDS
    full = stems(" ".join([fields, str(key.get("action") or ""), side.get("title") or "", side.get("lead") or ""]))
    return action, entities, full


def merge_confirm(p: dict[str, Any]) -> dict[str, Any]:
    """Twin of the merge question, asymmetric like the recorded fail-safe directions. `pair`/`singleton`
    merge only on the same named deed plus two shared entities, or one side's wording contained in the
    other's (an unmerged pair costs a roundup line). `chain` splits only when the two members share
    nothing at all — no deed, no entity, no containment (a false split weakens real confirmation)."""
    a_act, a_ent, a_full = _key_sets(p.get("a") or {})
    b_act, b_ent, b_full = _key_sets(p.get("b") or {})
    contained = overlap_coefficient(a_full, b_full) >= 0.6
    if p.get("mode") == "chain":
        same = bool(a_act & b_act) or bool(a_ent & b_ent) or contained
    else:
        same = bool(a_act & b_act and len(a_ent & b_ent) >= 2) or contained
    return {"same_event": same, "reason": "dry run: shared deed and entities" if same else "dry run: keys disagree"}


def rubric(p: dict[str, Any]) -> dict[str, Any]:
    titles = " ".join(d.get("title", "") for d in p.get("documents", []))
    low = titles.lower()
    doc_types = {d.get("doc_type") for d in p.get("documents", []) if d.get("official")}
    if doc_types & {"law", "order", "vote", "ruling"}:
        legal, legal_why = 2, "an adopted document is in the corpus"
    elif doc_types & {"statement", "release"}:
        legal, legal_why = 1, "official statement only"
    else:
        legal, legal_why = 0, "no official document"
    if any(k in low for k in ("congress", "senate", "president", "federal", "nationwide", "law", "sanctions", "parliament")):
        reach, reach_why = 2, "national scope in the headlines"
    elif any(k in low for k in ("dead", "killed", "casualt", "displaced", "evacuat")):
        reach, reach_why = 2, "confirmed deaths or mass displacement reach the whole country (rubric rule, 2026-10-24)"
    elif any(k in low for k in ("region", "city", "county", "district")):
        reach, reach_why = 1, "regional scope"
    else:
        reach, reach_why = 1, "scope not stated; regional assumed"
    if any(k in low for k in ("signed", "completed", "killed", "destroyed", "exchange")):
        irr, irr_why = 2, "completed or signed act"
    elif any(k in low for k in ("adopt", "approv", "pass", "amend", "impose")):
        irr, irr_why = 1, "adopted but reversible by a later act"
    else:
        irr, irr_why = 0, "announcement or talks"
    return {
        "legal_force": legal,
        "reach": reach,
        "irreversibility": irr,
        "rationale": {"legal_force": legal_why, "reach": reach_why, "irreversibility": irr_why},
    }


def _claim_from_sentence(sentence: str, doc: dict[str, Any]) -> dict[str, Any]:
    text = sentence.strip().rstrip(".")
    if doc.get("official") and doc.get("doc_type") in ("statement", "release"):
        return {"text": text, "kind": "statement", "speaker": doc.get("source"), "origin_document_id": doc.get("id")}
    m = _SAID.match(text)
    if m:
        return {"text": m.group("what").strip(), "kind": "statement", "speaker": m.group("who").strip(), "origin_document_id": doc.get("id")}
    m = _ACCORDING.match(text)
    if m:
        return {"text": m.group("what").strip(), "kind": "statement", "speaker": m.group("who").strip(), "origin_document_id": doc.get("id")}
    kind = "number" if re.search(r"\d", text) else "fact"
    return {"text": text, "kind": kind, "speaker": None, "origin_document_id": doc.get("id")}


def extract_claims(p: dict[str, Any]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for d in p.get("documents", [])[:8]:
        if d.get("official") and d.get("text"):
            for sent in _sentences(d["text"])[:3]:
                claims.append(_claim_from_sentence(sent, d))
            continue
        title = (d.get("title") or "").strip()
        if title:
            claims.append(_claim_from_sentence(title, d))
        lead = (d.get("lead") or "").strip()
        if lead:
            claims.append(_claim_from_sentence(_sentences(lead)[0], d))
    # drop near-duplicates, keeping the first (documents arrive in publication order)
    seen: list[str] = []
    out = []
    for c in claims:
        if any(overlap(c["text"], s) > 0.6 for s in seen):
            continue
        seen.append(c["text"])
        out.append(c)
    return {"claims": out[:10]}


def stance(p: dict[str, Any]) -> dict[str, Any]:
    claim, passage = p.get("claim", ""), p.get("passage", "")
    share = containment(claim, passage)
    low = passage.lower()
    # The fact-checker stand-in is stricter than the researcher's, the way a second model with a
    # "find reasons this could be wrong" prompt would be; that is what produces disagreements in a dry run.
    needed = 0.6 if p.get("role") == "fact_checker" else 0.5
    if share >= needed:
        if re.search(r"\b(not|no|denies|denied|contradict|has not|did not)\b", low) and not re.search(r"\b(not|no)\b", claim.lower()):
            return {"stance": "contradicts", "reason": f"dry run: {share:.0%} of the claim's words with a negation"}
        if p.get("source_kind") == "official" and p.get("doc_type") in ("statement", "release"):
            return {"stance": "statement", "reason": "dry run: official statement wording"}
        return {"stance": "supports", "reason": f"dry run: {share:.0%} of the claim's words in the passage"}
    return {"stance": "neutral", "reason": f"dry run: {share:.0%} of the claim's words in the passage"}


def frame(p: dict[str, Any]) -> dict[str, Any]:
    docs = p.get("documents", [])
    first = (docs[0].get("title") if docs else "") or ""
    flank = p.get("flank") or "center"
    words = " ".join(first.split()[:8])
    label = {"left": "a commitment", "right": "a cost", "center": "a procedural step"}.get(flank, "a procedural step")
    return {
        "highlights": words,
        "omits": "",
        "wording": first.split()[0].lower() if first else "",
        "interpretation_label": label,
    }


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return (text[0].upper() + text[1:] + ".") if text else ""


def write(p: dict[str, Any]) -> dict[str, Any]:
    draft = int(p.get("draft", 1))
    blocks: list[dict[str, Any]] = []
    confirmed = p.get("confirmed", [])
    for c in confirmed:
        blocks.append({"kind": "fact", "text": _sentence(c["text"]), "claim_ids": [c["id"]], "sources": c.get("sources", [])})
    for c in p.get("context", []):
        blocks.append({"kind": "context", "text": _sentence(c["text"]), "claim_ids": [c["id"]], "sources": c.get("sources", [])})
    statements = p.get("statements", [])
    if statements:
        sentences = ["What follows are statements, not confirmed facts."]
        for s in statements:
            who = s.get("who") or "The source"
            what = s["text"].strip().rstrip(".")
            sentences.append(f"{who} said {what[0].lower() + what[1:]}.")
        blocks.append(
            {
                "kind": "statements",
                "text": " ".join(sentences),
                "claim_ids": [s["id"] for s in statements],
                "sources": [src for s in statements for src in s.get("sources", [])],
            }
        )
    open_items = p.get("not_confirmed", [])
    if open_items:
        text = "Not confirmed. " + " ".join(
            _sentence(o["text"]).rstrip(".") + " — " + (o.get("why") or "no independent confirmation yet") + "." for o in open_items
        )
        blocks.append({"kind": "not_confirmed", "text": text, "claim_ids": [o["id"] for o in open_items], "sources": []})
    headline = p.get("headline", "")
    standfirst = " ".join(_sentence(c["text"]) for c in confirmed[:2]) or "No claim of this event is confirmed yet."
    if draft == 1:
        # Planted violation so every dry run exercises the critic -> writer loop once.
        standfirst = "A sweeping change. " + standfirst
    return {"headline": headline, "standfirst": standfirst, "blocks": blocks}


def roundup_line(p: dict[str, Any]) -> dict[str, Any]:
    title = (p.get("headline") or "").rstrip(".")
    lead = _sentences(p.get("lead") or "")
    first = lead[0].rstrip(".") if lead else ""
    line = title if not first or overlap(title, first) > 0.6 else f"{title}; {first[0].lower() + first[1:]}"
    return {"line": line + "."}


def summary(p: dict[str, Any]) -> dict[str, Any]:
    n_above, n_total = p.get("above_bar", 0), p.get("events", 0)
    if n_above == 0:
        s = f"No story crossed the bar today out of {n_total} events. The roundup carries all of them."
    elif n_above == 1:
        s = f"One of {n_total} events crossed the bar today: {(p.get('headlines') or ['(untitled)'])[0]}."
    else:
        s = f"{n_above} of {n_total} events crossed the bar today."
    review = p.get("needs_review", 0)
    if review:
        s += f" {review} flagged for review."
    missing = p.get("sources_missing") or []
    if missing:
        s += f" Sources missing today: {', '.join(missing)}."
    return {"summary": s}
