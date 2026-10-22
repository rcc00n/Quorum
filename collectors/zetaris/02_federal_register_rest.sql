-- Federal Register as a live REST table in Zetaris (no key). Shows the "SQL across sources" story for the judges:
-- a JOIN between live government documents and the collected outlet coverage.
-- Pattern copied from zetaris/getting-started open_data/rest_apis (PokeAPI recipe); run ONE statement at a time.
-- Adjust the option names if your bundle's recipe differs; the getting-started repo is the reference.

CREATE LIGHTNING DATABASE FEDREG_REST
  DESCRIPTION 'Federal Register documents API, live'
  OPTIONS (
    rest.url        'https://www.federalregister.gov/api/v1/documents.json?conditions[term]=Ukraine&order=newest&per_page=50',
    rest.method     'GET',
    rest.format     'json',
    rest.rootpath   '$.results[*]'
  );

CREATE SCHEMASTORE CONTAINER fedreg;

CREATE LIGHTNING REST TABLE fedreg_documents
  FROM FEDREG_REST
  COLUMNS (
    document_number  STRING  PATH '$.document_number',
    title            STRING  PATH '$.title',
    type             STRING  PATH '$.type',
    publication_date STRING  PATH '$.publication_date',
    html_url         STRING  PATH '$.html_url'
  );

-- Example join for the demo: which collected outlet stories appeared within two days of each FR document.
-- SELECT f.document_number, f.title AS official_title, d.source_id, d.title AS outlet_title
-- FROM fedreg.fedreg_documents f
-- JOIN QUORUM_COLLECT.public.documents d
--   ON d.topic_id = 'ukraine-aid'
--  AND d.published_at BETWEEN CAST(f.publication_date AS TIMESTAMP) AND CAST(f.publication_date AS TIMESTAMP) + INTERVAL 2 DAYS
-- ORDER BY f.publication_date DESC;
