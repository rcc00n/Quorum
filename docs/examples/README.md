# Examples

| File | What it is |
| --- | --- |
| `snapshot.sample.json` | One reasoning snapshot (ARCHITECTURE.md § 8) for one topic and day, produced by the dry run on the fictional fixture corpus. Shape is real, content is not news. Regenerate with `cd reasoning && python -m quorum_reasoning.run --dry-run --out /tmp/out` and copy `/tmp/out/russia-ukraine-war/2026-10-22.json` here. |

The sample is the test dataset for the portal: adapter, story page, topic page, roundup and trace views can be built against it before the first live run. The canonical contract stays § 8 of `docs/ARCHITECTURE.md`; this file follows it, never the other way round.
