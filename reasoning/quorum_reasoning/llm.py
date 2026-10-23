"""Model access. One OpenAI-compatible route (Nemotron via Meterless), read from .env like smoke_test.py.

Dry run: with QUORUM_DRY_RUN=1, or when no key is configured, every task is answered by the deterministic
heuristics in dryrun.py. The graph then runs end to end without spending credits — Studio, tests and the
first demo recording use this mode. Nothing here is a routine check; the graph runs only when started.
"""

from __future__ import annotations

import json
import os
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


def test_connection(which: str = "default") -> dict[str, str]:
    """One small chat completion on a lane. Returns the route asked for and the model that answered."""
    base, key, model = _route(which)
    if not (base and key):
        raise RuntimeError("no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env")
    completion = _client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    return {"lane": which, "route": model, "answered_by": getattr(completion, "model", "") or "", "reply": (completion.choices[0].message.content or "").strip()[:40]}


def is_dry_run(state_flag: bool) -> bool:
    if state_flag or os.getenv("QUORUM_DRY_RUN") == "1":
        return True
    base, key, _ = _route()
    return not (base and key)


def model_name(which: str = "default") -> str:
    return _route(which)[2]


def _prompt(task: str) -> str:
    p = _PROMPTS / f"{task}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else f"Task: {task}. Answer with JSON only."


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
    completion = _client().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": _prompt(task)},
            {"role": "user", "content": DATA_NOTE + "\n" + json.dumps(payload, ensure_ascii=False)},
        ],
    )
    text = completion.choices[0].message.content or "{}"
    obj = parse_json_object(text)
    if obj is None:
        raise ValueError(f"{task}: model did not return JSON")
    return obj
