import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import worker, { hmacHex, sha256Hex } from '../src/worker.js';
import { newEnv, call, office, putCard, postEvent, ev, jpeg, putPhoto, TOKEN, register, MASTER } from './helpers.js';

test('a card is served to the driver by token, and only by the right token', async () => {
  const env = newEnv();
  await putCard(env);
  const r = await call(env, 'GET', '/api/card/' + TOKEN);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.card.no, '26-A-00001');
  assert.equal((await call(env, 'GET', '/api/card/Tk_zzzzzzzzzzzzzzzzzzzzzz')).status, 404);
  assert.equal((await call(env, 'GET', '/api/card/short')).status, 404);
});

test('the token itself is never stored', async () => {
  const env = newEnv();
  await putCard(env);
  await postEvent(env, ev());
  for (const t of ['cards', 'events', 'nonces', 'rate']) {
    const rows = await env.DB.prepare(`SELECT * FROM ${t}`).all();
    assert.ok(!JSON.stringify(rows.results).includes(TOKEN), t);
  }
});

test('cancelled and expired cards answer 410 with a reason', async () => {
  const env = newEnv();
  await putCard(env, { cancelled: true });
  let r = await call(env, 'GET', '/api/card/' + TOKEN);
  assert.equal(r.status, 410);
  assert.equal((await r.json()).cancelled, true);
  assert.equal((await postEvent(env, ev())).status, 410, 'a cancelled trip takes no more events');
  await putCard(env, { cancelled: false, expiresAt: Math.floor(Date.now() / 1000) - 5 });
  r = await call(env, 'GET', '/api/card/' + TOKEN);
  assert.equal(r.status, 410);
  assert.equal((await r.json()).expired, true);
});

test('opening the link does not bind; the first real message does, and then a second phone is told so', async () => {
  const env = newEnv();
  await putCard(env);
  const bind = (d) => call(env, 'POST', '/api/bind/' + TOKEN, { body: JSON.stringify({ deviceId: d }) }).then((r) => r.json());
  assert.deepEqual(await bind('device-BBBB-2'), { bound: true });                 // the dispatcher looks at the link first ...
  assert.equal((await env.DB.prepare('SELECT bound_device FROM cards').first()).bound_device, null);
  assert.deepEqual(await bind('device-AAAA-1'), { bound: true });                 // ... the driver opens it later
  const sent = await (await postEvent(env, { ...ev(), deviceId: 'device-AAAA-1' })).json();
  assert.equal(sent.secondDevice, false);                                           // the driver's first real message binds his phone
  assert.deepEqual(await bind('device-AAAA-1'), { bound: true });
  assert.deepEqual(await bind('device-BBBB-2'), { bound: false, secondDevice: true });
  assert.equal((await bind('x')).error, 'Bad device');
});

test('events are stored once however many times the phone retries', async () => {
  const env = newEnv();
  await putCard(env);
  const e = ev();
  const a = await (await postEvent(env, e)).json();
  const b = await (await postEvent(env, e)).json();
  assert.equal(a.ok, true);
  assert.equal(b.duplicate, true);
  assert.equal(a.recvAt, b.recvAt);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 1);
});

test('bad events are refused with a clear status', async () => {
  const env = newEnv();
  await putCard(env);
  assert.equal((await postEvent(env, ev({ uuid: 'nope' }))).status, 400);
  assert.equal((await postEvent(env, ev({ type: 'delete' }))).status, 400);
  assert.equal((await postEvent(env, ev({ v: 2 }))).status, 400);
  assert.equal((await postEvent(env, ev({ deviceId: 'a' }))).status, 400);
  assert.equal((await postEvent(env, ev({ data: { x: 'y'.repeat(20000) } }))).status, 413);
  assert.equal((await call(env, 'POST', '/api/event/' + TOKEN, { body: '{not json' })).status, 400);
});

test('an event from another phone is accepted but marked', async () => {
  const env = newEnv();
  await putCard(env);
  assert.equal((await (await postEvent(env, ev({ deviceId: 'device-AAAA-1' }))).json()).secondDevice, false);
  const r = await (await postEvent(env, ev({ deviceId: 'device-BBBB-2', type: 'end' }))).json();
  assert.equal(r.ok, true);
  assert.equal(r.secondDevice, true);
  const inbox = await (await office(env, 'GET', '/office/inbox')).json();
  assert.deepEqual(inbox.events.map((x) => x.second), [false, true]);
  assert.equal(inbox.events[0].boundDevice, 'device-AAAA-1');
});

test('photos: stored once, checked by hash, only JPEG, size limited', async () => {
  const env = newEnv();
  await putCard(env);
  const id = randomUUID(), bytes = jpeg();
  assert.equal((await putPhoto(env, id, bytes)).status, 200);
  assert.equal((await (await putPhoto(env, id, bytes)).json()).duplicate, true);
  assert.equal((await putPhoto(env, randomUUID(), bytes, { sha: 'a'.repeat(64) })).status, 400);
  assert.equal((await putPhoto(env, randomUUID(), new Uint8Array(500).fill(7))).status, 400, 'not a jpeg');
  assert.equal((await putPhoto(env, randomUUID(), jpeg(700 * 1024))).status, 413);
  assert.equal((await putPhoto(env, randomUUID(), bytes, { headers: { 'X-Kind': 'selfie' } })).status, 400);
  assert.equal((await putPhoto(env, 'bad-id', bytes)).status, 400);
});

test('the office reads the inbox, downloads the photo, acknowledges, and the mailbox empties', async () => {
  const env = newEnv();
  await putCard(env);
  const e = ev(), id = randomUUID(), bytes = jpeg(20000);
  await postEvent(env, e);
  await putPhoto(env, id, bytes, { headers: { 'X-Event': e.uuid, 'X-Fallback': '1', 'X-Kind': 'paper' } });
  const inbox = await (await office(env, 'GET', '/office/inbox?limit=50')).json();
  assert.equal(inbox.events.length, 1);
  assert.equal(inbox.events[0].body.data.startKm, 1000);
  assert.equal(inbox.photos.length, 1);
  assert.deepEqual([inbox.photos[0].kind, inbox.photos[0].fallback, inbox.photos[0].eventUuid], ['paper', true, e.uuid]);
  const p = await office(env, 'GET', '/office/photo/' + id);
  const got = new Uint8Array(await p.arrayBuffer());
  assert.equal(await sha256Hex(got), await sha256Hex(bytes));
  const st = await (await office(env, 'GET', '/office/status')).json();
  assert.deepEqual([st.events, st.photos, st.cards], [1, 1, 1]);
  await office(env, 'POST', '/office/ack', { events: [e.uuid], photos: [id] });
  const after = await (await office(env, 'GET', '/office/inbox')).json();
  assert.deepEqual([after.events.length, after.photos.length], [0, 0]);
});

test('office requests must be signed, fresh, unrepeated and untampered', async () => {
  const env = newEnv();
  assert.equal((await call(env, 'GET', '/office/status')).status, 401, 'no signature');
  assert.equal((await office(env, 'GET', '/office/status', undefined, { secret: 'wrong-secret' })).status, 401);
  const wrong = await office(env, 'GET', '/office/status', undefined, { secret: 'wrong-secret' });
  assert.equal((await wrong.json()).reason, 'secret');
  const old = await office(env, 'GET', '/office/status', undefined, { time: Math.floor(Date.now() / 1000) - 600 });
  assert.equal(old.status, 401, 'too old');
  const oldBody = await old.json();
  assert.equal(oldBody.reason, 'clock', 'a clock that is off is not reported as a wrong secret');
  assert.ok(Math.abs(oldBody.skewSeconds + 600) < 5 && oldBody.serverTime);
  const nonce = 'ab'.repeat(16);
  assert.equal((await office(env, 'GET', '/office/status', undefined, { nonce })).status, 200);
  const again = await office(env, 'GET', '/office/status', undefined, { nonce });
  assert.equal(again.status, 401, 'replayed');
  assert.equal((await again.json()).reason, 'replay');
  // a valid signature for one body does not cover another
  const good = { cards: [] };
  const bytes = new TextEncoder().encode(JSON.stringify(good));
  const t = String(Math.floor(Date.now() / 1000)), n = 'cd'.repeat(16);
  const { hmacHex } = await import('../src/worker.js');
  const sig = await hmacHex('test-secret-0123456789abcdef', ['PUT', '/office/cards', t, n, await sha256Hex(bytes)].join('\n'));
  const r = await call(env, 'PUT', '/office/cards', { body: JSON.stringify({ cards: [], remove: ['x'] }), headers: { 'X-TO-Time': t, 'X-TO-Nonce': n, 'X-TO-Sig': sig } });
  assert.equal(r.status, 401);
  const noSecret = newEnv(); noSecret.OFFICE_SECRET = '';
  assert.equal((await office(noSecret, 'GET', '/office/status')).status, 503);
});

test('rate limits: 120 requests per token and 1200 per address in ten minutes (phones on one mobile-network address share it)', async () => {
  const env = newEnv();
  await putCard(env);
  let last;
  for (let i = 0; i < 121; i++) last = await call(env, 'GET', '/api/card/' + TOKEN);
  assert.equal(last.status, 429);
  assert.ok(last.headers.get('Retry-After'));
  // another token from the same address is still fine until the address limit
  assert.equal((await call(env, 'GET', '/api/card/Tk_otherotherotherother1')).status, 404);
});

test('every response carries the security headers; pages and the service worker are served', async () => {
  const env = newEnv();
  for (const path of ['/', '/t/' + TOKEN, '/sw.js', '/app/app.js', '/nope']) {
    const r = await call(env, 'GET', path);
    assert.ok(r.headers.get('content-security-policy').includes("default-src 'self'"), path);
    assert.equal(r.headers.get('x-content-type-options'), 'nosniff', path);
    assert.equal(r.headers.get('referrer-policy'), 'no-referrer', path);
  }
  assert.equal((await call(env, 'GET', '/sw.js')).headers.get('service-worker-allowed'), '/');
});

test('the daily cleanup removes old items and keeps new ones', async () => {
  const env = newEnv();
  await putCard(env);
  await postEvent(env, ev());
  await env.DB.prepare('UPDATE events SET recv_at = recv_at - ?').bind(40 * 86400).run();
  await postEvent(env, ev());
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 1);
});

test('card updates keep the bound phone unless the office releases it', async () => {
  const env = newEnv();
  const th = await putCard(env);
  await postEvent(env, ev({ deviceId: 'device-AAAA-1' }));
  await putCard(env, { body: { no: '26-A-00001', status: 'started' } });
  assert.equal((await env.DB.prepare('SELECT bound_device b FROM cards').first()).b, 'device-AAAA-1');
  await putCard(env, { releaseDevice: true });
  assert.equal((await env.DB.prepare('SELECT bound_device b FROM cards').first()).b, null);
  const removed = await office(env, 'PUT', '/office/cards', { remove: [th] });
  assert.equal(removed.status, 200);
  assert.equal((await call(env, 'GET', '/api/card/' + TOKEN)).status, 404);
});

test('a removed (replaced) link cannot be published again by a PC that still has it', async () => {
  const env = newEnv();
  const th = await putCard(env);
  const old = await postEvent(env, ev());                               // evidence sent before the replacement stays in the mailbox
  assert.equal(old.status, 200);
  assert.equal((await office(env, 'PUT', '/office/cards', { remove: [th] })).status, 200);
  assert.equal((await call(env, 'GET', '/api/card/' + TOKEN)).status, 404);
  assert.equal((await postEvent(env, ev())).status, 404, 'the old phone can no longer send as this trip');
  await putCard(env);                                                   // a stale PC publishes the old card again
  assert.equal((await call(env, 'GET', '/api/card/' + TOKEN)).status, 404, 'it stays dead');
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM cards').first()).n, 0);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 1, 'what was already received is kept for the office');
  // a new link for the same trip is a different token and works
  const other = await sha256Hex('Tk_zzzzzzzzzzzzzzzzzzzzzz');
  assert.equal((await office(env, 'PUT', '/office/cards', { cards: [{ tokenHash: other, tripId: 'tr1', body: {} }] })).status, 200);
  assert.equal((await call(env, 'GET', '/api/card/Tk_zzzzzzzzzzzzzzzzzzzzzz')).status, 200);
});

test('a revocation lives as long as the link it revokes (not a fixed 60 days)', async () => {
  const env = newEnv();
  const th = await putCard(env, { expiresAt: Math.floor(Date.now() / 1000) + 120 * 86400 });      // a trip planned far ahead: the link lives 120 days
  assert.equal((await office(env, 'PUT', '/office/cards', { remove: [th] })).status, 200);
  await env.DB.prepare('UPDATE revoked SET at = at - ?').bind(100 * 86400).run();                  // 100 days later a PC that was off reconnects
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first()).n, 1, 'the tombstone is still there');
  await putCard(env, { expiresAt: Math.floor(Date.now() / 1000) + 20 * 86400 });                   // it publishes the stale card
  assert.equal((await call(env, 'GET', '/api/card/' + TOKEN)).status, 404, 'the revoked link is still dead');
  await env.DB.prepare('UPDATE revoked SET until = ?').bind(Math.floor(Date.now() / 1000) - 1).run();   // the link would have expired by now
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first()).n, 0, 'only then is it forgotten');
});

test('a tombstone table made by the first version (without `until`) is upgraded in place and keeps its rows', async () => {
  const env = newEnv();
  await env.DB.prepare('DROP TABLE revoked').run();
  await env.DB.prepare('CREATE TABLE revoked (token_hash TEXT PRIMARY KEY, at INTEGER NOT NULL)').run();
  const old = await sha256Hex('Tk_oldoldoldoldoldoldold');
  const at = Math.floor(Date.now() / 1000) - 5 * 86400;
  await env.DB.prepare('INSERT INTO revoked(token_hash, at) VALUES(?, ?)').bind(old, at).run();
  await putCard(env);                                                  // any office card call makes the Worker check the table
  const r = await env.DB.prepare('SELECT at, until FROM revoked WHERE token_hash = ?').bind(old).first();
  assert.equal(r.at, at);
  assert.equal(r.until, at + 90 * 86400, 'an old row is kept for 90 days from its revocation');
});

test('a revoked link whose card is unknown is still remembered for a long time, and a link without expiry for ever', async () => {
  const env = newEnv();
  const unknown = await sha256Hex('Tk_unknownunknownunknown1');
  await office(env, 'PUT', '/office/cards', { remove: [unknown] });
  const r = await env.DB.prepare('SELECT until - at AS span FROM revoked').first();
  assert.ok(r.span >= 90 * 86400, 'at least 90 days when the expiry is not known: ' + r.span);
  const th = await putCard(env, { expiresAt: null });
  await office(env, 'PUT', '/office/cards', { remove: [th] });
  const forever = await env.DB.prepare('SELECT until - at AS span FROM revoked WHERE token_hash = ?').bind(th).first();
  assert.ok(forever.span > 3000 * 86400, 'a link that never expires is revoked for ever');
});

test('a mailbox set up before revocation existed keeps working (the table is made on first use) and old tombstones are cleaned', async () => {
  const env = newEnv();
  await env.DB.prepare('DROP TABLE revoked').run();
  const th = await putCard(env);
  assert.equal((await office(env, 'PUT', '/office/cards', { remove: [th, 'not-a-hash'] })).status, 200);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first()).n, 1, 'a malformed hash is ignored');
  await env.DB.prepare('UPDATE revoked SET until = ?').bind(Math.floor(Date.now() / 1000) - 1).run();
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first()).n, 0);
});

const receipts = async (env, uuids, token = TOKEN) => (await call(env, 'POST', '/api/receipts/' + token, { body: JSON.stringify({ uuids }), headers: { 'Content-Type': 'application/json' } })).json();

test('the phone can tell "in the mailbox" from "the office has it" from "unknown"', async () => {
  const env = newEnv();
  await putCard(env);
  const e1 = ev(), e2 = ev(), pid = randomUUID(), never = randomUUID();
  await postEvent(env, e1);
  await postEvent(env, e2);
  assert.equal((await putPhoto(env, pid, jpeg())).status, 200);
  let r = await receipts(env, [e1.uuid, e2.uuid, pid, never]);
  assert.deepEqual([r.office.sort(), r.mailbox.sort()], [[], [e1.uuid, e2.uuid, pid].sort()], 'received by the mailbox is not yet received by the office');
  assert.equal((await office(env, 'POST', '/office/ack', { events: [e1.uuid], photos: [pid] })).status, 200);
  r = await receipts(env, [e1.uuid, e2.uuid, pid, never]);
  assert.deepEqual([r.office.sort(), r.mailbox], [[e1.uuid, pid].sort(), [e2.uuid]], 'e1 and the photo are stored by the office; e2 still waits; the unknown id is in neither list');
  assert.equal((await office(env, 'POST', '/office/ack', { events: [e1.uuid] })).status, 200, 'acknowledging again is harmless');
  assert.deepEqual((await receipts(env, [e1.uuid])).office, [e1.uuid]);
});

test('an item the mailbox dropped without an acknowledgement is unknown, so the phone sends it again - and sending it again is safe', async () => {
  const env = newEnv();
  await putCard(env);
  const e1 = ev();
  await postEvent(env, e1);
  await env.DB.prepare('UPDATE events SET recv_at = recv_at - ?').bind(40 * 86400).run();
  await worker.scheduled({}, env);                                   // retention: 30 days
  let r = await receipts(env, [e1.uuid]);
  assert.deepEqual([r.office, r.mailbox], [[], []], 'purged unacknowledged: neither');
  assert.equal((await postEvent(env, e1)).status, 200, 'the phone sends the same event again');
  r = await receipts(env, [e1.uuid]);
  assert.deepEqual(r.mailbox, [e1.uuid]);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 1, 'one copy');
});

test('receipts: only the items of this link are shown as waiting in the mailbox; bad ids and bad requests are refused or ignored; old receipts are cleaned', async () => {
  const env = newEnv();
  await putCard(env);
  const other = 'Tk_zzzzzzzzzzzzzzzzzzzzzz', oh = await sha256Hex(other);
  await office(env, 'PUT', '/office/cards', { cards: [{ tokenHash: oh, tripId: 'tr2', body: {}, expiresAt: Math.floor(Date.now() / 1000) + 86400 }] });
  const mine = ev(), theirs = ev({ tripId: 'tr2' });
  await postEvent(env, mine);
  await postEvent(env, theirs, other);
  const r = await receipts(env, [mine.uuid, theirs.uuid, 'not-a-uuid', 7]);
  assert.deepEqual([r.office, r.mailbox], [[], [mine.uuid]], "another link's waiting item is not reported");
  assert.equal((await call(env, 'POST', '/api/receipts/Tk_unknownunknownunknown1', { body: '{}' })).status, 404);
  assert.equal((await call(env, 'POST', '/api/receipts/' + TOKEN, { body: 'not json' })).status, 400);
  assert.deepEqual(await receipts(env, []), { office: [], mailbox: [] });
  await office(env, 'POST', '/office/ack', { events: [mine.uuid] });
  await env.DB.prepare('UPDATE receipts SET at = at - ?').bind(61 * 86400).run();
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM receipts').first()).n, 0);
});

test('a large acknowledgement uses few statements, and a mailbox from before receipts existed keeps working', async () => {
  const env = newEnv();
  await env.DB.prepare('DROP TABLE receipts').run();
  await putCard(env);
  const evs = Array.from({ length: 120 }, () => ev()), th = await sha256Hex(TOKEN);
  for (const e of evs) await env.DB.prepare('INSERT INTO events(uuid, token_hash, trip_id, type, body, device_id, phone_at, recv_at, second) VALUES(?,?,?,?,?,?,?,?,0)').bind(e.uuid, th, 'tr1', 'start', '{}', 'device-0001', '', Math.floor(Date.now() / 1000)).run();
  let statements = 0;
  const batch = env.DB.batch.bind(env.DB);
  env.DB.batch = async (st) => { statements += st.length; return batch(st); };
  assert.equal((await office(env, 'POST', '/office/ack', { events: evs.map((e) => e.uuid) })).status, 200);
  assert.ok(statements <= 6, 'was ' + statements + ' (one DELETE per event before)');
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 0);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM receipts').first()).n, 120);
  assert.equal((await receipts(env, evs.slice(0, 100).map((e) => e.uuid))).office.length, 100);
});

test('the single-file bundle serves the driver page without any asset binding', async () => {
  const { execFileSync } = await import('node:child_process');
  const { pathToFileURL, fileURLToPath } = await import('node:url');
  const { dirname, join } = await import('node:path');
  const here = dirname(fileURLToPath(import.meta.url));
  execFileSync('node', [join(here, '..', 'build.js')]);
  const bundle = (await import(pathToFileURL(join(here, '..', 'dist', 'trip-orders-gateway.js')).href + '?t=' + Date.now())).default;
  const env = newEnv();
  delete env.ASSETS;
  const get = (p) => bundle.fetch(new Request('http://gw.test' + p, { headers: { 'CF-Connecting-IP': '1.1.1.1' } }), env);
  const page = await get('/t/' + TOKEN);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /<div id="app"/);
  assert.equal((await get('/app/app.js')).status, 200);
  assert.match((await get('/app/style.css')).headers.get('content-type'), /css/);
  assert.equal((await get('/sw.js')).headers.get('service-worker-allowed'), '/');
});

test('register gives each install its own derived secret and stores nothing secret', async () => {
  const env = newEnv();
  const a = await register(env, '198.51.100.1');
  const b = await register(env, '198.51.100.2');
  assert.match(a.tenantId, /^[0-9a-f]{32}$/);
  assert.notEqual(a.tenantId, b.tenantId);
  assert.equal(a.officeSecret, await hmacHex(MASTER, 'TO-TENANT1|' + a.tenantId));
  assert.notEqual(a.officeSecret, b.officeSecret);
  assert.equal(a.officeSecret.length, 64);
  const dump = JSON.stringify((await env.DB.prepare('SELECT * FROM tenants').all()).results);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM tenants').first()).n, 2);
  assert.ok(!dump.includes(a.officeSecret) && !dump.includes(b.officeSecret) && !dump.includes(MASTER));
  const noKey = newEnv();
  noKey.MASTER_KEY = '';
  assert.equal((await call(noKey, 'POST', '/office/register', { body: '{}' })).status, 503);
  const big = await call(env, 'POST', '/office/register', { body: 'x'.repeat(3000), headers: { 'CF-Connecting-IP': '198.51.100.9' } });
  assert.equal(big.status, 413);
});

test('register is limited to 5 an hour and 50 a day for one address', async () => {
  const env = newEnv();
  const ip = '198.51.100.20';
  for (let i = 0; i < 5; i++) assert.equal((await call(env, 'POST', '/office/register', { body: '{}', headers: { 'CF-Connecting-IP': ip } })).status, 200);
  const blocked = await call(env, 'POST', '/office/register', { body: '{}', headers: { 'CF-Connecting-IP': ip } });
  assert.equal(blocked.status, 429);
  assert.ok(blocked.headers.get('Retry-After'));
  assert.equal((await call(env, 'POST', '/office/register', { body: '{}', headers: { 'CF-Connecting-IP': '198.51.100.21' } })).status, 200, 'another address is its own limit');
  await env.DB.prepare('UPDATE rate SET count = 50 WHERE key = ?').bind('reg:d:' + ip).run();
  await env.DB.prepare('UPDATE rate SET window = window - ? WHERE key = ?').bind(3600, 'reg:h:' + ip).run();
  assert.equal((await call(env, 'POST', '/office/register', { body: '{}', headers: { 'CF-Connecting-IP': ip } })).status, 429, '50 a day');
});

test('a tenant cannot read or acknowledge another tenant, and a bad tenant is refused', async () => {
  const env = newEnv();
  const a = await register(env, '198.51.100.30');
  const b = await register(env, '198.51.100.31');
  const token = 'Tk_tenantAtenantAtenantA';
  const tokenHash = await sha256Hex(token);
  const as = (who) => ({ tenant: who.tenantId, secret: who.officeSecret });
  assert.equal((await office(env, 'PUT', '/office/cards', { cards: [{ tokenHash, tripId: 'tr-a', body: { no: 'A-1' }, expiresAt: Math.floor(Date.now() / 1000) + 86400 }] }, as(a))).status, 200);
  const e = ev({ tripId: 'tr-a' });
  assert.equal((await postEvent(env, e, token)).status, 200);
  const id = randomUUID();
  assert.equal((await putPhoto(env, id, jpeg(), {}, token)).status, 200);
  const mine = await (await office(env, 'GET', '/office/inbox', undefined, as(a))).json();
  assert.equal(mine.events.length, 1);
  assert.equal(mine.photos.length, 1);
  const other = await (await office(env, 'GET', '/office/inbox', undefined, as(b))).json();
  assert.deepEqual(other, { events: [], photos: [] });
  assert.equal((await office(env, 'GET', '/office/photo/' + id, undefined, as(b))).status, 404);
  assert.equal((await office(env, 'GET', '/office/photo/' + id, undefined, as(a))).status, 200);
  const stB = await (await office(env, 'GET', '/office/status', undefined, as(b))).json();
  assert.deepEqual([stB.events, stB.photos, stB.cards], [0, 0, 0]);
  assert.equal((await office(env, 'POST', '/office/ack', { events: [e.uuid], photos: [id] }, as(b))).status, 200);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 1, 'B cannot acknowledge A');
  assert.equal((await env.DB.prepare("SELECT COUNT(*) n FROM receipts").first()).n, 0);
  const legacy = await (await office(env, 'GET', '/office/inbox')).json();
  assert.equal(legacy.events.length, 0, 'the old shared mailbox does not see a new install');
  assert.equal((await office(env, 'GET', '/office/status', undefined, { tenant: 'not-a-tenant', secret: a.officeSecret })).status, 401);
  assert.equal((await office(env, 'GET', '/office/status', undefined, { tenant: 'ab'.repeat(16), secret: 'nope' })).status, 401);
  // a signature for A does not become B by swapping the header
  const swapped = await office(env, 'GET', '/office/status', undefined, { tenant: b.tenantId, secret: a.officeSecret });
  assert.equal(swapped.status, 401);
  await office(env, 'POST', '/office/ack', { events: [e.uuid], photos: [id] }, as(a));
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM events').first()).n, 0);
});

test('the legacy office secret still sees only the legacy mailbox', async () => {
  const env = newEnv();
  await putCard(env);
  await postEvent(env, ev());
  const inbox = await (await office(env, 'GET', '/office/inbox')).json();
  assert.equal(inbox.events.length, 1);
  assert.equal(inbox.events[0].body.data.startKm, 1000);
  const fresh = await register(env, '198.51.100.40');
  const hidden = await (await office(env, 'GET', '/office/inbox', undefined, { tenant: fresh.tenantId, secret: fresh.officeSecret })).json();
  assert.equal(hidden.events.length, 0);
  assert.equal((await office(env, 'GET', '/office/status')).status, 200);
});

test('each mailbox has a card cap and a daily photo cap, and an unused mailbox is deleted after 90 days', async () => {
  const env = newEnv();
  env.MAX_CARDS = '1';
  env.MAX_PHOTO_BYTES_PER_DAY = '3000';
  const a = await register(env, '198.51.100.50');
  const as = { tenant: a.tenantId, secret: a.officeSecret };
  const card = (hash, trip) => office(env, 'PUT', '/office/cards', { cards: [{ tokenHash: hash, tripId: trip, body: {}, expiresAt: Math.floor(Date.now() / 1000) + 3600 }] }, as);
  assert.equal((await card(await sha256Hex('Tk_capAAAAAAAAAAAAAAA1'), 't1')).status, 200);
  assert.equal((await card(await sha256Hex('Tk_capBBBBBBBBBBBBBBB2'), 't2')).status, 429);
  const token = 'Tk_capAAAAAAAAAAAAAAA1';
  assert.equal((await putPhoto(env, randomUUID(), jpeg(2000), {}, token)).status, 200);
  assert.equal((await putPhoto(env, randomUUID(), jpeg(2000), {}, token)).status, 429);
  await env.DB.prepare('UPDATE tenants SET last_seen = ? WHERE id = ?').bind(Math.floor(Date.now() / 1000) - 91 * 86400, a.tenantId).run();
  await worker.scheduled({}, env);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM tenants').first()).n, 0);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM cards').first()).n, 0);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM photos').first()).n, 0);
});

test('an old mailbox without a tenant column is migrated and stays on the legacy secret', async () => {
  const env = newEnv();
  for (const index of ['events_tenant', 'photos_tenant', 'cards_tenant']) await env.DB.prepare('DROP INDEX IF EXISTS ' + index).run();
  for (const table of ['cards', 'events', 'photos', 'revoked']) {
    await env.DB.prepare('ALTER TABLE ' + table + ' DROP COLUMN tenant').run();
  }
  await putCard(env);
  await postEvent(env, ev());
  const inbox = await (await office(env, 'GET', '/office/inbox')).json();
  assert.equal(inbox.events[0].type, 'start');
  assert.equal((await env.DB.prepare("SELECT tenant FROM cards").first()).tenant, 'legacy');
  assert.equal((await env.DB.prepare("SELECT tenant FROM events").first()).tenant, 'legacy');
});
