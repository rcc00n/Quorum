"""The Meterless route (2026-10-25): env aliases and the 8088 default, the thinking switch in the body on both routes,
the replay-key partition, the exact-lane check on pinned lanes, the H-MEM disclosure and rejection, the daemon setpoint
that turns H-MEM injection off before the first call, and `--test-connection` output.

No network and no credits: the client is a fake returning SimpleNamespace completions shaped like the SDK's, and the
daemon's control plane is a fake `llm._control_http` or `llm._control_exchange`. The real pipe is never opened: the
suite-wide guard in tests/conftest.py (per test, and for the whole session: imports and fixtures of every scope) fails
any test that reaches `llm._control_exchange` unfaked or hands the daemon's real pipe name to `llm._open_pipe` or
`llm._wait_named_pipe` (proved by
test_suite_guard_fails_a_test_that_forgets_the_stub), and the `_control_exchange` tests ask for its
`real_control_exchange` fixture and replace `open` inside llm.
"""

from __future__ import annotations

import errno
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from quorum_reasoning import graph, ids, llm, run

# captured at import, before any fixture replaces it (the three guarded seams come from the unguarded_control_seams
# fixture: the session guard in tests/conftest.py replaces them before this module is imported)
_REAL_CONTROL_HTTP = llm._control_http
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
ENV_NAMES = ("MODEL_BASE_URL", "MODEL_API_KEY", "METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN", "METERLESS_TOKEN",
             "NEMOTRON_MODEL", "NEMOTRON_MODEL_FACT_CHECKER", "NEMOTRON_MODEL_REVIEWER", "METERLESS_MODEL", "QUORUM_DRY_RUN")
FAKE_PIPE = r"\\.\pipe\quorum-test-no-such-pipe"
# what the setter sends, in order: the snapshot, the switch, the read-back
SETTER_REQUESTS = [("GET", "/admin/setpoints", None), ("POST", "/admin/setpoints", {"hmemKnowledge": False}), ("GET", "/admin/setpoints", None)]
ABSENT = object()  # a read-back document without the hmemKnowledge key (unlike an explicit JSON null)
_FROM_STATE = object()


@pytest.fixture
def env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "_loaded", True)  # never read the real .env
    monkeypatch.setenv("METERLESS_CONTROL_SOCKET", FAKE_PIPE)  # the name the failure messages below are checked for
    return monkeypatch  # an unfaked control-plane request fails the test (tests/conftest.py)


class _ControlPlane:
    """A fake daemon control plane holding a setpoints document: records every request; GET answers the document, POST
    merges its body into it (or replaces the document, `replace=True`). `readback` overrides hmemKnowledge in the GETs
    right after a POST (ABSENT drops the key); `readback_status` is those GETs' status, `get_status` every other GET's.
    `unwritten` is a daemon whose setpoints were never written: until a POST, GET answers `{"setpoints": null}`
    ("wrapped") or a bare null ("bare"). `raise_on` drops the pipe on the POST ("POST") or on the read-back ("readback")."""

    def __init__(self, readback=_FROM_STATE, post_status=200, get_status=200, readback_status=200, unreachable=False,
                 events=None, before=None, replace=False, unwritten=None, raise_on=None):
        self.requests: list[tuple[str, str, object]] = []
        self.state = None if unwritten else dict({"hmemKnowledge": True, "hmemTopK": 3} if before is None else before)
        self.readback, self.post_status, self.get_status, self.readback_status = readback, post_status, get_status, readback_status
        self.unreachable, self.replace, self.unwritten, self.raise_on = unreachable, replace, unwritten, raise_on
        self.events = events if events is not None else []

    def __call__(self, method, path, body=None):
        self.requests.append((method, path, body))
        self.events.append(f"control {method}")
        if self.unreachable:
            raise FileNotFoundError(2, "The system cannot find the file specified", FAKE_PIPE)
        readback = method == "GET" and len(self.requests) >= 2 and self.requests[-2][0] == "POST"
        if self.raise_on == method or (readback and self.raise_on == "readback"):
            raise BrokenPipeError(32, "Broken pipe")
        if method == "POST":
            self.state = dict(body or {}) if self.replace else {**(self.state or {}), **(body or {})}
            return self.post_status, {"setpoints": dict(self.state), "engines_notified": 1}
        if self.state is None:
            return self.get_status, ({"setpoints": None} if self.unwritten == "wrapped" else None)
        doc = dict(self.state)
        if readback and self.readback is not _FROM_STATE:
            if self.readback is ABSENT:
                doc.pop("hmemKnowledge", None)
            else:
                doc["hmemKnowledge"] = self.readback
        return (self.readback_status if readback else self.get_status), {"setpoints": doc}


@pytest.fixture
def control(env):
    def install(**kwargs):
        plane = _ControlPlane(**kwargs)
        env.setattr(llm, "_control_http", plane)
        return plane

    return install


def _met(requested: str, provider: str | None, routed: str | None, hmem: dict | None = None, from_cache: bool = False) -> dict:
    met = {"receipt_id": "rcpt_test_1", "requested_model": requested, "from_cache": from_cache,
           "receipt": {"hmem": hmem}}
    if provider is not None:
        met["provider_model"] = provider
    if routed is not None:
        met["routed_model"] = routed
    return met


def _completion(model: str, met: dict | None, content: str = '{"stance": "neutral", "reason": "r"}', finish_reason: str = "stop"):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None)
    choice = SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))
    return SimpleNamespace(model=model, choices=[choice], usage=usage, model_extra={"meterless": met} if met is not None else {})


class _Client:
    def __init__(self, completion):
        self.completion = completion
        self.kwargs: list[dict] = []
        create = self._create
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create, with_raw_response=SimpleNamespace(create=self._raw)))

    def _create(self, **kwargs):
        self.kwargs.append(kwargs)
        return self.completion

    def _raw(self, **kwargs):
        self.kwargs.append(kwargs)
        return SimpleNamespace(parse=lambda: self.completion, status_code=200)


# 1. env aliases --------------------------------------------------------------------------------------------------

def test_meterless_token_alias_and_8088_default(env):
    env.setenv("METERLESS_TOKEN", "test-token-not-real")
    env.setenv("NEMOTRON_MODEL", LIGHTNING)
    base, key, model = llm._route()
    assert base == "http://127.0.0.1:8088/v1" and key == "test-token-not-real" and model == LIGHTNING
    assert llm.route_configured() and llm.on_meterless()


def test_runtime_token_wins_over_alias_and_explicit_url_is_kept(env):
    env.setenv("METERLESS_RUNTIME_TOKEN", "runtime-token")
    env.setenv("METERLESS_TOKEN", "alias-token")
    env.setenv("METERLESS_BASE_URL", "http://127.0.0.1:9999/v1")
    base, key, _ = llm._route()
    assert (base, key) == ("http://127.0.0.1:9999/v1", "runtime-token")


def test_model_vars_keep_precedence(env):
    env.setenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    env.setenv("MODEL_API_KEY", "direct-key")
    env.setenv("METERLESS_TOKEN", "alias-token")
    base, key, _ = llm._route()
    assert (base, key) == ("https://integrate.api.nvidia.com/v1", "direct-key")
    assert not llm.on_meterless()


def test_model_key_without_url_gets_no_meterless_default(env):
    env.setenv("MODEL_API_KEY", "direct-key")
    env.setenv("METERLESS_TOKEN", "alias-token")
    assert llm._route()[0] == ""  # unchanged behaviour: a half-configured MODEL_* pair is not silently sent to 8088


# 2. request extras on both routes ----------------------------------------------------------------------------------

@pytest.mark.parametrize("base", ["http://127.0.0.1:8088/v1", "https://integrate.api.nvidia.com/v1"])
def test_thinking_off_and_nonempty_content_on_both_routes(env, base):
    env.setenv("MODEL_BASE_URL", base)
    env.setenv("MODEL_API_KEY", "k")
    kwargs = llm._request_extras()["extra_body"]["chat_template_kwargs"]
    assert kwargs == {"enable_thinking": False, "force_nonempty_content": True}


def test_replay_keys_differ_between_routes_and_direct_keys_unchanged(env, monkeypatch):
    args = dict(task="stance", which="default", model=LIGHTNING, messages=[{"role": "system", "content": "s"}], temperature=0.1, payload={"a": 1})
    env.setenv("MODEL_API_KEY", "k")
    env.setenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    direct = llm._request_key(**args)
    monkeypatch.setattr(llm, "on_meterless", lambda: False)
    assert llm._request_key(**args) == direct  # the direct key has no endpoint marker
    monkeypatch.setattr(llm, "on_meterless", lambda: True)
    assert llm._request_key(**args) != direct


# 3. exact-lane check -----------------------------------------------------------------------------------------------

# DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every `live` test runs once per Meterless family: the Runtime
# token alone (METERLESS_TOKEN, the 8088 default) and the MODEL_* pair pointed at the runtime (.env.example). Why:
# review round 6: with the token family only, gating the setter or the rejection on the Meterless token instead of on
# the route (`llm.on_meterless()`) left the suite green while a MODEL_* run started with injection on.
METERLESS_FAMILIES = {
    "meterless-token": {"METERLESS_TOKEN": "test-token-not-real"},
    "model-pair": {"MODEL_BASE_URL": "http://127.0.0.1:8088/v1", "MODEL_API_KEY": "test-key-not-real"},
}


@pytest.fixture(params=list(METERLESS_FAMILIES))
def live(request, env, monkeypatch):
    for name, value in METERLESS_FAMILIES[request.param].items():
        env.setenv(name, value)
    assert llm.on_meterless() and llm.route_configured()
    env.setenv("NEMOTRON_MODEL", LIGHTNING)
    env.setenv("NEMOTRON_MODEL_FACT_CHECKER", ULTRA)
    env.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    monkeypatch.setattr(llm, "journal_path", None)
    llm.reset_calls()
    llm.reset_pacing()

    def install(completion):
        client = _Client(completion)
        monkeypatch.setattr(llm, "_client", lambda: client)
        return client

    yield install
    llm.reset_calls()


def test_held_lane_is_served_and_discloses_hmem_and_cache(live):
    # 2026-10-25: hmem.injected 0 here; an injected count above 0 is now rejected (test_injected_memories_* below)
    client = live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 0, "strategy": "comprehensive"})))
    out = llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert out["stance"] == "neutral"
    row = llm.calls[-1]
    assert row["served"] == ULTRA and row["receipt_id"] == "rcpt_test_1"
    assert row["receipt_hmem_injected"] == 0 and row["receipt_from_cache"] is False
    assert llm.substitution_count() == 0
    assert client.kwargs[0]["model"] == ULTRA


@pytest.mark.parametrize("provider,routed", [(ULTRA, LIGHTNING), ("meterless/fast", LIGHTNING), (LIGHTNING, None)])
def test_substituted_lane_is_an_error_row_and_raises(live, provider, routed):
    live(_completion(routed or provider, _met(ULTRA, provider, routed)))
    with pytest.raises(llm.RouteSubstituted, match="route substituted"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["route_substituted"] is True
    assert row["error"] == f"route substituted {row['answered_model']} for {ULTRA}"
    assert llm.substitution_count() == 1 and llm.error_count() == 1
    assert llm.served_counts() == {"error": 1}


def test_substitution_is_skipped_per_passage_like_any_failed_call(live):
    assert issubclass(llm.RouteSubstituted, Exception) and not issubclass(llm.RouteSubstituted, llm.RateLimitAbort)


def test_substituted_reply_is_not_journalled_for_replay(live, tmp_path, monkeypatch):
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(LIGHTNING, _met(ULTRA, ULTRA, LIGHTNING)))
    with pytest.raises(llm.RouteSubstituted):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


def test_disposition_routes_are_not_checked(live, monkeypatch):
    monkeypatch.setenv("NEMOTRON_MODEL", "meterless/fast")
    live(_completion("meterless/fast", _met("meterless/fast", "meterless/fast", LIGHTNING)))
    llm.json_task("stance", {"claim": "c"}, dry_run=False)
    assert llm.calls[-1]["served"] == LIGHTNING and llm.substitution_count() == 0


def test_direct_route_response_without_meterless_object(live):
    live(_completion(LIGHTNING, None))
    llm.json_task("stance", {"claim": "c"}, dry_run=False)
    row = llm.calls[-1]
    assert row["served"] == LIGHTNING and "receipt_hmem_injected" not in row and "receipt_from_cache" not in row


def test_hmem_read_from_signed_envelope_and_absent_block():
    env_met = {"receipt_envelope": {"body": {"receipt": {"hmem": {"injected": 3}}}}}
    assert llm._hmem_injected(env_met) == 3
    assert llm._hmem_injected({"receipt": {"hmem": None}}) == 0
    assert llm._hmem_injected({}) is None
    # round 7: a non-empty meterless object with no receipt and no top-level hmem has no count (not 0: nothing says so)
    assert llm._hmem_report({"receipt_id": "r", "provider_model": ULTRA}) == (None, None)
    assert llm._hmem_report({"receipt_id": "r", "receipt": None, "receipt_envelope": None}) == (None, None)  # JSON nulls


# 5. --test-connection ----------------------------------------------------------------------------------------------

def test_test_connection_prints_provider_model_and_receipt_per_lane(live, control, monkeypatch, capsys):
    completions = {LIGHTNING: _completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING, hmem={"injected": 0}), "ready"),
                   ULTRA: _completion(LIGHTNING, _met(ULTRA, ULTRA, LIGHTNING), "ready")}
    events: list[str] = []
    plane = control(events=events)

    class _PerModel(_Client):
        def _create(self, **kwargs):
            self.kwargs.append(kwargs)
            events.append("completion")
            return completions[kwargs["model"]]

    client = _PerModel(None)
    monkeypatch.setattr(llm, "_client", lambda: client)
    assert run.main(["--test-connection"]) == 0
    out = capsys.readouterr().out
    assert f"provider_model {LIGHTNING}" in out and "receipt_id rcpt_test_1" in out and "lane held" in out
    assert f"SUBSTITUTED by {LIGHTNING}" in out  # the fact-checker lane answered from Lightning
    assert all(k["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False for k in client.kwargs)
    assert events == ["control GET", "control POST", "control GET", "completion", "completion"]  # the setpoint before the first call
    assert plane.requests == SETTER_REQUESTS


# review round (2026-10-25) ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("setup,needle", [
    ({"MODEL_BASE_URL": "https://integrate.api.nvidia.com/v1", "METERLESS_TOKEN": "t"}, "NVIDIA base URL with a Meterless token"),
    ({"METERLESS_BASE_URL": "https://integrate.api.nvidia.com/v1", "METERLESS_RUNTIME_TOKEN": "t"}, "NVIDIA base URL with a Meterless token"),
    ({"METERLESS_BASE_URL": "http://127.0.0.1:8088/v1", "MODEL_API_KEY": "k"}, "METERLESS_BASE_URL with MODEL_API_KEY"),
])
def test_mixed_pairs_are_not_a_route_and_live_mode_names_them(env, setup, needle):
    for name, value in setup.items():
        env.setenv(name, value)
    assert not llm.route_configured() and needle in (llm.route_problem() or "")
    assert needle in (run.live_mode_problem() or "")


@pytest.mark.parametrize("setup", [
    {"MODEL_BASE_URL": "http://127.0.0.1:8088/v1", "MODEL_API_KEY": "k"},  # Nightshift through the MODEL_* pair (.env.example)
    {"MODEL_BASE_URL": "http://127.0.0.1:8088/v1", "METERLESS_TOKEN": "t"},
    {"MODEL_BASE_URL": "https://integrate.api.nvidia.com/v1", "MODEL_API_KEY": "k"},
    {"METERLESS_TOKEN": "t"},
])
def test_single_family_pairs_are_routes(env, setup):
    for name, value in setup.items():
        env.setenv(name, value)
    assert llm.route_configured() and llm.route_problem() is None and run.live_mode_problem() is None


def test_live_mode_message_mentions_the_alias(env):
    assert "METERLESS_TOKEN" in run.live_mode_problem()


def test_direct_route_request_key_golden(env):
    import hashlib
    import json

    env.setenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    env.setenv("MODEL_API_KEY", "k")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    args = dict(task="stance", which="default", model=LIGHTNING, messages=messages, temperature=0.1, payload={"a": 1})
    prompt = "system:s\nuser:u"
    material = {"task": "stance", "lane": "default", "route": LIGHTNING,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "temperature": 0.1,
                "extras": llm._request_extras(), "payload": {"a": 1}}
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    assert llm._request_key(**args) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("met,expected,unreadable", [
    ({"receipt": {"hmem": 4}}, 4, False),
    ({"receipt": {"hmem": {"injected": "2"}}}, None, True),
    ({"receipt": {"hmem": {"injected": True}}}, None, True),
    ({"receipt": {"hmem": {"injected": 2.0}}}, None, True),
    ({"receipt": {"hmem": {"injected": -1}}}, None, True),
    ({"receipt": {"hmem": "lots"}}, None, True),
    ({"receipt": {"hmem": {"strategy": "minimal"}}}, None, True),
    ({"receipt": {"hmem": None}}, 0, False),
    ({}, None, False),
])
def test_hmem_unparsable_has_no_count_but_is_reported_and_plain_int_accepted(met, expected, unreadable):
    # 2026-10-25 review round 1: an unreadable block is no longer "nothing to report"; json_task rejects it
    assert llm._hmem_injected(met) == expected
    assert bool(llm._hmem_report(met)[1]) is unreadable


@pytest.mark.parametrize("flag,shown", [("false", "a string"), ("true", "a string"), (1, "1"), (0, "0"), ([], "a list")])
def test_from_cache_that_is_not_a_boolean_is_refused_and_not_coerced(live, tmp_path, monkeypatch, flag, shown):
    """Round 7: a non-boolean `from_cache` beside `cache.status` "miss" was served; it is now refused as a cache replay
    (load_journal already refused any `receipt_from_cache` other than false), and the value is still not coerced.
    Closing round 1: a string flag is named "a string", its text never copied into the row or the exception."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    met = {**_met(LIGHTNING, LIGHTNING, LIGHTNING), "from_cache": flag, "cache": {"status": "miss"}}
    assert llm._cache_hit(met) and llm._hmem_report(met) == (0, None)
    live(_completion(LIGHTNING, met))
    with pytest.raises(llm.MemoryInjected, match="nightshift cache replay refused") as caught:
        llm.json_task("stance", {"claim": "c"}, dry_run=False)
    row = llm.calls[-1]
    assert row["served"] == "error" and row["cache_refused"] is True and "receipt_from_cache" not in row
    assert row["error"] == f"{llm.CACHE_REPLAY_REFUSED} (from_cache is {shown}, not a boolean)"
    if isinstance(flag, str):
        assert f'"{flag}"' not in row["error"] and f'"{flag}"' not in str(caught.value)
    assert llm.cache_refused_count() == 1 and llm.hmem_rejected_count() == 0
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}  # not journalled for replay
    for absent in (None, False):  # null says nothing; false is the live answer's own flag
        assert not llm._cache_hit({**met, "from_cache": absent})


@pytest.mark.parametrize("met", [None, {"receipt_id": "r"}, {"receipt_id": "r", "provider_model": "", "routed_model": ""}])
def test_pinned_meterless_lane_without_evidence_is_unverified_not_error(live, met):
    live(_completion(LIGHTNING, met))
    llm.json_task("stance", {"claim": "c"}, dry_run=False)
    row = llm.calls[-1]
    assert row["lane_unverified"] is True and row["served"] == LIGHTNING and not row.get("error")
    assert "receipt_hmem_injected" not in row  # round 7: no receipt, so no count is claimed (not 0)
    assert llm.lane_unverified_count() == 1 and llm.substitution_count() == 0


def test_held_lane_is_not_unverified(live):
    live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    llm.json_task("stance", {"claim": "c"}, dry_run=False)
    assert "lane_unverified" not in llm.calls[-1] and llm.lane_unverified_count() == 0


# H-MEM off (2026-10-25): the daemon setpoint before the first call, and rejection of injected replies --------------

@pytest.mark.parametrize("injected", [1, 2])  # 1: the boundary; a `> 1` threshold must fail this test
def test_injected_memories_reject_the_reply_and_record_the_count(live, tmp_path, monkeypatch, injected):
    """Revert probe: removing the rejection in json_task makes this test fail (the call returns the reply instead)."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": injected, "reason": f"retrieved {injected} memories"})))
    with pytest.raises(llm.MemoryInjected, match=f"injected {injected} prior answers"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["answered_model"] == ULTRA and row["hmem_rejected"] is True
    assert row["receipt_hmem_injected"] == injected and "reply_sha256" not in row and "hmem_unreadable" not in row
    assert llm.hmem_rejected_count() == 1 and llm.error_count() == 1 and llm.served_counts() == {"error": 1}
    assert run.flagged_calls_note() == ", 1 rejected for injected memories"  # round 5: the run summary's own label
    journalled = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(journalled) == 1 and "reply" not in journalled[0] and journalled[0]["receipt_hmem_injected"] == injected
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}  # nothing to replay on --resume


@pytest.mark.parametrize("content", ["", "Let me think about this claim step by step"])
@pytest.mark.parametrize("met,flag,needle", [
    (_met(ULTRA, ULTRA, ULTRA, hmem={"injected": 2, "reason": "retrieved 2 memories"}), "hmem_rejected", "injected 2 prior answers"),
    (_met(ULTRA, ULTRA, ULTRA, hmem=None, from_cache=True), "cache_refused", llm.CACHE_REPLAY_REFUSED),
])
def test_rejection_does_not_depend_on_the_reply_parsing(live, tmp_path, monkeypatch, content, met, flag, needle):
    """Round 9 revert probe: a reply with injected memories (or a cache hit) whose content is no JSON, as the first genuine
    run's 2 truncated replies were, is still MemoryInjected with its flag and count, never the plain no-JSON ValueError."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, met, content=content, finish_reason="length"))
    with pytest.raises(llm.MemoryInjected, match=needle):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row[flag] is True and row["answered_model"] == ULTRA and "reply_sha256" not in row
    assert "reply carried no JSON object" not in row["error"] and len(llm.calls) == 1
    if flag == "hmem_rejected":
        assert row["receipt_hmem_injected"] == 2 and (llm.hmem_rejected_count(), llm.cache_refused_count()) == (1, 0)
    else:
        assert row["receipt_from_cache"] is True and (llm.hmem_rejected_count(), llm.cache_refused_count()) == (0, 1)
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


def test_rejection_leaves_pacing_and_the_429_breaker_as_a_served_call_does(live, monkeypatch):
    monkeypatch.setenv("QUORUM_MIN_INTERVAL_MS_FACT_CHECKER", "1")  # a paced lane (1 ms: the test does not wait)

    def preset():  # a lane raised by an earlier 429, three clean calls since, one failed 429 on record
        llm.reset_pacing()
        llm._lane_interval_by_route[ULTRA] = 2
        llm._clean_streak_by_route[ULTRA] = 3
        llm._last_failed_429_at_by_route[ULTRA] = 1.0

    def pacing():
        return dict(llm._lane_interval_by_route), dict(llm._clean_streak_by_route), dict(llm._last_failed_429_at_by_route)

    preset()
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 0})))
    llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    served = pacing()
    assert served == ({ULTRA: 2}, {ULTRA: 4}, {ULTRA: 1.0})  # HTTP 200: one more clean call on the raised lane
    preset()
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 2})))
    with pytest.raises(llm.MemoryInjected):  # MemoryInjected, never RateLimitAbort (a BaseException would escape this)
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert pacing() == served
    llm.reset_pacing()


def test_rejected_row_is_not_also_lane_unverified(live):
    live(_completion(LIGHTNING, {"receipt_id": "r", "receipt": {"hmem": {"injected": 2}}}))  # no provider/routed model
    with pytest.raises(llm.MemoryInjected):
        llm.json_task("stance", {"claim": "c"}, dry_run=False)
    row = llm.calls[-1]
    assert row["hmem_rejected"] is True and "lane_unverified" not in row
    assert llm.hmem_rejected_count() == 1 and llm.lane_unverified_count() == 0


@pytest.mark.parametrize("extra,flag,label,needle", [
    ({"receipt": {"hmem": {"injected": 2}}}, "hmem_rejected", "1 rejected for injected memories", "injected 2 prior answers"),
    ({"receipt": {"hmem": {"injected": 1}}}, "hmem_rejected", "1 rejected for injected memories", "injected 1 prior answers"),
    ({"receipt": {"hmem": "lots"}}, "hmem_rejected", "1 rejected for injected memories", "no readable injected count"),
    ({"receipt": {"hmem": None}, "from_cache": True}, "cache_refused", "1 refused as cache replays", llm.CACHE_REPLAY_REFUSED),
])
def test_substituted_reply_with_injected_memories_is_a_rejection_too(live, tmp_path, monkeypatch, extra, flag, label, needle):
    """Round 5: the substitution check ran first, so a pinned Ultra answered by Lightning with hmem.injected 2 raised
    RouteSubstituted and was neither flagged `hmem_rejected` nor counted. Now the H-MEM / cache verdict comes first: the
    dedicated MemoryInjected is raised, and the one row carries both flags and is counted under both labels."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(LIGHTNING, {"receipt_id": "r", "provider_model": ULTRA, "routed_model": LIGHTNING, **extra}))
    with pytest.raises(llm.MemoryInjected) as caught:
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert not isinstance(caught.value, llm.RouteSubstituted)
    assert needle in str(caught.value) and f"route substituted {LIGHTNING} for {ULTRA}" in str(caught.value)
    row = llm.calls[-1]
    assert row["served"] == "error" and row[flag] is True and row["route_substituted"] is True
    assert row["answered_model"] == LIGHTNING and "reply_sha256" not in row and len(llm.calls) == 1
    assert llm.substitution_count() == 1 and llm.error_count() == 1 and llm.served_counts() == {"error": 1}
    assert (llm.hmem_rejected_count(), llm.cache_refused_count()) == ((1, 0) if flag == "hmem_rejected" else (0, 1))
    note = run.flagged_calls_note()
    assert "1 lane substituted" in note and label in note
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


@pytest.mark.parametrize("hmem", [{"injected": 2.0}, {"injected": "2"}, {"injected": True}, {"reason": "retrieved 2 memories"},
                                  {"injected": -1}, {}, "lots", True])
def test_unreadable_hmem_block_is_rejected_not_served(live, tmp_path, monkeypatch, hmem):
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem=hmem)))
    with pytest.raises(llm.MemoryInjected, match="no readable injected count"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["hmem_rejected"] is True and row["hmem_unreadable"] is True
    assert "receipt_hmem_injected" not in row and llm.hmem_rejected_count() == 1
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


@pytest.mark.parametrize("hmem,count", [
    ({"injected": 0, "count": 2}, 2),  # round 4: `injected` alone won whenever present, so this was served as 0
    ({"injected": None, "count": 2}, 2),
    ({"count": 2}, 2),
    ({"injected": 2, "count": 0}, 2),
    ({"injected": 1, "count": 3}, 3),
])
def test_hmem_block_counts_the_larger_of_injected_and_count(live, hmem, count):
    """Decision 3 (an int > 0 anywhere rejects) and Nightshift's own reader (`hmemMeta.injected || hmemMeta.count`)."""
    assert llm._hmem_report({"receipt": {"hmem": hmem}}) == (count, None)
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem=hmem)))
    with pytest.raises(llm.MemoryInjected, match=f"injected {count} prior answers"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert llm.calls[-1]["receipt_hmem_injected"] == count and llm.calls[-1]["hmem_rejected"] is True


@pytest.mark.parametrize("hmem,count,needle", [
    ({"injected": 0, "count": "2"}, 0, "(count is str)"),  # the offending field is named, not `injected`
    ({"injected": "2", "count": 0}, 0, "(injected is str)"),
    ({"injected": 0, "count": -1}, 0, "(count is -1)"),
    ({"injected": 0, "count": True}, 0, "(count is true)"),
    ({"injected": 2, "count": "1"}, 2, "(count is str)"),
    ({"injected": None, "count": None}, None, "both absent or null"),
])
def test_hmem_block_with_an_unreadable_field_names_it(hmem, count, needle):
    # round 5: the readable field's count is kept beside the reason (it was dropped), and the reply is still rejected
    injected, unreadable = llm._hmem_report({"receipt": {"hmem": hmem}})
    assert injected == count and unreadable and needle in unreadable
    assert llm._hmem_report({"receipt": {"hmem": {"injected": 0, "count": 0}}}) == (0, None)  # both readable and 0: served


@pytest.mark.parametrize("met,needle", [
    ({"receipt": {"hmem": {"injected": 2}}, "receipt_envelope": {"body": {"receipt": {"hmem": "garbage"}}}}, "(the block is a str)"),
    ({"receipt": {"hmem": "garbage"}, "receipt_envelope": {"body": {"receipt": {"hmem": {"injected": 2}}}}}, "(the block is a str)"),
    ({"receipt": {"hmem": {"injected": 1}}, "hmem": {"injected": "1"}, "receipt_envelope": {"receipt": {"hmem": 2}}}, "(injected is str)"),
])
def test_readable_count_beside_an_unreadable_copy_is_disclosed_and_rejected(live, tmp_path, monkeypatch, met, needle):
    """Round 5: the parser stopped at the first unreadable copy, so the readable 2 beside it was dropped from the row."""
    assert llm._hmem_report(met)[0] == 2 and needle in llm._hmem_report(met)[1]
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, **met}))
    with pytest.raises(llm.MemoryInjected) as caught:
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert "injected 2 prior answers" in str(caught.value) and needle in str(caught.value)
    row = llm.calls[-1]
    assert row["served"] == "error" and row["hmem_rejected"] is True and row["hmem_unreadable"] is True
    assert row["receipt_hmem_injected"] == 2 and "reply_sha256" not in row
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


INJECTED_2 = json.dumps({"hmem": {"injected": 2, "reason": "retrieved 2 memories"}})
# round 7: a receipt copy or a meterless value that is present but not an object; (shape, meterless value or None for
# the held-lane base plus `extra`, the report expected, the reason's needle)
UNREADABLE_SHAPES = [
    ("receipt JSON string", None, {"receipt": INJECTED_2}, 2, None),  # decoded as `body` is: the 2 rejects
    ("receipt non-JSON string", None, {"receipt": "hmem=2"}, None, "(receipt is a string that is not JSON)"),
    ("receipt list", None, {"receipt": [{"hmem": 2}]}, None, "(receipt is a list)"),
    ("receipt JSON string of a list", None, {"receipt": "[2]"}, None, "(receipt is a JSON string holding a list)"),
    ("envelope JSON string beside receipt null", None,
     {"receipt": {"hmem": None}, "receipt_envelope": json.dumps({"body": {"receipt": json.loads(INJECTED_2)}})}, 2, None),
    ("envelope non-JSON string beside receipt null", None,
     {"receipt": {"hmem": None}, "receipt_envelope": "signed:abc"}, 0, "(receipt_envelope is a string that is not JSON)"),
    ("envelope number", None, {"receipt": {"hmem": None}, "receipt_envelope": 7}, 0, "(receipt_envelope is 7)"),
    # a readable block of 0 beside the unreadable copy: the 0 must not hide it
    ("envelope non-JSON string beside receipt 0", None,
     {"receipt": {"hmem": {"injected": 0}}, "receipt_envelope": "signed:abc"}, 0, "(receipt_envelope is a string that is not JSON)"),
    ("receipt list beside top-level hmem 0", None, {"hmem": 0, "receipt": [{"hmem": 2}]}, 0, "(receipt is a list)"),
    ("envelope body non-JSON string", None,
     {"receipt": {"hmem": None}, "receipt_envelope": {"body": "c2lnbmVk"}}, 0, "(receipt_envelope.body is a string that is not JSON)"),
    ("envelope body.receipt list", None,
     {"receipt": {"hmem": None}, "receipt_envelope": {"body": {"receipt": []}}}, 0, "(receipt_envelope.body.receipt is a list)"),
    ("envelope receipt non-JSON string", None,
     {"receipt": {"hmem": None}, "receipt_envelope": {"receipt": "x"}}, 0, "(receipt_envelope.receipt is a string that is not JSON)"),
    ("meterless JSON string", json.dumps({"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA,
                                          "receipt": json.loads(INJECTED_2)}), None, 2, None),
    ("meterless non-JSON string", "receipt hmem 2", None, None, "the response's meterless object is unreadable (it is a string that is not JSON)"),
    ("meterless list", [{"hmem": 2}], None, None, "the response's meterless object is unreadable (it is a list)"),
    ("meterless number", 2, None, None, "the response's meterless object is unreadable (it is 2)"),
]


@pytest.mark.parametrize("shape,raw,extra,count,needle", UNREADABLE_SHAPES, ids=[s[0] for s in UNREADABLE_SHAPES])
def test_receipt_or_meterless_value_that_is_not_an_object_is_never_served(live, tmp_path, monkeypatch, shape, raw, extra, count, needle):
    """Round 7 (coordinator decision 3, fail closed on any sign): a present `meterless` value, `receipt`,
    `receipt_envelope`, envelope `body` or envelope `receipt` that is not an object read as no receipt, and the reply was
    served with no count and no disclosure. A JSON string holding an object is decoded (its count rejects); anything
    else is an unreadable report, which rejects. One case per shape."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    if raw is None:
        raw = {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "from_cache": False, **extra}
    completion = _completion(ULTRA, None)
    completion.model_extra = {"meterless": raw}
    injected, unreadable = llm._hmem_report(llm._meterless(completion))
    assert injected == count and (needle is None) is (unreadable is None)
    if needle:
        assert needle in unreadable
    live(completion)
    with pytest.raises(llm.MemoryInjected) as caught:
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["hmem_rejected"] is True and "reply_sha256" not in row
    assert row.get("hmem_unreadable", False) is (needle is not None)
    assert row.get("receipt_hmem_injected") == count  # disclosed whenever a copy is readable, absent when none is
    assert (needle or f"injected {count} prior answers") in str(caught.value)
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}  # not journalled for replay


@pytest.mark.parametrize("flag", ["--test-connection", "--probe"])
@pytest.mark.parametrize("raw", ["receipt hmem 2", {"receipt_id": "r", "receipt": "hmem=2"}])
def test_cli_checks_refuse_a_meterless_value_that_is_not_an_object(live, control, capsys, flag, raw):
    control()
    completion = _completion(LIGHTNING, None, '{"stance": "neutral"}')
    completion.model_extra = {"meterless": raw}
    live(completion)
    assert run.main([flag]) == 2
    err = capsys.readouterr().err
    assert "MemoryInjected" in err and "unreadable" in err


def test_meterless_json_string_with_a_clean_receipt_is_served(live):
    """The other side: a `meterless` value sent as a JSON string holding an object with hmem null is decoded and served."""
    completion = _completion(ULTRA, None)
    completion.model_extra = {"meterless": json.dumps(_met(ULTRA, ULTRA, ULTRA, hmem=None))}
    live(completion)
    assert llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")["stance"] == "neutral"
    row = llm.calls[-1]
    assert row["served"] == ULTRA and row["receipt_hmem_injected"] == 0 and row["receipt_id"] == "rcpt_test_1"
    assert not row.get("error") and "lane_unverified" not in row


SIGNED_ENVELOPES = [
    {"body": {"receipt": {"hmem": {"injected": 2}}}},
    {"receipt": {"hmem": {"injected": 2}}},  # dgx-client.js receiptFromEnvelope: `body.receipt || env.receipt`
    {"body": {"ts_ms": 1}, "receipt": {"hmem": {"injected": 2}}},
    {"body": {"receipt": {"hmem": {"injected": 0}}}, "receipt": {"hmem": {"injected": 2}}},  # the larger count wins
    {"body": json.dumps({"receipt": {"hmem": {"injected": 2}}})},  # a body sent as a JSON string
]


@pytest.mark.parametrize("envelope", SIGNED_ENVELOPES)
@pytest.mark.parametrize("receipt", [{}, {"hmem": None}, {"hmem": {"injected": 0}}, None])  # None: no unsigned receipt
def test_signed_envelope_count_is_not_hidden_by_the_unsigned_receipt(live, receipt, envelope):
    met = {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "receipt_envelope": envelope}
    if receipt is not None:
        met["receipt"] = receipt
    assert llm._hmem_report(met) == (2, None)
    live(_completion(ULTRA, met))
    with pytest.raises(llm.MemoryInjected, match="injected 2 prior answers"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert llm.calls[-1]["receipt_hmem_injected"] == 2


@pytest.mark.parametrize("journalled,replayed", [(0, True), (None, True), (1, False), (2, False), ("2", False), (True, False)])
def test_journalled_reply_with_injected_memories_is_not_replayed(live, tmp_path, monkeypatch, capsys, journalled, replayed):
    """--resume / --seed-journal: a journal row from before the rejection, served with injected memories, stays in the
    ledger but its reply is not replayed; the request goes live again (None: a row without the disclosure field)."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 0}), '{"stance": "supports", "reason": "journalled"}'))
    llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["reply"] and row["request_key"] and not row.get("error")
    if journalled is None:
        row.pop("receipt_hmem_injected")
    else:
        row["receipt_hmem_injected"] = journalled  # as a run written before the rejection recorded it
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and len(llm.calls) == 1  # the paid call stays in the ledger either way
    assert bool(llm.replay) is replayed
    assert ("not replayed" in capsys.readouterr().err) is not replayed
    restored = llm.calls[0]
    # decision 5 (round 3): declined for replay, not rejected in this run: `replay_refused` only, its own summary label
    assert restored.get("replay_refused", False) is (not replayed) and "hmem_rejected" not in restored
    assert llm.replay_refused_count() == (0 if replayed else 1) and llm.hmem_rejected_count() == 0
    note = run.flagged_calls_note()
    assert ("1 journalled replies not replayed" in note) is (not replayed) and "rejected" not in note
    assert restored["served"] == ULTRA  # kept as journalled (whether it becomes "error" is the owner's call)
    client = live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA), '{"stance": "neutral", "reason": "live"}'))
    out = llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert out["reason"] == ("journalled" if replayed else "live")
    assert len(client.kwargs) == (0 if replayed else 1)


@pytest.mark.parametrize("journalled,replayed", [(False, True), (None, True), (True, False), ("true", False), (1, False)])
def test_journalled_cache_replay_is_not_replayed(live, tmp_path, monkeypatch, capsys, journalled, replayed):
    """Decision 5 (round 3): a journal row whose receipt said `from_cache: true` (written before the cache refusal) is
    not replayed, labelled `replay_refused` only (None: a row without the disclosure field)."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem=None), '{"stance": "supports", "reason": "journalled"}'))
    llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["receipt_from_cache"] is False and row["receipt_hmem_injected"] == 0
    if journalled is None:
        row.pop("receipt_from_cache")
    else:
        row["receipt_from_cache"] = journalled
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and bool(llm.replay) is replayed
    err = capsys.readouterr().err
    assert ("0 with prior answers injected by the runtime (H-MEM), 1 Nightshift cache replays" in err) is not replayed
    restored = llm.calls[0]
    assert restored.get("replay_refused", False) is (not replayed)
    assert not {"hmem_rejected", "cache_refused"} & restored.keys()
    assert llm.replay_refused_count() == (0 if replayed else 1) and llm.cache_refused_count() == 0


def test_injected_memories_are_skipped_per_passage_like_a_substitution():
    assert issubclass(llm.MemoryInjected, Exception) and not issubclass(llm.MemoryInjected, llm.RateLimitAbort)


@pytest.mark.parametrize("met", [
    _met(ULTRA, ULTRA, ULTRA, hmem=None),  # the 09:59 Ultra receipt with the setpoint false: hmem null
    _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 0}),
    {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "receipt_envelope": {"body": {"receipt": {"hmem": None}}}},
])
def test_hmem_null_and_zero_are_served(live, met):
    live(_completion(ULTRA, met))
    assert llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")["stance"] == "neutral"
    row = llm.calls[-1]
    assert row["served"] == ULTRA and row["receipt_hmem_injected"] == 0 and not row.get("error")
    assert "hmem_rejected" not in row and llm.hmem_rejected_count() == 0


@pytest.mark.parametrize("met", [
    {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "hmem": {"injected": 2}},  # top-level only
    {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "hmem": 2, "receipt": {"hmem": {"injected": 0}}},
    {"receipt_id": "r", "provider_model": ULTRA, "routed_model": ULTRA, "hmem": {"injected": 2}, "receipt": {"hmem": None},
     "receipt_envelope": {"body": {"receipt": {"hmem": {"injected": 0}}}}},
])
def test_top_level_hmem_joins_the_max_and_rejects(live, met):
    """Decision 3 (round 3): every place a count can appear joins one max; a top-level 2 beside a receipt 0 rejects."""
    assert llm._hmem_report(met) == (2, None)
    live(_completion(ULTRA, met))
    with pytest.raises(llm.MemoryInjected, match="injected 2 prior answers"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert llm.calls[-1]["receipt_hmem_injected"] == 2 and llm.calls[-1]["hmem_rejected"] is True


def test_top_level_hmem_null_or_zero_beside_receipts_is_served(live):
    for top in (None, 0, {"injected": 0}):
        met = {**_met(ULTRA, ULTRA, ULTRA, hmem=None), "hmem": top}
        assert llm._hmem_report(met) == (0, None)
    assert llm._hmem_report({"hmem": {"injected": 0}}) == (0, None)  # a top-level block alone is still read


CACHE_HITS = [
    {"from_cache": True},  # the 1.2.3 response's own flag
    {"from_cache": False, "cache": {"status": "exact", "source_model": ULTRA}},  # openai.mjs: `cache` is receipt.cache
    {"from_cache": False, "receipt": {"hmem": None, "cache": {"status": "semantic"}}},
    {"from_cache": False, "receipt_envelope": {"body": {"receipt": {"cache": {"status": "exact"}}}}},
    {"from_cache": False, "cache": json.dumps({"status": "exact"})},  # round 8: a JSON string holding the block is decoded
    {"from_cache": False, "receipt": {"hmem": None, "cache": json.dumps({"status": "semantic"})}},
]


@pytest.mark.parametrize("hit", CACHE_HITS)
def test_cache_replay_is_refused_counted_apart_and_not_replayable(live, tmp_path, monkeypatch, hit):
    """Decision 4 (round 3): a Nightshift cache hit (hmem null: the cache is read before the H-MEM block) is refused with
    MemoryInjected and its own reason, counted by cache_refused_count(), never journalled for replay."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    met = {**_met(ULTRA, ULTRA, ULTRA, hmem=None), **hit}
    assert llm._cache_hit(met) and llm._hmem_report(met) == (0, None)
    live(_completion(ULTRA, met))
    with pytest.raises(llm.MemoryInjected, match="nightshift cache replay refused: provenance of injected memories unknown"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["answered_model"] == ULTRA and row["cache_refused"] is True
    assert row["error"] == llm.CACHE_REPLAY_REFUSED and "hmem_rejected" not in row and "reply_sha256" not in row
    assert llm.cache_refused_count() == 1 and llm.hmem_rejected_count() == 0 and llm.error_count() == 1
    assert "1 refused as cache replays" in run.flagged_calls_note()
    journalled = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(journalled) == 1 and "reply" not in journalled[0]
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}


@pytest.mark.parametrize("met", [
    _met(ULTRA, ULTRA, ULTRA, hmem=None, from_cache=False),
    {**_met(ULTRA, ULTRA, ULTRA, hmem=None), "cache": {"status": "miss"}, "receipt": {"hmem": None, "cache": {"status": "miss"}}},
    {**_met(ULTRA, ULTRA, ULTRA, hmem=None), "cache": None, "receipt": {"hmem": None, "cache": None}},  # null says nothing
    {**_met(ULTRA, ULTRA, ULTRA, hmem=None), "cache": json.dumps({"status": "miss"})},  # a JSON string holding a miss
])
def test_cache_miss_is_served(live, met):
    live(_completion(ULTRA, met))
    assert llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")["stance"] == "neutral"
    assert not llm.calls[-1].get("error") and llm.cache_refused_count() == 0


@pytest.mark.parametrize("where,cache,shape", [
    ("top", "exact", "cache is a string that is not JSON"),
    ("top", json.dumps("exact"), "cache is a JSON string holding a str"),
    ("top", 1, "cache is 1"),
    ("top", ["exact"], "cache is a list"),
    ("receipt", "semantic", "a receipt's cache is a string that is not JSON"),
    ("envelope", True, "a receipt's cache is true"),
])
def test_cache_block_that_is_not_an_object_is_refused(live, tmp_path, monkeypatch, where, cache, shape):
    """Round 8: a present `cache` block that is not an object (top level or a receipt copy) was skipped and the reply
    served; it is now refused as a cache replay naming the shape, like a `from_cache` that is not a boolean."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    met = _met(ULTRA, ULTRA, ULTRA, hmem=None)
    if where == "top":
        met["cache"] = cache
    elif where == "receipt":
        met["receipt"] = {"hmem": None, "cache": cache}
    else:
        met["receipt_envelope"] = {"body": {"receipt": {"cache": cache}}}
    assert llm._hmem_report(met) == (0, None) and llm._cache_hit(met)
    live(_completion(ULTRA, met))
    with pytest.raises(llm.MemoryInjected, match="nightshift cache replay refused"):
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["cache_refused"] is True and "hmem_rejected" not in row and "reply_sha256" not in row
    assert row["error"] == f"{llm.CACHE_REPLAY_REFUSED} ({shape}, not an object)"
    assert llm.cache_refused_count() == 1 and llm.hmem_rejected_count() == 0
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}  # not journalled for replay


STRING_FLAG = "cache-flag-text-never-copied"  # a string `from_cache`: its text must not reach any failure string


def _with_copy_flag(where: str, flag) -> dict:
    """A clean Ultra receipt (top-level `from_cache` false, every `cache` block "miss") whose one receipt copy at `where`
    carries `from_cache: flag`."""
    met = {**_met(ULTRA, ULTRA, ULTRA, hmem=None), "cache": {"status": "miss"}}
    copy = {"hmem": None, "cache": {"status": "miss"}, "from_cache": flag}
    if where == "receipt":
        met["receipt"] = copy
    elif where == "envelope body.receipt":
        met["receipt_envelope"] = {"body": {"receipt": copy}}
    else:  # the envelope's receipt beside its body (dgx-client.js receiptFromEnvelope: `body.receipt || env.receipt`)
        met["receipt_envelope"] = {"body": {}, "receipt": copy}
    return met


@pytest.mark.parametrize("where", ["receipt", "envelope body.receipt", "envelope receipt"])
@pytest.mark.parametrize("flag,reason", [
    (True, llm.CACHE_REPLAY_REFUSED),
    (STRING_FLAG, f"{llm.CACHE_REPLAY_REFUSED} (a receipt's from_cache is a string, not a boolean)"),
    ("true", f"{llm.CACHE_REPLAY_REFUSED} (a receipt's from_cache is a string, not a boolean)"),
    (1, f"{llm.CACHE_REPLAY_REFUSED} (a receipt's from_cache is 1, not a boolean)"),
])
def test_from_cache_in_a_receipt_copy_is_refused(live, tmp_path, monkeypatch, where, flag, reason):
    """Closing round 1: only the top-level `from_cache` was read, so a receipt copy saying true (beside a top-level false
    and every cache block "miss") was served. Every copy is now held to the same rules, and a string flag is named only
    by its shape, in the ledger error and the MemoryInjected message alike; probe() and test_connection() refuse it too."""
    path = tmp_path / "j.jsonl"
    monkeypatch.setattr(llm, "journal_path", path)
    met = _with_copy_flag(where, flag)
    assert llm._hmem_report(met) == (0, None) and llm._cache_hit(met)
    live(_completion(ULTRA, met))
    with pytest.raises(llm.MemoryInjected, match="nightshift cache replay refused") as caught:
        llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    row = llm.calls[-1]
    assert row["served"] == "error" and row["cache_refused"] is True and row["error"] == reason
    assert row["receipt_from_cache"] is False  # the top-level flag is still disclosed as sent
    assert "hmem_rejected" not in row and "reply_sha256" not in row
    assert llm.cache_refused_count() == 1 and llm.hmem_rejected_count() == 0
    with pytest.raises(llm.MemoryInjected) as refused:
        llm._refuse_injected("connection test on fact_checker", met)  # what probe() and test_connection() call
    for text in (row["error"], str(caught.value), str(refused.value)):
        assert reason in text and STRING_FLAG not in text and '"true"' not in text
    llm.reset_calls()
    assert llm.load_journal(path) == 1 and llm.replay == {}  # not journalled for replay


@pytest.mark.parametrize("where", ["receipt", "envelope body.receipt", "envelope receipt"])
@pytest.mark.parametrize("flag", [False, None])
def test_receipt_copy_from_cache_false_or_null_is_served(live, where, flag):
    met = _with_copy_flag(where, flag)
    assert not llm._cache_hit(met)
    live(_completion(ULTRA, met))
    assert llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")["stance"] == "neutral"
    assert not llm.calls[-1].get("error") and llm.cache_refused_count() == 0


@pytest.mark.parametrize("hmem", [None, {"injected": 0}])
def test_probe_serves_a_clean_meterless_reply_after_the_setter(live, control, monkeypatch, capsys, hmem):
    """Round 8: null and 0 stay success in probe(): `--probe` exits 0 and prints the reply, after the setter."""
    events: list[str] = []
    plane = control(events=events)

    class _Recording(_Client):
        def _create(self, **kwargs):
            events.append("completion")
            return super()._create(**kwargs)

    client = _Recording(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING, hmem=hmem)))
    monkeypatch.setattr(llm, "_client", lambda: client)
    assert run.main(["--probe"]) == 0
    assert f"answered by {LIGHTNING}" in capsys.readouterr().out
    assert events == ["control GET", "control POST", "control GET", "completion"]  # the setpoint before the completion
    assert plane.requests == SETTER_REQUESTS


@pytest.mark.parametrize("flag", ["--test-connection", "--probe"])
def test_cli_checks_refuse_a_cache_replay(live, control, capsys, flag):
    control()
    live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING, from_cache=True), '{"stance": "neutral"}'))
    assert run.main([flag]) == 2
    err = capsys.readouterr().err
    assert "MemoryInjected" in err and llm.CACHE_REPLAY_REFUSED in err


def test_direct_route_completion_is_unchanged_and_never_touches_the_daemon(env, monkeypatch, capsys):
    env.setenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    env.setenv("MODEL_API_KEY", "direct-key-not-real")
    env.setenv("NEMOTRON_MODEL", LIGHTNING)
    env.setenv("QUORUM_MIN_INTERVAL_MS", "0")
    monkeypatch.setattr(llm, "journal_path", None)
    llm.reset_calls()
    llm.reset_pacing()
    client = _Client(_completion(LIGHTNING, None))
    monkeypatch.setattr(llm, "_client", lambda: client)
    # the env fixture's control plane fails the test if anything below reaches it
    assert llm.disable_hmem_injection() is None and run.live_guard() is None
    assert llm.json_task("stance", {"claim": "c"}, dry_run=False)["stance"] == "neutral"
    row = llm.calls[-1]
    assert row["served"] == LIGHTNING and not row.get("error")
    assert not {"receipt_hmem_injected", "hmem_rejected", "lane_unverified", "receipt_id"} & row.keys()
    client.completion = _completion(LIGHTNING, None, "ready")
    assert run.main(["--test-connection"]) == 0
    assert "meterless:" not in capsys.readouterr().err
    llm.reset_calls()


def test_setter_sends_exactly_hmem_false_then_reads_it_back(live, control):
    plane = control()
    assert llm.disable_hmem_injection() is None
    assert plane.requests == SETTER_REQUESTS
    assert plane.requests[1][2]["hmemKnowledge"] is False  # the JSON literal false, not a falsy stand-in
    assert plane.state == {"hmemKnowledge": False, "hmemTopK": 3}  # merged: the other setpoint kept


def test_setter_puts_exactly_hmem_false_on_the_wire(live, monkeypatch):
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        assert where == FAKE_PIPE  # METERLESS_CONTROL_SOCKET wins, as in transport.mjs
        doc = b'{"setpoints":{"hmemKnowledge":false}}' if request.startswith(b"GET") else b'{"setpoints":{"hmemKnowledge":false},"engines_notified":1}'
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (len(doc), doc)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)  # the real request builder; only the I/O is faked
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    assert llm.disable_hmem_injection() is None
    first, post, get = sent
    head, _, body = post.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    assert lines[0] == b"POST /admin/setpoints HTTP/1.1" and body == b'{"hmemKnowledge":false}'
    assert {b"Host: meterlessd", b"Accept: application/json", b"Connection: close", b"Content-Type: application/json",
            b"Content-Length: 23"} <= set(lines[1:])
    assert b"Authorization" not in head
    for request in (first, get):
        assert request == b"GET /admin/setpoints HTTP/1.1\r\nHost: meterlessd\r\nAccept: application/json\r\nConnection: close\r\n\r\n"


@pytest.mark.parametrize("plane,needle", [
    ({"readback": True}, "read back as true"),
    ({"readback": None}, "read back as null"),  # an explicit JSON null in the document
    ({"readback": ABSENT}, "read back as null"),  # the key missing from the document
    ({"readback": "false"}, 'read back as "false"'),  # the string, not the JSON literal
    ({"readback": 0}, "read back as 0"),
    ({"readback_status": 404}, "cannot confirm H-MEM injection is off: GET /admin/setpoints answered HTTP 404"),
    ({"get_status": 404}, "the first GET /admin/setpoints answered HTTP 404"),
    ({"post_status": 400}, "POST /admin/setpoints answered HTTP 400"),
    ({"unreachable": True}, f"control plane {FAKE_PIPE} is unreachable (FileNotFoundError"),
    ({"raise_on": "POST"}, f"cannot turn H-MEM injection off: POST /admin/setpoints on {FAKE_PIPE} failed (BrokenPipeError"),
    ({"raise_on": "readback"}, f"cannot confirm H-MEM injection is off: GET /admin/setpoints on {FAKE_PIPE} failed (BrokenPipeError"),
])
def test_failed_readback_is_a_live_start_failure(live, control, monkeypatch, tmp_path, capsys, plane, needle):
    control(**plane)
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert needle in (llm.disable_hmem_injection() or "")
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "refusing to run:" in err and needle in err


def test_setter_fails_when_the_post_dropped_or_changed_other_setpoints(live, control, monkeypatch, tmp_path, capsys):
    before = {"hmemKnowledge": True, "privacyMin": "local-only", "hmemTopK": 3, "raceWidth": 2}
    plane = control(before=before, replace=True)  # a daemon whose POST replaces the whole document
    problem = llm.disable_hmem_injection()
    assert problem and "changed or removed other daemon setpoints: hmemTopK, privacyMin, raceWidth" in problem
    assert "local-only" not in problem  # key names only, never values
    assert plane.requests == SETTER_REQUESTS and plane.state == {"hmemKnowledge": False}
    assert control(before=before).state and llm.disable_hmem_injection() is None  # a merging daemon passes

    def changing(method, path, body=None):  # a POST that also rewrites one other value
        doc = {"hmemKnowledge": False, "privacyMin": "cloud-ok"} if changing.posted else {"hmemKnowledge": True, "privacyMin": "local-only"}
        changing.posted = changing.posted or method == "POST"
        return 200, {"setpoints": doc}

    changing.posted = False
    monkeypatch.setattr(llm, "_control_http", changing)
    assert "other daemon setpoints: privacyMin" in (llm.disable_hmem_injection() or "")
    control(before=before, replace=True)
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    assert "refusing to run:" in capsys.readouterr().err


@pytest.mark.parametrize("unwritten", ["wrapped", "bare"])
def test_never_written_setpoints_are_an_empty_snapshot(live, control, monkeypatch, tmp_path, unwritten):
    """A fresh daemon (dgx-client.js: `r?.setpoints`, "null = never written"): nothing can be lost, the setter passes."""
    plane = control(unwritten=unwritten)
    assert llm.disable_hmem_injection() is None
    assert plane.requests == SETTER_REQUESTS and plane.state == {"hmemKnowledge": False}
    plane = control(unwritten=unwritten)

    def fake_run_local(*a, **k):
        raise llm.RateLimitAbort(LIGHTNING, 2)  # leave main() through a path it already handles (exit 3)

    monkeypatch.setattr(graph, "run_local", fake_run_local)
    monkeypatch.setattr(llm, "current_run_id", None)
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 3  # the graph started (exit 3 is its abort)
    assert plane.requests == SETTER_REQUESTS


@pytest.mark.parametrize("first,readback,needle", [
    (b'{"setpoints":null}', b'{"setpoints":{"hmemKnowledge":false}}', None),
    (b"null", b'{"setpoints":{"hmemKnowledge":false}}', None),
    (b"", b'{"setpoints":{"hmemKnowledge":false}}', None),
    (b"not json", b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b"[]", b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    # round 9: a wrapper that is not an object, and a bare object that is not a setpoints document, refuse before the POST
    (b'{"setpoints":[]}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"setpoints":[1,2]}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"setpoints":"x"}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"setpoints":3,"hmemKnowledge":true}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"error":"x"}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"ok":true}', b'{"setpoints":{"hmemKnowledge":false}}', "returned no setpoints document"),
    (b'{"hmemKnowledge":true}', b'{"setpoints":{"hmemKnowledge":false}}', None),  # a bare document holding the key is read
    (b'{"setpoints":null}', b'{"setpoints":null}', "read back as null"),  # the read-back still needs the value
    (b'{"setpoints":null}', b"", "no readable setpoints document (no body, or JSON null)"),  # round 8: named as unreadable
    (b'{"setpoints":null}', b"not json", "no readable setpoints document (a body that is not JSON)"),
])
def test_first_get_shapes_on_the_wire(live, monkeypatch, first, readback, needle):
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        posted = any(r.startswith(b"POST") for r in sent)
        doc = b'{"setpoints":{"hmemKnowledge":false},"engines_notified":1}' if request.startswith(b"POST") else (readback if posted else first)
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (len(doc), doc)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)  # the real request builder and parser; only the I/O is faked
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection()
    if needle is None:
        assert problem is None and len(sent) == 3
    else:
        assert problem and needle in problem and "other daemon setpoints" not in problem
        if "no setpoints document" in needle:
            assert len(sent) == 1  # refused before the POST


@pytest.mark.parametrize("first,shape", [
    (b'{"setpoints":[]}', "a setpoints wrapper that is not an object (a list)"),
    (b'{"setpoints":"x"}', "a setpoints wrapper that is not an object (a str)"),
    (b'{"setpoints":3,"hmemKnowledge":true}', "a setpoints wrapper that is not an object (a int)"),
    (b'{"error":"x"}', "JSON with no setpoints wrapper and no hmemKnowledge key"),
    (b'{"ok":true}', "JSON with no setpoints wrapper and no hmemKnowledge key"),
    (b"[]", "JSON that is not an object (a list)"),
    (b"not json", "a body that is not JSON"),
])
def test_first_get_that_is_no_document_names_its_shape_and_sends_no_post(live, monkeypatch, tmp_path, capsys, first, shape):
    """Round 9: `{"setpoints": []}` or `{"error": "x"}` became the snapshot, the machine-wide POST went out, and the failure
    told the operator to restore setpoints called `setpoints` or `error` that were never touched."""
    def wire():
        sent: list[bytes] = []

        def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
            sent.append(request)
            return _framed(first) if len(sent) == 1 else _framed(b'{"setpoints":{"hmemKnowledge":false}}')

        exchange.sent = sent
        return exchange

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    exchange = wire()
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    assert llm.disable_hmem_injection() == ("cannot turn H-MEM injection off: GET /admin/setpoints returned no setpoints "
                                            f"document to compare the change against ({shape}); nothing was changed")
    assert exchange.sent == [b"GET /admin/setpoints HTTP/1.1\r\nHost: meterlessd\r\nAccept: application/json\r\nConnection: close\r\n\r\n"]
    exchange = wire()
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2 and len(exchange.sent) == 1
    err = capsys.readouterr().err
    assert "refusing to run:" in err and shape in err and "other daemon setpoints" not in err


@pytest.mark.parametrize("before,after", [
    (1, True),  # a privacy flag: 1 becomes true
    (0, False),  # 0 becomes false
    (1, 1.0),  # a budget: an integer becomes a float
    (True, 1),
    ({"a": 1}, {"a": True}),  # nested values are compared the same way
])
def test_other_setpoint_that_changes_json_type_is_a_change(live, monkeypatch, before, after):
    """Round 9: Python `!=` treats 1, 1.0 and true as equal (and 0 and false), so a POST that changed a setpoint's type
    passed as unchanged; the daemon's JS reads setpoints with `===`."""
    def changing(method, path, body=None):
        doc = {"hmemKnowledge": False, "privacyFloor": after} if changing.posted else {"hmemKnowledge": True, "privacyFloor": before}
        changing.posted = changing.posted or method == "POST"
        return 200, {"setpoints": doc}

    changing.posted = False
    monkeypatch.setattr(llm, "_control_http", changing)
    problem = llm.disable_hmem_injection() or ""
    assert "changed or removed other daemon setpoints: privacyFloor (values not printed)" in problem
    assert llm._same_json({"b": [1, {"c": 0}], "a": 1.5}, {"a": 1.5, "b": [1, {"c": 0}]})  # key order is not a change


def test_type_changes_on_the_wire_are_caught(live, monkeypatch):
    """The round-9 probe through the real parser: 1 to true, 0 to false and 1 to 1.0 are three changed setpoints."""
    first = b'{"setpoints":{"hmemKnowledge":true,"privacyFloor":1,"cloudAllowed":0,"budget":1}}'
    readback = b'{"setpoints":{"hmemKnowledge":false,"privacyFloor":true,"cloudAllowed":false,"budget":1.0}}'
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        return _framed(first if len(sent) == 1 else readback)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection() or ""
    assert "other daemon setpoints: budget, cloudAllowed, privacyFloor (values not printed)" in problem and len(sent) == 3


@pytest.mark.parametrize("first", [
    b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n",  # cut off right after the headers
    b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n{\"setpoints\":{\"privacyMin\":",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n",  # no chunk at all, no terminating 0-size chunk
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n40\r\n{\"setpoints\":{",  # a chunk shorter than its size
])
def test_first_get_cut_short_refuses_before_the_post(live, monkeypatch, first):
    """Round 3: a first GET cut off after its headers is a failure, not a never-written (empty) snapshot; otherwise a
    daemon that replaced the document would pass with the privacy floor gone."""
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        doc = b'{"setpoints":{"hmemKnowledge":false}}'  # what a replacing daemon would read back: every other key gone
        return first if len(sent) == 1 else b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(doc), doc)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection()
    assert problem and "the first GET /admin/setpoints" in problem and "cut short" in problem
    assert len(sent) == 1  # refused before the POST


DAEMON_BYTES = b"Zq9-daemon-bytes"  # what a malformed field holds; no failure string may repeat it
MALFORMED = [
    (b"HTTP/1.1 200 OK\r\nContent-Length: " + DAEMON_BYTES + b"\r\n\r\n{}", "has a Content-Length that is not a non-negative integer"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: -2\r\n\r\n{}", "has a Content-Length that is not a non-negative integer"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: \r\n\r\n{}", "has a Content-Length that is not a non-negative integer"),
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + DAEMON_BYTES + b"\r\n{}\r\n0\r\n\r\n", "has a chunk size that is not hexadecimal"),
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n-2\r\n{}\r\n0\r\n\r\n", "has a chunk size that is not hexadecimal"),
    (b"HTTP/1.1 " + DAEMON_BYTES + b" OK\r\nContent-Length: 2\r\n\r\n{}", "its status code is not three digits"),
]


@pytest.mark.parametrize("raw,shape", MALFORMED)
def test_malformed_framing_is_reported_by_shape_not_by_the_daemons_bytes(raw, shape):
    """Closing round 1: `int()` raised "invalid literal ... b'<the daemon's bytes>'", which the setter printed."""
    with pytest.raises(ValueError) as caught:
        llm._parse_http_response(raw)
    assert shape in str(caught.value) and DAEMON_BYTES.decode() not in str(caught.value) and "-2" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None  # nothing chained carries the bytes either
    if b"Content-Length: " in raw and b"Content-Length: 2" not in raw:  # the reader's completeness check names the shape too
        with pytest.raises(ValueError, match="Content-Length that is not a non-negative integer") as early:
            llm._http_complete(raw)
        assert DAEMON_BYTES.decode() not in str(early.value) and early.value.__context__ is None


@pytest.mark.parametrize("raw,shape", MALFORMED)
@pytest.mark.parametrize("on", ["GET", "POST"])
def test_malformed_first_get_or_post_answer_names_the_shape_in_the_setter(live, monkeypatch, raw, shape, on):
    """The same through the setter's real request builder and parser: a malformed first GET refuses before the POST; a
    malformed POST answer is a POST failure followed by the best-effort read-back. The daemon's bytes appear in neither."""
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        if request.startswith(on.encode()) and (on == "POST" or len(sent) == 1):
            return raw
        return _framed(_MERGED if any(r.startswith(b"POST") for r in sent) else _SNAPSHOT)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection() or ""
    assert shape in problem and DAEMON_BYTES.decode() not in problem
    if on == "GET":
        assert problem.startswith("cannot turn H-MEM injection off: the first GET /admin/setpoints") and len(sent) == 1
    else:
        assert problem.startswith("cannot turn H-MEM injection off: POST /admin/setpoints") and len(sent) == 3
        assert problem.endswith("shows the POST applied (hmemKnowledge false, no other setpoint changed); retry the run")


def test_malformed_content_length_on_the_pipe_is_reported_by_shape(real_control_exchange, monkeypatch):
    """Through the real exchange (fake `open`): the reader stops at the malformed Content-Length, naming its shape."""
    _fake_open(monkeypatch, lambda path: _FakePipe([b"HTTP/1.1 200 OK\r\nContent-Length: " + DAEMON_BYTES + b"\r\n\r\n{}"]))
    with pytest.raises(ValueError, match="Content-Length that is not a non-negative integer") as caught:
        llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    assert DAEMON_BYTES.decode() not in str(caught.value)


_SNAPSHOT = b'{"setpoints":{"hmemKnowledge":true,"privacyMin":"local-only","hmemTopK":3}}'
# closing round 1: the warning ending every failure after a POST whose effect no read-back could confirm (keys of _SNAPSHOT)
MAY_HAVE_APPLIED = ("the POST may have been applied: check hmemKnowledge and these setpoints in Nightshift before retrying: "
                    "hmemTopK, privacyMin (values not printed)")
_MERGED = b'{"setpoints":{"hmemKnowledge":false,"privacyMin":"local-only","hmemTopK":3},"engines_notified":1}'


def _framed(doc: bytes) -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (len(doc), doc)


def _wire(readback: bytes):
    """A fake `_control_exchange`: the first GET answers `_SNAPSHOT` (other setpoints present), the POST merges
    (`_MERGED`), every GET after the POST answers `readback` as raw bytes; `.sent` records the requests."""
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        if request.startswith(b"POST"):
            return _framed(_MERGED)
        return readback if any(r.startswith(b"POST") for r in sent) else _framed(_SNAPSHOT)

    exchange.sent = sent
    return exchange


@pytest.mark.parametrize("readback,shape", [
    (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n", "no body and no Content-Length or chunked framing (cut off after its headers?)"),
    (_framed(b"not json"), "a body that is not JSON"),
    (_framed(b""), "no body, or JSON null"),
    (_framed(b"null"), "no body, or JSON null"),
    (_framed(b"[]"), "JSON that is not an object (a list)"),
    (_framed(b'{"ok":true}'), "JSON with no setpoints wrapper and no hmemKnowledge key"),
    # round 9: a wrapper that is not an object is unreadable, and the outer object is never read in its place
    (_framed(b'{"setpoints":"garbage","hmemKnowledge":false}'), "a setpoints wrapper that is not an object (a str)"),
    (_framed(b'{"setpoints":"garbage"}'), "a setpoints wrapper that is not an object (a str)"),
    (_framed(b'{"setpoints":[1,2],"hmemKnowledge":false,"privacyMin":"local-only","hmemTopK":3}'), "a setpoints wrapper that is not an object (a list)"),
])
def test_unreadable_readback_names_itself_and_claims_no_lost_setpoints(live, monkeypatch, tmp_path, capsys, readback, shape):
    """Round 8: a read-back that cannot be read was taken as an empty document, so the failure claimed the setpoint read
    back as null and that the POST wiped every other machine-wide setpoint (privacyMin, hmemTopK), which it did not."""
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)  # the real request builder and parser; only the I/O is faked
    exchange = _wire(readback)
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection()
    assert problem == (f"cannot confirm H-MEM injection is off: GET /admin/setpoints answered no readable setpoints document "
                       f"({shape}); {MAY_HAVE_APPLIED}")  # closing round 1: the POST went out, so the operator is told
    assert "other daemon setpoints" not in problem and "read back as" not in problem and len(exchange.sent) == 3
    assert "local-only" not in problem  # keys only, never values
    monkeypatch.setattr(llm, "_control_exchange", _wire(readback))
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "refusing to run:" in err and shape in err and "other daemon setpoints" not in err


@pytest.mark.parametrize("readback,needle", [
    (_framed(b'{"hmemKnowledge":false,"privacyMin":"local-only","hmemTopK":3}'), None),  # a bare document is still read
    (_framed(b'{"hmemKnowledge":false,"hmemTopK":3}'), "other daemon setpoints: privacyMin"),
    (_framed(b'{"setpoints":{"privacyMin":"local-only","hmemTopK":3}}'), "read back as null"),  # wrapped, key missing
])
def test_readable_readback_is_still_compared(live, monkeypatch, readback, needle):
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    monkeypatch.setattr(llm, "_control_exchange", _wire(readback))
    problem = llm.disable_hmem_injection()
    assert (problem is None) if needle is None else (needle in (problem or "") and "no readable setpoints document" not in problem)


_BEFORE = {"hmemKnowledge": True, "privacyMin": "local-only", "hmemTopK": 3}  # the keys of MAY_HAVE_APPLIED
_APPLIED = {"hmemKnowledge": False, "privacyMin": "local-only", "hmemTopK": 3}  # a merging daemon's document after the POST
_REPLACED = {"hmemKnowledge": False}  # a replacing daemon's: every other key gone
_LOST = ("changed or removed other daemon setpoints: hmemTopK, privacyMin (values not printed); they are machine-wide: "
         "check and restore them in Nightshift before a live run")


def _scripted(post, readback):
    """A fake `_control_http`: the first GET answers `_BEFORE`; the POST and the GET after it each answer (status, body)
    or raise the exception given; `.requests` records every request."""
    requests: list[tuple[str, str, object]] = []

    def control_http(method, path, body=None):
        requests.append((method, path, body))
        answer = {"GET": {"setpoints": dict(_BEFORE)}, "POST": post}[method] if len(requests) <= 2 else readback
        if isinstance(answer, BaseException):
            raise answer
        return answer if isinstance(answer, tuple) else (200, answer)

    control_http.requests = requests
    return control_http


POST_RAISES = TimeoutError("no answer within 3 s")  # the bytes may have been written: one deadline covers the whole exchange


@pytest.mark.parametrize("post,needle", [
    (POST_RAISES, f"cannot turn H-MEM injection off: POST /admin/setpoints on {FAKE_PIPE} failed (TimeoutError: no answer within 3 s); "),
    ((500, {"error": "engine restart"}), "cannot turn H-MEM injection off: POST /admin/setpoints answered HTTP 500; "),
])
@pytest.mark.parametrize("readback,shows", [
    ({"setpoints": _REPLACED}, f"a read-back GET /admin/setpoints shows: POST /admin/setpoints {_LOST}"),
    ({"setpoints": dict(_BEFORE)}, "a read-back GET /admin/setpoints shows: H-MEM injection is not off: hmemKnowledge read back as true after POST "
                                   "/admin/setpoints, not false"),
    ({"setpoints": _APPLIED}, "a read-back GET /admin/setpoints shows the POST applied (hmemKnowledge false, no other setpoint changed); retry the run"),
    (BrokenPipeError(32, "Broken pipe"), f"a read-back GET /admin/setpoints failed too (BrokenPipeError); {MAY_HAVE_APPLIED}"),
    ((503, {"setpoints": _APPLIED}), f"a read-back GET /admin/setpoints answered HTTP 503; {MAY_HAVE_APPLIED}"),
    ({"ok": True}, f"a read-back GET /admin/setpoints answered no readable setpoints document (JSON with no setpoints wrapper and no hmemKnowledge key); {MAY_HAVE_APPLIED}"),
])
def test_failed_post_is_followed_by_one_best_effort_readback(live, monkeypatch, tmp_path, capsys, post, needle, readback, shows):
    """Closing round 1: a POST that raised (a timeout, a reset, a cut framing: its bytes may have reached the daemon) or
    answered non-2xx skipped the other-setpoints check and never said the machine-wide change may have been applied. One
    best-effort GET now runs the same checks; when it cannot, the failure ends with the fixed warning (keys only). The
    failure stands even when that GET shows the POST applied."""
    fake = _scripted(post, readback)
    monkeypatch.setattr(llm, "_control_http", fake)
    problem = llm.disable_hmem_injection()
    assert problem == needle + shows
    assert fake.requests == SETTER_REQUESTS  # exactly one best-effort GET after the POST, nothing more
    assert "local-only" not in problem and "engine restart" not in problem  # values never printed
    monkeypatch.setattr(llm, "_control_http", _scripted(post, readback))
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    assert f"refusing to run: {needle}{shows}" in capsys.readouterr().err


@pytest.mark.parametrize("readback,needle", [
    (BrokenPipeError(32, "Broken pipe"), f"cannot confirm H-MEM injection is off: GET /admin/setpoints on {FAKE_PIPE} failed (BrokenPipeError: [Errno 32] Broken pipe)"),
    (ValueError("the control plane's response was cut short (3 of 500 body bytes)"), f"cannot confirm H-MEM injection is off: GET /admin/setpoints on {FAKE_PIPE} failed (ValueError: the control plane's response was cut short (3 of 500 body bytes))"),
    ((404, {"setpoints": _APPLIED}), "cannot confirm H-MEM injection is off: GET /admin/setpoints answered HTTP 404"),
    ({"setpoints": "garbage"}, "cannot confirm H-MEM injection is off: GET /admin/setpoints answered no readable setpoints document (a setpoints wrapper that is not an object (a str))"),
])
def test_failed_readback_after_a_2xx_post_says_the_post_may_have_applied(live, monkeypatch, tmp_path, capsys, readback, needle):
    """Closing round 1: a read-back that failed after a 2xx POST (an exception, a non-2xx status, no readable document)
    skipped the comparison and said nothing about the machine-wide change; the failure now ends with the fixed warning
    naming the first GET's keys (values never printed), and no further request is sent."""
    fake = _scripted((200, {"setpoints": _APPLIED, "engines_notified": 1}), readback)
    monkeypatch.setattr(llm, "_control_http", fake)
    problem = llm.disable_hmem_injection()
    assert problem == f"{needle}; {MAY_HAVE_APPLIED}"
    assert fake.requests == SETTER_REQUESTS and "local-only" not in problem and "other daemon setpoints" not in problem
    monkeypatch.setattr(llm, "_control_http", _scripted((200, {"setpoints": _APPLIED}), readback))
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    assert f"refusing to run: {needle}; {MAY_HAVE_APPLIED}" in capsys.readouterr().err


def test_may_have_applied_warning_on_a_never_written_daemon(live, control):
    """A daemon whose setpoints were never written has no other key to list; the warning still names hmemKnowledge."""
    control(unwritten="wrapped", raise_on="readback")
    assert llm.disable_hmem_injection().endswith(
        "the POST may have been applied: check hmemKnowledge in Nightshift before retrying (no other setpoint was set before the POST)")


def test_response_cut_by_a_broken_pipe_after_its_headers_is_not_an_empty_body(real_control_exchange, monkeypatch):
    # round 7: a broken pipe before any body byte is re-raised (it used to end the body, which the parser then refused)
    _fake_open(monkeypatch, lambda path: _FakePipe([b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n", BrokenPipeError(32, "Broken pipe")]))
    with pytest.raises(BrokenPipeError):
        llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    _fake_open(monkeypatch, lambda path: _FakePipe([b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n{", BrokenPipeError(32, "Broken pipe")]))
    raw = llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    with pytest.raises(ValueError, match=r"cut short \(1 of 500 body bytes\)"):  # a body begun, then cut: the parser refuses it
        llm._parse_http_response(raw)


@pytest.mark.skipif(sys.platform != "win32", reason="the per-user pipe name is derived on Windows only")
def test_profile_path_that_is_not_unicode_is_a_clear_live_start_failure(live, monkeypatch, tmp_path, capsys):
    """Round 3: an unpaired surrogate in LOCALAPPDATA cannot be encoded as UTF-8; the live start exits 2 with a message
    (no traceback), and nothing is opened (the pipe name could not be built)."""
    monkeypatch.delenv("METERLESS_CONTROL_SOCKET")
    monkeypatch.setattr(llm, "_local_app_data", lambda: "C:\\Users\\\ud800x\\AppData\\Local")
    with pytest.raises(OSError, match="not valid Unicode"):
        llm.control_socket_path()
    problem = llm.disable_hmem_injection()
    assert problem and "cannot derive the Meterless control pipe name" in problem and "UnicodeEncodeError" in problem
    client = live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))  # a probe that went out would land here
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    assert "refusing to run: cannot turn H-MEM injection off: cannot derive" in capsys.readouterr().err
    assert run.main(["--probe"]) == 2
    # round 4: exit 2 alone also holds when the probe went out and failed; the guard must refuse before it is sent
    assert "refusing to run: cannot turn H-MEM injection off: cannot derive" in capsys.readouterr().err
    assert client.kwargs == []


@pytest.mark.parametrize("argv", [["--model", "live"], []])  # []: no --model, a configured route is a live run
def test_live_run_sets_the_setpoint_before_the_graph(live, control, monkeypatch, tmp_path, capsys, argv):
    plane = control()
    seen = {}

    def fake_run_local(*a, **k):
        seen["requests"] = list(plane.requests)
        seen["dry_run"] = k.get("dry_run")
        raise llm.RateLimitAbort(LIGHTNING, 2)  # leave main() through a path it already handles (exit 3)

    monkeypatch.setattr(graph, "run_local", fake_run_local)
    monkeypatch.setattr(llm, "current_run_id", None)
    assert run.main([*argv, "--quiet", "--out", str(tmp_path)]) == 3
    assert seen == {"requests": SETTER_REQUESTS, "dry_run": False}
    assert plane.requests == SETTER_REQUESTS  # nothing more on the way out (exit 3): the setpoint is never turned back on
    assert "hmemKnowledge read back false" in capsys.readouterr().err


def test_live_run_checks_its_checkpoint_before_the_setter(live, control, monkeypatch, tmp_path, capsys):
    """Round 4: the machine-wide setter runs only when the graph will send a completion. A resume with no checkpoint, a
    fresh run over an existing checkpoint and a resume of a thread that already finished reach no control request."""
    plane = control()
    client = live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    monkeypatch.setattr(llm, "current_run_id", None)
    monkeypatch.setattr(llm, "journal_loaded_for", None)
    out = ["--quiet", "--out", str(tmp_path)]

    assert run.main(["--model", "live", "--resume", *out]) == 2
    assert "refusing to run: nothing to resume: no checkpoint for run" in capsys.readouterr().err
    assert plane.requests == [] and not (tmp_path / "_checkpoints").exists()  # and no empty checkpoint file left behind

    rid = ids.run_id("russia-ukraine-war", "2026-10-22", 1)  # a finished thread under the live run's id (a dry graph run)
    graph.run_local("russia-ukraine-war", "2026-10-22", dry_run=True, corpus="fixture", attempt=1,
                    checkpoint_path=str(tmp_path / "_checkpoints" / f"{rid}.sqlite"))
    assert run.main(["--model", "live", *out]) == 2
    assert f"refusing to run: run {rid} already has a checkpoint" in capsys.readouterr().err
    assert plane.requests == []

    assert run.main(["--model", "live", "--resume", *out]) in (0, 2)  # nothing left to run: the stored state is published
    assert "refusing to run" not in capsys.readouterr().err
    assert plane.requests == [] and client.kwargs == []

    monkeypatch.setattr(graph, "run_local", lambda *a, **k: (_ for _ in ()).throw(llm.RateLimitAbort(LIGHTNING, 2)))
    assert run.main(["--model", "live", "--attempt", "2", *out]) == 3  # a fresh attempt still runs the setter first
    assert plane.requests == SETTER_REQUESTS


def test_live_resume_with_work_left_runs_the_setter_before_the_graph(live, control, monkeypatch, tmp_path, capsys):
    """Round 7: the unsafe side of `checkpoint_problem`'s `sends`. A thread interrupted mid-graph (a dry run whose sixth
    model call raised RateLimitAbort, as a drained route does) is resumed with `--model live --resume`, as
    scripts/resume_with_next_key.sh does: the setter's three requests go out before the graph starts. Skipping the
    setter on a resume (`return None, False`, or `and not args.resume` at the call) fails here."""
    rid = ids.run_id("russia-ukraine-war", "2026-10-22", 1)
    ck = tmp_path / "_checkpoints" / f"{rid}.sqlite"
    real_json_task, calls = llm.json_task, []

    def interrupted(task, payload, *, dry_run, which="default"):
        calls.append(task)
        if len(calls) == 6:
            raise llm.RateLimitAbort(LIGHTNING, 2)
        return real_json_task(task, payload, dry_run=dry_run, which=which)

    monkeypatch.setattr(llm, "json_task", interrupted)
    with pytest.raises(llm.RateLimitAbort):
        graph.run_local("russia-ukraine-war", "2026-10-22", dry_run=True, corpus="fixture", attempt=1, checkpoint_path=str(ck))
    monkeypatch.setattr(llm, "json_task", real_json_task)
    assert len(calls) == 6 and run.checkpoint_problem(str(ck), rid, True) == (None, True)  # work left to send

    plane = control()
    client = live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    monkeypatch.setattr(llm, "current_run_id", None)
    monkeypatch.setattr(llm, "journal_loaded_for", None)
    seen = {}

    def fake_run_local(*a, **k):
        seen.update(requests=list(plane.requests), resume=k.get("resume"), checkpoint=k.get("checkpoint_path"))
        raise llm.RateLimitAbort(LIGHTNING, 2)  # leave main() through a path it already handles (exit 3)

    monkeypatch.setattr(graph, "run_local", fake_run_local)
    assert run.main(["--model", "live", "--resume", "--quiet", "--out", str(tmp_path)]) == 3
    assert seen == {"requests": SETTER_REQUESTS, "resume": True, "checkpoint": str(ck)}  # the setter first, then the graph
    assert plane.requests == SETTER_REQUESTS and client.kwargs == []
    assert "hmemKnowledge read back false" in capsys.readouterr().err


def test_dry_switch_only_in_dotenv_skips_the_setter_on_an_implicit_live_run(live, monkeypatch, tmp_path):
    """No --model, a configured route, QUORUM_DRY_RUN=1 only in .env: the run is dry, so the daemon is not touched
    (the env fixture fails the test if the setter is reached)."""
    monkeypatch.setattr(llm, "_env", lambda: monkeypatch.setenv("QUORUM_DRY_RUN", "1"))  # what load_dotenv would set
    seen = {}

    def fake_run_local(*a, **k):
        seen["dry"] = llm.is_dry_run(False)
        raise llm.RateLimitAbort(LIGHTNING, 2)

    monkeypatch.setattr(graph, "run_local", fake_run_local)
    monkeypatch.setattr(llm, "current_run_id", None)
    assert run.main(["--quiet", "--out", str(tmp_path)]) == 3
    assert seen == {"dry": True}


def _dry_twins_client(hmem_for=lambda task, n: None):
    """A fake client that answers every completion with the task's dry-run twin, on a held lane; `hmem_for(task, n)`
    (n: the task's 1-based call count) is the receipt's hmem block for that call (None: hmem null, served)."""
    from quorum_reasoning import dryrun
    from quorum_reasoning.untrusted import DATA_NOTE

    tasks = {llm._prompt(p.stem): p.stem for p in llm._PROMPTS.glob("*.md") if hasattr(dryrun, p.stem)}
    seen: dict[str, int] = {}

    class _DryTwins(_Client):
        def _raw(self, **kwargs):
            self.kwargs.append(kwargs)
            system, user = (m["content"] for m in kwargs["messages"])
            task = tasks[system]
            seen[task] = seen.get(task, 0) + 1
            answer = getattr(dryrun, task)(json.loads(user[len(DATA_NOTE) + 1:]))
            model = kwargs["model"]
            met = _met(model, model, model, hmem=hmem_for(task, seen[task]))
            completion = _completion(model, met, json.dumps(answer, ensure_ascii=False))
            return SimpleNamespace(parse=lambda: completion, status_code=200)

    return _DryTwins(None)


def test_live_graph_run_to_publish_never_turns_the_setpoint_back_on(live, control, monkeypatch, tmp_path):
    """A whole live graph run on the fixture corpus, every completion answered by the task's dry-run twin through the
    fake client: after publish, the control plane saw only the setter's three requests."""
    plane = control()
    client = _dry_twins_client()
    monkeypatch.setattr(llm, "_client", lambda: client)
    monkeypatch.setattr(llm, "current_run_id", None)
    monkeypatch.setattr(llm, "journal_loaded_for", None)
    assert run.main(["--model", "live", "--corpus", "fixture", "--quiet", "--out", str(tmp_path)]) in (0, 2)
    assert client.kwargs, "the graph made live calls"
    assert (tmp_path / "russia-ukraine-war" / "2026-10-22" / "v1.json").is_file()  # published
    assert plane.requests == SETTER_REQUESTS
    assert llm.hmem_rejected_count() == 0 and llm.substitution_count() == 0


def _summary_line(out: str) -> str:
    lines = [line for line in out.splitlines() if line.startswith("model calls: ")]
    assert len(lines) == 1, out
    return lines[0]


def test_run_summary_prints_the_rejections_and_the_declined_replays(live, control, monkeypatch, tmp_path, capsys):
    """Review round 6: the operator reads the rejection and refusal counts on the run summary's "model calls:" line;
    only `flagged_calls_note()` was tested, and every run.main test passed --quiet, so dropping the note from the line
    went unnoticed. Run 1 (not quiet): the first stance reply carries hmem.injected 2 and is rejected. Run 2 (a fresh
    attempt with --seed-journal): its journal holds one served reply from run 1 relabelled as injected, which is
    declined for replay and named as such, never as a rejection."""
    control()
    monkeypatch.setattr(llm, "current_run_id", None)
    monkeypatch.setattr(llm, "journal_loaded_for", None)
    client = _dry_twins_client(lambda task, n: {"injected": 2} if task == "stance" and n == 1 else None)
    monkeypatch.setattr(llm, "_client", lambda: client)
    out = ["--corpus", "fixture", "--out", str(tmp_path)]
    assert run.main(["--model", "live", *out]) in (0, 2)
    line = _summary_line(capsys.readouterr().out)
    assert llm.hmem_rejected_count() == 1
    assert "1 rejected for injected memories" in line and "not replayed" not in line

    first = ids.run_id("russia-ukraine-war", "2026-10-22", 1)
    rows = [json.loads(r) for r in (tmp_path / "_journal" / f"{first}.jsonl").read_text(encoding="utf-8").splitlines()]
    served = next(r for r in rows if r.get("reply") and not r.get("error"))
    served["receipt_hmem_injected"] = 2  # as a run journalled before the rejection existed
    second = ids.run_id("russia-ukraine-war", "2026-10-22", 2)
    (tmp_path / "_journal" / f"{second}.jsonl").write_text(json.dumps(served) + "\n", encoding="utf-8")
    llm.reset_calls()
    plane = control()
    monkeypatch.setattr(llm, "_client", lambda: _dry_twins_client())
    assert run.main(["--model", "live", "--attempt", "2", "--seed-journal", *out]) in (0, 2)
    line = _summary_line(capsys.readouterr().out)
    assert llm.replay_refused_count() == 1 and llm.hmem_rejected_count() == 0
    assert "1 journalled replies not replayed" in line and "rejected" not in line
    assert plane.requests == SETTER_REQUESTS  # round 7: a --seed-journal run turns injection off like any fresh live run


def test_non_loopback_meterless_base_is_a_live_start_failure_and_sends_nothing(env, monkeypatch, tmp_path, capsys):
    env.setenv("METERLESS_BASE_URL", "http://10.0.0.5:8088/v1")
    env.setenv("METERLESS_TOKEN", "test-token-not-real")
    env.setenv("NEMOTRON_MODEL", LIGHTNING)
    assert llm.on_meterless() and llm.route_configured()
    problem = llm.disable_hmem_injection()  # the env fixture fails the test if this reaches the control plane
    assert problem and "host 10.0.0.5 is not loopback" in problem
    monkeypatch.setattr(graph, "run_local", lambda *a, **k: pytest.fail("the graph must not start"))
    assert run.main(["--model", "live", "--quiet", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "refusing to run:" in err and "not loopback" in err and "read back false" not in err


@pytest.mark.parametrize("base", ["http://127.0.0.1:8088/v1", "http://localhost:8088/v1", "http://[::1]:8088/v1"])
def test_loopback_meterless_bases_run_the_setter(env, control, base):
    env.setenv("METERLESS_BASE_URL", base)
    env.setenv("METERLESS_TOKEN", "test-token-not-real")
    plane = control()
    assert llm.disable_hmem_injection() is None and plane.requests == SETTER_REQUESTS


@pytest.mark.parametrize("flag", ["--test-connection", "--probe"])
def test_cli_checks_refuse_on_failed_readback_and_send_no_completion(live, control, monkeypatch, capsys, flag):
    control(readback=True)
    client = live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    assert run.main([flag]) == 2
    assert client.kwargs == [] and "read back as true" in capsys.readouterr().err


@pytest.mark.parametrize("hmem,needle", [
    ({"injected": 1}, "injected 1 prior answers"),  # the boundary
    ({"injected": 2}, "injected 2 prior answers"),
    ({"reason": "retrieved 2 memories"}, "no readable injected count"),
])
@pytest.mark.parametrize("flag", ["--test-connection", "--probe"])
def test_cli_checks_reject_an_injected_reply(live, control, capsys, flag, hmem, needle):
    plane = control()
    live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING, hmem=hmem), '{"stance": "neutral"}'))
    assert run.main([flag]) == 2
    err = capsys.readouterr().err
    assert "MemoryInjected" in err and needle in err
    assert plane.requests == SETTER_REQUESTS  # the setter ran first on this family too (round 6)


@pytest.mark.parametrize("setup,needle", [
    ({"METERLESS_BASE_URL": "http://127.0.0.1:8088/v1"}, "no model route configured"),  # a Meterless base, no token
    ({"METERLESS_BASE_URL": "http://127.0.0.1:8088/v1", "MODEL_API_KEY": "k"}, "METERLESS_BASE_URL with MODEL_API_KEY"),
])
@pytest.mark.parametrize("flag", ["--test-connection", "--probe"])
def test_cli_checks_on_an_unusable_route_never_reach_the_daemon(env, control, monkeypatch, capsys, flag, setup, needle):
    for name, value in setup.items():
        env.setenv(name, value)
    assert llm.on_meterless() and not llm.route_configured()
    plane = control()
    client = _Client(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    monkeypatch.setattr(llm, "_client", lambda: client)
    assert run.main([flag]) == 2
    err = capsys.readouterr().err
    assert "refusing to run:" in err and needle in err
    assert plane.requests == [] and client.kwargs == []


@pytest.mark.parametrize("argv", [["--models"], ["--models", "--test-connection"]])  # --models wins: no completion
def test_models_never_runs_the_setter(live, control, monkeypatch, capsys, argv):
    plane = control()
    client = live(_completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING)))
    monkeypatch.setattr(llm, "list_models", lambda: [LIGHTNING, ULTRA])
    assert run.main(argv) == 0
    assert LIGHTNING in capsys.readouterr().out
    assert plane.requests == [] and client.kwargs == []


# The control pipe's name: golden values computed by Nightshift's own cli/lib/transport.mjs controlSocketPath (node,
# 2026-10-25), so the formula and its fallbacks are checked against the CLI, not against this module.
GOLDEN_PIPE_KEYS = [
    ({"LOCALAPPDATA": r"C:\Users\Someone\AppData\Local"}, "21f8137d3ba8"),
    ({"LOCALAPPDATA": "C:\\Users\\\u00dcn\u00efc\u00f6d\u00e9 \u00d1ame\\AppData\\Local"}, "99c3fe90cae4"),  # UTF-8 bytes, not latin-1
    ({"LOCALAPPDATA": r"C:\Users\Carol\AppData\Local"}, "d2f8ef3d967d"),
    ({"LOCALAPPDATA": r"C:\Users\user3\AppData\Local"}, "0be448cfdb04"),  # round 4: a leading 0 (padStart(12, '0'))
    ({"USERPROFILE": "C:/Users/Bob"}, "5a4c4fd7576b"),  # path.join normalizes the fallback ...
    ({"USERPROFILE": r"C:\Users\x\..\Bob"}, "5a4c4fd7576b"),
    ({"USERPROFILE": "C:\\Users\\Bob\\"}, "5a4c4fd7576b"),  # ... and drops the trailing separator
]


def _profile_env(env, environ):
    env.delenv("METERLESS_CONTROL_SOCKET")
    for name in ("LOCALAPPDATA", "USERPROFILE"):
        env.delenv(name, raising=False)
    for name, value in environ.items():
        env.setenv(name, value)


@pytest.mark.parametrize("environ,key", GOLDEN_PIPE_KEYS)
def test_control_pipe_name_matches_transport_mjs(env, environ, key):
    _profile_env(env, environ)
    env.setattr(llm, "_windows_profile_dir", lambda: pytest.fail("USERPROFILE or LOCALAPPDATA is set: no profile lookup"))
    assert llm._user_key(llm._local_app_data()) == key and len(key) == 12
    if sys.platform == "win32":
        assert llm.control_socket_path() == rf"\\.\pipe\ai.meterless.runtime-{key}-runtime"
    else:
        assert llm.control_socket_path() == llm.CONTROL_SOCKET_POSIX
    env.setenv("METERLESS_CONTROL_SOCKET", r"\\.\pipe\override")
    assert llm.control_socket_path() == r"\\.\pipe\override"


def test_fnv_vectors():
    # FNV-1a 64 published vectors: "" -> cbf29ce484222325, "a" -> af63dc4c8601ec8c; low 48 bits, input lower-cased
    assert llm._user_key("") == "9ce484222325" and llm._user_key("A") == "dc4c8601ec8c"


def test_control_pipe_name_without_localappdata_or_userprofile_uses_the_profile_directory(env):
    _profile_env(env, {"HOMEDRIVE": "D:", "HOMEPATH": r"\Home\Carol"})  # not what libuv's os.homedir() reads
    env.setattr(llm, "_windows_profile_dir", lambda: r"C:\Users\Carol")
    assert llm._local_app_data() == r"C:\Users\Carol\AppData\Local"
    assert llm._user_key(llm._local_app_data()) == "d2f8ef3d967d"  # transport.mjs: path.join(os.homedir(), 'AppData', 'Local')


def test_control_pipe_name_that_cannot_be_derived_is_a_live_start_failure(env):
    _profile_env(env, {"METERLESS_TOKEN": "test-token-not-real"})
    env.setattr(llm, "_windows_profile_dir", lambda: None)
    with pytest.raises(OSError, match="cannot derive the Meterless control pipe name"):
        llm._local_app_data()
    if sys.platform == "win32":  # elsewhere the packaged Unix socket needs no profile
        problem = llm.disable_hmem_injection()  # the env fixture fails the test if this reaches the control plane
        assert problem and "cannot derive the Meterless control pipe name" in problem


@pytest.mark.skipif(sys.platform != "win32", reason="GetUserProfileDirectoryW is Windows-only")
def test_profile_directory_is_read_from_the_process_token():
    import ntpath
    import os

    found = llm._windows_profile_dir()
    assert found and ntpath.isabs(found)
    if os.environ.get("USERPROFILE"):
        assert ntpath.normcase(ntpath.normpath(found)) == ntpath.normcase(ntpath.normpath(os.environ["USERPROFILE"]))


# _control_exchange: the only code that touches the pipe, driven here through a fake `open` inside llm --------------

class _FakePipe:
    """Answers each read with the next scripted item: bytes, an exception to raise, or a callable to call."""

    def __init__(self, reads):
        self.reads, self.written = list(reads), b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data):
        self.written += data
        return len(data)

    def read(self, n):
        item = self.reads.pop(0) if self.reads else b""
        if isinstance(item, BaseException):
            raise item
        return item() if callable(item) else item


def _fake_open(monkeypatch, behaviour):
    """Replaces `open` inside llm with `behaviour`, and the GetFileType check with "a pipe" (a fake has no OS handle;
    test_pipe_shaped_path_to_a_regular_file_is_refused_before_writing drives the real check). The pipe branch runs on
    Windows only (decision in `llm._control_exchange`), so every test that fakes the pipe skips elsewhere."""
    if sys.platform != "win32":
        pytest.skip("the named-pipe transport is Windows-only; elsewhere every path is a Unix socket")
    opened = []

    def fake(path, mode="r", buffering=-1):
        opened.append((path, mode, buffering))
        return behaviour(path)

    monkeypatch.setattr(llm, "open", fake, raising=False)  # shadows the builtin inside llm only
    monkeypatch.setattr(llm, "_file_type", lambda pipe: llm.FILE_TYPE_PIPE)
    return opened


def test_control_exchange_times_out_on_a_silent_pipe(real_control_exchange, monkeypatch):
    release = threading.Event()
    opened = _fake_open(monkeypatch, lambda path: _FakePipe([lambda: release.wait(5) and b""]))
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=0.2)
        assert time.monotonic() - started < 1.5  # the caller is not held by a daemon that never answers
    finally:
        release.set()
    assert opened == [(FAKE_PIPE, "r+b", 0)]


def test_control_timeout_is_the_clis_3_s(env, real_control_exchange, monkeypatch):
    import inspect

    assert llm.CONTROL_TIMEOUT_S == 3.0  # transport.mjs: 3 s; pinned both ways (a 0 s timeout fails every live start)
    assert inspect.signature(real_control_exchange).parameters["timeout"].default == llm.CONTROL_TIMEOUT_S
    seen: list[object] = []

    def exchange(where, request, timeout=None):
        seen.append(timeout)
        return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"

    monkeypatch.setattr(llm, "_control_exchange", exchange)
    assert _REAL_CONTROL_HTTP("GET", "/admin/setpoints") == (200, {})
    assert seen == [None]  # `_control_http` passes no timeout: the 3 s default applies, never a shorter one


def test_default_control_timeout_waits_for_a_slow_daemon(real_control_exchange, monkeypatch):
    """A daemon that answers after 0.5 s is answered through the default timeout (a 0 s or 0.1 s default fails here)."""
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    _fake_open(monkeypatch, lambda path: _FakePipe([lambda: time.sleep(0.5) or reply]))
    assert llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n") == reply


def _busy(where):
    return OSError(errno.EINVAL, "Invalid argument", where)  # what open() raises for ERROR_PIPE_BUSY (the CRT's mapping)


def test_busy_pipe_is_waited_for_and_retried(real_control_exchange, monkeypatch):
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    answers = [_busy(FAKE_PIPE), _FakePipe([reply])]

    def behaviour(path):
        item = answers.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    waits: list[tuple[str, int]] = []
    monkeypatch.setattr(llm, "_wait_named_pipe", lambda where, ms: waits.append((where, ms)) or 0)
    opened = _fake_open(monkeypatch, behaviour)
    assert llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2) == reply
    assert len(opened) == 2 and len(waits) == 1
    assert waits[0][0] == FAKE_PIPE and 0 < waits[0][1] <= llm.PIPE_BUSY_WAIT_S * 1000 == 2000


@pytest.mark.skipif(sys.platform != "win32", reason="OSError carries winerror on Windows only")
def test_busy_pipe_reported_by_winerror_is_waited_for(real_control_exchange, monkeypatch):
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    answers = [OSError(None, "All pipe instances are busy", FAKE_PIPE, llm.ERROR_PIPE_BUSY), _FakePipe([reply])]

    def behaviour(path):
        item = answers.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(llm, "_wait_named_pipe", lambda where, ms: 0)
    _fake_open(monkeypatch, behaviour)
    assert llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2) == reply


@pytest.mark.parametrize("wait_code", [llm.ERROR_SEM_TIMEOUT, 0])  # 121: still busy; 0: freed, then taken again each time
def test_pipe_that_stays_busy_is_a_clear_live_start_failure(live, real_control_exchange, monkeypatch, wait_code):
    monkeypatch.setattr(llm, "PIPE_BUSY_WAIT_S", 0.2)
    monkeypatch.setattr(llm, "_wait_named_pipe", lambda where, ms: wait_code)
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)

    def always_busy(path):
        raise _busy(path)

    _fake_open(monkeypatch, always_busy)
    started = time.monotonic()
    problem = llm.disable_hmem_injection()
    assert problem and "the control pipe is busy" in problem and "ControlPipeBusy" in problem and "Invalid argument" not in problem
    assert time.monotonic() - started < 1.5


@pytest.mark.parametrize("code,raised", [(llm.ERROR_FILE_NOT_FOUND, FileNotFoundError), (87, OSError)])
def test_einval_not_confirmed_busy_is_reraised(real_control_exchange, monkeypatch, code, raised):
    monkeypatch.setattr(llm, "_wait_named_pipe", lambda where, ms: code)

    def refuse(path):
        raise _busy(path)

    opened = _fake_open(monkeypatch, refuse)
    with pytest.raises(raised) as caught:
        llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    assert not isinstance(caught.value, llm.ControlPipeBusy) and len(opened) == 1


@pytest.mark.parametrize("reply", [
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n",
])
def test_control_exchange_returns_once_the_response_is_complete(real_control_exchange, monkeypatch, reply):
    """A daemon that keeps its end open after a complete reply: the next read would block, so the exchange must stop
    reading at the end of the response and not wait for the timeout."""
    release = threading.Event()
    _fake_open(monkeypatch, lambda path: _FakePipe([reply, lambda: release.wait(5) and b""]))
    started = time.monotonic()
    try:
        assert llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2) == reply
        assert time.monotonic() - started < 1.0
    finally:
        release.set()


def test_control_exchange_reraises_an_open_failure(real_control_exchange, monkeypatch):
    def refuse(path):
        raise FileNotFoundError(2, "The system cannot find the file specified", path)

    _fake_open(monkeypatch, refuse)
    with pytest.raises(FileNotFoundError):
        llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)


def test_control_exchange_keeps_a_response_cut_by_a_broken_pipe(real_control_exchange, monkeypatch):
    head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
    body = b'{"setpoints":{"hmemKnowledge":false}}'
    pipe = _FakePipe([head, body, BrokenPipeError(32, "Broken pipe")])  # no Content-Length: the daemon closes its end
    _fake_open(monkeypatch, lambda path: pipe)
    raw = llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    assert raw == head + body and pipe.written == b"GET /admin/setpoints HTTP/1.1\r\n\r\n"
    assert llm._parse_http_response(raw) == (200, {"setpoints": {"hmemKnowledge": False}})
    _fake_open(monkeypatch, lambda path: _FakePipe([b"HTTP/1.1 2", BrokenPipeError(32, "Broken pipe")]))
    with pytest.raises(BrokenPipeError):  # cut before the headers ended: nothing usable
        llm._control_exchange(FAKE_PIPE, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)


HEAD_ONLY = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"  # close-delimited: no Content-Length


@pytest.mark.parametrize("stall", [TimeoutError("timed out"), OSError(errno.EIO, "I/O error")])
def test_response_stalled_after_its_headers_is_a_failure_not_an_empty_body(stall):
    """Round 4 (coordinator decision 6): a timeout after the headers is a stall, not the daemon closing its end; it used
    to parse as (200, None), which the setter reads as setpoints never written."""
    with pytest.raises(type(stall)):
        llm._read_response(_FakePipe([HEAD_ONLY, stall]).read)


@pytest.mark.parametrize("close", [b"", BrokenPipeError(errno.EPIPE, "Broken pipe"), ConnectionResetError(errno.ECONNRESET, "reset")])
def test_close_after_the_headers_still_ends_a_close_delimited_body(close):
    assert llm._read_response(_FakePipe([HEAD_ONLY, b"{}", close]).read) == HEAD_ONLY + b"{}"


@pytest.mark.parametrize("close", [BrokenPipeError(errno.EPIPE, "Broken pipe"), ConnectionResetError(errno.ECONNRESET, "reset")])
def test_reset_before_any_body_byte_is_reraised(close):
    """Round 7: a reset or broken pipe right after the headers is a failure, not the end of an empty body."""
    with pytest.raises(type(close)):
        llm._read_response(_FakePipe([HEAD_ONLY, close]).read)
    assert llm._read_response(_FakePipe([HEAD_ONLY, b""]).read) == HEAD_ONLY  # EOF: the framing rule refuses it below


@pytest.mark.parametrize("first", [HEAD_ONLY, HEAD_ONLY + b"\r\n", b"HTTP/1.1 200 OK\r\n\r\n"])
def test_unframed_empty_first_get_refuses_before_the_post(live, monkeypatch, first):
    """Round 7 (coordinator decision 6): a first GET with no body and no Content-Length or chunked framing is what a GET
    cut off after its headers looks like; it refuses before the POST instead of reading as never written (a replacing
    daemon would otherwise pass with the privacy floor gone)."""
    sent: list[bytes] = []

    def exchange(where, request, timeout=llm.CONTROL_TIMEOUT_S):
        sent.append(request)
        doc = b'{"setpoints":{"hmemKnowledge":false}}'  # what a replacing daemon would read back: every other key gone
        return first if len(sent) == 1 else b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(doc), doc)

    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    monkeypatch.setattr(llm, "_control_exchange", exchange)
    problem = llm.disable_hmem_injection()
    assert problem and "the first GET /admin/setpoints answered no body and no Content-Length or chunked framing" in problem
    assert len(sent) == 1  # refused before the POST


@pytest.mark.parametrize("close,needle", [
    (b"", "the first GET /admin/setpoints answered no body and no Content-Length"),  # EOF: the framing rule
    (ConnectionResetError(errno.ECONNRESET, "reset"), "(ConnectionResetError"),  # re-raised by `_read_response`
    (BrokenPipeError(errno.EPIPE, "Broken pipe"), "(BrokenPipeError"),
])
def test_first_get_closed_right_after_its_headers_refuses_before_the_post(live, real_control_exchange, monkeypatch, close, needle):
    """The same through the real exchange and parser (fake `open`): EOF, a reset or a broken pipe right after the
    headers of a close-delimited first GET; one open, so no POST was sent."""
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    opened = _fake_open(monkeypatch, lambda path: _FakePipe([HEAD_ONLY, close]))
    problem = llm.disable_hmem_injection()
    assert problem and problem.startswith("cannot turn H-MEM injection off:") and needle in problem
    assert len(opened) == 1


def test_first_get_stalled_after_its_headers_refuses_before_the_post(live, real_control_exchange, monkeypatch):
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    opened = _fake_open(monkeypatch, lambda path: _FakePipe([HEAD_ONLY, TimeoutError("timed out")]))
    problem = llm.disable_hmem_injection()
    assert problem and "TimeoutError" in problem and len(opened) == 1  # the first GET failed: no POST was sent


class _DripSocket:
    """A Unix socket whose daemon sends one byte every 0.1 s (40 at most, then closes); honours settimeout."""

    def __init__(self, *args):
        self.timeouts: list[float] = []
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, value):
        self.timeouts.append(value)

    def connect(self, where):
        self.where = where

    def sendall(self, data):
        self.sent = data

    def recv(self, n):
        self.reads += 1
        if self.reads > 40:
            return b""  # bounded, so a per-recv timeout fails this test instead of hanging it
        if self.timeouts[-1] < 0.1:
            time.sleep(self.timeouts[-1])
            raise TimeoutError("timed out")
        time.sleep(0.1)
        return b"x"


def test_unix_socket_exchange_has_one_overall_deadline(real_control_exchange, monkeypatch):
    """Round 4: a per-recv timeout let a daemon that trickles bytes hold the live start for as long as it kept sending;
    the whole exchange now ends at `timeout` (the AF_UNIX branch, driven here on any host with a fake socket)."""
    import socket

    socks: list[_DripSocket] = []
    monkeypatch.setattr(llm, "sys", SimpleNamespace(platform="linux"))  # llm's own view of the host only
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *a: socks.append(_DripSocket()) or socks[-1])
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        llm._control_exchange("/tmp/quorum-test-no-such.sock", b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=0.5)
    assert time.monotonic() - started < 1.5
    assert socks[0].where == "/tmp/quorum-test-no-such.sock" and all(0 < t <= 0.5 for t in socks[0].timeouts)


@pytest.mark.skipif(sys.platform != "win32", reason="WaitNamedPipeW is Windows-only")
@pytest.mark.parametrize("where", [r"\\.\pipe\quorum-test-no-such-pipe", "//./pipe/quorum-test-no-such-pipe",
                                   r"\\?\pipe\quorum-test-no-such-pipe", r"\\.\PIPE\quorum-test-no-such-pipe"])
def test_wait_named_pipe_reports_a_pipe_that_does_not_exist(where):
    """Round 4: the real WaitNamedPipeW seam (it connects to nothing), which every busy-pipe test replaces: a name that
    does not exist is ERROR_FILE_NOT_FOUND in every spelling, so an EINVAL that is not busy is never retried as busy."""
    assert llm._wait_named_pipe(where, 50) == llm.ERROR_FILE_NOT_FOUND


@pytest.mark.parametrize("where", [r"\\.\pipe\quorum-test-x", r"\\?\pipe\quorum-test-x", r"\\.\PIPE\quorum-test-x", "//./pipe/quorum-test-x"])
def test_control_exchange_takes_every_pipe_spelling(real_control_exchange, monkeypatch, where):
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    opened = _fake_open(monkeypatch, lambda path: _FakePipe([reply]))
    assert llm._control_exchange(where, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2) == reply
    assert [o[0] for o in opened] == [where]


@pytest.mark.skipif(sys.platform != "win32", reason="the AF_UNIX refusal is Windows-only")
def test_control_exchange_refuses_a_unix_socket_path_on_windows(real_control_exchange, monkeypatch):
    opened = _fake_open(monkeypatch, lambda path: pytest.fail("not a pipe: nothing may be opened"))
    with pytest.raises(OSError, match="Unix control sockets are not supported on Windows"):
        llm._control_exchange("/tmp/quorum-test-no-such.sock", b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    assert opened == []


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 path normalisation of a \\\\.\\pipe\\..\\ path is Windows-only")
@pytest.mark.parametrize("prefix", ["\\\\.\\pipe\\..\\", "//./pipe/../", "\\\\.\\PIPE\\..\\"])
def test_pipe_shaped_path_to_a_regular_file_is_refused_before_writing(live, real_control_exchange, monkeypatch, tmp_path, prefix):
    """Round 5: the prefix alone took `\\\\.\\pipe\\..\\C:\\...\\victim.txt` for a pipe; Win32 resolves it to the regular file,
    which the setter's POST overwrote. The real `open` and the real GetFileType run here on a scratch file (no pipe)."""
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"original contents\r\n")
    where = prefix + str(victim)
    assert where.lower().startswith(llm._PIPE_PREFIXES)  # what the old check alone accepted
    opened: list[str] = []

    def spy(path, *args, **kwargs):  # the builtin, recorded: shows whether the refusal came before or after a real open
        opened.append(path)
        return open(path, *args, **kwargs)

    monkeypatch.setattr(llm, "open", spy, raising=False)
    request = b'POST /admin/setpoints HTTP/1.1\r\n\r\n{"hmemKnowledge":false}'
    # round 7: the name check refuses it before anything is opened
    with pytest.raises(OSError, match="'.' / '..' component after its prefix"):
        llm._control_exchange(where, request, timeout=2)
    assert opened == [] and victim.read_bytes() == b"original contents\r\n"
    monkeypatch.setenv("METERLESS_CONTROL_SOCKET", where)  # the setter on a Meterless route (`live`), through the real I/O
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    problem = llm.disable_hmem_injection()
    assert problem and "nothing was opened" in problem and opened == [] and victim.read_bytes() == b"original contents\r\n"
    # round 5's layer behind it: with the name check bypassed, GetFileType still refuses the disk file before a write
    monkeypatch.setattr(llm, "_pipe_name_problem", lambda where: None)
    with pytest.raises(OSError, match="is not a named pipe \\(it opened a disk file\\); nothing was written"):
        llm._control_exchange(where, request, timeout=2)
    assert opened == [where] and victim.read_bytes() == b"original contents\r\n"


REMOTE_TRAVERSALS = [
    "\\\\.\\pipe\\..\\UNC\\remote-host.example\\pipe\\quorum-test-x",
    "//./pipe/../UNC/remote-host.example/pipe/quorum-test-x",
    "\\\\.\\PIPE\\..\\unc\\remote-host.example\\pipe\\quorum-test-x",
    "\\\\.\\pipe\\..\\GLOBALROOT\\Device\\Mup\\remote-host.example\\pipe\\quorum-test-x",
    "\\\\.\\pipe\\quorum-test-x\\..\\..\\UNC\\remote-host.example\\pipe\\quorum-test-x",
    "\\\\?\\pipe\\..\\UNC\\remote-host.example\\pipe\\quorum-test-x",
    "//?/pipe/../UNC/remote-host.example/pipe/quorum-test-x",
    "\\\\.\\pipe\\.. \\UNC\\remote-host.example\\pipe\\quorum-test-x",
    "\\\\.\\pipe\\.\\..\\UNC\\remote-host.example\\pipe\\quorum-test-x",
    "\\\\.\\pipe\\",
]


@pytest.mark.parametrize("where", REMOTE_TRAVERSALS)
def test_pipe_name_that_can_leave_the_local_pipe_namespace_is_never_opened(live, real_control_exchange, monkeypatch, where):
    """Round 7: `\\\\.\\pipe\\..\\UNC\\<host>\\pipe\\x` passed the prefix check and normalises to a named pipe on another
    machine, whose handle also passes GetFileType (faked here as "a pipe"): the setter wrote GET, POST, GET to it and
    reported success, and the open alone starts SMB authentication with that host. `open` must never be called."""
    assert where.lower().startswith(llm._PIPE_PREFIXES)  # what the prefix check alone accepted
    opened = _fake_open(monkeypatch, lambda path: _FakePipe([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"] * 3))
    with pytest.raises(OSError, match="nothing was opened"):
        llm._control_exchange(where, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    monkeypatch.setenv("METERLESS_CONTROL_SOCKET", where)
    monkeypatch.setattr(llm, "_control_http", _REAL_CONTROL_HTTP)
    problem = llm.disable_hmem_injection()
    assert problem and "unreachable" in problem and "nothing was opened" in problem
    assert opened == []


@pytest.mark.skipif(sys.platform != "win32", reason="GetFullPathNameW is Windows-only")
def test_pipe_name_must_stay_under_the_local_pipe_root_after_canonicalisation(real_control_exchange, monkeypatch):
    """The second layer on its own: a name with no dot component whose Win32 canonical form (GetFullPathNameW, string
    only) leaves `\\\\.\\pipe\\` is refused before the open; the real GetFullPathNameW keeps every accepted spelling."""
    for where, full in [("\\\\.\\pipe\\quorum-test-x", "\\\\.\\pipe\\quorum-test-x"), ("//./pipe/quorum-test-x", "\\\\.\\pipe\\quorum-test-x"),
                        ("\\\\?\\pipe\\quorum-test-x", "\\\\?\\pipe\\quorum-test-x"), ("\\\\.\\pipe\\..\\UNC\\h\\pipe\\x", "\\\\.\\UNC\\h\\pipe\\x"),
                        ("\\\\.\\pipe\\..\\GLOBALROOT\\Device\\Mup\\h\\pipe\\x", "\\\\.\\GLOBALROOT\\Device\\Mup\\h\\pipe\\x")]:
        assert llm._full_path_name(where) == full
        assert (llm._pipe_name_problem(where) is None) is full.lower().startswith(llm._LOCAL_PIPE_ROOTS)
    opened = _fake_open(monkeypatch, lambda path: pytest.fail("a name outside the pipe root must not be opened"))
    monkeypatch.setattr(llm, "_full_path_name", lambda where: "\\\\.\\UNC\\remote-host.example\\pipe\\quorum-test-x")
    with pytest.raises(OSError, match=r"resolves to \\\\\.\\UNC\\remote-host\.example\\pipe\\quorum-test-x, outside"):
        llm._control_exchange("\\\\.\\pipe\\quorum-test-x", b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    monkeypatch.setattr(llm, "_full_path_name", lambda where: None)
    with pytest.raises(OSError, match="cannot canonicalise"):
        llm._control_exchange("\\\\.\\pipe\\quorum-test-x", b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=2)
    assert opened == []


@pytest.mark.skipif(sys.platform != "win32", reason="named pipes and GetFileType are Windows-only")
def test_a_real_named_pipe_passes_the_file_type_check(real_control_exchange):
    """The other side of the check above: a pipe this test creates itself (never the daemon's) opens through the real
    `_open_pipe` and GetFileType, so the check cannot fail every live start closed."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR] + [wintypes.DWORD] * 6 + [wintypes.LPVOID]
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    name = rf"\\.\pipe\quorum-test-scratch-{os.getpid()}-{time.monotonic_ns()}"
    server = kernel32.CreateNamedPipeW(name, 3, 0, 1, 4096, 4096, 0, None)  # duplex, byte mode, one instance
    assert server and server != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    try:
        with llm._open_pipe(name) as pipe:
            assert llm._file_type(pipe) == llm.FILE_TYPE_PIPE
    finally:
        kernel32.CloseHandle(server)


class _ReplySocket:
    """A Unix socket that answers one complete response."""

    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, value):
        pass

    def connect(self, where):
        self.where = where

    def sendall(self, data):
        self.sent = data

    def recv(self, n):
        reply, self.reply = self.reply, b""
        return reply


@pytest.mark.parametrize("where", [r"\\.\pipe\quorum-test-x", "//./pipe/quorum-test-x"])
def test_pipe_shaped_override_is_a_unix_socket_off_windows(real_control_exchange, monkeypatch, where):
    """Round 5: off Windows a pipe-shaped override (a .env copied from Windows) was opened as a regular file and the
    request written into it; now it is a Unix socket path, as transport.mjs's socketPath takes it (any host, fake socket)."""
    import socket

    socks: list[_ReplySocket] = []
    monkeypatch.setattr(llm, "sys", SimpleNamespace(platform="linux"))  # llm's own view of the host only
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *a: socks.append(_ReplySocket()) or socks[-1])
    monkeypatch.setattr(llm, "open", lambda *a, **k: pytest.fail("off Windows nothing is opened as a file"), raising=False)
    assert llm._control_exchange(where, b"GET /admin/setpoints HTTP/1.1\r\n\r\n", timeout=1) == _ReplySocket.reply
    assert socks[0].where == where and socks[0].sent == b"GET /admin/setpoints HTTP/1.1\r\n\r\n"


@pytest.mark.parametrize("raw,complete,expected", [
    (b"HTTP/1.1 200 OK\r\nContent-Length: 37\r\n\r\n{\"setpoints\":{\"hmemKnowledge\":false}}", True, (200, {"setpoints": {"hmemKnowledge": False}})),
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n10\r\n{\"hmemKnowledge\"\r\n7\r\n:false}\r\n0\r\n\r\n", True, (200, {"hmemKnowledge": False})),
    (b"HTTP/1.1 400 Bad Request\r\n\r\nnot json", False, (400, llm.NOT_JSON)),  # no length: read until the daemon closes
    (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}\r\nHTTP/1.1 200", True, (200, {})),  # bytes past Content-Length dropped
    (b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", True, (200, None)),  # an empty body
    (b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nnull", True, (200, None)),
    (b"HTTP/1.1 200 OK\r\n\r\n", False, (200, llm.UNFRAMED_EMPTY)),  # round 7: no bytes and no framing, maybe cut off
    (b"HTTP/1.1 200 OK\r\n\r\n\r\n", False, (200, llm.UNFRAMED_EMPTY)),
    (b"HTTP/1.1 200 OK\r\n\r\nnull", False, (200, None)),  # an explicit null, close-delimited
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n", True, (200, None)),  # an empty chunked body
])
def test_control_responses_are_parsed(raw, complete, expected):
    assert llm._http_complete(raw) is complete
    assert llm._parse_http_response(raw) == expected
    with pytest.raises(ValueError):
        llm._parse_http_response(b"")


@pytest.mark.parametrize("raw", [
    b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 37\r\n\r\n{\"setpoints\":{\"hmemKnowledge\":fal",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n",  # no terminating 0-size chunk
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n10\r\n{\"hmem\r\n",  # a chunk shorter than its size line
    b"HTTP/1.1 200 OK\r\nContent-Length: -1\r\n\r\n{}",
])
def test_control_responses_shorter_than_announced_are_refused(raw):
    with pytest.raises(ValueError):
        llm._parse_http_response(raw)


# The suite-wide guard (tests/conftest.py), proved with a mutant ------------------------------------------------------

FORGETFUL_TEST = '''
import pytest

from quorum_reasoning import graph, llm, run

NAMES = %r


def _forgetful_live_run(mp, out):
    """A live run on the Meterless route that stubs neither run.live_guard nor the control plane."""
    mp.setattr(llm, "_loaded", True)  # never the real .env
    for name in NAMES:
        mp.delenv(name, raising=False)
    mp.setenv("METERLESS_TOKEN", "test-token-not-real")

    def abort(*a, **k):
        raise llm.RateLimitAbort("m", 2)

    mp.setattr(graph, "run_local", abort)
    mp.setattr(llm, "current_run_id", None)
    return run.main(["--model", "live", "--quiet", "--out", str(out)])


def test_forgets_the_stub(monkeypatch, tmp_path):
    assert _forgetful_live_run(monkeypatch, tmp_path) == 3


@pytest.fixture(scope="module")
def forgetful_module_fixture(tmp_path_factory):
    """The same run from a module-scoped fixture, which runs before any function-scoped fixture of its test."""
    mp = pytest.MonkeyPatch()
    try:
        yield _forgetful_live_run(mp, tmp_path_factory.mktemp("out"))
    finally:
        mp.undo()


def test_forgets_the_stub_in_a_module_fixture(forgetful_module_fixture):
    assert forgetful_module_fixture == 3
''' % (ENV_NAMES,)


GUARD_LAYER_TESTS = """
from quorum_reasoning import llm

REQUEST = b"GET /admin/status HTTP/1.1\\r\\n\\r\\n"


def test_swallows_the_failure():
    \"\"\"Catches the stub's failure: only the teardown re-check can still fail this test.\"\"\"
    try:
        llm._control_exchange(llm.control_socket_path(), REQUEST)
    except BaseException:
        pass


def test_real_exchange_on_the_derived_name(real_control_exchange, monkeypatch):
    monkeypatch.delenv("METERLESS_CONTROL_SOCKET")
    llm._control_exchange(llm.control_socket_path(), REQUEST)


def test_open_pipe_on_the_derived_name(monkeypatch):
    monkeypatch.delenv("METERLESS_CONTROL_SOCKET")
    llm._open_pipe(llm.control_socket_path())


def test_wait_named_pipe_on_the_derived_name(monkeypatch):
    monkeypatch.delenv("METERLESS_CONTROL_SOCKET")
    llm._wait_named_pipe(llm.control_socket_path(), 50)
"""


# the session guard's layers, outside any test function: at the module's import and in module-scoped fixtures
GUARD_LAYERS_OUTSIDE_TESTS = """
import pytest

from quorum_reasoning import llm

try:  # at import, while pytest collects this module: only the session guard is in place
    llm._control_exchange(llm.control_socket_path(), b"GET /admin/import HTTP/1.1\\r\\n\\r\\n")
except BaseException:
    pass


@pytest.fixture(scope="module")
def swallowed():
    try:
        llm._control_exchange(llm.control_socket_path(), b"GET /admin/module HTTP/1.1\\r\\n\\r\\n")
    except BaseException:
        pass


def _on_the_derived_name(call):
    mp = pytest.MonkeyPatch()
    try:
        mp.delenv("METERLESS_CONTROL_SOCKET")
        call(llm.control_socket_path())
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def opened():
    _on_the_derived_name(llm._open_pipe)


@pytest.fixture(scope="module")
def waited():
    _on_the_derived_name(lambda where: llm._wait_named_pipe(where, 50))


def test_after_a_module_fixture_that_swallowed_the_failure(swallowed):
    pass


def test_module_fixture_opens_the_derived_name(opened):
    pass


def test_module_fixture_waits_on_the_derived_name(waited):
    pass
"""


class _InnerSession:
    """Every test report of one inner pytest session."""

    def __init__(self):
        self.reports: list = []
        self.code = None

    def pytest_runtest_logreport(self, report):
        self.reports.append(report)

    def phase(self, test: str, when: str = "call"):
        found = [r for r in self.reports if r.nodeid.endswith("::" + test) and r.when == when]
        assert len(found) == 1, f"{test} ({when}) did not run in the inner session"
        return found[0]


def _inner_session(root: Path, files: dict[str, str]) -> _InnerSession:
    """`pytest.main` on `root` in this process, never in a child process, so the sentinels the caller installed apply to
    every inner test; sys.modules and sys.path are restored afterwards, as pytester's inline_run does.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the guard's proof runs its inner sessions with an in-process
    `pytest.main`, not with the pytester fixture. Why: review round 4: `pytester.runpytest` follows `--runpytest`, and
    under `--runpytest=subprocess` (settable through PYTEST_ADDOPTS) the mutant ran in a child process where no sentinel
    applied, so it could POST to the live daemon; and the `pytest_plugins = ["pytester"]` it needed in tests/conftest.py
    broke collection from the repository root (a non-top-level conftest may not declare it)."""
    import importlib

    root.mkdir()
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    session = _InnerSession()
    modules, paths, meta = dict(sys.modules), list(sys.path), list(sys.meta_path)
    importlib.invalidate_caches()
    try:
        session.code = pytest.main([str(root), "-q", "-p", "no:cacheprovider", "-c", str(root / "pytest.ini"),
                                    "--rootdir", str(root), "--basetemp", str(root / "basetemp")], plugins=[session])
    finally:
        sys.modules.clear()
        sys.modules.update(modules)
        sys.path[:], sys.meta_path[:] = paths, meta
    return session


def test_suite_guard_fails_a_test_that_forgets_the_stub(tmp_path, monkeypatch, unguarded_control_seams):
    """Coordinator decision 2 (round 3), review round 4 and final review round 2. Inner sessions run in this process
    (`_inner_session`) with a fake profile, so even the derived pipe name is one that does not exist, and a sentinel
    `open` inside llm stands in for the pipe in all of them: the real daemon is never touched.

    Without tests/conftest.py (the mutant) the forgetful test and the forgetful module-scoped fixture each reach the
    derived name. With it, both fail before anything is opened, and each guard layer fails its own test: the teardown
    re-check (a test that swallows the stub's failure), the real-name refusal of `real_control_exchange`, and the
    real-name refusals of `_open_pipe` and `_wait_named_pipe`; outside any test function the session guard does the same
    (the stub in a module-scoped fixture, the refusals of `_open_pipe` and `_wait_named_pipe` there, and the re-check at
    the session's end of what a module's import and a module-scoped fixture swallowed); removing any one of them makes
    this test fail."""
    import socket

    reached: list[str] = []

    def sentinel(path, *a, **k):
        reached.append(str(path))
        raise FileNotFoundError(2, "sentinel: nothing is opened", str(path))

    monkeypatch.setattr(llm, "open", sentinel, raising=False)
    if sys.platform != "win32":  # elsewhere the derived control plane is the packaged Unix socket
        monkeypatch.setattr(socket, "socket", lambda *a, **k: sentinel(llm.CONTROL_SOCKET_POSIX))
    real_profile = os.environ.get("LOCALAPPDATA")
    fake_local = str(tmp_path / "fake-profile" / "AppData" / "Local")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fake-profile"))  # the fake profile first ...
    monkeypatch.setenv("LOCALAPPDATA", fake_local)
    monkeypatch.delenv("METERLESS_CONTROL_SOCKET")  # ... only then the safe override removed
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)  # the inner sessions take no options from the outer one
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setattr(llm, "_loaded", True)
    expected = llm.control_socket_path()  # computing it opens nothing
    if sys.platform == "win32":
        assert expected == rf"\\.\pipe\ai.meterless.runtime-{llm._user_key(fake_local)}-runtime"
        assert not real_profile or llm._user_key(real_profile) != llm._user_key(fake_local), "not this machine's pipe"
    else:
        assert expected == llm.CONTROL_SOCKET_POSIX
    # the unguarded originals, as in a session without the guard (the guarded session's conftest captures these)
    for seam, real in unguarded_control_seams.items():
        assert (real.__module__, real.__qualname__) == (llm.__name__, seam) and not hasattr(real, "__wrapped__"), seam
        monkeypatch.setattr(llm, seam, real)

    mutant = _inner_session(tmp_path / "mutant", {"test_forgetful.py": FORGETFUL_TEST})  # no conftest: the guard removed
    assert mutant.phase("test_forgets_the_stub").failed
    assert mutant.phase("test_forgets_the_stub_in_a_module_fixture").failed
    assert reached == [expected, expected], "without the guard the forgetful test and fixture reach the derived pipe"

    reached.clear()
    conftest = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    guarded = _inner_session(tmp_path / "guarded", {"conftest.py": conftest, "test_forgetful.py": FORGETFUL_TEST,
                                                    "test_guard_layers.py": GUARD_LAYER_TESTS,
                                                    "test_guard_layers_outside_tests.py": GUARD_LAYERS_OUTSIDE_TESTS})
    forgetful = guarded.phase("test_forgets_the_stub")
    assert forgetful.failed and ("a test reached the Meterless control plane unfaked: GET /admin/setpoints HTTP/1.1 on "
                                 + FAKE_PIPE) in forgetful.longreprtext
    outside = "code outside a test function (a test module's import or a session-, module- or class-scoped fixture)"
    in_fixture = guarded.phase("test_forgets_the_stub_in_a_module_fixture", "setup")
    assert in_fixture.failed and (f"{outside} reached the Meterless control plane unfaked: GET /admin/setpoints "
                                  f"HTTP/1.1 on {FAKE_PIPE}") in in_fixture.longreprtext
    for test, seam in (("opens", "_open_pipe"), ("waits_on", "_wait_named_pipe")):
        report = guarded.phase(f"test_module_fixture_{test}_the_derived_name", "setup")
        assert report.failed and f"{outside} reached the daemon's real control pipe or socket through llm.{seam}: {expected}" in report.longreprtext
    assert guarded.phase("test_after_a_module_fixture_that_swallowed_the_failure").passed
    at_the_end = [r for r in guarded.reports if r.when == "teardown" and r.failed and f"{outside} reached" in r.longreprtext]
    assert len(at_the_end) == 1, "the session's end re-checks what code outside a test function swallowed"
    for swallowed_line in ("GET /admin/import HTTP/1.1", "GET /admin/module HTTP/1.1"):
        assert f"{swallowed_line} on {FAKE_PIPE}" in at_the_end[0].longreprtext
    swallowed = guarded.phase("test_swallows_the_failure")
    teardown = guarded.phase("test_swallows_the_failure", "teardown")
    assert swallowed.passed and teardown.failed  # the teardown re-check
    assert "a test reached the Meterless control plane unfaked: GET /admin/status HTTP/1.1 on " + FAKE_PIPE in teardown.longreprtext
    exchange = guarded.phase("test_real_exchange_on_the_derived_name")
    assert exchange.failed and f"a test sent a control-plane request to the daemon's real pipe or socket: {expected}" in exchange.longreprtext
    for seam in ("_open_pipe", "_wait_named_pipe"):
        report = guarded.phase(f"test{seam}_on_the_derived_name")
        assert report.failed and f"through llm.{seam}: {expected}" in report.longreprtext
    assert reached == [], "with the guard nothing is opened"
