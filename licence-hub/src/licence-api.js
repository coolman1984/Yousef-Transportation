import {
  issueTrialCode, issueTrialWindowCode, issuePaidUntilCode, issuePermanentCode, paidPresetLastDay, normalize,
  importSigningKey,
} from './afcodes.js';
import { hex } from './auth.js';
import { calendarDateInTz, isValidCalendarIso, shiftCalendarDays } from './calendar.js';
import { signHubCalendar } from './hub-time.js';

const enc = new TextEncoder();
const now = () => Math.floor(Date.now() / 1000);
const defaultOfflineTails = new Map();

function offlineTailMap(env) {
  if (!env._offlineTails) {
    env._offlineTails = defaultOfflineTails;
  }
  return env._offlineTails;
}
const WINDOW = 600;
const TIME_IP_LIMIT = 120;
const TIME_MAX_IPS = 5000;
const timeIps = new Map();
let timeWindow;

const REQUIRED = ['kind', 'device', 'machine', 'nonce', 'shop', 'version'];
export const REASON_PAID_IN_STUDIO = 'paid_in_licence_studio';
export const REASON_PAID_KEY_MISSING = 'paid_signing_key_missing';
const HUB_TIME_KID_TRIAL = 'trial-hub';
const HUB_TIME_KID_PAID = 'paid';

const MAX_DEVICE = 32;
const MAX_MACHINE = 128;
const MAX_NONCE = 80;
const MAX_PENDING_PER_IP = 8;
const DEFAULT_PENDING_TTL_SEC = 900;
const TRIAL_DAYS_MIN = 1;
const TRIAL_DAYS_MAX = 14;

/** Inclusive trial length the hub may sign (office reader caps at 14 regardless of env). */
export function hubTrialDaysInclusive(raw) {
  const days = Number(raw);
  if (!Number.isFinite(days) || days < TRIAL_DAYS_MIN || days > TRIAL_DAYS_MAX) {
    throw new Error('trial_days_out_of_range');
  }
  return Math.floor(days);
}

/** Map Arabic-Indic and Eastern Arabic-Indic digits to ASCII 0-9. */
export function normalizeShopDigits(text) {
  return String(text || '').replace(/[\u0660-\u0669\u06F0-\u06F9]/g, (ch) => String(ch.charCodeAt(0) & 0xf));
}

/** Blank phone-like digit runs (>=7 digits; spaces/dashes/dots/parentheses allowed between digits). */
export function blankLongDigitRuns(text, minRun = 7) {
  const s = normalizeShopDigits(text);
  if (minRun < 2) return s;
  const re = new RegExp(
    `(?:\\([\\s.\\-()]*)?\\d(?:[\\s.\\-()]*\\d){${minRun - 1},}(?:[\\s.\\-()]*\\))?`,
    'g',
  );
  return s.replace(re, (chunk) => (chunk.replace(/\D/g, '').length >= minRun ? '' : chunk));
}

/** Payment reference fingerprint for D1 (raw ref is not stored). */
export async function refFingerprint(ref) {
  const r = String(ref || '').trim();
  if (!r) return '';
  return sha256Hex(r);
}

async function sha256Hex(data) {
  const buf = typeof data === 'string' ? enc.encode(data) : data;
  return hex(await crypto.subtle.digest('SHA-256', buf));
}

async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, enc.encode(msg)));
}

/** Deterministic poll token from nonce + server secret (returned only on the first request). */
export async function derivePollToken(sessionSecret, nonce) {
  if (!sessionSecret) throw new Error('no_session_secret');
  const digest = await hmacHex(sessionSecret, `licence-poll/v1|${nonce}`);
  return `lp_${digest.slice(0, 48)}`;
}

async function limited(env, key, max) {
  const w = Math.floor(now() / WINDOW);
  const r = await env.DB.prepare('INSERT INTO rate(key, window, count) VALUES(?, ?, 1) ON CONFLICT(key, window) DO UPDATE SET count = count + 1 RETURNING count').bind(key, w).first();
  return r.count > max;
}

// Same fixed-window pattern as limited(), without D1 work for this public route.
// Best effort per Worker isolate; add edge rate limiting in front of the Worker if needed.
function timeLimited(ip) {
  const w = Math.floor(now() / WINDOW);
  if (timeWindow !== w) {
    timeIps.clear();
    timeWindow = w;
  }
  const count = timeIps.get(ip) || 0;
  if (count >= TIME_IP_LIMIT || (!count && timeIps.size >= TIME_MAX_IPS)) return true;
  timeIps.set(ip, count + 1);
  return false;
}

export function products(env) {
  const raw = env.LICENCE_PRODUCTS;
  if (raw === undefined || raw === null || !String(raw).trim()) return null;
  const ids = String(raw).split(',').map((s) => s.trim()).filter(Boolean);
  if (!ids.length) return null;
  return new Set(ids);
}

/** Omitted `product` on licence/offline requests uses this id (set `LICENCE_DEFAULT_PRODUCT` or list first in `LICENCE_PRODUCTS`). */
export function defaultProduct(env) {
  const allowed = products(env);
  if (!allowed) return null;
  const explicit = String(env.LICENCE_DEFAULT_PRODUCT || '').trim();
  if (explicit && allowed.has(explicit)) return explicit;
  for (const id of allowed) return id;
  return null;
}

export function parseProductLabels(env) {
  const raw = env.LICENCE_PRODUCT_LABELS;
  if (!raw || typeof raw !== 'string') return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const out = {};
    for (const [id, label] of Object.entries(parsed)) {
      if (typeof id === 'string' && typeof label === 'string' && id.trim() && label) {
        out[id.trim()] = label;
      }
    }
    return out;
  } catch {
    return {};
  }
}

export function hubCalendarTz(env) {
  return String(env.LICENCE_CALENDAR_TZ || 'Africa/Cairo').trim() || 'Africa/Cairo';
}

export function ownerProductsPayload(env) {
  const allowed = products(env);
  if (!allowed) return null;
  return {
    products: [...allowed],
    labels: parseProductLabels(env),
    default_product: defaultProduct(env),
    calendar_tz: hubCalendarTz(env),
  };
}

export function productEnvSuffix(productId) {
  return String(productId || 'trip-orders').trim().toUpperCase().replace(/-/g, '_');
}

export function signingKeyForProduct(env, baseName, productId) {
  const specific = env[`${baseName}_${productEnvSuffix(productId)}`];
  if (specific) return specific;
  return env[baseName] || null;
}

/** First non-empty global or per-product secret in LICENCE_PRODUCTS order. */
export function anySigningKeyPem(env, baseName) {
  if (env[baseName]) return env[baseName];
  const allowed = products(env);
  if (!allowed) return null;
  for (const productId of allowed) {
    const specific = env[`${baseName}_${productEnvSuffix(productId)}`];
    if (specific) return specific;
  }
  return null;
}

export async function loadSigningKeys(env, productId = 'trip-orders') {
  const keys = { trialKey: null, paidKey: null };
  const trialPem = signingKeyForProduct(env, 'LICENCE_SIGNING_KEY', productId);
  const paidPem = signingKeyForProduct(env, 'PAID_SIGNING_KEY', productId);
  if (trialPem) keys.trialKey = await importSigningKey(trialPem);
  if (paidPem) keys.paidKey = await importSigningKey(paidPem);
  return keys;
}

function pendingTtl(env) {
  return Number(env.PENDING_TTL_SEC || DEFAULT_PENDING_TTL_SEC);
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra },
  });
}

/** Normalized 10-character device code — keys machine_trials and open-request checks. */
export function deviceKey(device) {
  const norm = normalize(String(device || ''));
  if (norm.length !== 10) throw new Error('bad_device_code');
  return norm;
}

export function deviceLockKey(dkey) {
  return `d:${dkey}`;
}

export function offlineRequestId(productId, dkey) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  return `offline:${product}:${dkey}`;
}

/** Pre–multi-product offline request id and lock row (trip-orders trial only). */
export function legacyOfflineRequestId(dkey) {
  return `offline:${dkey}`;
}

export function legacyOfflineLockKey(dkey) {
  return legacyOfflineRequestId(dkey);
}

/** Offline trial lock is per product + device so multiple products can share one device code. */
export function offlineDeviceLockKey(productId, dkey) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  return `od:${product}:${dkey}`;
}

export function machineLockKey(machineHash) {
  return `h:${machineHash}`;
}

/** Online trial lock: legacy d:/h: for trip-orders; pd:/ph: for other products. */
export function onlineDeviceLockKey(productId, dkey) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  if (product === 'trip-orders') return deviceLockKey(dkey);
  return `pd:${product}:${dkey}`;
}

export function onlineMachineLockKey(productId, machineHash) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  if (product === 'trip-orders') return machineLockKey(machineHash);
  return `ph:${product}:${machineHash}`;
}

function onlineLockKeys(productId, dkey, machineHash) {
  const locks = [onlineDeviceLockKey(productId, dkey)];
  if (machineHash) locks.push(onlineMachineLockKey(productId, machineHash));
  return locks;
}

/** 64-hex SHA-256 machine tag from the office app, or null when malformed. */
export function normalizeMachineHash(machine) {
  const m = String(machine || '').toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(m)) return null;
  return m;
}

async function trialLockRow(env, lockId) {
  const row = await env.DB.prepare('SELECT request_id FROM machine_trials WHERE machine = ?').bind(lockId).first();
  if (row) return row;
  if (lockId.startsWith('d:')) {
    return env.DB.prepare('SELECT request_id FROM machine_trials WHERE machine = ?').bind(lockId.slice(2)).first();
  }
  if (!lockId.includes(':')) {
    return env.DB.prepare('SELECT request_id FROM machine_trials WHERE machine = ?').bind(lockId).first();
  }
  return null;
}

/** Backfill d:/h: locks from pre-prefix machine_trials rows (upgrade-safe). */
export async function migrateLegacyTrialLocks(env) {
  const rows = await env.DB.prepare(
    `SELECT machine, request_id, at FROM machine_trials
     WHERE machine NOT LIKE 'd:%' AND machine NOT LIKE 'h:%'
       AND machine NOT LIKE 'od:%' AND machine NOT LIKE 'pd:%' AND machine NOT LIKE 'ph:%'
       AND machine NOT LIKE 'offline:%'`,
  ).bind().all();
  for (const row of rows.results || []) {
    const prefixed = deviceLockKey(row.machine);
    await env.DB.prepare(
      'INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING',
    ).bind(prefixed, row.request_id, row.at).run();
    const req = await env.DB.prepare('SELECT machine FROM licence_requests WHERE id = ?').bind(row.request_id).first();
    const machineHash = normalizeMachineHash(req?.machine);
    if (machineHash) {
      await env.DB.prepare(
        'INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING',
      ).bind(machineLockKey(machineHash), row.request_id, row.at).run();
    }
  }
}

/** Offline path: one trial per normalized device code only. */
export async function trialUsedForDevice(env, deviceKeyNorm) {
  const row = await trialLockRow(env, deviceLockKey(deviceKeyNorm));
  return Boolean(row);
}

/** Device-level trial locks for one product (offline od: plus online pd:/d:). */
export function productTrialDeviceLocks(productId, deviceKeyNorm) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  return [offlineDeviceLockKey(product, deviceKeyNorm), onlineDeviceLockKey(product, deviceKeyNorm)];
}

/** Machine-level trial locks for one product (online ph:/h:). */
export function productTrialMachineLocks(productId, machineHash) {
  if (!machineHash) return [];
  return [onlineMachineLockKey(productId, machineHash)];
}

async function anyTrialLockUsed(env, lockIds) {
  for (const lock of lockIds) {
    if (await trialLockRow(env, lock)) return true;
  }
  return false;
}

export async function trialUsedForOfflineProduct(env, productId, deviceKeyNorm, machineHash = null) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  if (await anyTrialLockUsed(env, productTrialDeviceLocks(product, deviceKeyNorm))) return true;
  if (await anyTrialLockUsed(env, productTrialMachineLocks(product, machineHash))) return true;
  if (product !== 'trip-orders') return false;
  if (await trialLockRow(env, legacyOfflineLockKey(deviceKeyNorm))) return true;
  const legacyReq = await env.DB.prepare(
    "SELECT id FROM licence_requests WHERE id = ? AND status IN ('issued', 'delivered')",
  ).bind(legacyOfflineRequestId(deviceKeyNorm)).first();
  return Boolean(legacyReq);
}

/** Online path: refuse when this product's trial lock was used on any channel. */
export async function trialUsedOnline(env, productId, deviceKeyNorm, machineHash) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  if (await anyTrialLockUsed(env, productTrialDeviceLocks(product, deviceKeyNorm))) return true;
  if (await anyTrialLockUsed(env, productTrialMachineLocks(product, machineHash))) return true;
  return false;
}

async function expireStalePending(env) {
  const cutoff = now() - pendingTtl(env);
  const t = now();
  await env.DB.prepare(
    "UPDATE licence_requests SET status = 'expired', reason = 'pending_timeout', updated_at = ? WHERE status = 'pending' AND created_at < ?",
  ).bind(t, cutoff).run();
}

async function openRequestForDevice(env, productId, deviceKeyNorm) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  const cutoff = now() - pendingTtl(env);
  return env.DB.prepare(
    "SELECT id FROM licence_requests WHERE device_key = ? AND product = ? AND status IN ('pending', 'approved') AND created_at >= ? LIMIT 1",
  ).bind(deviceKeyNorm, product, cutoff).first();
}

function hubCalendarDay(env) {
  const tz = env.LICENCE_CALENDAR_TZ || 'Africa/Cairo';
  return calendarDateInTz(new Date(), tz).iso;
}

export function hubTimeSigningMaterial(env) {
  const trialPem = env.LICENCE_SIGNING_KEY || null;
  const paidPem = env.PAID_SIGNING_KEY || null;
  if (!trialPem && !paidPem) return null;
  if (trialPem) return { pem: trialPem, kid: HUB_TIME_KID_TRIAL };
  if (paidPem) return { pem: paidPem, kid: HUB_TIME_KID_PAID };
  return null;
}

export function parseHubTimeNonce(url) {
  const raw = url.searchParams.get('nonce');
  if (raw === null || raw === '') return { ok: true, nonce: null };
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(raw)) return { ok: false };
  return { ok: true, nonce: raw };
}

export async function hubCalendarSigned(env, options = {}) {
  const day = hubCalendarDay(env);
  const material = hubTimeSigningMaterial(env);
  const serverTime = now();
  const unsigned = {
    calendar_day: day,
    serverTime,
    server_time: serverTime,
    signed: false,
  };
  if (!material) return unsigned;
  const key = await importSigningKey(material.pem);
  const signed = await signHubCalendar(key, material.kid, day, serverTime, {
    nonce: options.nonce || null,
  });
  return signed;
}

export function parseOwnerGrant(body = {}, env = {}) {
  const grant = String(body.grant || body.tier || 'trial').trim().toLowerCase();
  if (grant === 'trial' || grant === '14d') return { grant: 'trial' };
  if (grant === 'permanent' || grant === 'perm') return { grant: 'permanent' };
  if (grant === 'paid' || grant === 'monthly') {
    const preset = String(body.preset || '').trim();
    let until = String(body.paid_until || body.until || '').trim();
    if (preset && !until) {
      try {
        const tz = env.LICENCE_CALENDAR_TZ || 'Africa/Cairo';
        until = paidPresetLastDay(preset, new Date(), tz);
      } catch (e) {
        if (e?.message === 'date_out_of_range') throw e;
        throw new Error('bad_preset');
      }
    }
    if (!isValidCalendarIso(until)) throw new Error('bad_paid_until');
    return { grant: 'paid', paid_until: until };
  }
  throw new Error('bad_grant');
}

export function storedGrantMatches(row, grant, productId) {
  const expectedProduct = String(productId ?? row.product ?? 'trip-orders').trim() || 'trip-orders';
  const rowProduct = String(row.product || 'trip-orders').trim() || 'trip-orders';
  if (rowProduct !== expectedProduct) return false;
  const tier = String(row.licence_tier || row.kind || '').trim().toLowerCase();
  const expiry = String(row.licence_expiry || '').trim();
  if (grant.grant === 'trial') return tier === 'trial' || tier === '';
  if (grant.grant === 'permanent') return tier === 'permanent';
  if (grant.grant === 'paid') return tier === 'paid' && expiry === grant.paid_until;
  return false;
}

export function grantStrengthFromRow(row) {
  const tier = String(row?.licence_tier || row?.kind || '').trim().toLowerCase();
  if (tier === 'permanent') return { level: 3, paidUntil: '' };
  if (tier === 'paid' || tier === 'monthly') {
    return { level: 2, paidUntil: String(row?.licence_expiry || '').trim() };
  }
  return { level: 1, paidUntil: '' };
}

export function grantStrengthFromGrant(grant) {
  if (grant.grant === 'permanent') return { level: 3, paidUntil: '' };
  if (grant.grant === 'paid') return { level: 2, paidUntil: String(grant.paid_until || '').trim() };
  return { level: 1, paidUntil: '' };
}

/** True when a new grant would replace a stored code with a weaker or shorter paid term. */
export function wouldDowngradeGrant(existingRow, grant) {
  if (!existingRow) return false;
  const cur = grantStrengthFromRow(existingRow);
  if (!cur.level) return false;
  const next = grantStrengthFromGrant(grant);
  if (next.level < cur.level) return true;
  if (cur.level === 2 && next.level === 2 && cur.paidUntil && next.paidUntil && next.paidUntil < cur.paidUntil) {
    return true;
  }
  return false;
}

export function termFromRow(row) {
  if (!row) return null;
  const tier = String(row.licence_tier || row.kind || '').trim().toLowerCase();
  if (!tier) return null;
  const paidLike = tier === 'paid' || tier === 'monthly';
  const until = paidLike ? String(row.licence_expiry ?? row.last_day ?? '').trim() : '';
  return { tier: tier === 'monthly' ? 'paid' : tier, until };
}

export function pickStrongerTerm(a, b) {
  if (!a) return b;
  if (!b) return a;
  const cur = grantStrengthFromRow({ licence_tier: a.tier, licence_expiry: a.until });
  const other = grantStrengthFromRow({ licence_tier: b.tier, licence_expiry: b.until });
  if (other.level > cur.level) return b;
  if (cur.level > other.level) return a;
  if (cur.level === 2 && other.level === 2 && other.paidUntil > cur.paidUntil) return b;
  return a;
}

/** Strongest known grant for product+device from customers and issued/delivered rows (code may be cleared after ack). */
export async function currentTerm(env, productId, device) {
  const dkey = deviceKey(device);
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  const offlineId = offlineRequestId(product, dkey);
  let best = null;

  const cust = await env.DB.prepare(
    'SELECT licence_tier, licence_expiry, kind, last_day FROM customers WHERE device = ? AND product = ?',
  ).bind(device, product).first();
  best = pickStrongerTerm(best, termFromRow(cust));

  const rows = await env.DB.prepare(
    `SELECT licence_tier, licence_expiry, kind FROM licence_requests
     WHERE device_key = ? AND status IN ('issued', 'delivered') AND (product = ? OR id = ?)`,
  ).bind(dkey, product, offlineId).all();
  for (const row of rows.results || []) {
    best = pickStrongerTerm(best, termFromRow(row));
  }
  return best;
}

export function wouldDowngradeTerm(term, grant) {
  if (!term?.tier) return false;
  const cur = grantStrengthFromRow({ licence_tier: term.tier, licence_expiry: term.until });
  const next = grantStrengthFromGrant(grant);
  if (next.level < cur.level) return true;
  if (cur.level === 2 && next.level === 2 && cur.paidUntil && next.paidUntil && next.paidUntil < cur.paidUntil) {
    return true;
  }
  return false;
}

export function downgradeError(term) {
  const e = new Error('downgrade');
  e.current = { tier: term.tier, until: term.until || '' };
  return e;
}

/** Legacy `force` means reissue only; downgrade needs explicit confirm_downgrade. */
export function resolveIssueFlags(options = {}) {
  const reissue = options.reissue === true || options.force === true;
  const confirmDowngrade = options.confirm_downgrade === true;
  return { reissue, confirmDowngrade };
}

export function assertDowngradeAllowed(knownTerm, grant, confirmDowngrade) {
  if (confirmDowngrade) return;
  if (knownTerm && wouldDowngradeTerm(knownTerm, grant)) throw downgradeError(knownTerm);
}

/** Paid until calendar day inclusive; permanent always active. */
export function isActiveStrongTerm(term, env) {
  if (!term?.tier) return false;
  if (term.tier === 'permanent') return true;
  if (term.tier === 'paid') {
    const until = String(term.until || '').trim();
    if (!until || !isValidCalendarIso(until)) return false;
    const tz = env.LICENCE_CALENDAR_TZ || 'Africa/Cairo';
    const today = calendarDateInTz(new Date(), tz).iso;
    return today <= until;
  }
  return false;
}

export function downgradeForbiddenError(term) {
  const e = new Error('downgrade_forbidden');
  e.current = { tier: term.tier, until: term.until || '' };
  return e;
}

export function assertTrialNotOverStrongTerm(env, term, grant) {
  if (grant.grant !== 'trial') return;
  if (isActiveStrongTerm(term, env)) throw downgradeForbiddenError(term);
}

/** Row may supply original trial dates only when it is effectively trial and no paid/permanent term is active. */
export function rowIsTrialSource(row, strongTermActive) {
  if (!row || strongTermActive) return false;
  const licTier = String(row.licence_tier ?? '').trim().toLowerCase();
  const kind = String(row.kind ?? '').trim().toLowerCase();
  if (licTier === 'paid' || licTier === 'permanent') return false;
  if (licTier === 'trial') return true;
  if (licTier === '' && kind === 'trial') return true;
  return false;
}

function trialInclusiveDays(env) {
  return hubTrialDaysInclusive(env.TRIAL_DAYS || 14);
}

/** Original trial window for force re-issue (same first/last days, no extension). */
export async function originalTrialWindow(env, productId, device) {
  const product = String(productId || 'trip-orders').trim() || 'trip-orders';
  const knownTerm = await currentTerm(env, productId, device);
  const strongActive = isActiveStrongTerm(knownTerm, env);

  const cust = await env.DB.prepare(
    'SELECT first_day, last_day, licence_expiry, kind, licence_tier FROM customers WHERE device = ? AND product = ?',
  ).bind(device, product).first();
  if (rowIsTrialSource(cust, strongActive)) {
    const first = String(cust.first_day || '').trim();
    const last = String(cust.last_day || cust.licence_expiry || '').trim();
    if (first && last) return { first, last };
  }
  const dkey = deviceKey(device);
  const rows = await env.DB.prepare(
    `SELECT licence_expiry, licence_tier, kind FROM licence_requests
     WHERE device_key = ? AND product = ?
       AND status IN ('issued', 'delivered')
     ORDER BY updated_at DESC`,
  ).bind(dkey, product).all();
  for (const row of rows.results || []) {
    if (!rowIsTrialSource(row, strongActive)) continue;
    const last = String(row.licence_expiry || '').trim();
    if (!last) continue;
    const inclusive = trialInclusiveDays(env);
    const first = shiftCalendarDays(last, -(inclusive - 1));
    return { first, last };
  }
  return null;
}

export function trialWindowEnded(lastIso, env) {
  const tz = env.LICENCE_CALENDAR_TZ || 'Africa/Cairo';
  const today = calendarDateInTz(new Date(), tz).iso;
  return today > String(lastIso || '').trim();
}

async function trialSignOptions(env, grant, reissue, productId, device) {
  if (!reissue || grant.grant !== 'trial') return {};
  const win = await originalTrialWindow(env, productId, device);
  if (!win || trialWindowEnded(win.last, env)) throw new Error('trial_expired');
  return { trialFirstDay: win.first, trialLastDay: win.last };
}

async function latestIssuedForDeviceProduct(env, productId, dkey) {
  return env.DB.prepare(
    "SELECT * FROM licence_requests WHERE product = ? AND device_key = ? AND status IN ('issued', 'delivered') ORDER BY updated_at DESC LIMIT 1",
  ).bind(String(productId || 'trip-orders').trim() || 'trip-orders', dkey).first();
}

function customerUpsertStmts(env, shop, signed, meta, t, requestId) {
  const device = signed.device;
  const product = String(signed.product || 'trip-orders').trim() || 'trip-orders';
  const shopTrim = shop.slice(0, 60) || '—';
  const expiry = meta.expiry || null;
  return [
    env.DB.prepare(
      `UPDATE customers SET shop = ?, kind = ?, serial = ?, first_day = ?, last_day = ?, licence_tier = ?, licence_expiry = ?
       WHERE device = ? AND product = ? AND EXISTS (SELECT 1 FROM licence_requests WHERE id = ? AND code = ?)`,
    ).bind(shopTrim, meta.kind, signed.serial, signed.first_day, signed.last_day, meta.tier, expiry, device, product, requestId, signed.code),
    env.DB.prepare(
      `INSERT INTO customers(id, product, shop, device, kind, serial, first_day, last_day, licence_tier, licence_expiry, created_at)
       SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
       WHERE NOT EXISTS (SELECT 1 FROM customers WHERE device = ? AND product = ?)
         AND EXISTS (SELECT 1 FROM licence_requests WHERE id = ? AND code = ?)`,
    ).bind(crypto.randomUUID(), product, shopTrim, device, meta.kind, signed.serial, signed.first_day, signed.last_day, meta.tier, expiry, t, device, product, requestId, signed.code),
  ];
}

function tierMeta(grant, signed) {
  if (grant.grant === 'trial') return { kind: 'trial', tier: 'trial', expiry: signed.last_day || '' };
  if (grant.grant === 'permanent') return { kind: 'permanent', tier: 'permanent', expiry: '' };
  return { kind: 'monthly', tier: 'paid', expiry: grant.paid_until || signed.last_day || '' };
}

async function locksOwnedByRequest(env, productId, dkey, machineHash, requestId) {
  for (const lock of onlineLockKeys(productId, dkey, machineHash)) {
    const row = await trialLockRow(env, lock);
    if (!row || row.request_id !== requestId) return false;
  }
  return true;
}

export function licencePathname(pathname) {
  let p = pathname;
  for (const prefix of ['/api', '/licence-hub']) {
    if (p === prefix) p = '/';
    else if (p.startsWith(prefix + '/')) p = p.slice(prefix.length);
  }
  return p;
}

export async function handleLicence(request, env, url) {
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  const path = licencePathname(url.pathname);
  if ((path === '/licence/time' || path === '/licence/clock') && request.method === 'GET') {
    if (timeLimited(ip)) {
      return json({ error: 'rate' }, 429, { 'Retry-After': String(WINDOW - now() % WINDOW) });
    }
    const nonceParse = parseHubTimeNonce(url);
    if (!nonceParse.ok) return json({ error: 'bad_nonce' }, 400);
    return json(await hubCalendarSigned(env, { nonce: nonceParse.nonce }));
  }

  if (await limited(env, 'lic:ip:' + ip, 120)) return json({ error: 'rate' }, 429);
  if (!env.SESSION_SECRET) return json({ error: 'config' }, 503);
  const allowedProducts = products(env);
  if (!allowedProducts) return json({ error: 'config' }, 503);

  await migrateLegacyTrialLocks(env);
  await expireStalePending(env);

  if (path === '/licence/request' && request.method === 'POST') {
    let body;
    try { body = await request.json(); } catch { return json({ error: 'json' }, 400); }
    for (const f of REQUIRED) {
      if (typeof body[f] !== 'string') return json({ field: f }, 400);
    }
    if (body.ref !== undefined && body.ref !== null && typeof body.ref !== 'string') {
      return json({ field: 'ref' }, 400);
    }
    const product = typeof body.product === 'string' && body.product.trim()
      ? body.product.trim()
      : defaultProduct(env);
    if (!product) return json({ error: 'config' }, 503);
    body.product = product;
    if (body.device.length > MAX_DEVICE || body.machine.length > MAX_MACHINE || body.nonce.length > MAX_NONCE) {
      return json({ field: 'device' }, 400);
    }
    if (!allowedProducts.has(body.product)) return json({ field: 'product' }, 400);
    if (!['trial', 'monthly', 'permanent'].includes(body.kind)) return json({ field: 'kind' }, 400);
    let dkey;
    try { dkey = deviceKey(body.device); } catch { return json({ field: 'device' }, 400); }
    const machineHash = normalizeMachineHash(body.machine);
    if (!machineHash) return json({ field: 'machine' }, 400);

    const poll = await derivePollToken(env.SESSION_SECRET, body.nonce);
    const pollHash = await sha256Hex(poll);
    const shopStored = blankLongDigitRuns(body.shop).slice(0, 60);
    const refStored = await refFingerprint(body.ref);

    const existing = await env.DB.prepare('SELECT id, poll_token_hash, status, reason FROM licence_requests WHERE nonce = ?').bind(body.nonce).first();
    if (existing) {
      if (existing.poll_token_hash !== pollHash) return json({}, 401);
      return json({
        replay: true,
        id: existing.id,
        status: existing.status,
      });
    }

    const id = crypto.randomUUID();
    const t = now();
    const notifyBody = { ...body, shop: shopStored };

    if (body.kind !== 'trial') {
      if (await openRequestForDevice(env, body.product, dkey)) {
        return json({ field: 'device' }, 400);
      }
      if (await limited(env, 'lic:pending:' + ip, MAX_PENDING_PER_IP)) return json({ error: 'rate' }, 429);
      await env.DB.prepare(
        'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      ).bind(id, pollHash, body.product, body.kind, body.device, dkey, body.machine, body.nonce, shopStored, refStored, body.version.slice(0, 40), 'pending', t, t).run();
      await notifyOwner(env, notifyBody);
      return json({ id, poll_token: poll, status: 'pending' });
    }

    if (await trialUsedOnline(env, body.product, dkey, machineHash)) {
      await env.DB.prepare(
        'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, reason, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      ).bind(id, pollHash, body.product, body.kind, body.device, dkey, body.machine, body.nonce, shopStored, refStored, body.version.slice(0, 40), 'refused', 'already_used', t, t).run();
      return json({ id, poll_token: poll, status: 'refused', reason: 'already_used' });
    }

    if (await openRequestForDevice(env, body.product, dkey)) {
      return json({ field: 'device' }, 400);
    }

    if (await limited(env, 'lic:pending:' + ip, MAX_PENDING_PER_IP)) return json({ error: 'rate' }, 429);

    await env.DB.prepare(
      'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind(id, pollHash, body.product, body.kind, body.device, dkey, body.machine, body.nonce, shopStored, refStored, body.version.slice(0, 40), 'pending', t, t).run();

    await notifyOwner(env, notifyBody);
    return json({ id, poll_token: poll, status: 'pending' });
  }

  if (path === '/licence/status' && request.method === 'GET') {
    const id = url.searchParams.get('id') || '';
    const auth = request.headers.get('Authorization') || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (!id || !token) return json({}, 401);
    const pollHash = await sha256Hex(token);
    const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ? AND poll_token_hash = ?').bind(id, pollHash).first();
    if (!row) return json({}, 401);
    const cal = await hubCalendarSigned(env);
    if (row.status === 'pending') return json({ status: 'pending', stage: row.stage || '', ...cal });
    if (row.status === 'approved') return json({ status: 'pending', stage: 'approved', ...cal });
    if (row.status === 'issued' && row.code) {
      let dkey;
      try {
        dkey = deviceKey(row.device_key || row.device);
      } catch {
        return json({ status: 'pending', ...cal });
      }
      const machineHash = normalizeMachineHash(row.machine);
      const productId = String(row.product || 'trip-orders').trim() || 'trip-orders';
      const tier = String(row.licence_tier || row.kind || 'trial').trim().toLowerCase();
      const trialIssue = tier === 'trial' || row.kind === 'trial';
      if (trialIssue && !(await locksOwnedByRequest(env, productId, dkey, machineHash, row.id))) {
        return json({ status: 'pending', ...cal });
      }
      return json({ status: 'issued', code: row.code, ...cal });
    }
    if (row.status === 'refused') return json({ status: 'refused', reason: row.reason || 'refused', ...cal });
    if (row.status === 'expired') return json({ status: 'expired', ...cal });
    if (row.status === 'delivered') return json({ status: 'delivered', ...cal });
    return json({ status: row.status, ...cal });
  }

  if (path === '/licence/ack' && request.method === 'POST') {
    let body;
    try { body = await request.json(); } catch { return json({ error: 'json' }, 400); }
    const id = body.id || '';
    const auth = request.headers.get('Authorization') || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (!id || !token) return json({}, 401);
    const pollHash = await sha256Hex(token);
    const updated = await env.DB.prepare(
      'UPDATE licence_requests SET status = ?, code = NULL, updated_at = ? WHERE id = ? AND poll_token_hash = ? AND status = ? AND code IS NOT NULL',
    ).bind('delivered', now(), id, pollHash, 'issued').run();
    if (!updated.meta.changes) return json({ error: 'conflict' }, 409);
    return json({ ok: true });
  }

  return null;
}

async function notifyOwner(env, body) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const chat = env.TELEGRAM_CHAT_ID;
  if (!token || !chat) return;
  const text = `طلب ترخيص جديد\n${body.product || 'trip-orders'} · ${body.kind} · ${body.shop || '—'}\nجهاز: ${body.device}`;
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text }),
    });
  } catch { /* optional */ }
}

function signedFromRow(row, signed = null) {
  if (signed) return signed;
  return {
    code: row.code,
    serial: '',
    first_day: '',
    last_day: '',
    edition: 'trial',
    product: row.product,
    device: row.device,
  };
}

async function upsertOnlineLocks(env, requestId, productId, dkey, machineHash, t) {
  for (const lock of onlineLockKeys(productId, dkey, machineHash)) {
    await env.DB.prepare(
      'INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO UPDATE SET request_id = excluded.request_id, at = excluded.at',
    ).bind(lock, requestId, t).run();
  }
}

async function waitForIssuedOffline(env, requestId, attempts = 30) {
  for (let i = 0; i < attempts; i++) {
    const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
    if (row?.code && row.status === 'issued') return row;
    if (i > 0) await new Promise((r) => setTimeout(r, 5));
  }
  return null;
}

async function ensureCustomerRecord(env, row, signed, t) {
  const product = String(row.product || signed.product || 'trip-orders').trim() || 'trip-orders';
  const existing = await env.DB.prepare('SELECT id FROM customers WHERE device = ? AND product = ?').bind(signed.device, product).first();
  if (existing) return;
  await env.DB.prepare(
    'INSERT INTO customers(id, product, shop, device, kind, serial, first_day, last_day, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(crypto.randomUUID(), product, row.shop || '—', signed.device, row.kind || 'trial', signed.serial, signed.first_day, signed.last_day, t).run();
}

async function claimAndIssue(env, requestId, dkey, machineHash, signed, t, reissue, meta = {}) {
  const productId = String(meta.productId || signed.product || 'trip-orders').trim() || 'trip-orders';
  const grantKind = meta.grantKind || 'trial';
  const isTrialGrant = grantKind === 'trial';
  const replace = meta.replace === true;
  const deviceLock = onlineDeviceLockKey(productId, dkey);
  const machineLock = machineHash ? onlineMachineLockKey(productId, machineHash) : null;

  const stmts = [];
  if (isTrialGrant && (replace || reissue)) {
    await upsertOnlineLocks(env, requestId, productId, dkey, machineHash, t);
  } else if (isTrialGrant || !replace) {
    for (const lock of onlineLockKeys(productId, dkey, machineHash)) {
      stmts.push(
        env.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING').bind(lock, requestId, t),
      );
    }
  }

  const shop = meta.shop || '—';
  const kind = meta.kind || 'trial';
  const tier = meta.tier || kind;
  const expiry = meta.expiry || signed.last_day || '';
  let issueSql;
  let issueBinds;
  if (replace) {
    issueSql =
      'UPDATE licence_requests SET status = ?, stage = ?, code = ?, updated_at = ?, kind = ?, licence_tier = ?, licence_expiry = ? WHERE id = ? AND status != ?';
    issueBinds = ['issued', 'approved', signed.code, t, kind, tier, expiry || null, requestId, 'refused'];
  } else if (isTrialGrant) {
    issueSql =
      'UPDATE licence_requests SET status = ?, stage = ?, code = ?, updated_at = ? WHERE id = ? AND code IS NULL AND status NOT IN (?, ?) AND EXISTS (SELECT 1 FROM machine_trials WHERE machine = ? AND request_id = ?)';
    issueBinds = ['issued', 'approved', signed.code, t, requestId, 'refused', 'delivered', deviceLock, requestId];
    if (machineLock) {
      issueSql += ' AND EXISTS (SELECT 1 FROM machine_trials WHERE machine = ? AND request_id = ?)';
      issueBinds.push(machineLock, requestId);
    }
  } else {
    issueSql =
      'UPDATE licence_requests SET status = ?, stage = ?, code = ?, updated_at = ? WHERE id = ? AND code IS NULL AND status NOT IN (?, ?)';
    issueBinds = ['issued', 'approved', signed.code, t, requestId, 'refused', 'delivered'];
  }
  stmts.push(env.DB.prepare(issueSql).bind(...issueBinds));
  stmts.push(...customerUpsertStmts(env, shop, signed, { kind, tier, expiry }, t, requestId));
  if (!replace) {
    stmts.push(env.DB.prepare(
      'UPDATE licence_requests SET kind = ?, licence_tier = ?, licence_expiry = ? WHERE id = ? AND code = ?',
    ).bind(kind, tier, expiry || null, requestId, signed.code));
  }
  const issueStmtIndex = replace ? stmts.length - 3 : stmts.length - 4;
  const results = await env.DB.batch(stmts);
  const issued = results[issueStmtIndex]?.meta?.changes > 0;
  if (!issued) {
    const existing = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
    if (existing?.code && existing.status === 'issued') {
      return { ok: true, signed: signedFromRow(existing) };
    }
    await env.DB.prepare(
      'UPDATE licence_requests SET code = NULL, status = ?, reason = ?, updated_at = ? WHERE id = ? AND code IS NULL',
    ).bind('refused', 'already_used', t, requestId).run();
    await env.DB.prepare(
      'DELETE FROM machine_trials WHERE request_id = ? AND NOT EXISTS (SELECT 1 FROM licence_requests WHERE id = ? AND code IS NOT NULL)',
    ).bind(requestId, requestId).run();
    return { ok: false };
  }
  return { ok: true, signed };
}

async function signGrant(env, keys, grant, row, signOpts = {}) {
  const tz = env.LICENCE_CALENDAR_TZ || 'Africa/Cairo';
  const when = new Date();
  if (grant.grant === 'trial') {
    if (!keys.trialKey) throw new Error('no_signing_key');
    if (signOpts.trialFirstDay && signOpts.trialLastDay) {
      return issueTrialWindowCode(
        keys.trialKey,
        row.product,
        row.device,
        signOpts.trialFirstDay,
        signOpts.trialLastDay,
        when,
        tz,
      );
    }
    const days = hubTrialDaysInclusive(env.TRIAL_DAYS || 14);
    return issueTrialCode(keys.trialKey, row.product, row.device, days, when, tz);
  }
  if (!keys.paidKey) return { refused: true, reason: REASON_PAID_KEY_MISSING };
  if (grant.grant === 'permanent') {
    return issuePermanentCode(keys.paidKey, row.product, row.device, when, tz);
  }
  return issuePaidUntilCode(keys.paidKey, row.product, row.device, grant.paid_until, when, tz);
}

export async function approveRequest(env, requestId, keys, options = {}) {
  await migrateLegacyTrialLocks(env);
  const { reissue, confirmDowngrade } = resolveIssueFlags(options);
  let grant;
  try {
    grant = parseOwnerGrant(options, env);
  } catch (e) {
    if (e?.message === 'date_out_of_range') throw e;
    throw new Error('bad_grant');
  }
  const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
  if (!row || row.status === 'refused') return null;
  if (row.status === 'delivered' && !reissue) return null;

  let dkey;
  try {
    dkey = deviceKey(row.device_key || row.device);
  } catch {
    await refuseRequest(env, requestId, 'bad_device');
    throw new Error('bad_device_code');
  }
  const machineHash = normalizeMachineHash(row.machine);
  const productId = String(row.product || 'trip-orders').trim() || 'trip-orders';
  const rowIssued = row.status === 'issued' && row.code ? row : null;
  const knownTerm = await currentTerm(env, productId, row.device);
  assertTrialNotOverStrongTerm(env, knownTerm, grant);

  let replaceMode = false;
  if (rowIssued) {
    const ownsLocks = await locksOwnedByRequest(env, productId, dkey, machineHash, requestId);
    if (!reissue && storedGrantMatches(row, grant, productId) && ownsLocks) {
      await ensureCustomerRecord(env, row, signedFromRow(row), now());
      return signedFromRow(row);
    }
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
    replaceMode = true;
  } else if (reissue && row.status === 'delivered') {
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
    replaceMode = true;
  } else {
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
  }

  if (grant.grant === 'trial' && !reissue && (await trialUsedOnline(env, productId, dkey, machineHash))) {
    const owns = await locksOwnedByRequest(env, productId, dkey, machineHash, requestId);
    if (!owns) {
      assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
      await refuseRequest(env, requestId, 'already_used');
      return null;
    }
  }

  const t = now();
  let signed;
  try {
    const signOpts = await trialSignOptions(env, grant, reissue, productId, row.device);
    signed = await signGrant(env, keys, grant, row, signOpts);
  } catch (e) {
    if (e?.message === 'bad_device_code') {
      await refuseRequest(env, requestId, 'bad_device');
    }
    throw e;
  }
  if (signed?.refused) {
    if (signed.reason === REASON_PAID_KEY_MISSING) return signed;
    await refuseRequest(env, requestId, signed.reason || REASON_PAID_IN_STUDIO);
    return signed;
  }

  const meta = tierMeta(grant, signed);
  const outcome = await claimAndIssue(env, requestId, dkey, machineHash, signed, t, reissue, {
    shop: row.shop, kind: meta.kind, tier: meta.tier, expiry: meta.expiry, grantKind: grant.grant, replace: replaceMode,
    productId,
  });
  if (!outcome.ok) return null;
  return outcome.signed || signed;
}

export async function refuseRequest(env, requestId, reason = 'refused') {
  await env.DB.prepare('UPDATE licence_requests SET status = ?, reason = ?, updated_at = ? WHERE id = ?')
    .bind('refused', reason, now(), requestId).run();
}

async function issueOfflineCustomerInner(env, keys, device, shop, productId, options = {}) {
  const { reissue, confirmDowngrade } = resolveIssueFlags(options);
  let grant;
  try {
    grant = parseOwnerGrant(options, env);
  } catch (e) {
    if (e?.message === 'date_out_of_range') throw e;
    throw new Error('bad_grant');
  }
  const dkey = deviceKey(device);
  const requestId = offlineRequestId(productId, dkey);
  const lock = offlineDeviceLockKey(productId, dkey);
  const knownTerm = await currentTerm(env, productId, device);
  assertTrialNotOverStrongTerm(env, knownTerm, grant);
  const existing = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
  let ownsLock = false;
  let replacingIssued = false;
  if (existing?.status === 'delivered' && !reissue) {
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
    throw new Error('reissue_confirm');
  }
  if (existing?.status === 'delivered' && reissue) {
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
    replacingIssued = true;
    const claim = await trialLockRow(env, lock);
    ownsLock = Boolean(claim && claim.request_id === requestId);
  }
  if (existing?.code && existing.status === 'issued') {
    const claim = await trialLockRow(env, lock);
    if (claim && claim.request_id === requestId) {
      if (!reissue && storedGrantMatches(existing, grant, productId)) {
        await ensureCustomerRecord(env, existing, signedFromRow(existing), now());
        return signedFromRow(existing);
      }
      assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
      ownsLock = true;
      replacingIssued = true;
    }
  } else {
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
  }
  if (grant.grant === 'trial' && !reissue && (await trialUsedForOfflineProduct(env, productId, dkey))) {
    const claim = await trialLockRow(env, lock);
    const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
    if (row?.code && row.status === 'issued') {
      await ensureCustomerRecord(env, row, signedFromRow(row), now());
      return signedFromRow(row);
    }
    if (claim?.request_id === requestId) ownsLock = true;
    else throw new Error('already_used');
  }
  const t = now();
  const grantRow = { product: productId, device };
  let signed;
  try {
    const signOpts = await trialSignOptions(env, grant, reissue, productId, device);
    signed = await signGrant(env, keys, grant, grantRow, signOpts);
  } catch (e) {
    if (e?.message === 'no_signing_key') throw e;
    throw e;
  }
  if (signed?.refused) throw new Error(signed.reason || 'paid_signing_key_missing');
  const meta = tierMeta(grant, signed);
  const shopTrim = blankLongDigitRuns(shop).slice(0, 60) || '—';

  const resolveOfflineRowGrant = async (row) => {
    if (!row?.code || row.status !== 'issued') return false;
    if (storedGrantMatches(row, grant, productId)) {
      await ensureCustomerRecord(env, row, signedFromRow(row), t);
      return signedFromRow(row);
    }
    assertDowngradeAllowed(knownTerm, grant, confirmDowngrade);
    if (replacingIssued || reissue) {
      ownsLock = true;
      return false;
    }
    throw new Error('grant_conflict');
  };

  const buildOfflineIssueBatch = (opts = {}) => {
    const { includeLockInsert = false, includeLockReassign = false } = opts;
    const replacing = replacingIssued;
    const stmts = [];
    stmts.push(
      env.DB.prepare(
        'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET product = excluded.product, shop = excluded.shop, updated_at = excluded.updated_at',
      ).bind(requestId, 'offline', productId, 'trial', device, dkey, '', 'offline-' + requestId, shopTrim, '', '', 'pending', t, t),
    );
    if (includeLockReassign) {
      stmts.push(
        env.DB.prepare(
          'INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO UPDATE SET request_id = excluded.request_id, at = excluded.at',
        ).bind(lock, requestId, t),
      );
    } else if (includeLockInsert) {
      stmts.push(
        env.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING')
          .bind(lock, requestId, t),
      );
    }
    const issueSql = replacing
      ? 'UPDATE licence_requests SET status = ?, code = ?, device = ?, updated_at = ?, kind = ?, licence_tier = ?, licence_expiry = ? WHERE id = ? AND EXISTS (SELECT 1 FROM machine_trials WHERE machine = ? AND request_id = ?)'
      : 'UPDATE licence_requests SET status = ?, code = ?, device = ?, updated_at = ? WHERE id = ? AND code IS NULL AND EXISTS (SELECT 1 FROM machine_trials WHERE machine = ? AND request_id = ?)';
    const issueBinds = replacing
      ? ['issued', signed.code, signed.device, t, meta.kind, meta.tier, meta.expiry || null, requestId, lock, requestId]
      : ['issued', signed.code, signed.device, t, requestId, lock, requestId];
    const issueIdx = stmts.length;
    stmts.push(env.DB.prepare(issueSql).bind(...issueBinds));
    if (!replacing) {
      stmts.push(
        env.DB.prepare(
          'UPDATE licence_requests SET kind = ?, licence_tier = ?, licence_expiry = ? WHERE id = ? AND code = ?',
        ).bind(meta.kind, meta.tier, meta.expiry || null, requestId, signed.code),
      );
    }
    stmts.push(...customerUpsertStmts(env, shopTrim, signed, meta, t, requestId));
    stmts.push(
      env.DB.prepare(
        'DELETE FROM machine_trials WHERE request_id = ? AND NOT EXISTS (SELECT 1 FROM licence_requests WHERE id = ? AND code IS NOT NULL)',
      ).bind(requestId, requestId),
    );
    const product = String(productId || 'trip-orders').trim() || 'trip-orders';
    if (grant.grant === 'trial' && product === 'trip-orders') {
      stmts.push(
        env.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING')
          .bind(deviceLockKey(dkey), requestId, t),
      );
    }
    return { stmts, issueIdx };
  };

  const runOfflineIssueBatch = async (opts) => {
    const { stmts, issueIdx } = buildOfflineIssueBatch(opts);
    const results = await env.DB.batch(stmts);
    return results[issueIdx]?.meta?.changes > 0;
  };

  const finishAfterBatchFailure = async (e) => {
    const row = await waitForIssuedOffline(env, requestId);
    if (row) {
      if (!storedGrantMatches(row, grant, productId)) throw new Error('grant_conflict');
      await ensureCustomerRecord(env, row, signedFromRow(row), t);
      return signedFromRow(row);
    }
    throw e;
  };

  const trialReissueReassign = reissue && grant.grant === 'trial';
  try {
    if (!ownsLock) {
      let issued = await runOfflineIssueBatch({
        includeLockInsert: true,
        includeLockReassign: trialReissueReassign,
      });
      if (!issued) {
        const claim = await trialLockRow(env, lock);
        if (claim?.request_id === requestId) {
          const row = await waitForIssuedOffline(env, requestId);
          const done = row ? await resolveOfflineRowGrant(row) : false;
          if (done) return done;
          ownsLock = true;
          issued = await runOfflineIssueBatch({ includeLockReassign: trialReissueReassign });
        } else {
          const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
          const done = row ? await resolveOfflineRowGrant(row) : false;
          if (done) return done;
          if (row?.code && row.status === 'issued') {
            ownsLock = true;
            issued = await runOfflineIssueBatch({ includeLockReassign: trialReissueReassign });
          } else {
            throw new Error('already_used');
          }
        }
      }
      if (!issued) {
        const row = await waitForIssuedOffline(env, requestId);
        const done = row ? await resolveOfflineRowGrant(row) : false;
        if (done) return done;
        throw new Error('already_used');
      }
    } else {
      const claim = await trialLockRow(env, lock);
      if (!claim || claim.request_id !== requestId) {
        const row = await waitForIssuedOffline(env, requestId);
        const done = row ? await resolveOfflineRowGrant(row) : false;
        if (done) return done;
        if (!replacingIssued) throw new Error('already_used');
      }
      const issued = await runOfflineIssueBatch({ includeLockReassign: trialReissueReassign });
      if (!issued) {
        const row = await waitForIssuedOffline(env, requestId);
        const done = row ? await resolveOfflineRowGrant(row) : false;
        if (done) return done;
        throw new Error('already_used');
      }
    }
  } catch (e) {
    return await finishAfterBatchFailure(e);
  }
  const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
  if (row?.code && row.status === 'issued') {
    await ensureCustomerRecord(env, row, signed, t);
    return signedFromRow(row);
  }
  const again = await waitForIssuedOffline(env, requestId);
  if (again) {
    await ensureCustomerRecord(env, again, signedFromRow(again), t);
    return signedFromRow(again);
  }
  throw new Error('already_used');
}

export function issueOfflineCustomer(env, keys, device, shop, productId, options = {}) {
  const dkey = deviceKey(device);
  const tailKey = `${String(productId || 'trip-orders').trim()}:${dkey}`;
  const tails = offlineTailMap(env);
  const prev = tails.get(tailKey) || Promise.resolve();
  const job = prev.catch(() => {}).then(() => issueOfflineCustomerInner(env, keys, device, shop, productId, options));
  tails.set(tailKey, job);
  return job.finally(() => {
    if (tails.get(tailKey) === job) tails.delete(tailKey);
  });
}

/** Drop activation codes from delivered rows older than TRIAL_DAYS (scheduled). */
export function ownerCapabilities(env) {
  const byProduct = {};
  const allowed = products(env);
  if (!allowed) {
    return {
      products: {},
      paid_available: false,
      trial_available: false,
      calendar_tz: hubCalendarTz(env),
      config_error: true,
    };
  }
  for (const productId of allowed) {
    byProduct[productId] = {
      paid_available: Boolean(signingKeyForProduct(env, 'PAID_SIGNING_KEY', productId)),
      trial_available: Boolean(signingKeyForProduct(env, 'LICENCE_SIGNING_KEY', productId)),
    };
  }
  const paidAny = Object.values(byProduct).some((p) => p.paid_available);
  const trialAny = Object.values(byProduct).some((p) => p.trial_available);
  return {
    products: byProduct,
    paid_available: paidAny,
    trial_available: trialAny,
    calendar_tz: hubCalendarTz(env),
  };
}

export async function purgeStaleCodes(env) {
  const days = Number(env.TRIAL_DAYS || 14);
  const cutoff = now() - days * 86400;
  await expireStalePending(env);
  await env.DB.prepare(
    "UPDATE licence_requests SET code = NULL WHERE code IS NOT NULL AND updated_at < ? AND status = 'delivered' AND (licence_tier = '' OR licence_tier = 'trial')",
  ).bind(cutoff).run();
}
