# Data-collection block — handoff to the next coding agent

> **Status 2026-10-24 (Anastasia / Claude Code):** § 3 passed end to end on live data and the nine changes are committed
> (see `git log collectors/`). Found on the way: the committed collector had been crash-looping on a reverted content
> hash (fixed, see README › Decisions 2026-10-24); state.gov answers 403 to everything (feed left empty). Open: § 5
> questions to Yelysei, § 6 items 2–4.

Owner: Anastasia (@AnastasiaShkirpan), branch `data-collection`. Written 2026-10-23 by Anastasia / Claude (chat
session) for the Claude Code session that continues this block. Last pushed commit: `18fb009`. The working tree
holds **nine uncommitted, untested changes** (listed in § 2) — they were written against reasoning's code at
`yelysei/agents@58c9078` but no live run has exercised them yet. Do not commit them until § 3 passes.

## 1. Rules you must read before touching anything, and re-read before every commit and every Issue #2 post

1. `git fetch origin && git show origin/master:AGENTS.md` — the only rulebook. Sections that bind this block:
   § 2 (every decision in `collectors/README.md › Decisions`, same commit as the code; file-level choices as
   `DECISION(date, Anastasia/Claude Code): … Why: …` comments), § 3 (no secrets, inspect the diff, no mocks presented
   as integration), and *Shared Project Tracking*: work only in `data-collection`; statuses are exactly
   `NOT_STARTED | IN_PROGRESS | IMPLEMENTED | TESTED | INTEGRATED | DEPLOYED | BLOCKED | DEFERRED`; a live query is
   the only thing that makes INTEGRATED true.
2. `git show origin/feature/web-portals:docs/TEAM_HANDOFF.md` — the interface-change notification format
   (`WEB INTEGRATION CHANGE — ACTION REQUIRED` block) for anything that changes hashes, offsets, access levels,
   `wire_origin`, `supersedes_id`, `doc_type`, topic ids or the schema. Post it in Issue #2, tag @rcc00n; tag @Sor1na too
   when reasoning is affected.
3. `docs/DECISIONS.md` on `origin/yelysei/agents` (newer than master): log rows dated 2026-10-23/24 make
   `wire_origin`, `supersedes_id` and `official_docs.doc_type` load-bearing for the confirmation rule. Read rows
   216–222 and `reasoning/quorum_reasoning/rules/confirmation.py` before changing how those columns are produced.
4. GitHub Issue #2 — the tracker. Read all comments since 2026-10-23T23:00Z before posting.
5. `collectors/README.md` — this block's contract and decision log. `collectors/schema.sql` — the schema.

Do not merge or edit `yelysei/agents`, `feature/web-portals` or `master`. Read them; propose in Issue #2.

## 2. State of the working tree (uncommitted, written 2026-10-23 evening, untested live)

| Change | File(s) | Why | Risk if wrong |
| --- | --- | --- | --- |
| Topic id `ukraine-aid` → `russia-ukraine-war` | `run.py` (TOPICS), `migrations_001_topic_rename.sql` | Canonical id per DECISIONS 2026-10-23; reasoning's README/CLI/eval set use it | Reasoning's corpus query returns 0 rows if the migration was not applied |
| Wire detection `wire-v2` | `common.py` (`detect_wire_origin`, `WIRE_RULE_VERSION`) | Old `\breuters\b` on the lead marked citations as reprints; a false mark hides a confirmation, a missed one fabricates it | Regex coverage; verified only by a 12-case inline check, not on the live corpus |
| Government RSS → `official_docs` as `release` | `rss.py` (`collect_official_feed`), `run.py` | `kind='official'` sources with RSS (whitehouse/defense/state) were silently skipped | Feed URLs for defense.gov unprobed; page fetch may hit robots.txt |
| `defense-gov`, `state-gov` rows | `sources.csv` | Yelysei: defense.gov is an allowed official source for the topic | Unprobed feeds |
| Title/lead hygiene | `common.py` (`clean_field`, `TITLE_MAX=300`, `LEAD_MAX=600`) | Injection audit (reasoning side) | Changes `content_hash` inputs → every existing row's hash will differ on re-fetch and create a `supersedes_id` chain. **Decide before running**: either TRUNCATE and re-collect (clean), or accept one supersede wave. |
| `doc_type` mapping comments | `congress.py`, `federal_register.py` | Confirm exact enum values reasoning reads | None (comments) |
| `evidence.py` | `zetaris/evidence.py` | Sanitized reproducible Zetaris result Vadim asked for three times | Never run; Zetaris SQL dialect may reject `length()`/`COALESCE` |
| README decisions + semantics | `README.md` | AGENTS.md § 2 | — |

## 3. Verify before committing (in this order; stop on the first failure)

```bash
cd ~/Projects/Quorum
python3 -m py_compile collectors/*.py collectors/zetaris/*.py
python3 -m collectors.probe_feeds 2>/dev/null | grep -E "defense|state-gov"        # expect OK rows; fix URLs if FAIL
docker exec -i quorum-pg psql -U quorum -d quorum < collectors/migrations_001_topic_rename.sql   # prints topic_id|count: one row, russia-ukraine-war
docker compose -f collectors/docker-compose.yml up -d --build
docker compose -f collectors/docker-compose.yml logs -f collector                   # wait for "pass complete"; expect official/whitehouse, official/defense-gov, official/state-gov lines
python3 collectors/verify_collectors.py                                             # PASS on freshness
python3 collectors/zetaris/evidence.py --topic russia-ukraine-war --date 2026-10-24 # writes collectors/zetaris/evidence/<topic>_<date>.json
```

Then inspect the evidence JSON by hand: no `lead`, no body text, no credentials, titles ≤ 80 chars. Spot-check
`wire_origin` on the live corpus (**this is the most important check in this handoff**):

```sql
-- via docker exec -i quorum-pg psql -U quorum -d quorum
SELECT source_id, wire_origin, byline, left(lead, 120) FROM documents WHERE wire_origin IS NOT NULL ORDER BY id DESC LIMIT 30;
SELECT source_id, byline, left(lead, 120) FROM documents WHERE wire_origin IS NULL AND (lead ILIKE '%(AP)%' OR lead ILIKE '%(Reuters)%' OR byline ILIKE '%associated press%') LIMIT 30;
```

First query: every row should be a real reprint (dateline/byline), not an outlet quoting the agency. Second
query: should be empty; any row is a missed reprint → tighten `_WIRE_DATELINE`. Record what you find in the
commit message.

Commit only when all of the above pass. Commit message states the live numbers (documents, official_docs,
sources with rows, wire marks checked). Push to `origin/data-collection`.

## 4. Consistency with reasoning (`yelysei/agents@58c9078`) — check and fix on our side

Read-only inspection points and what they imply for this block:

1. `reasoning/quorum_reasoning/tools/corpus.py` — the two SQL statements it runs. `evidence.py` copies them; if
   Yelysei changes them, update `evidence.py::sql_pair` to match (same columns, same window). It also reads
   `s.flank, s.tier, s.kind, s.independence_group` — those columns must stay non-null for outlets.
2. `rules/confirmation.py` line 31 and `nodes/research.py` line 32: `wire_origin.lower()` is used **as** the
   independence group. Invariant to enforce here: `lower(wire_origin) ∈ {independence_group of rows with kind='agency'}`.
   Add that as a check in `verify_collectors.py` (FAIL if an agency row's `independence_group` ≠ lowercased wire name).
3. `tools/corpus.py` lines 102–106 and 161–164: rows **pointed at** by any `supersedes_id` are dropped from
   evidence/extraction but kept for spread. Our semantics match (new row points at old). Confirm in Issue #2 and
   state the gap: corrections under a new URL are not linked.
4. `state.py` line 29: `doc_type` enum `law | order | vote | ruling | statement | release`. We emit all but
   `ruling` and `statement`. Add a CHECK-style assertion in `verify_collectors.py`: `SELECT DISTINCT doc_type` ⊆ enum.
5. `tools/fetch_text.py`: delegates to `collectors.common.fetch_text(url, title=, lead=)`. Keep that signature
   stable. If reasoning's container cannot import `collectors`, the fix is packaging (a `pyproject.toml` at the
   repo root exposing `collectors`), not a second extractor — raise it in Issue #2 before changing anything.
6. Topic id: after the migration, `SELECT DISTINCT topic_id FROM documents` must return only `russia-ukraine-war`.

## 5. Open questions for Yelysei (post in Issue #2 as one comment; tag @Sor1na @rcc00n)

1. `wire_origin` lowercased equals our agency `independence_group` (`ap`, `reuters`, `afp`). Do you want us to add
   a `wire_group` column with the slug instead of relying on `.lower()`, or is the invariant + a verify check enough?
2. `supersedes_id`: confirmed — the new row points at the row it replaces (same canonical URL, changed hash). Gap:
   corrections published under a new URL are a new document, unlinked. Acceptable for the hackathon?
3. After `clean_field` shipped (2026-10-24), `content_hash` inputs changed (tags/controls stripped, title/lead
   capped). We did **not** TRUNCATE (it would have deleted the 2026-10-22/23 editions, which RSS cannot re-supply):
   31 of 158 rows were predicted to supersede themselves once when re-fetched, 15 did in the first pass, old rows
   stay. On your side they are superseded rows (spread only, never evidence). Acceptable?
4. Government RSS now lands in `official_docs` as `release`. Your `official_sql` returns them with
   `1 AS access_level` and `full_text AS text`; they will never confirm (release). Is that the behaviour you want, or
   should White House *transcripts* (what the President actually said) be `statement` instead of `release`?
5. Level-2 documents have no body, so a wire reprint credited only in the body is missed. Should reasoning treat
   NYT/WSJ/Atlantic/Reuters/AFP level-2 rows as possibly-wire for confirmation purposes (count once per source), or
   accept the double-count risk?
6. Edition window: `evidence.py` reproduces your `_edition_window`. If you change the 05:30 cut or the timezone,
   tell us — the collector schedule (every 15 min) assumes collection finishes well before the cut.
7. The ratings/audience audit (AllSides/MBFC/Ad Fontes + audience, one URL per figure) is assigned to this block.
   Which rating mode does your first live run read, so we fill that column first?

## 6. Then, in priority order

1. Issue #2 acknowledgement + evidence link + the § 5 questions in one comment (TEAM_HANDOFF format for the
   topic rename and wire-v2 as `WEB INTEGRATION CHANGE`, breaking: YES for the topic id, NO for wire-v2).
2. Ratings/audience audit → `sources.csv` with `audience_source_url` and a `ratings_checked_at` column (schema change
   → README decision + Issue #2 notification).
3. Minor-right outlets (Washington Examiner, Washington Times, Daily Caller, Newsmax, Free Beacon, Federalist,
   Blaze, Townhall, National Review, Daily Signal, RedState): probe feeds, add the reachable ones.
4. Merge: only after Yelysei confirms the first live run over `QUORUM_COLLECT` succeeded. Rebase `data-collection`
   on `origin/master`, open a PR, let Vadim's CI run, then take turns as agreed (collection first, reasoning second).
