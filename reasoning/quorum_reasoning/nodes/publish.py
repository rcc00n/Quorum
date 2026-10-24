"""publish: the snapshot of docs/ARCHITECTURE.md § 8 for one topic and edition day, plus the topic summary.

The snapshot is built from state only; storing and versioning it (analysis.snapshots) is the store's job
and is not part of this node. `status` is "partial" when any node recorded an error, "empty" when no story
crossed the bar, "ok" otherwise. The adapter must not turn a failed pull into an empty edition.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config, llm, untrusted
from ..state import Claim, Event, RunState, StepError
from ..tools.corpus import _edition_window, fixture_name
from ..trace import finish, step

SCHEMA_VERSION = "1.0"
EDITION_TZ = "America/New_York"
PUBLISH_LOCAL_TIME = time(8, 0)  # DECISIONS › Demo: cut at 05:30, out by 08:00 local


def envelope(state: RunState) -> dict:
    """Timing and provenance of the edition, for the portal's freshness and labelling (ARCHITECTURE.md § 8).

    `expires_at` is a hint, not a promise: the next edition of the topic is due at 08:00 local the following
    day; until a newer version or edition arrives the snapshot is current, after that the adapter may call it
    stale. `provenance.fictional` is true whenever the corpus is a fixture: such a snapshot is demo data and
    the portal shows it as such.
    """
    start, end = _edition_window(state["edition_date"])
    now = datetime.now(timezone.utc).replace(microsecond=0)
    tz = ZoneInfo(EDITION_TZ)
    next_day = date.fromisoformat(state["edition_date"]) + timedelta(days=1)
    expires = datetime.combine(next_day, PUBLISH_LOCAL_TIME, tz).astimezone(timezone.utc)
    fictional = state["corpus"] != "zetaris"
    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "published_at": None,  # set by the store when a version is published
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "edition_timezone": EDITION_TZ,
        "window": {"start": start, "end": end},
        "provenance": {
            "corpus": state["corpus"] + (f":{fixture_name()}" if fictional else ""),
            "model": "stand-ins" if llm.is_dry_run(state["dry_run"]) else llm.model_name(),
            "fact_checker_model": "stand-ins" if llm.is_dry_run(state["dry_run"]) else llm.model_name("fact_checker"),  # model_name itself says stand-ins when QUORUM_DRY_RUN is set
            "fictional": fictional,
            # what actually answered, counted from the responses — the evidence that Nemotron powered the run
            "model_calls": len(llm.calls),
            "answered_by": llm.served_counts(),
            "model_errors": llm.error_count(),  # transport failures and replies without JSON alike
        },
    }


def reading_minutes(e: Event) -> int:
    words = len(e["standfirst"].split()) + sum(len(b["text"].split()) for b in e["article"])
    return max(1, math.ceil(words / 200))


def claim_view(c: Claim) -> dict:
    return {
        "id": c["id"],
        "text": c["text"],
        "kind": c["kind"],
        "speaker": c.get("speaker"),
        "status": c["final_status"],
        "verifier": c["verifier_status"],
        "fact_checker": c["fact_checker_status"],
        "reason": c["adjudication"] if (c["final_status"] == "disputed" or c.get("resolved_by") == "reviewer") else c["verifier_reason"],
        # the third blind pass (decided 2026-10-24): present on every claim so the page can show all three verdicts
        "reviewer_status": c.get("reviewer_status"),
        "reviewer_reason": c.get("reviewer_reason", ""),
        "reviewer_quote": c.get("reviewer_quote", ""),
        "resolved_by": c.get("resolved_by", "agreement" if c["verifier_status"] == c["fact_checker_status"] else "dispute"),
        "evidence": [
            {
                "stance": ev["stance"],
                "quote": ev["quote"],
                "title": ev["title"],
                "url": ev["url"],
                "independence_group": ev["independence_group"],
                "found_by": ev["found_by"],
                "is_document": ev["is_document"],
                "by_headline": bool(ev.get("by_headline")),
                # the collectors' own ids and the quote binding (A5): the portal can resolve the registry row and
                # verify the quote against the same text later
                "source_id": ev.get("source_id"),
                "document_id": ev["document_id"],
                "official_doc_id": ev["official_doc_id"],
                "char_start": ev.get("char_start"),
                "char_end": ev.get("char_end"),
                "content_hash_at_quote": ev.get("content_hash_at_quote"),
                "access_achieved": ev.get("access_achieved"),
                "fetched_at": ev.get("fetched_at"),
                "hash_mismatch": ev.get("hash_mismatch"),
                "from_previous_day": bool(ev.get("from_previous_day")),
            }
            for ev in c["evidence"]
        ],
    }


def story_view(state: RunState, e: Event) -> dict:
    claims = [c for c in state["claims"].values() if c["event_id"] == e["id"]]
    by_id = {d["id"]: d for d in state["documents"]}
    return {
        "event_id": e["id"],
        "rank": e["rank"],
        "headline": e["headline"],
        "standfirst": e["standfirst"],
        "reading_minutes": reading_minutes(e),
        "rubric": e["rubric"],
        "photo": None,  # photo tool not built yet; see docs/DECISIONS.md › Stories as articles for the licence rule
        "article": e["article"],
        "claims": [claim_view(c) for c in claims],
        "spectrum": e["framing"],
        "sources": [{"title": by_id[i]["source_name"], "url": by_id[i]["url"]} for i in e["document_ids"] if i in by_id],
        "needs_review": e["needs_review"],
        "review_reason": e["review_reason"],
        "critic_notes": e["critic_notes"],
        "drafts": e["drafts"],
        "trace_ref": f"runs/{state['run_id']}/events/{e['id']}",
    }


_NO_STORY = re.compile(r"\bno (?:story|stories|event|events)\b.{0,40}?\b(?:crossed|cleared|passed|made|met)\b", re.IGNORECASE)
_NUMBER_WORDS = {"zero": 0, "no": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_COUNT_CROSSED = re.compile(r"\b(\d+|zero|none|one|two|three|four|five|six|seven|eight|nine|ten)\b(?: of \d+)?(?: \w+){0,3}? (?:crossed|cleared|passed|made it over|met) the bar", re.IGNORECASE)
_STORY_WORDS = {"story", "stories", "event", "events"}


def summary_contradiction(summary: str, above_bar: int) -> str | None:
    """Why a summary contradicts the run's own count of stories above the bar, or None when it agrees.

    Checked in code because the model's text is the one line a reader sees first: the first live fixture run
    produced "one story crossed the bar" and "no story crossed the bar" in one summary (Vadim's finding,
    NVIDIA-FIRST-01, snapshot 8f86e67c…9017). Two checks: the "no story crossed the bar" phrase may appear only
    on a zero day, and every "<N> ... crossed the bar" count must equal the real count. Anything else in the
    text is the model's to say.
    """
    text = summary or ""
    if _NO_STORY.search(text) and above_bar > 0:
        return f"says no story crossed the bar, but {above_bar} did"
    for m in _COUNT_CROSSED.finditer(text):
        raw = m.group(1).lower()
        n = _NUMBER_WORDS.get(raw)
        if n is None:
            n = int(raw)
        if n != above_bar:
            return f"says {raw} crossed the bar, but {above_bar} did"
    return None


def fallback_summary(events: int, above_bar: int, needs_review: int) -> str:
    """Code-built summary used when the model's is missing or contradicts the counts; marked `summary_source: fallback`."""
    if above_bar == 0:
        text = f"No story crossed the bar today out of {events} events. The roundup carries the day."
    elif above_bar == 1:
        text = f"One story crossed the bar today out of {events} events."
    else:
        text = f"{above_bar} stories crossed the bar today out of {events} events."
    if needs_review:
        text += f" {needs_review} event(s) flagged for review."
    return text


def run(state: RunState) -> dict:
    stories = sorted((e for e in state["events"] if e["above_bar"]), key=lambda e: e["rank"] or 0)
    with step(state, "publish", model=llm.model_name()) as s:
        n_review = sum(1 for e in state["events"] if e["needs_review"])
        payload = {
            "topic_id": state["topic_id"],
            "edition_date": state["edition_date"],
            "events": len(state["events"]),
            "above_bar": len(stories),
            "above_bar_case": "zero" if not stories else ("one" if len(stories) == 1 else "several"),
            "needs_review": n_review,
            "headlines": [untrusted.clip(e["headline"], untrusted.CAP_HEADLINE) for e in stories],
            "sources_missing": [],
        }
        summary_source = "model"
        summary_errors: list[StepError] = []
        try:
            summary = untrusted.clip(llm.json_task("summary", payload, dry_run=state["dry_run"]).get("summary", ""), untrusted.CAP_SUMMARY)
            problem = summary_contradiction(summary, len(stories)) or (None if summary.strip() else "empty summary")
            if problem:
                summary_errors.append(StepError(node="publish", event_id=None, message=f"summary rejected: {problem}; fallback text used"))
                s.reason = f"model summary rejected: {problem}; fallback text"
                summary, summary_source = fallback_summary(len(state["events"]), len(stories), n_review), "fallback"
        except Exception as exc:  # noqa: BLE001
            summary_errors.append(StepError(node="publish", event_id=None, message=f"summary model call failed: {str(exc)[:200]}; fallback text used"))
            s.reason = f"summary model call failed: {str(exc)[:120]}; fallback text"
            summary, summary_source = fallback_summary(len(state["events"]), len(stories), n_review), "fallback"
        errors = list(state.get("errors", [])) + summary_errors
        status = "partial" if errors else ("empty" if not stories else "ok")
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "topic_id": state["topic_id"],
            "edition_date": state["edition_date"],
            "run_id": state["run_id"],
            "version": 1,  # the store assigns the real version on insert
            "status": status,
            **envelope(state),
            "bar": {"threshold": config.get("impact_bar", "threshold", 6), "confirmation_min": config.get("impact_bar", "confirmation_min", 1)},
            "summary": summary,
            "summary_source": summary_source,  # "model", or "fallback" when the model's text failed or contradicted the counts (then `errors` says so)
            "sources_missing": [],  # filled once plan can compare the sources table with the day's corpus
            "stories": [story_view(state, e) for e in stories],
            "roundup": state["roundup"] or {"empty_day": not stories, "count": 0, "groups": []},
            "errors": list(errors),
            "trace": list(state.get("steps", [])) + [],
        }
        s.decision = f"snapshot {status}: {len(stories)} stories, roundup of {snapshot['roundup']['count']}"
        s.reason = s.reason or "built from state; the store versions it"
    rec = finish(state, s)
    snapshot["trace"].append(rec)
    return {"snapshot": snapshot, "summary": summary, "steps": [rec], "errors": summary_errors}
