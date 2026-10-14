import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyMigrations } from '../scripts/apply-migrations.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

test('fresh schema.sql needs no 0001 migration', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(join(root, 'schema.sql'), 'utf8'));
  const cols = db.prepare("PRAGMA table_info(licence_requests)").all().map((r) => r.name);
  assert.ok(cols.includes('licence_tier'));
  assert.ok(cols.includes('product'));
});

test('0002_product_column.sql contains ALTER for wrangler one-shot', () => {
  const sql = readFileSync(join(root, 'migrations/0002_product_column.sql'), 'utf8');
  assert.match(sql, /ALTER TABLE licence_requests ADD COLUMN product/i);
});

test('apply-migrations is safe to run twice on legacy-shaped db', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE licence_requests (
    id TEXT PRIMARY KEY, poll_token_hash TEXT, kind TEXT, device TEXT, device_key TEXT,
    machine TEXT, nonce TEXT, shop TEXT, ref TEXT, version TEXT, status TEXT,
    stage TEXT, reason TEXT, code TEXT, created_at INTEGER, updated_at INTEGER
  );`);
  db.exec(`CREATE TABLE customers (
    id TEXT PRIMARY KEY, shop TEXT, device TEXT, kind TEXT, serial TEXT,
    first_day TEXT, last_day TEXT, created_at INTEGER
  );`);
  applyMigrations(db);
  applyMigrations(db);
  const cols = db.prepare("PRAGMA table_info(licence_requests)").all().map((r) => r.name);
  assert.ok(cols.includes('licence_tier'));
  assert.ok(cols.includes('product'));
});
