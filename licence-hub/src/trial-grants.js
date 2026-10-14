import { normalize } from './afcodes.js';
import { calendarDateInTz, isValidCalendarIso, shiftCalendarDays } from './calendar.js';

const LINK_QUERY_LIMIT = 64;
const ETW_PREFIX = 'etw|';

/** 64-hex SHA-256 machine tag from the office app, or null when malformed. */
export function normalizeMachineHash(machine) {
  const m = String(machine || '').trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(m)) return null;
  return m;
}

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

function windowFromRequestRow(row, env) {
  if (!row || !rowIsTrialLike(row)) return null;
  const last = String(row.licence_expiry || '').trim();
  if (!last || !isValidCalendarIso(last)) return null;
  const inclusive = trialInclusiveDays(env);
  const first = shiftCalendarDays(last, -(inclusive - 1));
  return { first, last, source: row.id || null };
}

function windowFromCustomerRow(row) {
  if (!row || !rowIsTrialLike(row)) return null;
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

async function trialWindowForLock(env, lockMachine, requestId) {
  const etw = parseEtwKey(lockMachine);
  if (etw) {
    const win = parseEtwWindow(requestId);
    if (win) return { ...win, product: etw.product, kind: etw.kind, subject: etw.kind === 'm' ? etw.subject.toLowerCase() : etw.subject };
  }
  if (!requestId) return null;
  const req = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
  const win = windowFromRequestRow(req, env);
  if (!win) return null;
  const subj = lockSubject(lockMachine);
  if (!subj) return null;
  const product = String(req?.product || 'trip-orders').trim() || 'trip-orders';
  return {
    first: win.first,
    last: win.last,
    product,
    kind: subj.kind,
    subject: subj.kind === 'm' ? subj.subject.toLowerCase() : subj.subject,
    source: win.source,
  };
}

function recordSubject(map, product, kind, subject, window, source) {
  const key = `${product}\0${kind}\0${subject}`;
  const prev = map.get(key);
  const next = pickEarlierWindow(prev, { first: window.first, last: window.last, source });
  map.set(key, next);
}

export async function backfillTrialGrants(env, productFilter) {
  const products = productFilter ? [normalizeProduct(productFilter)] : null;
  const subjectWindows = new Map();
  const createdAt = new Date().toISOString();

  const etwRows = await env.DB.prepare(
    "SELECT machine, request_id FROM machine_trials WHERE machine LIKE 'etw|%'",
  ).bind().all();
  for (const row of etwRows.results || []) {
    const parsed = await trialWindowForLock(env, row.machine, row.request_id);
    if (!parsed) continue;
    if (products && !products.includes(parsed.product)) continue;
    recordSubject(subjectWindows, parsed.product, parsed.kind, parsed.subject, parsed, parsed.source);
  }

  const lockRows = await env.DB.prepare('SELECT machine, request_id FROM machine_trials').bind().all();
  for (const row of lockRows.results || []) {
    const m = String(row.machine || '');
    if (m.startsWith(ETW_PREFIX)) continue;
    const parsed = await trialWindowForLock(env, m, row.request_id);
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
    const win = windowFromRequestRow(row, env);
    if (!win) continue;
    const product = normalizeProduct(row.product);
    if (products && !products.includes(product)) continue;
    const dkey = String(row.device_key || '').trim() || deviceKeyNorm(row.device);
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

async function machinesFromRequests(env, product, deviceKeys, machineHashes) {
  const machines = new Set(machineHashes);
  const deviceKeysOut = new Set(deviceKeys);
  const deviceCodes = new Set();
  if (deviceKeys.length) {
    const ph = deviceKeys.map(() => 'device_key = ?').join(' OR ');
    const rows = await env.DB.prepare(
      `SELECT DISTINCT machine, device, device_key FROM licence_requests WHERE product = ? AND (${ph}) LIMIT ?`,
    ).bind(product, ...deviceKeys, LINK_QUERY_LIMIT).all();
    for (const row of rows.results || []) {
      const mh = normalizeMachineHash(row.machine);
      if (mh) machines.add(mh);
      if (row.device_key) deviceKeysOut.add(String(row.device_key));
      if (row.device) deviceCodes.add(String(row.device));
    }
  }
  if (machineHashes.length) {
    const ph = machineHashes.map(() => 'lower(machine) = ?').join(' OR ');
    const rows = await env.DB.prepare(
      `SELECT DISTINCT device_key, device, machine FROM licence_requests WHERE product = ? AND (${ph}) LIMIT ?`,
    ).bind(product, ...machineHashes, LINK_QUERY_LIMIT).all();
    for (const row of rows.results || []) {
      if (row.device_key) deviceKeysOut.add(String(row.device_key));
      if (row.device) deviceCodes.add(String(row.device));
      const mh = normalizeMachineHash(row.machine);
      if (mh) machines.add(mh);
    }
  }
  return { deviceKeys: deviceKeysOut, deviceCodes, machines };
}

/** Every linked device key and machine hash (lowercased) for trial identity. */
export async function linkedSubjects(env, productId, device, machines = []) {
  const product = normalizeProduct(productId);
  const dkey = deviceKeyNorm(device);
  const machineSet = new Set();
  for (const m of machines) {
    const mh = normalizeMachineHash(m);
    if (mh) machineSet.add(mh);
  }

  const deviceKeySet = new Set([dkey]);
  const deviceCodeSet = new Set([String(device || '').trim()]);
  for (let round = 0; round < 2; round++) {
    const devList = [...deviceKeySet].slice(0, LINK_QUERY_LIMIT);
    const machList = [...machineSet].slice(0, LINK_QUERY_LIMIT);
    const expanded = await machinesFromRequests(env, product, devList, machList);
    for (const d of expanded.deviceKeys) deviceKeySet.add(d);
    for (const c of expanded.deviceCodes) deviceCodeSet.add(c);
    for (const m of expanded.machines) machineSet.add(m);

    if (deviceCodeSet.size) {
      const codes = [...deviceCodeSet].slice(0, LINK_QUERY_LIMIT);
      const ph = codes.map(() => 'device = ?').join(' OR ');
      const custRows = await env.DB.prepare(
        `SELECT device FROM customers WHERE product = ? AND (${ph}) LIMIT ?`,
      ).bind(product, ...codes, LINK_QUERY_LIMIT).all();
      for (const row of custRows.results || []) {
        deviceCodeSet.add(String(row.device));
        try {
          deviceKeySet.add(deviceKeyNorm(row.device));
        } catch { /* skip */ }
      }
    }
  }

  return {
    devices: [...deviceKeySet],
    machines: [...machineSet],
    deviceCodes: [...deviceCodeSet],
  };
}

async function strongestTermForDevice(env, product, deviceKeyStr, deviceCodes = []) {
  let best = null;
  for (const code of deviceCodes) {
    const cust = await env.DB.prepare(
      'SELECT licence_tier, licence_expiry, kind, last_day FROM customers WHERE product = ? AND device = ?',
    ).bind(product, code).first();
    best = pickStrongerTerm(best, termFromRow(cust));
  }

  const rows = await env.DB.prepare(
    `SELECT licence_tier, licence_expiry, kind FROM licence_requests
     WHERE product = ? AND device_key = ? LIMIT ?`,
  ).bind(product, deviceKeyStr, LINK_QUERY_LIMIT).all();
  for (const row of rows.results || []) {
    best = pickStrongerTerm(best, termFromRow(row));
  }
  return best;
}

async function earliestLedgerWindow(env, product, devices, machines) {
  let best = null;
  const kinds = [
    ...devices.map((d) => ['d', d]),
    ...machines.map((m) => ['m', m]),
  ];
  for (const [kind, subject] of kinds) {
    const row = await env.DB.prepare(
      `SELECT first_day, last_day FROM trial_grants
       WHERE product = ? AND subject_kind = ? AND subject = ?`,
    ).bind(product, kind, subject).first();
    if (!row) continue;
    const win = { first: String(row.first_day), last: String(row.last_day) };
    if (!isValidCalendarIso(win.first) || !isValidCalendarIso(win.last)) continue;
    best = pickEarlierWindow(best, win);
  }
  return best;
}

export async function resolveTrial(env, productId, device, machines = [], options = {}) {
  const product = normalizeProduct(productId);
  const today = options.today || calendarDateInTz(new Date(), hubCalendarTz(env)).iso;
  const linked = await linkedSubjects(env, product, device, machines);
  const codesByKey = new Map();
  for (const code of linked.deviceCodes || []) {
    try {
      const dk = deviceKeyNorm(code);
      if (!codesByKey.has(dk)) codesByKey.set(dk, new Set());
      codesByKey.get(dk).add(code);
    } catch { /* skip */ }
  }

  const ledger = await earliestLedgerWindow(env, product, linked.devices, linked.machines);
  if (ledger) {
    return {
      kind: 'existing',
      first_day: ledger.first,
      last_day: ledger.last,
      active: today <= ledger.last,
    };
  }

  for (const dkey of linked.devices) {
    const term = await strongestTermForDevice(env, product, dkey, [...(codesByKey.get(dkey) || [])]);
    if (isActiveStrongTerm(term, env, today)) {
      return { kind: 'blocked', reason: 'downgrade_forbidden' };
    }
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
