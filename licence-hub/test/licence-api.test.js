import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPrivateKey } from 'node:crypto';
import { newD1 } from './d1-mock.js';
import { handleLicence, approveRequest, derivePollToken, REASON_PAID_IN_STUDIO } from '../src/licence-api.js';
import { importSigningKey } from '../src/afcodes.js';

const SECRET = 'test-session-secret-0123456789abcdef';

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
  };
}

function body(over = {}) {
  return {
    product: 'trip-orders',
    kind: 'trial',
    device: '7KD2M-QX9TP',
    machine: 'machine-hash-a',
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

test('only one trial code per machine on concurrent approval', async () => {
  const e = env();
  const key = await importSigningKey(pemFromSeed(Buffer.alloc(32, 9)));
  const machine = 'same-machine';
  const a = await postRequest(e, body({ machine, nonce: 'n1' }));
  const b = await postRequest(e, body({ machine, nonce: 'n2' }));
  const signedA = await approveRequest(e, a.data.id, key);
  const signedB = await approveRequest(e, b.data.id, key);
  assert.ok(signedA?.code);
  assert.equal(signedB, null);
  const rowB = await e.DB.prepare('SELECT status, reason FROM licence_requests WHERE id = ?').bind(b.data.id).first();
  assert.equal(rowB.status, 'refused');
  assert.equal(rowB.reason, 'already_used');
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

test('derivePollToken is stable for a nonce', async () => {
  const a = await derivePollToken(SECRET, 'fixed-nonce');
  const b = await derivePollToken(SECRET, 'fixed-nonce');
  assert.equal(a, b);
  assert.match(a, /^lp_[0-9a-f]+$/);
});
