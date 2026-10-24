# collectors — data collection block

Owner: data collection (block 1 in `docs/DECISIONS.md › Stack and work blocks`). This folder holds everything that gets publications and official documents into the database that Zetaris exposes to the reasoning block. Project-wide rules are in `docs/DECISIONS.md`; this file holds only what is local to collection.

## What this block delivers

One Postgres database (schema in `schema.sql`) with five tables, registered in Zetaris as a data source. Reasoning and the frontend read these tables and nothing else from this block.

| Table | Who reads it | What it is |
| --- | --- | --- |
| `sources` | reasoning, frontend | The outlet / agency / government-body registry: flank, tier, ratings, audience, `independence_group`, feed URLs. Loaded from `sources.csv`. |
| `documents` | reasoning, frontend | One row per publication: URL, title, lead, source, times, language, access level, `content_hash`, `wire_origin`. **No full text.** |
| `official_docs` | reasoning | Government documents with full text (public domain): laws, orders, votes, statements, releases. |
| `quotes` | frontend | Exact quotes with character offsets. Schema owned here, rows written by reasoning. |
| `coverage` | frontend | One row per publication per event, never deduplicated — for "covered by N of M in the cohort". |

Contract details:

- Collection delivers a flat stream of documents with `topic_id`. Event ids and clustering belong to reasoning.
- Full article text is not stored. Reasoning gets `fetch_text(url)` (honours robots.txt and the source's access level) and stores only `quotes`. `official_docs` is the one exception: those texts are public domain.
- All timestamps are UTC ISO-8601; `lang` is ISO 639-1.
- A `quotes` row is accepted only if `quote_text` is found verbatim in the text at `url` at insert time; otherwise it is rejected. This is what makes "every conclusion carries its sources" checkable.

Semantics the other blocks rely on (confirmed 2026-10-22 for the portal and reasoning handoffs):

- `fetch_text(url, title=, lead=)` in `collectors/common.py` is the public read contract. It returns `FetchedText(text, content_hash, access_level, fetched_at)`; `text` is paragraph text as a Python `str`.
- **Offsets are Unicode code points**, not bytes: `quotes.char_start/char_end` index into `FetchedText.text`; `verify_quote(text, quote, start, end)` is the acceptance rule.
- **`content_hash`** = sha256 of `title + "\n" + lead + "\n" + first 2000 characters of body text`. It detects edits to headline, lead and opening — not edits deeper in a long article. `quotes.content_hash_at_quote` records the hash of the version the quote was cut from; `fetch_text` recomputes the same formula so the two can be compared.
- **Access level** is per document, decided at collection: 1 full text (robots.txt allowed, no paywall), 2 title + lead only, 3 fact of coverage only. `fetch_text` returns the level it achieved now, which can be lower than the stored one if robots.txt changed.
- **Provenance of `sources` fields**: `independence_group` is hand-set for all 17 sources (agencies are their own group; outlets their own; reprints are detected per document via `wire_origin`, not via the registry). `allsides`, `mbfc`, `adfontes` and `audience` are **empty for all outlets as of 2026-10-22** — filling them is the source-audit task in `docs/DECISIONS.md`, and the four rating modes on the portal have nothing to compute until it is done. `audience_source_url` must cite where each audience figure came from.
- **`wire_origin`** (rule `wire-v2`, 2026-10-23) fires only on authorship signals: an agency byline, a wire dateline credit opening the lead (`WASHINGTON (AP) —`, `KYIV, Oct 22 (Reuters) -`), an "X contributed to this report" trailer, or Reuters' "Reporting by …; Editing by …" sign-off. It does **not** fire on a citation inside the lead ("…, Reuters reported"). Values are exactly `AP`, `Reuters`, `AFP`; lowercased they equal the agency rows' `independence_group` (`ap`, `reuters`, `afp`) — reasoning relies on that equality, so neither side renames. Known miss: a reprint credited only deep in the body of a level-2 document (no body fetched).
- **`supersedes_id`** means: this row is the current version of the same canonical URL whose content hash changed on re-fetch; it points at the row it replaces. The old row is kept. Corrections published under a **new URL** are a new document and are not linked — reasoning should accept that gap for the hackathon; linking them needs title/entity matching we do not do.
- **`official_docs.doc_type`** values are exactly `law | order | vote | ruling | statement | release`. Federal Register: PRESDOCU→order, RULE→law, PRORULE/NOTICE→release. Congress.gov: enacted→law, passed/agreed by a chamber→vote (the fact established is the vote and its outcome), otherwise release. Government RSS (whitehouse.gov, defense.gov, state.gov)→release, full text stored. No collector emits `ruling` or `statement` yet (no court source in the slice).
- **Zetaris retrieval** is live: datasource `QUORUM_COLLECT` (id 807) over this Postgres; `SELECT ... FROM QUORUM_COLLECT.documents` returns collected rows through `agent/tools_zetaris.py`.

## Access levels

| Level | What is taken | When |
| --- | --- | --- |
| 1 | Full text fetched from the page (for reasoning, not stored) | robots.txt allows our user agent and the source is not paywalled |
| 2 | Title and lead from RSS only | Paywalled sources (NYT, WaPo, WSJ, The Atlantic) and any domain whose robots.txt disallows us; scores shown "by headline" |
| 3 | Fact of publication only (URL, time) from GDELT | Sources with no usable feed; counts for `coverage`, not for analysis |

## Channels per source group (hackathon slice)

| Group | Access route | First-day check |
| --- | --- | --- |
| AP | apnews.com has no official RSS; headlines by domain through the GDELT DOC 2.0 API; page fetch only if robots.txt allows | robots.txt |
| Reuters | Google news-sitemap XML (`reuters.com/arc/outboundfeeds/news-sitemap/`), ~30 latest, level 2 | sitemap still served |
| AFP | France24 English RSS (AFP's own outlet), level 2 | — |
| Guardian | Open Platform API, free key, full text | key in `.env` |
| NYT, WSJ | RSS, level 2 | section feed URLs |
| WaPo, ISW | no feed reachable by bots (502 / 403 on 2026-10-22); level 3 via GDELT only | retry later |
| CNN, NPR, Fox News, NY Post, Daily Wire, Breitbart; Vox, Mother Jones, The Intercept, Slate, The Daily Beast, The New Republic, The Nation, Salon, Common Dreams | RSS + page fetch at level 1 | robots.txt per domain (all allow as of 2026-10-22) |
| The Atlantic | RSS, level 2 (paywall) | — |
| ISW, DeepState, Oryx | RSS or update page; stored as attributed statements | update frequency |
| federalregister.gov | JSON API, no key | which sections map to the topic |
| defense.gov, state.gov | press-release / transcript RSS → `official_docs` as `release` | feed URLs (probe) |
| congress.gov | API with a free api.data.gov key: bills, votes, texts | key in `.env` |
| whitehouse.gov, state.gov, defense.gov | press-release / briefing RSS | feed URLs |
| president.gov.ua, mod.gov.ua, kremlin.ru, mid.ru | RSS where present, else page fetch; titles need translation for the demo | reachability from the build machine |
| GDELT DOC 2.0 API | fallback for everything: URL, title, time, tone by domain and query, 15-minute lag, no key | request limits |

## Running

Continuous (the normal way; survives terminal close, sleep and reboot while Docker Desktop runs):

```
docker compose -f collectors/docker-compose.yml up -d --build   # Postgres on host port 5433 + collector loop, every 15 min
docker compose -f collectors/docker-compose.yml logs -f collector
docker compose -f collectors/docker-compose.yml up -d --build   # again after any change to collectors/ or sources.csv
```

Manual, for development:

```
pip install -r collectors/requirements.txt
psql "$DATABASE_URL" -f collectors/schema.sql        # once
python3 -m collectors.probe_feeds                    # which feeds answer, robots.txt verdict per domain
python3 -m collectors.run                            # one pass over every topic and collector
python3 -m collectors.run --only rss --loop 900      # one collector, every 15 minutes
python3 collectors/verify_collectors.py              # PASS / FAIL / BLOCKED, same exit codes as scripts/checks.py
```

Layout:

```
collectors/
  common.py             env, Postgres, polite Fetcher (robots.txt + 2 s/domain), hashing, wire_origin, upserts
  rss.py                outlets via RSS: title + lead; page fetched only for the hash at level 1
  guardian.py           Guardian Open Platform (GUARDIAN_API_KEY), full text for the hash
  federal_register.py   Federal Register documents API, no key; full text stored in official_docs
  congress.py           Congress.gov v3 bills (CONGRESS_API_KEY) -> official_docs
  run.py                entry point; TOPICS dict lives here until the portal provides topics
  probe_feeds.py        network-only feed check
  verify_collectors.py  readiness check
  schema.sql            Postgres DDL
  sources.csv           hand-edited registry: rss_urls separated by |
  zetaris/              register.py (REST, via agent/tools_zetaris.py) + SQL to register Postgres as datasource QUORUM_COLLECT
```

Database: the Postgres that ships inside the Zetaris bundle, or any Postgres reachable from both the collectors and the
Zetaris containers (`host.docker.internal` from inside Docker). `DATABASE_URL` in `.env` points at it; `python3 collectors/zetaris/register.py` registers it in Zetaris as datasource `QUORUM_COLLECT` (needs `requests`, `python-dotenv` and the Zetaris settings in `.env`). Reasoning queries it as `SELECT ... FROM QUORUM_COLLECT.documents` through `agent/tools_zetaris.py`. Registered 2026-10-22, datasource id 807.

Environment variables (names only; values in local `.env`): `DATABASE_URL`, `GUARDIAN_API_KEY`, `CONGRESS_API_KEY`, `COLLECTOR_USER_AGENT`.

Tested end-to-end against a mock feed and a local Postgres: topic filter, robots.txt downgrade to level 2, wire detection, tracking-parameter stripping, re-run idempotence, article-edit versioning via `supersedes_id`, official_docs upsert. Live feeds were not reachable from the sandbox; run `probe_feeds.py` on a machine with open internet and fix any feed URL that fails.

## Decisions

| Date | Who (human / tool) | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | Yelysei / Claude | Full article text is never stored; `documents` keeps title, lead, URL, hash. Quotes are stored with character offsets and the hash of the text they were cut from. | Keeps the block clear of retrieval-copy claims (the theory in Dow Jones v. Perplexity) while every quote stays verifiable. |
| 2026-10-22 | Yelysei / Claude | Three access levels (full text / RSS headline+lead / coverage only); robots.txt decides between 1 and 2 automatically, checked once a day per domain. | Paywalled and bot-blocking outlets still count for coverage without us bypassing anything. |
| 2026-10-22 | Yelysei / Claude | Honest user agent `QuorumBot/0.1 (+contact)`, at most one request per 2 seconds per domain. | We do not masquerade as a browser; rate matches what a small crawler is expected to do. |
| 2026-10-22 | Yelysei / Claude | `wire_origin` is set from the byline and a same-day title match against AP / Reuters / AFP; such rows stay in `coverage` but are excluded from confirmation. | Implements "ten reprints of one wire story are one piece of evidence" from `docs/DECISIONS.md › Principles`. |
| 2026-10-22 | Yelysei / Claude | A changed `content_hash` on re-fetch creates a new `documents` row with `supersedes_id`; the old row is kept. | Edits to published articles are themselves a signal and must not overwrite history. |
| 2026-10-22 | Yelysei / Claude | Collectors write to Postgres; Zetaris sits on top as the SQL layer. Direct Zetaris REST connectors to external APIs are tried first, Postgres-only is the fallback. | Collection must not depend on an untested connector two days before the deadline. |
| 2026-10-22 | Anastasia / Claude | Collectors are plain Python modules run by `collectors/run.py` (cron or `--loop`), writing to Postgres with psycopg; no Django, Celery or framework yet. | The portal does not exist yet; a Django app can wrap these tables later with `inspectdb` without rewriting the collectors. |
| 2026-10-22 | Anastasia / Claude | Topic matching at collection is a whole-word match of `topics.query_terms` against title + lead; no model call. | Cheap gate that keeps the demo corpus small; reasoning re-clusters anyway. |
| 2026-10-22 | Anastasia / Claude | Federal Register and Congress.gov are collected both by Python (into `official_docs`, for the hash-and-quote pipeline) and exposed as live Zetaris REST tables (for the judges' cross-source SQL demo). | Satisfies the "SQL across sources" requirement without making collection depend on an untested connector. |
| 2026-10-22 | Anastasia / Claude | Google News RSS is not used for article discovery: its links cannot be resolved to publisher URLs without executing Google's JavaScript (no redirect, no token in HTML as of 2026-10-22). Sources without a bot-readable feed (WaPo, ISW) drop to level 3. | A `documents.url` that points at news.google.com is not a citation the user can verify. |
| 2026-10-22 | Anastasia / Claude | US-centred corpus: US outlets get 3–4 section feeds each, Guardian is capped at 50 `us-news` items, AFP comes via France24 at level 2. | The demo is a US event on a US spectrum; the first live run was 100 Guardian items vs 2–3 per US outlet. |
| 2026-10-22 | Anastasia / Claude | Postgres is registered in Zetaris with `CREATE DATASOURCE` (JDBC) + `REGISTER DATASOURCE TABLES`, not `CREATE LIGHTNING DATABASE`, which Zetaris reserves for file and REST sources. Tables are addressed as `QUORUM_COLLECT.<table>`. | Per zetaris/getting-started `zetaris-lightning-sql-commands.md`; verified live. |
| 2026-10-22 | Anastasia / Claude | Collectors run continuously as a Docker Compose service next to the Postgres (`collectors/docker-compose.yml`), one pass every 15 minutes, `restart: unless-stopped`. Not on the portal VPS. | ARCHITECTURE.md needs two days of corpus before the demo day is chosen; the VPS is Vadim's production and changes there need all three owners' approval. Same image moves to a server later. |
| 2026-10-22 | Anastasia / Claude | All ten minor-left outlets from DECISIONS.md added with their native RSS (probe: all reachable, robots allow); minor-right still only Daily Wire and Breitbart. | Cohort diagram needs both minor cohorts populated; right side is the next addition. |
| 2026-10-24 | Anastasia / Claude Code | `sources` gains six nullable provenance columns (`allsides_label`, `allsides_source_url`, `mbfc_label`, `mbfc_source_url`, `adfontes_source_url`, `ratings_checked_at`), added by `migrations_002_ratings_provenance.sql`; every rating or audience figure in `sources.csv` must cite its URL and the check date, enforced by `verify_collectors.py`. Mapping to [-1, 1] is the one in `docs/DECISIONS.md › Spectrum ratings`; a label outside the scale (AllSides "Mixed") keeps the label and leaves the number NULL. | A mapped number is not checkable without the page it came from; the portal's four rating modes need figures another person can verify. Notified in Issue #2 before the commit (breaking: NO). |
| 2026-10-24 | Anastasia / Claude Code | `audience` = monthly website visits (total visits, not uniques, not TV) from a public page that prints the figure with its month: Similarweb's public website page first, Press Gazette's monthly US top-50 ranking second, Semrush's public page only where Similarweb prints no figure (salon.com on 2026-10-24); the month is named in the commit message. | `docs/DECISIONS.md` leaves "where the audience estimates come from" open; one consistent, public, re-checkable source beats mixing media kits with trackers. Proposed as a DECISIONS.md row in Issue #2. |
| 2026-10-24 | Anastasia / Claude Code | `verify_collectors.py` FAILs the block on three contract invariants: `lower(wire_origin)` equals an agency row's `independence_group` (registry and data side), `official_docs.doc_type` ⊆ `law|order|vote|ruling|statement|release`, exactly one `topic_id` across `documents` and `official_docs` equal to `run.py`'s; outlets must carry flank, tier and independence_group. | Reasoning (`rules/confirmation.py`, `nodes/research.py`, `state.py`, `tools/corpus.py`) uses these verbatim; a rename on either side would break confirmation silently. |
| 2026-10-24 | Anastasia / Claude Code | `state-gov` stays in `sources.csv` with no feed URL; `defense-gov` (two feeds) and `whitehouse` are live. | state.gov answered 403 "Technical Difficulties" to every path, robots.txt included, for both our user agent and a browser one on 2026-10-24; nothing to fix on our side, re-probe before the demo. |
| 2026-10-24 | Anastasia / Claude Code | `upsert_document` treats an existing `(canonical_url, content_hash)` pair anywhere in a URL's chain as a known version (refresh `fetched_at`, insert nothing); only a hash never seen for that URL creates a row with `supersedes_id`. | The newest-row-only comparison crashed the pass on a reverted hash (A→B→A) via the UNIQUE constraint: 37 container restarts on 2026-10-24 and no collection after the failing source. |
| 2026-10-24 | Anastasia / Claude Code | On a level-1 source, only robots.txt downgrades an item to level 2; a transient page-fetch failure skips the item for that pass. | The level-2 hash omits the body, so a downgrade fabricated a `supersedes_id` chain on an unchanged article and the next good fetch collided with the original hash. |
| 2026-10-24 | Anastasia / Claude Code | `clean_field` shipped without a TRUNCATE: rows whose title/lead the cleaner changes (31 of 158 on 2026-10-24) supersede themselves once when re-fetched; old rows stay. | A TRUNCATE would delete the 2026-10-22/23 editions, which RSS cannot re-supply; reasoning excludes superseded rows from evidence, so the one-time wave only double-counts those rows in spread. |
| 2026-10-23 | Anastasia / Claude Code | Topic id renamed `ukraine-aid` → `russia-ukraine-war`; collected rows re-keyed by `migrations_001_topic_rename.sql`. Only one id exists. | Reasoning's README, CLI and 28-claim evaluation set use `russia-ukraine-war`; DECISIONS.md log 2026-10-23 (snapshot envelope) names it canonical. |
| 2026-10-23 | Anastasia / Claude Code | Wire detection `wire-v2`: authorship signals only (byline, dateline credit, contributed-trailer, Reuters sign-off); citations inside the lead no longer mark a reprint. 12-case unit check in the commit message. | `wire_origin` is now load-bearing for confirmation (reasoning counts a reprint in the wire's group; the origin outlet counts as a group since 2026-10-24): a false mark hides a confirmation, a missed mark can fabricate one. |
| 2026-10-23 | Anastasia / Claude Code | Government RSS feeds (whitehouse/defense/state) are collected into `official_docs` as `release` with full text, by `rss.collect_official_feed`; previously `kind='official'` sources with RSS were silently skipped. | A government statement is a statement, not coverage; it must reach reasoning's `official_docs` query, where `release` never confirms. |
| 2026-10-23 | Anastasia / Claude Code | Title ≤ 300 and lead ≤ 600 characters, tags and C0 control characters stripped at collection (`clean_field`). | Injection audit on the reasoning side; two layers of hygiene. |
| 2026-10-23 | Anastasia / Claude Code | `collectors/zetaris/evidence.py` runs reasoning's own two corpus statements through the authenticated Zetaris route and writes a sanitized JSON (ids, hashes, levels, wire marks, counts; no text) to `collectors/zetaris/evidence/`. | AGENTS.md tracking §4: only a real query is INTEGRATED evidence; Issue #2 asked for a reproducible sanitized result. |
