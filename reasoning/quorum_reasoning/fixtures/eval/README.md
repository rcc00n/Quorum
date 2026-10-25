# Evaluation dataset: russia-ukraine-war, 2026-10-09 to 2026-10-22

Real claims from the last 14 days before 2026-10-23, with the documents a run needs and the status the
pipeline is expected to assign under the rules in `docs/ARCHITECTURE.md` § 6. Built 2026-10-23 for the
reasoning review (workstream C). The eval runner is `reasoning/tests/eval.py`.

## Shape

- `days/<edition_date>.json` — one file per edition day, same document shape as `fixtures/sample_day.json`,
  plus `expected_above_bar` and `expected_above_bar_reason` (the rubric applied by hand to the real facts).
- `claims.json` — 28 claims. Each has: `claim` (text), `edition_date`, `expected_status`
  (`confirmed` / `disputed` / `unverified`), `expected_reason` (why, under § 6), `justification`
  (a quoted passage, its URL, the source id), and `doc_ids` (the day documents that carry it).

Composition: 9 expected `confirmed` (4 by official document, 5 by two or more independence groups),
1 expected `disputed` (conflicting casualty tolls), 18 expected `unverified` (single group, or a party's
statement about its own conduct). Sources used: npr, cnn, fox-news, breitbart, daily-beast, new-republic
(outlets from `collectors/sources.csv`), federal-register (official). Days: 7.

An expected status is justified by a quote or it is `unverified`: where coverage in the collected slice
comes from one independence group only, the expected status is `unverified` even when the event is
real-world true (e.g. e28, the 2026-10-22 Kyiv strike), because the rule is applied to the documents the
run sees, not to the world.

## Provenance and limits

- Collected 2026-10-23 with web search through the build environment's search tool. Titles and URLs are
  verbatim from search results. **Leads are reconstructed from search-result summaries and are not verbatim
  outlet text** (`verbatim: false` on those justification quotes): the build container's proxy blocks direct
  page fetches, and reuters.com, apnews.com, nypost.com, nytimes.com and theguardian.com block the search
  crawler via robots.txt, so those outlets do not appear at all. No full article bodies are stored anywhere —
  titles, short leads and short quotes only, within each source's access level.
- The official document text in `days/2026-10-17.json` is an excerpt reconstructed from search-result
  quotations of the public-domain Executive Order 14436 (Federal Register 2026-21599), not the full verbatim
  text. Verify against the URL before using it in a live acceptance run.
- defense.gov is allowed by the task but has no row in `collectors/sources.csv`, so no defense.gov document
  is included (noted for Anastasia).
- `published_at` values inside each edition window are approximate where the source page did not state a
  time; each is placed inside the 24 hours ending 05:30 America/New_York (09:30Z in October) of its edition day.

## Running

```bash
cd reasoning && . .venv/bin/activate
python tests/eval.py                 # dry run: no credits, no network; what CI runs
python -m pytest tests/eval.py       # the smoke test (dry run must complete and produce the matrix)
python tests/eval.py --live --confirm-credits   # model run; prints the call estimate first and needs the flag
```

## What dry run measures, and what it cannot

Dry run replaces every model judgment with deterministic stand-ins (`dryrun.py`): clustering merges by
title-word cosine, stances come from word containment, rubric points from title keywords. So the dry-run
numbers measure the pipeline's mechanics and the rule layer — above all that **nothing reaches `confirmed`
without a document or two independence groups** (false confirmed must be 0 in dry run, and is) — not
whether the model reads text correctly. Known mechanical effects visible in the baseline: real titles of
one event often share few exact words, so clusters fragment and cross-outlet confirmation is missed
(`missed confirmed` is dominated by this); the stricter fact-checker stand-in produces `disputed` on some
claims two models would agree on. Only `--live` measures extraction quality, stance accuracy and the
rubric's judgment against `expected_above_bar`.

Baseline (dry run, 2026-10-23): false confirmed 0, missed confirmed 7, disputed rate 5%, 7 of 28 claims
not extracted; above-bar matches expected on 4 of 7 days.

After the event-key clustering redesign and the 2026-10-24 rule decisions (origin group counts next to one
other; confirmed deaths reach the whole country), dry run: false confirmed 1, missed confirmed 4, disputed
rate 0%, above-bar matches 3 of 7 days. The clustering fragmentation is gone — the Kramatorsk bus-strike
outlets form one event whose toll claims are `disputed` in the state, and the day correctly escalates
(points 6, zero confirmed claims) instead of publishing a story. Known artifacts of the harness, not the
rules: the "false confirmed 1" is the matcher mapping e07's narrow date claim onto the run's broader
Treasury-license claim, which is legitimately confirmed under the origin rule while e07's own claim stays
single-source; the "disputed 0%" is the matcher picking an unmatched variant over the disputed toll claim;
2026-10-19's above-bar difference is the rubric stand-in's keyword reach on the Trump-angle titles. The
remaining `missed confirmed` distance is the stance stand-in's word-overlap bound, measurable only live.
Hand-applied `expected_above_bar` values were re-checked against the 2026-10-24 rules (see the day files'
reasons; none changed value).
