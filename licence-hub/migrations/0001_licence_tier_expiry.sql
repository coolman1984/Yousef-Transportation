-- Legacy only: tier/expiry columns (already in schema.sql for new hubs).
-- Do NOT run on a database created from current schema.sql — use migrations/README.md.
-- Safe re-run: node scripts/apply-migrations.mjs
ALTER TABLE licence_requests ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';
ALTER TABLE licence_requests ADD COLUMN licence_expiry TEXT;
ALTER TABLE customers ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';
ALTER TABLE customers ADD COLUMN licence_expiry TEXT;
-- Backfill (also run by scripts/apply-migrations.mjs after columns exist):
-- UPDATE licence_requests SET licence_tier = 'trial' WHERE licence_tier = '' AND kind = 'trial';
-- UPDATE licence_requests SET licence_tier = 'permanent' WHERE licence_tier = '' AND kind = 'permanent';
-- UPDATE licence_requests SET licence_tier = 'paid' WHERE licence_tier = '' AND kind = 'monthly'
--   AND licence_expiry IS NOT NULL AND TRIM(licence_expiry) != '';
