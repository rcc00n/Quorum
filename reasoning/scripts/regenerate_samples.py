"""Regenerate the three committed dry-run snapshots in docs/examples/ (Vadim's test data for the portal).

    cd reasoning && python scripts/regenerate_samples.py

No credits, no network: every run is a dry run on a fixture day. The partial sample is produced by making the
`frame` task fail once, the way docs/examples/README.md describes, so `status: partial` and `errors` show a
recorded model failure with the run going on. Run it whenever the snapshot shape changes, and say so in the
WEB INTEGRATION CHANGE notice (docs/TEAM_HANDOFF.md on feature/web-portals).
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

from quorum_reasoning import graph, llm  # noqa: E402

TOPIC = "russia-ukraine-war"


def write(name: str, snapshot: dict) -> None:
    path = EXAMPLES / name
    content = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()  # the git blob's hash (LF), not the CRLF working copy's
    print(f"{name}: status {snapshot['status']}, {len(snapshot['stories'])} stories, roundup {snapshot['roundup']['count']}, sha256 {digest}")


def main() -> int:
    os.environ["QUORUM_DRY_RUN"] = "1"
    os.environ.pop("QUORUM_FIXTURE", None)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
