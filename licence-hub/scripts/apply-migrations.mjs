#!/usr/bin/env node
/**
 * Guarded D1 migrations for local SQLite files or CI.
 * Usage: node scripts/apply-migrations.mjs [--local] /path/to/d1.sqlite
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

function addColumnIfMissing(db, migrationId, table, column, ddl) {
  if (migrationApplied(db, migrationId)) return;
  if (columnExists(db, table, column)) {
    markApplied(db, migrationId);
    return;
  }
  db.exec(ddl);
  markApplied(db, migrationId);
}

export function applyMigrations(db) {
  ensureMigrationsTable(db);
  addColumnIfMissing(
    db,
    '0001_licence_tier_expiry',
    'licence_requests',
    'licence_tier',
    "ALTER TABLE licence_requests ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';\n"
      + 'ALTER TABLE licence_requests ADD COLUMN licence_expiry TEXT;\n'
      + "ALTER TABLE customers ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';\n"
      + 'ALTER TABLE customers ADD COLUMN licence_expiry TEXT;',
  );
  addColumnIfMissing(
    db,
    '0002_product_column',
    'licence_requests',
    'product',
    "ALTER TABLE licence_requests ADD COLUMN product TEXT NOT NULL DEFAULT 'trip-orders';",
  );
}

const cliArgs = process.argv.slice(2).filter((a) => a !== '--local');
const dbPath = cliArgs[0];
if (dbPath) {
  const db = new DatabaseSync(dbPath);
  applyMigrations(db);
  console.log('Migrations applied to', dbPath);
} else if (process.argv.length > 2) {
  console.error('Usage: node scripts/apply-migrations.mjs [--local] <sqlite-path>');
  process.exit(1);
}
