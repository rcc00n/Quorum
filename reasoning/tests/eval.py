"""Evaluation of the reasoning graph against real claims (fixtures/eval/).

Runs the graph over the eval days, matches each expected claim against the claims the run extracted, and
prints, before anything else: false confirmed, missed confirmed, the disputed rate, and events above the
bar vs expected. Then a confusion matrix of expected vs actual status.

Dry run is the default and is what CI runs: deterministic stand-ins, no credits, no network. It measures the
pipeline's mechanics (clustering, extraction plumbing, the rule layer on word-overlap stances), not the
model's judgment — see fixtures/eval/README.md for what only a live run can measure.

    python tests/eval.py                 # dry run (the default)
    python tests/eval.py --live ...      # refuses without --confirm-credits; prints the model-call estimate first
    python -m pytest tests/eval.py       # the pytest smoke test on the dry run

DECISION(2026-10-23, Yelysei Shkirpan/Claude Code): the eval injects each day's documents by replacing
plan.load_documents for the duration of the run instead of adding a fixture-path switch to tools/corpus.py.
Why: the eval must not change production code paths, and the plan node already accepts any document list.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from quorum_reasoning import graph
from quorum_reasoning.nodes import plan
from quorum_reasoning.state import DocRef
from quorum_reasoning.text import containment

EVAL_DIR = Path(__file__).resolve().parent.parent / "quorum_reasoning" / "fixtures" / "eval"
STATUSES = ("confirmed", "disputed", "unverified")
ACTUALS = STATUSES + ("not_extracted",)
MATCH_THRESHOLD = 0.5  # share of one claim's tokens found in the other, either direction

TOPIC = "russia-ukraine-war"


def load_days() -> list[dict]:
    days = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((EVAL_DIR / "days").glob("*.json"))]
    if not days:
        raise SystemExit(f"no eval days in {EVAL_DIR / 'days'}")
    return days


def load_claims() -> list[dict]:
    return json.loads((EVAL_DIR / "claims.json").read_text(encoding="utf-8"))["claims"]


def docrefs(day: dict) -> list[DocRef]:
    return [DocRef(**{k: v for k, v in d.items() if k != "topic_id"}) for d in day["documents"]]


def run_day(day: dict, *, dry_run: bool) -> dict:
    """One graph run with the day's documents injected in place of the corpus loader."""
    docs = docrefs(day)
    original = plan.load_documents
    plan.load_documents = lambda topic_id, edition_date, **kw: list(docs)  # noqa: ARG005
    try:
        return graph.run_local(TOPIC, day["edition_date"], dry_run=dry_run)
    finally:
        plan.load_documents = original


def match(expected_text: str, run_claims: list[dict]) -> dict | None:
    """The run's claim that best matches the expected claim's wording, or None."""
    best, best_score = None, 0.0
    for c in run_claims:
        score = max(containment(expected_text, c["text"]), containment(c["text"], expected_text))
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= MATCH_THRESHOLD else None


def estimate_model_calls(days: list[dict]) -> int:
    """Upper-bound estimate for a live run, from the shapes that drive the call count."""
    total = 0
    for day in days:
        n = len(day["documents"])
        pairs = n * (n - 1) // 2  # worst case: every pair lands in the borderline band
        events = n  # worst case: no merges
        claims = min(2 * n, 10 * events)  # the extractor caps at 10 per event
        stance = claims * n * 2 * 2  # claims x candidate docs x 2 rounds x (researcher + fact-checker)
        total += pairs + events * 2 + stance + events * 3 + 2  # + score/extract, frame/write/roundup, summary/critique margin
    return total


def evaluate(*, dry_run: bool = True) -> dict:
    days = load_days()
    expected = load_claims()
    by_day = {d["edition_date"]: d for d in days}
    results = []  # one row per expected claim
    above_bar = {}  # date -> (actual, expected)
    for day in days:
        state = run_day(day, dry_run=dry_run)
        run_claims = [c for c in state["claims"].values()]
        above_bar[day["edition_date"]] = (sum(1 for e in state["events"] if e["above_bar"]), day.get("expected_above_bar"))
        for exp in (e for e in expected if e["edition_date"] == day["edition_date"]):
            m = match(exp["claim"], run_claims)
            results.append(
                {
                    "id": exp["id"],
                    "edition_date": exp["edition_date"],
                    "expected": exp["expected_status"],
                    "actual": (m["final_status"] or "unverified") if m else "not_extracted",
                    "matched_text": m["text"] if m else None,
                }
            )
    missing_days = {e["edition_date"] for e in expected} - set(by_day)
    if missing_days:
        raise SystemExit(f"claims reference eval days with no day file: {sorted(missing_days)}")

    matrix: Counter[tuple[str, str]] = Counter((r["expected"], r["actual"]) for r in results)
    false_confirmed = sum(n for (exp, act), n in matrix.items() if act == "confirmed" and exp != "confirmed")
    missed_confirmed = sum(n for (exp, act), n in matrix.items() if exp == "confirmed" and act != "confirmed")
    matched = [r for r in results if r["actual"] != "not_extracted"]
    disputed_rate = (sum(1 for r in matched if r["actual"] == "disputed") / len(matched)) if matched else 0.0
    return {
        "results": results,
        "matrix": matrix,
        "false_confirmed": false_confirmed,
        "missed_confirmed": missed_confirmed,
        "disputed_rate": disputed_rate,
        "above_bar": above_bar,
        "n_claims": len(results),
        "n_not_extracted": sum(1 for r in results if r["actual"] == "not_extracted"),
    }


def print_report(ev: dict, *, verbose: bool = False) -> None:
    print("== Headline numbers ==")
    print(f"false confirmed (expected not confirmed, got confirmed): {ev['false_confirmed']}")
    print(f"missed confirmed (expected confirmed, got something else): {ev['missed_confirmed']}")
    print(f"disputed rate (share of matched claims judged disputed): {ev['disputed_rate']:.0%}")
    print("events above bar vs expected, per day:")
    for date, (actual, expected) in sorted(ev["above_bar"].items()):
        flag = "" if actual == expected else "  <- differs"
        print(f"  {date}: actual {actual}, expected {expected}{flag}")
    print(f"claims evaluated: {ev['n_claims']}; not extracted by the pipeline: {ev['n_not_extracted']}")
    print()
    print("== Confusion matrix (rows: expected, columns: actual) ==")
    header = "expected \\ actual".ljust(20) + "".join(a.rjust(15) for a in ACTUALS)
    print(header)
    for exp in STATUSES:
        row = exp.ljust(20) + "".join(str(ev["matrix"].get((exp, act), 0)).rjust(15) for act in ACTUALS)
        print(row)
    if verbose:
        print()
        print("== Per-claim results ==")
        for r in ev["results"]:
            mark = "ok " if r["expected"] == r["actual"] else "DIFF"
            print(f"{mark} {r['id']} {r['edition_date']} expected={r['expected']} actual={r['actual']}")


# --- pytest smoke test: the dry-run eval completes and produces the matrix -----------------------------


def test_eval_dry_run_completes():
    ev = evaluate(dry_run=True)
    assert ev["n_claims"] >= 20
    assert sum(ev["matrix"].values()) == ev["n_claims"]
    assert set(ev["above_bar"]) == {d["edition_date"] for d in load_days()}
    # the headline numbers exist and are internally consistent
    assert ev["false_confirmed"] >= 0 and ev["missed_confirmed"] >= 0
    assert 0.0 <= ev["disputed_rate"] <= 1.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the reasoning graph on the eval dataset.")
    ap.add_argument("--live", action="store_true", help="call the model instead of the dry-run stand-ins (spends credits)")
    ap.add_argument("--confirm-credits", action="store_true", help="required with --live: confirm the printed call estimate")
    ap.add_argument("--verbose", action="store_true", help="print per-claim results")
    args = ap.parse_args(argv)

    if args.live:
        estimate = estimate_model_calls(load_days())
        print(f"A live run makes up to about {estimate} model calls over {len(load_days())} days.")
        if not args.confirm_credits:
            print("Refusing to run live without --confirm-credits. Dry run spends nothing and needs no flag.")
            return 2
        ev = evaluate(dry_run=False)
    else:
        ev = evaluate(dry_run=True)
    print_report(ev, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
