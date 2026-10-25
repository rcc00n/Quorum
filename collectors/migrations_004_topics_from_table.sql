-- topics becomes the source of truth (see collectors/schema.sql DECISION 2026-10-25 and README › Topics).
-- Additive and idempotent:
--   docker exec -i quorum-pg psql -U quorum -d quorum < collectors/migrations_004_topics_from_table.sql
-- Zetaris keeps the column list it saw at registration: afterwards re-run, as Administrator,
--   REGISTER DATASOURCE TABLES ('topics') FROM QUORUM_COLLECT;
ALTER TABLE topics
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS active     BOOLEAN NOT NULL DEFAULT true;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'topics_id_slug_check') THEN
        ALTER TABLE topics ADD CONSTRAINT topics_id_slug_check CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,63}$');
    END IF;
END $$;
-- One-off cleanup: the retired id 'ukraine-aid' was re-inserted by the pre-rename collector image, which ran for two
-- minutes after migrations_001 (2026-10-24 01:10Z-01:12Z) with the old upsert. Nothing references it; with the table as
-- the source of truth it would make every pass walk the feeds twice. Deleted only while no row points at it.
DELETE FROM topics t
 WHERE t.id = 'ukraine-aid'
   AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.topic_id = t.id)
   AND NOT EXISTS (SELECT 1 FROM official_docs o WHERE o.topic_id = t.id)
   AND NOT EXISTS (SELECT 1 FROM coverage c WHERE c.topic_id = t.id);
SELECT id, name, cardinality(query_terms) AS terms, active, created_at FROM topics ORDER BY created_at, id;
