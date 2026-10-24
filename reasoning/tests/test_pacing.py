"""Adaptive pacing of live model calls (2026-10-24, from the journals of two live runs): the default lane's base
interval, the per-route interval that doubles on HTTP 429 and steps back down after clean calls, the 150 s pause
after two 429s in a row with its one extra attempt, and the rate-limit headers kept in the ledger row.

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
    assert llm.min_interval_ms() == 2400
    assert llm.min_interval_ms("fact_checker") == 4000


def test_one_429_then_success_retries_after_15_s_and_doubles_the_lane(live, clock):
    client = live([_rate_limited({"x-ratelimit-remaining": "0", "Authorization": "Bearer secret", "x-other": "1"}), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 2
    assert clock.sleeps == [llm.RETRY_RATE_LIMIT_WAIT_S]  # the retry is 15 s after the first attempt: no extra throttle wait
    assert llm._effective_interval_ms("default", MODEL) == 4800
    row = llm.calls[-1]
    assert row["attempts"] == 2 and row["served"] == MODEL and "waited 15 s" in row["retried_after"]
    assert row["rate_headers"] == [{"x-ratelimit-remaining": "0"}], "only rate-limit headers, never Authorization"


def test_no_429_means_no_rate_headers_key(live, clock):
    live([_completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert "rate_headers" not in llm.calls[-1]


def test_two_429s_pause_150_s_then_third_attempt_is_served(live, clock):
    client = live([_rate_limited(), _rate_limited(), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 3
    assert clock.sleeps == [15.0, 150.0]
    row = llm.calls[-1]
    assert row["attempts"] == 3 and row["served"] == MODEL and row["http_status"] == 200
    assert row["rate_headers"] == [{}, {}], "one entry per 429 attempt"
    assert not llm._pause_next_by_route.get(MODEL) and not llm._failed_429_calls_by_route.get(MODEL)


def test_three_429s_fail_after_the_pause(live, clock):
    client = live([_rate_limited(), _rate_limited(), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 3 and clock.sleeps == [15.0, 150.0]
    row = llm.calls[-1]
    assert row["served"] == "error" and row["attempts"] == 3 and row["http_status"] == 429 and len(row["rate_headers"]) == 3
    assert llm.error_count() == 1
    assert llm._effective_interval_ms("default", MODEL) == llm.LANE_INTERVAL_CAP_MS  # 2400 → 4800 → 9600 → cap


def test_retry_after_wins_for_the_first_wait_and_the_long_pause_still_holds(live, clock):
    live([_rate_limited({"retry-after": "7"}), _rate_limited({"retry-after": "7"}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps == [7.0, 150.0], "the wait before attempt 3 is max(Retry-After, 150 s)"
    assert llm.calls[-1]["rate_headers"] == [{"retry-after": "7"}, {"retry-after": "7"}]


def test_timeout_then_429_gets_no_third_attempt(live, clock):
    client = live([APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2 and clock.sleeps == [llm.RETRY_DEFAULT_WAIT_S]
    assert llm.calls[-1]["attempts"] == 2


def test_call_after_a_failed_call_pauses_once_then_fails_on_two_attempts(live, clock):
    live([_rate_limited(), _rate_limited(), _rate_limited()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    clock.sleeps.clear()
    client = live([_rate_limited(), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2
    assert clock.sleeps[:2] == [150.0, 15.0] and len(clock.sleeps) == 2, clock.sleeps  # not [10, 150, 150]
    assert llm.calls[-1]["attempts"] == 2 and llm.calls[-1]["served"] == "error"


def test_breaker_stops_the_run_on_the_third_consecutive_failed_call(live, clock):
    live([_rate_limited()] * 7)
    for _ in range(2):
        with pytest.raises(RateLimitError):
            llm.json_task("stance", {}, dry_run=False)
    with pytest.raises(llm.RateLimitAbort) as info:
        llm.json_task("stance", {}, dry_run=False)
    assert not isinstance(info.value, Exception), "the nodes' `except Exception` must not swallow it"
    assert info.value.route == MODEL and info.value.count == 3
    assert len(llm.calls) == 3 and all(c["served"] == "error" for c in llm.calls), "the aborting call still has its ledger row"


def test_a_success_resets_the_breaker(live, clock):
    live([_rate_limited()] * 5 + [_completion()] + [_rate_limited()] * 3)
    for _ in range(2):
        with pytest.raises(RateLimitError):
            llm.json_task("stance", {}, dry_run=False)
    llm.json_task("stance", {}, dry_run=False)  # 150 s pause, then served
    with pytest.raises(RateLimitError):  # not RateLimitAbort: the streak was broken
        llm.json_task("stance", {}, dry_run=False)


def test_run_maps_rate_limit_abort_to_exit_3(fake_route_env, monkeypatch, tmp_path, capsys):
    from quorum_reasoning import graph, run as run_cli

    def refuse(*a, **k):
        raise llm.RateLimitAbort(MODEL, 3)

    monkeypatch.setattr(graph, "run_local", refuse)
    assert run_cli.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 3
    err = capsys.readouterr().err
    assert f"refusing to continue: route {MODEL} refused 3 consecutive calls; wait a few minutes, then re-run with --resume" in err


def test_unpaced_lane_keeps_the_plain_single_retry(live, clock, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    client = live([_rate_limited(), _rate_limited(), _completion()] + [_rate_limited()] * 6)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2 and clock.sleeps == [15.0]
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert clock.sleeps == [15.0], "no pause before the next call, no adaptive wait"
    for _ in range(3):
        with pytest.raises(RateLimitError):  # never RateLimitAbort on an unpaced lane
            llm.json_task("stance", {}, dry_run=False)
    assert 150.0 not in clock.sleeps


def test_pause_counter_is_per_route(live, clock, monkeypatch):
    live([_rate_limited()] * 3)
    with pytest.raises(RateLimitError):
        llm.json_task("stance", {}, dry_run=False)
    assert llm._pause_next_by_route.get(MODEL)
    monkeypatch.setattr(llm, "_route", lambda which="default": ("http://127.0.0.1:9/v1", "test-token-not-real", "nvidia/other-model"))
    clock.sleeps.clear()
    clock.now += 100.0
    client = live([_rate_limited(), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 2 and clock.sleeps == [15.0], "a 429 history on another route causes no pause"


@pytest.mark.parametrize("first", ["timeout", "503"])
def test_server_errors_keep_one_retry_and_leave_the_429_counters_alone(live, clock, first):
    err = APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")) if first == "timeout" else _status_error(503)
    client = live([err, err, _completion()])
    with pytest.raises(Exception):
        llm.json_task("stance", {}, dry_run=False)
    assert client.attempts == 2 and clock.sleeps == [llm.RETRY_DEFAULT_WAIT_S]
    assert not llm._pause_next_by_route and not llm._failed_429_calls_by_route and not llm._lane_interval_by_route
    assert "rate_headers" not in llm.calls[-1]


def test_clean_calls_step_the_interval_down_never_below_base(live, clock):
    live([_rate_limited(), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 4800
    # the retried call that was finally served counts as the first successful call of the streak
    live([_completion() for _ in range(llm.LANE_STEP_DOWN_AFTER - 2)])
    for _ in range(llm.LANE_STEP_DOWN_AFTER - 2):
        llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 4800, "14 successful calls: not yet"
    live([_completion() for _ in range(3 * llm.LANE_STEP_DOWN_AFTER)])
    llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 2400
    for _ in range(3 * llm.LANE_STEP_DOWN_AFTER - 1):
        llm.json_task("stance", {}, dry_run=False)
    assert llm._effective_interval_ms("default", MODEL) == 2400, "never below the configured base"


def test_step_down_halves_once_per_15_calls(clock, monkeypatch):
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS", raising=False)
    for _ in range(3):
        llm._note_rate_limited("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 10_000
    for _ in range(llm.LANE_STEP_DOWN_AFTER):
        llm._note_success("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 5000
    for _ in range(llm.LANE_STEP_DOWN_AFTER):
        llm._note_success("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 2500
    for _ in range(llm.LANE_STEP_DOWN_AFTER):
        llm._note_success("default", MODEL)
    assert llm._effective_interval_ms("default", MODEL) == 2400


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
    llm._throttle("default", "other")  # shared pause only (2.4 s since the last call anywhere)
    assert clock.sleeps == [2.4]
    llm._note_rate_limited("default", "lightning")
    clock.sleeps.clear()
    llm._throttle("default", "lightning")  # 2.4 s have passed; the raised 4.8 s interval needs 2.4 s more
    assert clock.sleeps == [2.4]
    clock.sleeps.clear()
    clock.now += 3.0
    llm._throttle("default", "other")  # untouched route: its 2.4 s base has passed, no wait
    assert clock.sleeps == []


def test_verbose_line_names_the_wait_and_the_new_interval(live, clock, monkeypatch, capsys):
    monkeypatch.setattr(llm, "_verbose", lambda: True)
    live([_rate_limited(), _rate_limited(), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    err = capsys.readouterr().err
    assert "429; retry in 15 s; lane interval now 4800 ms" in err
    assert "429 again; lane paused 150 s; lane interval now 9600 ms" in err


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


def test_long_retry_after_sets_the_long_pause(live, clock):
    live([_rate_limited({"retry-after": "300"}), _rate_limited({"retry-after": "300"}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps == [llm.RETRY_MAX_WAIT_S, 300.0], "first wait capped at 60 s; the long pause is max(Retry-After, 150 s)"


def test_long_pause_is_capped(live, clock):
    live([_rate_limited({"retry-after": "5000"}), _rate_limited({"retry-after": "5000"}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps == [llm.RETRY_MAX_WAIT_S, llm.RATE_LIMIT_PAUSE_MAX_S]


def test_shared_zero_turns_the_fact_checker_lane_off_too(live, clock, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", raising=False)
    assert llm.min_interval_ms("fact_checker") == 0
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", "4000")
    assert llm.min_interval_ms("fact_checker") == 4000, "the lane's own env still wins"
    monkeypatch.delenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER")
    client = live([_rate_limited(), _rate_limited(), _completion()])
    with pytest.raises(RateLimitError):
        llm.json_task("verify", {}, dry_run=False, which="fact_checker")
    assert client.attempts == 2 and clock.sleeps == [15.0], "Nightshift: the plain single retry, no pause"
    assert not llm._pause_next_by_route and not llm._failed_429_calls_by_route


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
    assert llm._retry_after_seconds(_rate_limited({"retry-after": value})) is None
    assert llm._retry_wait(_rate_limited({"retry-after": value})) == llm.RETRY_RATE_LIMIT_WAIT_S
    client = live([_rate_limited({"retry-after": value}), _rate_limited({"retry-after": value}), _completion()])
    assert llm.json_task("stance", {}, dry_run=False) == {"ok": True}
    assert client.attempts == 3 and clock.sleeps == [15.0, 150.0]


@pytest.mark.parametrize("value", ["0", "-5"])
def test_zero_or_negative_retry_after_floors_the_first_wait_at_1_s(live, clock, value):
    assert llm._retry_wait(_rate_limited({"retry-after": value})) == 1.0
    live([_rate_limited({"retry-after": value}), _completion()])
    llm.json_task("stance", {}, dry_run=False)
    assert clock.sleeps[0] == 1.0  # the raised lane interval (4.8 s) may add a throttle wait after it
