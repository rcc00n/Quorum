"""The Meterless route (2026-10-25): env aliases and the 8088 default, the thinking switch in the body on both routes,
the replay-key partition, the exact-lane check on pinned lanes, the H-MEM disclosure and `--test-connection` output.

No network and no credits: the client is a fake returning SimpleNamespace completions shaped like the SDK's.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from quorum_reasoning import llm, run

LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
ENV_NAMES = ("MODEL_BASE_URL", "MODEL_API_KEY", "METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN", "METERLESS_TOKEN",
             "NEMOTRON_MODEL", "NEMOTRON_MODEL_FACT_CHECKER", "NEMOTRON_MODEL_REVIEWER", "METERLESS_MODEL", "QUORUM_DRY_RUN")


@pytest.fixture
def env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "_loaded", True)  # never read the real .env
    return monkeypatch


def _met(requested: str, provider: str | None, routed: str | None, hmem: dict | None = None, from_cache: bool = False) -> dict:
    met = {"receipt_id": "rcpt_test_1", "requested_model": requested, "from_cache": from_cache,
           "receipt": {"hmem": hmem}}
    if provider is not None:
        met["provider_model"] = provider
    if routed is not None:
        met["routed_model"] = routed
    return met


def _completion(model: str, met: dict | None, content: str = '{"stance": "neutral", "reason": "r"}'):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None)
    choice = SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
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

@pytest.fixture
def live(env, monkeypatch):
    env.setenv("METERLESS_TOKEN", "test-token-not-real")
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
    client = live(_completion(ULTRA, _met(ULTRA, ULTRA, ULTRA, hmem={"injected": 2, "strategy": "comprehensive"})))
    out = llm.json_task("stance", {"claim": "c"}, dry_run=False, which="fact_checker")
    assert out["stance"] == "neutral"
    row = llm.calls[-1]
    assert row["served"] == ULTRA and row["receipt_id"] == "rcpt_test_1"
    assert row["receipt_hmem_injected"] == 2 and row["receipt_from_cache"] is False
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


# 5. --test-connection ----------------------------------------------------------------------------------------------

def test_test_connection_prints_provider_model_and_receipt_per_lane(live, monkeypatch, capsys):
    completions = {LIGHTNING: _completion(LIGHTNING, _met(LIGHTNING, LIGHTNING, LIGHTNING, hmem={"injected": 0}), "ready"),
                   ULTRA: _completion(LIGHTNING, _met(ULTRA, ULTRA, LIGHTNING), "ready")}

    class _PerModel(_Client):
        def _create(self, **kwargs):
            self.kwargs.append(kwargs)
            return completions[kwargs["model"]]

    client = _PerModel(None)
    monkeypatch.setattr(llm, "_client", lambda: client)
    assert run.main(["--test-connection"]) == 0
    out = capsys.readouterr().out
    assert f"provider_model {LIGHTNING}" in out and "receipt_id rcpt_test_1" in out and "lane held" in out
    assert f"SUBSTITUTED by {LIGHTNING}" in out  # the fact-checker lane answered from Lightning
    assert all(k["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False for k in client.kwargs)
