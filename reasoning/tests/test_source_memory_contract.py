"""Source memory (H-MEM) contract without the engine: default off, dry runs never touch it, recall is candidate-only.

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the off/dry/candidate-only guarantees are proved here against an
in-process stand-in of the sidecar's JSON contract (reasoning/memory/sidecar.mjs: `store` keeps each distinct row once,
`recall` returns every stored record after a JSON round trip), so the suite proves them on every machine. Why: the
engine-backed tests (tests/test_source_memory.py, tests/test_memory_storage_safety.py) skip without a reference
checkout in METERLESS_HOME; the guarantees must not depend on that. The stand-in never decides what the engine
recalls, only what Quorum does with a recalled record. All records are explicit TEST data on the fixture corpus.
"""

from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest

from quorum_reasoning import config, graph, llm
from quorum_reasoning.nodes import frame, research
from quorum_reasoning.rules.confirmation import origin_group, verdict
from quorum_reasoning.state import StepRecord
from quorum_reasoning.tools import memory
from quorum_reasoning.tools.fetch_text import FetchResult, content_hash
from test_source_memory import TEXT, state

FRESH_CONTRADICTION = "The Senate did not pass the aid bill."


class FakeSidecar:
    """The sidecar's store/recall contract, in process. No engine, no subprocess, no store directory."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.calls: list[tuple[str, object]] = []

    def __call__(self, st, action, **payload):
        self.calls.append((action, st.get("dry_run")))
        if action == "store":
            seen = {json.dumps(r, sort_keys=True) for r in self.records}
            new = [json.loads(json.dumps(r)) for r in payload["rows"] if json.dumps(r, sort_keys=True) not in seen]
            self.records += new
            return {"count": len(new), "rows": [], "ledger_entries": len(new)}
        if action == "recall":
            rows = [{"record": json.loads(json.dumps(r)), "memory_id": f"TEST-m{i}", "relevance": 1.0} for i, r in enumerate(self.records)]
            return {"rows": rows, "count": 0, "ledger_entries": 1}
        raise ValueError("Unsupported action")


def flag_on(monkeypatch) -> None:
    original = config.get
    monkeypatch.setattr(config, "get", lambda section, key, default=None: "on" if (section, key) == ("engines", "hmem") else original(section, key, default))


@pytest.fixture
def fake(monkeypatch):
    """A live-looking state (dry_run False) with the memory hooks on and the sidecar replaced by FakeSidecar."""
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    sidecar = FakeSidecar()
    monkeypatch.setattr(memory, "_call", sidecar)
    monkeypatch.setattr(memory, "enabled", lambda s: not s["dry_run"])  # as tests/test_source_memory.py: no model route in tests
    return sidecar


def remembered_state(sidecar: FakeSidecar):
    s = state()
    steps, errors = memory.remember(s, [])
    assert not errors and "stored 1" in steps[0]["decision"] and len(sidecar.records) == 1
    s["claims"]["TEST-claim"]["evidence"] = []  # today's run starts with no evidence: only memory knows document 2 supported it
    return s


# ---- default off; dry runs never touch memory ----


def test_committed_flag_is_off_even_on_a_live_route(monkeypatch):
    assert config.load()["engines"]["hmem"] == "off"
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "route_configured", lambda: True)
    assert not memory.enabled(state())
    flag_on(monkeypatch)
    assert memory.enabled(state())


@pytest.mark.parametrize("why", ["state", "env", "no route"])
def test_flag_on_still_never_enables_a_dry_run(monkeypatch, why):
    flag_on(monkeypatch)
    s = state()
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "route_configured", lambda: why != "no route")
    if why == "state":
        s["dry_run"] = True
    elif why == "env":
        monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    assert not memory.enabled(s)
    with patch.object(memory, "_call", side_effect=AssertionError("dry mode touched memory")) as call:
        assert memory.remember(s, s["events"]) == ([], [])
        assert memory.prioritize(s, "TEST-event", TEXT, s["documents"]) == (s["documents"], [], [])
    call.assert_not_called()


def test_whole_dry_run_with_the_flag_on_never_calls_the_sidecar(monkeypatch):
    flag_on(monkeypatch)
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    calls: list = []
    monkeypatch.setattr(memory, "_call", lambda *a, **k: calls.append(a) or {"rows": [], "count": 0, "ledger_entries": 0})
    final = graph.run_local("russia-ukraine-war", "2026-10-22", dry_run=True)
    assert calls == []
    assert not [x for x in final["steps"] if x["node"] == "memory"]
    assert not [x for x in final["errors"] if x["node"] == "memory"]


# ---- what is written ----


def test_only_bound_supporting_evidence_of_confirmed_facts_is_written(fake):
    for change in (
        lambda c, ev: c.update(final_status="unverified"),
        lambda c, ev: c.update(kind="statement"),
        lambda c, ev: ev.update(stance="statement"),
        lambda c, ev: ev.update(char_start=None),
        lambda c, ev: ev.update(url="https://example.org/TEST/elsewhere"),
        lambda c, ev: ev.update(content_hash_at_quote=None),
    ):
        s = state()
        claim = s["claims"]["TEST-claim"]
        change(claim, claim["evidence"][0])
        steps, errors = memory.remember(s, [])
        assert not errors and steps[0]["decision"] == "stored 0 source memories"
    assert fake.records == [] and [a for a, _ in fake.calls] == []  # nothing eligible: the sidecar is not even called
    s = state()
    memory.remember(s, [])
    (row,) = fake.records
    assert row["kind"] == "evidence-candidate" and row["docref"] == memory.identity(s["documents"][1])
    assert row["fictional"] is True and row["topic_id"] == "russia-ukraine-war" and row["run_id"] == "TEST-memory-run"
    assert memory.remember(s, [])[0][0]["decision"] == "stored 0 source memories"  # the same rows again are not stored twice


def test_frame_writes_each_outlets_label_with_its_exact_docref(fake):
    s = state()
    s["events"][0]["above_bar"] = True
    with patch.object(frame.llm, "json_task", return_value={"interpretation_label": "TEST source framing"}):
        result = frame.run(s)
    assert result["steps"][-1]["node"] == "memory" and result["steps"][-1]["decision"] == "stored 2 source memories"
    framing = next(r for r in fake.records if r["kind"] == "framing")
    assert framing["docref"] == memory.identity(s["documents"][0]) and framing["interpretation_label"] == "TEST source framing"
    assert set(result["steps"][-1]) == set(StepRecord.__annotations__) - {"detail"}  # the ordinary trace row shape


# ---- recall is candidate-only ----


def fresh(text: str) -> FetchResult:
    return FetchResult(text, text, content_hash("TEST bill", TEXT, text), 1, "2026-10-22T10:00:00Z", "TEST shared fetcher")


def test_recalled_document_is_judged_on_its_fresh_text(fake):
    s = remembered_state(fake)
    with patch.object(research, "fetch_result", return_value=fresh(FRESH_CONTRADICTION)) as fetch, patch.object(research.llm, "json_task", return_value={"stance": "contradicts", "contradicted_span": FRESH_CONTRADICTION}) as model:
        result = research.run(s)
    (ev,) = result["claims"]["TEST-claim"]["evidence"]
    assert fetch.called and model.call_count == 1
    assert ev["stance"] == "contradicts" and ev["quote"] == FRESH_CONTRADICTION  # the fresh text and the fresh judgment, not the remembered quote
    assert ev["content_hash_at_quote"] == fresh(FRESH_CONTRADICTION).content_hash
    (mem,) = [x for x in result["steps"] if x["node"] == "memory"]
    assert mem["decision"] == "recalled 1 authorized source candidates" and "fresh verification required" in mem["reason"]


def test_a_remembered_supports_never_confirms_by_itself(fake):
    s = remembered_state(fake)
    by_id = {d["id"]: d for d in s["documents"]}
    with patch.object(research.llm, "json_task", return_value={"stance": "neutral"}) as model:
        result = research.run(s)
    claim = result["claims"]["TEST-claim"]
    assert model.called and claim["evidence"] == []  # the model said neutral today: memory adds no row
    assert verdict(claim["evidence"], origin_group(claim, by_id))[0] == "unverified"
    assert any(x["node"] == "memory" and x["decision"].startswith("recalled 1") for x in result["steps"])


def test_a_recalled_page_that_is_gone_today_yields_nothing(fake):
    s = remembered_state(fake)
    real = research.fetch_result
    seen: dict[int, int] = {}

    def gone_at_judgment(doc, **kw):  # ranking still sees the stored text; the fresh fetch for the stance call finds nothing
        seen[doc["id"]] = seen.get(doc["id"], 0) + 1
        return real(doc, **kw) if seen[doc["id"]] == 1 else None

    with patch.object(research, "fetch_result", side_effect=gone_at_judgment), patch.object(research.llm, "json_task") as model:
        result = research.run(s)
    assert seen.get(2) == 2  # document 2 was ranked, recalled and fetched again
    model.assert_not_called()
    assert result["claims"]["TEST-claim"]["evidence"] == []


def test_memory_reorders_within_the_existing_cap_and_never_widens_it(fake, monkeypatch):
    s = remembered_state(fake)
    for i in range(3, 14):  # newer copies outrank document 2 on the ordinary ranking (ties go to the newest)
        d = copy.deepcopy(s["documents"][1])
        d.update(id=i, source_id=f"TEST-{i}", source_name=f"TEST-{i}", independence_group=f"TEST-{i}", url=f"https://example.org/TEST/{i}", published_at="2026-10-21T13:00:00Z")
        s["documents"].append(d)
    original = config.get
    monkeypatch.setattr(config, "get", lambda section, key, default=None: 1 if (section, key) == ("research", "candidates_per_claim") else original(section, key, default))
    with patch.object(research.llm, "json_task", return_value={"stance": "neutral"}) as model:
        research.run(copy.deepcopy(s))
    assert model.call_count == 1 and model.call_args[0][1]["source"] == "TEST-2"  # the recalled document took the one slot
    fake.records.clear()
    with patch.object(research.llm, "json_task", return_value={"stance": "neutral"}) as model:
        research.run(copy.deepcopy(s))
    assert model.call_count == 1 and model.call_args[0][1]["source"] != "TEST-2"  # without memory: the ordinary ranking


@pytest.mark.parametrize(
    "change",
    [
        lambda doc, rec: doc.update(content_hash="a" * 64),  # the page changed since it was remembered
        lambda doc, rec: doc.update(source_id="TEST-other"),
        lambda doc, rec: doc.update(official=True),  # another id namespace
        lambda doc, rec: doc.update(superseded=True),
        lambda doc, rec: doc.update(fetched_at="2026-10-22T00:00:00Z"),
        lambda doc, rec: rec["docref"].update(id=2.0),  # type-exact identity
        lambda doc, rec: rec.update(topic_id="TEST-other-topic"),
        lambda doc, rec: rec.update(fictional=False),  # a real-corpus record never steers a fixture run, nor the reverse
        lambda doc, rec: rec.update(kind="framing"),
        lambda doc, rec: (doc.update(published_at="2026-10-01T12:00:00Z"), rec["docref"].update(published_at="2026-10-01T12:00:00Z")),  # outside the window
    ],
)
def test_only_an_exact_current_docref_in_the_ranked_pool_is_moved_up(fake, change):
    s = remembered_state(fake)
    doc = copy.deepcopy(s["documents"][1])
    change(doc, fake.records[0])
    other = s["documents"][0]
    ordered, steps, errors = memory.prioritize(s, "TEST-event", TEXT, [other, doc])
    assert not errors and ordered == [other, doc] and steps[0]["decision"] == "recalled 0 authorized source candidates"


def test_prioritize_returns_only_documents_it_was_given(fake):
    s = remembered_state(fake)
    ordered, _, _ = memory.prioritize(s, "TEST-event", TEXT, [s["documents"][0]])
    assert ordered == [s["documents"][0]]  # document 2 is remembered but not in today's pool: it is not added
    ordered, _, _ = memory.prioritize(s, "TEST-event", TEXT, [s["documents"][0], s["documents"][1]])
    assert ordered[0] is s["documents"][1] and len(ordered) == 2  # the same objects, reordered; no record or quote inside


# ---- failures ----


def test_failures_keep_the_ordinary_ranking_and_name_only_the_exception_type(fake, monkeypatch):
    s = state()
    leak = "TEST secret C:/private/store remembered quote"
    monkeypatch.setattr(memory, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(leak)))
    ordered, steps, errors = memory.prioritize(s, "TEST-event", TEXT, s["documents"])
    assert ordered == s["documents"] and steps[0]["decision"] == "memory recall unavailable"
    w_steps, w_errors = memory.remember(s, [])
    assert w_steps[0]["decision"] == "memory write unavailable"
    for text in (steps[0]["reason"], errors[0]["message"], w_steps[0]["reason"], w_errors[0]["message"]):
        assert "RuntimeError" in text and "secret" not in text and "private" not in text
    assert errors[0]["node"] == w_errors[0]["node"] == "memory"


def test_sidecar_io_is_utf8_and_the_store_stays_outside_the_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("QUORUM_HMEM_DIR", str(tmp_path / "TEST-store"))
    monkeypatch.setenv("METERLESS_HOME", str(tmp_path / "TEST-checkout"))
    monkeypatch.setattr(memory, "_launcher", lambda home: ["TEST-node", "TEST-cli"])
    seen = {}

    def run(argv, **kw):
        seen.update(kw, argv=argv)
        return type("Done", (), {"stdout": '{"rows": [], "count": 0, "ledger_entries": 0}'})()

    s = state()
    s["claims"]["TEST-claim"]["text"] = "TEST Zelensky’s «aid» bill"
    with patch.object(memory.subprocess, "run", side_effect=run):
        memory._call(s, "recall", query=s["claims"]["TEST-claim"]["text"])
    assert seen["encoding"] == "utf-8" and "text" not in seen and seen["input"].isascii()
    assert seen["argv"][-1].endswith("sidecar.mjs") and json.loads(seen["input"])["dry_run"] is False
    repo_store = memory.Path(memory.__file__).resolve().parents[3] / "TEST-store"
    monkeypatch.setenv("QUORUM_HMEM_DIR", str(repo_store))
    with patch.object(memory.subprocess, "run", side_effect=AssertionError("ran with a store inside the repository")), pytest.raises(ValueError):
        memory._call(s, "recall", query="TEST")
    assert not repo_store.exists()
