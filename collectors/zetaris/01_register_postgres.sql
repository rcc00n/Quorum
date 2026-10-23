-- Register the collectors' Postgres in Zetaris as a JDBC datasource and import its tables.
-- Syntax per zetaris/getting-started docs/guides/zetaris-lightning-sql-commands.md (CREATE DATASOURCE, not
-- CREATE LIGHTNING DATABASE, which is for file/REST sources). Run ONE statement at a time, as an Administrator.
-- From inside the Zetaris Docker network the collectors' Postgres (docker container quorum-pg, host port 5433)
-- is reachable at host.docker.internal. Credentials below are the local dev defaults from collectors/README.md.

CREATE DATASOURCE QUORUM_COLLECT DESCRIBE BY "Quorum data-collection block: sources, documents, official_docs, quotes, coverage" OPTIONS (
  jdbcdriver "org.postgresql.Driver",
  jdbcurl "jdbc:postgresql://host.docker.internal:5433/quorum",
  username "quorum",
  password "quorum",
  fetchsize "1000"
);

REGISTER DATASOURCE TABLES ('sources', 'topics', 'documents', 'official_docs', 'quotes', 'coverage') FROM QUORUM_COLLECT;

-- Checks (each on its own):
-- SHOW DATASOURCES;
-- SHOW DATASOURCE TABLES QUORUM_COLLECT WITH STATISTICS;
-- SELECT source_id, title, access_level, wire_origin FROM QUORUM_COLLECT.documents ORDER BY published_at DESC LIMIT 20;
-- SELECT s.flank, count(*) FROM QUORUM_COLLECT.documents d JOIN QUORUM_COLLECT.sources s ON s.id = d.source_id GROUP BY s.flank;
