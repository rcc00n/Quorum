"""Guards around live mode (work items A1–A3, 2026-10-24): fail-closed `--model live`, the summary consistency
check with a truthful `status`, and the model-call path's retry and ledger accounting.

No credits and no network: the model client is replaced by fakes that raise the SDK's own exception types or
return canned completions. Findings these tests pin come from Vadim's independent fixture run (Issue #2,
NVIDIA-FIRST-01): a dry run labelled live, a summary that said "one story crossed the bar" and "no story
crossed the bar" at once while `status` stayed ok, three HTTP attempts per call behind the ledger's back, and
JSON-parse failures that never reached `model_errors`.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from quorum_reasoning import graph, llm, run as run_cli
from quorum_reasoning.nodes import publish
from quorum_reasoning.state import initial_state

TOPIC, DAY = "russia-ukraine-war", "2026-10-22"
ROUTE_VARS = ("MODEL_BASE_URL", "MODEL_API_KEY", "METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN")


@pytest.fixture
def no_route(monkeypatch):
    for name in ROUTE_VARS:
        monkeypatch.setenv(name, "")
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "_loaded", True)  # do not re-read .env over the cleared variables


@pytest.fixture
def fake_route(monkeypatch):
    monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("MODEL_API_KEY", "test-token-not-real")
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "_loaded", True)


# --- A1: live mode fails closed --------------------------------------------------------------------------


def test_live_without_a_route_exits_2_and_runs_nothing(no_route, monkeypatch, capsys):
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not run"))
    assert run_cli.main(["--model", "live", "--quiet"]) == 2
    assert "no model route is configured" in capsys.readouterr().err


def test_live_with_dry_switch_set_is_an_error(fake_route, monkeypatch, capsys):
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not run"))
    assert run_cli.main(["--model", "live", "--quiet"]) == 2
    assert "QUORUM_DRY_RUN=1" in capsys.readouterr().err


def test_eval_live_fails_closed_too(no_route, capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("eval_cli", Path(__file__).with_name("eval.py"))
    eval_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_cli)  # type: ignore[union-attr]
    assert eval_cli.main(["--live", "--confirm-credits"]) == 2
    assert "no model route" in capsys.readouterr().err


def test_explicit_dry_run_is_unaffected(no_route, tmp_path):
    assert run_cli.main(["--dry-run", "--quiet", "--out", str(tmp_path)]) == 0
    assert (tmp_path / TOPIC / DAY / "v1.json").is_file() and (tmp_path / TOPIC / DAY / "latest.json").is_file()
    assert not (tmp_path / TOPIC / DAY / "v1.ledger.json").exists(), "a dry run makes no live calls, so no ledger"


# --- A2: the summary may not contradict the run's own counts ----------------------------------------------


@pytest.mark.parametrize(
    "summary, above, problem",
    [
        ("One story crossed the bar today. No story crossed the bar today; the roundup carries the day.", 1, "no story"),
        ("No story crossed the bar today out of 5 events.", 0, None),
        ("Two of 9 events crossed the bar today.", 2, None),
        ("Two of 9 events crossed the bar today.", 1, "two"),
        ("3 stories crossed the bar today.", 3, None),
        ("Three stories crossed the bar: a, b and c.", 2, "three"),
        ("No events were seen today.", 2, None),  # no claim about the bar: not for this check to judge
    ],
)
def test_summary_contradiction_detector(summary, above, problem):
    found = publish.summary_contradiction(summary, above)
    if problem is None:
        assert found is None, found
    else:
        assert found and problem in found.lower()


def _state_with_one_story():
    st = graph.run_local(TOPIC, DAY, dry_run=True)
    return st


def test_contradictory_model_summary_is_rejected_and_status_becomes_partial(monkeypatch):
    st = _state_with_one_story()
    assert st["snapshot"]["status"] == "ok" and st["snapshot"]["summary_source"] == "model"
    recorded = {"summary": "One story crossed the bar today. No story crossed the bar today; the roundup carries the day."}
    monkeypatch.setattr(llm, "json_task", lambda task, payload, **kw: recorded if task == "summary" else pytest.fail(task))
    pre = {**st, "snapshot": None, "steps": [s for s in st["steps"] if s["node"] != "publish"], "errors": []}
    out = publish.run(pre)
    snap = out["snapshot"]
    assert snap["status"] == "partial"
    assert snap["summary_source"] == "fallback"
    assert publish.summary_contradiction(snap["summary"], len(snap["stories"])) is None
    assert any(e["node"] == "publish" and "summary rejected" in e["message"] for e in snap["errors"])
    assert out["errors"] and out["errors"][0]["node"] == "publish"


def test_failed_summary_call_is_an_error_not_a_silent_fallback(monkeypatch):
    st = _state_with_one_story()

    def boom(task, payload, **kw):
        raise RuntimeError("HTTP 500 from the route")

    monkeypatch.setattr(llm, "json_task", boom)
    pre = {**st, "snapshot": None, "steps": [s for s in st["steps"] if s["node"] != "publish"], "errors": []}
    snap = publish.run(pre)["snapshot"]
    assert snap["status"] == "partial" and snap["summary_source"] == "fallback"
    assert any("summary model call failed" in e["message"] for e in snap["errors"])


def test_dry_run_summary_agrees_with_the_counts():
    st = _state_with_one_story()
    snap = st["snapshot"]
    assert snap["summary_source"] == "model"
    assert publish.summary_contradiction(snap["summary"], len(snap["stories"])) is None
    assert snap["status"] == "ok" and snap["errors"] == []


# --- A3: one explicit retry, complete ledger rows, parse failures counted --------------------------------


def _completion(content: str, *, model="nvidia/test-model", finish="stop", tokens=(100, 20)):
    usage = SimpleNamespace(prompt_tokens=tokens[0], completion_tokens=tokens[1], completion_tokens_details=SimpleNamespace(reasoning_tokens=0))
    choice = SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))
    return SimpleNamespace(model=model, choices=[choice], usage=usage, model_extra={})


def _status_error(status: int, headers: dict | None = None) -> APIStatusError:
    request = httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")
    response = httpx.Response(status, headers=headers or {}, request=request)
    return APIStatusError("upstream said no", response=response, body=None)


class _FakeClient:
    """Stands in for the OpenAI client: answers from a script of exceptions or completions, in order."""

    def __init__(self, script):
        self.script = list(script)
        self.attempts = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=self._create)))

    def _create(self, **kwargs):
        self.attempts += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(parse=lambda: item, status_code=200)


@pytest.fixture
def live_calls(fake_route, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # the retry's wait is recorded, not spent
    llm.reset_calls()

    def install(script):
        client = _FakeClient(script)
        monkeypatch.setattr(llm, "_client", lambda: client)
        return client

    return install


def test_one_retry_on_429_honours_retry_after(live_calls):
    client = live_calls([_status_error(429, {"retry-after": "7"}), _completion('{"stance": "supports"}')])
    out = llm.json_task("stance", {"claim": "x", "passage": "x"}, dry_run=False)
    assert out == {"stance": "supports"} and client.attempts == 2
    row = llm.calls[-1]
    assert row["attempts"] == 2 and "waited 7 s" in row["retried_after"] and "429" in row["retried_after"]
    assert row["http_status"] == 200 and row["finish_reason"] == "stop" and (row["tokens_in"], row["tokens_out"]) == (100, 20)
    assert row["served"] == "nvidia/test-model" and "error" not in row


def test_second_failure_is_final_two_attempts_at_most(live_calls):
    client = live_calls([_status_error(503), _status_error(503), _completion("{}")])
    with pytest.raises(APIStatusError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2
    row = llm.calls[-1]
    assert row["served"] == "error" and row["http_status"] == 503 and row["attempts"] == 2
    assert llm.error_count() == 1


def test_client_errors_other_than_429_are_not_retried(live_calls):
    client = live_calls([_status_error(400), _completion("{}")])
    with pytest.raises(APIStatusError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 1 and llm.calls[-1]["attempts"] == 1


def test_timeout_gets_the_one_retry(live_calls):
    client = live_calls([APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")), _completion('{"ok": true}')])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 2 and llm.calls[-1]["attempts"] == 2


def test_reply_without_json_is_a_counted_error_with_its_finish_reason(live_calls):
    live_calls([_completion("I cannot answer that in JSON", finish="length")])
    with pytest.raises(ValueError, match="no JSON"):
        llm.json_task("stance", {}, dry_run=False)
    row = llm.calls[-1]
    assert row["served"] == "nvidia/test-model" and row["finish_reason"] == "length" and "no JSON" in row["error"]
    assert llm.error_count() == 1
    assert sum(llm.served_counts().values()) == len(llm.calls) == 1  # provenance stays consistent for the portal's parser


def test_ledger_is_written_next_to_the_snapshot_never_inside_it(fake_route, monkeypatch, tmp_path):
    """A live run's ledger lands in the private output directory; the snapshot carries only the counts."""
    from quorum_reasoning import store

    llm.reset_calls()
    llm.calls.append({"task": "summary", "lane": "default", "route": "r", "served": "nvidia/test-model", "ms": 1, "attempts": 1, "http_status": 200, "finish_reason": "stop", "tokens_in": 1, "tokens_out": 1})
    snap = {"topic_id": TOPIC, "edition_date": DAY, "version": 1, "published_at": None, "run_id": "r"}
    path, version = store.publish(snap, tmp_path, ledger=llm.calls)
    assert version == 1 and path == tmp_path / TOPIC / DAY / "v1.json"
    ledger = run_cli.ledger_path(tmp_path, TOPIC, DAY, version)
    assert ledger == tmp_path / TOPIC / DAY / "v1.ledger.json"
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert data["calls"][0]["http_status"] == 200
    assert "calls" not in json.loads(path.read_text(encoding="utf-8"))
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    env_json = json.dumps(publish.envelope(st))
    assert "http_status" not in env_json and "finish_reason" not in env_json and '"task"' not in env_json
    assert publish.envelope(st)["provenance"]["model_calls"] == 1
    llm.reset_calls()


# --- per-lane pacing (2026-10-24, from the first genuine run) ----------------------------------------------


def test_lane_pacing_reads_lane_config_then_env_then_shared(monkeypatch):
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS", raising=False)
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", raising=False)
    assert llm.min_interval_ms() == int(llm.config.get("models", "min_interval_ms"))
    assert llm.min_interval_ms("fact_checker") == int(llm.config.get("models", "min_interval_ms_fact_checker")) > llm.min_interval_ms()
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", "0")
    assert llm.min_interval_ms("fact_checker") == 0, "the lane's env override wins (Nightshift paces upstream)"
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    assert llm.min_interval_ms() == 0 and llm.min_interval_ms("reviewer") == int(llm.config.get("models", "min_interval_ms_reviewer"))


def test_throttle_waits_per_route_not_only_per_process(monkeypatch):
    waits = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: waits.append(round(s, 1)))
    monkeypatch.setattr(llm, "min_interval_ms", lambda which="default": 0 if which == "default" else 4000)
    llm._last_call_by_route.clear()
    llm._throttle("fact_checker", "ultra")
    llm._throttle("default", "lightning")  # another route: no lane wait
    llm._throttle("fact_checker", "ultra")  # same route again within 4 s: waits
    assert len(waits) == 1 and 3.0 <= waits[0] <= 4.0


def test_rate_limit_retry_waits_longer_than_a_server_error():
    assert llm._retry_wait(_status_error(429)) == llm.RETRY_RATE_LIMIT_WAIT_S > llm._retry_wait(_status_error(503))
    assert llm._retry_wait(_status_error(429, {"retry-after": "7"})) == 7.0
