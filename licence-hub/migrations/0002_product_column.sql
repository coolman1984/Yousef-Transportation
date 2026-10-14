-- Legacy databases missing product on licence_requests (fresh schema.sql already has it).
-- Prefer: node scripts/apply-migrations.mjs [--default-product <id>] [--local] <sqlite-path> (guarded).
-- Safe re-run on D1: column add may fail if product already exists — use apply-migrations.mjs instead.
-- For wrangler one-shot: substitute __DEFAULT_PRODUCT__ with your LICENCE_DEFAULT_PRODUCT (or first LICENCE_PRODUCTS id).
ALTER TABLE licence_requests ADD COLUMN product TEXT NOT NULL DEFAULT '__DEFAULT_PRODUCT__';
