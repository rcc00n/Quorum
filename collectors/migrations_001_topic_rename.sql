-- One-off: re-key rows collected under the provisional topic id to the shared one (see collectors/run.py DECISION).
-- Run once against the collectors' Postgres, before the collector container is restarted with the new TOPICS:
--   docker exec -i quorum-pg psql -U quorum -d quorum < collectors/migrations_001_topic_rename.sql
BEGIN;
INSERT INTO topics (id, name, query_terms)
  SELECT 'russia-ukraine-war', 'Russia–Ukraine war and US aid', query_terms FROM topics WHERE id = 'ukraine-aid'
  ON CONFLICT (id) DO NOTHING;
UPDATE documents     SET topic_id = 'russia-ukraine-war' WHERE topic_id = 'ukraine-aid';
UPDATE official_docs SET topic_id = 'russia-ukraine-war' WHERE topic_id = 'ukraine-aid';
UPDATE coverage      SET topic_id = 'russia-ukraine-war' WHERE topic_id = 'ukraine-aid';
DELETE FROM topics WHERE id = 'ukraine-aid';
COMMIT;
SELECT topic_id, count(*) FROM documents GROUP BY topic_id;
