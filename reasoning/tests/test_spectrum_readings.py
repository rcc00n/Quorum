""""Across the spectrum" readings (frame node, flag `[frame] readings`; docs/DECISIONS.md › Stories as articles).

One paragraph per side on how it interpreted the fact, each sentence backed by a verbatim quote that code finds in the
text the run read; the snapshot carries them as the optional `spectrum.readings` list. Everything here runs on
stand-ins or scripted replies: no test reaches a model (test_no_live_call_with_the_flag_on proves the dry path).

The flag-off tests pin the behaviour of d57bd6f (the commit this feature started from): the committed samples in
docs/examples/ were byte-identical to d57bd6f's fixture dry runs apart from `generated_at` and trace `duration_ms`
(checked on an exact d57bd6f copy, 2026-10-26), and FRAME_CALLS_D57BD6F is the digest of d57bd6f's six `frame` calls on
the fixture day (task, payload, lane), the request-key material that a journal replay depends on besides the prompt.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tomllib
from pathlib import Path

import pytest

from quorum_reasoning import config, dryrun, graph, llm
from quorum_reasoning.nodes import frame
from quorum_reasoning.state import initial_state
from quorum_reasoning.tools.fetch_text import FetchResult, fetch_result

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"
ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"
PROMPTS = Path(frame.__file__).resolve().parent.parent / "prompts"
FRAME_MD_D57BD6F = "a3647032df41bb9ff2a20d72ac735e006a036825e5bd87c137b6bfa252b2045e"  # sha256 of prompts/frame.md as llm._prompt reads it
FRAME_CALLS_D57BD6F = "846cfb760c1d965d9d9b16ef88eb07ed883d5dc7268525c285ae5b234503ecc4"  # the 6 frame calls of the fixture day
READING_KEYS = ["flank", "source", "text", "sentences", "unanswered"]
SENTENCE_KEYS = ["answers", "text", "quote", "url", "document_id", "char_start", "char_end"]


# --- helpers -------------------------------------------------------------------------------------------------------


def _flag(monkeypatch, value: str = "on", **frame_keys: str) -> None:
    real = config.get
    values = {("frame", "readings"): value, **{("frame", k): v for k, v in frame_keys.items()}}
    monkeypatch.setattr(config, "get", lambda s, k, d=None: values[(s, k)] if (s, k) in values else real(s, k, d))


def _norm(snapshot: dict) -> dict:
    s = json.loads(json.dumps(snapshot))
    s.pop("generated_at", None)
    for t in s.get("trace", []):
        t.pop("duration_ms", None)
    return s


def _dry_run(monkeypatch, fixture: str | None = None) -> dict:
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    if fixture:
        monkeypatch.setenv("QUORUM_FIXTURE", fixture)
    else:
        monkeypatch.delenv("QUORUM_FIXTURE", raising=False)
    return graph.run_local(TOPIC, DAY, dry_run=True)


def validate_readings(readings: object) -> None:
    """The shape docs/ARCHITECTURE.md § 8 (interface change 2026-10-26) asks the portal parser to accept."""
    assert isinstance(readings, list)
    order = []
    for r in readings:
        assert list(r) == READING_KEYS, r
        assert r["flank"] in frame.FLANKS
        assert r["source"] is None or (isinstance(r["source"], str) and r["source"])
        assert isinstance(r["sentences"], list) and 1 <= len(r["sentences"]) <= 5
        answers = [s["answers"] for s in r["sentences"]]
        assert answers == [q for q in frame.QUESTIONS if q in answers]  # the questions' order, each at most once
        for s in r["sentences"]:
            assert list(s) == SENTENCE_KEYS, s
            assert isinstance(s["text"], str) and s["text"] and isinstance(s["quote"], str) and s["quote"]
            assert s["url"].startswith("https://")
            assert type(s["document_id"]) is int and s["document_id"] > 0
            a, b = s["char_start"], s["char_end"]
            assert type(a) is int and type(b) is int and 0 <= a < b and b - a == len(s["quote"])
        assert r["text"] == " ".join(s["text"] for s in r["sentences"])
        assert r["unanswered"] == [q for q in frame.QUESTIONS if q not in answers]
        order.append((frame.FLANKS.index(r["flank"]), r["source"] is not None))
    assert order == sorted(order)  # left, right, center; within a flank its own entry before the outlet entries
    flank_entries = [f for f, outlet in order if not outlet]
    assert len(flank_entries) == len(set(flank_entries))


TEXT_L1 = (
    "The rule tightens asylum screening at the southern border. Advocates said the change puts families at risk. "
    "The groups blamed the administration for the new limits. Officials said the rule is meant to reduce crossings. "
    "Lawyers plan to challenge the rule in federal court. Shelters near the border reported longer waits for families this week."
)
TEXT_L2 = "The new asylum rule takes effect on Monday. Critics called it a cruel step that ignores the law. Senators asked for hearings next week."
TEXT_R1 = "The rule restores order at the southern border. Supporters praised the change as long overdue. They said open borders caused the backlog."
TEXT_R2 = "Border agents welcomed the new asylum rule. The union said the rule gives agents the tools they asked for."


def _doc(i: int, source: str, flank: str | None, *, tier: str = "major", text: str | None = None, access: int = 1, title: str = "", lead: str = "") -> dict:
    return {
        "id": i, "source_id": source.lower().replace(" ", "-"), "source_name": source, "independence_group": source.lower(),
        "kind": "outlet", "flank": flank, "tier": tier, "url": f"https://news.example.org/{i}", "title": title or f"Story {i}",
        "lead": lead, "published_at": "2026-10-22T08:00:00Z", "access_level": access, "wire_origin": None, "text": text,
    }


def _state(docs: list[dict]) -> dict:
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["documents"] = docs
    st["events"] = [{
        "id": "ev1", "document_ids": [d["id"] for d in docs], "headline": "Asylum rule", "standfirst": "", "rubric": None,
        "above_bar": True, "rank": 1, "needs_review": False, "article": [], "drafts": 0, "versions": [], "critic_status": None,
        "critic_notes": "", "framing": {}, "review_reason": "",
    }]
    return st


def _reply(doc_id: int, label: str, *sentences: tuple) -> dict:
    """A frame_reading reply: (answers, text, quote) rows, or (answers, text, quote, document_id) to cite another id."""
    rows = [{"answers": s[0], "text": s[1], "quote": s[2], "document_id": s[3] if len(s) > 3 else doc_id} for s in sentences]
    return {"highlights": "h", "omits": "", "wording": "w", "interpretation_label": label, "sentences": rows}


def _script(monkeypatch, replies: dict) -> list[tuple]:
    """llm.json_task answers from `replies`: by document id for frame_reading/frame, by flank for frame_flank_reading;
    an Exception value is raised. Returns the calls (task, payload, lane)."""
    calls: list[tuple] = []

    def fake(task, payload, *, dry_run, which="default"):
        calls.append((task, payload, which))
        if task == "frame_flank_reading":
            ans = replies[("flank", payload["flank"])]
        elif task == "frame_reading":
            ans = replies[payload["documents"][0]["id"]]
        else:
            ans = replies.get(("frame", payload["source"]), {"highlights": "", "omits": "", "wording": "", "interpretation_label": "a label"})
        if isinstance(ans, Exception):
            raise ans
        return ans

    monkeypatch.setattr(llm, "json_task", fake)
    return calls


def _run(st: dict) -> tuple[dict, dict, list]:
    out = frame.run(st)
    e = out["events"][0]
    return e["framing"], out["steps"][0], out["errors"]


def _entry(readings: list[dict], flank: str, source: str | None = None) -> dict | None:
    return next((r for r in readings if r["flank"] == flank and r["source"] == source), None)


# --- flag and configuration ---------------------------------------------------------------------------------------


def test_committed_config_has_readings_off_and_default_lanes():
    raw = tomllib.loads((ROOT / "reasoning" / "config" / "reasoning.toml").read_text(encoding="utf-8"))["frame"]
    assert raw == {"readings": "off", "reading_lane": "default", "flank_reading_lane": "default"}
    assert frame.settings() == (False, "default", "default")


def test_flag_on_reads_the_configured_lanes(monkeypatch):
    _flag(monkeypatch, "on", reading_lane="fact_checker", flank_reading_lane="reviewer")
    assert frame.settings() == (True, "fact_checker", "reviewer")


@pytest.mark.parametrize("sample, fixture, fail_frame", [
    ("snapshot.sample.json", None, False),
    ("snapshot.empty-day.sample.json", "usecases/quiet_day", False),
    ("snapshot.partial.sample.json", None, True),
])
def test_flag_off_reproduces_d57bd6f_on_the_fixture_dry_runs(monkeypatch, sample, fixture, fail_frame):
    """Flag off: the fixture dry runs equal the committed samples (d57bd6f's output) apart from timing, no spectrum carries
    `readings`, and the frame calls are d57bd6f's: same task, payload and lane, and frame.md unchanged."""
    assert hashlib.sha256(llm._prompt("frame").encode("utf-8")).hexdigest() == FRAME_MD_D57BD6F
    real = llm.json_task
    frame_calls: list[str] = []

    def recording(task, payload, **kw):
        if task.startswith("frame"):
            frame_calls.append(json.dumps({"task": task, "payload": payload, "which": kw.get("which", "default")}, sort_keys=True, ensure_ascii=False))
        if fail_frame and task == "frame":
            raise RuntimeError("model route returned HTTP 503")  # what regenerate_samples.py does for the partial sample
        return real(task, payload, **kw)

    monkeypatch.setattr(llm, "json_task", recording)
    snap = _dry_run(monkeypatch, fixture)["snapshot"]
    committed = json.loads((EXAMPLES / sample).read_text(encoding="utf-8"))
    assert _norm(snap) == _norm(committed)
    assert all("readings" not in s["spectrum"] for s in snap["stories"])
    assert all(json.loads(c)["task"] == "frame" for c in frame_calls)
    if sample == "snapshot.sample.json":
        assert len(frame_calls) == 6
        assert hashlib.sha256("\n".join(frame_calls).encode("utf-8")).hexdigest() == FRAME_CALLS_D57BD6F


def test_flag_off_frame_reads_no_text_and_makes_only_frame_calls(monkeypatch):
    def no_fetch(*a, **k):
        raise AssertionError("frame fetched text with the flag off")

    monkeypatch.setattr(frame, "fetch_result", no_fetch)
    docs = [_doc(1, "Left One", "left", text=TEXT_L1), _doc(2, "Right One", "right", text=TEXT_R1)]
    calls = _script(monkeypatch, {})
    framing, rec, errors = _run(_state(docs))
    assert [c[0] for c in calls] == ["frame", "frame"]
    assert [c[1] for c in calls] == [frame.frame_payload(d) for d in docs]
    assert "readings" not in framing and "readings" not in rec["decision"] and "detail" not in rec
    assert errors == []


def test_an_invalid_flag_value_turns_readings_off_and_is_recorded(monkeypatch):
    _flag(monkeypatch, "yes")
    calls = _script(monkeypatch, {})
    out = frame.run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    assert [c[0] for c in calls] == ["frame"]
    assert "readings" not in out["events"][0]["framing"]
    assert any('[frame] readings must be "off" or "on"' in e["message"] for e in out["errors"])


def test_an_unknown_lane_turns_readings_off_and_is_recorded(monkeypatch):
    _flag(monkeypatch, "on", reading_lane="ultra")
    calls = _script(monkeypatch, {})
    out = frame.run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    assert [c[0] for c in calls] == ["frame"]
    assert any("[frame] reading_lane must be one of" in e["message"] for e in out["errors"])


# --- the flag-on snapshot ------------------------------------------------------------------------------------------


@pytest.fixture
def flag_on_run(monkeypatch):
    _flag(monkeypatch, "on")
    return _dry_run(monkeypatch)


def test_flag_on_snapshot_shape_is_additive(monkeypatch):
    """Every story's spectrum gains `readings` and nothing else: with the stand-ins every other field equals the
    flag-off run's; the readings follow the § 8 shape, cite only documents of the story's own event and side, and each
    quote sits at its offsets in the text the run read."""
    off = _dry_run(monkeypatch)["snapshot"]
    _flag(monkeypatch, "on")
    state = _dry_run(monkeypatch)
    snap = state["snapshot"]
    by_id = {d["id"]: d for d in state["documents"]}
    members = {e["id"]: set(e["document_ids"]) for e in state["events"]}
    assert snap["stories"], "the fixture day has stories above the bar"
    for on_story, off_story in zip(snap["stories"], off["stories"], strict=True):
        spectrum = dict(on_story["spectrum"])
        readings = spectrum.pop("readings")
        assert spectrum == off_story["spectrum"]
        validate_readings(readings)
        assert readings, "every fixture story has at least one flank reading"
        for r in readings:
            for s in r["sentences"]:
                doc = by_id[s["document_id"]]
                assert s["document_id"] in members[on_story["event_id"]]
                assert doc["url"] == s["url"] and (doc.get("flank") or "center") == r["flank"]
                assert fetch_result(doc, dry_run=True).quote_text[s["char_start"]:s["char_end"]] == s["quote"]
    assert snap["status"] == "ok" and not snap["errors"]


def test_flag_on_fixture_day_uses_one_flank_call_and_the_one_outlet_rule(flag_on_run):
    """The aid story: CNN alone on the left (its reading is the flank's, no call), three right outlets with one label
    (one flank call, no outlet entries); the sanctions story: one outlet per side, no call at all."""
    rows = [s for s in flag_on_run["steps"] if s["node"] == "frame"]
    assert [r["decision"].split("; readings: ")[1] for r in rows] == ["2 published (0 outlet entries), 1 flank call(s)", "2 published (0 outlet entries), 0 flank call(s)"]
    aid = flag_on_run["snapshot"]["stories"][0]["spectrum"]["readings"]
    assert [(r["flank"], r["source"]) for r in aid] == [("left", None), ("right", None)]
    assert {s["document_id"] for s in aid[0]["sentences"]} == {103}  # CNN's own document


def test_dry_stand_ins_are_deterministic(monkeypatch):
    _flag(monkeypatch, "on")
    first = _norm(_dry_run(monkeypatch)["snapshot"])
    second = _norm(_dry_run(monkeypatch)["snapshot"])
    assert first == second
    payload = {"documents": [{"id": 7, "title": "T", "lead": "", "text": TEXT_L1}], "source": "Left One", "flank": "left", "tier": "major"}
    assert dryrun.frame_reading(payload) == dryrun.frame_reading(json.loads(json.dumps(payload)))
    flank_in = {"flank": "left", "readings": [{"source": "Left One", "interpretation_label": "a risk", "sentences": dryrun.frame_reading(payload)["sentences"]}]}
    assert dryrun.frame_flank_reading(flank_in) == dryrun.frame_flank_reading(json.loads(json.dumps(flank_in)))


def test_no_live_call_with_the_flag_on(monkeypatch):
    """With the flag on and QUORUM_DRY_RUN=1 every reading task is answered by its stand-in: nothing reaches the client,
    the ledger stays empty, and each task the frame node asked for has a stand-in in dryrun.py."""
    def no_client(*a, **k):
        raise AssertionError("a test reached the model client")

    monkeypatch.setattr(llm, "_client", no_client)
    monkeypatch.setattr(llm, "_create", no_client)
    _flag(monkeypatch, "on")
    real = llm.json_task
    tasks: list[str] = []

    def recording(task, payload, **kw):
        tasks.append(task)
        return real(task, payload, **kw)

    monkeypatch.setattr(llm, "json_task", recording)
    _dry_run(monkeypatch)
    assert {"frame_reading", "frame_flank_reading"} <= set(tasks) and "frame" not in tasks
    assert all(hasattr(dryrun, t) for t in set(tasks))
    assert llm.calls == []


# --- grounding: the verbatim check and the fail-closed drops ------------------------------------------------------


def test_a_quote_is_bound_to_the_fetched_text_or_to_title_and_lead(monkeypatch):
    _flag(monkeypatch, "on")
    lead_only = _doc(2, "Right One", "right", access=2, title="Border rule restores order", lead="Supporters praised the change as long overdue.")
    docs = [_doc(1, "Left One", "left", text=TEXT_L1), lead_only]
    _script(monkeypatch, {
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk to families.", "the change puts families at risk")),
        2: _reply(2, "order", ("judgement", "It presents the rule as good.", "Supporters praised the change as long overdue")),
    })
    framing, _, _ = _run(_state(docs))
    left = _entry(framing["readings"], "left")["sentences"][0]
    assert TEXT_L1[left["char_start"]:left["char_end"]] == "the change puts families at risk"
    right = _entry(framing["readings"], "right")["sentences"][0]
    bound = lead_only["title"] + "\n" + lead_only["lead"]  # level 2: offsets index title + "\n" + lead
    assert bound[right["char_start"]:right["char_end"]] == "Supporters praised the change as long overdue"
    assert right["url"] == "https://news.example.org/2" and right["document_id"] == 2


@pytest.mark.parametrize("quote, doc_id, why", [
    ("The Change Puts Families At Risk", 1, "quote not found verbatim in the text the run read"),  # case changed
    ("the change puts  families at risk", 1, "quote not found verbatim in the text the run read"),  # whitespace changed
    ("The rule restores order at the southern border", 1, "quote not found verbatim in the text the run read"),  # the other side's words under its own id
    ("The rule restores order at the southern border", 2, "quote cited from another document than this outlet's"),  # the other side's document
    (TEXT_L1[:301], 1, "quote over the 300-character cap"),  # verbatim, but over the evidence quote cap
    ("the rule", 1, "quote under 3 words"),
    ("", 1, "no quote"),
])
def test_an_outlet_sentence_whose_quote_fails_is_dropped(monkeypatch, quote, doc_id, why):
    _flag(monkeypatch, "on")
    docs = [_doc(1, "Left One", "left", text=TEXT_L1), _doc(2, "Right One", "right", text=TEXT_R1)]
    assert TEXT_L1[:301] in TEXT_L1 and len(TEXT_L1[:301]) == 301
    _script(monkeypatch, {
        1: _reply(1, "a risk",
                  ("direction", "Left One presents the rule as a risk to families.", "The rule tightens asylum screening at the southern border"),
                  ("judgement", "It presents the rule as bad for families.", quote, doc_id)),
        2: _reply(2, "order", ("direction", "Right One presents the rule as restoring order.", "The rule restores order at the southern border")),
    })
    framing, rec, errors = _run(_state(docs))
    left = _entry(framing["readings"], "left")
    assert [s["answers"] for s in left["sentences"]] == ["direction"]
    assert left["unanswered"] == ["judgement", "cause", "why", "next"]
    assert {"text": "It presents the rule as bad for families.", "reason": f"Left One: {why} (judgement)"} in rec["detail"]
    assert "1 reading note(s)" in rec["decision"] and errors == []


def test_a_reading_with_no_passing_sentence_is_not_published(monkeypatch):
    _flag(monkeypatch, "on")
    docs = [_doc(1, "Left One", "left", text=TEXT_L1), _doc(2, "Right One", "right", text=TEXT_R1)]
    _script(monkeypatch, {
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk.", "words that are not in the article")),
        2: _reply(2, "order", ("direction", "Right One presents the rule as restoring order.", "The rule restores order at the southern border")),
    })
    framing, rec, _ = _run(_state(docs))
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == [("right", None)]
    assert {"text": "(reading)", "reason": "Left One: no sentence passed; reading not published"} in rec["detail"]
    assert framing["outlets"][0]["interpretation_label"] == "a risk"  # the labels stay: only the reading is withheld


def test_unanswered_lists_the_questions_the_side_leaves_open(monkeypatch):
    _flag(monkeypatch, "on")
    _script(monkeypatch, {1: _reply(1, "a risk",
        ("next", "It says lawyers will challenge the rule in court.", "Lawyers plan to challenge the rule in federal court"),
        ("direction", "Left One presents the rule as a risk to families.", "the change puts families at risk"))})
    framing, _, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    (r,) = framing["readings"]
    assert [s["answers"] for s in r["sentences"]] == ["direction", "next"]  # the questions' order, not the reply's
    assert r["unanswered"] == ["judgement", "cause", "why"]
    assert r["text"] == "Left One presents the rule as a risk to families. It says lawyers will challenge the rule in court."


def test_one_sentence_per_question_known_questions_only_and_text_clipped(monkeypatch):
    _flag(monkeypatch, "on")
    long_text = "Left One presents the rule as a risk " + "and a burden " * 40
    _script(monkeypatch, {1: _reply(1, "a risk",
        ("direction", long_text, "the change puts families at risk"),
        ("direction", "A second direction sentence.", "The rule tightens asylum screening at the southern border"),
        ("mood", "It sounds worried.", "Advocates said the change puts families at risk"),
        ("cause", "  It   blames the\nadministration.  ", "The groups blamed the administration for the new limits"))})
    framing, rec, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    (r,) = framing["readings"]
    assert [s["answers"] for s in r["sentences"]] == ["direction", "cause"]
    assert len(r["sentences"][0]["text"]) == frame.READING_SENTENCE_CAP and r["sentences"][0]["text"].endswith(" …")
    assert r["sentences"][1]["text"] == "It blames the administration."
    reasons = {row["reason"] for row in rec["detail"]}
    assert "Left One: a second sentence for the same question (direction)" in reasons
    assert "Left One: answers none of the five questions" in reasons


@pytest.mark.parametrize("text", [
    "Readers leave thinking the rule is harsh.",
    "The outlet wants readers to see the rule as harsh.",
    "Left One sets out to convey that the rule is harsh.",
    "It leaves its audience with the impression of a harsh rule.",
    "The article leaves you thinking the rule is harsh.",
    "Left One wants you to fear the rule.",
])
def test_a_sentence_about_readers_is_dropped(monkeypatch, text):
    _flag(monkeypatch, "on")
    _script(monkeypatch, {1: _reply(1, "a risk",
        ("direction", text, "the change puts families at risk"),
        ("cause", "It blames the administration.", "The groups blamed the administration for the new limits"))})
    framing, rec, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    (r,) = framing["readings"]
    assert [s["answers"] for s in r["sentences"]] == ["cause"] and r["unanswered"][0] == "direction"
    assert {"text": text, "reason": "Left One: written about readers, not stated directly (direction)"} in rec["detail"]


def test_a_direct_direction_sentence_passes_the_guard():
    assert frame._READER_META.search("Left One presents the rule as a risk to families.") is None
    assert frame._READER_META.search("Officials say the rule aims to make screening faster.") is None  # an aim of the rule, not of the outlet


# --- flanks: the one-outlet rule, the flank call and where outlets differ ---------------------------------------


def _left_pair() -> list[dict]:
    return [_doc(1, "Left One", "left", text=TEXT_L1), _doc(3, "Left Two", "left", tier="minor", text=TEXT_L2), _doc(2, "Right One", "right", text=TEXT_R1)]


def _left_pair_replies(label_b: str = "a risk", flank_sentences: list[dict] | None = None) -> dict:
    return {
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk to families.", "the change puts families at risk"),
                  ("next", "It says lawyers will challenge the rule.", "Lawyers plan to challenge the rule in federal court")),
        3: _reply(3, label_b, ("judgement", "It presents the rule as bad.", "Critics called it a cruel step that ignores the law")),
        2: _reply(2, "order", ("direction", "Right One presents the rule as restoring order.", "The rule restores order at the southern border")),
        ("flank", "left"): {"sentences": flank_sentences if flank_sentences is not None else [
            {"answers": "direction", "text": "Left outlets present the rule as a risk to families.", "quote": "the change puts families at risk", "document_id": 1},
            {"answers": "judgement", "text": "They present it as bad.", "quote": "Critics called it a cruel step that ignores the law", "document_id": 3},
        ]},
    }


def test_a_one_outlet_flank_needs_no_call_and_its_reading_is_the_flanks(monkeypatch):
    _flag(monkeypatch, "on")
    calls = _script(monkeypatch, _left_pair_replies())
    framing, _, _ = _run(_state(_left_pair()))
    assert [c[0] for c in calls].count("frame_flank_reading") == 1  # the left flank only
    assert calls[-1][1]["flank"] == "left"
    right = _entry(framing["readings"], "right")
    assert right["sentences"][0]["document_id"] == 2 and right["source"] is None


def test_the_flank_call_reuses_only_verified_input_quotes(monkeypatch):
    _flag(monkeypatch, "on")
    flank_sentences = [
        {"answers": "direction", "text": "Left outlets present the rule as a risk to families.", "quote": "the change puts families at risk", "document_id": 1},
        {"answers": "judgement", "text": "They present it as bad.", "quote": "Advocates said the change puts families at risk", "document_id": 1},  # verbatim, not an input quote
        {"answers": "cause", "text": "They blame the courts.", "quote": "Critics called it a cruel step that ignores the law", "document_id": 1},  # an input quote under another id
        {"answers": "why", "text": "They cite order.", "quote": "The rule restores order at the southern border", "document_id": 2},  # the right flank's quote
        {"answers": "next", "text": "They expect hearings.", "quote": "Senators asked for hearings next week", "document_id": 3},  # verbatim in Left Two, never verified
    ]
    calls = _script(monkeypatch, _left_pair_replies(flank_sentences=flank_sentences))
    framing, rec, _ = _run(_state(_left_pair()))
    payload = next(c[1] for c in calls if c[0] == "frame_flank_reading")
    assert [r["source"] for r in payload["readings"]] == ["Left One", "Left Two"]  # major first; only verified sentences go in
    assert [s["quote"] for r in payload["readings"] for s in r["sentences"]] == ["the change puts families at risk", "Lawyers plan to challenge the rule in federal court", "Critics called it a cruel step that ignores the law"]
    left = _entry(framing["readings"], "left")
    assert [s["answers"] for s in left["sentences"]] == ["direction"]
    assert left["unanswered"] == ["judgement", "cause", "why", "next"]
    flank_reasons = [row["reason"] for row in rec["detail"] if row["reason"].startswith("left flank")]
    assert flank_reasons == [f"left flank: quote is not one of this flank's verified outlet quotes ({q})" for q in ("judgement", "cause", "why", "next")]


def test_a_flank_quote_no_longer_verbatim_in_its_document_is_dropped(monkeypatch):
    _flag(monkeypatch, "on")
    real = frame.fetch_result
    seen: dict[int, int] = {}

    def changing(doc, *, dry_run):
        seen[doc["id"]] = seen.get(doc["id"], 0) + 1
        got = real(doc, dry_run=dry_run)
        if doc["id"] == 3 and seen[3] > 1:  # the page changed between the outlet reading and the flank check
            changed = got.quote_text.replace("cruel step", "harsh step")
            return FetchResult(changed, changed, got.content_hash, got.access_achieved, got.fetched_at, got.fetcher)
        return got

    monkeypatch.setattr(frame, "fetch_result", changing)
    _script(monkeypatch, _left_pair_replies())
    framing, rec, _ = _run(_state(_left_pair()))
    left = _entry(framing["readings"], "left")
    assert [s["answers"] for s in left["sentences"]] == ["direction"]
    assert {"text": "They present it as bad.", "reason": "left flank: quote no longer verbatim in its document's text (judgement)"} in rec["detail"]


def test_outlet_entries_appear_only_where_the_flanks_outlets_differ(monkeypatch):
    _flag(monkeypatch, "on")
    _script(monkeypatch, _left_pair_replies(label_b="A risk."))  # the same frame, written differently
    framing, rec, _ = _run(_state(_left_pair()))
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == [("left", None), ("right", None)]
    assert "(0 outlet entries)" in rec["decision"]

    _script(monkeypatch, _left_pair_replies(label_b="a cruel step"))
    framing, rec, _ = _run(_state(_left_pair()))
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == [("left", None), ("left", "Left One"), ("left", "Left Two"), ("right", None)]
    assert _entry(framing["readings"], "left", "Left Two")["unanswered"] == ["direction", "cause", "why", "next"]
    assert "(2 outlet entries)" in rec["decision"]
    validate_readings(framing["readings"])


def test_outlets_differ_rule():
    r = lambda label: {"label": label}  # noqa: E731
    assert not frame.outlets_differ([r("a cost")])
    assert not frame.outlets_differ([r("A cost"), r("a cost.")])
    assert not frame.outlets_differ([r("the cost"), r("")])  # a missing label is no different frame
    assert frame.outlets_differ([r("a cost"), r("a security commitment")])


def test_one_reading_per_outlet_when_an_outlet_runs_two_articles(monkeypatch):
    _flag(monkeypatch, "on")
    second = _doc(4, "Left One", "left", text=TEXT_L2)  # the same source, a second article
    calls = _script(monkeypatch, {
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk.", "the change puts families at risk")),
        4: _reply(4, "a cruel step", ("judgement", "It presents the rule as bad.", "Critics called it a cruel step that ignores the law")),
    })
    framing, _, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1), second]))
    assert "frame_flank_reading" not in [c[0] for c in calls]
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == [("left", None)]
    assert framing["readings"][0]["sentences"][0]["document_id"] == 1


def test_a_failed_flank_call_publishes_no_flank_paragraph_and_is_recorded(monkeypatch):
    _flag(monkeypatch, "on")
    replies = _left_pair_replies()
    replies[("flank", "left")] = RuntimeError("model route returned HTTP 503")
    _script(monkeypatch, replies)
    framing, rec, errors = _run(_state(_left_pair()))
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == [("right", None)]
    assert "1 flank call(s), 1 failed" in rec["decision"]
    assert [e["message"] for e in errors] == ["1 flank reading call(s) failed: left: upstream operation failed; internal details withheld (RuntimeError)"]


def test_center_outlets_get_their_own_reading_after_left_and_right(monkeypatch):
    _flag(monkeypatch, "on")
    docs = [_doc(5, "Center One", None, text=TEXT_R2), _doc(2, "Right One", "right", text=TEXT_R1), _doc(1, "Left One", "left", text=TEXT_L1)]
    _script(monkeypatch, {
        5: _reply(5, "a tool for agents", ("direction", "Center One presents the rule as a tool for agents.", "Border agents welcomed the new asylum rule")),
        2: _reply(2, "order", ("direction", "Right One presents the rule as restoring order.", "The rule restores order at the southern border")),
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk.", "the change puts families at risk")),
    })
    framing, _, _ = _run(_state(docs))
    assert [r["flank"] for r in framing["readings"]] == ["left", "right", "center"]
    validate_readings(framing["readings"])


# --- the call itself -----------------------------------------------------------------------------------------------


def test_the_reading_call_carries_the_article_text_clipped_and_uses_the_configured_lane(monkeypatch):
    _flag(monkeypatch, "on", reading_lane="default", flank_reading_lane="reviewer")
    long = TEXT_L1 + " " + "More reporting follows here. " * 400
    calls = _script(monkeypatch, {
        1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk.", "the change puts families at risk")),
        3: _reply(3, "a risk", ("judgement", "It presents the rule as bad.", "Critics called it a cruel step that ignores the law")),
        ("flank", "left"): {"sentences": []},
    })
    framing, rec, _ = _run(_state([_doc(1, "Left One", "left", text=long), _doc(3, "Left Two", "left", text=TEXT_L2)]))
    task, payload, lane = calls[0]
    assert task == "frame_reading" and lane == "default"
    (doc,) = payload["documents"]
    assert doc["id"] == 1 and len(doc["text"]) == frame.READING_TEXT_CAP and doc["text"].endswith(" …")
    assert set(payload) == {"documents", "source", "flank", "tier"} and set(doc) == {"id", "title", "lead", "text"}
    assert calls[-1][0] == "frame_flank_reading" and calls[-1][2] == "reviewer"
    assert {"text": "(flank reading)", "reason": "left flank: no sentence passed; not published"} in rec["detail"]
    assert [(r["flank"], r["source"]) for r in framing["readings"]] == []  # same label, no flank paragraph: nothing published


def test_a_level_3_outlet_keeps_the_plain_frame_call(monkeypatch):
    _flag(monkeypatch, "on")
    calls = _script(monkeypatch, {1: _reply(1, "a risk", ("direction", "Left One presents the rule as a risk.", "the change puts families at risk"))})
    framing, rec, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1), _doc(6, "Right Paywall", "right", access=3)]))
    assert [c[0] for c in calls] == ["frame_reading", "frame"]
    assert calls[1][1] == frame.frame_payload(_doc(6, "Right Paywall", "right", access=3))
    assert len(framing["outlets"]) == 2 and _entry(framing["readings"], "right") is None
    assert {"text": "(reading)", "reason": "Right Paywall: no text the run may read (level 3); no reading"} in rec["detail"]


def test_trace_detail_rows_fit_the_portal_limit(monkeypatch):
    _flag(monkeypatch, "on")
    bad = [(q, f"Sentence {i}.", f"not in the article {i}") for i, q in enumerate(frame.QUESTIONS * 3)]
    _script(monkeypatch, {1: _reply(1, "a risk", *bad)})
    _, rec, _ = _run(_state([_doc(1, "Left One", "left", text=TEXT_L1)]))
    assert len(rec["detail"]) == frame.DETAIL_ROWS_MAX == 12
    assert all(set(row) == {"text", "reason"} and all(isinstance(v, str) for v in row.values()) for row in rec["detail"])
    assert "16 reading note(s)" in rec["decision"]  # 15 dropped sentences + "not published"


def test_the_reading_prompts_exist_and_carry_the_data_rule():
    frame_md = (PROMPTS / "frame.md").read_text(encoding="utf-8").strip().splitlines()
    for name in ("frame_reading.md", "frame_flank_reading.md"):
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert text.strip().splitlines()[-1] == frame_md[-1]  # the quoted-material paragraph, word for word
        for q in frame.QUESTIONS:
            assert f"`{q}`" in text
        assert "readers leave thinking" in text and "never guess" in text


# --- the readings example for the web side --------------------------------------------------------------------------


def _regenerate_module():
    spec = importlib.util.spec_from_file_location("regenerate_samples", ROOT / "reasoning" / "scripts" / "regenerate_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_readings_example_is_fictional_out_of_the_portal_glob_and_current(monkeypatch):
    path = EXAMPLES / "spectrum-readings.sample.json"
    assert path not in set(EXAMPLES.glob("snapshot*.json"))  # the CI step and web/tests/contract.cjs validate only these
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed["fictional"] is True and committed["provenance"]["fictional"] is True and "FICTIONAL" in committed["_note"]
    for story in committed["stories"]:
        validate_readings(story["spectrum"]["readings"])
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    monkeypatch.delenv("QUORUM_FIXTURE", raising=False)
    assert _regenerate_module().readings_sample() == committed
    assert config.get("frame", "readings") == "off" and dryrun.frame.__module__ == "quorum_reasoning.dryrun" and dryrun.frame.__name__ == "frame"  # the generator put both back
