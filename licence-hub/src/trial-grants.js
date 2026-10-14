import { normalize } from './afcodes.js';
import { calendarDateInTz, isValidCalendarIso, shiftCalendarDays } from './calendar.js';

const LINK_CLOSURE_CAP = 256;
const ETW_PREFIX = 'etw|';

/** 64-hex SHA-256 machine tag from the office app, or null when malformed. */
export function normalizeMachineHash(machine) {
  const m = String(machine || '').toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(m)) return null;
  return m;
}

const SQL_MACHINE_HEX =
  "length(lower(lr.machine)) = 64 AND lower(lr.machine) NOT GLOB '*[^0-9a-f]*'";

function deviceKeyNorm(device) {
  const norm = normalize(String(device || ''));
  if (norm.length !== 10) throw new Error('bad_device_code');
  return norm;
}

function hubCalendarTz(env) {
  return String(env.LICENCE_CALENDAR_TZ || 'Africa/Cairo').trim() || 'Africa/Cairo';
}

function trialInclusiveDays(env) {
  const days = Number(env.TRIAL_DAYS || 14);
  if (!Number.isFinite(days) || days < 1 || days > 14) return 14;
  return Math.floor(days);
}

function normalizeProduct(productId) {
  return String(productId || 'trip-orders').trim() || 'trip-orders';
}

function parseEtwKey(machine) {
  if (!String(machine || '').startsWith(ETW_PREFIX)) return null;
  const parts = String(machine).split('|');
  if (parts.length < 4 || parts[0] !== 'etw') return null;
  const product = parts[1];
  const kind = parts[2];
  const subject = parts.slice(3).join('|');
  if (kind === 'd' || kind === 'm') return { product, kind, subject };
  return null;
}

function parseEtwWindow(requestId) {
  const raw = String(requestId || '');
  const sep = raw.indexOf('|');
  if (sep < 0) return null;
  const first = raw.slice(0, sep).trim();
  const last = raw.slice(sep + 1).trim();
  if (!isValidCalendarIso(first) || !isValidCalendarIso(last)) return null;
  if (first > last) return null;
  return { first, last };
}

function pickEarlierWindow(a, b) {
  if (!a) return b;
  if (!b) return a;
  if (a.first !== b.first) return a.first < b.first ? a : b;
  return a.last <= b.last ? a : b;
}

function rowIsTrialLike(row) {
  const licTier = String(row?.licence_tier ?? '').trim().toLowerCase();
  const kind = String(row?.kind ?? '').trim().toLowerCase();
  if (licTier === 'paid' || licTier === 'permanent') return false;
  if (licTier === 'trial') return true;
  if (licTier === '' && kind === 'trial') return true;
  return false;
}

/** True when this row is evidence of a past trial (including paid replace of a trial request). */
function rowWasTrialSource(row) {
  const kind = String(row?.kind ?? '').trim().toLowerCase();
  if (kind === 'trial') return true;
  return rowIsTrialLike(row);
}

function windowFromRequestRow(row, env) {
  if (!row || !rowIsTrialLike(row)) return null;
  const last = String(row.licence_expiry || '').trim();
  if (!last || !isValidCalendarIso(last)) return null;
  const inclusive = trialInclusiveDays(env);
  const first = shiftCalendarDays(last, -(inclusive - 1));
  return { first, last, source: row.id || null };
}

function windowFromRequestRowForBackfill(row, env) {
  if (!row || !rowWasTrialSource(row)) return null;
  const tz = hubCalendarTz(env);
  const inclusive = trialInclusiveDays(env);
  const candidates = [];
  const kindTrial = String(row?.kind ?? '').trim().toLowerCase() === 'trial';
  const trialLikeNow = rowIsTrialLike(row);
  const last = String(row.licence_expiry || '').trim();
  if (trialLikeNow && last && isValidCalendarIso(last)) {
    candidates.push({
      first: shiftCalendarDays(last, -(inclusive - 1)),
      last,
      source: row.id || null,
    });
  } else if (kindTrial && last && isValidCalendarIso(last)) {
    candidates.push({
      first: shiftCalendarDays(last, -(inclusive - 1)),
      last,
      source: row.id || null,
    });
  }
  const created = Number(row.created_at);
  if (kindTrial && !trialLikeNow && Number.isFinite(created) && created > 0) {
    const firstDay = calendarDateInTz(new Date(created * 1000), tz).iso;
    const lastDay = shiftCalendarDays(firstDay, inclusive - 1);
    candidates.push({ first: firstDay, last: lastDay, source: row.id || null });
  }
  if (!candidates.length && trialLikeNow && Number.isFinite(created) && created > 0) {
    const firstDay = calendarDateInTz(new Date(created * 1000), tz).iso;
    const lastDay = shiftCalendarDays(firstDay, inclusive - 1);
    candidates.push({ first: firstDay, last: lastDay, source: row.id || null });
  }
  let best = null;
  for (const c of candidates) best = pickEarlierWindow(best, c);
  return best;
}

function windowFromCustomerRow(row) {
  if (!row) return null;
  const kind = String(row?.kind ?? '').trim().toLowerCase();
  const licTier = String(row?.licence_tier ?? '').trim().toLowerCase();
  const trialCustomer = kind === 'trial' || licTier === 'trial' || (licTier === '' && kind === 'trial');
  if (!trialCustomer && !rowIsTrialLike(row)) return null;
  const first = String(row.first_day || '').trim();
  const last = String(row.last_day || row.licence_expiry || '').trim();
  if (!first || !last || !isValidCalendarIso(first) || !isValidCalendarIso(last)) return null;
  if (first > last) return null;
  return { first, last, source: row.id || null };
}

function lockSubject(machine) {
  const m = String(machine || '');
  if (m.startsWith('d:')) return { kind: 'd', subject: m.slice(2) };
  if (m.startsWith('h:')) return { kind: 'm', subject: m.slice(2).toLowerCase() };
  if (m.startsWith('od:') || m.startsWith('pd:')) {
    const parts = m.split(':');
    if (parts.length >= 3) return { kind: 'd', subject: parts.slice(2).join(':') };
  }
  if (m.startsWith('ph:')) {
    const parts = m.split(':');
    if (parts.length >= 3) return { kind: 'm', subject: parts.slice(2).join(':').toLowerCase() };
  }
  if (m.startsWith('offline:')) {
    const parts = m.split(':');
    if (parts.length === 2) return { kind: 'd', subject: parts[1] };
    if (parts.length >= 3) return { kind: 'd', subject: parts[parts.length - 1] };
  }
  if (!m.includes(':') && m.length === 10) return { kind: 'd', subject: m };
  return null;
}

function termFromRow(row) {
  if (!row) return null;
  const tier = String(row.licence_tier || row.kind || '').trim().toLowerCase();
  if (!tier) return null;
  const paidLike = tier === 'paid' || tier === 'monthly';
  const until = paidLike ? String(row.licence_expiry ?? row.last_day ?? '').trim() : '';
  return { tier: tier === 'monthly' ? 'paid' : tier, until };
}

function grantStrength(tier, until) {
  if (tier === 'permanent') return { level: 3, paidUntil: '' };
  if (tier === 'paid') return { level: 2, paidUntil: String(until || '').trim() };
  return { level: 1, paidUntil: '' };
}

function pickStrongerTerm(a, b) {
  if (!a) return b;
  if (!b) return a;
  const cur = grantStrength(a.tier, a.until);
  const other = grantStrength(b.tier, b.until);
  if (other.level > cur.level) return b;
  if (cur.level > other.level) return a;
  if (cur.level === 2 && other.level === 2 && other.paidUntil > cur.paidUntil) return b;
  return a;
}

export function isActiveStrongTerm(term, env, todayIso) {
  if (!term?.tier) return false;
  if (term.tier === 'permanent') return true;
  if (term.tier === 'paid') {
    const until = String(term.until || '').trim();
    if (!until || !isValidCalendarIso(until)) return false;
    const today = todayIso || calendarDateInTz(new Date(), hubCalendarTz(env)).iso;
    return today <= until;
  }
  return false;
}

function recordSubject(map, product, kind, subject, window, source) {
  const key = `${product}\0${kind}\0${subject}`;
  const prev = map.get(key);
  const next = pickEarlierWindow(prev, { first: window.first, last: window.last, source });
  map.set(key, next);
}

function trialWindowFromLockRow(row, env) {
  const lockMachine = row.machine;
  const requestId = row.request_id;
  const etw = parseEtwKey(lockMachine);
  if (etw) {
    const win = parseEtwWindow(requestId);
    if (!win) return null;
    return {
      first: win.first,
      last: win.last,
      product: etw.product,
      kind: etw.kind,
      subject: etw.kind === 'm' ? etw.subject.toLowerCase() : etw.subject,
      source: requestId,
    };
  }
  if (!row.id) return null;
  const status = String(row.status || '').trim().toLowerCase();
  if (!['issued', 'delivered', 'expired'].includes(status)) return null;
  const win = windowFromRequestRowForBackfill(row, env);
  if (!win) return null;
  const subj = lockSubject(lockMachine);
  if (!subj) return null;
  const product = normalizeProduct(row.product);
  return {
    first: win.first,
    last: win.last,
    product,
    kind: subj.kind,
    subject: subj.kind === 'm' ? subj.subject.toLowerCase() : subj.subject,
    source: win.source,
  };
}

export async function backfillTrialGrants(env, productFilter) {
  const products = productFilter ? [normalizeProduct(productFilter)] : null;
  const subjectWindows = new Map();
  const createdAt = new Date().toISOString();

  const lockSql = `
    SELECT mt.machine, mt.request_id,
           lr.id, lr.product, lr.kind, lr.licence_tier, lr.licence_expiry, lr.created_at
    FROM machine_trials mt
    LEFT JOIN licence_requests lr ON lr.id = mt.request_id`;
  const lockRows = await env.DB.prepare(lockSql).bind().all();

  for (const row of lockRows.results || []) {
    const parsed = trialWindowFromLockRow(row, env);
    if (!parsed) continue;
    if (products && !products.includes(parsed.product)) continue;
    recordSubject(subjectWindows, parsed.product, parsed.kind, parsed.subject, parsed, parsed.source);
  }

  const reqSql = products
    ? `SELECT * FROM licence_requests WHERE product = ? AND status IN ('issued', 'delivered', 'expired')`
    : `SELECT * FROM licence_requests WHERE status IN ('issued', 'delivered', 'expired')`;
  const reqRows = products
    ? await env.DB.prepare(reqSql).bind(products[0]).all()
    : await env.DB.prepare(reqSql).bind().all();
  for (const row of reqRows.results || []) {
    const win = windowFromRequestRowForBackfill(row, env);
    if (!win) continue;
    const product = normalizeProduct(row.product);
    if (products && !products.includes(product)) continue;
    let dkey;
    try {
      dkey = String(row.device_key || '').trim() || deviceKeyNorm(row.device);
    } catch {
      continue;
    }
    recordSubject(subjectWindows, product, 'd', dkey, win, win.source);
    const mh = normalizeMachineHash(row.machine);
    if (mh) recordSubject(subjectWindows, product, 'm', mh, win, win.source);
  }

  const custSql = products
    ? 'SELECT * FROM customers WHERE product = ?'
    : 'SELECT * FROM customers';
  const custRows = products
    ? await env.DB.prepare(custSql).bind(products[0]).all()
    : await env.DB.prepare(custSql).bind().all();
  for (const row of custRows.results || []) {
    const win = windowFromCustomerRow(row);
    if (!win) continue;
    const product = normalizeProduct(row.product);
    if (products && !products.includes(product)) continue;
    let dkey;
    try {
      dkey = deviceKeyNorm(row.device);
    } catch {
      continue;
    }
    recordSubject(subjectWindows, product, 'd', dkey, win, win.source);
  }

  const stmts = [];
  for (const [key, win] of subjectWindows) {
    const [product, kind, subject] = key.split('\0');
    stmts.push(
      env.DB.prepare(
        `INSERT OR IGNORE INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
         VALUES(?, ?, ?, ?, ?, ?, ?)`,
      ).bind(product, kind, subject, win.first, win.last, createdAt, win.source || null),
    );
  }
  if (stmts.length) await env.DB.batch(stmts);
  return stmts.length;
}

async function computeLinkedClosure(env, product, device, machines = []) {
  const dkey = deviceKeyNorm(device);
  const seedMachines = [];
  for (const m of machines) {
    const mh = normalizeMachineHash(m);
    if (mh) seedMachines.push(mh);
  }

  const seedParts = [`SELECT 'd' AS kind, ? AS id`];
  const binds = [dkey];
  for (const mh of seedMachines) {
    seedParts.push(`SELECT 'm', ?`);
    binds.push(mh);
  }
  const seedsSql = seedParts.join(' UNION ALL ');

  const sql = `
WITH RECURSIVE
seeds(kind, id) AS (
  ${seedsSql}
),
closure(kind, id) AS (
  SELECT kind, id FROM seeds
  UNION
  SELECT tg2.subject_kind, tg2.subject
  FROM closure c
  INNER JOIN trial_grants tg1 ON tg1.product = ?
    AND tg1.subject_kind = c.kind AND tg1.subject = c.id
  INNER JOIN trial_grants tg2 ON tg2.product = tg1.product
    AND tg2.source_request IS NOT NULL AND tg2.source_request = tg1.source_request
  UNION
  SELECT 'm', lower(lr.machine)
  FROM closure c
  INNER JOIN licence_requests lr ON lr.product = ?
    AND c.kind = 'd' AND lr.device_key = c.id AND ${SQL_MACHINE_HEX}
  UNION
  SELECT 'd', lr.device_key
  FROM closure c
  INNER JOIN licence_requests lr ON lr.product = ?
    AND c.kind = 'm' AND lower(lr.machine) = c.id AND length(lr.device_key) > 0
)
SELECT kind, id FROM closure`;

  binds.push(product, product, product);
  const rows = await env.DB.prepare(sql).bind(...binds).all();
  const deviceSet = new Set();
  const machineSet = new Set();
  for (const row of rows.results || []) {
    if (row.kind === 'd') deviceSet.add(String(row.id));
    else if (row.kind === 'm') machineSet.add(String(row.id));
  }
  const nodeCount = deviceSet.size + machineSet.size;
  if (nodeCount > LINK_CLOSURE_CAP) {
    return { blocked: true, reason: 'link_limit' };
  }
  return { blocked: false, devices: [...deviceSet], machines: [...machineSet] };
}

/** Every linked device key and machine hash (lowercased) for trial identity. */
export async function linkedSubjects(env, productId, device, machines = []) {
  const product = normalizeProduct(productId);
  const closure = await computeLinkedClosure(env, product, device, machines);
  if (closure.blocked) {
    return { devices: [], machines: [], deviceCodes: [], link_limit: true };
  }
  const deviceCodes = await deviceCodesForClosure(env, product, device, closure.devices);
  return {
    devices: closure.devices,
    machines: closure.machines,
    deviceCodes,
    link_limit: false,
  };
}

async function strongestTermOnClosure(env, product, devices, deviceCodes) {
  let best = null;
  if (deviceCodes.length) {
    const ph = deviceCodes.map(() => '?').join(', ');
    const custRows = await env.DB.prepare(
      `SELECT licence_tier, licence_expiry, kind, last_day FROM customers
       WHERE product = ? AND device IN (${ph})`,
    ).bind(product, ...deviceCodes).all();
    for (const row of custRows.results || []) {
      best = pickStrongerTerm(best, termFromRow(row));
    }
  }
  if (devices.length) {
    const ph = devices.map(() => '?').join(', ');
    const reqRows = await env.DB.prepare(
      `SELECT licence_tier, licence_expiry, kind FROM licence_requests
       WHERE product = ? AND device_key IN (${ph}) AND status IN ('issued', 'delivered')`,
    ).bind(product, ...devices).all();
    for (const row of reqRows.results || []) {
      best = pickStrongerTerm(best, termFromRow(row));
    }
  }
  return best;
}

async function earliestLedgerWindow(env, product, devices, machines) {
  const clauses = [];
  const binds = [product];
  if (devices.length) {
    const ph = devices.map(() => '?').join(', ');
    clauses.push(`(subject_kind = 'd' AND subject IN (${ph}))`);
    binds.push(...devices);
  }
  if (machines.length) {
    const ph = machines.map(() => '?').join(', ');
    clauses.push(`(subject_kind = 'm' AND subject IN (${ph}))`);
    binds.push(...machines);
  }
  if (!clauses.length) return null;
  const row = await env.DB.prepare(
    `SELECT first_day, last_day FROM trial_grants
     WHERE product = ? AND (${clauses.join(' OR ')})
     ORDER BY first_day ASC, last_day ASC LIMIT 1`,
  ).bind(...binds).first();
  if (!row) return null;
  const win = { first: String(row.first_day), last: String(row.last_day) };
  if (!isValidCalendarIso(win.first) || !isValidCalendarIso(win.last)) return null;
  return win;
}

async function deviceCodesForClosure(env, product, device, devices) {
  const deviceCodes = new Set([String(device || '').trim()]);
  if (devices.length) {
    const ph = devices.map(() => '?').join(', ');
    const devRows = await env.DB.prepare(
      `SELECT DISTINCT device FROM licence_requests WHERE product = ? AND device_key IN (${ph})`,
    ).bind(product, ...devices).all();
    for (const row of devRows.results || []) {
      if (row.device) deviceCodes.add(String(row.device));
    }
  }
  const codes = [...deviceCodes];
  if (codes.length) {
    const ph = codes.map(() => '?').join(', ');
    const custRows = await env.DB.prepare(
      `SELECT device FROM customers WHERE product = ? AND device IN (${ph})`,
    ).bind(product, ...codes).all();
    for (const row of custRows.results || []) {
      if (row.device) deviceCodes.add(String(row.device));
    }
  }
  return [...deviceCodes];
}

export async function resolveTrial(env, productId, device, machines = [], options = {}) {
  const product = normalizeProduct(productId);
  const today = options.today || calendarDateInTz(new Date(), hubCalendarTz(env)).iso;
  const closure = await computeLinkedClosure(env, product, device, machines);
  if (closure.blocked) {
    return { kind: 'blocked', reason: 'link_limit' };
  }
  const deviceCodes = await deviceCodesForClosure(env, product, device, closure.devices);
  const strongTerm = await strongestTermOnClosure(env, product, closure.devices, deviceCodes);
  const blockedBy = isActiveStrongTerm(strongTerm, env, today) ? 'downgrade_forbidden' : null;

  const ledger = await earliestLedgerWindow(env, product, closure.devices, closure.machines);
  if (ledger) {
    return {
      kind: 'existing',
      first_day: ledger.first,
      last_day: ledger.last,
      active: today <= ledger.last,
      blocked_by: blockedBy,
    };
  }

  if (blockedBy) {
    return { kind: 'blocked', reason: 'downgrade_forbidden' };
  }

  return { kind: 'eligible' };
}

export function trialGrantStatements(env, productId, device, machines, window, sourceRequest) {
  const product = normalizeProduct(productId);
  const dkey = deviceKeyNorm(device);
  const first = String(window?.first_day || window?.first || '').trim();
  const last = String(window?.last_day || window?.last || '').trim();
  if (!isValidCalendarIso(first) || !isValidCalendarIso(last)) {
    throw new Error('bad_trial_window');
  }
  const createdAt = new Date().toISOString();
  const src = sourceRequest || null;
  const stmts = [
    env.DB.prepare(
      `INSERT OR IGNORE INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
       VALUES(?, 'd', ?, ?, ?, ?, ?)`,
    ).bind(product, dkey, first, last, createdAt, src),
  ];
  const seen = new Set();
  for (const raw of machines || []) {
    const mh = normalizeMachineHash(raw);
    if (!mh || seen.has(mh)) continue;
    seen.add(mh);
    stmts.push(
      env.DB.prepare(
        `INSERT OR IGNORE INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
         VALUES(?, 'm', ?, ?, ?, ?, ?)`,
      ).bind(product, mh, first, last, createdAt, src),
    );
  }
  return stmts;
}
