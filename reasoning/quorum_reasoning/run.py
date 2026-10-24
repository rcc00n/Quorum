"""CLI: one run for one topic and edition day.

    python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run
    python -m quorum_reasoning.run --date 2026-10-22 --model live --corpus fixture   # try the prompts, no Zetaris needed
    python -m quorum_reasoning.run --date 2026-10-23 --model live --corpus zetaris   # the real thing
    python -m quorum_reasoning.run --models         # routes the hotspot offers; pin Nemotron ones in .env
    python -m quorum_reasoning.run --test-connection # one completion per lane, shows which model answered
    python -m quorum_reasoning.run --probe           # one real task: raw reply and token counts (is thinking off?)
    python -m quorum_reasoning.run --mermaid        # the graph as Mermaid, for docs/ARCHITECTURE.md

Two axes: --model dry|live (dry = deterministic stand-ins, no credits; also forced by QUORUM_DRY_RUN=1 or a
missing key) and --corpus fixture|zetaris. --dry-run is the shortcut for --model dry --corpus fixture.
Writes the snapshot to <out>/<topic>/<date>.json and prints the trace.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import graph, llm


def format_step(s: dict) -> str:
    ev = (s["event_id"] or "-")[:12]
    line = f"{s['node']:<18}{s['iteration']:>3}  {ev:<14}{s['duration_ms']:>6}  {s['decision']}"
    if s["reason"]:
        line += f" — {s['reason']}"
    return line


def print_header(file=sys.stdout) -> None:
    print(f"{'node':<18}{'it':>3}  {'event':<14}{'ms':>6}  decision — reason", file=file, flush=True)


def print_trace(steps: list[dict], file=sys.stdout) -> None:
    print_header(file)
    for s in steps:
        print(format_step(s), file=file)


def live_mode_problem() -> str | None:
    """Why `--model live` cannot run, or None. Live mode fails closed: it never falls back to stand-ins.

    DECISION(2026-10-24, Yelysei Shkirpan/Claude Code): a live run with no route configured, or with
    QUORUM_DRY_RUN=1 set, exits 2 before the graph starts instead of warning and running dry. Why: a dry run
    labelled live is the one outcome that can be mistaken for integration evidence (Vadim's finding in
    NVIDIA-FIRST-01); the explicit dry switch and the explicit live flag contradicting each other is an
    error to fix, not a preference to resolve silently.
    """
    if os.getenv("QUORUM_DRY_RUN") == "1":
        return "--model live together with QUORUM_DRY_RUN=1; unset the variable or drop --model live"
    if not llm.route_configured():
        return "--model live but no model route is configured (MODEL_BASE_URL and MODEL_API_KEY, or METERLESS_BASE_URL and METERLESS_RUNTIME_TOKEN, in .env)"
    return None


def write_ledger(out_dir: Path, topic: str, date: str) -> Path | None:
    """The per-run call ledger, next to the snapshot and never inside it: task, lane, route, answering model,
    HTTP status, finish_reason, tokens, attempts, receipt id, error. Private evidence for the output directory."""
    if not llm.calls:
        return None
    path = out_dir / topic / f"{date}.ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"topic_id": topic, "edition_date": date, "calls": llm.calls}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Quorum reasoning graph for one topic and day.")
    ap.add_argument("--topic", default="russia-ukraine-war")
    ap.add_argument("--date", default="2026-10-22", help="edition date, YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="shortcut for --model dry --corpus fixture")
    ap.add_argument("--model", choices=["dry", "live"], default=None, help="dry: stand-ins, no credits; live: the route in .env")
    ap.add_argument("--corpus", choices=["fixture", "zetaris"], default=None, help="where the day's documents come from")
    ap.add_argument("--fixture", default=None, help="fixture day for --corpus fixture: sample_day (default) or e.g. usecases/quiet_day")
    ap.add_argument("--out", default="snapshots", help="directory for the snapshot JSON")
    ap.add_argument("--mermaid", action="store_true", help="print the graph as Mermaid and exit")
    ap.add_argument("--models", action="store_true", help="list the routes the configured hotspot offers (GET /v1/models) and exit")
    ap.add_argument("--test-connection", action="store_true", help="one small completion per lane (default, fact_checker) and exit")
    ap.add_argument("--probe", action="store_true", help="one real stance task on the default lane: raw reply, token counts, latency — shows whether the model still thinks aloud")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="also print every live model call as it happens (task, lane, model that answered, ms)")
    args = ap.parse_args(argv)

    if args.mermaid:
        print(graph.mermaid())
        return 0
    if args.models or args.test_connection or args.probe:
        try:
            if args.probe:
                r = llm.probe()
                print(f"route {r['route']}  answered by {r['answered_by'] or '?'}  {r['ms']} ms  tokens in>out {r['tokens_in']}>{r['tokens_out']}  reply {r['reply_chars']} chars")
                print(f"parsed: {r['parsed']}")
                print("reply head:")
                print(r["reply_head"])
            elif args.models:
                for m in llm.list_models():
                    print(m + ("   <- Nemotron" if "nemotron" in m.lower() else ""))
            else:
                for lane in ("default", "fact_checker"):
                    r = llm.test_connection(lane)
                    print(f"{r['lane']:<13} route {r['route']}  answered by {r['answered_by'] or '?'}  reply: {r['reply']!r}")
        except Exception as exc:  # noqa: BLE001 — a CLI check reports, it does not trace
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.fixture:
        os.environ["QUORUM_FIXTURE"] = args.fixture
    model_dry = args.dry_run if args.model is None else args.model == "dry"
    if model_dry:
        os.environ["QUORUM_DRY_RUN"] = "1"  # the explicit dry switch, so every module (trace model names included) agrees
    corpus = args.corpus or ("fixture" if (args.dry_run or model_dry) else "zetaris")
    if args.model == "live":
        problem = live_mode_problem()
        if problem:
            print(f"refusing to run: {problem}", file=sys.stderr)
            return 2
    if args.verbose:
        os.environ["QUORUM_VERBOSE"] = "1"
    on_step = None
    if not args.quiet:
        print_header()
        on_step = lambda rec: print(format_step(rec), flush=True)  # noqa: E731 — progress as each node finishes
    state = graph.run_local(args.topic, args.date, dry_run=model_dry, corpus=corpus, on_step=on_step)
    snapshot = state["snapshot"]
    out = Path(args.out) / args.topic / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    ledger = write_ledger(Path(args.out), args.topic, args.date)
    if not args.quiet:
        print()
        prov = snapshot["provenance"]
        print(f"corpus: {state['corpus']}; model: {'stand-ins' if llm.is_dry_run(state['dry_run']) else llm.model_name()}; fact-checker: {prov['fact_checker_model']}")
        if prov["model_calls"]:
            answered = ", ".join(f"{m} ×{n}" for m, n in prov["answered_by"].items())
            print(f"model calls: {prov['model_calls']} ({prov['model_errors']} failed); answered by: {answered}")
        print(f"status: {snapshot['status']}; stories: {len(snapshot['stories'])}; roundup: {snapshot['roundup']['count']}; errors: {len(snapshot['errors'])}")
        print(f"summary ({snapshot['summary_source']}): {snapshot['summary']}")
        print(f"snapshot: {out}")
        if ledger:
            print(f"ledger (private, not part of the snapshot): {ledger}")
    return 0 if snapshot["status"] != "partial" else 2


if __name__ == "__main__":
    sys.exit(main())
