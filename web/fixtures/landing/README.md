# Landing fixtures

Data the public landing page renders. Both files are copies of committed artefacts elsewhere in the repository; `web/tests/landing.cjs` fails when a copy drifts from its source.

| File | Source | What it is |
| --- | --- | --- |
| `zetaris-evidence-russia-ukraine-war-2026-10-24.json` | `collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json` | A real, sanitized Zetaris query over the collected corpus (2026-10-24 edition window; counts, SQL, five title samples; no article text). Rendered as the hero artefact. |
| `sources.json` | `collectors/sources.csv` | The registry's public columns (id, name, domain, kind, flank, tier, access_level_default) for the 40 sources; names only, no ratings or feed URLs. The tally grid. |
| `rules.json` | `reasoning/config/reasoning.toml` (`[loops]`, `[writing]`) | The three loop limits, the 26 forbidden words and the 9 attribution verbs the landing quotes. |
| `graph.json` | `docs/ARCHITECTURE.md § 5` | The 15 node names in run order and the three loops with their limit keys. |
| `trace.sample.json` | `docs/examples/snapshot.sample.json` (`trace`) | Rows of the committed dry-run sample: fictional content, real shape. The landing labels it "dry run · fictional" wherever it is shown. Replace with a public-safe excerpt of a canonical run when the reasoning owner provides one. |

The copy exists because `deploy/build-web.sh` builds `web/` alone, outside the repository, so the page cannot import from `collectors/` or `docs/` at build time.

DECISION(2026-10-25, Anastasia/Claude Code): the landing shows only numbers and titles that exist in a committed file or a published snapshot; fixtures are byte-for-byte copies checked by a test. Why: the page must claim nothing the repository cannot back, and a hand-typed number drifts.
