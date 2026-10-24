-- documents.topic_match: where the topic's query terms matched (see collectors/schema.sql DECISION 2026-10-24).
-- Additive, nullable; the backfill only fills NULLs, so it is safe to run more than once:
--   docker exec -i quorum-pg psql -U quorum -d quorum < collectors/migrations_003_topic_match.sql
-- Zetaris keeps the column list it saw at registration: afterwards re-run, as Administrator,
--   REGISTER DATASOURCE TABLES ('documents') FROM QUORUM_COLLECT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS topic_match TEXT CHECK (topic_match IN ('title', 'lead', 'body'));
WITH pat AS (
    SELECT id AS topic_id, '\m(' || array_to_string(array(SELECT regexp_replace(t, '([.\\+*?\[^\]$(){}=!<>|:-])', '\\\1', 'g')
                                                         FROM unnest(query_terms) AS t), '|') || ')\M' AS rx
    FROM topics
)
-- A lead stored at the 600-character cap (clean_field, 2026-10-23) may have carried the term beyond the cap, where the
-- collector matched it on the full RSS summary: that is 'lead', not 'body'. 'body' is then only the Guardian API search.
UPDATE documents d SET topic_match = CASE
        WHEN d.title ~* pat.rx THEN 'title'
        WHEN coalesce(d.lead, '') ~* pat.rx THEN 'lead'
        WHEN d.source_id <> 'guardian' AND length(coalesce(d.lead, '')) >= 600 THEN 'lead'
        ELSE 'body' END
FROM pat WHERE pat.topic_id = d.topic_id AND d.topic_match IS NULL;
SELECT topic_match, count(*) FROM documents GROUP BY 1 ORDER BY 1;
SELECT source_id, count(*) FROM documents WHERE topic_match = 'body' GROUP BY 1 ORDER BY 2 DESC;
