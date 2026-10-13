import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash, createPrivateKey } from 'node:crypto';
import { newD1 } from './d1-mock.js';
import {
  handleLicence, approveRequest, refuseRequest, issueOfflineCustomer, derivePollToken, purgeStaleCodes,
  deviceKey, deviceLockKey, migrateLegacyTrialLocks, trialUsedForDevice, REASON_PAID_IN_STUDIO,
} from '../src/licence-api.js';
import { importSigningKey } from '../src/afcodes.js';

const SECRET = 'test-session-secret-0123456789abcdef';
const MACHINE_A = 'a'.repeat(64);
const MACHINE_B = 'b'.repeat(64);

function pollHash(token) {
  return createHash('sha256').update(token).digest('hex');
}

function pemFromSeed(seed32) {
  const seed = Buffer.from(seed32);
  const pk = createPrivateKey({
    key: Buffer.concat([Buffer.from('302e020100300506032b657004220420', 'hex'), seed]),
    format: 'der',
    type: 'pkcs8',
  });
  return pk.export({ type: 'pkcs8', format: 'pem' });
}

function env() {
  return {
    DB: newD1(),
    SESSION_SECRET: SECRET,
    LICENCE_PRODUCTS: 'trip-orders',
    TRIAL_DAYS: '14',
    LICENCE_CALENDAR_TZ: 'Africa/Cairo',
    PENDING_TTL_SEC: '900',
  };
}

function body(over = {}) {
  return {
    product: 'trip-orders',
    kind: 'trial',
    device: '7KD2M-QX9TP',
    machine: MACHINE_A,
    nonce: 'nonce-' + crypto.randomUUID(),
    shop: 'Shop',
    ref: 'ref',
    version: '1.0',
    ...over,
  };
}

async function postRequest(e, payload) {
  const req = new Request('https://hub.test/licence/request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': '1.2.3.4' },
    body: JSON.stringify(payload),
  });
  const res = await handleLicence(req, e, new URL(req.url));
  return { res, data: await res.json() };
}

async function getStatus(e, id, poll) {
  const req = new Request('https://hub.test/licence/status?id=' + id, {
    method: 'GET',
    headers: { Authorization: 'Bearer ' + poll },
  });
  const res = await handleLicence(req, e, new URL(req.url));
  return { res, data: await res.json() };
}

test('monthly and permanent requests are refused at submit', async () => {
  const e = env();
  for (const kind of ['monthly', 'permanent']) {
    const { data } = await postRequest(e, body({ kind }));
    assert.equal(data.status, 'refused');
    assert.equal(data.reason, REASON_PAID_IN_STUDIO);
    assert.ok(data.poll_token);
  }
});

test('nonce replay returns the same poll token', async () => {
  const e = env();
  const payload = body();
  const first = await postRequest(e, payload);
  const second = await postRequest(e, payload);
  assert.equal(second.data.replay, true);
  assert.equal(second.data.poll_token, first.data.poll_token);
  assert.equal(second.data.id, first.data.id);
});

test('losing concurrent approval never exposes issued code on status poll', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 19)));
  const device = '7KD2M-QX9TP';
  const dkey = deviceKey(device);
  const t = 1;
  const pollA = await derivePollToken(SECRET, 'n-a');
  const pollB = await derivePollToken(SECRET, 'n-b');
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('a', pollHash(pollA), 'trip-orders', 'trial', device, dkey, MACHINE_A, 'n-a', '', '', '', 'pending', t, t).run();
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('b', pollHash(pollB), 'trip-orders', 'trial', device, dkey, MACHINE_B, 'n-b', '', '', '', 'pending', t, t).run();
  const [signedA, signedB] = await Promise.all([approveRequest(e, 'a', key), approveRequest(e, 'b', key)]);
  const winners = [signedA, signedB].filter((s) => s?.code);
  assert.equal(winners.length, 1);
  const stB = await getStatus(e, 'b', pollB);
  const stA = await getStatus(e, 'a', pollA);
  const issued = [stA.data, stB.data].filter((d) => d.status === 'issued' && d.code);
  assert.equal(issued.length, 1);
});

test('only one trial wins on concurrent approval for the same device', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 9)));
  const device = '7KD2M-QX9TP';
  const dkey = deviceKey(device);
  const t = 1;
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('a', 'h1', 'trip-orders', 'trial', device, dkey, MACHINE_A, 'n1', '', '', '', 'pending', t, t).run();
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('b', 'h2', 'trip-orders', 'trial', device, dkey, MACHINE_B, 'n2', '', '', '', 'pending', t, t).run();
  const [signedA, signedB] = await Promise.all([approveRequest(e, 'a', key), approveRequest(e, 'b', key)]);
  const winners = [signedA, signedB].filter((s) => s?.code);
  assert.equal(winners.length, 1);
  const rowB = await e.DB.prepare('SELECT status, reason FROM licence_requests WHERE id = ?').bind('b').first();
  const rowA = await e.DB.prepare('SELECT status, reason FROM licence_requests WHERE id = ?').bind('a').first();
  const refused = [rowA, rowB].find((r) => r.status === 'refused');
  assert.ok(refused);
  assert.equal(refused.reason, 'already_used');
});

test('second online trial for same machine hash is refused after install_id wipe (new device code)', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 7)));
  const first = await postRequest(e, body({ device: '7KD2M-QX9TP', machine: MACHINE_A, nonce: 'n1' }));
  await approveRequest(e, first.data.id, key);
  const second = await postRequest(e, body({ device: 'ABCDE-FGHJK', machine: MACHINE_A, nonce: 'n2' }));
  assert.equal(second.data.status, 'refused');
  assert.equal(second.data.reason, 'already_used');
});

test('offline mint blocks later online trial for that device', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 11)));
  await issueOfflineCustomer(e, key, '7KD2M-QX9TP', 'Shop', 'trip-orders');
  const rows = await e.DB.prepare('SELECT machine FROM machine_trials').bind().all();
  assert.equal(rows.results[0].machine, deviceLockKey(deviceKey('7KD2M-QX9TP')));
  const online = await postRequest(e, body({ nonce: 'n3' }));
  assert.equal(online.data.reason, 'already_used');
});

test('offline concurrent mint only succeeds once', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 12)));
  const device = '7KD2M-QX9TP';
  const results = await Promise.allSettled([
    issueOfflineCustomer(e, key, device, 'A', 'trip-orders'),
    issueOfflineCustomer(e, key, device, 'B', 'trip-orders'),
  ]);
  const ok = results.filter((r) => r.status === 'fulfilled');
  assert.equal(ok.length, 2);
  const codes = ok.map((r) => r.value.code);
  assert.equal(codes[0], codes[1]);
});

test('short device code is rejected at request', async () => {
  const e = env();
  const { res, data } = await postRequest(e, body({ device: 'ABC', nonce: 'short' }));
  assert.equal(res.status, 400);
  assert.equal(data.field, 'device');
});

test('open pending is limited to one row per device until TTL expires', async () => {
  const e = env();
  const first = await postRequest(e, body({ nonce: 'p1' }));
  assert.equal(first.data.status, 'pending');
  const second = await postRequest(e, body({ nonce: 'p2' }));
  assert.equal(second.res.status, 400);
  assert.equal(second.data.field, 'device');
  const old = Math.floor(Date.now() / 1000) - 2000;
  await e.DB.prepare('UPDATE licence_requests SET created_at = ?, updated_at = ? WHERE id = ?')
    .bind(old, old, first.data.id).run();
  const third = await postRequest(e, body({ nonce: 'p3' }));
  assert.equal(third.data.status, 'pending');
});

test('status returns calendar_day as YYYY-MM-DD string', async () => {
  const e = env();
  const { data } = await postRequest(e, body());
  const st = await getStatus(e, data.id, data.poll_token);
  assert.match(st.data.calendar_day, /^\d{4}-\d{2}-\d{2}$/);
});

test('ack clears stored activation code', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 2)));
  const { data } = await postRequest(e, body());
  await approveRequest(e, data.id, key);
  const poll = data.poll_token;
  const ackReq = new Request('https://hub.test/licence/ack', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + poll },
    body: JSON.stringify({ id: data.id }),
  });
  await handleLicence(ackReq, e, new URL(ackReq.url));
  const row = await e.DB.prepare('SELECT code, status FROM licence_requests WHERE id = ?').bind(data.id).first();
  assert.equal(row.code, null);
  assert.equal(row.status, 'delivered');
});

test('owner force reissue replaces device trial lock', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 4)));
  const device = '7KD2M-QX9TP';
  const first = await postRequest(e, body({ nonce: 'f1' }));
  await approveRequest(e, first.data.id, key);
  const retry = await postRequest(e, body({ nonce: 'f2' }));
  assert.equal(retry.data.reason, 'already_used');
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('lost', 'hx', 'trip-orders', 'trial', device, deviceKey(device), MACHINE_A, 'n-lost', '', '', '', 'pending', 2, 2).run();
  const forced = await approveRequest(e, 'lost', key, { force: true });
  assert.ok(forced?.code);
});

test('issued row without machine lock is not returned until claim is repaired', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 6)));
  const { data } = await postRequest(e, body({ nonce: 'orphan' }));
  await e.DB.prepare(
    "UPDATE licence_requests SET status = 'issued', code = 'FAKE-CODE' WHERE id = ?",
  ).bind(data.id).run();
  const out = await approveRequest(e, data.id, key);
  assert.ok(out?.code);
  assert.notEqual(out.code, 'FAKE-CODE');
  assert.match(out.code, /^[0-9A-Z-]+$/);
  const lock = await e.DB.prepare('SELECT request_id FROM machine_trials WHERE machine = ?')
    .bind(deviceLockKey(deviceKey('7KD2M-QX9TP'))).first();
  assert.equal(lock.request_id, data.id);
});

test('purgeStaleCodes blanks old issued rows', async () => {
  const e = env();
  const old = Math.floor(Date.now() / 1000) - 20 * 86400;
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, code, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('old', 'h', 'trip-orders', 'trial', '7KD2M-QX9TP', deviceKey('7KD2M-QX9TP'), MACHINE_A, 'n', '', '', '', 'delivered', 'CODE-OLD', old, old).run();
  await purgeStaleCodes(e);
  const row = await e.DB.prepare('SELECT code FROM licence_requests WHERE id = ?').bind('old').first();
  assert.equal(row.code, null);
});

test('approve retry returns the same code', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 3)));
  const { data } = await postRequest(e, body());
  const first = await approveRequest(e, data.id, key);
  const second = await approveRequest(e, data.id, key);
  assert.equal(first.code, second.code);
});

test('paid pending request approval is refused', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 5)));
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('id1', 'hash', 'trip-orders', 'monthly', '7KD2M-QX9TP', 'm1', 'n-old', '', '', '', 'pending', 1, 1).run();
  const out = await approveRequest(e, 'id1', key);
  assert.equal(out.refused, true);
  assert.equal(out.reason, REASON_PAID_IN_STUDIO);
});

test('legacy unprefixed machine_trials row blocks reuse after upgrade', async () => {
  const e = env();
  const device = '7KD2M-QX9TP';
  const dkey = deviceKey(device);
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)').bind(dkey, 'legacy-req', 1).run();
  assert.equal(await trialUsedForDevice(e, dkey), true);
  await migrateLegacyTrialLocks(e);
  assert.equal(await trialUsedForDevice(e, dkey), true);
});

test('offline issuance survives customer insert failure and retries same code', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 21)));
  const device = '7KD2M-QX9TP';
  const origPrepare = e.DB.prepare.bind(e.DB);
  let failCustomers = true;
  e.DB.prepare = (sql) => {
    const stmt = origPrepare(sql);
    if (failCustomers && sql.includes('INSERT INTO customers')) {
      return {
        bind(...args) {
          return {
            run() { throw new Error('simulated-D1-error'); },
            first() { return stmt.bind(...args).first(); },
            all() { return stmt.bind(...args).all(); },
          };
        },
      };
    }
    return stmt;
  };
  await assert.rejects(() => issueOfflineCustomer(e, key, device, 'Shop', 'trip-orders'), /simulated-D1-error/);
  failCustomers = false;
  const second = await issueOfflineCustomer(e, key, device, 'Shop', 'trip-orders');
  assert.ok(second.code);
  const third = await issueOfflineCustomer(e, key, device, 'Shop', 'trip-orders');
  assert.equal(third.code, second.code);
});

test('derivePollToken is stable for a nonce', async () => {
  const a = await derivePollToken(SECRET, 'fixed-nonce');
  const b = await derivePollToken(SECRET, 'fixed-nonce');
  assert.equal(a, b);
  assert.match(a, /^lp_[0-9a-f]+$/);
});

function wrapAsyncD1(syncDb) {
  return {
    prepare(sql) {
      const inner = syncDb.prepare(sql);
      return {
        bind(...args) {
          const bound = inner.bind(...args);
          return {
            run: () => Promise.resolve(bound.run()),
            first: () => Promise.resolve(bound.first()),
            all: () => Promise.resolve(bound.all()),
          };
        },
      };
    },
    batch: (stmts) => syncDb.batch(stmts),
  };
}

test('offline issuance awaits D1 run() like production', async () => {
  const e = env();
  e.DB = wrapAsyncD1(e.DB);
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 31)));
  const signed = await issueOfflineCustomer(e, key, '7KD2M-QX9TP', 'Shop', 'trip-orders');
  assert.ok(signed.code);
  const again = await issueOfflineCustomer(e, key, '7KD2M-QX9TP', 'Shop', 'trip-orders');
  assert.equal(again.code, signed.code);
});

test('legacy migration backfills machine hash lock from delivered request', async () => {
  const e = env();
  const device = '7KD2M-QX9TP';
  const dkey = deviceKey(device);
  const t = 1;
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, code, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('legacy-req', 'h', 'trip-orders', 'trial', device, dkey, MACHINE_A, 'n', '', '', '', 'issued', 'CODE', t, t).run();
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)').bind(dkey, 'legacy-req', t).run();
  e.DB = wrapAsyncD1(e.DB);
  await migrateLegacyTrialLocks(e);
  const hlock = await e.DB.prepare('SELECT request_id FROM machine_trials WHERE machine = ?').bind('h:' + MACHINE_A).first();
  assert.equal(hlock.request_id, 'legacy-req');
  const second = await postRequest(e, body({ device: 'ABCDE-FGHJK', machine: MACHINE_A, nonce: 'n-hash' }));
  assert.equal(second.data.reason, 'already_used');
});

test('losing concurrent approval releases partial device locks', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 33)));
  const hash = MACHINE_A;
  const devA = '7KD2M-QX9TP';
  const devB = 'ABCDE-FGHJK';
  const t = 1;
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('win', 'h1', 'trip-orders', 'trial', devA, deviceKey(devA), hash, 'n1', '', '', '', 'pending', t, t).run();
  await e.DB.prepare(
    'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind('lose', 'h2', 'trip-orders', 'trial', devB, deviceKey(devB), hash, 'n2', '', '', '', 'pending', t, t).run();
  const [a, b] = await Promise.all([approveRequest(e, 'win', key), approveRequest(e, 'lose', key)]);
  const winners = [a, b].filter((s) => s?.code);
  assert.equal(winners.length, 1);
  const locks = await e.DB.prepare('SELECT machine, request_id FROM machine_trials').bind().all();
  const deviceLocks = (locks.results || []).filter((r) => r.machine.startsWith('d:'));
  assert.equal(deviceLocks.length, 1);
  const online = await postRequest(e, body({ device: devB, machine: MACHINE_B, nonce: 'n-free' }));
  assert.equal(online.data.status, 'pending');
});

test('offline issuance survives interrupted code write and retries same code', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 34)));
  const device = '7KD2M-QX9TP';
  const origPrepare = e.DB.prepare.bind(e.DB);
  let failIssue = true;
  e.DB.prepare = (sql) => {
    const stmt = origPrepare(sql);
    if (failIssue && sql.includes('UPDATE licence_requests SET status = ?') && sql.includes('code = ?')) {
      return {
        bind(...args) {
          return {
            async run() { throw new Error('simulated-D1-error'); },
            first: () => stmt.bind(...args).first(),
            all: () => stmt.bind(...args).all(),
          };
        },
      };
    }
    return stmt;
  };
  await assert.rejects(() => issueOfflineCustomer(e, key, device, 'Shop', 'trip-orders'), /simulated-D1-error/);
  failIssue = false;
  const second = await issueOfflineCustomer(e, key, device, 'Shop', 'trip-orders');
  assert.ok(second.code);
});

test('request with empty, short or non-hex machine tag is rejected', async () => {
  const e = env();
  for (const machine of ['', 'abc', 'z'.repeat(64), 'a'.repeat(63), 'a'.repeat(65)]) {
    const r = await postRequest(e, body({ machine }));
    assert.equal(r.status ?? r.res?.status ?? 400, 400);
    assert.equal(r.data.field, 'machine');
  }
});

test('approval-race loser keeps no machine_trials rows and adds no customer', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 35)));
  const devA = '7KD2M-QX9TP';
  const devB = 'ABCDE-FGHJK';
  for (const [id, dev, n] of [['w2', devA, 'm1'], ['l2', devB, 'm2']]) {
    await e.DB.prepare(
      'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind(id, 'h' + id, 'trip-orders', 'trial', dev, deviceKey(dev), MACHINE_A, n, '', '', '', 'pending', 1, 1).run();
  }
  const [a, b] = await Promise.all([approveRequest(e, 'w2', key), approveRequest(e, 'l2', key)]);
  const winner = a?.code ? 'w2' : 'l2';
  assert.equal([a, b].filter((s) => s?.code).length, 1);
  const locks = (await e.DB.prepare('SELECT machine, request_id FROM machine_trials').bind().all()).results || [];
  assert.ok(locks.length > 0);
  assert.ok(locks.every((r) => r.request_id === winner));
  const cust = (await e.DB.prepare('SELECT id FROM customers').bind().all()).results || [];
  assert.equal(cust.length, 1);
});
