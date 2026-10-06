import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import worker, { sha256Hex } from '../src/worker.js';
import { newEnv, call, office, putCard, postEvent, ev, jpeg, putPhoto, TOKEN } from './helpers.js';

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

test('the first phone binds; a second phone is told so', async () => {
  const env = newEnv();
  await putCard(env);
  const bind = (d) => call(env, 'POST', '/api/bind/' + TOKEN, { body: JSON.stringify({ deviceId: d }) }).then((r) => r.json());
  assert.deepEqual(await bind('device-AAAA-1'), { bound: true });
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
  assert.equal((await office(env, 'GET', '/office/status', undefined, { time: Math.floor(Date.now() / 1000) - 600 })).status, 401, 'too old');
  const nonce = 'ab'.repeat(16);
  assert.equal((await office(env, 'GET', '/office/status', undefined, { nonce })).status, 200);
  assert.equal((await office(env, 'GET', '/office/status', undefined, { nonce })).status, 401, 'replayed');
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

test('rate limits: 60 requests per token and 300 per address in ten minutes', async () => {
  const env = newEnv();
  await putCard(env);
  let last;
  for (let i = 0; i < 61; i++) last = await call(env, 'GET', '/api/card/' + TOKEN);
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

test('a mailbox set up before revocation existed keeps working (the table is made on first use) and old tombstones are cleaned', async () => {
  const env = newEnv();
  await env.DB.prepare('DROP TABLE revoked').run();
  const th = await putCard(env);
  assert.equal((await office(env, 'PUT', '/office/cards', { remove: [th, 'not-a-hash'] })).status, 200);
  assert.equal((await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first()).n, 1, 'a malformed hash is ignored');
  await env.DB.prepare('UPDATE revoked SET at = at - ?').bind(61 * 86400).run();
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
