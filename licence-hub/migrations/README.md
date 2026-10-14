# D1 migrations

## Fresh database

```bash
npx wrangler d1 execute <database> --remote --file=schema.sql
```

`schema.sql` is complete for new hubs. **Do not run `0001` on a fresh database** — those columns are already in `schema.sql`.

## Existing database (created before tier/expiry columns)

Run migrations **before** deploying a worker that writes `licence_tier` / `licence_expiry`:

```bash
node scripts/apply-migrations.mjs --local   # or pass D1 via wrangler
# Production:
npx wrangler d1 execute <database> --remote --file=migrations/0001_licence_tier_expiry.sql
npx wrangler d1 execute <database> --remote --file=migrations/0002_product_column.sql
```

`scripts/apply-migrations.mjs` skips `ALTER` when `pragma_table_info` shows the column already exists (safe to re-run).

## Deploy order

1. Apply any pending migrations on D1.
2. `npx wrangler deploy`

Deploying the worker before migrations on an old database will break issuance (missing columns).
