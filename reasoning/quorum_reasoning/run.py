"""CLI: one run for one topic and edition day.

    python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run
    python -m quorum_reasoning.run --date 2026-10-22 --model live --corpus fixture   # try the prompts, no Zetaris needed
    python -m quorum_reasoning.run --date 2026-10-23 --model live --corpus zetaris   # the real thing
    python -m quorum_reasoning.run --mermaid        # the graph as Mermaid, for docs/ARCHITECTURE.md

Two axes: --model dry|live (dry = deterministic stand-ins, no credits; also forced by QUORUM_DRY_RUN=1 or a
missing key) and --corpus fixture|zetaris. --dry-run is the shortcut for --model dry --corpus fixture.
Writes the snapshot to <out>/<topic>/<date>.json and prints the trace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import graph, llm


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
    ap.add_argument("--dry-run", action="store_true", help="shortcut for --model dry --corpus fixture")
    ap.add_argument("--model", choices=["dry", "live"], default=None, help="dry: stand-ins, no credits; live: the route in .env")
    ap.add_argument("--corpus", choices=["fixture", "zetaris"], default=None, help="where the day's documents come from")
    ap.add_argument("--out", default="snapshots", help="directory for the snapshot JSON")
    ap.add_argument("--mermaid", action="store_true", help="print the graph as Mermaid and exit")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.mermaid:
        print(graph.mermaid())
        return 0

    model_dry = args.dry_run if args.model is None else args.model == "dry"
    corpus = args.corpus or ("fixture" if (args.dry_run or model_dry) else "zetaris")
    if args.model == "live" and llm.is_dry_run(False):
        print("no model route configured (MODEL_BASE_URL / MODEL_API_KEY in .env, or QUORUM_DRY_RUN=1 is set): running dry", file=sys.stderr)
    state = graph.run_local(args.topic, args.date, dry_run=model_dry, corpus=corpus)
    snapshot = state["snapshot"]
    out = Path(args.out) / args.topic / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.quiet:
        print_trace(state["steps"])
        print()
        print(f"corpus: {state['corpus']}; model: {'stand-ins' if llm.is_dry_run(state['dry_run']) else llm.model_name()}")
        print(f"status: {snapshot['status']}; stories: {len(snapshot['stories'])}; roundup: {snapshot['roundup']['count']}; errors: {len(snapshot['errors'])}")
        print(f"summary: {snapshot['summary']}")
        print(f"snapshot: {out}")
    return 0 if snapshot["status"] != "partial" else 2


if __name__ == "__main__":
    sys.exit(main())
