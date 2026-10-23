"""CLI: one run for one topic and edition day.

    python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run
    python -m quorum_reasoning.run --mermaid        # the graph as Mermaid, for docs/ARCHITECTURE.md

Writes the snapshot to <out>/<topic>/<date>.json and prints the trace. With --dry-run (or QUORUM_DRY_RUN=1,
or no model key in .env) no credits are spent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import graph


def print_trace(steps: list[dict], file=sys.stdout) -> None:
    print(f"{'node':<18}{'it':>3}  {'event':<14}{'ms':>6}  decision — reason", file=file)
    for s in steps:
        ev = (s["event_id"] or "-")[:12]
        line = f"{s['node']:<18}{s['iteration']:>3}  {ev:<14}{s['duration_ms']:>6}  {s['decision']}"
        if s["reason"]:
            line += f" — {s['reason']}"
        print(line, file=file)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Quorum reasoning graph for one topic and day.")
    ap.add_argument("--topic", default="russia-ukraine-war")
    ap.add_argument("--date", default="2026-10-22", help="edition date, YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="deterministic stand-ins instead of model calls")
    ap.add_argument("--out", default="snapshots", help="directory for the snapshot JSON")
    ap.add_argument("--mermaid", action="store_true", help="print the graph as Mermaid and exit")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.mermaid:
        print(graph.mermaid())
        return 0

    state = graph.run_local(args.topic, args.date, dry_run=args.dry_run)
    snapshot = state["snapshot"]
    out = Path(args.out) / args.topic / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.quiet:
        print_trace(state["steps"])
        print()
        print(f"status: {snapshot['status']}; stories: {len(snapshot['stories'])}; roundup: {snapshot['roundup']['count']}; errors: {len(snapshot['errors'])}")
        print(f"summary: {snapshot['summary']}")
        print(f"snapshot: {out}")
    return 0 if snapshot["status"] != "partial" else 2


if __name__ == "__main__":
    sys.exit(main())
