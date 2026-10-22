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
| Reuters, AFP | Google News RSS by domain (`news.google.com/rss/search?q=site:reuters.com+<topic>`) | feed stability |
| Guardian | Open Platform API, free key, full text | key in `.env` |
| NYT, WaPo, WSJ, The Atlantic | RSS, level 2 | section feed URLs |
| CNN, NPR, Fox News, NY Post, Vox, Slate, Daily Wire, Breitbart, Washington Examiner, Newsmax | RSS + page fetch at level 1 | robots.txt per domain |
| ISW, DeepState, Oryx | RSS or update page; stored as attributed statements | update frequency |
| federalregister.gov | JSON API, no key | which sections map to the topic |
| congress.gov | API with a free api.data.gov key: bills, votes, texts | key in `.env` |
| whitehouse.gov, state.gov, defense.gov | press-release / briefing RSS | feed URLs |
| president.gov.ua, mod.gov.ua, kremlin.ru, mid.ru | RSS where present, else page fetch; titles need translation for the demo | reachability from the build machine |
| GDELT DOC 2.0 API | fallback for everything: URL, title, time, tone by domain and query, 15-minute lag, no key | request limits |

## Running

Not implemented yet; the layout below is the plan for the first commit of code.

```
collectors/
  schema.sql            Postgres DDL for the five tables
  sources.csv           source registry, edited by hand (ratings, audience, groups)
  verify_collectors.py  PASS / FAIL / BLOCKED check in the style of scripts/checks.py
```

Environment variables (names only; values in local `.env`): `DATABASE_URL`, `GUARDIAN_API_KEY`, `CONGRESS_API_KEY`, `COLLECTOR_USER_AGENT`.

## Decisions

| Date | Who (human / tool) | What | Why |
| --- | --- | --- | --- |
| 2026-10-22 | Yelysei / Claude | Full article text is never stored; `documents` keeps title, lead, URL, hash. Quotes are stored with character offsets and the hash of the text they were cut from. | Keeps the block clear of retrieval-copy claims (the theory in Dow Jones v. Perplexity) while every quote stays verifiable. |
| 2026-10-22 | Yelysei / Claude | Three access levels (full text / RSS headline+lead / coverage only); robots.txt decides between 1 and 2 automatically, checked once a day per domain. | Paywalled and bot-blocking outlets still count for coverage without us bypassing anything. |
| 2026-10-22 | Yelysei / Claude | Honest user agent `QuorumBot/0.1 (+contact)`, at most one request per 2 seconds per domain. | We do not masquerade as a browser; rate matches what a small crawler is expected to do. |
| 2026-10-22 | Yelysei / Claude | `wire_origin` is set from the byline and a same-day title match against AP / Reuters / AFP; such rows stay in `coverage` but are excluded from confirmation. | Implements "ten reprints of one wire story are one piece of evidence" from `docs/DECISIONS.md › Principles`. |
| 2026-10-22 | Yelysei / Claude | A changed `content_hash` on re-fetch creates a new `documents` row with `supersedes_id`; the old row is kept. | Edits to published articles are themselves a signal and must not overwrite history. |
| 2026-10-22 | Yelysei / Claude | Collectors write to Postgres; Zetaris sits on top as the SQL layer. Direct Zetaris REST connectors to external APIs are tried first, Postgres-only is the fallback. | Collection must not depend on an untested connector two days before the deadline. |
