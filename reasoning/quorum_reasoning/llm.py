"""Model access. One OpenAI-compatible route (Nemotron via Meterless), read from .env like smoke_test.py.

Dry run: with QUORUM_DRY_RUN=1, or when no key is configured, every task is answered by the deterministic
heuristics in dryrun.py. The graph then runs end to end without spending credits — Studio, tests and the
first demo recording use this mode. Nothing here is a routine check; the graph runs only when started.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import sys
import threading
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
    served calls that carry `reply` and `request_key` also fill the replay queues (decision at `replay`), unless the
    row discloses injected memories or a Nightshift cache replay (decision below); journals written before 2026-10-24
    have neither field and replay nothing."""
    replay.clear()
    if not path.is_file():
        return 0
    n = refused_hmem = refused_cache = 0
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
            # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a journalled reply is queued for replay only when its
            # row discloses no injected memories (`receipt_hmem_injected` absent, or the integer 0) and no Nightshift
            # cache replay (`receipt_from_cache` absent, or exactly false); any other value in either field (a count
            # above 0, true, a string) refuses it. The row stays in the ledger, since it is a paid call, but its reply is
            # never replayed, so `json_task` sends that request live again. Why: journals written before the H-MEM
            # rejection (attempt 1 of 2026-10-22: 1206 rows with 1-3 injected memories) would otherwise hand --resume
            # and --seed-journal exactly the replies `json_task` now rejects; a cache replay is refused for the reason at
            # `_cache_hit`.
            # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a refused row is restored with `replay_refused: true`
            # only (never `hmem_rejected` or `cache_refused`), counted by `replay_refused_count()` and named in the run
            # summary as "journalled replies not replayed"; its `served` value is kept as journalled (whether provenance
            # should file it under "error" is the owner's call, open). Why: coordinator decision 5 (review round 3): a
            # resumed run did not reject those replies, it only declined to replay them, so the summary must not claim
            # a rejection; round 2 had restored them as `hmem_rejected`, and before that as plain served answers.
            hmem = row.get("receipt_hmem_injected")
            clean_hmem = "receipt_hmem_injected" not in row or (type(hmem) is int and hmem == 0)
            clean_cache = "receipt_from_cache" not in row or row["receipt_from_cache"] is False
            if clean_hmem and clean_cache:
                replay.setdefault(key, deque()).append(reply)
            else:
                if not clean_hmem:
                    refused_hmem += 1
                else:
                    refused_cache += 1
                row["replay_refused"] = True
        calls.append(row)
        n += 1
    if refused_hmem or refused_cache:
        print(f"journal: {refused_hmem + refused_cache} journalled replies not replayed ({refused_hmem} with prior answers "
              f"injected by the runtime (H-MEM), {refused_cache} Nightshift cache replays); their requests go live again", file=sys.stderr)
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
    base, key, _ = _route_family()
    model = os.getenv("NEMOTRON_MODEL") or os.getenv("METERLESS_MODEL") or "meterless/auto"
    if which == "fact_checker":
        model = os.getenv("NEMOTRON_MODEL_FACT_CHECKER") or model
    elif which == "reviewer":
        # the third blind reviewer: its own route when set, else the fact-checker's (a different model than the
        # verifier's lane when available — DECISIONS.md › Principles for handling facts, 2026-10-24)
        model = os.getenv("NEMOTRON_MODEL_REVIEWER") or os.getenv("NEMOTRON_MODEL_FACT_CHECKER") or model
    return base.strip(), key.strip(), model.strip()


def _is_direct_url(base: str) -> bool:
    """True for NVIDIA's own endpoint (integrate.api.nvidia.com), the direct route."""
    from urllib.parse import urlparse

    host = (urlparse(base).hostname or "").lower()
    return host == DIRECT_ROUTE_HOST_SUFFIX or host.endswith("." + DIRECT_ROUTE_HOST_SUFFIX)


def _route_family() -> tuple[str, str, str | None]:
    """(base URL, key, problem): base and key resolved as one family.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a Meterless token (METERLESS_RUNTIME_TOKEN / METERLESS_TOKEN)
    is used only with a Meterless base URL (MODEL_BASE_URL or METERLESS_BASE_URL pointing anywhere but NVIDIA, or the
    8088 default), and MODEL_API_KEY never pairs with a METERLESS_BASE_URL; a mixed pair is reported as `problem`, so
    `route_configured()` is False and `run.live_mode_problem()` names it. Why: review of this branch (2026-10-25): an
    NVIDIA URL with a Meterless token, or the other way round, sends a credential to the wrong service."""
    model_base = (os.getenv("MODEL_BASE_URL") or "").strip()
    meterless_base = (os.getenv("METERLESS_BASE_URL") or "").strip()
    model_key = (os.getenv("MODEL_API_KEY") or "").strip()
    meterless_key = (os.getenv("METERLESS_RUNTIME_TOKEN") or os.getenv("METERLESS_TOKEN") or "").strip()
    base = model_base or meterless_base
    key = model_key or meterless_key
    if not base and not model_key and meterless_key:
        base = METERLESS_DEFAULT_BASE_URL
    problem = None
    if key and base:
        if not model_key and _is_direct_url(base):
            problem = "mixed model route: NVIDIA base URL with a Meterless token (set MODEL_API_KEY, or point the URL at the Meterless runtime)"
        elif model_key and not model_base:
            problem = "mixed model route: METERLESS_BASE_URL with MODEL_API_KEY (blank MODEL_API_KEY and set METERLESS_TOKEN, or set MODEL_BASE_URL)"
    return base, key, problem


def route_problem() -> str | None:
    """Why the configured base URL and key do not form one route, or None."""
    _env()
    return _route_family()[2]


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
    _refuse_injected(f"probe on {model}", _meterless(completion))  # decision in `json_task`: the reply is not used
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
    met = _meterless(completion)
    _refuse_injected(f"connection test on {which} ({model})", met)  # decision in `json_task`: the reply is not used
    out: dict[str, Any] = {"lane": which, "route": model, "answered_by": getattr(completion, "model", "") or "", "reply": (completion.choices[0].message.content or "").strip()[:40]}
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
    base, _, _ = _route()
    return bool(base) and not _is_direct_url(base)


def route_configured() -> bool:
    """True when MODEL_BASE_URL and MODEL_API_KEY (or the METERLESS_* names) are both set."""
    base, key, _ = _route()
    return bool(base and key) and route_problem() is None


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
    met = _meterless(completion)
    routed = str(met.get("routed_model") or met.get("provider_model") or "")
    if routed and (served.startswith("meterless/") or not served):
        served = routed
    return served, str(met.get("receipt_id") or "")


def _json_object(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(object, shape): a dict as it is, a JSON string holding an object decoded, None (absent or JSON null) as
    (None, None); anything else is (None, what it is), an unreadable value (decision at `_meterless`)."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        return value, None
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return None, "a string that is not JSON"
        if isinstance(decoded, dict):
            return decoded, None
        return None, f"a JSON string holding {'null' if decoded is None else 'a ' + type(decoded).__name__}"
    return None, f"{json.dumps(value) if isinstance(value, (bool, int, float)) else 'a ' + type(value).__name__}"


_UNREADABLE_METERLESS = "_quorum_unreadable_meterless"  # `_meterless`: why the response's meterless value is unreadable


def _meterless(completion: Any) -> dict[str, Any]:
    """The response's `meterless` object: empty when the field is absent or null (the direct route), decoded when it
    is a JSON string holding an object, else a dict carrying only `_UNREADABLE_METERLESS`, which `_hmem_report` rejects.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a `meterless` value, an unsigned `receipt`, a `receipt_envelope`,
    its `body` or its `receipt` that is present (not absent, not null) but not an object is unreadable, unless it is a
    JSON string holding an object, which is decoded as `body` already was; an unreadable one makes the hmem report
    unreadable, so `json_task` rejects the reply (`hmem_unreadable`) and probe() / test_connection() refuse it. Why:
    review round 7 (coordinator decision 3, fail closed on any sign): a JSON-string receipt carrying `hmem.injected` 2,
    or a `meterless` value that was a string, read as no receipt at all and the reply was served with no count and no
    disclosure. Nightshift 1.2.3 sends objects (engine/openai.mjs: `receipt`, `receipt_envelope: signed || null`), so
    these shapes reject nothing it sends today."""
    raw = (getattr(completion, "model_extra", None) or {}).get("meterless")
    met, shape = _json_object(raw)
    if shape:
        return {_UNREADABLE_METERLESS: f"the response's meterless object is unreadable (it is {shape})"}
    return met or {}


def _receipt_scan(met: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """(every receipt a `meterless` object carries, why one present copy is unreadable): the unsigned `receipt` and the
    signed envelope's `body.receipt` and `receipt`, each a dict or a JSON string holding one (decision at `_meterless`)."""
    receipts: list[dict[str, Any]] = []
    problems: list[str] = []

    def take(name: str, value: Any) -> dict[str, Any] | None:
        obj, shape = _json_object(value)
        if shape:
            problems.append(f"{name} is {shape}")
        return obj

    receipt = take("receipt", met.get("receipt"))
    if receipt is not None:
        receipts.append(receipt)
    env = take("receipt_envelope", met.get("receipt_envelope"))
    if env is not None:
        # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the envelope's receipt is read at `body.receipt` and at
        # `receipt` (Nightshift dgx-client.js receiptFromEnvelope: `body.receipt || env.receipt`), and a `body` sent as a
        # JSON string is decoded first; every copy found joins the max. Why: review round 2: an envelope carrying its
        # receipt beside `body` was not read, so an injected count there was served undisclosed (fail-open).
        body = take("receipt_envelope.body", env.get("body"))
        signed = take("receipt_envelope.body.receipt", body.get("receipt")) if body is not None else None
        if signed is not None:
            receipts.append(signed)
        beside = take("receipt_envelope.receipt", env.get("receipt"))
        if beside is not None:
            receipts.append(beside)
    return receipts, (f"the response's receipt is unreadable ({problems[0]})" if problems else None)


def _receipt_copies(met: dict[str, Any]) -> list[dict[str, Any]]:
    """The readable receipts of `_receipt_scan`."""
    return _receipt_scan(met)[0]


# orchestrator.js runChat: `hmem:${hmemMeta.injected || hmemMeta.count} records`; at most 18 digits, so int() never
# meets Python's digit limit (a longer count is an H-MEM entry with no readable count, which rejects too)
_HMEM_SOURCE = re.compile(r"hmem:([0-9]{1,18}) records")


def _names_hmem(text: str) -> bool:
    """True when `text` names H-MEM in any spelling ("hmem", "H-MEM", "h_mem", "H MEM"), case ignored."""
    return "hmem" in re.sub(r"[\s_\-]", "", text.lower())


def _egress_hmem(met: dict[str, Any], receipts: list[dict[str, Any]]) -> tuple[list[int], str | None]:
    """(the H-MEM record counts the egress manifests disclose, why one manifest is unreadable): the top-level `egress`
    and every readable receipt copy's `egress` (`_receipt_scan`), read for `_hmem_report`.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): Nightshift's egress manifest is read as a sign of injected
    memories, at the top level and in every receipt copy (each through `_json_object`, so a JSON string holding an
    object is decoded): a `sent.context_sources` entry "hmem:<n> records" and a `never_eligible` entry whose `reason`
    names H-MEM (any spelling, case ignored) with a non-negative int `count` join `_hmem_report`'s max as that count.
    A present (not absent, not null) manifest is unreadable, which rejects the reply as an unreadable hmem report, when
    it is not an object, its `sent` is not an object, `sent.context_sources` or `never_eligible` is not a list, a
    `context_sources` entry is not a string, a `never_eligible` entry is not an object with a string `reason`, a
    `context_sources` entry names H-MEM in any other form (an MCP server named for it included), or an H-MEM
    `never_eligible` entry has no readable `count`; each is named by shape only, never the entry's text. An absent or
    null manifest says nothing. Why: closing review round 4 (coordinator decision 3, fail closed on any sign): with the
    hmem block null or missing, a manifest listing "hmem:2 records" was served with `receipt_hmem_injected` 0, and
    Nightshift's two-whitelist rule (orchestrator.js recordReceipt, data.js normalizeReceipt) is how one field can be
    dropped while the other survives. Nightshift 1.2.3 builds every manifest with `redact.egressManifest` (both lists
    always present, `context_sources` strings, `never_eligible` objects with a reason and a count) from the same
    `hmemMeta` as the hmem block, so this refuses nothing it sends today."""
    counts: list[int] = []
    problems: list[str] = []

    def unreadable(detail: str) -> None:
        problems.append(f"the response's egress manifest is unreadable ({detail})")

    def no_count(detail: str) -> None:
        problems.append(f"the response's egress manifest names H-MEM records with no readable count ({detail})")

    def shape(value: Any) -> str:  # a field: `.get` cannot tell absent from null
        return "absent or null" if value is None else _flag_shape(value)

    def item_shape(value: Any) -> str:  # a list entry: present, so None is a JSON null
        return "null" if value is None else _flag_shape(value)

    for name, raw in [("egress", met.get("egress")), *(("a receipt's egress", r.get("egress")) for r in receipts)]:
        manifest, bad = _json_object(raw)
        if bad:
            unreadable(f"{name} is {bad}")
            continue
        if manifest is None:
            continue
        sent, bad = _json_object(manifest.get("sent"))
        sources = sent.get("context_sources") if sent is not None else None
        if bad or sent is None:
            unreadable(f"{name}.sent is {bad or 'absent or null'}")
        elif not isinstance(sources, list):
            unreadable(f"{name}.sent.context_sources is {shape(sources)}, not a list")
        else:
            for entry in sources:
                if not isinstance(entry, str):
                    unreadable(f"{name}.sent.context_sources has an entry that is {item_shape(entry)}, not a string")
                    continue
                match = _HMEM_SOURCE.fullmatch(entry)
                if match:
                    counts.append(int(match.group(1)))
                elif _names_hmem(entry):
                    no_count(f'{name}.sent.context_sources has an entry naming H-MEM not in the form "hmem:<n> records"')
        never = manifest.get("never_eligible")
        if not isinstance(never, list):
            unreadable(f"{name}.never_eligible is {shape(never)}, not a list")
            continue
        for item in never:
            if not isinstance(item, dict):
                unreadable(f"{name}.never_eligible has an entry that is {item_shape(item)}, not an object")
                continue
            reason = item.get("reason")
            if not isinstance(reason, str):
                unreadable(f"{name}.never_eligible has an entry whose reason is {shape(reason)}, not a string")
                continue
            if not _names_hmem(reason):
                continue
            count = item.get("count")
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                counts.append(count)
            else:
                no_count(f"{name}.never_eligible has an H-MEM entry whose count is {shape(count)}")
    return counts, (problems[0] if problems else None)


def _hmem_report(met: dict[str, Any]) -> tuple[int | None, str | None]:
    """(injected count, why the hmem report is unreadable): how many H-MEM records the runtime injected into the prompt.

    Read from every place a count can appear: the unsigned receipt (`receipt.hmem`), the signed envelope's copies
    (`receipt_envelope.body.receipt.hmem`, `receipt_envelope.receipt.hmem`) and a top-level `hmem`; a block is an integer
    or a dict with an integer `injected` and/or `count` (the larger one counts). The count is None when the response
    carries no receipt and no top-level block (direct route: not a Meterless call), 0 when the receipts carry no hmem
    block or a null one. The second value is set when a present block has no readable count (2.0, "2", true, a dict
    whose `injected` and `count` are both absent or null, either of them present but not a non-negative int); the count
    is then the max of the readable copies and fields, or None when none is readable.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every block found joins one max, so a signed envelope or a
    top-level `hmem` saying 2 is not hidden by an unsigned receipt without hmem (or with 0); a present but unreadable
    block is reported, not treated as "nothing injected", and `json_task` rejects that reply too. Why: review round 1 of
    the H-MEM change: the old parser served such replies undisclosed (fail-open), and the goal is that no response
    carrying injected memories is used; review round 3 (coordinator decision 3): the top-level `hmem` was read only when
    no receipt had a block, so a top-level 2 beside a receipt 0 was served.

    Nightshift 1.2.3 (engine/js/engine/orchestrator.js, runChat): before the phase loop it prepends a system message of
    up to `hmemTopK` "prior vetted answers" retrieved by scope (`meterless-scope`) and app (`meterless-app`); the sync
    chat path exposes no per-request switch (`noMemory` is set only by the jobs plane). The count is disclosed per row,
    and a count above 0 rejects the reply (decision in `json_task`); the daemon-wide switch is `disable_hmem_injection`.
    A `meterless` value or receipt copy that is present but not an object is unreadable too (decision at `_meterless`).
    The egress manifests (top level and every receipt copy) join the same max and the same unreadable reason, after
    the receipt and hmem reasons (decision at `_egress_hmem`); a readable manifest that names no H-MEM adds nothing."""
    if not met:
        return None, None
    if met.get(_UNREADABLE_METERLESS):
        return None, str(met[_UNREADABLE_METERLESS])
    receipts, unreadable_receipt = _receipt_scan(met)
    egress_counts, unreadable_egress = _egress_hmem(met, receipts)
    blocks = [r["hmem"] for r in receipts if r.get("hmem") is not None]
    if met.get("hmem") is not None:
        blocks.append(met["hmem"])
    if not blocks:
        if egress_counts:
            return max(egress_counts), unreadable_receipt or unreadable_egress
        return (0 if receipts else None), unreadable_receipt or unreadable_egress  # a receipt without an hmem block: nothing injected
    def readable(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    def shown(value: Any) -> str:
        return json.dumps(value) if isinstance(value, (bool, int, float)) else type(value).__name__

    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every block and field is read to the end: readable counts join
    # one max and the first unreadable one is kept as the reason, so a readable 2 beside an unreadable copy is returned
    # as (2, reason): the row discloses `receipt_hmem_injected` 2 and is still rejected. Why: review round 5: the parser
    # returned at the first unreadable block, so the readable count was dropped from the error row (coordinator decision 3).
    counts: list[int] = list(egress_counts)
    unreadable: str | None = unreadable_receipt
    for block in blocks:
        if not isinstance(block, dict):
            if readable(block):
                counts.append(block)
            elif unreadable is None:
                shape = f"the block is {json.dumps(block) if isinstance(block, (bool, int, float)) else 'a ' + type(block).__name__}"
                unreadable = f"the receipt's hmem block has no readable injected count ({shape})"
            continue
        # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a dict block's `injected` and `count` are both read; every
        # one that is present and not null must be a non-negative int (else the block is unreadable, naming that field),
        # and the block's count is their max, so {"injected": 0, "count": 2} is 2 and rejects. Why: review round 4:
        # `injected` alone won whenever present, so that block was served as nothing injected (fail-open against
        # coordinator decision 3), while Nightshift's own reader takes `hmemMeta.injected || hmemMeta.count`.
        fields = {name: block[name] for name in ("injected", "count") if block.get(name) is not None}
        if not fields and unreadable is None:
            unreadable = "the receipt's hmem block has no readable injected count (no injected/count value: both absent or null)"
        for name, value in fields.items():
            if readable(value):
                counts.append(value)
            elif unreadable is None:
                unreadable = f"the receipt's hmem block has no readable injected count ({name} is {shown(value)})"
    return (max(counts) if counts else None), unreadable or unreadable_egress


def _hmem_rejection(injected: int | None, unreadable: str | None) -> str | None:
    """Why a reply is rejected for H-MEM (`_hmem_report`'s two values), or None when it is not: a count above 0, an
    unreadable block, or both (decision in `json_task`)."""
    reasons = []
    if injected is not None and injected > 0:
        reasons.append(f"runtime injected {injected} prior answers (H-MEM) into the prompt")
    if unreadable:
        reasons.append(unreadable)
    return "; ".join(reasons) or None


def _hmem_injected(met: dict[str, Any]) -> int | None:
    """The injected count of `_hmem_report`: None when the response carries no receipt or no readable count, 0 when the
    receipt says nothing was injected (an unreadable copy beside it still rejects the reply: `_hmem_report`)."""
    return _hmem_report(met)[0]


CACHE_REPLAY_REFUSED = "nightshift cache replay refused: provenance of injected memories unknown"


def _flag_shape(flag: Any) -> str:
    """How a non-boolean `from_cache` is named in a refusal: a number as itself, a string only as "a string" (never its
    text), anything else by its type (decision at `_cache_refusal`)."""
    if isinstance(flag, (int, float)):
        return json.dumps(flag)
    return "a string" if isinstance(flag, str) else f"a {type(flag).__name__}"


def _cache_refusal(met: dict[str, Any]) -> str | None:
    """Why the reply is refused as a Nightshift cache replay (`CACHE_REPLAY_REFUSED`, with the unreadable value's shape
    named when a `from_cache` is not a boolean, a `cache` block is not an object or a `cache` object has no readable
    `status`), or None (decision at `_cache_hit`).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a `from_cache` that is present, not null and not a JSON boolean
    ("true", "false", 1, 0) is refused as a cache replay (`cache_refused`, reason `CACHE_REPLAY_REFUSED` plus the value),
    not served and not written to `receipt_from_cache`; absent or null means the response does not say. Why: review
    round 7: such a flag beside `cache.status` "miss" was served, while `load_journal` refuses any `receipt_from_cache`
    other than false; Nightshift 1.2.3 sends `!!result.fromCache`, a boolean, so this refuses nothing it sends today.
    ("plus the value" superseded 2026-10-25 for strings and copies: decision below.)

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the same `from_cache` rules (true, or present, non-null and not a
    boolean) apply to the top-level flag and to every receipt copy (`_receipt_copies`: the unsigned `receipt`, the
    envelope's `body.receipt` and `receipt`), whatever the other copies or a `cache` block "miss" say; a non-boolean flag
    is named by `_flag_shape`, so a string is "a string" and its text never reaches the ledger error or the MemoryInjected
    message. Why: closing review round 1: only the top-level flag was read, so a receipt copy saying `from_cache: true`
    was served (fail-open against coordinator decision 3), and a string flag was copied into the error row (the
    coordinator's rule: failure strings report shapes, never values)."""
    for name, flag in [("from_cache", met.get("from_cache")), *(("a receipt's from_cache", r.get("from_cache")) for r in _receipt_copies(met))]:
        if flag is True:
            return CACHE_REPLAY_REFUSED
        if flag is not None and not isinstance(flag, bool):
            return f"{CACHE_REPLAY_REFUSED} ({name} is {_flag_shape(flag)}, not a boolean)"
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every `cache` block (top level and each receipt copy) is read
    # through `_json_object`: a JSON string holding an object is decoded and checked; any other present, non-null value
    # that is not an object ("exact", a number, a list, a JSON string holding something else) is refused as a cache replay
    # naming its shape (same MemoryInjected, same `cache_refused`). Why: review round 8: such a block was skipped and the
    # reply served, the one fail-open field left in the cache verdict (coordinator decisions 3 and 4); Nightshift 1.2.3
    # always sends an object there (openai.mjs: `cache: result.receipt?.cache || {status: ...}`).
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a present `cache` object (top level or a receipt copy, a JSON
    # string holding one included) is served only when its `status` is exactly the string "miss"; a status that is
    # absent or null is refused naming that shape, one that is not a string is refused naming it by `_flag_shape` (a
    # number or boolean as itself, a list or object by its type; no text of the block is copied), and any other string is
    # a hit kind, refused with the plain reason as before. `cache: null` and an absent
    # block still say nothing and are served. Why: closing review round 3: an object without a readable status
    # ({}, {"status": null}, {"hit": true}) was served, the one unreadable cache verdict not refused (coordinator
    # decision 3, as `_hmem_report` rejects an hmem block with no readable count); Nightshift 1.2.3 writes a status on
    # every receipt cache block it builds (orchestrator.js recordReceipt: `input.cache || {status: 'miss'}`, a live
    # answer `{status: 'miss', ...}`, a hit `{status: hit.kind, ...}`; openai.mjs falls back to `{status: hit/miss}`),
    # so this refuses nothing it sends today and would cost one passage per such reply.
    for name, raw in [("cache", met.get("cache")), *(("a receipt's cache", r.get("cache")) for r in _receipt_copies(met))]:
        block, shape = _json_object(raw)
        if shape:
            return f"{CACHE_REPLAY_REFUSED} ({name} is {shape}, not an object)"
        if block is None:
            continue
        status = block.get("status")
        if status is None:
            return f"{CACHE_REPLAY_REFUSED} ({name} has no readable status: absent or null)"
        if not isinstance(status, str):
            return f"{CACHE_REPLAY_REFUSED} ({name} has no readable status: {_flag_shape(status)}, not a string)"
        if status != "miss":
            return CACHE_REPLAY_REFUSED
    return None


def _cache_hit(met: dict[str, Any]) -> bool:
    """True when the runtime answered from its own answer cache: the top-level `from_cache` or any receipt copy's
    `from_cache` is true (or not a boolean: decisions at `_cache_refusal`), or the top-level `cache` block or any receipt
    copy's `cache` block is an object whose `status` is not exactly the string "miss" (Nightshift writes the hit kind
    there, "exact" or "semantic"; every live answer says "miss"; a status that is absent, null or not a string is
    unreadable and refused too) or is present but not an object (decisions in `_cache_refusal`); `cache: null` and an
    absent block say nothing.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): on the Meterless route a cache hit is refused like an injected
    reply: an error row (`cache_refused: true`, `cache_refused_count()`, counted apart from `hmem_rejected`), the reply
    neither used nor journalled for replay, MemoryInjected raised with CACHE_REPLAY_REFUSED so the node skips the passage;
    probe() and test_connection() refuse it too. A refused cache hit loses that passage (a repeated identical request is
    the one the cache answers). Why: coordinator decision 4 (review round 3): orchestrator.js looks the cache up before the
    H-MEM block and returns a cached answer with hmem null, and the answers of 2026-10-22 attempt 1 were cached while
    injection was on, so `hmemKnowledge: false` does not reach a cached answer and its receipt cannot tell."""
    return _cache_refusal(met) is not None


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


def lane_unverified_count() -> int:
    """Ledger rows on a pinned Meterless lane whose response carried no model evidence (decision in `json_task`)."""
    return sum(1 for c in calls if c.get("lane_unverified"))


def substitution_count() -> int:
    """Ledger rows whose pinned lane was answered by another model (decision in `json_task`)."""
    return sum(1 for c in calls if c.get("route_substituted"))


class MemoryInjected(ValueError):
    """The runtime prepended H-MEM "prior vetted answers" to the prompt (receipt `hmem.injected` > 0); the reply is not
    used and the node skips the passage like any failed call (decision in `json_task`)."""


def hmem_rejected_count() -> int:
    """Ledger rows of this run whose reply was rejected because the runtime injected prior answers (decision in
    `json_task`); journalled replies refused for replay are counted by `replay_refused_count()` instead."""
    return sum(1 for c in calls if c.get("hmem_rejected"))


def cache_refused_count() -> int:
    """Ledger rows whose reply was refused as a Nightshift cache replay (decision at `_cache_hit`)."""
    return sum(1 for c in calls if c.get("cache_refused"))


def replay_refused_count() -> int:
    """Journal rows restored by `load_journal` whose reply was not replayed (decision in `load_journal`)."""
    return sum(1 for c in calls if c.get("replay_refused"))


def _refuse_injected(where: str, met: dict[str, Any]) -> None:
    """Raises MemoryInjected when the receipt or an egress manifest says prior answers were injected, carries an hmem
    block or a manifest with no readable count, or the reply is a Nightshift cache replay; no receipt, a null block and
    0 pass (decisions in `json_task`, `_hmem_report`, `_egress_hmem` and `_cache_hit`)."""
    why = _hmem_rejection(*_hmem_report(met)) or _cache_refusal(met)
    if why:
        raise MemoryInjected(f"{where}: {why}; reply not used")


# The Meterless daemon's control plane, as Nightshift's own CLI reaches it (cli/lib/transport.mjs › controlSocketPath,
# adminStatus): plain HTTP/1.1 over a per-user named pipe on Windows (a Unix socket elsewhere), Host `meterlessd`, no
# auth header, 3 s timeout.
CONTROL_SOCKET_POSIX = "/run/meterless/runtime.sock"
CONTROL_TIMEOUT_S = 3.0
HMEM_SETPOINT = "hmemKnowledge"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})  # transport.mjs › LOOPBACK_HOSTS (urlparse drops the [ ] of [::1])
_PIPE_PREFIXES = ("\\\\.\\pipe\\", "\\\\?\\pipe\\", "//./pipe/", "//?/pipe/")  # compared lower-cased


def _windows_profile_dir() -> str | None:
    """The account's profile directory as libuv's os.homedir() reads it when USERPROFILE is unset
    (GetUserProfileDirectoryW on the process token); None when it cannot be read or this is not Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # private instances: argtypes stay local to this call
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        userenv = ctypes.WinDLL("userenv", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        userenv.GetUserProfileDirectoryW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        userenv.GetUserProfileDirectoryW.restype = wintypes.BOOL
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            return None
        try:
            size = wintypes.DWORD(0)
            userenv.GetUserProfileDirectoryW(token, None, ctypes.byref(size))  # asks for the buffer size
            buf = ctypes.create_unicode_buffer(max(size.value, 1))
            if not userenv.GetUserProfileDirectoryW(token, buf, ctypes.byref(size)):
                return None
            return buf.value or None
        finally:
            kernel32.CloseHandle(token)
    except (OSError, AttributeError, ValueError):
        return None


def _local_app_data() -> str:
    """%LOCALAPPDATA%, else %USERPROFILE%\\AppData\\Local, else <profile directory>\\AppData\\Local (transport.mjs ›
    localAppData). Raises OSError when LOCALAPPDATA and USERPROFILE are unset and the profile directory cannot be read.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the fallbacks are joined and normalized as Node's path.join does
    on Windows (`ntpath.normpath`: "/" becomes "\\", "..", repeated and trailing separators collapse), and the last one
    uses the profile directory libuv's os.homedir() reads with USERPROFILE unset (GetUserProfileDirectoryW), not
    HOMEDRIVE+HOMEPATH; when that cannot be read the pipe name is not guessed. Why: a different spelling gives a
    different FNV key and so another pipe; review round 1 found three such mismatches with transport.mjs."""
    import ntpath

    if os.environ.get("LOCALAPPDATA"):
        return os.environ["LOCALAPPDATA"]
    profile = os.environ.get("USERPROFILE") or _windows_profile_dir()
    if not profile:
        raise OSError("cannot derive the Meterless control pipe name: LOCALAPPDATA and USERPROFILE are unset and the "
                      "profile directory could not be read (set METERLESS_CONTROL_SOCKET)")
    return ntpath.normpath(ntpath.join(profile, "AppData", "Local"))


def _user_key(profile: str) -> str:
    """FNV-1a 64 over the UTF-8 bytes of the lower-cased profile path, low 48 bits as 12 lower-case hex digits
    (transport.mjs › userKey, which mirrors meterless-core::paths::user_key)."""
    h = 0xCBF29CE484222325
    for b in str(profile).lower().encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return format(h & 0xFFFFFFFFFFFF, "012x")


def control_socket_path() -> str:
    """Where the daemon's control plane listens: METERLESS_CONTROL_SOCKET when set (the CLI's own override), else the
    per-user pipe `\\\\.\\pipe\\ai.meterless.runtime-<userKey>-runtime` on Windows, else the packaged Unix socket.
    Raises OSError when the Windows pipe name cannot be derived (`_local_app_data`, or a profile path that is not
    valid Unicode)."""
    _env()
    override = os.environ.get("METERLESS_CONTROL_SOCKET")
    if override:
        return override
    if sys.platform == "win32":
        profile = _local_app_data()
        try:
            key = _user_key(profile)
        except UnicodeError as exc:
            # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a profile path that cannot be encoded as UTF-8 (an
            # unpaired UTF-16 surrogate, which Windows env vars and NTFS names allow) is a clear OSError, so the live
            # start fails with exit 2 and a message instead of a traceback; the name is not guessed (Node's Buffer.from
            # would substitute U+FFFD, and whether the daemon does the same is not known). Why: review round 3.
            raise OSError("cannot derive the Meterless control pipe name: the profile path (LOCALAPPDATA / USERPROFILE) "
                          f"is not valid Unicode ({type(exc).__name__}); set METERLESS_CONTROL_SOCKET") from exc
        return rf"\\.\pipe\ai.meterless.runtime-{key}-runtime"
    return CONTROL_SOCKET_POSIX


def _content_length(value: bytes | str) -> int:
    """A Content-Length header's value as an int; raises ValueError naming only its shape (decision at
    `_parse_http_response`)."""
    text = value.decode("iso-8859-1") if isinstance(value, bytes) else value
    if not re.fullmatch(r"[0-9]+", text.strip()):
        raise ValueError("the control plane's response has a Content-Length that is not a non-negative integer")
    return int(text.strip())


def _http_complete(buf: bytes) -> bool:
    """True once `buf` holds a whole HTTP response (by Content-Length or the last chunk); else read on until close.
    A malformed Content-Length raises ValueError by shape (`_content_length`)."""
    head, sep, body = buf.partition(b"\r\n\r\n")
    if not sep:
        return False
    low = head.lower()
    if b"transfer-encoding: chunked" in low:
        return body.endswith(b"0\r\n\r\n")
    for line in low.split(b"\r\n"):
        if line.startswith(b"content-length:"):
            return len(body) >= _content_length(line.split(b":", 1)[1])
    return False


def _read_response(read) -> bytes:
    """Reads until the response is complete (`_http_complete`), EOF, or the daemon closing its end after the headers.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): only EOF, a broken pipe (EPIPE) and a connection reset
    (ECONNRESET) end a close-delimited response once its headers are in; a timeout and any other OSError are re-raised.
    Why: review round 4: a socket timeout counted as a close, so a first GET that stalled after its headers parsed as
    (200, None), which `disable_hmem_injection` reads as setpoints never written (coordinator decision 6).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a broken pipe or reset ends the response only once at least one
    body byte followed the headers; one that arrives before any body byte is re-raised. Why: review round 7: a first GET
    reset right after its headers (no Content-Length, not chunked) read as an empty body, which skipped the check that
    the POST kept the other setpoints (coordinator decision 6); a plain EOF there is caught by the framing rule at
    `_parse_http_response` instead (on a Windows pipe the CRT reports the daemon's close as EOF)."""
    buf = b""
    while True:
        try:
            chunk = read(65536)
        except (BrokenPipeError, ConnectionResetError):  # the daemon closed its end; TimeoutError is not one of these
            if buf.partition(b"\r\n\r\n")[2]:
                break
            raise
        if not chunk:
            break
        buf += chunk
        if _http_complete(buf):
            break
    return buf


ERROR_FILE_NOT_FOUND = 2
ERROR_SEM_TIMEOUT = 121  # WaitNamedPipeW: no instance became free in time
ERROR_PIPE_BUSY = 231
PIPE_BUSY_WAIT_S = 2.0


class ControlPipeBusy(OSError):
    """Every instance of the daemon's control pipe stayed in use for PIPE_BUSY_WAIT_S."""


def _wait_named_pipe(where: str, ms: int) -> int:
    """WaitNamedPipeW on `where` for up to `ms`: 0 once an instance is free, else the Win32 error (ERROR_SEM_TIMEOUT: still
    busy; ERROR_FILE_NOT_FOUND: no such pipe); -1 off Windows. The seam the busy-pipe tests replace."""
    if sys.platform != "win32":
        return -1
    import ctypes
    from ctypes import wintypes

    low = where.lower()
    prefix = next(p for p in _PIPE_PREFIXES if low.startswith(p))
    rest = where[len(prefix):]
    if prefix != "\\\\?\\pipe\\":
        rest = rest.replace("/", "\\")  # what Win32 path normalisation does to the name open() was given
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # a private instance: argtypes stay local to this call
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    if kernel32.WaitNamedPipeW("\\\\.\\pipe\\" + rest, max(1, int(ms))):
        return 0
    return ctypes.get_last_error() or ERROR_SEM_TIMEOUT


_LOCAL_PIPE_ROOTS = ("\\\\.\\pipe\\", "\\\\?\\pipe\\")  # what a canonical local pipe name starts with (compared lower-cased)


def _full_path_name(where: str) -> str | None:
    """GetFullPathNameW of `where`: Win32's own path normalisation as a string (no I/O, nothing is opened); None when it
    fails or this is not Windows. The seam the canonical-prefix test replaces."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # a private instance: argtypes stay local to this call
        kernel32.GetFullPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.LPWSTR)]
        kernel32.GetFullPathNameW.restype = wintypes.DWORD
        size = kernel32.GetFullPathNameW(where, 0, None, None)
        if not size:
            return None
        buf = ctypes.create_unicode_buffer(size)
        n = kernel32.GetFullPathNameW(where, size, buf, None)
        return buf.value if 0 < n < size else None
    except (OSError, AttributeError, ValueError):
        return None


def _pipe_name_problem(where: str) -> str | None:
    """Why `where` is not a name in this machine's local pipe namespace, or None (decision below).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): before anything is opened, a pipe-shaped name is refused when the
    part after its prefix is empty, holds a NUL, or has a component made only of dots and spaces (".", "..", ".. ") in
    any spelling (`\\\\?\\` included, "/" and "\\" both separators), and when GetFullPathNameW (string only) does not
    keep it under `\\\\.\\pipe\\` or `\\\\?\\pipe\\`. Why: review round 7: `\\\\.\\pipe\\..\\UNC\\<host>\\pipe\\x` (and the
    `//./` and `GLOBALROOT\\Device\\Mup` spellings) passed the prefix check and normalises to a pipe on another machine,
    which also passes the GetFileType check: the setter would switch a remote daemon and report success, and opening the
    UNC name offers the user's NTLM response to that host even when what opens is then refused."""
    low = where.lower()
    prefix = next((p for p in _PIPE_PREFIXES if low.startswith(p)), None)
    if prefix is None:
        return f"{where} is not a named pipe (\\\\.\\pipe\\<name>); nothing was opened"
    rest = where[len(prefix):]
    if not rest or "\0" in rest or any(part and not part.strip(". ") for part in rest.replace("/", "\\").split("\\")):
        return (f"the control pipe name {where} has an empty pipe name, a NUL or a '.' / '..' component after its prefix, "
                "which can resolve outside this machine's pipe namespace; nothing was opened")
    full = _full_path_name(where)
    if full is None:
        return f"cannot canonicalise the control pipe name {where} (GetFullPathNameW failed); nothing was opened"
    if not full.lower().startswith(_LOCAL_PIPE_ROOTS) or len(full) <= len(_LOCAL_PIPE_ROOTS[0]):
        return f"the control pipe name {where} resolves to {full}, outside this machine's pipe namespace; nothing was opened"
    return None


def _open_pipe(where: str):
    """open(where, "r+b", buffering=0), waiting up to PIPE_BUSY_WAIT_S in all for a busy pipe to free an instance; the
    name must be a local pipe name (`_pipe_name_problem`, checked before the open) and what opens must be a pipe
    (decision below).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): an open that fails with ERROR_PIPE_BUSY (winerror 231, or the bare
    EINVAL the CRT maps it to) waits on WaitNamedPipeW for the time left of PIPE_BUSY_WAIT_S (2 s) and retries; a pipe
    still busy then raises ControlPipeBusy ("the control pipe is busy"); an EINVAL that WaitNamedPipeW does not confirm as
    busy is re-raised as it came. Why: review round 3: the daemon serves few instances (the cockpit polls /admin/status),
    Node's socketPath waits on a busy pipe, and Python's open() failed at once with "Invalid argument", which named no
    cause."""
    problem = _pipe_name_problem(where)  # decision there: before the open, so a remote host never sees the name
    if problem:
        raise OSError(problem)
    deadline = time.monotonic() + PIPE_BUSY_WAIT_S
    while True:
        try:
            pipe = open(where, "r+b", buffering=0)
        except OSError as exc:
            if getattr(exc, "winerror", None) != ERROR_PIPE_BUSY and exc.errno != errno.EINVAL:
                raise
            busy = ControlPipeBusy(f"the control pipe is busy: every instance stayed in use for {PIPE_BUSY_WAIT_S:g} s")
            left = deadline - time.monotonic()
            if left <= 0:
                raise busy from exc
            code = _wait_named_pipe(where, int(left * 1000))
            if code == ERROR_SEM_TIMEOUT:
                raise busy from exc
            if code == ERROR_FILE_NOT_FOUND:
                raise FileNotFoundError(ERROR_FILE_NOT_FOUND, "The system cannot find the file specified", where) from exc
            if code != 0:
                raise
            time.sleep(0.01)  # an instance is free: retry the open (another client may take it first)
            continue
        # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): what open() returned must be a pipe (GetFileType ==
        # FILE_TYPE_PIPE) before anything is written; any other file type is closed unwritten and raises OSError naming
        # it. Why: review round 5: the prefix alone took `\\.\pipe\..\C:\x.txt` for a pipe, and Win32 path normalisation
        # resolves it to the regular file C:\x.txt, so the setter's POST overwrote that file's first bytes.
        kind = _file_type(pipe)
        if kind != FILE_TYPE_PIPE:
            pipe.close()
            raise OSError(f"{where} is not a named pipe (it opened {_FILE_TYPES.get(kind, f'a file of type {kind}')}); "
                          "nothing was written")
        return pipe


FILE_TYPE_PIPE = 3
_FILE_TYPES = {0: "a file of unknown type", 1: "a disk file", 2: "a character device", 3: "a pipe", -1: "a handle whose type could not be read"}


def _file_type(pipe) -> int:
    """GetFileType of an open file's handle: 1 a disk file, 2 a character device, FILE_TYPE_PIPE (3) a pipe or socket;
    -1 when it cannot be read or this is not Windows. The seam the fake-`open` tests replace."""
    if sys.platform != "win32":
        return -1
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # a private instance: argtypes stay local to this call
        kernel32.GetFileType.argtypes = [wintypes.HANDLE]
        kernel32.GetFileType.restype = wintypes.DWORD
        return int(kernel32.GetFileType(msvcrt.get_osfhandle(pipe.fileno())))
    except (OSError, AttributeError, ValueError):
        return -1


def _control_exchange(where: str, request: bytes, timeout: float = CONTROL_TIMEOUT_S) -> bytes:
    """Writes one request to the control pipe or socket and returns the raw response bytes. Raises OSError /
    TimeoutError when the whole exchange does not finish within `timeout`. A Windows pipe has no read timeout, so its
    exchange runs in a daemon thread; a Unix socket's calls each get the time left (decision below).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a named pipe is recognised by its prefix in either spelling
    (`\\\\.\\pipe\\`, `\\\\?\\pipe\\`, or with forward slashes) and in any case; on Windows any other path is refused
    with a clear OSError instead of reaching AF_UNIX. Why: Windows CPython has no socket.AF_UNIX, so an override such as
    `\\\\.\\PIPE\\x` failed as "AttributeError ... AF_UNIX", and Node's socketPath (transport.mjs) takes only pipes there.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the pipe branch is taken on Windows only; elsewhere every path,
    a pipe-shaped one included, is a Unix socket path, as transport.mjs passes any override to http.request({socketPath}).
    On Windows `_open_pipe` also refuses a name outside the local pipe namespace before opening it (`_pipe_name_problem`)
    and whatever opens but is not a pipe (decisions there). Why: review round 5: off
    Windows `\\\\.\\pipe\\x` from a copied .env is a relative regular filename, and the pipe branch wrote the request
    into it."""
    if sys.platform == "win32" and where.lower().startswith(_PIPE_PREFIXES):
        result: dict[str, Any] = {}

        def talk() -> None:
            try:
                with _open_pipe(where) as pipe:
                    pipe.write(request)
                    result["raw"] = _read_response(pipe.read)
            except BaseException as exc:  # noqa: BLE001 — handed back to the caller's thread
                result["exc"] = exc

        worker = threading.Thread(target=talk, name="meterless-control", daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            raise TimeoutError(f"no answer within {timeout:.0f} s")
        if "exc" in result:
            raise result["exc"]
        return result["raw"]
    if sys.platform == "win32":
        raise OSError(f"{where} is not a named pipe (\\\\.\\pipe\\<name>); Unix control sockets are not supported on Windows")
    import socket

    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the Unix socket gets one overall deadline of `timeout` for
    # connect, send and every read (each call's socket timeout is the time left; none left raises TimeoutError), like the
    # pipe's worker join. Why: review round 4: a per-recv timeout let a daemon that trickles bytes hold `--model live`
    # for as long as it kept sending.
    deadline = time.monotonic() + timeout

    def time_left() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"no answer within {timeout:.0f} s")
        return left

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:  # type: ignore[attr-defined]
        sock.settimeout(time_left())
        sock.connect(where)
        sock.settimeout(time_left())
        sock.sendall(request)

        def read(n: int) -> bytes:
            sock.settimeout(time_left())
            return sock.recv(n)

        return _read_response(read)


NOT_JSON = object()  # `_parse_http_response`: a body that is there but is not JSON (unlike an empty body or JSON null)
UNFRAMED_EMPTY = object()  # `_parse_http_response`: no body bytes and no framing (it may have been cut off after its headers)


def _parse_http_response(raw: bytes) -> tuple[int, Any]:
    """(status, JSON body) of a raw HTTP/1.1 response: None for a framed empty body or JSON null, UNFRAMED_EMPTY for a
    close-delimited response with no body bytes, NOT_JSON for a body that is not JSON; raises ValueError when there is no
    status line or the body is shorter than its framing announced.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a Content-Length body shorter than announced, a chunk shorter
    than its size line, and a chunked body without its terminating 0-size chunk raise ValueError; only a framed empty
    body (Content-Length 0 or an empty chunked body) is "no body" (None); a close-delimited one with no bytes is
    UNFRAMED_EMPTY, which `disable_hmem_injection` refuses on the first GET. Why: review round 3: a first GET cut off
    after its headers parsed as (200, None), which `disable_hmem_injection` reads as setpoints never written, so the
    check that the POST kept the other setpoints (the privacy floor) was silently skipped; review round 7: the same held
    for a close-delimited first GET ended by EOF or a reset right after its headers (coordinator decision 6).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a status code that is not three digits, a chunk size that is not
    hexadecimal and a Content-Length that is not a non-negative integer (`_content_length`, also in `_http_complete`)
    raise ValueError naming only that shape; the daemon's bytes are never repeated in the message. Why: closing review
    round 1: `int()` raised "invalid literal ... b'<the daemon's bytes>'", which the setter's failure printed (the
    coordinator's rule: failure strings report shapes, never values)."""
    head, sep, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    parts = lines[0].split(" ", 2)
    if not sep or len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise ValueError("the control plane did not answer with an HTTP response")
    if not re.fullmatch(r"[0-9]{3}", parts[1]):
        raise ValueError("the control plane did not answer with an HTTP response (its status code is not three digits)")
    status = int(parts[1])
    headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:]) if k.strip()}
    framed = True
    if "chunked" in headers.get("transfer-encoding", "").lower():
        plain = b""
        while True:
            size_line, found, rest = body.partition(b"\r\n")
            if not found:
                raise ValueError("the control plane's chunked response was cut short (no terminating 0-size chunk)")
            size_field = size_line.split(b";")[0].strip()
            if not re.fullmatch(rb"[0-9A-Fa-f]+", size_field):
                raise ValueError("the control plane's chunked response has a chunk size that is not hexadecimal")
            size = int(size_field, 16)
            if size == 0:
                break
            if len(rest) < size + 2 or rest[size : size + 2] != b"\r\n":
                raise ValueError(f"the control plane's chunked response was cut short (a {size}-byte chunk is incomplete)")
            plain += rest[:size]
            body = rest[size + 2 :]
        body = plain
    elif "content-length" in headers:
        announced = _content_length(headers["content-length"])
        if len(body) < announced:
            raise ValueError(f"the control plane's response was cut short ({len(body)} of {announced} body bytes)")
        body = body[:announced]
    else:
        framed = False  # close-delimited: the body is whatever came before the daemon closed its end
    if not body.strip():
        return status, (None if framed else UNFRAMED_EMPTY)
    try:
        return status, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, NOT_JSON


def _control_http(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    """One HTTP/1.1 request on the daemon's control plane: (status, body as `_parse_http_response` reads it). Raises when the pipe or
    socket cannot be reached. The single seam tests replace: no test opens the real control plane."""
    data = b"" if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    head = [f"{method} {path} HTTP/1.1", "Host: meterlessd", "Accept: application/json", "Connection: close"]
    if body is not None:
        head += ["Content-Type: application/json", f"Content-Length: {len(data)}"]
    raw = _control_exchange(control_socket_path(), ("\r\n".join(head) + "\r\n\r\n").encode("ascii") + data)
    return _parse_http_response(raw)


def _setpoint_doc(body: Any) -> tuple[dict[str, Any] | None, str]:
    """The setpoints document of a GET answer as `(document, "")`, or `(None, shape)` naming why there is none.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): one reader for both GETs. A `{"setpoints": ...}` wrapper is
    read only when its value is an object, or null (Nightshift dgx-client.js: "null = never written", an empty
    document); any other value is "a setpoints wrapper that is not an object" and the outer object is never read as a
    bare document. A bare object (no `setpoints` key) is a document only when it holds the hmemKnowledge key; one
    without it, such as {"ok": true} or {"error": "x"}, is "JSON with no setpoints wrapper and no hmemKnowledge key".
    Why: review round 9: `{"setpoints": []}` or `{"error": "x"}` on the first GET became the snapshot, so the
    machine-wide POST went out and the failure told the operator to restore setpoints named `setpoints` or `error`
    that were never touched; a read-back `{"setpoints": "x", "hmemKnowledge": false}` passed on the outer key."""
    if body is UNFRAMED_EMPTY:
        return None, "no body and no Content-Length or chunked framing (cut off after its headers?)"
    if body is NOT_JSON:
        return None, "a body that is not JSON"
    if body is None:
        return None, "no body, or JSON null"
    if not isinstance(body, dict):
        return None, f"JSON that is not an object (a {type(body).__name__})"
    if "setpoints" in body:
        inner = body["setpoints"]
        if inner is None or isinstance(inner, dict):
            return dict(inner or {}), ""
        return None, f"a setpoints wrapper that is not an object (a {type(inner).__name__})"
    if HMEM_SETPOINT in body:
        return dict(body), ""
    return None, f"JSON with no setpoints wrapper and no {HMEM_SETPOINT} key"


def _same_json(a: Any, b: Any) -> bool:
    """True when two parsed JSON values are the same JSON: 1, 1.0 and true differ, as do 0 and false.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the other-setpoints check compares canonical JSON text
    (`json.dumps(..., sort_keys=True)`), not Python `==`, so a POST that turns 1 into true, 0 into false or 1 into 1.0
    counts as a change. Why: review round 9: `!=` treats those as equal, so a privacy flag changing type passed as
    unchanged, while the daemon's JS reads setpoints with `===`; failing closed on 1 vs 1.0 costs one refused start."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def disable_hmem_injection() -> str | None:
    """Turns the Meterless daemon's H-MEM reinjection off and confirms it: None on success, else why not.

    Only on the Meterless family (`on_meterless()`); on the direct NVIDIA route it sends nothing and returns None.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): POST /admin/setpoints with exactly {"hmemKnowledge": false} on the
    daemon's control plane, then GET /admin/setpoints; only a read-back that is JSON `false` passes (true, absent, null,
    0, a non-200 status or an unreachable pipe are failures). The setpoint is machine-wide for this daemon and is left
    false after the run, never restored. Why: the chat path has no per-request switch (`noMemory` exists only on the jobs
    plane) and orchestrator.js skips the reinjection block only when `hmemKnowledge === false`; with the setpoint false
    the 2026-10-25 receipts (Lightning 09:43, Ultra 09:59) had hmem null and 23 input tokens, with it on (Ultra 03:45)
    2 injected memories and 145 input tokens.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the setter runs only when the Meterless base URL's host is
    loopback (127.0.0.1, localhost, ::1); any other host is a live-start failure and nothing is sent. Why: the control
    pipe is this machine's daemon, so for a remote runtime it would switch the wrong daemon and claim success, and
    transport.mjs refuses non-loopback bases for the same reason (review round 1).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a GET /admin/setpoints before the POST snapshots the document,
    and any other setpoint that the POST changed (as JSON, type included: decision at `_same_json`) or removed is a
    live-start failure naming the keys (values are not printed); the POST body stays exactly {"hmemKnowledge": false}.
    Why: IPC_SPEC.md says the POST "rewrites" the
    setpoints namespace without saying whether it merges; if it replaces, the run would silently wipe the user's
    machine-wide privacy floor and budgets (a privacy floor that vanishes lets prompts leave the machine).
    """
    if not on_meterless():
        return None
    from urllib.parse import urlparse

    host = (urlparse(_route()[0]).hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        return (f"cannot turn H-MEM injection off: the Meterless base URL host {host or '?'} is not loopback, so this "
                "machine's control pipe is not that runtime's; point the base URL at 127.0.0.1 or use the direct NVIDIA route")
    try:
        where = control_socket_path()
    except Exception as exc:  # noqa: BLE001 — OSError, or anything else deriving the name raised: reported, never raised
        return f"cannot turn H-MEM injection off: {exc}" if isinstance(exc, OSError) else \
            f"cannot turn H-MEM injection off: cannot derive the Meterless control pipe name ({type(exc).__name__}: {exc}); set METERLESS_CONTROL_SOCKET"
    try:
        status, before = _control_http("GET", "/admin/setpoints")
    except OSError as exc:  # reported, never raised: the caller refuses to start
        return f"cannot turn H-MEM injection off: the Meterless control plane {where} is unreachable ({type(exc).__name__}: {exc})"
    except Exception as exc:  # noqa: BLE001 — a response cut short or not HTTP (decision at `_parse_http_response`)
        return f"cannot turn H-MEM injection off: the first GET /admin/setpoints on {where} failed ({type(exc).__name__}: {exc})"
    if not 200 <= status < 300:
        return f"cannot turn H-MEM injection off: the first GET /admin/setpoints answered HTTP {status}"
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a first GET answering `{"setpoints": null}`, a bare JSON null or
    # a framed empty body (Content-Length 0, an empty chunked body) is a daemon whose setpoints were never written: the
    # snapshot is an empty document (nothing can be lost); a close-delimited body with no bytes (UNFRAMED_EMPTY), a body
    # that is not JSON, or JSON that is not a document (`_setpoint_doc`: a non-object wrapper such as `{"setpoints": []}`,
    # or a bare object without hmemKnowledge such as `{"error": "x"}`), still refuses before the POST, naming the shape,
    # and the read-back must still hold `hmemKnowledge: false`. Why: review round 2: a fresh daemon answered
    # `{"setpoints": null}`, which was read as a document with the key `setpoints`, so the first live start failed after
    # the POST and wrongly said other setpoints were wiped; review round 7: an unframed empty body is what a GET cut off
    # after its headers looks like; review round 9: the other non-documents still reached the POST (decision at `_setpoint_doc`).
    if before is UNFRAMED_EMPTY:
        return ("cannot turn H-MEM injection off: the first GET /admin/setpoints answered no body and no Content-Length "
                "or chunked framing (cut off after its headers?), so the other setpoints could not be snapshotted; nothing was changed")
    before_doc, shape = ({}, "") if before is None else _setpoint_doc(before)
    if before_doc is None:
        return (f"cannot turn H-MEM injection off: GET /admin/setpoints returned no setpoints document to compare the change "
                f"against ({shape}); nothing was changed")
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every failure once the POST may have reached the daemon says so.
    # A POST that raised (any exception: the seam cannot tell whether its bytes were written, and one deadline covers the
    # open, the write and the read) or answered a non-2xx status is followed by one best-effort GET /admin/setpoints run
    # through the same checks as the read-back (`_setpoint_problems`: hmemKnowledge false, other setpoints unchanged),
    # whose result joins the failure; the failure stands even when that GET shows the POST applied (a retry runs the
    # setter again). When that GET, or the read-back after a 2xx POST, raises, answers non-2xx or carries no readable
    # document, the failure ends with `_post_may_have_applied` (the keys of the first GET's document, values never
    # printed). Why: closing review round 1: such a failure skipped the other-setpoints comparison and never told the
    # operator that the machine-wide change may have been applied (coordinator decision 6, the privacy floor).
    # ("whose result joins the failure" superseded in part 2026-10-25 for a POST that raised: such a failure also ends
    # with the warning unless that GET shows the POST applied; decision at `_readback_after_failed_post`.)
    try:
        status, _ = _control_http("POST", "/admin/setpoints", {HMEM_SETPOINT: False})
    except Exception as exc:  # noqa: BLE001
        return (f"cannot turn H-MEM injection off: POST /admin/setpoints on {where} failed ({type(exc).__name__}: {exc}); "
                + _readback_after_failed_post(before_doc, exc))
    if not 200 <= status < 300:
        return f"cannot turn H-MEM injection off: POST /admin/setpoints answered HTTP {status}; " + _readback_after_failed_post(before_doc)
    try:
        status, body = _control_http("GET", "/admin/setpoints")
    except Exception as exc:  # noqa: BLE001
        return (f"cannot confirm H-MEM injection is off: GET /admin/setpoints on {where} failed ({type(exc).__name__}: {exc}); "
                + _post_may_have_applied(before_doc))
    if not 200 <= status < 300:
        return f"cannot confirm H-MEM injection is off: GET /admin/setpoints answered HTTP {status}; " + _post_may_have_applied(before_doc)
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a read-back with no readable setpoints document (a close-delimited
    # body with no bytes, a body that is not JSON, a framed empty body or JSON null, JSON that is not an object, a wrapper
    # whose `setpoints` is not an object (round 9), or a bare object without the `{"setpoints": ...}` wrapper that lacks
    # the hmemKnowledge key just written, such as {"ok": true})
    # is one failure naming that shape and nothing else; the hmemKnowledge value and the other-setpoints comparison run
    # only on a readable document (a wrapped one missing the key still reads back as null). Why: review round 8: such a
    # read-back was read as an empty document, so the failure said the setpoint read back as null and that the POST wiped
    # every other machine-wide setpoint, which could send the operator to rewrite setpoints that were never changed.
    # ("nothing else" superseded 2026-10-25: the failure now ends with `_post_may_have_applied`, keys only, which claims
    # no change: decision at the POST above.)
    after_doc, shape = _setpoint_doc(body)  # the same reader as the first GET (decision at `_setpoint_doc`)
    if after_doc is None:
        return (f"cannot confirm H-MEM injection is off: GET /admin/setpoints answered no readable setpoints document ({shape}); "
                + _post_may_have_applied(before_doc))
    return "; ".join(_setpoint_problems(before_doc, after_doc)) or None


def _readback_shape(value: Any) -> str:
    """How a read-back hmemKnowledge that is not JSON false is named: null (also for an absent key), true and a number as
    JSON literals, anything else by its shape only, never its text (decision at `_setpoint_problems`)."""
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "an object"
    if isinstance(value, list):
        return "an array"
    return _flag_shape(value)  # true and a number as themselves, a string as "a string"


def _setpoint_problems(before_doc: dict[str, Any], after_doc: dict[str, Any]) -> list[str]:
    """What a readable read-back shows against the first GET's document: hmemKnowledge not JSON false, and other
    setpoints the POST changed (as JSON, `_same_json`) or removed, named by key only (decisions in `disable_hmem_injection`).

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a read-back hmemKnowledge that is not JSON false is named by
    `_readback_shape`: true, null (also for an absent key) and a number as JSON literals, a string as "a string", an
    object as "an object", an array as "an array"; the daemon's text never reaches the failure. Why: closing review
    round 2: `json.dumps(value)` copied a string or a whole object from the daemon into the failure and onto stderr (the
    coordinator's rule: failure strings report shapes, never values), the one daemon text left after `_flag_shape`."""
    problems = []
    value = after_doc.get(HMEM_SETPOINT)
    if value is not False:
        problems.append(f"H-MEM injection is not off: {HMEM_SETPOINT} read back as {_readback_shape(value)} after POST /admin/setpoints, not false")
    lost = sorted(k for k in before_doc if k != HMEM_SETPOINT and (k not in after_doc or not _same_json(after_doc[k], before_doc[k])))
    if lost:
        problems.append(f"POST /admin/setpoints changed or removed other daemon setpoints: {', '.join(lost)} (values not "
                        "printed); they are machine-wide: check and restore them in Nightshift before a live run")
    return problems


def _post_may_have_applied(before_doc: dict[str, Any], pending: bool = False) -> str:
    """The fixed warning when no read-back could be compared after a POST that may have reached the daemon: the keys the
    first GET held, never their values (decision at the POST in `disable_hmem_injection`). `pending`: the POST timed
    out, so it may still be applied after this answer (decision at `_readback_after_failed_post`)."""
    lead = ("the POST may still be applied (it timed out and the daemon may apply it later)" if pending
            else "the POST may have been applied")
    others = sorted(k for k in before_doc if k != HMEM_SETPOINT)
    if not others:
        return f"{lead}: check {HMEM_SETPOINT} in Nightshift before retrying (no other setpoint was set before the POST)"
    return f"{lead}: check {HMEM_SETPOINT} and these setpoints in Nightshift before retrying: {', '.join(others)} (values not printed)"


def _readback_after_failed_post(before_doc: dict[str, Any], post_exc: BaseException | None = None) -> str:
    """One best-effort GET /admin/setpoints after a POST that failed (`post_exc`: the exception it raised, None for a
    non-2xx answer) but may have reached the daemon: what it shows (`_setpoint_problems`, or that the POST was
    applied), with `_post_may_have_applied` whenever it cannot show the POST applied after a POST that raised, else
    `_post_may_have_applied` alone (decision at the POST in `disable_hmem_injection`). Never raises.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): after a POST that raised (any exception: unlike a non-2xx
    answer, it does not show the daemon has finished with the request), the failure ends with `_post_may_have_applied`
    unless this GET shows the POST applied: after the problems it shows, and also when it shows hmemKnowledge false
    and no other setpoint changed while the first GET already held hmemKnowledge false (the document is the same with
    or without the POST). After a TimeoutError the warning says the POST may still be applied (the pipe exchange's
    worker thread outlives the deadline with the POST's bytes written). Why: closing review round 2: a timed-out POST
    that the daemon applied as a replace after this GET was reported as only "read back as true", and a retry then
    snapshotted the wiped document and passed, so the loss of the machine-wide privacy floor was never reported."""
    pending = isinstance(post_exc, TimeoutError)
    try:
        status, body = _control_http("GET", "/admin/setpoints")
    except Exception as exc:  # noqa: BLE001 — best effort: any failure is the warning
        return f"a read-back GET /admin/setpoints failed too ({type(exc).__name__}); " + _post_may_have_applied(before_doc, pending)
    if not 200 <= status < 300:
        return f"a read-back GET /admin/setpoints answered HTTP {status}; " + _post_may_have_applied(before_doc, pending)
    after_doc, shape = _setpoint_doc(body)
    if after_doc is None:
        return (f"a read-back GET /admin/setpoints answered no readable setpoints document ({shape}); "
                + _post_may_have_applied(before_doc, pending))
    problems = _setpoint_problems(before_doc, after_doc)
    if problems:
        shows = "a read-back GET /admin/setpoints shows: " + "; ".join(problems)
        return shows if post_exc is None else f"{shows}; {_post_may_have_applied(before_doc, pending)}"
    if post_exc is not None and before_doc.get(HMEM_SETPOINT) is False:
        return (f"a read-back GET /admin/setpoints shows {HMEM_SETPOINT} false and no other setpoint changed, but "
                f"{HMEM_SETPOINT} was already false before the POST, so it does not show the POST applied; "
                + _post_may_have_applied(before_doc, pending))
    return (f"a read-back GET /admin/setpoints shows the POST applied ({HMEM_SETPOINT} false, no other setpoint changed); "
            "retry the run")


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
    injected, hmem_unreadable = _hmem_report(met)
    if injected is not None:
        entry["receipt_hmem_injected"] = injected  # disclosed on every row; above 0 the reply is rejected (decision below)
    if isinstance(met.get("from_cache"), bool):
        entry["receipt_from_cache"] = met["from_cache"]
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): on a pinned lane (explicit model id), a Meterless response whose
    # `provider_model` or `routed_model` differs from the id asked for is an error row (`served` "error", the answering
    # model in `answered_model`, `route_substituted: true`, counted by `substitution_count()`), its reply is neither
    # used nor journalled for replay, and RouteSubstituted is raised so the node skips that passage. Why: the owner
    # requires exact-lane identity for the blind fact-checker; an answer from another model is not that check.
    # A substituted reply that is also rejected for H-MEM or refused as a cache replay raises MemoryInjected instead,
    # with `route_substituted` kept on the same row (precedence in the decision below).
    substitute = substituted_lane(model, met)
    substituted = {"route_substituted": True} if substitute is not None else {}
    answered = substitute if substitute is not None else served
    also = f"; route substituted {substitute} for {model}" if substitute is not None else ""
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a Meterless response whose receipt says the runtime injected
    # prior answers (`_hmem_report` count > 0), or carries an hmem block with no readable count (`hmem_unreadable: true`,
    # decision at `_hmem_report`), is an error row (`served` "error", the answering model in `answered_model`,
    # `hmem_rejected: true`, `receipt_hmem_injected` kept when any copy is readable, counted by `hmem_rejected_count()`),
    # its reply is neither used nor journalled for replay, and MemoryInjected is raised so the node skips that passage, as
    # for RouteSubstituted. This verdict and the cache refusal come before the substitution check and the lane-evidence
    # mark: a reply that is also substituted raises MemoryInjected, its row carries `route_substituted: true` as well and
    # is counted by both `hmem_rejected_count()` and `substitution_count()`, and a rejected row is never also
    # `lane_unverified`. hmem null or 0 is served; a response with no `meterless` object (direct route, count None) is
    # unchanged; probe() and test_connection() refuse the same replies (`_refuse_injected`); journalled replies with a
    # count are not replayed (decision in `load_journal`); pacing and the 429 breaker see the call as served (HTTP 200).
    # Why: H-MEM prepends earlier answers to our prompt, so the reply is not an independent reading of this passage;
    # run.py turns injection off before the first call (`disable_hmem_injection`) and this catches any response that
    # still carries injected memories; review round 5: the substitution check ran first, so a substituted reply with
    # injected memories raised RouteSubstituted and was neither flagged `hmem_rejected` nor counted as a rejection.
    rejection = _hmem_rejection(injected, hmem_unreadable)
    if rejection:
        entry.update(served="error", answered_model=answered, hmem_rejected=True, error=rejection + also, **substituted)
        if hmem_unreadable:
            entry["hmem_unreadable"] = True
        calls.append(entry)
        _journal(entry, payload)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {answered:<42} REJECTED: {'unreadable hmem block' if hmem_unreadable else f'{injected} injected memories'}{also}", file=sys.stderr, flush=True)
        raise MemoryInjected(f"{task}: {entry['error']}")
    cache_refusal = _cache_refusal(met)
    if cache_refusal:  # decision at `_cache_hit`: same handling as an injected reply, counted apart
        entry.update(served="error", answered_model=answered, cache_refused=True, error=cache_refusal + also, **substituted)
        calls.append(entry)
        _journal(entry, payload)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {answered:<42} REFUSED: Nightshift cache replay{also}", file=sys.stderr, flush=True)
        raise MemoryInjected(f"{task}: {entry['error']}")
    if substitute is not None:
        entry.update(served="error", answered_model=substitute, route_substituted=True, error=f"route substituted {substitute} for {model}")
        calls.append(entry)
        _journal(entry, payload)
        if _verbose():
            print(f"  · {task:<15} {which:<13} {substitute:<42} SUBSTITUTED for {model}", file=sys.stderr, flush=True)
        raise RouteSubstituted(f"{task}: {entry['error']}")
    # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): on the Meterless route a pinned lane whose response has no
    # `meterless` block, or neither provider_model nor routed_model, is served but marked `lane_unverified: true`
    # (`lane_unverified_count()`), not an error. Why: review of this branch: absent evidence is not a substitution,
    # but it must not pass as a verified lane either.
    if model and not model.startswith("meterless/") and on_meterless():
        if not (met.get("provider_model") or met.get("routed_model")):
            entry["lane_unverified"] = True
    text =(choice.message.content if choice is not None and choice.message else None) or ""
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
