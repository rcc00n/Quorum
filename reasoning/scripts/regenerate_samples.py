"""Regenerate the three committed dry-run snapshots in docs/examples/ (Vadim's test data for the portal) and the
fictional `spectrum.readings` example beside them.

    cd reasoning && python scripts/regenerate_samples.py              # all four files
    cd reasoning && python scripts/regenerate_samples.py --readings   # only docs/examples/spectrum-readings.sample.json

No credits, no network: every run is a dry run on a fixture day. The partial sample is produced by making the
`frame` task fail once, the way docs/examples/README.md describes, so `status: partial` and `errors` show a
recorded model failure with the run going on. Run it whenever the snapshot shape changes, and say so in the
WEB INTEGRATION CHANGE notice (docs/TEAM_HANDOFF.md on feature/web-portals).

The readings example is the same fixture day with `[frame] readings` switched on for this process only (the committed
config stays "off"). It is not a snapshot and its name keeps it out of the `snapshot*.json` files the portal's CI step
and web/tests/contract.cjs validate: the portal parser rejects `spectrum.readings` until the web side adopts the
interface change in docs/ARCHITECTURE.md § 8 (2026-10-26).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"
sys.path.insert(0, str(ROOT / "reasoning"))

from quorum_reasoning import config, dryrun, graph, llm  # noqa: E402

TOPIC = "russia-ukraine-war"


def write(name: str, snapshot: dict) -> None:
    path = EXAMPLES / name
    content = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()  # the git blob's hash (LF), not the CRLF working copy's
    print(f"{name}: status {snapshot['status']}, {len(snapshot['stories'])} stories, roundup {snapshot['roundup']['count']}, sha256 {digest}")


READINGS_NOTE = (
    "FICTIONAL example of spectrum.readings (docs/ARCHITECTURE.md § 8, interface change 2026-10-26): the dry run on the "
    "fixture day with [frame] readings = \"on\", every model task answered by its deterministic stand-in. Not a snapshot "
    "and not news: the portal parser does not accept spectrum.readings yet, so this file stays out of the snapshot*.json "
    "samples it validates. So that it also shows outlet entries (a flank whose outlets differ), the stand-in labels "
    "minor outlets \"a cost to taxpayers\" here; in an ordinary dry run every outlet of a flank gets one label. "
    "Rebuilt by reasoning/scripts/regenerate_samples.py --readings."
)


def readings_sample() -> dict:
    """The stories' spectra of a flag-on fixture dry run, readings included (no timing fields, so it is reproducible)."""
    real_get, real_frame = config.get, dryrun.frame

    def minor_label(p: dict) -> dict:
        out = real_frame(p)
        return out | {"interpretation_label": "a cost to taxpayers"} if p.get("tier") == "minor" else out

    config.get = lambda section, key, default=None: "on" if (section, key) == ("frame", "readings") else real_get(section, key, default)
    dryrun.frame = minor_label
    try:
        snapshot = graph.run_local(TOPIC, "2026-10-22", dry_run=True)["snapshot"]
    finally:
        config.get, dryrun.frame = real_get, real_frame
    return {
        "_note": READINGS_NOTE,
        "fictional": True,
        "provenance": {key: snapshot["provenance"][key] for key in ("corpus", "model", "fictional")},
        "topic_id": snapshot["topic_id"],
        "edition_date": snapshot["edition_date"],
        "stories": [{"event_id": s["event_id"], "headline": s["headline"], "spectrum": s["spectrum"]} for s in snapshot["stories"]],
    }


def write_readings() -> None:
    path = EXAMPLES / "spectrum-readings.sample.json"
    content = json.dumps(readings_sample(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"{path.name}: sha256 {hashlib.sha256(content.encode('utf-8')).hexdigest()}")


def main() -> int:
    os.environ["QUORUM_DRY_RUN"] = "1"
    os.environ.pop("QUORUM_FIXTURE", None)
    if "--readings" in sys.argv[1:]:
        write_readings()
        return 0
    write("snapshot.sample.json", graph.run_local(TOPIC, "2026-10-22", dry_run=True)["snapshot"])

    os.environ["QUORUM_FIXTURE"] = "usecases/quiet_day"
    write("snapshot.empty-day.sample.json", graph.run_local(TOPIC, "2026-10-22", dry_run=True)["snapshot"])
    os.environ.pop("QUORUM_FIXTURE", None)

    real = llm.json_task

    def failing_frame(task, payload, **kw):
        if task == "frame":
            raise RuntimeError("model route returned HTTP 503")  # the allowlisted public error shape
        return real(task, payload, **kw)

    llm.json_task = failing_frame
    try:
        write("snapshot.partial.sample.json", graph.run_local(TOPIC, "2026-10-22", dry_run=True)["snapshot"])
    finally:
        llm.json_task = real
    write_readings()
    return 0


if __name__ == "__main__":
    sys.exit(main())
