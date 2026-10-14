#!/usr/bin/env node
/**
 * Guarded D1 migrations for local SQLite files or CI.
 * Usage: node scripts/apply-migrations.mjs [--local] [--default-product <id>] /path/to/d1.sqlite
 *
 * Default product id for 0002/0003 legacy DEFAULTs:
 *   --default-product, else LICENCE_DEFAULT_PRODUCT, else first LICENCE_PRODUCTS in wrangler.toml, else my-product.
 */
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function columnExists(db, table, column) {
  const rows = db.prepare(`PRAGMA table_info(${table})`).all();
  return rows.some((r) => r.name === column);
}

function migrationApplied(db, id) {
  try {
    return Boolean(db.prepare('SELECT 1 FROM schema_migrations WHERE id = ?').get(id));
  } catch {
    return false;
  }
}

function markApplied(db, id) {
  db.prepare('INSERT OR IGNORE INTO schema_migrations(id, applied_at) VALUES(?, ?)').run(id, Math.floor(Date.now() / 1000));
}

function ensureMigrationsTable(db) {
  db.exec(`CREATE TABLE IF NOT EXISTS schema_migrations (
  id TEXT PRIMARY KEY,
  applied_at INTEGER NOT NULL
);`);
}

function indexExists(db, name) {
  const row = db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?").get(name);
  return Boolean(row);
}

function readWranglerVars() {
  try {
    const text = readFileSync(join(root, 'wrangler.toml'), 'utf8');
    const vars = {};
    for (const line of text.split('\n')) {
      const m = line.match(/^([A-Z_][A-Z0-9_]*) = "(.*)"/);
      if (m) vars[m[1]] = m[2];
    }
    return vars;
  } catch {
    return {};
  }
}

export function resolveDefaultProduct(cliValue) {
  if (cliValue && String(cliValue).trim()) return String(cliValue).trim();
  if (process.env.LICENCE_DEFAULT_PRODUCT && String(process.env.LICENCE_DEFAULT_PRODUCT).trim()) {
    return String(process.env.LICENCE_DEFAULT_PRODUCT).trim();
  }
  const vars = readWranglerVars();
  if (vars.LICENCE_DEFAULT_PRODUCT && String(vars.LICENCE_DEFAULT_PRODUCT).trim()) {
    return String(vars.LICENCE_DEFAULT_PRODUCT).trim();
  }
  const products = String(vars.LICENCE_PRODUCTS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (products.length) return products[0];
  return 'my-product';
}

export function substituteDefaultProduct(sql, defaultProduct) {
  const id = String(defaultProduct || 'my-product').replace(/'/g, "''");
  return sql.replaceAll('__DEFAULT_PRODUCT__', id);
}

function loadMigrationSql(filename, defaultProduct) {
  const raw = readFileSync(join(root, 'migrations', filename), 'utf8');
  return substituteDefaultProduct(raw, defaultProduct);
}

function addColumnIfMissing(db, migrationId, table, column, ddl) {
  if (migrationApplied(db, migrationId)) return;
  if (columnExists(db, table, column)) {
    markApplied(db, migrationId);
    return;
  }
  db.exec(ddl);
  markApplied(db, migrationId);
}

/** Legacy rows: copy kind into licence_tier when tier column was added empty. */
function backfillLicenceTierFromKind(db) {
  const migrationId = '0001_backfill_licence_tier';
  if (migrationApplied(db, migrationId)) return;
  if (!columnExists(db, 'licence_requests', 'licence_tier')) return;
  db.exec(
    `UPDATE licence_requests SET licence_tier = 'trial' WHERE licence_tier = '' AND kind = 'trial'`,
  );
  db.exec(
    `UPDATE licence_requests SET licence_tier = 'permanent' WHERE licence_tier = '' AND kind = 'permanent'`,
  );
  db.exec(
    `UPDATE licence_requests SET licence_tier = 'paid'
     WHERE licence_tier = '' AND kind = 'monthly'
       AND licence_expiry IS NOT NULL AND TRIM(licence_expiry) != ''`,
  );
  if (columnExists(db, 'customers', 'licence_tier')) {
    db.exec(
      `UPDATE customers SET licence_tier = 'trial' WHERE licence_tier = '' AND kind = 'trial'`,
    );
    db.exec(
      `UPDATE customers SET licence_tier = 'permanent' WHERE licence_tier = '' AND kind = 'permanent'`,
    );
    db.exec(
      `UPDATE customers SET licence_tier = 'paid'
       WHERE licence_tier = '' AND kind = 'monthly'
         AND licence_expiry IS NOT NULL AND TRIM(licence_expiry) != ''`,
    );
  }
  markApplied(db, migrationId);
}

function dedupeCustomersProductDevice(db) {
  const dupes = db.prepare(
    'SELECT product, device FROM customers GROUP BY product, device HAVING COUNT(*) > 1',
  ).all();
  for (const { product, device } of dupes) {
    const rows = db.prepare(
      'SELECT rowid FROM customers WHERE product = ? AND device = ? ORDER BY created_at DESC, rowid DESC',
    ).all(product, device);
    for (let i = 1; i < rows.length; i++) {
      db.prepare('DELETE FROM customers WHERE rowid = ?').run(rows[i].rowid);
    }
  }
}

function applyCustomersProductMigration(db, defaultProduct) {
  const migrationId = '0003_customers_product';
  if (migrationApplied(db, migrationId)) return;
  if (!columnExists(db, 'customers', 'product')) {
    const sql = loadMigrationSql('0003_customers_product.sql', defaultProduct);
    const alterLine = sql
      .split('\n')
      .map((line) => line.trim())
      .find((line) => /^ALTER\s+TABLE/i.test(line));
    if (alterLine) db.exec(alterLine);
  }
  dedupeCustomersProductDevice(db);
  if (!indexExists(db, 'customers_product_device')) {
    db.exec('CREATE UNIQUE INDEX customers_product_device ON customers(product, device);');
  }
  markApplied(db, migrationId);
}

export function applyMigrations(db, options = {}) {
  const defaultProduct = resolveDefaultProduct(options.defaultProduct);
  ensureMigrationsTable(db);
  addColumnIfMissing(
    db,
    '0001_licence_requests_licence_tier',
    'licence_requests',
    'licence_tier',
    "ALTER TABLE licence_requests ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';",
  );
  addColumnIfMissing(
    db,
    '0001_licence_requests_licence_expiry',
    'licence_requests',
    'licence_expiry',
    'ALTER TABLE licence_requests ADD COLUMN licence_expiry TEXT;',
  );
  addColumnIfMissing(
    db,
    '0001_customers_licence_tier',
    'customers',
    'licence_tier',
    "ALTER TABLE customers ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';",
  );
  addColumnIfMissing(
    db,
    '0001_customers_licence_expiry',
    'customers',
    'licence_expiry',
    'ALTER TABLE customers ADD COLUMN licence_expiry TEXT;',
  );
  backfillLicenceTierFromKind(db);
  const productDdl = loadMigrationSql('0002_product_column.sql', defaultProduct).trim();
  addColumnIfMissing(db, '0002_product_column', 'licence_requests', 'product', productDdl);
  applyCustomersProductMigration(db, defaultProduct);
  return defaultProduct;
}

function parseCli(argv) {
  const out = { local: false, defaultProduct: null, dbPath: null };
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--local') {
      out.local = true;
      continue;
    }
    if (a === '--default-product') {
      out.defaultProduct = args[++i];
      continue;
    }
    if (!a.startsWith('-')) out.dbPath = a;
  }
  return out;
}

const cli = parseCli(process.argv);
if (cli.dbPath) {
  const db = new DatabaseSync(cli.dbPath);
  const used = applyMigrations(db, { defaultProduct: cli.defaultProduct });
  console.log('Migrations applied to', cli.dbPath, '(default product:', used + ')');
} else if (process.argv.length > 2) {
  console.error('Usage: node scripts/apply-migrations.mjs [--local] [--default-product <id>] <sqlite-path>');
  process.exit(1);
}
