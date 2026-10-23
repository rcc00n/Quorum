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
| CNN, NPR, Fox News, NY Post, Vox, Slate, Daily Wire, Breitbart, Washington Examiner, Newsmax | RSS + page fetch at level 1 | robots.txt per domain |
| ISW, DeepState, Oryx | RSS or update page; stored as attributed statements | update frequency |
| federalregister.gov | JSON API, no key | which sections map to the topic |
| congress.gov | API with a free api.data.gov key: bills, votes, texts | key in `.env` |
| whitehouse.gov, state.gov, defense.gov | press-release / briefing RSS | feed URLs |
| president.gov.ua, mod.gov.ua, kremlin.ru, mid.ru | RSS where present, else page fetch; titles need translation for the demo | reachability from the build machine |
| GDELT DOC 2.0 API | fallback for everything: URL, title, time, tone by domain and query, 15-minute lag, no key | request limits |

## Running

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
  zetaris/              Lightning SQL to register Postgres and a live Federal Register REST table in Zetaris
```

Database: the Postgres that ships inside the Zetaris bundle, or any Postgres reachable from both the collectors and the
Zetaris containers (`host.docker.internal` from inside Docker). `DATABASE_URL` in `.env` points at it; `collectors/zetaris/01_register_postgres.sql` registers it in Zetaris.

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
