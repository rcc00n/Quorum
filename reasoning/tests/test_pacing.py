"""Pacing of live model calls (2026-10-24, from three live runs' journals): the lanes' base intervals, the one retry
on HTTP 429, the route interval that doubles once and steps back after clean calls, the stop on the second refused
call within 10 minutes (RateLimitAbort, exit 3), the rate-limit headers kept in the ledger row, the journal repair and
the replay of journalled answers on --resume.

No credits, no network and no real waiting: the client is a fake that raises the SDK's own exception types, and
`time.sleep` / `time.monotonic` are replaced by a fake clock that only records and advances.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, RateLimitError

from quorum_reasoning import llm

MODEL = "nvidia/test-model"


def _completion(content: str = '{"ok": true}'):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2, completion_tokens_details=None)
    choice = SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
    return SimpleNamespace(model=MODEL, choices=[choice], usage=usage, model_extra={})


def _rate_limited(headers: dict | None = None) -> RateLimitError:
    request = httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")
    response = httpx.Response(429, headers=headers or {}, request=request)
    return RateLimitError("Too Many Requests", response=response, body={"status": 429, "title": "Too Many Requests"})


def _status_error(status: int) -> APIStatusError:
    request = httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")
    return APIStatusError("upstream said no", response=httpx.Response(status, request=request), body=None)


class _FakeClient:
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


class _Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(llm.time, "sleep", c.sleep)
    monkeypatch.setattr(llm.time, "monotonic", c.monotonic)
    llm.reset_pacing()
    yield c
    llm.reset_pacing()


@pytest.fixture
def fake_route_env(monkeypatch):
    monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("MODEL_API_KEY", "test-token-not-real")
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)
    monkeypatch.setattr(llm, "_loaded", True)


@pytest.fixture
def live(clock, fake_route_env, monkeypatch):
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS", raising=False)
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", raising=False)
    monkeypatch.setattr(llm, "_loaded", True)
    monkeypatch.setattr(llm, "_route", lambda which="default": ("http://127.0.0.1:9/v1", "test-token-not-real", MODEL))
    llm.reset_calls()

    def install(script):
        client = _FakeClient(script)
        monkeypatch.setattr(llm, "_client", lambda: client)
        return client

    yield install
    llm.reset_calls()


def test_base_intervals_from_config(monkeypatch):
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS", raising=False)
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", raising=False)
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_REVIEWER", raising=False)
    assert llm.min_interval_ms() == 6000
    assert llm.min_interval_ms("fact_checker") == 10000 and llm.min_interval_ms("reviewer") == 10000


def test_one_429_then_success_retries_after_15_s_and_doubles_the_lane_once(live, clock):
    client = live([_rate_limited({"x-ratelimit-remaining": "0", "Authorization": "Bearer secret", "x-other": "1"}), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 2
    assert clock.sleeps == [llm.RETRY_RATE_LIMIT_WAIT_S]  # 15 s already exceed the raised 12 s interval: no throttle wait
    assert llm._effective_interval_ms("default", MODEL) == 12000
    row = llm.calls[-1]
    assert row["attempts"] == 2 and row["served"] == MODEL and "waited 15 s" in row["retried_after"]
    assert row["rate_headers"] == [{"x-ratelimit-remaining": "0"}], "only rate-limit headers, never Authorization"


def test_no_429_means_no_rate_headers_key(live, clock):
    live([_completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert "rate_headers" not in llm.calls[-1]


def test_two_429s_fail_the_call_on_two_attempts(live, clock):
    client = live([_rate_limited(), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2 and clock.sleeps == [15.0]
    row = llm.calls[-1]
    assert row["served"] == "error" and row["attempts"] == 2 and row["http_status"] == 429
    assert row["rate_headers"] == [{}, {}], "one entry per 429 attempt"
    assert llm.error_count() == 1


def test_interval_doubles_only_once(live, clock):
    for _ in range(3):
        llm._note_rate_limited("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 2 * llm.min_interval_ms() == 12000


def test_retry_after_decides_the_retry_wait_capped_at_60_s(live, clock):
    live([_rate_limited({"retry-after": "7"}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps[0] == 7.0
    clock.sleeps.clear()
    clock.now += 100.0
    live([_rate_limited({"retry-after": "300"}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps == [llm.RETRY_MAX_WAIT_S]


def test_timeout_then_429_fails_on_two_attempts(live, clock):
    client = live([APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2 and clock.sleeps[0] == llm.RETRY_DEFAULT_WAIT_S
    assert llm.calls[-1]["attempts"] == 2


def test_second_failed_call_within_10_min_aborts_the_run(live, clock):
    live([_rate_limited()] * 4)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    with pytest.raises(llm.RateLimitAbort) as info:
        llm.json_task("stance", {}, dry_run=False)
    assert not isinstance(info.value, Exception), "the nodes' `except Exception` must not swallow it"
    assert info.value.route == MODEL and info.value.count == 2
    assert str(info.value) == (
        f"route {MODEL} is drained (2 refused calls in 10 min); the bucket refills at ~2-4 requests/min: "
        "wait at least 5 hours, then re-run with --resume"
    )
    assert len(llm.calls) == 2 and all(c["served"] == "error" for c in llm.calls), "the aborting call still has its ledger row"
    assert 150.0 not in clock.sleeps, "no long pause any more"


def test_failed_calls_more_than_10_min_apart_do_not_abort(live, clock):
    live([_rate_limited()] * 2 + [_completion()] + [_rate_limited()] * 2)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    clock.now += 11 * 60
    llm.json_task("stance", {}, dry_run=False)
    with pytest.raises(RateLimitError):  # a refusal, not RateLimitAbort: the previous one is 11 min old
        llm.json_task("stance", {}, dry_run=False)


def test_a_success_between_failures_does_not_reset_the_window(live, clock):
    live([_rate_limited()] * 2 + [_completion()] + [_rate_limited()] * 2)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    llm.json_task("stance", {}, dry_run=False)
    with pytest.raises(llm.RateLimitAbort):
        llm.json_task("stance", {}, dry_run=False)


def test_run_maps_rate_limit_abort_to_exit_3(fake_route_env, monkeypatch, tmp_path, capsys):
    from quorum_reasoning import graph, run as run_cli

    def refuse(*a, **k):
        raise llm.RateLimitAbort(MODEL, 2)

    monkeypatch.setattr(graph, "run_local", refuse)
    assert run_cli.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 3
    err = capsys.readouterr().err
    assert f"refusing to continue: route {MODEL} is drained (2 refused calls in 10 min)" in err
    assert "wait at least 5 hours, then re-run with --resume" in err


def test_unpaced_lane_keeps_the_plain_single_retry_and_never_aborts(live, clock, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    client = live([_rate_limited()] * 6)
    for _ in range(3):
        with pytest.raises(RateLimitError):  # never RateLimitAbort on an unpaced lane
            llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 6 and clock.sleeps == [15.0, 15.0, 15.0]
    assert not llm._lane_interval_by_route and not llm._last_failed_429_at_by_route


def test_failure_window_is_per_route(live, clock, monkeypatch):
    live([_rate_limited()] * 2)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    monkeypatch.setattr(llm, "_route", lambda which="default": ("http://127.0.0.1:9/v1", "test-token-not-real", "nvidia/other-model"))
    live([_rate_limited()] * 2)
    with pytest.raises(RateLimitError):  # the first failure on this route: no abort
        llm.json_task("stance", {}, dry_run=False)


@pytest.mark.parametrize("first", ["timeout", "503"])
def test_server_errors_keep_one_retry_and_leave_the_429_state_alone(live, clock, first):
    err = APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")) if first == "timeout" else _status_error(503)
    client = live([err, err, err, err])
    for _ in range(2):
        with pytest.raises(Exception) as info:
            llm.json_task("stance", {}, dry_run=False)
        assert not isinstance(info.value, llm.RateLimitAbort)
    assert client.attempts == 4
    assert not llm._last_failed_429_at_by_route and not llm._lane_interval_by_route
    assert "rate_headers" not in llm.calls[-1]


def test_clean_calls_step_the_interval_back_to_base(live, clock):
    live([_rate_limited(), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 12000
    # the retried call that was finally served counts as the first successful call of the streak
    live([_completion() for _ in range(llm.LANE_STEP_DOWN_AFTER - 2)])
    for _ in range(llm.LANE_STEP_DOWN_AFTER - 2):
        llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 12000, "14 successful calls: not yet"
    live([_completion() for _ in range(20)])
    llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 6000
    for _ in range(19):
        llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 6000, "never below the configured base"


def test_zero_interval_lane_is_not_adapted(clock, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    llm._note_rate_limited("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 0


def test_dry_run_never_sleeps(clock, monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: pytest.fail("a dry run must not reach the client"))
    llm.json_task("stance", {"claim": "x", "passage": "x"}, dry_run=True)
    assert clock.sleeps == []


def test_throttle_honours_the_raised_interval_on_its_route_only(clock, monkeypatch):
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS", raising=False)
    llm._throttle("default", "lightning")
    llm._throttle("default", "other")  # shared pause only (6 s since the last call anywhere)
    assert clock.sleeps == [6.0]
    llm._note_rate_limited("default", "lightning")
    clock.sleeps.clear()
    llm._throttle("default", "lightning")  # 6 s have passed; the raised 12 s interval needs 6 s more
    assert clock.sleeps == [6.0]
    clock.sleeps.clear()
    clock.now += 7.0
    llm._throttle("default", "other")  # untouched route: its 6 s base has passed, no wait
    assert clock.sleeps == []


def test_verbose_line_names_the_wait_and_the_new_interval(live, clock, monkeypatch, capsys):
    monkeypatch.setattr(llm, "_verbose", lambda: True)
    live([_rate_limited(), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert "429; retry in 15 s; lane interval now 12000 ms" in capsys.readouterr().err


# --- replay from the journal on --resume (Vadim, CANONICAL-DURABLE-01) -------------------------------------


def _journal_two_identical_calls(live, monkeypatch, tmp_path):
    """A first run that made the same request twice and got two different answers, journalled."""
    import json as _json

    path = tmp_path / "run.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live([_completion('{"n": 1}'), _completion('{"n": 2}')])
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 1}
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 2}
    rows = [_json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["reply"] for r in rows] == ['{"n": 1}', '{"n": 2}'] and rows[0]["request_key"] == rows[1]["request_key"]
    assert all("reply" not in c for c in llm.calls), "the reply text stays in the journal, not in the ledger"
    return path, rows


def _resume(path):
    llm.reset_calls()
    return llm.load_journal(path)


def test_identical_requests_replay_in_order_then_go_live(live, clock, monkeypatch, tmp_path):
    path, _ = _journal_two_identical_calls(live, monkeypatch, tmp_path)
    assert _resume(path) == 2
    client = live([_completion('{"n": 3}')])
    clock.sleeps.clear()
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 1}
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 2}
    assert client.attempts == 0 and clock.sleeps == [], "a replay neither paces nor reaches the network"
    assert len(llm.calls) == 2, "a replay adds no ledger row: the restored row already counts it"
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 3}
    assert client.attempts == 1 and len(llm.calls) == 3


def test_a_different_request_is_not_replayed(live, clock, monkeypatch, tmp_path):
    path, _ = _journal_two_identical_calls(live, monkeypatch, tmp_path)
    _resume(path)
    client = live([_completion('{"n": 9}')])
    assert llm.json_task("stance", {"claim": "y"}, dry_run=False) == {"n": 9} and client.attempts == 1


def test_corrupted_reply_falls_back_to_a_live_call(live, clock, monkeypatch, tmp_path):
    import json as _json

    path, rows = _journal_two_identical_calls(live, monkeypatch, tmp_path)
    rows[0]["reply"] = "garbled, no JSON here"
    path.write_text("".join(_json.dumps(r) + "\n" for r in rows[:1]), encoding="utf-8")
    _resume(path)
    client = live([_completion('{"n": 7}')])
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 7} and client.attempts == 1


def test_old_format_journal_replays_nothing(live, clock, monkeypatch, tmp_path):
    import json as _json

    path, rows = _journal_two_identical_calls(live, monkeypatch, tmp_path)
    for r in rows:
        r.pop("reply"), r.pop("request_key")
    path.write_text("".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert _resume(path) == 2 and not llm.replay
    client = live([_completion('{"n": 5}')])
    assert llm.json_task("stance", {"claim": "x"}, dry_run=False) == {"n": 5} and client.attempts == 1


# --- round 3: journal tail, long Retry-After, Nightshift lanes, request keys -------------------------------


def test_append_after_a_truncated_tail_keeps_every_good_row(live, clock, monkeypatch, tmp_path):
    import json as _json

    path = tmp_path / "run.jsonl"
    good = {"task": "stance", "lane": "default", "route": MODEL, "served": MODEL, "attempts": 1}
    path.write_text(_json.dumps(good) + "\n" + _json.dumps(good)[:25], encoding="utf-8")  # the process died mid-write
    monkeypatch.setattr(llm, "journal_path", path)
    live([_completion('{"n": 1}')])
    llm.json_task("stance", {"claim": "x"}, dry_run=False)
    llm.reset_calls()
    assert llm.load_journal(path) == 2, "the first row and the appended one; only the cut line is skipped"
    assert llm.calls[-1].get("request_key") and len(llm.replay) == 1


def test_shared_zero_turns_the_fact_checker_lane_off_too(live, clock, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", raising=False)
    assert llm.min_interval_ms("fact_checker") == 0
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", "7000")
    assert llm.min_interval_ms("fact_checker") == 7000, "the lane's own env still wins"
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER")
    client = live([_rate_limited(), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("verify", {}, dry_run=False, which="fact_checker")
    assert client.attempts == 2 and clock.sleeps == [15.0], "Nightshift: the plain single retry"
    assert not llm._last_failed_429_at_by_route and not llm._lane_interval_by_route


_MESSAGES = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "data"}]


@pytest.mark.parametrize("change", ["prompt", "extras", "temperature", "lane", "route", "payload", "task"])
def test_request_key_covers_everything_that_shapes_a_reply(monkeypatch, change):
    args = dict(task="stance", which="default", model=MODEL, messages=_MESSAGES, temperature=0.1, payload={"claim": "x"})
    before = llm._request_key(**args)
    if change == "prompt":
        args["messages"] = [{"role": "system", "content": "prompt v2"}, _MESSAGES[1]]
    elif change == "extras":
        monkeypatch.setattr(llm, "_request_extras", lambda: {"max_tokens": 999})
    elif change == "temperature":
        args["temperature"] = 0.2
    elif change == "lane":
        args["which"] = "fact_checker"
    elif change == "route":
        args["model"] = "nvidia/other-model"
    elif change == "payload":
        args["payload"] = {"claim": "y"}
    else:
        args["task"] = "extract"
    assert llm._request_key(**args) != before


def test_request_key_is_stable(monkeypatch):
    args = dict(task="stance", which="default", model=MODEL, messages=_MESSAGES, temperature=0.1, payload={"b": 1, "a": 2})
    assert llm._request_key(**args) == llm._request_key(**{**args, "payload": {"a": 2, "b": 1}})


def test_reset_calls_clears_the_replay_queues():
    from collections import deque

    llm.replay["k"] = deque(['{"x": 1}'])
    llm.reset_calls()
    assert llm.replay == {}


def test_load_journal_never_queues_an_error_row(tmp_path):
    import json as _json

    path = tmp_path / "run.jsonl"
    rows = [
        {"task": "stance", "served": "error", "error": "reply carried no JSON object", "request_key": "k1", "reply": '{"x": 1}'},
        {"task": "stance", "served": MODEL, "request_key": "k2", "reply": '{"x": 2}'},
    ]
    path.write_text("".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    llm.reset_calls()
    assert llm.load_journal(path) == 2
    assert "k1" not in llm.replay and list(llm.replay["k2"]) == ['{"x": 2}']
    assert all("reply" not in c for c in llm.calls)
    llm.reset_calls()


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "NaN"])
def test_non_finite_retry_after_counts_as_absent(live, clock, value):
    assert llm._retry_wait(_rate_limited({"retry-after": value})) == llm.RETRY_RATE_LIMIT_WAIT_S
    client = live([_rate_limited({"retry-after": value}), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 2 and clock.sleeps == [15.0]


@pytest.mark.parametrize("value", ["0", "-5"])
def test_zero_or_negative_retry_after_floors_the_first_wait_at_1_s(live, clock, value):
    assert llm._retry_wait(_rate_limited({"retry-after": value})) == 1.0
    live([_rate_limited({"retry-after": value}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps[0] == 1.0  # the raised lane interval (4.8 s) may add a throttle wait after it


def test_seed_journal_loads_replay_without_a_checkpoint(tmp_path, monkeypatch):
    """--seed-journal: a fresh run (no checkpoint) restores its journal's rows and replay queues before starting."""
    import json
    from quorum_reasoning import graph, run as run_cli

    rid = "2026-10-24-russia-ukraine-war-7"
    jdir = tmp_path / "_journal"; jdir.mkdir()
    row = {"task": "stance", "lane": "default", "route": "m", "served": "m", "attempts": 1, "ms": 1, "tokens_in": 1, "tokens_out": 1,
           "request_key": "k" * 64, "reply": "{\"stance\": \"supports\"}", "run_id": rid, "payload": {}}
    (jdir / f"{rid}.jsonl").write_text(json.dumps(row) + chr(10), encoding="utf-8")
    seen = {}

    def fake_run_local(*a, **kw):
        seen["calls"] = len(llm.calls); seen["replay"] = sum(len(q) for q in llm.replay.values()); seen["resume"] = kw.get("resume")
        raise llm.RateLimitAbort("m", 2)  # leave main() through the path it already handles (exit 3); the assertions are on `seen`

    monkeypatch.setattr(graph, "run_local", fake_run_local)
    monkeypatch.setattr(llm, "journal_loaded_for", None)  # main() sets it; restore so no later test keeps a stale ledger
    monkeypatch.setattr(llm, "current_run_id", None)
    monkeypatch.setattr(llm, "journal_path", None)
    monkeypatch.setattr(run_cli, "live_guard", lambda *a, **k: None, raising=False)
    monkeypatch.setenv("QUORUM_DRY_RUN", "0")
    rc = run_cli.main(["--topic", "russia-ukraine-war", "--date", "2026-10-24", "--model", "live", "--attempt", "7", "--seed-journal", "--quiet", "--out", str(tmp_path)])
    assert rc == 3 and seen == {"calls": 1, "replay": 1, "resume": False}, (rc, seen)


def test_plan_keeps_a_seeded_ledger_and_replay(tmp_path, monkeypatch):
    """A journal seeded from an earlier attempt carries that attempt's run_id; plan must not wipe it (attempt 4 regression)."""
    import json
    from quorum_reasoning.nodes import plan
    from quorum_reasoning.state import initial_state

    row = {"task": "stance", "lane": "default", "route": "m", "served": "m", "attempts": 1, "ms": 1, "tokens_in": 1, "tokens_out": 1,
           "request_key": "k" * 64, "reply": "{}", "run_id": "2026-10-24-russia-ukraine-war-3", "payload": {}}
    j = tmp_path / "j.jsonl"; j.write_text(json.dumps(row) + chr(10), encoding="utf-8")
    llm.reset_calls(); llm.load_journal(j)
    st = initial_state("2026-10-24-russia-ukraine-war-4", "russia-ukraine-war", "2026-10-24", dry_run=True)
    monkeypatch.setattr(llm, "journal_loaded_for", "2026-10-24-russia-ukraine-war-4")
    plan.run(st)
    assert len(llm.calls) == 1 and sum(len(q) for q in llm.replay.values()) == 1
    monkeypatch.setattr(llm, "journal_loaded_for", None)
    plan.run(st)
    assert llm.calls == [] and llm.replay == {}  # without the marker the old per-run wipe still applies
    llm.reset_calls()
