-- Ratings/audience provenance columns on sources (see collectors/schema.sql DECISION 2026-10-24 and README › Decisions).
-- Additive and nullable; safe to run more than once:
-- Zetaris does not pick up new columns by itself: after this ALTER, re-run (as Administrator, one statement)
--   REGISTER DATASOURCE TABLES ('sources') FROM QUORUM_COLLECT;
-- which refreshed the registered table in place on 2026-10-24 without touching the other tables.
--   docker exec -i quorum-pg psql -U quorum -d quorum < collectors/migrations_002_ratings_provenance.sql
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS allsides_label      TEXT,
    ADD COLUMN IF NOT EXISTS allsides_source_url TEXT,
    ADD COLUMN IF NOT EXISTS mbfc_label          TEXT,
    ADD COLUMN IF NOT EXISTS mbfc_source_url     TEXT,
    ADD COLUMN IF NOT EXISTS adfontes_source_url TEXT,
    ADD COLUMN IF NOT EXISTS ratings_checked_at  DATE;
SELECT count(*) FILTER (WHERE allsides IS NOT NULL OR mbfc IS NOT NULL OR adfontes IS NOT NULL) AS rated,
       count(*) FILTER (WHERE audience IS NOT NULL) AS with_audience, count(*) AS sources
FROM sources;
