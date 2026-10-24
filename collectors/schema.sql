-- Quorum data-collection schema (Postgres 14+).
-- Contract with reasoning and frontend: see collectors/README.md.
-- DECISION(2026-10-22, Yelysei/Claude): no full-text column on documents; see collectors/README.md › Decisions.

CREATE TABLE IF NOT EXISTS sources (
    id                   TEXT PRIMARY KEY,                 -- slug, e.g. 'fox-news'
    name                 TEXT NOT NULL,
    domain               TEXT NOT NULL,
    kind                 TEXT NOT NULL CHECK (kind IN ('agency', 'outlet', 'official', 'military')),
    flank                TEXT CHECK (flank IN ('left', 'right', 'center')), -- NULL for official/military
    tier                 TEXT CHECK (tier IN ('major', 'minor')),
    independence_group   TEXT NOT NULL,                    -- agencies: own name; reprints collapse here
    audience             BIGINT,                           -- monthly visits, hand-entered
    audience_source_url  TEXT,
    allsides             REAL,                             -- mapped to [-1, 1], NULL if unrated; mapping: docs/DECISIONS.md › Spectrum ratings
    mbfc                 REAL,
    adfontes             REAL,
    -- DECISION(2026-10-24, Anastasia/Claude Code): every rating/audience figure cites its source. Label columns keep the
    -- rating as printed by the rater ("Lean Left", "LEFT-CENTER"); the REAL columns above are the mapped value.
    -- ratings_checked_at is the day all figures of the row were read. Why: a mapped number is not checkable without
    -- the page it came from; DECISIONS.md requires audience_source_url, the same holds for the three ratings.
    allsides_label       TEXT,
    allsides_source_url  TEXT,
    mbfc_label           TEXT,
    mbfc_source_url      TEXT,
    adfontes_source_url  TEXT,
    ratings_checked_at   DATE,
    rss_urls             TEXT[] NOT NULL DEFAULT '{}',
    access_level_default SMALLINT NOT NULL DEFAULT 1 CHECK (access_level_default IN (1, 2, 3)),
    country              TEXT,
    lang                 TEXT NOT NULL DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS topics (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    query_terms TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES sources(id),
    topic_id      TEXT REFERENCES topics(id),
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title         TEXT NOT NULL,
    lead          TEXT,
    byline        TEXT,
    published_at  TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    lang          TEXT NOT NULL DEFAULT 'en',
    access_level  SMALLINT NOT NULL CHECK (access_level IN (1, 2, 3)),
    content_hash  TEXT NOT NULL,                           -- sha256 of title + lead + first 2000 chars at fetch
    wire_origin   TEXT CHECK (wire_origin IN ('AP', 'Reuters', 'AFP')),
    wire_origin_version TEXT,                              -- rule/model version that set wire_origin
    supersedes_id BIGINT REFERENCES documents(id),         -- set when a re-fetch found a changed hash
    UNIQUE (canonical_url, content_hash)
);
CREATE INDEX IF NOT EXISTS documents_topic_published ON documents (topic_id, published_at DESC);
CREATE INDEX IF NOT EXISTS documents_source_published ON documents (source_id, published_at DESC);

CREATE TABLE IF NOT EXISTS official_docs (
    id           BIGSERIAL PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    topic_id     TEXT REFERENCES topics(id),
    url          TEXT NOT NULL UNIQUE,
    doc_type     TEXT NOT NULL CHECK (doc_type IN ('law', 'order', 'vote', 'ruling', 'statement', 'release')),
    doc_number   TEXT,
    title        TEXT NOT NULL,
    full_text    TEXT NOT NULL,                            -- public domain: stored in full
    signed_at    TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    lang         TEXT NOT NULL DEFAULT 'en'
);

-- Written by reasoning; schema owned by collection.
CREATE TABLE IF NOT EXISTS quotes (
    id                    BIGSERIAL PRIMARY KEY,
    document_id           BIGINT REFERENCES documents(id),
    official_doc_id       BIGINT REFERENCES official_docs(id),
    claim_id              TEXT NOT NULL,                   -- reasoning's claim identifier
    quote_text            TEXT NOT NULL,
    char_start            INTEGER NOT NULL,
    char_end              INTEGER NOT NULL,
    content_hash_at_quote TEXT NOT NULL,
    verified_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((document_id IS NULL) <> (official_doc_id IS NULL))
);

-- One row per publication per event, never deduplicated.
CREATE TABLE IF NOT EXISTS coverage (
    document_id             BIGINT NOT NULL REFERENCES documents(id),
    event_id                TEXT NOT NULL,                 -- assigned by reasoning
    source_id               TEXT NOT NULL REFERENCES sources(id),
    topic_id                TEXT REFERENCES topics(id),
    published_at            TIMESTAMPTZ,
    counted_in_confirmation BOOLEAN NOT NULL DEFAULT true, -- false for wire reprints
    PRIMARY KEY (document_id, event_id)
);
