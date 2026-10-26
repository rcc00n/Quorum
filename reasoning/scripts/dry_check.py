"""Dry check for one topic-day: the whole graph with stand-ins on the day's real corpus, counting the model calls a
live run would make. No model call of any kind is sent.

    python -X utf8 scripts/dry_check.py --topic climate-policy --date 2026-10-26 --out <scratch store> [--report r.json]
    python -X utf8 scripts/dry_check.py --topic russia-ukraine-war --date 2026-10-22 --corpus fixture --out <scratch>
    python -X utf8 scripts/dry_check.py --list-topics     # collection's `topics` table: {"topics", "filtered", "skipped"}

The count is per task and lane: `default` is the fast lane (Lightning), `fact_checker` and `reviewer` are the Ultra
lanes. It is an estimate: the stand-ins answer differently from the model (event keys, claims, rubric facts), so a
live run makes more or fewer calls; `run_editions.py` uses it to share topics between keys and rotates keys when a
run drains one anyway. `--out` is a scratch store for the stand-in snapshot, never the live store.

`--env-file` loads a `.env` (Zetaris credentials for `--corpus zetaris`) without overriding the environment; model
credentials are blanked first, so the file cannot give this process a model route. Nothing from it is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

REASONING = Path(__file__).resolve().parents[1]
FAST_LANES = ("default",)
ULTRA_LANES = ("fact_checker", "reviewer")
TOPIC_RULE = "^[a-z0-9][a-z0-9-]{0,63}$"  # printed in messages; the rule itself is tools/corpus._TOPIC_ID
# Model credentials the dry check must never hold (llm._route_family reads exactly these).
MODEL_CREDENTIALS = ("MODEL_API_KEY", "METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN")
# The llm attributes estimate() replaces (decision at _isolate); a rename in llm.py must fail the check, not void it.
LLM_SEAMS = ("_create", "_client", "disable_hmem_injection", "json_task")


class LiveCallRefused(RuntimeError):
    pass


def _refuse(*_a: Any, **_k: Any) -> Any:
    raise LiveCallRefused("dry check: a live model or control-plane call was attempted and refused")


def write_json_atomic(path: Path, obj: Any) -> None:
    """Temp file in the same folder, then os.replace: a reader sees the old file or the new one, never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _isolate(env_file: str | None, blank: list[str]) -> None:
    """Forces the dry model before anything is imported: QUORUM_DRY_RUN=1 and every model credential blank.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the dry check blanks MODEL_API_KEY, the Meterless tokens and
    every key name it is given before it loads any .env (load_dotenv never overrides a variable that is present, even
    empty), on top of `--model dry`, and replaces `llm._create`, `llm._client` and `llm.disable_hmem_injection` with a
    refusal; a missing seam (LLM_SEAMS) fails the check instead of leaving the patch a no-op. Why: the estimate runs on
    the owner's machine next to the real keys; with no route the graph is dry by construction, so not even a bug in the
    dry switch can send a paid call or touch the Nightshift control plane."""
    os.environ["QUORUM_DRY_RUN"] = "1"
    for name in (*MODEL_CREDENTIALS, *blank):
        os.environ[name] = ""
    if env_file:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    if str(REASONING) not in sys.path:
        sys.path.insert(0, str(REASONING))


# the same as run_editions.WINDOWS_DEVICE (decisions at run_editions.topic_id_problem; a test pins both scripts)
WINDOWS_DEVICE = re.compile(r"^(?:con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])$", re.IGNORECASE)


def topic_id_problem(topic: Any) -> str | None:
    """Why `topic` cannot be checked, or None: the shared topic-id rule, then no Windows device name."""
    from quorum_reasoning.tools.corpus import _TOPIC_ID

    if not isinstance(topic, str) or _TOPIC_ID.fullmatch(topic) is None:
        return f"not a topic id by the shared rule {TOPIC_RULE}"
    if WINDOWS_DEVICE.fullmatch(topic):
        return "a Windows reserved device name (con, prn, aux, nul, com0-9, lpt0-9): as a report or store name it opens a device"
    return None


def topic_id_ok(topic: Any) -> bool:
    """The shared topic-id rule and no Windows device name (decisions at run_editions.topic_id_problem)."""
    return topic_id_problem(topic) is None


def list_topics() -> dict[str, Any]:
    """collection's `topics` table through Zetaris (read-only SELECTs): {"topics": [ids], "filtered": bool, "skipped":
    [{"id", "reason"}]}. A row whose id breaks the shared rule is listed under skipped, never dropped silently.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the listing first asks for active rows in collection order
    (`WHERE active ORDER BY created_at, id`, as collectors/common.load_topics reads them) and, when Zetaris refuses
    that, falls back to every row in the order Zetaris returns them with "filtered": false; the runner then plans
    `--topics all` but refuses it with --live. Why: on 2026-10-26 Zetaris exposes only id, name and query_terms of
    topics (HTTP 400 on `active` and `created_at`), so retired rows and the order are invisible; the first query
    starts working once collection registers both columns (ask in Issue #2), with no change here. Two queries at most."""
    from quorum_reasoning.tools import corpus

    db = corpus._zetaris_db()
    try:
        rows = corpus._run_sql(f"SELECT id FROM {db}.topics WHERE active ORDER BY created_at, id", 1000)
        filtered = True
    except Exception:  # noqa: BLE001 — the columns are not registered (HTTP 400); a second failure below is raised
        rows = corpus._run_sql(f"SELECT id FROM {db}.topics", 1000)
        filtered = False
    topics: list[str] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        tid = str((row or {}).get("id") or "").strip()
        problem = topic_id_problem(tid)
        if problem is None:
            if tid not in topics:
                topics.append(tid)
        else:
            skipped.append({"id": tid[:64], "reason": f"{problem} ({len(tid)} characters)"})
    return {"topics": topics, "filtered": filtered, "skipped": skipped}


def estimate(topic: str, date: str, out: Path, corpus: str, fixture: str | None) -> dict[str, Any]:
    from quorum_reasoning import llm, run, store

    missing = [name for name in LLM_SEAMS if not callable(getattr(llm, name, None))]
    if missing:
        raise RuntimeError(f"dry check: llm.{', llm.'.join(missing)} not found; the refusal seams no longer match llm.py")
    llm._create = _refuse  # type: ignore[assignment]  # decision at _isolate
    llm._client = _refuse  # type: ignore[assignment]
    llm.disable_hmem_injection = _refuse  # type: ignore[assignment]
    counts: Counter[tuple[str, str]] = Counter()
    original = llm.json_task

    def counting(task: str, payload: dict[str, Any], *, dry_run: bool, which: str = "default") -> dict[str, Any]:
        counts[(task, which)] += 1
        return original(task, payload, dry_run=True, which=which)

    llm.json_task = counting  # type: ignore[assignment]  # every node calls llm.json_task by attribute
    before = store.versions(out, topic, date)
    argv = ["--topic", topic, "--date", date, "--model", "dry", "--corpus", corpus, "--out", str(out)]
    if fixture:
        argv += ["--fixture", fixture]
    rc = run.main(argv)
    after = store.versions(out, topic, date)
    snap = store.load(out, topic, date) if after and after != before else None
    by_lane: Counter[str] = Counter()
    by_task: Counter[str] = Counter()
    for (task, lane), n in counts.items():
        by_lane[lane] += n
        by_task[task] += n
    fast = sum(by_lane[lane] for lane in FAST_LANES)
    ultra = sum(by_lane[lane] for lane in ULTRA_LANES)
    return {
        "topic": topic,
        "date": date,
        "corpus": corpus,
        "exit_code": rc,
        "snapshot_status": snap.get("status") if snap else None,
        "version": snap.get("version") if snap else None,
        "stories": len(snap.get("stories") or []) if snap else None,
        "roundup": (snap.get("roundup") or {}).get("count") if snap else None,
        "calls": {"total": fast + ultra + sum(n for lane, n in by_lane.items() if lane not in FAST_LANES + ULTRA_LANES),
                  "fast": fast, "ultra": ultra, "by_lane": dict(by_lane), "by_task": dict(sorted(by_task.items()))},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dry check: count the model calls a live run of one topic-day would make (no model call).")
    ap.add_argument("--topic")
    ap.add_argument("--date", help="edition date, YYYY-MM-DD")
    ap.add_argument("--out", help="scratch store for the stand-in snapshot (never the live store)")
    ap.add_argument("--corpus", choices=["zetaris", "fixture"], default="zetaris")
    ap.add_argument("--fixture", default=None, help="with --corpus fixture: the bundled day (default sample_day)")
    ap.add_argument("--report", default=None, help="write the estimate as JSON to this file (atomically)")
    ap.add_argument("--env-file", default=None, help="a .env to load without overriding the environment (model credentials stay blank)")
    ap.add_argument("--blank", default="", help="comma-separated extra variable names to blank (the runner passes its key names)")
    ap.add_argument("--list-topics", action="store_true", help="print the topic ids of collection's topics table as JSON and exit")
    args = ap.parse_args(argv)
    _isolate(args.env_file, [n for n in args.blank.split(",") if n.strip()])

    if args.list_topics:
        try:
            print(json.dumps(list_topics()))
        except Exception as exc:  # noqa: BLE001 — a CLI check reports
            print(f"listing topics failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return 0
    if not (args.topic and args.date and args.out):
        ap.error("--topic, --date and --out are required (or --list-topics)")
    problem = topic_id_problem(args.topic)
    if problem:
        ap.error(f"--topic is {problem}")
    out = Path(args.out)
    if (out / "_journal").exists() or (out / "_checkpoints").exists():
        print(f"refusing to run: {out} holds live runs (_journal/_checkpoints); a dry check writes stand-in snapshots to a scratch store only", file=sys.stderr)
        return 2
    try:
        report = estimate(args.topic, args.date, out, args.corpus, args.fixture)
    except Exception as exc:  # noqa: BLE001 — reported to the runner, which marks the topic failed
        report = {"topic": args.topic, "date": args.date, "corpus": args.corpus, "error": f"{type(exc).__name__}: {exc}"[:300]}
    if args.report:
        write_json_atomic(Path(args.report), report)
    calls = report.get("calls")
    if calls:
        print(f"dry check {args.topic} {args.date}: {calls['total']} model calls ({calls['fast']} fast lane, {calls['ultra']} Ultra), snapshot {report['snapshot_status']}", file=sys.stderr)
        return 0
    print(f"dry check {args.topic} {args.date} failed: {report.get('error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
