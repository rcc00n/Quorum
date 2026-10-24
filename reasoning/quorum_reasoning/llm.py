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
    """Answering model -> calls. Every ledger row has exactly one `served` value ("error" for a call that got no
    reply), so the counts sum to `len(calls)`; a reply that answered but carried no JSON stays under its model
    and is counted separately by `error_count`."""
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
    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): the SDK retries nothing (max_retries=0); the one
    # retry this module allows is explicit, in `_create`, on 429/5xx/timeouts only, honouring Retry-After.
    # Why: max_retries=2 let the SDK make three HTTP attempts per call behind the ledger's back, which broke
    # the two-attempt rule (AGENTS.md § 3) and hid the 429s of the first live fixture run (Vadim, NVIDIA-FIRST-01).
    return OpenAI(
        base_url=base,
        api_key=key,
        timeout=TIMEOUT_S,
        max_retries=0,
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
    served, receipt_id = _served_and_receipt(completion, model)
    return {
        "lane": which,
        "route": model,
        "answered_by": served,
        "receipt_id": receipt_id,
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


def route_configured() -> bool:
    """True when MODEL_BASE_URL and MODEL_API_KEY (or the METERLESS_* names) are both set."""
    base, key, _ = _route()
    return bool(base and key)


def is_dry_run(state_flag: bool) -> bool:
    if state_flag or os.getenv("QUORUM_DRY_RUN") == "1":
        return True
    return not route_configured()


def error_count() -> int:
    """Ledger rows that did not end in a parsed answer: transport failures and replies without JSON alike."""
    return sum(1 for c in calls if c.get("error"))


def model_name(which: str = "default") -> str:
    """The route a lane would use, or "stand-ins" when the run is dry (QUORUM_DRY_RUN=1 or no route).

    Trace rows and the envelope carry this: a dry run must never show a real model name as if it had answered
    (the committed samples did, from the local .env, until 2026-10-24).
    """
    if is_dry_run(False):
        return "stand-ins"
    return _route(which)[2]


def _served_and_receipt(completion: Any, route: str) -> tuple[str, str]:
    """The model that answered, and Nightshift's receipt id when the response carries one.

    Nightshift's chat response body carries a `meterless` object (requested/provider/routed model,
    receipt_id, signed receipt envelope). The OpenAI SDK keeps unknown response fields in `model_extra`.
    `routed_model` beats a `meterless/*` value in the standard `model` field as evidence of what answered;
    the receipt id goes into the call ledger so the demo can point at Console › Proof per request.
    """
    served = str(getattr(completion, "model", None) or route)
    met = (getattr(completion, "model_extra", None) or {}).get("meterless") or {}
    if not isinstance(met, dict):
        return served, ""
    routed = str(met.get("routed_model") or met.get("provider_model") or "")
    if routed and (served.startswith("meterless/") or not served):
        served = routed
    return served, str(met.get("receipt_id") or "")


_last_call_at = 0.0


def _prompt(task: str) -> str:
    p = _PROMPTS / f"{task}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else f"Task: {task}. Answer with JSON only."


def _request_extras() -> dict[str, Any]:
    """Body fields beyond model/messages: the reply ceiling and NVIDIA's thinking switch.

    `chat_template_kwargs.enable_thinking` is the documented control for hosted Nemotron 3.5 / Nemotron 3 Nano
    endpoints (and vLLM); the OpenAI SDK sends `extra_body` entries as top-level JSON fields, which an
    OpenAI-compatible proxy forwards. A system-prompt "/no_think" is Qwen3's switch and did nothing here.

    DECISION(2026-10-23, Yelysei Shkirpan/Claude Code): with thinking off, `force_nonempty_content: true`
    rides along in chat_template_kwargs (NVIDIA's Lightning cookbook and NVIDIA's own client configs send it
    so the answer lands in `content`, never only in the reasoning field); with thinking on, `max_tokens` is
    lifted to reasoning_budget + 1000 when it is lower. Why: the trace counts against max_tokens and is
    forcibly cut only at budget + 500 (Lightning usage cookbook), so a lower ceiling returns
    `finish_reason: length` with no answer at all.
    """
    extras: dict[str, Any] = {}
    max_tokens = int(config.get("models", "max_tokens", 0) or 0)
    thinking_on = str(config.get("models", "reasoning", "off")).lower() == "on"
    budget = int(config.get("models", "reasoning_budget", 0) or 0)
    if thinking_on and budget > 0 and max_tokens > 0:
        max_tokens = max(max_tokens, budget + 1000)
    if max_tokens > 0:
        extras["max_tokens"] = max_tokens
    kwargs: dict[str, Any] = {"enable_thinking": thinking_on}
    if not thinking_on:
        kwargs["force_nonempty_content"] = True
    body: dict[str, Any] = {"chat_template_kwargs": kwargs}
    if thinking_on and budget > 0:
        body["reasoning_budget"] = budget  # NVIDIA's name for the thinking-token cap (build.nvidia.com sample code)
    extras["extra_body"] = body
    return extras


def min_interval_ms() -> int:
    """Pause between two live calls: QUORUM_MIN_INTERVAL_MS when set (Nightshift runs set it to 0), else
    config/reasoning.toml › models.min_interval_ms (the direct route's trial cap; see the decision there)."""
    raw = os.getenv("QUORUM_MIN_INTERVAL_MS", "").strip()
    if raw:
        return max(0, int(raw))
    return int(config.get("models", "min_interval_ms", 0) or 0)


def _throttle() -> None:
    """Keeps at least min_interval_ms() between two live calls (the provider's per-minute cap)."""
    global _last_call_at
    gap = min_interval_ms() / 1000.0
    if gap > 0:
        wait = _last_call_at + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    _last_call_at = time.monotonic()


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DEFAULT_WAIT_S = 5.0
RETRY_MAX_WAIT_S = 60.0


def _retry_wait(exc: Exception) -> float | None:
    """Seconds to wait before the single retry, or None when the failure is not retryable (4xx other than 429,
    malformed replies, anything that is not a transport or server-side failure)."""
    from openai import APIConnectionError, APIStatusError, APITimeoutError  # imported lazily: not needed in dry run

    if isinstance(exc, APITimeoutError):
        return RETRY_DEFAULT_WAIT_S
    if isinstance(exc, APIStatusError):
        if exc.status_code not in RETRY_STATUSES:
            return None
        wait = RETRY_DEFAULT_WAIT_S
        header = exc.response.headers.get("retry-after") if getattr(exc, "response", None) is not None else None
        if header:
            try:
                wait = float(header)
            except ValueError:
                from datetime import datetime, timezone
                from email.utils import parsedate_to_datetime

                try:
                    wait = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError):
                    wait = RETRY_DEFAULT_WAIT_S
        return min(max(wait, 1.0), RETRY_MAX_WAIT_S)
    if isinstance(exc, APIConnectionError):
        return RETRY_DEFAULT_WAIT_S  # a dropped socket counts like a timeout
    return None


def _create(model: str, messages: list[dict[str, str]], temperature: float, entry: dict[str, Any]) -> tuple[Any, int]:
    """One chat completion with at most one explicit retry. Returns (completion, HTTP status).

    The retry fires only on 429 / 5xx / timeouts / dropped connections, after Retry-After when the server
    sends it (floored at 1 s, capped at 60 s), and is recorded in the ledger row (`attempts`, `retried_after`).
    Two attempts in total: the external-operation rule of AGENTS.md § 3.
    """
    attempt = 0
    while True:
        attempt += 1
        entry["attempts"] = attempt
        _throttle()
        try:
            raw = _client().chat.completions.with_raw_response.create(model=model, temperature=temperature, messages=messages, **_request_extras())
            return raw.parse(), int(raw.status_code)
        except Exception as exc:  # noqa: BLE001 — classified by _retry_wait
            wait = _retry_wait(exc) if attempt == 1 else None
            if wait is None:
                raise
            entry["retried_after"] = f"{type(exc).__name__}: HTTP {getattr(exc, 'status_code', '-')}, waited {wait:.0f} s"
            if _verbose():
                print(f"  · {entry['task']:<15} {entry['lane']:<13} {model:<42} {type(exc).__name__}; one retry in {wait:.0f} s", file=sys.stderr, flush=True)
            time.sleep(wait)


def json_task(task: str, payload: dict[str, Any], *, dry_run: bool, which: str = "default") -> dict[str, Any]:
    """Runs one named task. `payload` is what the model sees; the reply is parsed JSON.

    Every task has a dry-run twin in dryrun.py with the same input and output shape. The payload's text
    fields are quoted outside material: the user message labels them as data (untrusted.DATA_NOTE) and the
    prompts repeat the rule. The reply is parsed as the last balanced JSON object, so hostile text that
    baits the model into echoing JSON-shaped material before its answer does not break or hijack the parse.

    Every live call leaves exactly one ledger row (`calls`), written after parsing so a reply without JSON
    is counted as an error (`error`), with the HTTP status, `finish_reason` and token counts of the reply.
    The ledger is private (run.py writes it next to the snapshot in the output directory, never into it).
    """
    if is_dry_run(dry_run):
        return getattr(dryrun, task)(payload)

    _, _, model = _route(which)
    temperature = float(config.get("models", "temperature", 0.1))
    messages = [
        {"role": "system", "content": _prompt(task)},
        {"role": "user", "content": DATA_NOTE + "\n" + json.dumps(payload, ensure_ascii=False)},
    ]
    entry: dict[str, Any] = {"task": task, "lane": which, "route": model, "served": "error", "ms": 0, "attempts": 0}
    started = time.perf_counter()
    try:
        completion, status = _create(model, messages, temperature, entry)
    except Exception as exc:
        entry["ms"] = int((time.perf_counter() - started) * 1000)
        entry["http_status"] = getattr(exc, "status_code", None)
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        calls.append(entry)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {model:<42} FAILED {entry['ms']:>6} ms  {type(exc).__name__}", file=sys.stderr, flush=True)
        raise
    entry["ms"] = int((time.perf_counter() - started) * 1000)
    served, receipt_id = _served_and_receipt(completion, model)
    usage = getattr(completion, "usage", None)
    choice = completion.choices[0] if getattr(completion, "choices", None) else None
    entry.update(
        served=served,
        http_status=status,
        finish_reason=getattr(choice, "finish_reason", None),
        tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
        tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
    )
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None) if details is not None else None
    if reasoning_tokens is not None:
        entry["reasoning_tokens"] = int(reasoning_tokens or 0)
    if receipt_id:
        entry["receipt_id"] = receipt_id
    text = (choice.message.content if choice is not None and choice.message else None) or ""
    obj = parse_json_object(text)
    if obj is None:
        why = f" (finish_reason {entry['finish_reason']})" if entry.get("finish_reason") not in (None, "stop") else ""
        entry["error"] = "reply carried no JSON object" + why
    calls.append(entry)
    if _verbose():
        flag = "" if served == model or model.startswith("meterless/") else "  (substituted)"
        if entry.get("error"):
            flag += "  NO JSON"
        print(f"  · {task:<15} {which:<13} {served:<42} {entry['ms']:>6} ms  {entry['tokens_in']:>5}>{entry['tokens_out']:<5}{flag}", file=sys.stderr, flush=True)
    if obj is None:
        raise ValueError(f"{task}: model did not return JSON ({entry['error']})")
    return obj
