-- Migration 005 (2026-10-26, Anastasia/Claude Code; asked in the PR #28 review): rewrite the canonical_url of Newsmax rows
-- stored before the section fold (collectors/common.py canonicalize) to the folded form
-- https://www.newsmax.com/<slug>/<yyyy>/<mm>/<dd>/id/<n>, so a URL seen again after the deploy refreshes its row instead of
-- inserting a second one, and a later edit links to the right row with supersedes_id.
-- Within each folded (canonical_url, content_hash) group only the oldest row (smallest id) is rewritten; its section
-- twins (the 3 pairs of 2026-10-26) keep their old canonical_url, because UNIQUE (canonical_url, content_hash) forbids
-- two rows with the folded pair and the rewritten twin already catches future fetches. documents.url is never changed.
-- Idempotent: an already folded row has new_url = canonical_url and is skipped.
BEGIN;
WITH folded AS (
    SELECT id, content_hash, canonical_url,
           regexp_replace(canonical_url,
               '^(https?://[^/]*newsmax\.com)(?:/[a-z0-9-]+)*?/([a-z0-9-]+/[0-9]{4}/[0-9]{2}/[0-9]{2}/id/[0-9]+)$',
               '\1/\2') AS new_url
    FROM documents
    WHERE source_id = 'newsmax'
),
ranked AS (
    SELECT f.*, row_number() OVER (PARTITION BY new_url, content_hash ORDER BY id) AS rn
    FROM folded f
    WHERE f.new_url <> f.canonical_url
)
UPDATE documents d
SET canonical_url = r.new_url
FROM ranked r
WHERE d.id = r.id
  AND r.rn = 1
  AND NOT EXISTS (SELECT 1 FROM documents o WHERE o.canonical_url = r.new_url AND o.content_hash = r.content_hash);
COMMIT;
