"""The portal's producer-shaped sidecar fixture is what this builder writes (2026-10-27, Anastasia / Claude Code).

DECISION(2026-10-27, Anastasia/Claude Code): backend/portal/fixtures/reasoning-demo/snapshot.sample.sidecar.json holds
the bytes `build_sidecar` + `serialize` write for the bundled (fictional) sample, with corpus_as_of_utc = the window's
start and producer-config.sample.toml's sha256 as the config hash. This test regenerates them in reasoning's own suite
(CI combined-python, the reasoning venv), so a change to the builder or the serializer (keys, key order, values taken
from the snapshot, JSON encoding) fails here before a hand-over; the portal binds the same bytes in
backend/portal/test_reasoning_sidecar.py. Only these two functions are pinned: the CLI refuses a fictional snapshot and
hashes the real reasoning.toml. Why: the portal suite cannot load this script, since a release archive ships
backend/ and deploy/ only and the VPS upgrade runs `manage.py test portal` there. To change the builder on purpose,
regenerate the fixture by the recipe in its README and tell the portal owner (Issue #2).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPT = HERE.parents[1] / "scripts" / "edition_sidecar.py"
FIXTURES = HERE.parents[2] / "backend" / "portal" / "fixtures" / "reasoning-demo"


def _load_script():
    spec = importlib.util.spec_from_file_location("edition_sidecar_portal_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_portal_fixture_is_what_the_builder_writes():
    es = _load_script()
    raw = (FIXTURES / "snapshot.sample.json").read_bytes()
    p = json.loads(raw)
    committed = (FIXTURES / "snapshot.sample.sidecar.json").read_bytes()
    config = (FIXTURES / "producer-config.sample.toml").read_bytes()
    commit = json.loads(committed)["producer"]["commit"]
    rebuilt = es.serialize(es.build_sidecar(raw, p, p["window"]["start"], commit, hashlib.sha256(config).hexdigest()))
    assert rebuilt == committed, (
        "build_sidecar/serialize no longer write the portal's fixture: regenerate "
        "backend/portal/fixtures/reasoning-demo/snapshot.sample.sidecar.json by the recipe in its README "
        "and tell the portal owner (Issue #2)"
    )
