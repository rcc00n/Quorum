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
    llm._env()  # .env may set QUORUM_DRY_RUN; read it before judging (review finding, 2026-10-24)
    if os.getenv("QUORUM_DRY_RUN") == "1":
        return "--model live together with QUORUM_DRY_RUN=1 (shell or .env); unset the variable or drop --model live"
    problem = llm.route_problem()
    if problem:
        return f"--model live with a {problem}"
    if not llm.route_configured():
        return "--model live but no model route is configured (MODEL_BASE_URL and MODEL_API_KEY, or METERLESS_RUNTIME_TOKEN / its alias METERLESS_TOKEN with METERLESS_BASE_URL, which defaults to http://127.0.0.1:8088/v1 when blank, in .env)"
    return None


def live_guard() -> str | None:
    """Why the first live completion must not be sent, or None. On the Meterless route it turns the daemon's H-MEM
    reinjection off and confirms the read-back (`llm.disable_hmem_injection`); the direct NVIDIA route never calls it.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every run.py path that sends completions calls this first: a live
    graph run (`--model live`, or no --model with a configured route), `--test-connection` and `--probe` (not `--models`,
    which sends none, nor `--models --test-connection`, where `--models` wins), always on a configured route (decision in
    `main`; a live graph run only after `checkpoint_problem` found work to send); a failure exits 2 before the graph
    starts or the probe is sent. The setpoint stays false after
    the run. A Meterless base URL that is not loopback is such a failure (decision at `llm.disable_hmem_injection`), so
    "on this daemon" below is always the local one. Why: the chat API has no per-request off switch, so the daemon
    setpoint is the only way to keep earlier answers out of our prompts; `llm.json_task` still rejects any response that
    carries injected memories.
    """
    if not llm.on_meterless():
        return None
    problem = llm.disable_hmem_injection()
    if problem is None:
        print(f"meterless: {llm.HMEM_SETPOINT} read back false (prior-answer injection off on this daemon)", file=sys.stderr)
    return problem


def checkpoint_problem(checkpoint: str | None, rid: str, resume: bool) -> tuple[str | None, bool]:
    """(why the run cannot start, whether it will send any completion), read from the run's checkpoint before anything
    is sent: `graph.run_local`'s own refusals (resume with no checkpoint, a fresh run over an existing one) and a resumed
    thread that already finished (nothing left to run, so no completion goes out). `graph.run_local` still enforces them.

    DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): a live run checks these before `live_guard`, refuses with exit 2
    and the same message `graph.run_local` gives, and skips the setter when the resumed thread has nothing left to run;
    a checkpoint file that does not exist is not created here. Why: review round 4: the machine-wide setter POSTed
    `hmemKnowledge: false` for `--model live --resume` with no checkpoint, which then refused without sending a
    completion (the same defect round 2 fixed for the CLI checks); graph.py is outside this change's files, so the
    checks are mirrored here rather than given to run_local as a hook."""
    path = Path(checkpoint) if checkpoint else None
    if path is None or not path.is_file():
        if resume:
            return f"nothing to resume: no checkpoint for run {rid} in {checkpoint}", False
        return None, True
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        state = graph.builder.compile(checkpointer=SqliteSaver(conn)).get_state({"configurable": {"thread_id": rid}})
    finally:
        conn.close()
    if resume:
        if not state.values:
            return f"nothing to resume: no checkpoint for run {rid} in {checkpoint}", False
        return None, bool(state.next)
    if state.values:
        return f"run {rid} already has a checkpoint in {checkpoint}: pass --resume to continue it, or --attempt N+1 for a fresh run", False
    return None, True


def flagged_calls_note() -> str:
    """The run summary's non-zero ledger flags, each under its own label: ", 2 lane substituted, 1 refused as cache
    replays", or "". Journal rows a resumed run declined to replay are named as such, never as rejections (decision in
    `llm.load_journal`)."""
    flags = (
        (llm.substitution_count(), "lane substituted"),
        (llm.lane_unverified_count(), "lane unverified"),
        (llm.hmem_rejected_count(), "rejected for injected memories"),
        (llm.cache_refused_count(), "refused as cache replays"),
        (llm.replay_refused_count(), "journalled replies not replayed"),
    )
    return "".join(f", {n} {label}" for n, label in flags if n)


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
    ap.add_argument("--seed-journal", action="store_true", help="start the run fresh (no checkpoint) but load this run id's journal first, so identical requests are answered from it (replay) and its rows count in the ledger; for a new attempt seeded from an earlier attempt's journal")
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
            # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the guard runs only when the branch below that actually
            # runs sends a completion (`--probe`, or `--test-connection` unless `--models` wins over it) and only on a
            # configured route; a mixed pair or a missing route exits 2 first and reaches no control request. Why: review
            # round 2: the setter is machine-wide, and it ran for a check that then sent no completion (no token, a
            # mixed pair, `--models --test-connection`).
            if args.probe or (args.test_connection and not args.models):
                problem = llm.route_problem()
                if problem is None and not llm.route_configured():
                    problem = "no model route configured: set MODEL_BASE_URL and MODEL_API_KEY (or METERLESS_*) in .env"
                problem = problem or live_guard()  # decision at live_guard
                if problem:
                    print(f"refusing to run: {problem}", file=sys.stderr)
                    return 2
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
                    if "receipt_id" in r:  # the Meterless route: the pin the runtime accepted and the receipt to check it by
                        verdict = f"SUBSTITUTED by {r['substituted']}" if r.get("substituted") else "lane held"
                        print(f"{'':<13} provider_model {r['provider_model'] or '?'}  routed_model {r['routed_model'] or '?'}  receipt_id {r['receipt_id'] or '?'}  hmem injected {r['hmem_injected']}  {verdict}")
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
    rid = ids.run_id(args.topic, args.date, args.attempt)
    checkpoint = None
    if args.checkpoint or args.resume or not model_dry:
        checkpoint = str(Path(args.out) / "_checkpoints" / f"{rid}.sqlite")
    if args.resume and model_dry:
        print("refusing to run: --resume with a dry model would finish a live run on stand-ins; drop --dry-run / --model dry", file=sys.stderr)
        return 2
    if not model_dry:
        llm._env()  # .env may set QUORUM_DRY_RUN; read it first so the guard runs only when the run will really be live
        if not llm.is_dry_run(False):
            problem, sends = checkpoint_problem(checkpoint, rid, args.resume)  # decision at checkpoint_problem
            if not problem and sends:
                problem = live_guard()  # decision at live_guard: before the graph, so no completion goes out with injection on
            if problem:
                print(f"refusing to run: {problem}", file=sys.stderr)
                return 2
    if args.verbose:
        os.environ["QUORUM_VERBOSE"] = "1"
    on_step = None
    if not args.quiet:
        print_header()
        on_step = lambda rec: print(format_step(rec), flush=True)  # noqa: E731 — progress as each node finishes
    llm.current_run_id = rid
    if not model_dry:
        llm.journal_path = Path(args.out) / "_journal" / f"{rid}.jsonl"  # private: full request payloads and receipts
        if args.resume or args.seed_journal:
            # DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): --seed-journal loads the run id's journal for replay
            # without a checkpoint, so a fresh attempt can be seeded from an earlier attempt's journal (copied under the
            # new run id, with the rows to be redone removed) when the earlier checkpoint holds state that must not be
            # resumed. Why: attempt 3 of 2026-10-24 completed a reviewer pass over gated claims (a bug fixed the same
            # night); resuming it would publish those verdicts, restarting without replay would repay ~1500 calls.
            llm.reset_calls()
            loaded = llm.load_journal(llm.journal_path)
            llm.journal_loaded_for = rid  # plan.run keeps the loaded ledger/replay for this run id even when rows carry an earlier attempt's run_id
            print(f"{'resuming' if args.resume else 'seeding'} {rid}: {loaded} journalled calls restored into the ledger", file=sys.stderr)
    try:
        state = graph.run_local(args.topic, args.date, dry_run=model_dry, corpus=corpus, attempt=args.attempt, on_step=on_step, checkpoint_path=checkpoint, resume=args.resume)
    except llm.RateLimitAbort as exc:  # decision at llm.RATE_LIMIT_ABORT_WINDOW_S
        print(f"refusing to continue: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        if "resume" in str(exc) or "already has a checkpoint" in str(exc):
            print(f"refusing to run: {exc}", file=sys.stderr)
            return 2
        raise
    if args.resume and store.versions(Path(args.out), args.topic, args.date) and state.get("snapshot") and any(
        store.load(Path(args.out), args.topic, args.date, v).get("run_id") == rid for v in store.versions(Path(args.out), args.topic, args.date)
    ):
        print(f"run {rid} had already finished and published; nothing to do (its version is in the store)", file=sys.stderr)
        return 0
    snapshot = state["snapshot"]
    out, version = store.publish(snapshot, Path(args.out), ledger=llm.calls)
    ledger = ledger_path(Path(args.out), args.topic, args.date, version)
    if not args.quiet:
        print()
        prov = snapshot["provenance"]
        print(f"corpus: {state['corpus']}; model: {'stand-ins' if llm.is_dry_run(state['dry_run']) else llm.model_name()}; fact-checker: {prov['fact_checker_model']}")
        if prov["model_calls"]:
            answered = ", ".join(f"{m} ×{n}" for m, n in prov["answered_by"].items())
            print(f"model calls: {prov['model_calls']} ({prov['model_errors']} failed{flagged_calls_note()}); answered by: {answered}")
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
