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


def _route(which: str = "default") -> tuple[str, str, str]:
    _env()
    base = os.getenv("MODEL_BASE_URL") or os.getenv("METERLESS_BASE_URL") or ""
    key = os.getenv("MODEL_API_KEY") or os.getenv("METERLESS_RUNTIME_TOKEN") or ""
    model = os.getenv("NEMOTRON_MODEL") or os.getenv("METERLESS_MODEL") or "meterless/auto"
    return base.strip(), key.strip(), model.strip()


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

    Every task has a dry-run twin in dryrun.py with the same input and output shape.
    """
    if is_dry_run(dry_run):
        return getattr(dryrun, task)(payload)

    from openai import OpenAI  # imported lazily: not needed in dry run

    base, key, model = _route(which)
    client = OpenAI(base_url=base, api_key=key)
    temperature = float(config.get("models", "temperature", 0.1))
    completion = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": _prompt(task)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        extra_headers={"X-Quorum-Task": task},
    )
    text = completion.choices[0].message.content or "{}"
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"{task}: model did not return JSON")
    return json.loads(text[start : end + 1])
