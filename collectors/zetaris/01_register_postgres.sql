-- Register the collectors' Postgres in Zetaris as a Lightning database.
-- Run in the Zetaris SQL Editor ONE statement at a time (Lightning SQL, see the participant guide 1.8).
-- Replace host/port/user/password with the values from your local .env (never commit them here).
-- From inside the Zetaris Docker network the collectors' Postgres is reachable at host.docker.internal.

CREATE LIGHTNING DATABASE QUORUM_COLLECT
  DESCRIPTION 'Quorum data-collection block: sources, documents, official_docs, quotes, coverage'
  OPTIONS (
    jdbc.url      'jdbc:postgresql://host.docker.internal:5433/quorum',
    jdbc.driver   'org.postgresql.Driver',
    jdbc.user     'quorum',
    jdbc.password 'quorum'
  );

-- Then confirm (each on its own):
-- SHOW LIGHTNING DATABASES;
-- SELECT id, source_id, title, access_level, wire_origin FROM QUORUM_COLLECT.public.documents ORDER BY published_at DESC LIMIT 20;
