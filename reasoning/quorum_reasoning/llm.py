"""Model access. One OpenAI-compatible route (Nemotron via Meterless), read from .env like smoke_test.py.

Dry run: with QUORUM_DRY_RUN=1, or when no key is configured, every task is answered by the deterministic
heuristics in dryrun.py. The graph then runs end to end without spending credits — Studio, tests and the
first demo recording use this mode. Nothing here is a routine check; the graph runs only when started.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections import deque
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


METERLESS_DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"  # the Windows runtime's loopback port (decision in `_route`)
DIRECT_ROUTE_HOST_SUFFIX = "nvidia.com"  # integrate.api.nvidia.com: the direct route; any other base URL is the Meterless runtime
APP_NAME = "quorum-reasoning"  # the meterless-app header: how the request shows up in Nightshift's receipts
TIMEOUT_S = 180  # a model load on the hotspot can take minutes (Setup Guide › Power)

# Ledger of live calls in the current run: what was asked and which model actually answered. The hotspot may
# substitute a model (its routing modes rank lanes, they do not pin them), so the answering model is the
# evidence, not the route in .env. Reset by `plan`, summarised into the snapshot's provenance by `publish`.
calls: list[dict[str, Any]] = []

# When set (run.py, live runs), every ledger row is also appended at once to this JSON-lines file together with the
# full request payload the model saw (task, lane, payload), so a run that dies mid-way leaves a complete, private
# request/receipt journal; `load_journal` restores the ledger of a resumed run from it.
journal_path: Path | None = None
current_run_id: str | None = None  # set by run.py; stamped on every ledger row and journal line
journal_loaded_for: str | None = None  # set by run.py after load_journal(): the run id whose ledger/replay the loaded rows serve

# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a resumed run replays answers from its own journal: every
# served call journals its raw reply (`reply`) and a `request_key` (sha256 over task, lane, route, the rendered
# prompt, the sampling parameters and the payload), `load_journal` queues the replies per key, and `json_task`
# answers a request with the next queued reply before any pacing or network. Why: the checkpoint is per node, so
# `--resume` re-ran a half-finished node and repeated every call it had already paid for (Vadim,
# CANONICAL-DURABLE-01). The reply text lives only in the private journal (git-ignored, never in the snapshot or the
# ledger). A queue, not a single value: identical requests legitimately repeat within a run (~20 per run) and each
# repeat consumes its own journalled answer in order. A replay adds no ledger row: the restored journal row already
# counts that call, so the provenance counts stay one row per paid call. The queues are keyed across the whole run, not
# per node, so an identical later request may be answered from an earlier node's queued reply; the answer is the same
# request's answer and the counts stay exact, so this is accepted.
replay: dict[str, deque[str]] = {}


def reset_calls() -> None:
    calls.clear()
    replay.clear()


def _journal(entry: dict[str, Any], payload: dict[str, Any], reply: str | None = None) -> None:
    if journal_path is None:
        return
    line: dict[str, Any] = {**entry, "payload": payload}
    if reply is not None:
        line["reply"] = reply
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a journal whose last byte is not a newline (the process
        # died mid-write) gets one before the next row. Why: otherwise the new row is glued to the truncated tail and
        # `load_journal` skips both, losing a paid call and its reply.
        needs_newline = False
        if journal_path.is_file() and journal_path.stat().st_size > 0:
            with journal_path.open("rb") as tail:
                tail.seek(-1, os.SEEK_END)
                needs_newline = tail.read(1) != b"\n"
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if needs_newline else "") + json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as exc:  # the journal must never break a run
        print(f"journal write failed: {exc}", file=sys.stderr)


def load_journal(path: Path) -> int:
    """Restores the ledger from a journal (payloads and reply texts dropped). Returns the number of rows loaded.
    Used on --resume so the snapshot's provenance counts cover the whole run, not only the resumed part. Rows of
    served calls that carry `reply` and `request_key` also fill the replay queues (decision at `replay`); journals
    written before 2026-10-24 have neither and replay nothing."""
    replay.clear()
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print("journal: one truncated line skipped (the process died while writing it)", file=sys.stderr)
            continue
        row.pop("payload", None)
        reply = row.pop("reply", None)
        key = row.get("request_key")
        if isinstance(reply, str) and isinstance(key, str) and not row.get("error"):
            replay.setdefault(key, deque()).append(reply)
        calls.append(row)
        n += 1
    return n


def served_counts() -> dict[str, int]:
    """Answering model -> calls. Every ledger row has exactly one `served` value ("error" for a call that got no
    usable reply: transport failure or a reply without JSON), so the counts sum to `len(calls)` and the "error"
    count equals `error_count()`; `answered_model` on a no-JSON row keeps the model that did answer."""
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
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): MODEL_BASE_URL / MODEL_API_KEY keep precedence; the Meterless
    # pair is read when they are blank: the token from METERLESS_RUNTIME_TOKEN or its alias METERLESS_TOKEN, the URL from
    # METERLESS_BASE_URL or, when only a Meterless token is set, METERLESS_DEFAULT_BASE_URL (127.0.0.1:8088). Why: the
    # owner's machine keeps the Runtime token under METERLESS_TOKEN with METERLESS_BASE_URL blank, and the runtime
    # listens on 8088, not 8080 (verified by hand 2026-10-25, GET /v1/models listed both Nemotron ids).
    base = os.getenv("MODEL_BASE_URL") or os.getenv("METERLESS_BASE_URL") or ""
    model_key = os.getenv("MODEL_API_KEY") or ""
    meterless_key = os.getenv("METERLESS_RUNTIME_TOKEN") or os.getenv("METERLESS_TOKEN") or ""
    key = model_key or meterless_key
    if not base.strip() and not model_key.strip() and meterless_key.strip():
        base = METERLESS_DEFAULT_BASE_URL
    model = os.getenv("NEMOTRON_MODEL") or os.getenv("METERLESS_MODEL") or "meterless/auto"
    if which == "fact_checker":
        model = os.getenv("NEMOTRON_MODEL_FACT_CHECKER") or model
    elif which == "reviewer":
        # the third blind reviewer: its own route when set, else the fact-checker's (a different model than the
        # verifier's lane when available — DECISIONS.md › Principles for handling facts, 2026-10-24)
        model = os.getenv("NEMOTRON_MODEL_REVIEWER") or os.getenv("NEMOTRON_MODEL_FACT_CHECKER") or model
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


def test_connection(which: str = "default") -> dict[str, Any]:
    """One small chat completion on a lane. Returns the route asked for and the model that answered; on the Meterless
    route also `provider_model`, `routed_model`, `receipt_id`, `hmem_injected` and `substituted` (None when the lane held)."""
    base, key, model = _route(which)
    if not (base and key):
        raise RuntimeError("no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env")
    completion = _client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "system", "content": _prompt("connection_test")}, {"role": "user", "content": "Reply with the single word: ready"}],
        **_request_extras(),
    )
    out: dict[str, Any] = {"lane": which, "route": model, "answered_by": getattr(completion, "model", "") or "", "reply": (completion.choices[0].message.content or "").strip()[:40]}
    met = _meterless(completion)
    if met:
        out.update(
            provider_model=str(met.get("provider_model") or ""),
            routed_model=str(met.get("routed_model") or ""),
            receipt_id=str(met.get("receipt_id") or ""),
            hmem_injected=_hmem_injected(met),
            substituted=substituted_lane(model, met),
        )
    return out


def on_meterless() -> bool:
    """True when the configured base URL is not NVIDIA's own endpoint, i.e. the request goes through the Meterless
    runtime (Nightshift). Decides the replay-key partition; the lane check reads the response itself."""
    from urllib.parse import urlparse

    base, _, _ = _route()
    host = (urlparse(base).hostname or "").lower()
    return bool(host) and not (host == DIRECT_ROUTE_HOST_SUFFIX or host.endswith("." + DIRECT_ROUTE_HOST_SUFFIX))


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


def _meterless(completion: Any) -> dict[str, Any]:
    """The response's `meterless` object (empty on the direct route or when the field is not a dict)."""
    met = (getattr(completion, "model_extra", None) or {}).get("meterless") or {}
    return met if isinstance(met, dict) else {}


def _hmem_injected(met: dict[str, Any]) -> int | None:
    """How many H-MEM records the runtime injected into the prompt, from the receipt (`receipt.hmem.injected`, or the
    signed envelope's copy); None when the response carries no receipt, 0 when the receipt says nothing was injected.

    Nightshift 1.2.3 (engine/js/engine/orchestrator.js, runChat): before the phase loop it prepends a system message of
    up to `hmemTopK` "prior vetted answers" retrieved by scope (`meterless-scope`) and app (`meterless-app`); the sync
    chat path exposes no per-request switch (`noMemory` is set only by the jobs plane). The count is disclosed per row."""
    if not met:
        return None
    receipt = met.get("receipt")
    if not isinstance(receipt, dict):
        env = met.get("receipt_envelope")
        body = env.get("body") if isinstance(env, dict) else None
        receipt = body.get("receipt") if isinstance(body, dict) else None
    hmem = (receipt or {}).get("hmem") if isinstance(receipt, dict) else None
    if hmem is None:
        hmem = met.get("hmem")
    if isinstance(hmem, dict):
        try:
            return int(hmem.get("injected") or hmem.get("count") or 0)
        except (TypeError, ValueError):
            return 0
    return 0 if isinstance(receipt, dict) else None


def substituted_lane(requested: str, met: dict[str, Any]) -> str | None:
    """The model the runtime answered with instead of an explicitly pinned one, or None when the lane held.

    Only explicit model ids are checked (`meterless/*` dispositions are ranked, not pinned): every present value of
    `provider_model` (the pin the runtime accepted) and `routed_model` (the model that answered) must equal the id
    asked for. Mentor's contract (2026-10-25): exact id in `model`, `provider_model` must equal it."""
    if not met or not requested or requested.startswith("meterless/"):
        return None
    for field in ("provider_model", "routed_model"):
        value = str(met.get(field) or "")
        if value and value != requested:
            return value
    return None


class RouteSubstituted(ValueError):
    """The runtime answered a pinned lane with another model; the node skips the passage like any failed call."""


def substitution_count() -> int:
    """Ledger rows whose pinned lane was answered by another model (decision in `json_task`)."""
    return sum(1 for c in calls if c.get("route_substituted"))


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


def min_interval_ms(which: str = "default") -> int:
    """Pause before a live call on a lane, resolved in this order: the lane's own env (`QUORUM_MIN_INTERVAL_MS_<LANE>`);
    0 when the shared env `QUORUM_MIN_INTERVAL_MS` is set to 0; the lane's `models.min_interval_ms_<lane>` in
    config/reasoning.toml; the shared env; `models.min_interval_ms`. Nightshift runs set only the shared env to 0,
    which turns every lane off unless that lane's own env says otherwise.

    DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): the fact-checker and reviewer lanes pace themselves
    separately, and the pause is measured per model route, not per process. Why: on the first genuine run
    (edition 2026-10-24, direct route) the Ultra-550B lane refused most often — the fact-checker fires up
    to eight Ultra calls per claim back to back — and Lightning refused too (54 HTTP 429s in that run's journal,
    corrected 2026-10-24: an earlier version of this note said Lightning never refused); one shared 1600 ms pause
    cannot respect two different per-minute caps.

    This is the lane's base interval; the interval actually kept between calls adapts to 429s
    (`_effective_interval_ms`).
    """
    for name in ((f"QUORUM_MIN_INTERVAL_MS_{which.upper()}",) if which != "default" else ()):
        raw = os.getenv(name, "").strip()
        if raw:
            return max(0, int(raw))
    shared_raw = os.getenv("QUORUM_MIN_INTERVAL_MS", "").strip()
    # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): an explicit shared 0 wins over the lanes' TOML values. Why:
    # the documented Nightshift setup sets only QUORUM_MIN_INTERVAL_MS=0 (the hotspot paces upstream), and the 4000 ms
    # TOML value of the fact-checker lane kept pacing it and gave it the direct route's pause and breaker.
    if shared_raw and int(shared_raw) <= 0:
        return 0
    if which != "default":
        lane_value = config.get("models", f"min_interval_ms_{which}", None)
        if lane_value is not None:
            return max(0, int(lane_value))
    raw = os.getenv("QUORUM_MIN_INTERVAL_MS", "").strip()
    if raw:
        return max(0, int(raw))
    return int(config.get("models", "min_interval_ms", 0) or 0)


_last_call_by_route: dict[str, float] = {}

# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): the interval between calls adapts per model route: an HTTP 429
# doubles the route's interval (capped at LANE_INTERVAL_CAP_MS) for every later call on it, and each run of
# LANE_STEP_DOWN_AFTER consecutive successful calls halves it once, never below the lane's configured base. Lanes
# paced at 0 (Nightshift) and dry runs are not adapted. Why: the NVIDIA direct route answers 429 with no Retry-After;
# the old handling (one retry, then straight back to the fixed cadence) kept the key pressed against the limit, and
# after ~30-35 min the provider switched to a stricter state that refused even ~8 requests/min for minutes. 15 clean
# calls per step down, so a raised lane recovers within minutes once the provider accepts calls again.
# (superseded 2026-10-24, next entry: the 10 s cap and repeated doubling are gone)
# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a 429 on a paced route sets its interval to twice the lane's
# base (once: LANE_INTERVAL_FACTOR, no further doubling), and LANE_STEP_DOWN_AFTER consecutive served calls bring it
# back to the base. Lanes paced at 0 (Nightshift) and dry runs are not adapted. Why: three runs' journals show a
# per-model bucket with a slow refill (~2-4 requests/min), not a per-minute cap; slowing down further does not
# refill a drained bucket, so the interval only backs off a little and the abort rule (RATE_LIMIT_ABORT_WINDOW_S)
# stops the run instead of crawling.
LANE_INTERVAL_FACTOR = 2
LANE_STEP_DOWN_AFTER = 15
_lane_interval_by_route: dict[str, int] = {}  # raised interval (ms) per route; absent = the lane's base
_clean_streak_by_route: dict[str, int] = {}  # consecutive successful calls since the last 429
_last_failed_429_at_by_route: dict[str, float] = {}  # monotonic time of the route's last call that failed on 429


def reset_pacing() -> None:
    """Forgets every route's adapted interval, streaks, failures and last-call times (tests; a fresh process starts clean)."""
    global _last_call_at
    _last_call_at = 0.0
    _last_call_by_route.clear()
    _lane_interval_by_route.clear()
    _clean_streak_by_route.clear()
    _last_failed_429_at_by_route.clear()


def _effective_interval_ms(which: str = "default", route: str = "") -> int:
    """The lane's interval as currently adapted for `route`: the configured base, or the raised value after 429s."""
    base = min_interval_ms(which)
    if base <= 0:
        return 0
    return max(base, _lane_interval_by_route.get(route, base))


def _note_rate_limited(which: str, route: str) -> tuple[int, int]:
    """Records one 429 on `route`; returns (interval before, interval after) in ms."""
    _clean_streak_by_route[route] = 0
    before = _effective_interval_ms(which, route)
    base = min_interval_ms(which)
    if base <= 0:
        return before, before
    after = base * LANE_INTERVAL_FACTOR
    _lane_interval_by_route[route] = after
    return before, after


def _note_success(which: str, route: str) -> None:
    """Records one served call on `route`; LANE_STEP_DOWN_AFTER in a row bring a raised interval back to the base."""
    if route not in _lane_interval_by_route:
        _clean_streak_by_route[route] = 0
        return
    streak = _clean_streak_by_route.get(route, 0) + 1
    if streak >= LANE_STEP_DOWN_AFTER or min_interval_ms(which) <= 0:
        _lane_interval_by_route.pop(route, None)
        streak = 0
    _clean_streak_by_route[route] = streak


def _throttle(which: str = "default", route: str = "") -> None:
    """Keeps at least the lane's current interval (`_effective_interval_ms`) since the last call to the same model
    route (the provider's per-minute cap is per model), and at least the shared pause since any call at all."""
    global _last_call_at
    now = time.monotonic()
    shared = min_interval_ms() / 1000.0
    lane = _effective_interval_ms(which, route) / 1000.0
    wait = max(_last_call_at + shared - now, _last_call_by_route.get(route, 0.0) + lane - now, 0.0)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = _last_call_by_route[route] = time.monotonic()


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DEFAULT_WAIT_S = 5.0
RETRY_RATE_LIMIT_WAIT_S = 15.0  # a 429 without Retry-After: the first live run showed 5 s was not enough on the Ultra lane
RETRY_MAX_WAIT_S = 60.0
# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a call whose first two attempts were both answered 429 waits
# max(RATE_LIMIT_PAUSE_S, the raw Retry-After in seconds) capped at RATE_LIMIT_PAUSE_MAX_S (an HTTP-date Retry-After
# is ignored here; the first wait keeps `_retry_wait` and its 60 s cap), and gets a third and last attempt;
# a call that fails on 429 makes the next call on the same route start behind one RATE_LIMIT_PAUSE_S pause, and that
# call gets the usual two attempts only (no second long pause). Paced lanes only: a lane at 0 ms (Nightshift) keeps
# the plain single retry. Why: on the NVIDIA direct route (the only route this evidence is from) the stricter state
# reached after ~30-35 min at the limit refused calls for 2.5-10+ min and the single 15 s retry rescued only ~55%;
# a third attempt is allowed only behind the long pause. (superseded 2026-10-24: the 150 s pause and the third attempt
# are removed; see the abort rule at RATE_LIMIT_ABORT_WINDOW_S)
# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): three consecutive calls on one route that failed on 429, each
# already behind its long pause, stop the run with RateLimitAbort; run.py turns it into exit code 3 and the run is
# continued later with --resume. RateLimitAbort derives from BaseException. Why: the nodes catch `Exception` per
# passage so one failed call skips one passage; a provider that keeps refusing would otherwise turn every remaining
# passage into a silent skip and publish an edition of failures. Three, because one or two failed calls in a row
# can still be a recoverable episode, while three in a row already sit behind ~8 min of refusals. (superseded
# 2026-10-24 for the count and the window, next entry; RateLimitAbort stays a BaseException for the same reason)
# DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): stop instead of crawl. A 429 gets one retry (15 s, or
# Retry-After capped at 60 s); a call refused on both attempts fails, and the second such failed call on one route
# within RATE_LIMIT_ABORT_WINDOW_S (monotonic clock) raises RateLimitAbort, which run.py turns into exit code 3:
# wait at least 5 hours, then --resume (the journal replays the finished calls). RateLimitAbort derives from
# BaseException so the nodes' per-passage `except Exception` cannot swallow it. Paced lanes only; a lane at 0 ms
# (Nightshift) keeps the plain single retry and never aborts. Why: three runs' journals and NVIDIA user reports show
# a per-model bucket (Lightning ~700-900 requests, Ultra ~250) refilling at ~2-4 requests/min (full refill 3.5-7 h),
# with no rate headers and no Retry-After; once drained, any faster pace is refused, the old 150 s pauses and third
# attempts kept it drained (60 successes in 30 min), and 429 streaks are reported to bring hour-long lockouts.
RATE_LIMIT_ABORT_WINDOW_S = 600.0


class RateLimitAbort(BaseException):
    """A route refused two calls within RATE_LIMIT_ABORT_WINDOW_S: its bucket is drained; stop the run (run.py: exit 3)."""

    def __init__(self, route: str, count: int = 2):
        super().__init__(
            f"route {route} is drained ({count} refused calls in {RATE_LIMIT_ABORT_WINDOW_S / 60:.0f} min); "
            "the bucket refills at ~2-4 requests/min: wait at least 5 hours, then re-run with --resume"
        )
        self.route = route
        self.count = count


RATE_HEADER_PREFIXES = ("x-ratelimit", "ratelimit")


def _rate_headers(exc: Exception) -> dict[str, str] | None:
    """The rate-limit headers of a refused call (names lower-cased), or None when the exception has no response.
    Only `x-ratelimit*`, `ratelimit*` and `retry-after` are kept: never Authorization or any other header."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is None:
        return None
    kept: dict[str, str] = {}
    for name, value in headers.items():
        low = str(name).lower()
        if low == "retry-after" or low.startswith(RATE_HEADER_PREFIXES):
            kept[low] = str(value)
    return kept


def _retry_wait(exc: Exception) -> float | None:
    """Seconds to wait before a retry, or None when the failure is not retryable (4xx other than 429,
    malformed replies, anything that is not a transport or server-side failure)."""
    from openai import APIConnectionError, APIStatusError, APITimeoutError  # imported lazily: not needed in dry run

    if isinstance(exc, APITimeoutError):
        return RETRY_DEFAULT_WAIT_S
    if isinstance(exc, APIStatusError):
        if exc.status_code not in RETRY_STATUSES:
            return None
        wait = RETRY_RATE_LIMIT_WAIT_S if exc.status_code == 429 else RETRY_DEFAULT_WAIT_S
        header = exc.response.headers.get("retry-after") if getattr(exc, "response", None) is not None else None
        if header:
            try:
                parsed = float(header)
                wait = parsed if math.isfinite(parsed) else wait  # "nan"/"inf": as if no Retry-After was sent
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
    sends it (floored at 1 s, capped at 60 s), and is recorded in the ledger row (`attempts`, `retried_after`;
    every 429 attempt also appends the response's rate-limit headers to `rate_headers`). Two attempts in total:
    the external-operation rule of AGENTS.md § 3. On a paced lane a 429 also raises the route's interval
    (decision at LANE_INTERVAL_FACTOR), and a call that ends on a 429 is timed for the abort rule
    (decision at RATE_LIMIT_ABORT_WINDOW_S; raised by json_task once the failed call's row is written).
    """
    lane = entry.get("lane", "default")
    paced = min_interval_ms(lane) > 0
    attempt = 0
    while True:
        attempt += 1
        entry["attempts"] = attempt
        _throttle(lane, model)
        try:
            raw = _client().chat.completions.with_raw_response.create(model=model, temperature=temperature, messages=messages, **_request_extras())
            result = raw.parse(), int(raw.status_code)
        except Exception as exc:  # noqa: BLE001 — classified by _retry_wait
            status = getattr(exc, "status_code", None)
            wait = _retry_wait(exc) if attempt == 1 else None
            note = f"one retry in {wait:.0f} s" if wait is not None else ""
            if status == 429:
                headers = _rate_headers(exc)
                if headers is not None:
                    entry.setdefault("rate_headers", []).append(headers)
                if paced:
                    before, after = _note_rate_limited(lane, model)
                    if wait is not None:
                        note = f"429; retry in {wait:.0f} s"
                        if after != before:
                            note += f"; lane interval now {after} ms"
                    else:
                        now = time.monotonic()
                        previous = _last_failed_429_at_by_route.get(model)
                        _last_failed_429_at_by_route[model] = now
                        if previous is not None and now - previous <= RATE_LIMIT_ABORT_WINDOW_S:
                            entry["_abort"] = True  # json_task raises RateLimitAbort after writing the row
            if wait is None:
                raise
            step = f"{type(exc).__name__}: HTTP {status if status is not None else '-'}, waited {wait:.0f} s"
            entry["retried_after"] = f"{entry['retried_after']}; then {step}" if entry.get("retried_after") else step
            if _verbose():
                print(f"  · {entry['task']:<15} {lane:<13} {model:<42} {type(exc).__name__}; {note}", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        _note_success(lane, model)
        return result


def _request_key(task: str, which: str, model: str, messages: list[dict[str, str]], temperature: float, payload: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of everything that shapes a reply (decision at `replay`)."""
    prompt = "\n".join(f"{m['role']}:{m['content']}" for m in messages)
    material = {
        "task": task,
        "lane": which,
        "route": model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "temperature": temperature,
        "extras": _request_extras(),
        "payload": payload,
    }
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): requests through the Meterless runtime carry
    # `"endpoint": "meterless"` in the key material; direct-route keys are unchanged. Why: the body sent is the same on
    # both routes, so without it a direct-route journal would replay its answers on a Meterless run (and back), and
    # the restored rows would claim receipts of the other route; existing direct-route journals keep replaying.
    if on_meterless():
        material["endpoint"] = "meterless"
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    key = _request_key(task, which, model, messages, temperature, payload)
    queued = replay.get(key)
    if queued:
        obj = parse_json_object(queued.popleft())  # the live path's own extraction (decision at `replay`)
        if obj is not None:
            if _verbose():
                print(f"  · {task:<15} replayed from journal", file=sys.stderr, flush=True)
            return obj
    entry: dict[str, Any] = {"task": task, "lane": which, "route": model, "served": "error", "ms": 0, "attempts": 0, "run_id": current_run_id, "request_key": key}
    started = time.perf_counter()
    try:
        completion, status = _create(model, messages, temperature, entry)
    except Exception as exc:
        abort = bool(entry.pop("_abort", False))
        entry["ms"] = int((time.perf_counter() - started) * 1000)
        entry["http_status"] = getattr(exc, "status_code", None)
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        calls.append(entry)
        _journal(entry, payload)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {model:<42} FAILED {entry['ms']:>6} ms  {type(exc).__name__}", file=sys.stderr, flush=True)
        if abort:  # decision at RATE_LIMIT_ABORT_WINDOW_S
            raise RateLimitAbort(model, 2) from exc
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
    met = _meterless(completion)
    injected = _hmem_injected(met)
    if injected is not None:
        entry["receipt_hmem_injected"] = injected  # disclosure only; see _hmem_injected
    if met and "from_cache" in met:
        entry["receipt_from_cache"] = bool(met.get("from_cache"))
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): on a pinned lane (explicit model id), a Meterless response whose
    # `provider_model` or `routed_model` differs from the id asked for is an error row (`served` "error", the answering
    # model in `answered_model`, `route_substituted: true`, counted by `substitution_count()`), its reply is neither
    # used nor journalled for replay, and RouteSubstituted is raised so the node skips that passage. Why: the owner
    # requires exact-lane identity for the blind fact-checker; an answer from another model is not that check.
    substitute = substituted_lane(model, met)
    if substitute is not None:
        entry.update(served="error", answered_model=substitute, route_substituted=True, error=f"route substituted {substitute} for {model}")
        calls.append(entry)
        _journal(entry, payload)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {substitute:<42} SUBSTITUTED for {model}", file=sys.stderr, flush=True)
        raise RouteSubstituted(f"{task}: {entry['error']}")
    text = (choice.message.content if choice is not None and choice.message else None) or ""
    obj = parse_json_object(text)
    if obj is None:
        why = f" (finish_reason {entry['finish_reason']})" if entry.get("finish_reason") not in (None, "stop") else ""
        entry["error"] = "reply carried no JSON object" + why
        # DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a reply without a usable answer is filed under "error" in
        # `served` (the model that answered is kept in `answered_model`), so `answered_by["error"]` equals
        # `model_errors`, the equality the portal's parser checks. Why: the first genuine run had 2 such replies and
        # the snapshot failed Vadim's consistency rule (63 ≠ 61).
        entry["answered_model"] = served
        served = entry["served"] = "error"
    if obj is not None:
        entry["reply_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()  # the reply's fingerprint; the text itself stays private
    calls.append(entry)
    _journal(entry, payload, reply=text if obj is not None else None)
    if _verbose():
        flag = "" if served == model or model.startswith("meterless/") else "  (substituted)"
        if entry.get("error"):
            flag += "  NO JSON"
        print(f"  · {task:<15} {which:<13} {served:<42} {entry['ms']:>6} ms  {entry['tokens_in']:>5}>{entry['tokens_out']:<5}{flag}", file=sys.stderr, flush=True)
    if obj is None:
        raise ValueError(f"{task}: model did not return JSON ({entry['error']})")
    return obj
