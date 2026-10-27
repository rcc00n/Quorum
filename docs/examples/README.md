# Examples

Reasoning snapshots (ARCHITECTURE.md § 8). The three `snapshot.*.sample.json` files are produced by the dry run on fictional fixture corpora; `editions/` holds real editions (below). In those three the shape is real and the content is not news; each carries `provenance.fictional: true`, and the portal labels such data as demo. The canonical contract stays § 8; these files follow it, never the other way round.

All three are rebuilt by `python scripts/regenerate_samples.py` (from `reasoning/`, venv active); the per-file commands below are what it runs.

| File | What it is | Regenerate (from `reasoning/`, venv active) |
| --- | --- | --- |
| `snapshot.sample.json` | A normal day: two stories above the bar, two events in the roundup, one verifier/fact-checker disagreement resolved by the third blind reviewer (all three verdicts on the claim), the critic's rejection and rewrite in `trace`. | `python -m quorum_reasoning.run --dry-run --out /tmp/out`, copy `/tmp/out/russia-ukraine-war/2026-10-22/v1.json` (the script writes the snapshot before the store, so `version` is 1 and `published_at` null in these files) |
| `snapshot.empty-day.sample.json` | A completed quiet day: `status: empty`, no stories, `roundup.empty_day: true` with every event listed. Not the same as "no edition". | `python -m quorum_reasoning.run --dry-run --fixture usecases/quiet_day --out /tmp/out` |
| `snapshot.partial.sample.json` | A run in which one node failed on a model call and the run went on: `status: partial`, `errors` names the node and event, the affected stories carry coverage counts but no framing labels. | one-off: `llm.json_task` made to raise for the `frame` task, then `graph.run_local(...)`; see the commit that added the file |

Status mapping for the portal: `ok` → available; `empty` → available, quiet day (not pending); `partial` → partial, with `errors` as the recorded gaps; a failed pull → the adapter's own error state, never an empty edition. Freshness: `generated_at` is when reasoning built it, `published_at` is set by the store when a version is published (null in these files), `expires_at` is the next edition's due time (08:00 America/New_York the following day) — a hint for marking an edition stale when nothing newer has arrived.

## editions/

Real editions, not fixtures: `editions/<date>/<topic>.json` is an installed edition's snapshot, byte for byte (`provenance.fictional: false`, the public trace included), and `editions/<date>/<topic>.run-summary.json` its run summary, counts only (calls by node, lane, model and route, failed calls, substituted and unverified lanes, H-MEM, cache hits, Meterless receipts as a count, memory trace rows, the producer commit, `corpus_as_of_utc` and the snapshot's sha256). Both are written by `reasoning/scripts/export_public_edition.py` once the edition is installed on the site (docs/DECISIONS.md › Demo for the judges, Public edition samples); the ledgers, journals and logs behind them stay private. They are never regenerated: a new run is a new edition.
