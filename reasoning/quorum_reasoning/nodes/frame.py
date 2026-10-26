"""frame: how each outlet frames a story above the bar, plus cohort coverage counts.

The model labels one outlet's document at a time (highlights, omits, wording, interpretation label). Cohort
shares are counted in code from the day's corpus: for each cohort, how many of its sources covered the event
out of how many published anything on the topic today. Cohorts follow DECISIONS.md › Spectrum ratings and
cohorts: major/minor × left/right, plus center; agencies and official sources are not a cohort. The model's
labels are untrusted free text built from untrusted titles and leads: they are bounded before they reach the
snapshot.

Readings (flag `[frame] readings` in config/reasoning.toml; DECISIONS.md › Stories as articles, "Across the
spectrum"): with the flag on, the one call per outlet becomes `frame_reading`. It returns the same four labels plus
sentences on how the outlet interpreted the fact (direction, judgement, cause, why, next), each with a verbatim quote
that code finds in the text the run read for that document (tools.fetch_text.fetch_result), as it finds any words the
sentence itself puts in quotation marks; a sentence whose quote or quotation fails is dropped and its question is
listed as unanswered. A flank with two or more outlet readings gets one `frame_flank_reading` call, whose sentences
may only reuse those quotes and describe only the outlet whose quote each carries, or what the outlets share. The
result is the optional `spectrum.readings` list; every other spectrum field keeps its shape. With the flag off the
node makes the same calls (task, prompt, payload) and writes the same output as before the feature.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable

from .. import config, llm, untrusted
from ..state import DocRef, RunState, StepError
from ..tools.fetch_text import FetchResult, fetch_result, find_quote
from ..trace import finish, step
from .research import EVIDENCE_QUOTE_CAP

COHORTS = ("major_left", "minor_left", "major_right", "minor_right", "center")

QUESTIONS = ("direction", "judgement", "cause", "why", "next")  # the paragraph's order (DECISIONS.md › Stories as articles)
FLANKS = ("left", "right", "center")  # the order of spectrum.readings
LANES = ("default", "fact_checker", "reviewer")  # the lanes llm._route knows

# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a frame_reading call carries the article text the run read
# (fetch_result's `text`), clipped to READING_TEXT_CAP = 6000 characters (untrusted.clip). Why: about 1 000 words, so
# a typical news article is read whole (cause, why and next are usually stated after the opening paragraphs, which
# extract's 4 000-character CAP_TEXT can cut), at roughly 1 500 input tokens per outlet; the providers' limits are
# per request, not per token, so the cap costs latency only. A quote is still checked against the whole fetched text.
READING_TEXT_CAP = 6000
READING_SENTENCE_CAP = 300  # characters of one reading sentence (untrusted.clip); a paragraph holds at most five
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a reading quote needs at least READING_QUOTE_MIN_WORDS words and at
# most EVIDENCE_QUOTE_CAP characters (the evidence quote cap); outside that the sentence is dropped, never clipped. Why:
# a one- or two-word run ("the bill") is verbatim in almost any article and grounds nothing, and a clipped quote
# would no longer be the article's words.
READING_QUOTE_MIN_WORDS = 3
DETAIL_ROWS_MAX = 12  # trace detail rows per step the portal parser accepts (backend/portal/reasoning_preview.py)

# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a reading sentence written about readers or about what the outlet
# wants them to think ("readers leave thinking …", "the outlet wants readers to …", "sets out to convey …") is dropped,
# whatever question it answers. Why: Yelysei's rule for the direction sentence: a neutral statement written directly;
# the same phrasing in a later sentence is the same fault, and code can check it where a prompt can only ask.
# Review round 2: widened to an intention (a verb such as wants/aims/seeks/tries/sets out to, "is designed/meant to",
# or "the goal/aim/purpose … is") + "to" + a framing verb, and to "leaves/gives/creates the impression". Convey,
# persuade, convince, portray and depict always count; show, make, present, suggest, frame, paint, cast, position and
# spin count when "that" follows at once or "as"/"look"/"seem"/"appear"/"sound" within five words, so a rule's or an
# actor's aim ("the rule aims to make screening faster") still passes. The bare readers/viewers/listeners/audiences
# match stays broad: narrowing it to grammatical roles would let "Readers of the outlet see …" through, and an
# over-match costs one sentence, which then counts as unanswered.
_W = r"[\w'’-]+"
_INTENT = (
    r"(?:wants?|wanted|aims?|aimed|seeks?|sought|tries|tried|try|trying|intends?|intended|hopes?|hoped|attempts?|attempted"
    r"|strives?|strove|sets? out|setting out|(?:is|are|was|were) (?:designed|meant|intended|written)"
    rf"|(?:goal|aim|purpose|intent|intention|objective)s? (?:{_W} ){{0,4}}?(?:is|are|was|were))"
)
_READER_META = re.compile(
    r"\b(?:readers?|viewers?|listeners?|audiences?)\b"
    rf"|\bleaves? (?:{_W} ){{0,2}}(?:thinking|believing|feeling|with the (?:impression|sense))\b"
    rf"|\b(?:leaves?|leaving|left|gives?|gave|giving|creates?|created|creating) (?:{_W} ){{0,2}}?(?:the|an) impression\b"
    rf"|\b{_INTENT} to (?:convey|persuade|convince|portray|depict)\b"
    rf"|\b{_INTENT} to (?:show|make|present|suggest|frame|paint|cast|position|spin)\b"
    rf"(?: that\b| (?:{_W} ){{0,5}}?(?:as|look|looks|seem|seems|appear|appears|sound|sounds)\b)"
    r"|\bwants? (?:you|people|the public)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"\w+")


def cohort_of(doc: DocRef) -> str | None:
    if doc["kind"] != "outlet":
        return None
    flank, tier = doc.get("flank"), doc.get("tier")
    if flank in ("left", "right"):
        return f"{tier or 'minor'}_{flank}"
    return "center"


def coverage(all_docs: list[DocRef], event_doc_ids: list[int]) -> dict[str, list[int]]:
    """{cohort: [sources that covered the event, sources of that cohort active today]}"""
    active: dict[str, set[str]] = defaultdict(set)
    covered: dict[str, set[str]] = defaultdict(set)
    members = set(event_doc_ids)
    for d in all_docs:
        c = cohort_of(d)
        if c is None or d.get("from_previous_day") or d.get("superseded"):
            continue  # an earlier day's publication is evidence, not today's coverage; a superseded version is its chain's newest row
        active[c].add(d["source_id"])
        if d["id"] in members:
            covered[c].add(d["source_id"])
    return {c: [len(covered[c]), len(active[c])] for c in COHORTS}


def settings() -> tuple[bool, str, str]:
    """(readings on, lane of frame_reading, lane of frame_flank_reading) from config [frame]. ValueError for a flag
    other than "off"/"on", or, with the flag on, a lane llm._route does not know."""
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): readings sit behind `[frame] readings`, committed "off". Why:
    # the portal parser (backend/portal/reasoning_preview.py, spectrum's optional keys) rejects any unknown spectrum key
    # with unsupported_reasoning_field, so a snapshot carrying readings is refused whole until the web side adds the
    # key (docs/ARCHITECTURE.md § 8, interface change 2026-10-26); off, frame's calls and output are as before.
    flag = str(config.get("frame", "readings", "off")).strip().lower()
    if flag not in ("off", "on"):
        raise ValueError(f'[frame] readings must be "off" or "on", got {flag!r}')
    if flag == "off":
        return False, "default", "default"
    lanes = []
    for key in ("reading_lane", "flank_reading_lane"):
        lane = str(config.get("frame", key, "default")).strip()
        if lane not in LANES:
            raise ValueError(f"[frame] {key} must be one of {', '.join(LANES)}, got {lane!r}")
        lanes.append(lane)
    return True, lanes[0], lanes[1]


def frame_payload(d: DocRef) -> dict[str, Any]:
    """The `frame` call's payload, unchanged since before readings (its request key must not move)."""
    return {
        "documents": [{"title": untrusted.clip(d["title"], untrusted.CAP_TITLE), "lead": untrusted.clip(d["lead"], untrusted.CAP_LEAD)}],
        "source": d["source_name"],
        "flank": d.get("flank"),
        "tier": d.get("tier"),
    }


def reading_payload(d: DocRef, fetched: FetchResult) -> dict[str, Any]:
    """The `frame_reading` call's payload: `frame`'s fields plus the document id and the text the run read."""
    return {
        "documents": [
            {
                "id": d["id"],
                "title": untrusted.clip(d["title"], untrusted.CAP_TITLE),
                "lead": untrusted.clip(d["lead"], untrusted.CAP_LEAD),
                "text": untrusted.clip(fetched.text or "", READING_TEXT_CAP),
            }
        ],
        "source": d["source_name"],
        "flank": d.get("flank"),
        "tier": d.get("tier"),
    }


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a model-written document_id is an int, or a string of 1 to 18
# ASCII digits (surrounding whitespace allowed); anything else is no id, so the sentence fails closed as cited from
# another document. Why: str.isdigit() also accepts "²" and "①", and int() raises on those and on digit strings past
# Python's 4300-digit limit; an exception there would fail the whole frame step, not just that sentence.
_DOC_ID = re.compile(r"[0-9]{1,18}")


def _doc_id(value: Any) -> int | None:
    """The document id a model reply cites, or None; total: never raises, whatever the reply holds."""
    if type(value) is int:
        return value
    if isinstance(value, str) and _DOC_ID.fullmatch(value.strip()):
        return int(value.strip())
    return None


def quote_problem(quote: Any) -> str | None:
    """Why a reading quote is refused before it is looked up, or None (decision at READING_QUOTE_MIN_WORDS)."""
    if not isinstance(quote, str) or not quote.strip():
        return "no quote"
    if len(quote) > EVIDENCE_QUOTE_CAP:
        return f"quote over the {EVIDENCE_QUOTE_CAP}-character cap"
    if len(_WORD.findall(quote)) < READING_QUOTE_MIN_WORDS:
        return f"quote under {READING_QUOTE_MIN_WORDS} words"
    return None


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; review round 3): words a reading sentence's `text` puts in quotation
# marks must be the article's own: each quotation must be found verbatim, as whole words (find_quote's exact match, not
# inside a longer word), in the text the run read for the sentence's cited document, which contains the sentence's own
# `quote`; otherwise the sentence is dropped ("quotation in the sentence not found verbatim"), and so is a sentence with
# a quotation mark code cannot pair ("unpaired quotation mark in the sentence"). Double marks pair as "…", ＂…＂, “…”,
# ‟…”, „…“, „…”, «…», »…« and ”…”, with no double mark inside (a nested double mark is unpaired); a single quotation
# opens with ‘, or with ' or ’ not preceded by a letter or digit and followed by a non-space, and runs to the last ' or ’
# not followed by a letter or digit before the next opening one, so an apostrophe inside ("the country's plan") never
# ends it early and a plural possessive after it can only lengthen what is checked. A comma or period just inside the
# closing mark is not part of the words (the American convention); a quotation without a letter or digit fails. Why:
# only `quote` was checked, so a sentence could put invented words in quotation marks and attribute them to a named
# outlet, and the page would publish them as that outlet's words; both prompts now also say `text` carries no quotation
# marks, so a dropped sentence costs one question (unanswered), never a misquote.
_NOT_DOUBLE = '[^"＂“”„‟«»]*'
_SINGLE_OPEN = r"(?:‘|(?<!\w)['’](?=\S))"
_QUOTATION = re.compile(
    "|".join(
        [
            f'"({_NOT_DOUBLE})"',
            f"＂({_NOT_DOUBLE})＂",
            f"[“‟]({_NOT_DOUBLE})”",
            f"„({_NOT_DOUBLE})[“”]",
            f"«({_NOT_DOUBLE})»",
            f"»({_NOT_DOUBLE})«",
            f"”({_NOT_DOUBLE})”",
            rf"{_SINGLE_OPEN}((?:(?!{_SINGLE_OPEN}).)*)['’](?!\w)",
        ]
    ),
    re.DOTALL,
)
_STRAY_MARK = re.compile(
    '["＂“”„‟«»‘‚‛‹›「」『』〝〞〟]'
    + f"|{_SINGLE_OPEN}"
)


def quotations(text: str) -> list[str] | None:
    """The words `text` puts in quotation marks, in order, or None when a quotation mark is left unpaired (decision
    above). Matched quotations are blanked with NUL before the stray-mark search, which keeps every other position
    and makes a mark right after a quotation count as preceded by a non-letter."""
    found: list[str] = []
    rest = list(text)
    for m in _QUOTATION.finditer(text):
        found.append(next(g for g in m.groups() if g is not None))
        rest[m.start() : m.end()] = "\0" * (m.end() - m.start())
    return None if _STRAY_MARK.search("".join(rest)) else found


def verbatim_words(haystack: str, words: str) -> bool:
    """True when the quoted `words` occur in `haystack` exactly, not as part of a longer word (decision above)."""
    words = words.strip()
    if words.endswith((",", ".")) and not words.endswith(".."):
        words = words[:-1].rstrip()
    if not _WORD.search(words):
        return False
    pattern = ("(?<!\\w)" if re.match(r"\w", words) else "") + re.escape(words) + ("(?!\\w)" if re.search(r"\w$", words) else "")
    return re.search(pattern, haystack) is not None


Finder = Callable[[int | None, str], "tuple[DocRef, tuple[int, int], str] | str"]


def checked_sentences(raw: Any, *, who: str, find: Finder) -> tuple[list[dict], list[dict]]:
    """(sentences that passed, in QUESTIONS order; dropped notes as trace detail rows {text, reason}).

    A sentence passes when it answers one of QUESTIONS not answered yet in this reply, is not about readers
    (_READER_META), pairs every quotation mark it uses (quotations), its quote passes quote_problem and
    `find(document_id, quote)`, which returns the document, the code-point span [start, end) of the quote in that
    document's text and that text, or why it failed, and every quotation in it is verbatim in that text
    (verbatim_words). The sentence text is model output: a string (anything else fails closed), whitespace collapsed
    and clipped to READING_SENTENCE_CAP, and the checks run on the clipped text, the one that is published."""
    kept: dict[str, dict] = {}
    notes: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            notes.append({"text": "(not an object)", "reason": f"{who}: sentence is not an object"})
            continue
        answers = item.get("answers")
        raw_text = item.get("text")
        if raw_text is None:
            raw_text = ""  # a missing sentence is an empty one
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; review round 2): a sentence `text` that is not a string is
        # dropped ("sentence text is not a string"), never turned into one with str(). Why: a dict, list, number or bool
        # from the model would otherwise be published as its Python repr in a side's paragraph, while every other
        # malformed field already fails closed.
        is_text = isinstance(raw_text, str)
        text = untrusted.clip(" ".join(raw_text.split()), READING_SENTENCE_CAP) if is_text else ""
        label = f" ({answers})" if answers in QUESTIONS else ""
        quote = item.get("quote")
        if answers not in QUESTIONS:
            reason = "answers none of the five questions"
        elif answers in kept:
            reason = "a second sentence for the same question"
        elif not is_text:
            reason = "sentence text is not a string"
        elif not text:
            reason = "empty sentence"
        elif _READER_META.search(text):
            reason = "written about readers, not stated directly"
        elif (quoted := quotations(text)) is None:
            reason = "unpaired quotation mark in the sentence"
        else:
            reason = quote_problem(quote)
        found: Any = None
        if reason is None:
            found = find(_doc_id(item.get("document_id")), quote)
            if isinstance(found, str):
                reason = found
            elif not all(verbatim_words(found[2], words) for words in quoted):
                reason = "quotation in the sentence not found verbatim"
        if reason is not None:
            notes.append({"text": text or ("(empty)" if is_text else "(not a string)"), "reason": f"{who}: {reason}{label}"})
            continue
        doc, (start, end), _ = found
        kept[answers] = {"answers": answers, "text": text, "quote": quote, "url": doc["url"], "document_id": doc["id"], "char_start": start, "char_end": end}
    return [kept[q] for q in QUESTIONS if q in kept], notes


def outlet_finder(d: DocRef, fetched: FetchResult) -> Finder:
    """An outlet's quote must come from that outlet's document, verbatim in the text the run read for it (fetched
    article text, or `title + "\n" + lead` when only that was achieved: FetchResult.quote_text, as for evidence)."""

    def find(doc_id: int | None, quote: str):
        if doc_id != d["id"]:
            return "quote cited from another document than this outlet's"
        span = find_quote(fetched.quote_text, quote)
        return (d, span, fetched.quote_text) if span else "quote not found verbatim in the text the run read"

    return find


def flank_finder(inputs: dict[tuple[int, str], DocRef], *, dry_run: bool) -> Finder:
    """A flank sentence must reuse one of the flank's verified outlet quotes (same document, same words) and that quote
    must still be verbatim in its document's text, read again through fetch_result (the run's cache)."""

    def find(doc_id: int | None, quote: str):
        doc = inputs.get((doc_id, quote)) if doc_id is not None else None
        if doc is None:
            return "quote is not one of this flank's verified outlet quotes"
        try:
            fetched = fetch_result(doc, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 — a failed re-read drops this sentence, not the frame step
            return f"its document's text could not be read again ({untrusted.public_failure(exc)})"
        span = find_quote(fetched.quote_text, quote) if fetched is not None else None
        return (doc, span, fetched.quote_text) if span else "quote no longer verbatim in its document's text"

    return find


def _label_key(label: str) -> str:
    words = re.sub(r"[^\w\s]", " ", (label or "").casefold()).split()
    if words and words[0] in ("a", "an", "the"):
        words = words[1:]
    return " ".join(words)


def outlets_differ(readings: list[dict]) -> bool:
    """True when a flank's outlet readings get their own entries.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a flank gets outlet entries when it has at least two published
    outlet readings (one per outlet) whose interpretation labels differ after case folding, punctuation removal and a
    leading "a"/"an"/"the" dropped; empty labels are ignored. Why: Yelysei's rule (2026-10-26) is a reading per outlet
    only where the flank's outlets differ, decided in code; the prompt asks for reused labels, so "A cost" and "a cost."
    are one frame, and a missing label is no evidence of a different one."""
    labels = {_label_key(r["label"]) for r in readings} - {""}
    return len(readings) >= 2 and len(labels) >= 2


def reading_entry(flank: str, source: str | None, sentences: list[dict]) -> dict:
    """One spectrum.readings item: the paragraph is the sentences joined by one space."""
    answered = {s["answers"] for s in sentences}
    return {
        "flank": flank,
        "source": source,
        "text": " ".join(s["text"] for s in sentences),
        "sentences": [dict(s) for s in sentences],
        "unanswered": [q for q in QUESTIONS if q not in answered],
    }


def flank_payload(flank: str, readings: list[dict]) -> dict[str, Any]:
    return {
        "flank": flank,
        "readings": [
            {
                "source": r["source"],
                "interpretation_label": r["label"],
                "sentences": [{"answers": s["answers"], "text": s["text"], "quote": s["quote"], "document_id": s["document_id"]} for s in r["sentences"]],
            }
            for r in readings
        ],
    }


def build_readings(outlet_readings: list[dict], *, dry_run: bool, lane: str) -> tuple[list[dict], list[dict], list[str], int]:
    """(spectrum.readings, dropped notes, failed flank calls, flank calls made) from the outlet readings of one event.

    Per flank (left, right, center): one reading per outlet, the first published one in document order (an outlet may
    run two articles), major outlets first. No reading: no entry. One: it is the flank's reading (source null), no
    call. Two or more: one frame_flank_reading call over their verified sentences. Then the outlet entries, when the
    outlets differ (outlets_differ) and the flank's own entry was published.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code; review round 2): outlet entries are published only under their
    flank's own entry; when the flank call fails or none of its sentences survive, the flank publishes nothing and a
    trace note says the outlet readings were withheld. Why: the decision is one paragraph per side with the outlet
    readings under it, so every outlet entry in spectrum.readings follows its flank's entry and the page never needs
    a side heading without its paragraph; a failed flank call is already a StepError (status partial)."""
    out: list[dict] = []
    notes: list[dict] = []
    failed: list[str] = []
    calls = 0
    for flank in FLANKS:
        seen: set[str] = set()
        side: list[dict] = []
        for r in outlet_readings:
            if r["flank"] == flank and r["sentences"] and r["source_id"] not in seen:
                seen.add(r["source_id"])
                side.append(r)
        side.sort(key=lambda r: 0 if r["tier"] == "major" else 1)
        if not side:
            continue
        published = False
        if len(side) == 1:
            out.append(reading_entry(flank, None, side[0]["sentences"]))
            published = True
        else:
            calls += 1
            ans: Any = None
            problem: str | None = None
            try:
                ans = llm.json_task("frame_flank_reading", flank_payload(flank, side), dry_run=dry_run, which=lane)
            except Exception as exc:  # noqa: BLE001 — the flank paragraph is lost, the outlet readings stay
                problem = untrusted.public_failure(exc)
            if problem is None and not isinstance(ans, dict):
                problem = "no object"
            if problem is not None:
                failed.append(f"{flank}: {problem}")
            else:
                inputs = {(s["document_id"], s["quote"]): r["doc"] for r in side for s in r["sentences"]}
                kept, dropped = checked_sentences(ans.get("sentences"), who=f"{flank} flank", find=flank_finder(inputs, dry_run=dry_run))
                notes += dropped
                if kept:
                    out.append(reading_entry(flank, None, kept))
                    published = True
                else:
                    notes.append({"text": "(flank reading)", "reason": f"{flank} flank: no sentence passed; not published"})
        if outlets_differ(side):
            if published:
                out.extend(reading_entry(flank, r["source"], r["sentences"]) for r in side)
            else:
                notes.append({"text": "(outlet readings)", "reason": f"{flank} flank: no flank paragraph, so its {len(side)} outlet readings are not published"})
    return out, notes, failed, calls


def run(state: RunState) -> dict:
    by_id = {d["id"]: d for d in state["documents"]}
    events = [dict(e) for e in state["events"]]
    steps, errors = [], []
    try:
        readings_on, outlet_lane, flank_lane = settings()
    except ValueError as exc:  # a mistyped flag or lane must not cost the run its framing: readings off, recorded
        readings_on, outlet_lane, flank_lane = False, "default", "default"
        errors.append(StepError(node="frame", event_id=None, message=f"{exc}; readings off for this run"))
    for e in events:
        if not e["above_bar"]:
            continue
        with step(state, "frame", event_id=e["id"], model=llm.model_name()) as s:
            outlets = []
            failed: list[str] = []
            outlet_readings: list[dict] = []
            notes: list[dict] = []
            try:
                for did in e["document_ids"]:
                    d = by_id[did]
                    if cohort_of(d) is None:
                        continue
                    fetched: FetchResult | None = None
                    if readings_on:
                        why_none = f"{d['source_name']}: no text the run may read (level 3); no reading"
                        try:
                            fetched = fetch_result(d, dry_run=state["dry_run"])  # research read it already: the run's cache
                        except Exception as exc:  # noqa: BLE001 — no text, no reading; the labels still come
                            why_none = f"{d['source_name']}: text unavailable ({untrusted.public_failure(exc)}); no reading"
                        if fetched is None:
                            notes.append({"text": "(reading)", "reason": why_none})
                    try:
                        if fetched is not None:
                            ans = llm.json_task("frame_reading", reading_payload(d, fetched), dry_run=state["dry_run"], which=outlet_lane)
                        else:
                            ans = llm.json_task("frame", frame_payload(d), dry_run=state["dry_run"])
                    except Exception as exc:  # noqa: BLE001 — one outlet unlabelled, the others keep their labels
                        failed.append(f"{d['source_name']}: {untrusted.public_failure(exc)}")
                        continue
                    if not isinstance(ans, dict):
                        failed.append(f"{d['source_name']}: no object")
                        continue
                    outlets.append(
                        {
                            "source": d["source_name"],
                            "cohort": cohort_of(d),
                            "flank": d.get("flank") or "center",
                            "url": d["url"],
                            "highlights": untrusted.clip(ans.get("highlights", ""), untrusted.CAP_LABEL),
                            "omits": untrusted.clip(ans.get("omits", ""), untrusted.CAP_LABEL),
                            "wording": untrusted.clip(ans.get("wording", ""), untrusted.CAP_LABEL),
                            "interpretation_label": untrusted.clip(ans.get("interpretation_label", ""), untrusted.CAP_LABEL),
                        }
                    )
                    if fetched is not None:
                        kept, dropped = checked_sentences(ans.get("sentences"), who=d["source_name"], find=outlet_finder(d, fetched))
                        notes += dropped
                        if not kept:
                            notes.append({"text": "(reading)", "reason": f"{d['source_name']}: no sentence passed; reading not published"})
                        outlet_readings.append(
                            {"flank": outlets[-1]["flank"], "source": d["source_name"], "source_id": d["source_id"], "tier": d.get("tier"), "label": outlets[-1]["interpretation_label"], "doc": d, "sentences": kept}
                        )
                labels: Counter[str] = Counter(o["interpretation_label"] for o in outlets if o["interpretation_label"])
                by_label_flank: dict[str, Counter[str]] = defaultdict(Counter)
                for o in outlets:
                    by_label_flank[o["interpretation_label"]][o["flank"]] += 1
                # both sides are always present (ARCHITECTURE § 8; the portal parser requires them on a completed frame):
                # a flank no outlet covered is empty strings, which is itself the finding
                sides = {flank: {"highlights": "", "omits": "", "wording": "", "example_url": ""} for flank in ("left", "right")}
                for flank in ("left", "right"):
                    side = [o for o in outlets if o["flank"] == flank]
                    side.sort(key=lambda o: 0 if o["cohort"].startswith("major") else 1)
                    if side:
                        sides[flank] = {k: side[0][k] for k in ("highlights", "omits", "wording")} | {"example_url": side[0]["url"]}
                e["framing"] = {
                    "rating_mode": "average",  # the flank on each source row is the averaged rating; other modes need the sources table
                    **sides,
                    "note": "",
                    "coverage": coverage(state["documents"], e["document_ids"]),
                    "interpretations": [
                        {"label": label, "outlets": n, "mostly": by_label_flank[label].most_common(1)[0][0]} for label, n in labels.most_common()
                    ],
                    "outlets": outlets,
                }
                s.decision = f"{len(outlets)} outlets labelled; {len(labels)} interpretation(s)" + (f"; {len(failed)} outlet call(s) failed" if failed else "")
                s.reason = "labels per outlet from the model; cohort shares counted in code" + (f"; failures: {failed[0]}" if failed else "")
                if readings_on:
                    readings, flank_notes, flank_failed, flank_calls = build_readings(outlet_readings, dry_run=state["dry_run"], lane=flank_lane)
                    notes += flank_notes
                    e["framing"]["readings"] = readings
                    entries = sum(1 for r in readings if r["source"] is not None)
                    s.decision += (
                        f"; readings: {len(readings)} published ({entries} outlet entries), {flank_calls} flank call(s)"
                        + (f", {len(flank_failed)} failed" if flank_failed else "")
                        + (f"; {len(notes)} reading note(s)" if notes else "")
                    )
                    s.reason += "; readings: every sentence quotes its side's own text, checked verbatim in code"
                    if flank_failed:
                        s.reason += f"; flank failure: {flank_failed[0]}"
                        errors.append(StepError(node="frame", event_id=e["id"], message=f"{len(flank_failed)} flank reading call(s) failed: {flank_failed[0]}"))
                    if notes:
                        s.detail = notes[:DETAIL_ROWS_MAX]  # the decision counts every note; the portal takes 12 rows
                if failed:
                    errors.append(StepError(node="frame", event_id=e["id"], message=f"{len(failed)} outlet framing call(s) failed: {failed[0]}"))
            except Exception as exc:  # noqa: BLE001
                errors.append(StepError(node="frame", event_id=e["id"], message=str(exc)[:300]))
                e["framing"] = {"rating_mode": "average", "coverage": coverage(state["documents"], e["document_ids"]), "interpretations": [], "outlets": outlets}
                s.decision = "failed; coverage counts only"
                s.reason = untrusted.public_failure(exc)
        steps.append(finish(state, s))
    return {"events": events, "steps": steps, "errors": errors}
