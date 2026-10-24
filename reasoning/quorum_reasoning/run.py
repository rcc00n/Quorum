"""CLI: one run for one topic and edition day.

    python -m quorum_reasoning.run --topic russia-ukraine-war --date 2026-10-22 --dry-run
    python -m quorum_reasoning.run --date 2026-10-22 --model live --corpus fixture   # try the prompts, no Zetaris needed
    python -m quorum_reasoning.run --date 2026-10-23 --model live --corpus zetaris   # the real thing
    python -m quorum_reasoning.run --models         # routes the hotspot offers; pin Nemotron ones in .env
    python -m quorum_reasoning.run --test-connection # one completion per lane, shows which model answered
    python -m quorum_reasoning.run --probe           # one real task: raw reply and token counts (is thinking off?)
    python -m quorum_reasoning.run --mermaid        # the graph as Mermaid, for docs/ARCHITECTURE.md

    python -m quorum_reasoning.run --list            # every stored snapshot version under --out
    python -m quorum_reasoning.run --show --topic russia-ukraine-war --date 2026-10-22 [--version 2]

Two axes: --model dry|live (dry = deterministic stand-ins, no credits; also forced by QUORUM_DRY_RUN=1 or a
missing key) and --corpus fixture|zetaris. --dry-run is the shortcut for --model dry --corpus fixture.
Stores the snapshot as the next immutable version under <out>/<topic>/<date>/v<N>.json (store.py), refreshes
latest.json, writes the private call ledger beside it, and prints the trace.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import graph, ids, llm, store


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


def ledger_path(out_dir: Path, topic: str, date: str, version: int) -> Path | None:
    """Where the store put the run's private call ledger (task, lane, route, answering model, HTTP status,
    finish_reason, tokens, attempts, receipt id, error), or None when the run made no live call."""
    path = store.day_dir(out_dir, topic, date) / f"v{version}.ledger.json"
    return path if path.is_file() else None


def print_listing(out_dir: Path) -> None:
    rows = store.listing(out_dir)
    if not rows:
        print(f"no snapshots under {out_dir}")
        return
    print(f"{'topic':<22}{'date':<12}{'v':>3}  {'status':<8}{'stories':>7}  {'fictional':<9} {'published_at':<21} sha256")
    for r in rows:
        print(f"{r['topic_id']:<22}{r['edition_date']:<12}{r['version']:>3}  {r['status']:<8}{r['stories']:>7}  {str(r['fictional']):<9} {r['published_at'] or '-':<21} {r['sha256']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Quorum reasoning graph for one topic and day.")
    ap.add_argument("--topic", default="russia-ukraine-war")
    ap.add_argument("--date", default="2026-10-22", help="edition date, YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="shortcut for --model dry --corpus fixture")
    ap.add_argument("--model", choices=["dry", "live"], default=None, help="dry: stand-ins, no credits; live: the route in .env")
    ap.add_argument("--corpus", choices=["fixture", "zetaris"], default=None, help="where the day's documents come from")
    ap.add_argument("--fixture", default=None, help="fixture day for --corpus fixture: sample_day (default) or e.g. usecases/quiet_day")
    ap.add_argument("--out", default="snapshots", help="store root: <out>/<topic>/<date>/v<N>.json")
    ap.add_argument("--list", action="store_true", help="list every stored snapshot version under --out and exit")
    ap.add_argument("--show", action="store_true", help="print one stored snapshot (--topic, --date, optional --version) and exit")
    ap.add_argument("--version", type=int, default=None, help="with --show: the version to print (default: newest)")
    ap.add_argument("--checkpoint", action="store_true", help="checkpoint every node into <out>/_checkpoints/<run_id>.sqlite (always on with --model live)")
    ap.add_argument("--resume", action="store_true", help="continue the run <date>-<topic>-<attempt> from its last completed node (needs the checkpoint file)")
    ap.add_argument("--attempt", type=int, default=1, help="attempt number in the run id (default 1); a fresh live run of the same day after a finished one needs 2, 3, …")
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
    if args.list:
        print_listing(Path(args.out))
        return 0
    if args.show:
        try:
            snap = store.load(Path(args.out), args.topic, args.date, args.version)
        except FileNotFoundError as exc:
            print(f"not found: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(snap, ensure_ascii=False, indent=2))
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
    rid = ids.run_id(args.topic, args.date, args.attempt)
    llm.current_run_id = rid
    checkpoint = None
    if args.checkpoint or args.resume or not model_dry:
        checkpoint = str(Path(args.out) / "_checkpoints" / f"{rid}.sqlite")
    if not model_dry:
        llm.journal_path = Path(args.out) / "_journal" / f"{rid}.jsonl"  # private: full request payloads and receipts
        if args.resume:
            llm.reset_calls()
            loaded = llm.load_journal(llm.journal_path)
            print(f"resuming {rid}: {loaded} journalled calls restored into the ledger", file=sys.stderr)
    try:
        state = graph.run_local(args.topic, args.date, dry_run=model_dry, corpus=corpus, attempt=args.attempt, on_step=on_step, checkpoint_path=checkpoint, resume=args.resume)
    except ValueError as exc:
        if "resume" in str(exc):
            print(f"refusing to run: {exc}", file=sys.stderr)
            return 2
        raise
    snapshot = state["snapshot"]
    out, version = store.publish(snapshot, Path(args.out), ledger=llm.calls)
    ledger = ledger_path(Path(args.out), args.topic, args.date, version)
    if not args.quiet:
        print()
        prov = snapshot["provenance"]
        print(f"corpus: {state['corpus']}; model: {'stand-ins' if llm.is_dry_run(state['dry_run']) else llm.model_name()}; fact-checker: {prov['fact_checker_model']}")
        if prov["model_calls"]:
            answered = ", ".join(f"{m} ×{n}" for m, n in prov["answered_by"].items())
            print(f"model calls: {prov['model_calls']} ({prov['model_errors']} failed); answered by: {answered}")
        print(f"status: {snapshot['status']}; stories: {len(snapshot['stories'])}; roundup: {snapshot['roundup']['count']}; errors: {len(snapshot['errors'])}")
        print(f"summary ({snapshot['summary_source']}): {snapshot['summary']}")
        print(f"snapshot: {out} (version {version}, published_at {snapshot['published_at']}, sha256 {store.sha256_of(out)})")
        if ledger:
            print(f"ledger (private, not part of the snapshot): {ledger}")
        if checkpoint:
            print(f"checkpoint (private): {checkpoint}; journal: {llm.journal_path or '-'}")
    return 0 if snapshot["status"] != "partial" else 2


if __name__ == "__main__":
    sys.exit(main())
