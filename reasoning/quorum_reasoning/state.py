"""Graph state. Every node returns a partial dict; keys with a reducer (steps, errors) accumulate."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

ClaimStatus = Literal["confirmed", "disputed", "unverified"]
Stance = Literal["supports", "contradicts", "neutral", "statement"]


class DocRef(TypedDict):
    """A document as collection delivers it. No article text: reasoning fetches text at analysis time."""

    id: int
    source_id: str
    source_name: str
    independence_group: str
    kind: str  # agency | outlet | official | military
    flank: str | None  # left | right | center | None
    tier: str | None  # major | minor | None
    url: str
    title: str
    lead: str
    published_at: str  # ISO 8601 UTC
    access_level: int  # 1 full text, 2 headline+lead, 3 coverage only
    wire_origin: str | None
    official: NotRequired[bool]  # True for official_docs rows
    doc_type: NotRequired[str | None]  # law | order | vote | ruling | statement | release
    text: NotRequired[str | None]  # only for official_docs (public domain); never for outlets
    superseded: NotRequired[bool]  # a correction replaced this row: spread and coverage only, never evidence
    from_previous_day: NotRequired[bool]  # loaded from an earlier edition window for research round 2: evidence only, never an event, spread or coverage
    topic_match: NotRequired[str | None]  # title | lead | body — where collection's topic terms matched (documents.topic_match); counted in the trace, never used to filter
    seed_match: NotRequired[str | None]  # official documents of the edition window, Zetaris corpus: title | lead (the abstract) where a term of the run's topic matched (topic_match.official_seed_match); None: nothing matched
    evidence_only: NotRequired[bool]  # official document no topic term matched in title or abstract (or the terms were unavailable): evidence for research round 2 and the fact-checker only, never an event or a roundup item (DECISIONS.md › Sources)
    canonical_url: NotRequired[str | None]  # documents.canonical_url (tracking parameters stripped by collection)
    content_hash: NotRequired[str | None]  # documents.content_hash at collection: sha256(title + "\n" + lead + "\n" + body[:2000])
    fetched_at: NotRequired[str | None]  # when collection fetched the row (ISO 8601 UTC); official_docs.fetched_at for official rows


class Evidence(TypedDict):
    """One passage with a stance. The quote is bound to the text it was cut from (work item A5, 2026-10-24):
    code-point offsets `[char_start, char_end)` into the text named by `access_achieved` (1: the fetched article
    text as `collectors.common.fetch_text` returned it, or the official document's `full_text`; 2: the string
    `title + "\n" + lead`), the collectors' content hash of that text at fetch time, and whether it differs from
    the hash collection stored for the document."""

    quote: str
    document_id: int | None
    official_doc_id: int | None
    source_id: str  # registry id of the publishing source (sources.id)
    independence_group: str
    stance: Stance
    found_by: str  # researcher | verifier | fact_checker
    url: str
    title: str
    is_document: bool  # True when it comes from a signed/adopted official document
    by_headline: NotRequired[bool]  # True when the source is level 2: the passage comes from headline and lead only
    char_start: NotRequired[int | None]  # code-point offset of `quote` in the quoted text, start-inclusive; None when not found verbatim
    char_end: NotRequired[int | None]  # end-exclusive
    content_hash_at_quote: NotRequired[str | None]  # collectors' formula over the quoted text at fetch time
    access_achieved: NotRequired[int | None]  # 1 full text was read, 2 headline and lead only (what the fetch achieved now, not the registry default)
    fetched_at: NotRequired[str | None]  # when the quoted text was fetched (ISO 8601 UTC); collection's fetched_at for text collection stored
    hash_mismatch: NotRequired[bool | None]  # True when content_hash_at_quote differs from documents.content_hash (the page changed since collection); None when no stored hash to compare
    from_previous_day: NotRequired[bool]  # the quoted document was published in an earlier edition window (research round 2 widening)


class Claim(TypedDict):
    id: str
    event_id: str
    text: str
    kind: str  # fact | statement | number | context
    origin_document_id: int | None
    speaker: NotRequired[str | None]  # for statements: who said it, as the extractor read it
    evidence: list[Evidence]
    verifier_status: ClaimStatus | None
    verifier_reason: str
    fact_checker_status: ClaimStatus | None
    fact_checker_reason: str
    final_status: ClaimStatus | None
    adjudication: str
    fact_checker_judged: NotRequired[int]  # stance calls the fact-checker completed for this claim; 0 with failures = unavailable
    fact_check_skipped: NotRequired[bool]  # internal, never exported: the event cannot reach the impact bar, so no blind fact-check (bar gate)
    # the third blind pass (nodes/review_disputed.py), present only on claims the two checkers disagreed on
    review_passes: NotRequired[int]
    reviewer_status: NotRequired[ClaimStatus | None]  # the accepted verdict; None when the pass was invalid or failed
    reviewer_reason: NotRequired[str]
    reviewer_quote: NotRequired[str]  # the decisive words, found in the cited evidence row
    resolved_by: NotRequired[str]  # agreement | reviewer | dispute


class Rubric(TypedDict):
    legal_force: int  # 0 none, 1 official statement, 2 adopted document
    reach: int  # 0 local/unknown, 1 region or sector, 2 national, 3 several countries
    irreversibility: int  # 0 reversible, 1 hard to reverse, 2 irreversible
    confirmation: int  # 0 unverified, 1 one independent source, 2 two or a document — computed, not judged
    total: int
    rationale: dict[str, str]


class ArticleBlock(TypedDict):
    kind: Literal["fact", "context", "statements", "not_confirmed"]
    text: str
    claim_ids: list[str]
    sources: list[dict]  # {title, url, quote_id?}


class Event(TypedDict):
    id: str
    document_ids: list[int]
    headline: str
    standfirst: str
    rubric: Rubric | None
    above_bar: bool
    rank: int | None
    needs_review: bool
    article: list[ArticleBlock]
    drafts: int
    versions: list[dict]  # every draft with the critic's verdict; rejections are kept, not overwritten
    critic_status: str | None  # approved | rejected | None
    critic_notes: str
    framing: dict  # per-cohort labels, coverage counts; filled by `frame`
    review_reason: str  # why `needs_review` is set, empty otherwise


class StepRecord(TypedDict):
    node: str
    iteration: int
    event_id: str | None
    decision: str
    reason: str
    model: str | None
    duration_ms: int
    detail: NotRequired[list[dict]]  # audit rows a decision summarises, e.g. extract's dropped claims (text, reason)


class StepError(TypedDict):
    node: str
    event_id: str | None
    message: str


class RunInput(TypedDict):
    """What starts a run. Studio shows exactly these fields; everything else in RunState is filled by `plan`."""

    topic_id: str  # slug, e.g. russia-ukraine-war
    edition_date: str  # YYYY-MM-DD
    dry_run: NotRequired[bool]  # True: deterministic stand-ins for every model call, no credits
    corpus: NotRequired[Literal["fixture", "zetaris"]]  # where documents come from; default fixture when dry_run, else zetaris
    run_id: NotRequired[str]  # default: <date>-<topic>-1


class RunState(TypedDict):
    run_id: str
    topic_id: str
    edition_date: str  # YYYY-MM-DD
    dry_run: bool  # model axis: stand-ins instead of model calls
    corpus: str  # corpus axis: fixture | zetaris
    documents: list[DocRef]
    events: list[Event]
    claims: dict[str, Claim]
    research_rounds: dict[str, int]  # event_id -> rounds used
    roundup: dict | None
    summary: str
    snapshot: dict | None
    steps: Annotated[list[StepRecord], operator.add]
    errors: Annotated[list[StepError], operator.add]


def run_input(topic_id: str, edition_date: str, *, dry_run: bool, corpus: str | None = None, run_id: str | None = None) -> RunInput:
    inp = RunInput(topic_id=topic_id, edition_date=edition_date, dry_run=dry_run)
    if corpus:
        inp["corpus"] = corpus  # type: ignore[typeddict-item]
    if run_id:
        inp["run_id"] = run_id
    return inp


def initial_state(run_id: str, topic_id: str, edition_date: str, *, dry_run: bool) -> RunState:
    """A full state for tests that call a node directly; the graph itself starts from `run_input`."""
    return RunState(
        run_id=run_id,
        topic_id=topic_id,
        edition_date=edition_date,
        dry_run=dry_run,
        corpus="fixture" if dry_run else "zetaris",
        documents=[],
        events=[],
        claims={},
        research_rounds={},
        roundup=None,
        summary="",
        snapshot=None,
        steps=[],
        errors=[],
    )
