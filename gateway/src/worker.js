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
const LIMIT_TOKEN = 120, LIMIT_IP = 1200, WINDOW = 600;      // requests per 10 minutes
const LEGACY_TENANT = 'legacy';
const TENANT_RE = /^[0-9a-f]{32}$/;
const REGISTER_BODY_MAX = 2048;
const REGISTER_PER_HOUR = 5, REGISTER_PER_DAY = 50;
const REGISTER_GLOBAL_PER_HOUR = 30, REGISTER_GLOBAL_PER_DAY = 200;
const TENANT_IDLE_DAYS = 90;
const DEFAULT_MAX_CARDS = 2000;
const DEFAULT_MAX_PHOTO_BYTES = 50 * 1024 * 1024;

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
// Bounded constant-time compare. HMAC hex is 64 characters; a different length never matches,
// and a very long value cannot stretch the loop. The secret itself is never compared.
function same(a, b) {
  const n = 64;
  let d = (a ? a.length : 0) ^ (b ? b.length : 0);
  for (let i = 0; i < n; i++) {
    const x = a && i < a.length ? a.charCodeAt(i) : 0;
    const y = b && i < b.length ? b.charCodeAt(i) : 0;
    d |= x ^ y;
  }
  return d === 0;
}
function masterKey(env) {
  const k = typeof env.MASTER_KEY === 'string' ? env.MASTER_KEY : '';
  // Missing, blank, or too short: refuse. Never fall open and never treat a placeholder as a key.
  return k.trim().length >= 16 ? k : '';
}
function changesOf(result) {
  const n = result && result.meta ? result.meta.changes : result && result.changes;
  return Number(n) || 0;
}
function columnNames(info) {
  return (info.results || []).map((c) => c.name);
}
function primaryKey(info) {
  return (info.results || []).filter((c) => c.pk > 0).sort((a, b) => a.pk - b.pk).map((c) => c.name);
}
async function addColumn(env, sql) {
  try {
    await env.DB.prepare(sql).run();
  } catch (e) {
    // Two requests can migrate the same table at once. The loser sees "duplicate column"; the rows stay.
    if (!/duplicate column/i.test(String(e && e.message || e))) throw e;
  }
}
const iso = (s) => new Date(s * 1000).toISOString();

function reply(status, data, extra) {
  const h = { ...HEADERS, 'Content-Type': 'application/json; charset=utf-8', ...(extra || {}) };
  return new Response(data === null ? null : JSON.stringify(data), { status, headers: h });
}
class Fail extends Error { constructor(status, msg, extra) { super(msg); this.status = status; this.extra = extra; } }

async function readBody(request, max) {
  const declared = request.headers.get('Content-Length');
  if (declared !== null && Number(declared) > max) throw new Fail(413, 'Too large');
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > max) {
        try { await reader.cancel(); } catch { /* already failed */ }
        throw new Fail(413, 'Too large');
      }
      chunks.push(value);
    }
  } catch (e) {
    if (e instanceof Fail) throw e;
    throw new Fail(400, 'Bad body');
  }
  const buf = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { buf.set(chunk, offset); offset += chunk.byteLength; }
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
// A window stored as its unix start, so the 10-minute cleanup (small window numbers) does not wipe hour/day rows.
async function limitedSpan(env, key, max, span) {
  const w = Math.floor(now() / span) * span;
  const r = await env.DB.prepare('INSERT INTO rate(key, window, count) VALUES(?, ?, 1) ON CONFLICT(key, window) DO UPDATE SET count = count + 1 RETURNING count').bind(key, w).first();
  return r.count > max;
}

function capNumber(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

// ---------------------------------------------------------------- one mailbox per install
// MASTER_KEY is a Worker secret. The office secret is HMAC(MASTER_KEY, "TO-TENANT1|"+tenantId) and is never written to D1.
const tenantReady = new WeakSet();
async function tenantSecret(master, tenantId) {
  return hmacHex(master, 'TO-TENANT1|' + tenantId);
}
async function ensureTenant(env) {
  if (tenantReady.has(env.DB)) return;
  await env.DB.prepare('CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL, install_hash TEXT)').run();
  await env.DB.prepare('CREATE TABLE IF NOT EXISTS usage (tenant TEXT NOT NULL, day INTEGER NOT NULL, bytes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (tenant, day))').run();
  const tenantCols = columnNames(await env.DB.prepare('PRAGMA table_info(tenants)').all());
  if (tenantCols.length && !tenantCols.includes('install_hash')) await addColumn(env, 'ALTER TABLE tenants ADD COLUMN install_hash TEXT');
  // The hash index is created here, not in schema.sql: an old database has no install_hash column yet, and a
  // CREATE INDEX on a missing column would abort deploy. Several NULLs are allowed, so old rows stay valid.
  await env.DB.prepare('CREATE UNIQUE INDEX IF NOT EXISTS tenants_install ON tenants(install_hash)').run();
  for (const table of ['cards', 'events', 'photos', 'revoked']) {
    const names = columnNames(await env.DB.prepare('PRAGMA table_info(' + table + ')').all());
    if (!names.length || names.includes('tenant')) continue;   // missing table, or already migrated
    await addColumn(env, 'ALTER TABLE ' + table + " ADD COLUMN tenant TEXT NOT NULL DEFAULT 'legacy'");
  }
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS events_tenant ON events (tenant, id)').run();
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS photos_tenant ON photos (tenant, id)').run();
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS cards_tenant ON cards (tenant)').run();
  tenantReady.add(env.DB);
}
async function touchTenant(env, tenant) {
  if (!tenant || tenant === LEGACY_TENANT) return;
  await env.DB.prepare('UPDATE tenants SET last_seen = ? WHERE id = ?').bind(now(), tenant).run();
}

// ---------------------------------------------------------------- driver side
async function driver(request, env, url, parts) {
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  const token = parts[2];
  if (!TOKEN_RE.test(token || '')) throw new Fail(404, 'Not found');
  const th = await sha256Hex(token);
  if (await limited(env, 'ip:' + ip, LIMIT_IP) || await limited(env, 'tk:' + th, LIMIT_TOKEN)) throw new Fail(429, 'Too many requests', { 'Retry-After': '60' });
  await ensureTenant(env);
  const card = await env.DB.prepare('SELECT trip_id, body, cancelled, bound_device, expires_at, tenant FROM cards WHERE token_hash = ?').bind(th).first();
  if (!card) throw new Fail(404, 'Unknown link');
  if (card.expires_at && card.expires_at < now()) throw new Fail(410, 'This link has expired', { expired: true });
  const kind = parts[1], m = request.method;
  const tenant = card.tenant || LEGACY_TENANT;

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
    // Opening the link only asks "may I go on?": the phone becomes THE phone of the trip with its first real message (event), not with a look.
    // So a dispatcher who opens the link to check it does not take the trip away from the driver.
    if (!card.bound_device || card.bound_device === dev) return reply(200, { bound: true });
    return reply(200, { bound: false, secondDevice: true });
  }

  if (kind === 'event' && m === 'POST') {
    const { data, buf } = await readJson(request, MAX_JSON);
    if (!data || !UUID_RE.test(String(data.uuid || '')) || !EVENT_TYPES.has(data.type) || data.v !== 1) throw new Fail(400, 'Bad event');
    const dev = String(data.deviceId || '');
    if (dev.length < 8 || dev.length > 64) throw new Fail(400, 'Bad device');
    const have = await env.DB.prepare('SELECT recv_at, token_hash FROM events WHERE uuid = ?').bind(data.uuid).first();
    if (have) {
      // The same phone retrying is a duplicate. Another mailbox's row must not look like success: the phone would drop its copy.
      if (have.token_hash === th) return reply(200, { ok: true, recvAt: iso(have.recv_at), duplicate: true });
      throw new Fail(503, 'Try again');
    }
    let bound = card.bound_device;
    if (!bound) {
      await env.DB.prepare('UPDATE cards SET bound_device = ? WHERE token_hash = ? AND bound_device IS NULL').bind(dev, th).run();
      bound = (await env.DB.prepare('SELECT bound_device FROM cards WHERE token_hash = ?').bind(th).first()).bound_device;
    }
    const t = now();
    const ins = await env.DB.prepare('INSERT OR IGNORE INTO events(uuid, token_hash, trip_id, type, body, device_id, phone_at, recv_at, second, tenant) VALUES(?,?,?,?,?,?,?,?,?,?)')
      .bind(data.uuid, th, card.trip_id, data.type, new TextDecoder().decode(buf), dev, String(data.phoneAt || '').slice(0, 40), t, bound === dev ? 0 : 1, tenant).run();
    if (!changesOf(ins)) {
      const again = await env.DB.prepare('SELECT recv_at, token_hash FROM events WHERE uuid = ?').bind(data.uuid).first();
      if (again && again.token_hash === th) return reply(200, { ok: true, recvAt: iso(again.recv_at), duplicate: true });
      throw new Fail(503, 'Try again');
    }
    await touchTenant(env, tenant);
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
    const have = await env.DB.prepare('SELECT recv_at, token_hash FROM photos WHERE uuid = ?').bind(id).first();
    if (have) {
      if (have.token_hash === th) return reply(200, { ok: true, recvAt: iso(have.recv_at), duplicate: true });
      throw new Fail(503, 'Try again');
    }
    const day = Math.floor(now() / 86400);
    const cap = capNumber(env.MAX_PHOTO_BYTES_PER_DAY, DEFAULT_MAX_PHOTO_BYTES);
    const used = await env.DB.prepare('SELECT bytes FROM usage WHERE tenant = ? AND day = ?').bind(tenant, day).first();
    if ((used ? used.bytes : 0) + buf.length > cap) throw new Fail(429, 'Too many photos today', { 'Retry-After': '3600' });
    const t = now();
    const ev = request.headers.get('X-Event') || '';
    const ins = await env.DB.prepare('INSERT OR IGNORE INTO photos(uuid, token_hash, trip_id, kind, fallback, event_uuid, sha256, size, data, recv_at, tenant) VALUES(?,?,?,?,?,?,?,?,?,?,?)')
      .bind(id, th, card.trip_id, k, request.headers.get('X-Fallback') === '1' ? 1 : 0, UUID_RE.test(ev) ? ev : null, sum, buf.length, buf, t, tenant).run();
    if (!changesOf(ins)) {
      const again = await env.DB.prepare('SELECT recv_at, token_hash FROM photos WHERE uuid = ?').bind(id).first();
      if (again && again.token_hash === th) return reply(200, { ok: true, recvAt: iso(again.recv_at), duplicate: true });
      throw new Fail(503, 'Try again');
    }
    await env.DB.prepare('INSERT INTO usage(tenant, day, bytes) VALUES(?, ?, ?) ON CONFLICT(tenant, day) DO UPDATE SET bytes = bytes + excluded.bytes').bind(tenant, day, buf.length).run();
    await touchTenant(env, tenant);
    return reply(200, { ok: true, recvAt: iso(t) });
  }
  throw new Fail(404, 'Not found');
}

// ---------------------------------------------------------------- office side
// No X-TO-Tenant: the historical single mailbox (OFFICE_SECRET), tenant 'legacy'. A tenant header selects that install's derived secret.
// The tenant id is part of the signed message, so a header cannot be swapped onto another office's signature.
async function officeAuth(request, env, url, bodyBytes) {
  const raw = request.headers.get('X-TO-Tenant');
  const tenantHeader = raw == null ? '' : String(raw).trim().toLowerCase();
  let secret, tenant;
  if (!tenantHeader) {
    if (!env.OFFICE_SECRET) throw new Fail(503, 'The gateway has no office secret yet');
    secret = env.OFFICE_SECRET;
    tenant = LEGACY_TENANT;
  } else {
    if (!TENANT_RE.test(tenantHeader)) throw new Fail(401, 'Unauthorised', { reason: 'secret' });
    const master = masterKey(env);
    if (!master) throw new Fail(503, 'The gateway has no master key yet');
    secret = await tenantSecret(master, tenantHeader);
    tenant = tenantHeader;
  }
  const t = Number(request.headers.get('X-TO-Time')), nonce = request.headers.get('X-TO-Nonce') || '', sig = (request.headers.get('X-TO-Sig') || '').toLowerCase();
  if (!t || !/^[0-9a-f]{16,64}$/.test(nonce) || !sig) throw new Fail(401, 'Unauthorised', { reason: 'secret' });
  // A clock that is off is told apart from a wrong secret, so the office is not sent chasing the secret (the skew is not a secret).
  if (Math.abs(now() - t) > 300) throw new Fail(401, 'Clock is off', { reason: 'clock', skewSeconds: t - now(), serverTime: iso(now()) });
  const parts = [request.method, url.pathname + url.search, String(t), nonce, await sha256Hex(bodyBytes)];
  if (tenantHeader) parts.push(tenantHeader);
  const expected = await hmacHex(secret, parts.join('\n'));
  if (!same(expected, sig)) throw new Fail(401, 'Unauthorised', { reason: 'secret' });
  const r = await env.DB.prepare('INSERT OR IGNORE INTO nonces(nonce, at) VALUES(?, ?)').bind(nonce, now()).run();
  if (!(r.meta ? r.meta.changes : r.changes)) throw new Fail(401, 'Replayed request', { reason: 'replay' });
  if (tenant !== LEGACY_TENANT) {
    const row = await env.DB.prepare('SELECT id FROM tenants WHERE id = ?').bind(tenant).first();
    // The signature already matched, so this office is real and its row was removed (90 idle days). Say so;
    // a wrong secret never reaches this line, and the answer carries no secret.
    if (!row) throw new Fail(401, 'This mailbox was removed after a long time with no use.', { reason: 'expired' });
    await touchTenant(env, tenant);
  }
  return tenant;
}

// installId is a 128-bit value the PC keeps and sends again if the answer was lost. D1 stores only its hash,
// so a database copy cannot be traded for the office secret. The secret is derived again, never stored.
async function installHash(buf) {
  if (!buf.length) return '';
  let data;
  try { data = JSON.parse(new TextDecoder().decode(buf)); } catch { throw new Fail(400, 'Not JSON'); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Fail(400, 'Not JSON');
  const id = String(data.installId || '').trim().toLowerCase();
  if (!id) return '';
  if (!TENANT_RE.test(id)) throw new Fail(400, 'Bad install');
  return sha256Hex(id);
}
async function register(request, env) {
  await ensureTenant(env);
  const master = masterKey(env);
  if (!master) throw new Fail(503, 'The gateway has no master key yet');
  // Known install first. A lost answer must be able to recover even when this address, or the
  // whole gateway, has already used its budget of new mailboxes. A bad body is refused here too,
  // before any counter moves.
  const hash = await installHash(await readBody(request, REGISTER_BODY_MAX));
  if (hash) {
    const existing = await env.DB.prepare('SELECT id FROM tenants WHERE install_hash = ?').bind(hash).first();
    if (existing) {
      await touchTenant(env, existing.id);
      return reply(200, { tenantId: existing.id, officeSecret: await tenantSecret(master, existing.id) });
    }
  }
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  if (await limitedSpan(env, 'reg:h:' + ip, REGISTER_PER_HOUR, 3600) || await limitedSpan(env, 'reg:d:' + ip, REGISTER_PER_DAY, 86400)) {
    throw new Fail(429, 'Too many registrations', { 'Retry-After': '3600' });
  }
  // Per address is not enough: a new address is cheap. The global ceiling is what stops a full disk.
  if (await limitedSpan(env, 'reg:gh', REGISTER_GLOBAL_PER_HOUR, 3600) || await limitedSpan(env, 'reg:gd', REGISTER_GLOBAL_PER_DAY, 86400)) {
    throw new Fail(429, 'Too many registrations', { 'Retry-After': '3600' });
  }
  const id = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, '0')).join('');
  const secret = await tenantSecret(master, id);
  const t = now();
  try {
    await env.DB.prepare('INSERT INTO tenants(id, created_at, last_seen, install_hash) VALUES(?, ?, ?, ?)').bind(id, t, t, hash || null).run();
  } catch (e) {
    if (hash && /UNIQUE/i.test(String(e && e.message || e))) {
      const existing = await env.DB.prepare('SELECT id FROM tenants WHERE install_hash = ?').bind(hash).first();
      if (existing) return reply(200, { tenantId: existing.id, officeSecret: await tenantSecret(master, existing.id) });
    }
    throw e;
  }
  return reply(200, { tenantId: id, officeSecret: secret });
}

// Links the office replaced. A removed card is remembered here so a PC that still has the old link in its data cannot publish it again.
// The tombstone lives as long as the link itself (its expiry + 7 days; 90 days when the card is not known any more; for ever when the link never expires):
// forgetting it earlier would let a PC that was off for months bring a still-valid revoked link back.
// schema.sql was run by hand once on existing mailboxes, so the table is also created (and its `until` column added) here the first time it is needed.
const REVOKED_UNKNOWN_DAYS = 90, REVOKED_MARGIN_DAYS = 7, REVOKED_FOREVER_DAYS = 3650;
const revokedReady = new WeakSet();
const REVOKED_NEW = `CREATE TABLE IF NOT EXISTS revoked (
  token_hash TEXT NOT NULL,
  at INTEGER NOT NULL,
  until INTEGER NOT NULL DEFAULT 0,
  tenant TEXT NOT NULL DEFAULT 'legacy',
  PRIMARY KEY (token_hash, tenant)
)`;
const REVOKED_COPY = `CREATE TABLE revoked_scope (
  token_hash TEXT NOT NULL,
  at INTEGER NOT NULL,
  until INTEGER NOT NULL DEFAULT 0,
  tenant TEXT NOT NULL DEFAULT 'legacy',
  PRIMARY KEY (token_hash, tenant)
)`;
// One tombstone per (link, mailbox). A single primary key on the hash let another office occupy it and
// stop the real office from keeping a replaced link dead.
async function ensureRevoked(env) {
  if (revokedReady.has(env.DB)) return;
  // Look before CREATE. Creating an empty `revoked` first would hide the case where the copy
  // is the only table left, and the migration would then treat the empty table as finished.
  await recoverRevoked(env);
  await env.DB.prepare(REVOKED_NEW).run();
  await migrateRevoked(env);
  await recoverRevoked(env);
  revokedReady.add(env.DB);
}
function alreadyMoved(e) {
  return /no such table/i.test(String(e && e.message || e));
}
async function recoverRevoked(env) {
  const scope = columnNames(await env.DB.prepare('PRAGMA table_info(revoked_scope)').all());
  if (!scope.length) return;
  const names = columnNames(await env.DB.prepare('PRAGMA table_info(revoked)').all());
  if (!names.length) {
    try { await env.DB.prepare('ALTER TABLE revoked_scope RENAME TO revoked').run(); }
    catch (e) { if (!alreadyMoved(e)) throw e; }
    return;
  }
  const kept = await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first();
  const saved = await env.DB.prepare('SELECT COUNT(*) n FROM revoked_scope').first();
  // The copy is the table that still has the rows (the rename did not happen). An empty new
  // table must not win. The swap is one transaction, so a second request cannot drop the rows.
  if ((kept ? kept.n : 0) === 0 && saved && saved.n > 0) {
    try {
      await env.DB.batch([
        env.DB.prepare('DROP TABLE revoked'),
        env.DB.prepare('ALTER TABLE revoked_scope RENAME TO revoked'),
      ]);
    } catch (e) { if (!alreadyMoved(e)) throw e; }
    return;
  }
  if (saved && saved.n > 0 && names.includes('tenant')) {
    try {
      await env.DB.prepare(`INSERT OR IGNORE INTO revoked (token_hash, at, until, tenant)
        SELECT token_hash, at, COALESCE(until, 0), CASE WHEN tenant IS NULL OR tenant = '' THEN 'legacy' ELSE tenant END FROM revoked_scope`).run();
    } catch (e) { if (!alreadyMoved(e)) throw e; }
  }
  await env.DB.prepare('DROP TABLE IF EXISTS revoked_scope').run();
}
async function migrateRevoked(env) {
  let info = await env.DB.prepare('PRAGMA table_info(revoked)').all();
  let names = columnNames(info);
  if (!names.length) return;
  if (!names.includes('until')) {
    await addColumn(env, 'ALTER TABLE revoked ADD COLUMN until INTEGER NOT NULL DEFAULT 0');
    // Only the default 0 left by ADD COLUMN. A second request must not rewrite tombstones that already have a date.
    await env.DB.prepare('UPDATE revoked SET until = at + ? WHERE until = 0').bind(REVOKED_UNKNOWN_DAYS * 86400).run();
  }
  if (!names.includes('tenant')) await addColumn(env, "ALTER TABLE revoked ADD COLUMN tenant TEXT NOT NULL DEFAULT 'legacy'");
  info = await env.DB.prepare('PRAGMA table_info(revoked)').all();
  const pk = primaryKey(info);
  if (pk.includes('token_hash') && pk.includes('tenant')) return;
  const before = await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first();
  await env.DB.batch([
    env.DB.prepare('DROP TABLE IF EXISTS revoked_scope'),
    env.DB.prepare(REVOKED_COPY),
    env.DB.prepare(`INSERT INTO revoked_scope (token_hash, at, until, tenant)
      SELECT token_hash, at, COALESCE(until, 0), CASE WHEN tenant IS NULL OR tenant = '' THEN 'legacy' ELSE tenant END FROM revoked`),
    env.DB.prepare('DROP TABLE revoked'),
    env.DB.prepare('ALTER TABLE revoked_scope RENAME TO revoked'),
  ]);
  const after = await env.DB.prepare('SELECT COUNT(*) n FROM revoked').first();
  if ((before ? before.n : 0) !== (after ? after.n : 0)) throw new Error('revoked migration lost rows');
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
  await ensureTenant(env);
  const tenant = await officeAuth(request, env, url, bodyBytes);
  const what = parts[1], m = request.method;
  const json = () => { try { return JSON.parse(new TextDecoder().decode(bodyBytes)); } catch { throw new Fail(400, 'Not JSON'); } };

  if (what === 'cards' && m === 'PUT') {
    const d = json(), stmts = [];
    await ensureRevoked(env);
    const incoming = (d.cards || []).slice(0, 500);
    const freshHashes = [];
    for (const c of incoming) {
      if (!/^[0-9a-f]{64}$/.test(c.tokenHash || '') || !c.tripId) throw new Fail(400, 'Bad card');
      freshHashes.push(c.tokenHash);
    }
    if (freshHashes.length) {
      const have = await env.DB.prepare(`SELECT token_hash FROM cards WHERE tenant = ? AND token_hash IN (${freshHashes.map(() => '?').join(',')})`).bind(tenant, ...freshHashes).all();
      const known = new Set((have.results || []).map((r) => r.token_hash));
      const adding = freshHashes.filter((h) => !known.has(h)).length;
      const count = await env.DB.prepare('SELECT COUNT(*) n FROM cards WHERE tenant = ?').bind(tenant).first();
      if ((count ? count.n : 0) + adding > capNumber(env.MAX_CARDS, DEFAULT_MAX_CARDS)) throw new Fail(429, 'Too many trips in the mailbox');
    }
    for (const c of incoming) {
      const body = JSON.stringify(c.body || {});
      if (body.length > 8192) throw new Fail(400, 'Card too large');
      // a revoked link of THIS mailbox is never published again. Another install's card with the same hash is left alone.
      // A live mailbox is never overwritten. A card whose mailbox row is already gone (the 90-day cleanup
      // deletes the row last) can be claimed again by the office that still holds the link, so the link works.
      stmts.push(env.DB.prepare('INSERT INTO cards(token_hash, trip_id, body, cancelled, expires_at, updated_at, tenant) SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM revoked WHERE token_hash = ? AND tenant = ?) ON CONFLICT(token_hash) DO UPDATE SET body = excluded.body, cancelled = excluded.cancelled, expires_at = excluded.expires_at, updated_at = excluded.updated_at, tenant = excluded.tenant WHERE cards.tenant = excluded.tenant OR (cards.tenant != \'legacy\' AND NOT EXISTS (SELECT 1 FROM tenants WHERE id = cards.tenant))')
        .bind(c.tokenHash, c.tripId, body, c.cancelled ? 1 : 0, c.expiresAt || null, now(), tenant, c.tokenHash, tenant));
      if (c.releaseDevice) stmts.push(env.DB.prepare('UPDATE cards SET bound_device = NULL WHERE token_hash = ? AND tenant = ?').bind(c.tokenHash, tenant));
    }
    for (const h of (d.remove || []).slice(0, 500)) {
      if (!/^[0-9a-f]{64}$/.test(String(h))) continue;
      stmts.push(env.DB.prepare('INSERT INTO revoked(token_hash, at, until, tenant) VALUES(?, ?, COALESCE((SELECT CASE WHEN expires_at IS NULL THEN ? ELSE MAX(expires_at, ?) + ? END FROM cards WHERE token_hash = ? AND tenant = ?), ?), ?) ON CONFLICT(token_hash, tenant) DO UPDATE SET until = MAX(until, excluded.until)')
        .bind(String(h), now(), now() + REVOKED_FOREVER_DAYS * 86400, now(), REVOKED_MARGIN_DAYS * 86400, String(h), tenant, now() + REVOKED_UNKNOWN_DAYS * 86400, tenant));
      stmts.push(env.DB.prepare('DELETE FROM cards WHERE token_hash = ? AND tenant = ?').bind(String(h), tenant));
    }
    if (stmts.length) await env.DB.batch(stmts);
    return reply(200, { ok: true, cards: incoming.length });
  }
  if (what === 'inbox' && m === 'GET') {
    const limit = Math.min(200, Math.max(1, Number(url.searchParams.get('limit')) || 100));
    const ev = await env.DB.prepare('SELECT e.id, e.uuid, e.trip_id, e.type, e.body, e.device_id, e.phone_at, e.recv_at, e.second, c.bound_device FROM events e LEFT JOIN cards c ON c.token_hash = e.token_hash AND c.tenant = e.tenant WHERE e.tenant = ? ORDER BY e.id LIMIT ?').bind(tenant, limit).all();
    const ph = await env.DB.prepare('SELECT id, uuid, trip_id, kind, fallback, event_uuid, sha256, size, recv_at FROM photos WHERE tenant = ? ORDER BY id LIMIT ?').bind(tenant, limit).all();
    return reply(200, {
      events: (ev.results || []).map((r) => ({ id: r.id, uuid: r.uuid, tripId: r.trip_id, type: r.type, body: JSON.parse(r.body), deviceId: r.device_id, phoneAt: r.phone_at, recvAt: iso(r.recv_at), second: !!r.second, boundDevice: r.bound_device || '' })),
      photos: (ph.results || []).map((r) => ({ id: r.id, uuid: r.uuid, tripId: r.trip_id, kind: r.kind, fallback: !!r.fallback, eventUuid: r.event_uuid || '', sha256: r.sha256, size: r.size, recvAt: iso(r.recv_at) })),
    });
  }
  if (what === 'photo' && m === 'GET') {
    if (!UUID_RE.test(parts[2] || '')) throw new Fail(400, 'Bad id');
    const r = await env.DB.prepare('SELECT data, sha256 FROM photos WHERE uuid = ? AND tenant = ?').bind(parts[2], tenant).first();
    if (!r) throw new Fail(404, 'No such photo');
    return new Response(new Uint8Array(r.data), { status: 200, headers: { ...HEADERS, 'Content-Type': 'image/jpeg', 'X-Sha256': r.sha256 } });
  }
  if (what === 'ack' && m === 'POST') {
    const d = json(), stmts = [];
    await ensureReceipts(env);
    const askedE = (d.events || []).slice(0, 500).filter((u) => UUID_RE.test(u)), askedP = (d.photos || []).slice(0, 500).filter((u) => UUID_RE.test(u)), t = now();
    const owned = async (table, ids) => {
      if (!ids.length) return [];
      const r = await env.DB.prepare(`SELECT uuid FROM ${table} WHERE tenant = ? AND uuid IN (${ids.map(() => '?').join(',')})`).bind(tenant, ...ids).all();
      return (r.results || []).map((row) => row.uuid);
    };
    const ev = await owned('events', askedE), ph = await owned('photos', askedP);
    for (const c of chunks([...ev, ...ph], 40)) stmts.push(env.DB.prepare(`INSERT OR IGNORE INTO receipts(uuid, at) VALUES ${marks(c.length, 2)}`).bind(...c.flatMap((u) => [u, t])));
    for (const c of chunks(ev, 80)) stmts.push(env.DB.prepare(`DELETE FROM events WHERE tenant = ? AND uuid IN (${c.map(() => '?').join(',')})`).bind(tenant, ...c));
    for (const c of chunks(ph, 80)) stmts.push(env.DB.prepare(`DELETE FROM photos WHERE tenant = ? AND uuid IN (${c.map(() => '?').join(',')})`).bind(tenant, ...c));
    if (stmts.length) await env.DB.batch(stmts);
    return reply(200, { ok: true });
  }
  if (what === 'status' && m === 'GET') {
    const oneT = (sql) => env.DB.prepare(sql).bind(tenant).first();
    const [e, p, c, old] = await Promise.all([oneT('SELECT COUNT(*) n FROM events WHERE tenant = ?'), oneT('SELECT COUNT(*) n FROM photos WHERE tenant = ?'), oneT('SELECT COUNT(*) n FROM cards WHERE tenant = ?'), oneT('SELECT MIN(recv_at) t FROM events WHERE tenant = ?')]);
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
      if (parts[0] === 'office' && parts[1] === 'register' && m === 'POST') return await register(request, env);
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
    await ensureTenant(env);
    await ensureRevoked(env);
    await ensureReceipts(env);
    const idle = now() - TENANT_IDLE_DAYS * 86400;
    const old = await env.DB.prepare('SELECT id FROM tenants WHERE last_seen < ?').bind(idle).all();
    // One mailbox is one group. A batch limit must not delete the card and leave the tenant row:
    // the office would still be signed in, so it would not open the mailbox again, and the link would 404.
    const groups = [];
    for (const row of old.results || []) {
      groups.push([
        env.DB.prepare('DELETE FROM cards WHERE tenant = ?').bind(row.id),
        env.DB.prepare('DELETE FROM events WHERE tenant = ?').bind(row.id),
        env.DB.prepare('DELETE FROM photos WHERE tenant = ?').bind(row.id),
        env.DB.prepare('DELETE FROM revoked WHERE tenant = ?').bind(row.id),
        env.DB.prepare('DELETE FROM usage WHERE tenant = ?').bind(row.id),
        env.DB.prepare('DELETE FROM tenants WHERE id = ?').bind(row.id),
      ]);
    }
    const cleanup = [
      env.DB.prepare('DELETE FROM revoked WHERE until < ?').bind(now()),
      env.DB.prepare('DELETE FROM receipts WHERE at < ?').bind(now() - RECEIPT_DAYS * 86400),
      env.DB.prepare('DELETE FROM events WHERE recv_at < ?').bind(cut),
      env.DB.prepare('DELETE FROM photos WHERE recv_at < ?').bind(cut),
      env.DB.prepare('DELETE FROM cards WHERE expires_at IS NOT NULL AND expires_at < ?').bind(now() - 7 * 86400),
      env.DB.prepare('DELETE FROM nonces WHERE at < ?').bind(now() - 3600),
      env.DB.prepare('DELETE FROM rate WHERE window < ?').bind(Math.floor(now() / WINDOW) - 2),
      env.DB.prepare('DELETE FROM rate WHERE key LIKE ? AND window < ?').bind('reg:%', now() - 2 * 86400),
      env.DB.prepare('DELETE FROM usage WHERE day < ?').bind(Math.floor(now() / 86400) - 2),
    ];
    // D1 accepts a limited batch. Pack whole mailboxes, then the daily retention, 40 statements at a time.
    let batch = [];
    const flush = async () => { if (batch.length) { await env.DB.batch(batch); batch = []; } };
    for (const group of groups) {
      if (batch.length && batch.length + group.length > 40) await flush();
      batch.push(...group);
    }
    for (const stmt of cleanup) {
      if (batch.length >= 40) await flush();
      batch.push(stmt);
    }
    await flush();
  },
};

export { hmacHex, sha256Hex };
