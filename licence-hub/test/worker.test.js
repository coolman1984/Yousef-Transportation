import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPrivateKey } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import worker from '../src/worker.js';
import { d1FromDb, newD1 } from './d1-mock.js';
import { CSRF_COOKIE, signSession } from '../src/auth.js';
import { deviceKey } from '../src/licence-api.js';
import { BACKFILL_OWNER_MAX_STEPS_PER_CALL, TRIAL_GRANTS_BACKFILL_MARKER } from '../src/trial-grants.js';

const hubRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

function pemFromSeed(seed32) {
  const seed = Buffer.from(seed32);
  const pk = createPrivateKey({
    key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), seed]),
    format: 'der',
    type: 'pkcs8',
  });
  return pk.export({ type: 'pkcs8', format: 'pem' });
}

async function ownerFetch(e, path, { method = 'GET', body = null, csrf = 'owner-csrf' } = {}) {
  const exp = Math.floor(Date.now() / 1000) + 3600;
  await e.DB.prepare('INSERT OR REPLACE INTO owner_sessions(id, csrf, expires_at) VALUES(?, ?, ?)').bind('sess1', csrf, exp).run();
  const token = await signSession(e.SESSION_SECRET, 'sess1');
  const headers = {
    Cookie: `lh_session=${encodeURIComponent(token)}`,
    'Sec-Fetch-Site': 'same-origin',
  };
  if (body) {
    headers['Content-Type'] = 'application/json';
    body.csrf = csrf;
  }
  return worker.fetch(new Request(`https://hub.test${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined }), e);
}

const HEADERS_CHECK = ['Content-Security-Policy', 'Cache-Control', 'X-Content-Type-Options'];

function mockAssets() {
  return {
    fetch(req) {
      const path = new URL(req.url).pathname;
      const body = path.includes('index.html') ? '<html><script src="/owner/index-boot.js"></script></html>' : '/* css */';
      return new Response(body, { headers: { 'Content-Type': 'text/html' } });
    },
  };
}

function env(over = {}) {
  return {
    DB: newD1(),
    ASSETS: mockAssets(),
    SESSION_SECRET: 'sess',
    ...over,
  };
}

function pre0004SchemaSqlWithoutMigrations() {
  const full = readFileSync(join(hubRoot, 'schema.sql'), 'utf8');
  const trialIdx = full.indexOf('CREATE TABLE IF NOT EXISTS trial_grants');
  assert.ok(trialIdx > 0);
  return full.slice(0, trialIdx).replace(
    /CREATE TABLE IF NOT EXISTS schema_migrations[\s\S]*?;\s*\n/,
    '',
  );
}

function d1AfterWrangler0004And0005() {
  const db = new DatabaseSync(':memory:');
  db.exec(pre0004SchemaSqlWithoutMigrations());
  assert.equal(
    db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").get(),
    undefined,
  );
  db.exec(readFileSync(join(hubRoot, 'migrations/0004_trial_grants.sql'), 'utf8'));
  db.exec(readFileSync(join(hubRoot, 'migrations/0005_trial_grants_backfill_staging.sql'), 'utf8'));
  assert.ok(db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").get());
  return d1FromDb(db);
}

async function postTrialRequest(e, nonce) {
  return worker.fetch(new Request('https://hub.test/licence/request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': '1.2.3.4' },
    body: JSON.stringify({
      product: 'trip-orders',
      kind: 'trial',
      device: '7KD2M-QX9TP',
      machine: 'a'.repeat(64),
      nonce,
      shop: 'Shop',
      ref: '',
      version: '1.0',
    }),
  }), e);
}

test('owner dashboard is served at /owner/ with security headers', async () => {
  const e = env();
  await e.DB.prepare('INSERT INTO owner_sessions(id, csrf, expires_at) VALUES(?, ?, ?)').bind('s1', 'c', Math.floor(Date.now() / 1000) + 3600).run();
  const token = await import('../src/auth.js').then((m) => m.signSession('sess', 's1'));
  const req = new Request('https://hub.test/owner/', {
    headers: { Cookie: `lh_session=${encodeURIComponent(token)}` },
  });
  const res = await worker.fetch(req, e);
  assert.equal(res.status, 200);
  for (const h of HEADERS_CHECK) assert.ok(res.headers.get(h), h);
  assert.ok(!String(await res.text()).includes('import {'), 'no inline module bootstrap');
});

test('logout without session does not send clearing Set-Cookie', async () => {
  const e = env();
  const res = await worker.fetch(new Request('https://hub.test/owner/logout', { method: 'POST' }), e);
  assert.equal(res.status, 303);
  assert.equal(res.headers.get('Set-Cookie'), null);
});

test('/owner/index.html redirects to /owner/', async () => {
  const e = env();
  const res = await worker.fetch(new Request('https://hub.test/owner/index.html'), e);
  assert.equal(res.status, 308);
  assert.equal(res.headers.get('Location'), 'https://hub.test/owner/');
});

test('public calendar limits each IP to 120 requests per ten minutes without D1 or secrets', async (t) => {
  let nowMs = 600 * 1000 * 3000000 + 1000;
  t.mock.method(Date, 'now', () => nowMs);
  const e = {
    get DB() { assert.fail('time must not use D1'); },
    get SESSION_SECRET() { assert.fail('time must not read session secrets'); },
  };
  const request = (ip, suffix = '') => new Request('https://hub.test/licence/time' + suffix, {
    headers: { 'CF-Connecting-IP': ip, 'X-Forwarded-For': crypto.randomUUID() },
  });
  for (let i = 0; i < 120; i++) {
    const res = await worker.fetch(request('192.0.2.1'), e);
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.ok(body.calendar_day);
    assert.equal(body.signed, false);
    assert.equal(body.kid, undefined);
  }
  const blocked = await worker.fetch(request('192.0.2.1', '?retry=1'), e);
  assert.equal(blocked.status, 429);
  assert.deepEqual(await blocked.json(), { error: 'rate' });
  assert.equal(blocked.headers.get('Retry-After'), '599');
  for (const h of HEADERS_CHECK) assert.ok(blocked.headers.get(h), h);
  assert.equal(blocked.headers.get('Cache-Control'), 'no-store');
  assert.equal((await worker.fetch(request('192.0.2.2'), e)).status, 200);
  nowMs += 598 * 1000;
  assert.equal((await worker.fetch(request('192.0.2.1'), e)).status, 429);
  nowMs += 1000;
  assert.equal((await worker.fetch(request('192.0.2.1'), e)).status, 200);
});

test('GET /owner/api/products is allowed before POST-only gate', async () => {
  const e = env({
    LICENCE_PRODUCTS: 'trip-orders,al-store',
    LICENCE_PRODUCT_LABELS: '{"trip-orders":"طلبات الرحلات","al-store":"المتجر"}',
  });
  const res = await ownerFetch(e, '/owner/api/products');
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.deepEqual([...data.products].sort(), ['al-store', 'trip-orders']);
  assert.equal(data.default_product, 'trip-orders');
  assert.equal(data.labels['trip-orders'], 'طلبات الرحلات');
});

test('GET /owner/api/products honors LICENCE_DEFAULT_PRODUCT', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders,al-store', LICENCE_DEFAULT_PRODUCT: 'al-store' });
  const data = await (await ownerFetch(e, '/owner/api/products')).json();
  assert.equal(data.default_product, 'al-store');
});

test('GET /owner/api/capabilities returns per-product paid flags', async () => {
  const e = env({
    LICENCE_PRODUCTS: 'trip-orders,al-store',
    PAID_SIGNING_KEY_AL_STORE: pemFromSeed(Buffer.alloc(32, 93)),
  });
  const res = await ownerFetch(e, '/owner/api/capabilities');
  const data = await res.json();
  assert.equal(data.products['trip-orders'].paid_available, false);
  assert.equal(data.products['al-store'].paid_available, true);
});

test('GET /owner/api/customers shows strongest currentTerm not newest issued row', async () => {
  const e = env({ PAID_SIGNING_KEY: pemFromSeed(Buffer.alloc(32, 94)) });
  const device = 'ABCD2EFGH3';
  const dkey = deviceKey(device);
  const t = 10;
  await e.DB.prepare(
    'INSERT INTO customers(id, product, shop, device, kind, licence_tier, licence_expiry, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('cust-perm', 'trip-orders', 'Shop', device, 'permanent', 'permanent', '', t).run();
  await e.DB.prepare(
    `INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, code, licence_tier, licence_expiry, created_at, updated_at)
     VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind('perm-old', 'hp1', 'trip-orders', 'permanent', device, dkey, 'a'.repeat(64), 'n1', 'Shop', '', '', 'delivered', 'PERM-CODE', 'permanent', '', t, t).run();
  await e.DB.prepare(
    `INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, code, licence_tier, licence_expiry, created_at, updated_at)
     VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind('paid-newer', 'hp2', 'trip-orders', 'monthly', device, dkey, 'a'.repeat(64), 'n2', 'Shop', '', '', 'issued', 'PAID-CODE', 'paid', '2026-11-14', t + 5, t + 50).run();
  const res = await ownerFetch(e, '/owner/api/customers');
  const data = await res.json();
  const row = (data.items || []).find((i) => i.device === device && i.product === 'trip-orders');
  assert.equal(row.licence_tier, 'permanent');
});

test('GET /owner/api/customers lists one row per device and product', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders,al-store' });
  const device = 'ABCD2EFGH3';
  const dkey = deviceKey(device);
  const t = 10;
  for (const [cid, product] of [['cust-to', 'trip-orders'], ['cust-al', 'al-store']]) {
    await e.DB.prepare(
      'INSERT INTO customers(id, product, shop, device, kind, licence_tier, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)',
    ).bind(cid, product, 'Shop', device, 'trial', 'trial', t).run();
  }
  for (const [id, product] of [['c1', 'trip-orders'], ['c2', 'al-store']]) {
    await e.DB.prepare(
      'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, code, licence_tier, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind(id, 'h' + id, product, 'trial', device, dkey, 'a'.repeat(64), 'n' + id, 'Shop', '', '', 'issued', 'CODE-' + product, 'trial', t, t + 1).run();
  }
  const res = await ownerFetch(e, '/owner/api/customers');
  const data = await res.json();
  const products = (data.items || []).filter((i) => i.device === device).map((i) => i.product).sort();
  assert.deepEqual(products, ['al-store', 'trip-orders']);
});

test('customer dashboard serves 200 records within D1 Free 50-query cap', async () => {
  const e = env();
  const count = 200;
  for (let n = 0; n < count; n++) {
    const device = 'ABCDEF' + String(n).padStart(4, '0');
    const product = n % 2 === 0 ? 'trip-orders' : 'al-store';
    await e.DB.prepare(
      'INSERT INTO customers(id, product, shop, device, kind, licence_tier, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)',
    ).bind('customer-' + n, product, 'Shop', device, 'trial', 'trial', 1000 + n).run();
    const tier = n === 199 ? 'permanent' : (n % 3 === 0 ? 'paid' : 'trial');
    await e.DB.prepare(
      'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, licence_tier, licence_expiry, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind('grant-' + n, 'hash-' + n, product, tier === 'paid' ? 'monthly' : tier,
      device, deviceKey(device), 'a'.repeat(64), 'nonce-' + n, 'Shop', '', '',
      'issued', tier, tier === 'paid' ? '2027-12-31' : '', 1000 + n, 1000 + n).run();
  }
  const db = e.DB;
  let queries = 0;
  e.DB = {
    prepare(sql) {
      queries++;
      if (queries > 50) throw Error('D1 Free query budget exceeded');
      return db.prepare(sql);
    },
  };
  const res = await ownerFetch(e, '/owner/api/customers');
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.items.length, count);
  assert.ok(queries < 20, `queries: ${queries}`);
  assert.equal(data.items.find((x) => x.device === 'ABCDEF0199')?.licence_tier, 'permanent');
  assert.equal(data.items.find((x) => x.device === 'ABCDEF0000')?.licence_tier, 'paid');
  assert.equal(data.items.find((x) => x.device === 'ABCDEF0000')?.licence_expiry, '2027-12-31');
});

test('owner offline API signs with the product sent in the body', async () => {
  const e = env({
    LICENCE_PRODUCTS: 'trip-orders,al-store',
    LICENCE_SIGNING_KEY_AL_STORE: pemFromSeed(Buffer.alloc(32, 92)),
  });
  const res = await ownerFetch(e, '/owner/api/offline', {
    method: 'POST',
    body: {
      device: 'ABCD2EFGH3',
      shop: 'متجر',
      product: 'al-store',
      grant: 'trial',
    },
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.ok(data.code);
  const row = await e.DB.prepare('SELECT product FROM licence_requests WHERE device_key = ? ORDER BY created_at DESC LIMIT 1')
    .bind(deviceKey('ABCD2EFGH3')).first();
  assert.equal(row.product, 'al-store');
});

test('PR B r3: owner backfill route caps max_steps per invocation', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders' });
  const win = { last: '2026-06-14' };
  for (let i = 0; i < 60; i++) {
    const device = `CAP${String(i).padStart(2, '0')}-DEV${String(i).padStart(2, '0')}`;
    await e.DB.prepare(
      `INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
        status, licence_tier, licence_expiry, created_at, updated_at)
       VALUES(?, 'h', 'trip-orders', 'trial', ?, ?, ?, ?, '', '', '', 'delivered', 'trial', ?, 1, 1)`,
    ).bind(`cap-${i}`, device, deviceKey(device), 'a'.repeat(64), `n-${i}`, win.last).run();
  }
  const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', {
    method: 'POST',
    body: { max_steps: 500 },
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.ok, true);
  assert.ok(data.steps <= 2);
});

function passThroughD1(inner, prepare) {
  return {
    prepare,
    batch: (stmts) => inner.batch(stmts),
  };
}

test('owner backfill returns 500 when 0005 tables are missing', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders' });
  await e.DB.prepare('DROP TABLE trial_grants_backfill_progress').bind().run();
  await e.DB.prepare('DROP TABLE trial_grants_backfill_staging').bind().run();
  await e.DB.prepare('DROP TABLE trial_issue_batch_sentinel').bind().run();
  const stillThere = await e.DB.prepare(
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'",
  ).bind().first();
  assert.equal(stillThere.name, 'schema_migrations');

  const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', { method: 'POST', body: {} });
  assert.equal(res.status, 500);
  const data = await res.json();
  assert.deepEqual(Object.keys(data), ['ok', 'error', 'message', 'complete', 'steps']);
  assert.equal(data.ok, false);
  assert.equal(data.error, 'backfill_failed');
  assert.match(data.message, /no such table: trial_grants_backfill_progress/);
  assert.equal(data.complete, false);
  assert.equal(data.steps, 0);
  const marker = await e.DB.prepare('SELECT id FROM schema_migrations WHERE id = ?')
    .bind(TRIAL_GRANTS_BACKFILL_MARKER).first();
  assert.equal(marker, null);
});

test('owner backfill success shape stays ok, complete, and bounded steps', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders' });
  const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', {
    method: 'POST',
    body: { max_steps: 500 },
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.deepEqual(Object.keys(data), ['ok', 'complete', 'steps']);
  assert.equal(data.ok, true);
  assert.equal(data.complete, true);
  assert.equal(data.steps, 1);
  assert.ok(data.steps <= BACKFILL_OWNER_MAX_STEPS_PER_CALL);
  const marker = await e.DB.prepare('SELECT id FROM schema_migrations WHERE id = ?')
    .bind(TRIAL_GRANTS_BACKFILL_MARKER).first();
  assert.equal(marker.id, TRIAL_GRANTS_BACKFILL_MARKER);
});

test('owner backfill reports steps finished before a later step fails', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders' });
  const win = { last: '2026-06-14' };
  for (let i = 0; i < 24; i++) {
    const device = `PAR${String(i).padStart(2, '0')}-DEV${String(i).padStart(2, '0')}`;
    await e.DB.prepare(
      `INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
        status, licence_tier, licence_expiry, created_at, updated_at)
       VALUES(?, 'h', 'trip-orders', 'trial', ?, ?, ?, ?, '', '', '', 'delivered', 'trial', ?, 1, 1)`,
    ).bind(`partial-${i}`, device, deviceKey(device), 'b'.repeat(64), `np-${i}`, win.last).run();
  }
  const inner = e.DB;
  let progressReads = 0;
  e.DB = passThroughD1(inner, (sql) => {
    const stmt = inner.prepare(sql);
    if (String(sql) !== 'SELECT phase, after_rowid FROM trial_grants_backfill_progress WHERE id = 1') return stmt;
    return {
      bind(...args) {
        const bound = stmt.bind(...args);
        return {
          async run() { return bound.run(); },
          async all() { return bound.all(); },
          async first() {
            progressReads += 1;
            if (progressReads >= 2) throw new Error('step_two_failed');
            return bound.first();
          },
        };
      },
    };
  });

  const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', {
    method: 'POST',
    body: { max_steps: 2 },
  });
  assert.equal(res.status, 500);
  const data = await res.json();
  assert.equal(data.ok, false);
  assert.equal(data.error, 'backfill_failed');
  assert.equal(data.message, 'step_two_failed');
  assert.equal(data.complete, false);
  assert.equal(data.steps, 1);
  assert.ok(progressReads >= 2);
  const staged = await inner.prepare('SELECT COUNT(*) AS n FROM trial_grants_backfill_staging').bind().first();
  assert.ok(staged.n > 0);
  const marker = await inner.prepare('SELECT id FROM schema_migrations WHERE id = ?')
    .bind(TRIAL_GRANTS_BACKFILL_MARKER).first();
  assert.equal(marker, null);
});

test('owner backfill returns complete null when the completion probe fails', async () => {
  const e = env({ LICENCE_PRODUCTS: 'trip-orders' });
  const inner = e.DB;
  e.DB = passThroughD1(inner, (sql) => {
    if (String(sql).includes('FROM schema_migrations')) {
      return {
        bind() {
          return {
            async first() { throw new Error('completion_probe_failed'); },
            async run() { throw new Error('completion_probe_failed'); },
            async all() { throw new Error('completion_probe_failed'); },
          };
        },
      };
    }
    return inner.prepare(sql);
  });

  const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', { method: 'POST', body: {} });
  assert.equal(res.status, 500);
  const data = await res.json();
  assert.deepEqual(data, {
    ok: false,
    error: 'backfill_failed',
    message: 'completion_probe_failed',
    complete: null,
    steps: 0,
  });
});

test('PR B r3: owner approve maps already_used to 400', async () => {
  const e = env({ LICENCE_SIGNING_KEY: pemFromSeed(Buffer.alloc(32, 88)), LICENCE_PRODUCTS: 'trip-orders' });
  const device = '7KD2M-QX9TP';
  const dkey = deviceKey(device);
  const machine = 'a'.repeat(64);
  const reqId = 'req-already-used-owner';
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(reqId, 'h', 'trip-orders', 'trial', device, dkey, machine, 'n-au', 'Shop', '', '', 'pending', 1, 1).run();
  const { trialGrantStatements } = await import('../src/trial-grants.js');
  const { machineLockKey, onlineDeviceLockKey } = await import('../src/licence-api.js');
  await e.DB.batch(await trialGrantStatements(
    e, 'trip-orders', device, [machine], { first_day: '2020-01-01', last_day: '2020-01-14' }, reqId,
  ));
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(onlineDeviceLockKey('trip-orders', dkey), reqId, 1).run();
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(machineLockKey(machine), reqId, 1).run();
  const res = await ownerFetch(e, '/owner/api/approve', {
    method: 'POST',
    body: { id: reqId, grant: 'trial' },
  });
  assert.equal(res.status, 400);
  assert.deepEqual(await res.json(), { error: 'already_used', message: 'already_used' });
  const row = await e.DB.prepare('SELECT status, reason FROM licence_requests WHERE id = ?').bind(reqId).first();
  assert.equal(row.status, 'refused');
  assert.equal(row.reason, 'already_used');
});

test('PR B r5: owner approve of 2nd pending trial on a machine whose window ended -> 409 trial_expired, not 404', async () => {
  const e = env({ LICENCE_SIGNING_KEY: pemFromSeed(Buffer.alloc(32, 88)), LICENCE_PRODUCTS: 'trip-orders' });
  const device = '7KD2M-QX9TP';
  const machine = 'b'.repeat(64);
  const reqId = 'req-second-on-machine';
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(reqId, 'h', 'trip-orders', 'trial', device, deviceKey(device), machine, 'n-2nd', 'Shop', '', '', 'pending', 1, 1).run();
  const { trialGrantStatements } = await import('../src/trial-grants.js');
  await e.DB.batch(await trialGrantStatements(
    e, 'trip-orders', device, [machine], { first_day: '2020-01-01', last_day: '2020-01-14' }, 'req-first-on-machine',
  ));
  const res = await ownerFetch(e, '/owner/api/approve', { method: 'POST', body: { id: reqId, grant: 'trial' } });
  assert.equal(res.status, 409);
  assert.deepEqual(await res.json(), { error: 'trial_expired' });
  const row = await e.DB.prepare('SELECT status, reason FROM licence_requests WHERE id = ?').bind(reqId).first();
  assert.equal(row.status, 'refused');
  assert.equal(row.reason, 'trial_expired');
});

test('owner approve paid without PAID_SIGNING_KEY returns 503 and keeps pending', async () => {
  const e = env({ LICENCE_SIGNING_KEY: pemFromSeed(Buffer.alloc(32, 97)) });
  const device = 'ABCD2EFGH3';
  const dkey = deviceKey(device);
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('req-paid-miss', 'h', 'trip-orders', 'monthly', device, dkey, 'a'.repeat(64), 'n', 'Shop', '', '', 'pending', 1, 1).run();
  const res = await ownerFetch(e, '/owner/api/approve', {
    method: 'POST',
    body: { id: 'req-paid-miss', grant: 'paid', paid_until: '2028-06-01' },
  });
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), { error: 'paid_key_missing' });
  const row = await e.DB.prepare('SELECT status FROM licence_requests WHERE id = ?').bind('req-paid-miss').first();
  assert.equal(row.status, 'pending');
});

test('PR B r5: wrangler 0004+0005 on legacy db without schema_migrations enables trial and owner backfill', async () => {
  const e = env({
    LICENCE_PRODUCTS: 'trip-orders',
    TRIAL_DAYS: '14',
    LICENCE_CALENDAR_TZ: 'Africa/Cairo',
    PENDING_TTL_SEC: '900',
  });
  e.DB = d1AfterWrangler0004And0005();
  const { isTrialGrantsBackfillComplete } = await import('../src/trial-grants.js');
  assert.equal(await isTrialGrantsBackfillComplete(e), false);

  let complete = false;
  for (let i = 0; i < 20 && !complete; i++) {
    const res = await ownerFetch(e, '/owner/api/backfill-trial-grants', { method: 'POST', body: {} });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.ok, true);
    complete = data.complete;
  }
  assert.equal(complete, true);
  assert.equal(await isTrialGrantsBackfillComplete(e), true);
  const marker = await e.DB.prepare('SELECT id FROM schema_migrations WHERE id = ?')
    .bind(TRIAL_GRANTS_BACKFILL_MARKER).first();
  assert.equal(marker.id, TRIAL_GRANTS_BACKFILL_MARKER);

  const ok = await postTrialRequest(e, 'wrangler-after-backfill');
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).status, 'pending');
});

test('calendar limiter bounds stored IPs and frees them at the next window', async (t) => {
  let nowMs = 600 * 1000 * 3000010;
  t.mock.method(Date, 'now', () => nowMs);
  const request = (ip) => new Request('https://hub.test/licence/time', {
    headers: { 'CF-Connecting-IP': ip },
  });
  for (let i = 0; i < 5000; i++) {
    assert.equal((await worker.fetch(request(`test-ip-${i}`), {})).status, 200);
  }
  assert.equal((await worker.fetch(request('new-ip'), {})).status, 429);
  assert.equal((await worker.fetch(request('test-ip-0'), {})).status, 200);
  nowMs += 600 * 1000;
  assert.equal((await worker.fetch(request('new-ip'), {})).status, 200);
});
