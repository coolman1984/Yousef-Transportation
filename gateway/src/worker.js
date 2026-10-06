// Trip Orders gateway - a Cloudflare Worker + D1 mailbox. No dependencies.
// Drivers' phones talk to /t/, /api/ (the link token is the key); office PCs talk to /office/ (signed requests).
// Tokens are never stored or logged: the database keys everything by sha256(token).

const enc = new TextEncoder();
const MAX_JSON = 16 * 1024;
const MAX_PHOTO = 600 * 1024;
const MAX_CARDS_BODY = 1024 * 1024;
const TOKEN_RE = /^[A-Za-z0-9_-]{16,64}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-9a-f][0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EVENT_TYPES = new Set(['start', 'end', 'route', 'note']);
const PHOTO_KINDS = new Set(['start_odo', 'end_odo', 'paper', 'other']);
const LIMIT_TOKEN = 60, LIMIT_IP = 300, WINDOW = 600;      // requests per 10 minutes

const HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'camera=(self), geolocation=(), microphone=()',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' blob: data:; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
  'Cache-Control': 'no-store',
};

const now = () => Math.floor(Date.now() / 1000);
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
const sha256Hex = async (data) => hex(await crypto.subtle.digest('SHA-256', typeof data === 'string' ? enc.encode(data) : data));
async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, enc.encode(msg)));
}
function same(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
const iso = (s) => new Date(s * 1000).toISOString();

function reply(status, data, extra) {
  const h = { ...HEADERS, 'Content-Type': 'application/json; charset=utf-8', ...(extra || {}) };
  return new Response(data === null ? null : JSON.stringify(data), { status, headers: h });
}
class Fail extends Error { constructor(status, msg, extra) { super(msg); this.status = status; this.extra = extra; } }

async function readBody(request, max) {
  const len = Number(request.headers.get('Content-Length') || 0);
  if (len > max) throw new Fail(413, 'Too large');
  const buf = new Uint8Array(await request.arrayBuffer());
  if (buf.length > max) throw new Fail(413, 'Too large');
  return buf;
}
async function readJson(request, max) {
  const buf = await readBody(request, max);
  try { return { data: JSON.parse(new TextDecoder().decode(buf)), buf }; } catch { throw new Fail(400, 'Not JSON'); }
}

async function limited(env, key, max) {
  const w = Math.floor(now() / WINDOW);
  const r = await env.DB.prepare('INSERT INTO rate(key, window, count) VALUES(?, ?, 1) ON CONFLICT(key, window) DO UPDATE SET count = count + 1 RETURNING count').bind(key, w).first();
  return r.count > max;
}

// ---------------------------------------------------------------- driver side
async function driver(request, env, url, parts) {
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  const token = parts[2];
  if (!TOKEN_RE.test(token || '')) throw new Fail(404, 'Not found');
  const th = await sha256Hex(token);
  if (await limited(env, 'ip:' + ip, LIMIT_IP) || await limited(env, 'tk:' + th, LIMIT_TOKEN)) throw new Fail(429, 'Too many requests', { 'Retry-After': '60' });
  const card = await env.DB.prepare('SELECT trip_id, body, cancelled, bound_device, expires_at FROM cards WHERE token_hash = ?').bind(th).first();
  if (!card) throw new Fail(404, 'Unknown link');
  if (card.expires_at && card.expires_at < now()) throw new Fail(410, 'This link has expired', { expired: true });
  const kind = parts[1], m = request.method;

  if (kind === 'card' && m === 'GET') {
    if (card.cancelled) throw new Fail(410, 'This trip was cancelled', { cancelled: true });
    return reply(200, { card: JSON.parse(card.body), bound: !!card.bound_device, serverTime: iso(now()) });
  }
  if (card.cancelled) throw new Fail(410, 'This trip was cancelled', { cancelled: true });

  if (kind === 'receipts' && m === 'POST') {
    const { data } = await readJson(request, 8192);
    const ids = [...new Set((Array.isArray(data && data.uuids) ? data.uuids : []).map(String).filter((u) => UUID_RE.test(u)))].slice(0, 100);
    if (!ids.length) return reply(200, { office: [], mailbox: [] });
    await ensureReceipts(env);
    const q = ids.map(() => '?').join(',');
    const [rc, ev, ph] = await Promise.all([
      env.DB.prepare(`SELECT uuid FROM receipts WHERE uuid IN (${q})`).bind(...ids).all(),
      env.DB.prepare(`SELECT uuid FROM events WHERE token_hash = ? AND uuid IN (${q})`).bind(th, ...ids).all(),
      env.DB.prepare(`SELECT uuid FROM photos WHERE token_hash = ? AND uuid IN (${q})`).bind(th, ...ids).all(),
    ]);
    const office = new Set((rc.results || []).map((r) => r.uuid));
    const mailbox = [...(ev.results || []), ...(ph.results || [])].map((r) => r.uuid).filter((u) => !office.has(u));
    return reply(200, { office: [...office], mailbox });
  }

  if (kind === 'bind' && m === 'POST') {
    const { data } = await readJson(request, 1024);
    const dev = String(data.deviceId || '');
    if (dev.length < 8 || dev.length > 64) throw new Fail(400, 'Bad device');
    if (!card.bound_device) {
      await env.DB.prepare('UPDATE cards SET bound_device = ? WHERE token_hash = ? AND bound_device IS NULL').bind(dev, th).run();
      const again = await env.DB.prepare('SELECT bound_device FROM cards WHERE token_hash = ?').bind(th).first();
      card.bound_device = again.bound_device;
    }
    if (card.bound_device === dev) return reply(200, { bound: true });
    return reply(200, { bound: false, secondDevice: true });
  }

  if (kind === 'event' && m === 'POST') {
    const { data, buf } = await readJson(request, MAX_JSON);
    if (!data || !UUID_RE.test(String(data.uuid || '')) || !EVENT_TYPES.has(data.type) || data.v !== 1) throw new Fail(400, 'Bad event');
    const dev = String(data.deviceId || '');
    if (dev.length < 8 || dev.length > 64) throw new Fail(400, 'Bad device');
    const have = await env.DB.prepare('SELECT recv_at FROM events WHERE uuid = ?').bind(data.uuid).first();
    if (have) return reply(200, { ok: true, recvAt: iso(have.recv_at), duplicate: true });
    let bound = card.bound_device;
    if (!bound) {
      await env.DB.prepare('UPDATE cards SET bound_device = ? WHERE token_hash = ? AND bound_device IS NULL').bind(dev, th).run();
      bound = (await env.DB.prepare('SELECT bound_device FROM cards WHERE token_hash = ?').bind(th).first()).bound_device;
    }
    const t = now();
    await env.DB.prepare('INSERT OR IGNORE INTO events(uuid, token_hash, trip_id, type, body, device_id, phone_at, recv_at, second) VALUES(?,?,?,?,?,?,?,?,?)')
      .bind(data.uuid, th, card.trip_id, data.type, new TextDecoder().decode(buf), dev, String(data.phoneAt || '').slice(0, 40), t, bound === dev ? 0 : 1).run();
    return reply(200, { ok: true, recvAt: iso(t), secondDevice: bound !== dev });
  }

  if (kind === 'photo' && m === 'PUT') {
    const id = parts[3];
    if (!UUID_RE.test(id || '')) throw new Fail(400, 'Bad photo id');
    const k = request.headers.get('X-Kind') || '';
    if (!PHOTO_KINDS.has(k)) throw new Fail(400, 'Bad kind');
    const buf = await readBody(request, MAX_PHOTO);
    if (buf.length < 100) throw new Fail(400, 'Empty photo');
    if (!(buf[0] === 0xff && buf[1] === 0xd8)) throw new Fail(400, 'Not a JPEG photo');
    const sum = await sha256Hex(buf);
    if ((request.headers.get('X-Sha256') || '').toLowerCase() !== sum) throw new Fail(400, 'The photo arrived damaged; send it again');
    const have = await env.DB.prepare('SELECT recv_at FROM photos WHERE uuid = ?').bind(id).first();
    if (have) return reply(200, { ok: true, recvAt: iso(have.recv_at), duplicate: true });
    const t = now();
    const ev = request.headers.get('X-Event') || '';
    await env.DB.prepare('INSERT OR IGNORE INTO photos(uuid, token_hash, trip_id, kind, fallback, event_uuid, sha256, size, data, recv_at) VALUES(?,?,?,?,?,?,?,?,?,?)')
      .bind(id, th, card.trip_id, k, request.headers.get('X-Fallback') === '1' ? 1 : 0, UUID_RE.test(ev) ? ev : null, sum, buf.length, buf, t).run();
    return reply(200, { ok: true, recvAt: iso(t) });
  }
  throw new Fail(404, 'Not found');
}

// ---------------------------------------------------------------- office side
async function officeAuth(request, env, url, bodyBytes) {
  if (!env.OFFICE_SECRET) throw new Fail(503, 'The gateway has no office secret yet');
  const t = Number(request.headers.get('X-TO-Time')), nonce = request.headers.get('X-TO-Nonce') || '', sig = (request.headers.get('X-TO-Sig') || '').toLowerCase();
  if (!t || Math.abs(now() - t) > 300 || !/^[0-9a-f]{16,64}$/.test(nonce) || !sig) throw new Fail(401, 'Unauthorised');
  const expected = await hmacHex(env.OFFICE_SECRET, [request.method, url.pathname + url.search, String(t), nonce, await sha256Hex(bodyBytes)].join('\n'));
  if (!same(expected, sig)) throw new Fail(401, 'Unauthorised');
  const r = await env.DB.prepare('INSERT OR IGNORE INTO nonces(nonce, at) VALUES(?, ?)').bind(nonce, now()).run();
  if (!(r.meta ? r.meta.changes : r.changes)) throw new Fail(401, 'Replayed request');
}

// Links the office replaced. A removed card is remembered here so a PC that still has the old link in its data cannot publish it again.
// schema.sql was run by hand once on existing mailboxes, so the table is also created here the first time it is needed.
const REVOKED_DAYS = 60;
const revokedReady = new WeakSet();
async function ensureRevoked(env) {
  if (revokedReady.has(env.DB)) return;
  await env.DB.prepare('CREATE TABLE IF NOT EXISTS revoked (token_hash TEXT PRIMARY KEY, at INTEGER NOT NULL)').run();
  revokedReady.add(env.DB);
}

// What the office has acknowledged. The phone asks for these receipts and only then forgets its own copy: "received by the mailbox" is not "stored by the office".
// A receipt is just the id of the item and the time; items the mailbox dropped without an acknowledgement (retention) have none, so the phone sends them again.
const RECEIPT_DAYS = 60;
const receiptsReady = new WeakSet();
async function ensureReceipts(env) {
  if (receiptsReady.has(env.DB)) return;
  await env.DB.prepare('CREATE TABLE IF NOT EXISTS receipts (uuid TEXT PRIMARY KEY, at INTEGER NOT NULL)').run();
  receiptsReady.add(env.DB);
}
const marks = (n, per) => Array.from({ length: n }, () => '(' + Array(per).fill('?').join(',') + ')').join(',');
function chunks(list, n) { const out = []; for (let i = 0; i < list.length; i += n) out.push(list.slice(i, i + n)); return out; }

async function office(request, env, url, parts) {
  const bodyBytes = request.method === 'GET' ? new Uint8Array(0) : await readBody(request, MAX_CARDS_BODY);
  await officeAuth(request, env, url, bodyBytes);
  const what = parts[1], m = request.method;
  const json = () => { try { return JSON.parse(new TextDecoder().decode(bodyBytes)); } catch { throw new Fail(400, 'Not JSON'); } };

  if (what === 'cards' && m === 'PUT') {
    const d = json(), stmts = [];
    await ensureRevoked(env);
    for (const c of (d.cards || []).slice(0, 500)) {
      if (!/^[0-9a-f]{64}$/.test(c.tokenHash || '') || !c.tripId) throw new Fail(400, 'Bad card');
      const body = JSON.stringify(c.body || {});
      if (body.length > 8192) throw new Fail(400, 'Card too large');
      // a revoked link is never published again (WHERE NOT EXISTS), whichever PC sends it
      stmts.push(env.DB.prepare('INSERT INTO cards(token_hash, trip_id, body, cancelled, expires_at, updated_at) SELECT ?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM revoked WHERE token_hash = ?) ON CONFLICT(token_hash) DO UPDATE SET body = excluded.body, cancelled = excluded.cancelled, expires_at = excluded.expires_at, updated_at = excluded.updated_at')
        .bind(c.tokenHash, c.tripId, body, c.cancelled ? 1 : 0, c.expiresAt || null, now(), c.tokenHash));
      if (c.releaseDevice) stmts.push(env.DB.prepare('UPDATE cards SET bound_device = NULL WHERE token_hash = ?').bind(c.tokenHash));
    }
    for (const h of (d.remove || []).slice(0, 500)) {
      if (!/^[0-9a-f]{64}$/.test(String(h))) continue;
      stmts.push(env.DB.prepare('INSERT OR REPLACE INTO revoked(token_hash, at) VALUES(?,?)').bind(String(h), now()));
      stmts.push(env.DB.prepare('DELETE FROM cards WHERE token_hash = ?').bind(String(h)));
    }
    if (stmts.length) await env.DB.batch(stmts);
    return reply(200, { ok: true, cards: (d.cards || []).length });
  }
  if (what === 'inbox' && m === 'GET') {
    const limit = Math.min(200, Math.max(1, Number(url.searchParams.get('limit')) || 100));
    const ev = await env.DB.prepare('SELECT e.id, e.uuid, e.trip_id, e.type, e.body, e.device_id, e.phone_at, e.recv_at, e.second, c.bound_device FROM events e LEFT JOIN cards c ON c.token_hash = e.token_hash ORDER BY e.id LIMIT ?').bind(limit).all();
    const ph = await env.DB.prepare('SELECT id, uuid, trip_id, kind, fallback, event_uuid, sha256, size, recv_at FROM photos ORDER BY id LIMIT ?').bind(limit).all();
    return reply(200, {
      events: (ev.results || []).map((r) => ({ id: r.id, uuid: r.uuid, tripId: r.trip_id, type: r.type, body: JSON.parse(r.body), deviceId: r.device_id, phoneAt: r.phone_at, recvAt: iso(r.recv_at), second: !!r.second, boundDevice: r.bound_device || '' })),
      photos: (ph.results || []).map((r) => ({ id: r.id, uuid: r.uuid, tripId: r.trip_id, kind: r.kind, fallback: !!r.fallback, eventUuid: r.event_uuid || '', sha256: r.sha256, size: r.size, recvAt: iso(r.recv_at) })),
    });
  }
  if (what === 'photo' && m === 'GET') {
    if (!UUID_RE.test(parts[2] || '')) throw new Fail(400, 'Bad id');
    const r = await env.DB.prepare('SELECT data, sha256 FROM photos WHERE uuid = ?').bind(parts[2]).first();
    if (!r) throw new Fail(404, 'No such photo');
    return new Response(new Uint8Array(r.data), { status: 200, headers: { ...HEADERS, 'Content-Type': 'image/jpeg', 'X-Sha256': r.sha256 } });
  }
  if (what === 'ack' && m === 'POST') {
    const d = json(), stmts = [];
    await ensureReceipts(env);
    const ev = (d.events || []).slice(0, 500).filter((u) => UUID_RE.test(u)), ph = (d.photos || []).slice(0, 500).filter((u) => UUID_RE.test(u)), t = now();
    for (const c of chunks([...ev, ...ph], 40)) stmts.push(env.DB.prepare(`INSERT OR IGNORE INTO receipts(uuid, at) VALUES ${marks(c.length, 2)}`).bind(...c.flatMap((u) => [u, t])));
    for (const c of chunks(ev, 90)) stmts.push(env.DB.prepare(`DELETE FROM events WHERE uuid IN (${c.map(() => '?').join(',')})`).bind(...c));
    for (const c of chunks(ph, 90)) stmts.push(env.DB.prepare(`DELETE FROM photos WHERE uuid IN (${c.map(() => '?').join(',')})`).bind(...c));
    if (stmts.length) await env.DB.batch(stmts);
    return reply(200, { ok: true });
  }
  if (what === 'status' && m === 'GET') {
    const one = (sql) => env.DB.prepare(sql).first();
    const [e, p, c, old] = await Promise.all([one('SELECT COUNT(*) n FROM events'), one('SELECT COUNT(*) n FROM photos'), one('SELECT COUNT(*) n FROM cards'), one('SELECT MIN(recv_at) t FROM events')]);
    return reply(200, { version: 1, events: e.n, photos: p.n, cards: c.n, oldestUnackedSeconds: old.t ? now() - old.t : 0, serverTime: iso(now()) });
  }
  throw new Fail(404, 'Not found');
}

// ---------------------------------------------------------------- static pages and the entry point
// In the single-file bundle (build.js) the driver page files are embedded here; with wrangler they come from env.ASSETS.
let EMBEDDED_ASSETS = null;
const MIME = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', css: 'text/css; charset=utf-8', svg: 'image/svg+xml', webmanifest: 'application/manifest+json' };
async function fetchAsset(env, request, path) {
  if (env.ASSETS) {
    const u = new URL(request.url);
    u.pathname = path;
    return env.ASSETS.fetch(new Request(u.toString(), { method: 'GET' }));
  }
  const text = EMBEDDED_ASSETS && EMBEDDED_ASSETS[path];
  if (text === undefined || text === null) return new Response('Not found', { status: 404 });
  return new Response(text, { status: 200, headers: { 'Content-Type': MIME[path.split('.').pop()] || 'text/plain' } });
}
async function asset(env, request, path, extra) {
  const r = await fetchAsset(env, request, path);
  const h = new Headers(r.headers);
  for (const [k, v] of Object.entries(HEADERS)) h.set(k, v);
  h.set('Cache-Control', path.startsWith('/app/fonts/') ? 'public, max-age=31536000, immutable' : 'no-cache');
  for (const [k, v] of Object.entries(extra || {})) h.set(k, v);
  return new Response(r.body, { status: r.status, headers: h });
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const parts = url.pathname.split('/').filter(Boolean);
      const m = request.method;
      if (parts[0] === 'api') return await driver(request, env, url, parts);
      if (parts[0] === 'office') return await office(request, env, url, parts);
      if (parts[0] === 't' && parts.length === 2 && m === 'GET') return await asset(env, request, '/index.html');
      if (parts[0] === 'sw.js' && m === 'GET') return await asset(env, request, '/app/sw.js', { 'Service-Worker-Allowed': '/', 'Content-Type': 'text/javascript; charset=utf-8' });
      if (parts[0] === 'app' && m === 'GET') return await asset(env, request, url.pathname);
      if (url.pathname === '/' && m === 'GET') return reply(200, { name: 'Trip Orders gateway', ok: true });
      return reply(404, { error: 'Not found' });
    } catch (e) {
      if (e instanceof Fail) return reply(e.status, { error: e.message, ...(e.extra && !e.extra['Retry-After'] ? e.extra : {}) }, e.extra && e.extra['Retry-After'] ? { 'Retry-After': e.extra['Retry-After'] } : undefined);
      return reply(500, { error: 'Server error' });
    }
  },

  async scheduled(_event, env) {
    const days = Number(env.RETENTION_DAYS || 30), cut = now() - days * 86400;
    await ensureRevoked(env);
    await ensureReceipts(env);
    await env.DB.batch([
      env.DB.prepare('DELETE FROM revoked WHERE at < ?').bind(now() - REVOKED_DAYS * 86400),
      env.DB.prepare('DELETE FROM receipts WHERE at < ?').bind(now() - RECEIPT_DAYS * 86400),
      env.DB.prepare('DELETE FROM events WHERE recv_at < ?').bind(cut),
      env.DB.prepare('DELETE FROM photos WHERE recv_at < ?').bind(cut),
      env.DB.prepare('DELETE FROM cards WHERE expires_at IS NOT NULL AND expires_at < ?').bind(now() - 7 * 86400),
      env.DB.prepare('DELETE FROM nonces WHERE at < ?').bind(now() - 3600),
      env.DB.prepare('DELETE FROM rate WHERE window < ?').bind(Math.floor(now() / WINDOW) - 2),
    ]);
  },
};

export { hmacHex, sha256Hex };
