"""Loads config/reasoning.toml once. Nothing in here is a product decision; the file is."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "reasoning.toml"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    with _CONFIG_PATH.open("rb") as fh:
        return tomllib.load(fh)


def get(section: str, key: str, default: Any = None) -> Any:
    return load().get(section, {}).get(key, default)
