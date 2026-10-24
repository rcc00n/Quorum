"""cluster: group the day's documents into events, by structured event keys.

For every document the fast lane extracts one event key (canonical sentence, actors, action, object, place,
date, numbers) from title + lead + the first ~1500 characters of text when the access level allows, from
title + lead for level 2, from the title alone for level 3. Code then groups by key overlap: near-identical
keys merge with no model call; keys sharing no significant entity or action stay apart with no model call;
everything in between is a model pair question. A second pass offers every document left alone to the model
against each existing event's key. For every event with three or more documents, code finds the
least-similar pair inside it and asks the model: "no" removes the weakest link and re-checks the two halves;
"unsure" keeps the event together and marks it in the trace. Fail-safe directions: a pair or singleton
question merges only on a JSON boolean true (a false split only weakens confirmation); a chain question
splits only on a JSON boolean false (a false merge lends foreign evidence, but an unsure answer must not
shred a real event). Events form only from the edition window's documents; earlier days supply evidence in
research round 2 and context, never events.

DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): event keys replace title-token cosine as the grouping
signal; stemming is a filter aid, not the judge. Why: exact title words fragment real days — one strike's
NPR/CNN/Breitbart titles share ~2 tokens (review finding C2), which made cross-outlet confirmation
structurally unreachable, while transitive title chains could weld unrelated documents into one event
(finding A7). Embeddings (nvidia/nemotron-3-embed-1b) stay a later option for the overlap measure if the
first live days show the filter still misses pairs. The superseded titles-only decision is kept in
reasoning/README.md › Decisions.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .. import config, ids, llm, untrusted
from ..state import DocRef, Event, RunState, StepError
from ..text import overlap_coefficient, stems
from ..tools.fetch_text import fetch_text
from ..trace import finish, step

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "the a an and or of to in on for by with at from as is are was were be been into that this it its after before over under say says said".split()
)

# Engineering constants, not product thresholds: they bound payload sizes and list lengths.
KEY_TEXT_CHARS = 1500  # of fetched text, level 1 and official documents only
KEY_LIST_MAX = 6
KEY_FIELD_CHARS = 80


def _terms(doc: DocRef) -> set[str]:
    """Title word set (legacy helper; the grouping signal is the event key now)."""
    return {t for t in _WORD.findall(doc["title"].lower()) if t not in _STOP and len(t) > 1}


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


class _UF:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> None:
        self.p[self.find(i)] = self.find(j)


def _clip_list(value: Any) -> list[str]:
    out = []
    for v in value if isinstance(value, list) else []:
        if isinstance(v, (str, int, float)):
            s = untrusted.clip(str(v), KEY_FIELD_CHARS).strip()
            if s:
                out.append(s)
        if len(out) >= KEY_LIST_MAX:
            break
    return out


def _fallback_key(doc: DocRef) -> dict[str, Any]:
    """A key built by code from the title alone: the fail-safe when the model's key is unusable."""
    return {"canonical": doc["title"], "actors": [], "action": "", "object": sorted(stems(doc["title"])), "place": [], "date": None, "numbers": []}


def _valid_key(ans: Any, doc: DocRef) -> dict[str, Any]:
    if not isinstance(ans, dict):
        return _fallback_key(doc)
    key = {
        "canonical": untrusted.clip(str(ans.get("canonical") or doc["title"]), untrusted.CAP_TITLE),
        "actors": _clip_list(ans.get("actors")),
        "action": untrusted.clip(str(ans.get("action") or ""), KEY_FIELD_CHARS),
        "object": _clip_list(ans.get("object")),
        "place": _clip_list(ans.get("place")),
        "date": untrusted.clip(str(ans.get("date")), KEY_FIELD_CHARS) if ans.get("date") else None,
        "numbers": _clip_list(ans.get("numbers")),
    }
    if not (key["actors"] or key["action"] or key["object"]):
        return _fallback_key(doc)
    return key


def _key_payload(doc: DocRef, *, dry_run: bool) -> dict[str, Any]:
    text = ""
    if doc["access_level"] == 1 or doc.get("official"):
        text = (fetch_text(doc, dry_run=dry_run) or "")[:KEY_TEXT_CHARS]
    return {
        "id": doc["id"],
        "title": untrusted.clip(doc["title"], untrusted.CAP_TITLE),
        "lead": untrusted.clip(doc["lead"], untrusted.CAP_LEAD) if doc["access_level"] <= 2 else "",
        "text": text,
        "source": doc["source_name"],
        "official": bool(doc.get("official")),
        "doc_type": doc.get("doc_type"),
    }


def _significant(key: dict[str, Any]) -> set[str]:
    """Stemmed tokens of the key's entity and action fields: the floor test and the overlap measure."""
    fields = " ".join([key.get("action") or ""] + key["actors"] + key["object"] + key["place"] + key["numbers"])
    return stems(fields)


def _side(doc: DocRef, key: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "title": untrusted.clip(doc["title"], untrusted.CAP_TITLE),
        "lead": untrusted.clip(doc["lead"], untrusted.CAP_LEAD),
        "published_at": doc["published_at"],
    }


def _event_side(members: list[DocRef], keys: dict[int, dict[str, Any]]) -> dict[str, Any]:
    rep = _representative(members)
    return {
        "key": keys[rep["id"]],
        "title": _headline(members),
        "lead": untrusted.clip(next((d["lead"] for d in members if d["lead"]), ""), untrusted.CAP_LEAD),
        "published_at": rep["published_at"],
        "member_titles": [untrusted.clip(d["title"], untrusted.CAP_TITLE) for d in members[:8]],
    }


def _representative(members: list[DocRef]) -> DocRef:
    order = {"agency": 0, "official": 1, "outlet": 2, "military": 3}
    return sorted(members, key=lambda d: (order.get(d["kind"], 9), d["published_at"]))[0]


def _headline(members: list[DocRef]) -> str:
    return _representative(members)["title"]


def run(state: RunState) -> dict:
    # Events form only from the edition window's documents, and a supersede chain (one URL re-fetched with a changed
    # hash) is one publication represented by its newest row: superseded versions stay in the state for the trace but
    # are not clustered, counted or listed (DECISIONS.md log 2026-10-24, chain-once rule).
    docs = [d for d in state["documents"] if not d.get("from_previous_day") and not d.get("superseded")]
    folded = sum(1 for d in state["documents"] if d.get("superseded") and not d.get("from_previous_day"))
    merge_hi = float(config.get("clustering", "key_merge_overlap", 0.75))
    budget = int(config.get("clustering", "merge_questions_max", 80))
    errors: list[StepError] = []
    asked = {"pair": 0, "singleton": 0, "chain": 0}
    merged = {"auto": 0, "pair": 0, "singleton": 0}
    splits = 0
    unsure = 0

    def ask(mode: str, a: dict[str, Any], b: dict[str, Any]) -> Any:
        """One merge question. Returns True, False or None (unsure / failed / budget spent)."""
        nonlocal budget
        if budget <= 0:
            return None
        budget -= 1
        asked[mode] += 1
        try:
            ans = llm.json_task("merge_confirm", {"mode": mode, "a": a, "b": b}, dry_run=state["dry_run"])
        except Exception as exc:  # noqa: BLE001 — a failed call takes the fail-safe direction
            errors.append(StepError(node="cluster", event_id=None, message=str(exc)[:300]))
            return None
        same = ans.get("same_event")
        return same if isinstance(same, bool) else None  # "unsure" and any echoed string are None

    with step(state, "cluster", model=llm.model_name()) as s:
        keys: dict[int, dict[str, Any]] = {}
        for d in docs:
            try:
                keys[d["id"]] = _valid_key(llm.json_task("event_key", _key_payload(d, dry_run=state["dry_run"]), dry_run=state["dry_run"]), d)
            except Exception as exc:  # noqa: BLE001 — a document with no key still takes part via its title
                errors.append(StepError(node="cluster", event_id=None, message=str(exc)[:300]))
                keys[d["id"]] = _fallback_key(d)
        sig = {d["id"]: _significant(keys[d["id"]]) or stems(d["title"]) for d in docs}
        full = {d["id"]: sig[d["id"]] | stems(keys[d["id"]]["canonical"]) | stems(d["title"]) | stems(d["lead"]) for d in docs}

        uf = _UF(len(docs))
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                a, b = docs[i]["id"], docs[j]["id"]
                if not (sig[a] & sig[b]):
                    continue  # no shared significant entity or action: apart, no model call
                if overlap_coefficient(full[a], full[b]) >= merge_hi:
                    if uf.find(i) != uf.find(j):
                        merged["auto"] += 1
                        uf.union(i, j)
                    continue
                if uf.find(i) == uf.find(j):
                    continue
                if ask("pair", _side(docs[i], keys[a]), _side(docs[j], keys[b])) is True:
                    merged["pair"] += 1
                    uf.union(i, j)

        groups: dict[int, list[int]] = {}
        for idx in range(len(docs)):
            groups.setdefault(uf.find(idx), []).append(idx)
        clusters: list[list[int]] = sorted(groups.values(), key=lambda g: (-len(g), docs[g[0]]["id"]))

        # Second pass: every document left alone is offered against each existing multi-document event.
        for cl in [c for c in clusters if len(c) == 1]:
            lone = docs[cl[0]]
            candidates = [c for c in clusters if len(c) >= 2 and sig[lone["id"]] & set().union(*(sig[docs[m]["id"]] for m in c))]
            candidates.sort(key=lambda c: (-len(sig[lone["id"]] & set().union(*(sig[docs[m]["id"]] for m in c))), docs[c[0]]["id"]))
            for cand in candidates:
                members = [docs[m] for m in cand]
                if ask("singleton", _side(lone, keys[lone["id"]]), _event_side(members, keys)) is True:
                    merged["singleton"] += 1
                    cand.extend(cl)
                    clusters.remove(cl)
                    break

        # Chain check: the least-similar pair inside every 3+ event must be a confirmed "same event".
        worklist = [c for c in clusters if len(c) >= 3]
        chain_notes: list[str] = []
        while worklist:
            cl = worklist.pop()
            pairs = [(m, n) for x, m in enumerate(cl) for n in cl[x + 1 :]]
            m, n = min(pairs, key=lambda p: (overlap_coefficient(full[docs[p[0]]["id"]], full[docs[p[1]]["id"]]), docs[p[0]]["id"], docs[p[1]]["id"]))
            verdict = ask("chain", _side(docs[m], keys[docs[m]["id"]]), _side(docs[n], keys[docs[n]["id"]]))
            if verdict is False:
                splits += 1
                half_a, half_b = [m], [n]
                for other in cl:
                    if other in (m, n):
                        continue
                    oid = docs[other]["id"]
                    ca = overlap_coefficient(full[oid], full[docs[m]["id"]])
                    cb = overlap_coefficient(full[oid], full[docs[n]["id"]])
                    (half_a if ca >= cb else half_b).append(other)
                clusters.remove(cl)
                clusters.extend([half_a, half_b])
                worklist.extend([h for h in (half_a, half_b) if len(h) >= 3])
            elif verdict is None:
                unsure += 1
                chain_notes.append(f"kept together unconfirmed: {sorted(docs[i]['id'] for i in cl)}")

        events: list[Event] = []
        for cl in clusters:
            members = sorted((docs[i] for i in cl), key=lambda d: d["published_at"])
            events.append(
                Event(
                    id=ids.event_id(state["topic_id"], state["edition_date"], [d["id"] for d in members]),
                    document_ids=[d["id"] for d in members],
                    headline=_headline(members),
                    standfirst="",
                    rubric=None,
                    above_bar=False,
                    rank=None,
                    needs_review=False,
                    article=[],
                    drafts=0,
                    versions=[],
                    critic_status=None,
                    critic_notes="",
                    framing={},
                    review_reason="",
                )
            )
        events.sort(key=lambda e: -len(e["document_ids"]))
        previous = len(state["documents"]) - len(docs) - folded
        s.decision = (
            f"{len(events)} events from {len(docs)} documents"
            + (f" ({previous} earlier-day documents held for evidence only)" if previous else "")
            + (f" ({folded} superseded versions folded into their chains' newest rows)" if folded else "")
            + f"; {merged['auto']} key merges in code, "
            f"model: {asked['pair']} pair / {asked['singleton']} singleton / {asked['chain']} chain questions, "
            f"{merged['pair'] + merged['singleton']} merged, {splits} split, {unsure} kept unconfirmed"
        )
        s.reason = "event keys from the fast lane; code buckets by stemmed key overlap; the model answers only the in-between" + (
            "; " + "; ".join(chain_notes) if chain_notes else ""
        )
    return {"events": events, "steps": [finish(state, s)], "errors": errors}
