import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyMigrations, resolveDefaultProduct, substituteDefaultProduct } from '../scripts/apply-migrations.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

test('fresh schema.sql needs no 0001 migration', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(join(root, 'schema.sql'), 'utf8'));
  const cols = db.prepare("PRAGMA table_info(licence_requests)").all().map((r) => r.name);
  assert.ok(cols.includes('licence_tier'));
  assert.ok(cols.includes('product'));
  const custCols = db.prepare('PRAGMA table_info(customers)').all().map((r) => r.name);
  assert.ok(custCols.includes('product'));
  const idx = db.prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'customers_product_device'").get();
  assert.ok(idx);
});

test('0002_product_column.sql contains ALTER for wrangler one-shot', () => {
  const sql = readFileSync(join(root, 'migrations/0002_product_column.sql'), 'utf8');
  assert.match(sql, /ALTER TABLE licence_requests ADD COLUMN product/i);
  assert.match(sql, /__DEFAULT_PRODUCT__/);
});

test('resolveDefaultProduct and SQL substitution', () => {
  assert.equal(resolveDefaultProduct('custom-id'), 'custom-id');
  const sql = substituteDefaultProduct("DEFAULT '__DEFAULT_PRODUCT__'", 'my-product');
  assert.match(sql, /DEFAULT 'my-product'/);
});

test('apply-migrations uses default product on legacy licence_requests', () => {
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
  applyMigrations(db, { defaultProduct: 'al-store' });
  db.exec("INSERT INTO licence_requests(id, poll_token_hash, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES('x','h','trial','d','dk','m','n','','','','pending',1,1)");
  const row = db.prepare('SELECT product FROM licence_requests WHERE id = ?').get('x');
  assert.equal(row.product, 'al-store');
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
  const applied = db.prepare('SELECT id FROM schema_migrations ORDER BY id').all().map((r) => r.id);
  assert.ok(applied.includes('0003_customers_product'));
});

test('0001 backfills licence_tier from kind on legacy rows', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE licence_requests (
    id TEXT PRIMARY KEY, poll_token_hash TEXT, kind TEXT, device TEXT, device_key TEXT,
    machine TEXT, nonce TEXT, shop TEXT, ref TEXT, version TEXT, status TEXT,
    stage TEXT, reason TEXT, code TEXT, licence_expiry TEXT, created_at INTEGER, updated_at INTEGER
  );`);
  db.exec(`CREATE TABLE customers (
    id TEXT PRIMARY KEY, shop TEXT, device TEXT, kind TEXT, serial TEXT,
    first_day TEXT, last_day TEXT, licence_expiry TEXT, created_at INTEGER
  );`);
  db.exec(`INSERT INTO licence_requests(id, poll_token_hash, kind, device, device_key, machine, nonce, shop, ref, version, status, licence_expiry, created_at, updated_at)
    VALUES('t1','h','trial','d','dk','m','n','','','','pending',NULL,1,1),
           ('m1','h','monthly','d2','dk2','m','n','','','','delivered','2028-01-01',1,1),
           ('m2','h','monthly','d3','dk3','m','n','','','','delivered',NULL,1,1)`);
  db.exec(`INSERT INTO customers(id, shop, device, kind, licence_expiry, created_at)
    VALUES('c1','S','DEV','permanent',NULL,1)`);
  applyMigrations(db);
  assert.equal(db.prepare('SELECT licence_tier FROM licence_requests WHERE id = ?').get('t1').licence_tier, 'trial');
  assert.equal(db.prepare('SELECT licence_tier FROM licence_requests WHERE id = ?').get('m1').licence_tier, 'paid');
  assert.equal(db.prepare('SELECT licence_tier FROM licence_requests WHERE id = ?').get('m2').licence_tier, '');
  assert.equal(db.prepare('SELECT licence_tier FROM customers WHERE id = ?').get('c1').licence_tier, 'permanent');
});

test('0003 dedupes duplicate customers before unique index', () => {
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
  db.exec(`INSERT INTO customers(id, shop, device, kind, created_at) VALUES('old', 'A', 'DEV1', 'trial', 1);`);
  db.exec(`INSERT INTO customers(id, shop, device, kind, created_at) VALUES('new', 'B', 'DEV1', 'trial', 9);`);
  applyMigrations(db);
  applyMigrations(db);
  const rows = db.prepare('SELECT id FROM customers WHERE device = ?').all('DEV1');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].id, 'new');
  const idx = db.prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'customers_product_device'").get();
  assert.ok(idx);
});
