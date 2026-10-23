"""Model access. One OpenAI-compatible route (Nemotron via Meterless), read from .env like smoke_test.py.

Dry run: with QUORUM_DRY_RUN=1, or when no key is configured, every task is answered by the deterministic
heuristics in dryrun.py. The graph then runs end to end without spending credits — Studio, tests and the
first demo recording use this mode. Nothing here is a routine check; the graph runs only when started.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import config, dryrun
from .untrusted import DATA_NOTE, parse_json_object

_PROMPTS = Path(__file__).resolve().parent / "prompts"
_loaded = False


def _env() -> None:
    global _loaded
    if not _loaded:
        # the repo-level .env (../../.env) first, then a local one
        for p in (Path(__file__).resolve().parents[2] / ".env", Path(".env")):
            if p.is_file():
                load_dotenv(p, override=False)
        _loaded = True


APP_NAME = "quorum-reasoning"  # the meterless-app header: how the request shows up in Nightshift's receipts
TIMEOUT_S = 180  # a model load on the hotspot can take minutes (Setup Guide › Power)

# Ledger of live calls in the current run: what was asked and which model actually answered. The hotspot may
# substitute a model (its routing modes rank lanes, they do not pin them), so the answering model is the
# evidence, not the route in .env. Reset by `plan`, summarised into the snapshot's provenance by `publish`.
calls: list[dict[str, Any]] = []


def reset_calls() -> None:
    calls.clear()


def served_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for c in calls:
        out[c["served"]] = out.get(c["served"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _verbose() -> bool:
    return os.getenv("QUORUM_VERBOSE") == "1"


def _route(which: str = "default") -> tuple[str, str, str]:
    """(base URL, Runtime token, model route) for a task lane.

    One hotspot (Nightshift) for every lane; what differs per lane is the model route. `default` reads
    NEMOTRON_MODEL (the fast worker lane); `fact_checker` reads NEMOTRON_MODEL_FACT_CHECKER and falls back
    to the default route when it is not set. Routes are Nightshift ids (`meterless/<class>.<disposition>` or
    a pinned model id from GET /v1/models); the NVIDIA key itself lives in Nightshift's Providers tab, never here.
    """
    _env()
    base = os.getenv("MODEL_BASE_URL") or os.getenv("METERLESS_BASE_URL") or ""
    key = os.getenv("MODEL_API_KEY") or os.getenv("METERLESS_RUNTIME_TOKEN") or ""
    model = os.getenv("NEMOTRON_MODEL") or os.getenv("METERLESS_MODEL") or "meterless/auto"
    if which == "fact_checker":
        model = os.getenv("NEMOTRON_MODEL_FACT_CHECKER") or model
    return base.strip(), key.strip(), model.strip()


def _client():
    from openai import OpenAI  # imported lazily: not needed in dry run

    base, key, _ = _route()
    # meterless-app and meterless-scope are the Runtime contract's required headers (Setup Guide § 4.5);
    # NVIDIA's own endpoint ignores them, so the same client works on a direct route.
    return OpenAI(
        base_url=base,
        api_key=key,
        timeout=TIMEOUT_S,
        max_retries=2,
        default_headers={"meterless-app": APP_NAME, "meterless-scope": "user"},
    )


def list_models() -> list[str]:
    """GET /v1/models on the configured hotspot: the routes a run may pin. Raises when the route is not configured."""
    base, key, _ = _route()
    if not (base and key):
        raise RuntimeError("no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env")
    return sorted(m.id for m in _client().models.list())


def probe(which: str = "default") -> dict[str, Any]:
    """One small real task (stance) on a lane; returns the raw reply, its token counts and the parsed JSON.

    What to read in it: a reply of a few dozen completion tokens that is pure JSON means the thinking trace is
    off; hundreds of tokens of prose before the JSON means the model still thinks aloud on this route.
    """
    base, key, model = _route(which)
    if not (base and key):
        raise RuntimeError("no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env")
    payload = {
        "claim": "The Senate passed the bill 68-30",
        "passage": "The Senate passed the bill 68-30 and the House passed the bill 311-112.",
        "source": "Example Wire",
        "source_kind": "agency",
        "doc_type": None,
        "role": "researcher",
    }
    started = time.perf_counter()
    completion = _client().chat.completions.create(
        model=model,
        temperature=float(config.get("models", "temperature", 0.1)),
        messages=[
            {"role": "system", "content": _prompt("stance")},
            {"role": "user", "content": DATA_NOTE + "\n" + json.dumps(payload, ensure_ascii=False)},
        ],
        **_request_extras(),
    )
    ms = int((time.perf_counter() - started) * 1000)
    text = completion.choices[0].message.content or ""
    usage = getattr(completion, "usage", None)
    return {
        "lane": which,
        "route": model,
        "answered_by": getattr(completion, "model", "") or "",
        "ms": ms,
        "tokens_in": int(getattr(usage, "prompt_tokens", 0) or 0),
        "tokens_out": int(getattr(usage, "completion_tokens", 0) or 0),
        "reply_chars": len(text),
        "reply_head": text[:400],
        "parsed": parse_json_object(text),
    }


def test_connection(which: str = "default") -> dict[str, str]:
    """One small chat completion on a lane. Returns the route asked for and the model that answered."""
    base, key, model = _route(which)
    if not (base and key):
        raise RuntimeError("no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env")
    completion = _client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "system", "content": _prompt("connection_test")}, {"role": "user", "content": "Reply with the single word: ready"}],
        **_request_extras(),
    )
    return {"lane": which, "route": model, "answered_by": getattr(completion, "model", "") or "", "reply": (completion.choices[0].message.content or "").strip()[:40]}


def is_dry_run(state_flag: bool) -> bool:
    if state_flag or os.getenv("QUORUM_DRY_RUN") == "1":
        return True
    base, key, _ = _route()
    return not (base and key)


def model_name(which: str = "default") -> str:
    return _route(which)[2]


_last_call_at = 0.0


def _prompt(task: str) -> str:
    p = _PROMPTS / f"{task}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else f"Task: {task}. Answer with JSON only."


def _request_extras() -> dict[str, Any]:
    """Body fields beyond model/messages: the reply ceiling and NVIDIA's thinking switch.

    `chat_template_kwargs.enable_thinking` is the documented control for hosted Nemotron 3.5 / Nemotron 3 Nano
    endpoints (and vLLM); the OpenAI SDK sends `extra_body` entries as top-level JSON fields, which an
    OpenAI-compatible proxy forwards. A system-prompt "/no_think" is Qwen3's switch and did nothing here.
    """
    extras: dict[str, Any] = {}
    max_tokens = int(config.get("models", "max_tokens", 0) or 0)
    if max_tokens > 0:
        extras["max_tokens"] = max_tokens
    thinking_on = str(config.get("models", "reasoning", "off")).lower() == "on"
    body: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking_on}}
    budget = int(config.get("models", "reasoning_budget", 0) or 0)
    if thinking_on and budget > 0:
        body["reasoning_budget"] = budget  # NVIDIA's name for the thinking-token cap (build.nvidia.com sample code)
    extras["extra_body"] = body
    return extras


def _throttle() -> None:
    """Keeps at least models.min_interval_ms between two live calls (the provider's per-minute cap)."""
    global _last_call_at
    gap = int(config.get("models", "min_interval_ms", 0) or 0) / 1000.0
    if gap > 0:
        wait = _last_call_at + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    _last_call_at = time.monotonic()


def json_task(task: str, payload: dict[str, Any], *, dry_run: bool, which: str = "default") -> dict[str, Any]:
    """Runs one named task. `payload` is what the model sees; the reply is parsed JSON.

    Every task has a dry-run twin in dryrun.py with the same input and output shape. The payload's text
    fields are quoted outside material: the user message labels them as data (untrusted.DATA_NOTE) and the
    prompts repeat the rule. The reply is parsed as the last balanced JSON object, so hostile text that
    baits the model into echoing JSON-shaped material before its answer does not break or hijack the parse.
    """
    if is_dry_run(dry_run):
        return getattr(dryrun, task)(payload)

    _, _, model = _route(which)
    temperature = float(config.get("models", "temperature", 0.1))
    _throttle()
    started = time.perf_counter()
    try:
        completion = _client().chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": _prompt(task)},
                {"role": "user", "content": DATA_NOTE + "\n" + json.dumps(payload, ensure_ascii=False)},
            ],
            **_request_extras(),
        )
    except Exception as exc:
        ms = int((time.perf_counter() - started) * 1000)
        calls.append({"task": task, "lane": which, "route": model, "served": "error", "ms": ms, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
        if _verbose():
            print(f"  · {task:<15} {which:<13} {model:<42} FAILED {ms:>6} ms  {type(exc).__name__}", file=sys.stderr, flush=True)
        raise
    ms = int((time.perf_counter() - started) * 1000)
    served = getattr(completion, "model", None) or model
    usage = getattr(completion, "usage", None)
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
    calls.append({"task": task, "lane": which, "route": model, "served": served, "ms": ms, "tokens_in": tokens_in, "tokens_out": tokens_out})
    if _verbose():
        flag = "" if served == model or model.startswith("meterless/") else "  (substituted)"
        print(f"  · {task:<15} {which:<13} {served:<42} {ms:>6} ms  {tokens_in:>5}>{tokens_out:<5}{flag}", file=sys.stderr, flush=True)
    text = completion.choices[0].message.content or "{}"
    obj = parse_json_object(text)
    if obj is None:
        raise ValueError(f"{task}: model did not return JSON")
    return obj
