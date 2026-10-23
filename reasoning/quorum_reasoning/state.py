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


class Evidence(TypedDict):
    quote: str
    document_id: int | None
    official_doc_id: int | None
    independence_group: str
    stance: Stance
    found_by: str  # researcher | verifier | fact_checker
    url: str
    title: str
    is_document: bool  # True when it comes from a signed/adopted official document


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


class StepError(TypedDict):
    node: str
    event_id: str | None
    message: str


class RunState(TypedDict):
    run_id: str
    topic_id: str
    edition_date: str  # YYYY-MM-DD
    dry_run: bool
    documents: list[DocRef]
    events: list[Event]
    claims: dict[str, Claim]
    research_rounds: dict[str, int]  # event_id -> rounds used
    roundup: dict | None
    summary: str
    snapshot: dict | None
    steps: Annotated[list[StepRecord], operator.add]
    errors: Annotated[list[StepError], operator.add]


def initial_state(run_id: str, topic_id: str, edition_date: str, *, dry_run: bool) -> RunState:
    return RunState(
        run_id=run_id,
        topic_id=topic_id,
        edition_date=edition_date,
        dry_run=dry_run,
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
