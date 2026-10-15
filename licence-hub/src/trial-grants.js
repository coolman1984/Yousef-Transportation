import { normalize } from './afcodes.js';
import { calendarDateInTz, isValidCalendarIso, shiftCalendarDays } from './calendar.js';

const LINK_CLOSURE_CAP = 256;
const D1_STMT_BIND_MAX = 90;
const RESOLVE_QUERY_BUDGET = 50;
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

function inChunkSize(reservedBinds) {
  return Math.max(1, D1_STMT_BIND_MAX - reservedBinds);
}

/** @returns {{ ok: true } | { ok: false, reason: 'link_limit' }} */
function spendQueryBudget(budget) {
  if (!budget) return { ok: true };
  budget.used += 1;
  if (budget.used > RESOLVE_QUERY_BUDGET) return { ok: false, reason: 'link_limit' };
  return { ok: true };
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

function windowFromRequestRowForBackfill(row, env) {
  if (!row || !requestIsTrialGrantSource(row)) return null;
  const last = String(row.licence_expiry || '').trim();
  if (!last || !isValidCalendarIso(last)) return null;
  const inclusive = trialInclusiveDays(env);
  return {
    first: shiftCalendarDays(last, -(inclusive - 1)),
    last,
    source: row.id || null,
  };
}

function customerTrialLastDay(row) {
  const lastDay = String(row?.last_day ?? '').trim();
  if (lastDay) return lastDay;
  const exp = row?.licence_expiry;
  if (exp === null || exp === undefined) return '';
  return String(exp).trim();
}

function windowFromCustomerRow(row) {
  if (!row) return null;
  const kind = String(row?.kind ?? '').trim().toLowerCase();
  const licTier = String(row?.licence_tier ?? '').trim().toLowerCase();
  if (licTier === 'paid' || licTier === 'permanent' || kind === 'paid' || kind === 'permanent') {
    return null;
  }
  const trialCustomer = kind === 'trial' || licTier === 'trial' || (licTier === '' && kind === 'trial');
  if (!trialCustomer && !rowIsTrialLike(row)) return null;
  const first = String(row.first_day || '').trim();
  const last = customerTrialLastDay(row);
  if (!first || !last || !isValidCalendarIso(first) || !isValidCalendarIso(last)) return null;
  if (first > last) return null;
  return { first, last, source: row.id || null };
}

function paidUntilFromRow(row) {
  const exp = row?.licence_expiry;
  if (exp !== null && exp !== undefined) {
    const trimmed = String(exp).trim();
    if (trimmed === '') {
      return String(row?.last_day ?? '').trim();
    }
    return trimmed;
  }
  return String(row?.last_day ?? '').trim();
}

function termFromRow(row) {
  if (!row) return null;
  const tier = String(row.licence_tier || row.kind || '').trim().toLowerCase();
  if (!tier) return null;
  const paidLike = tier === 'paid' || tier === 'monthly';
  const until = paidLike ? paidUntilFromRow(row) : '';
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

function requestIsTrialGrantSource(row) {
  const status = String(row?.status ?? '').trim().toLowerCase();
  const reason = String(row?.reason ?? '').trim().toLowerCase();
  if (status === 'expired' && reason === 'pending_timeout') return false;
  if (!['issued', 'delivered', 'expired'].includes(status)) return false;

  const last = String(row?.licence_expiry ?? '').trim();
  const hasExpiry = last !== '' && isValidCalendarIso(last);

  if (rowIsTrialLike(row)) {
    if (status === 'expired' && !hasExpiry) return false;
    return true;
  }
  return false;
}

/** Trial window from an etw| machine_trials row only (not d:/h: locks). */
function trialWindowFromEtwRow(row) {
  const etw = parseEtwKey(row.machine);
  if (!etw) return null;
  const win = parseEtwWindow(row.request_id);
  if (!win) return null;
  let subject;
  if (etw.kind === 'm') {
    subject = etw.subject.toLowerCase();
  } else {
    try {
      subject = deviceKeyNorm(etw.subject);
    } catch {
      return null;
    }
  }
  return {
    first: win.first,
    last: win.last,
    product: etw.product,
    kind: etw.kind,
    subject,
    source: null,
  };
}

export async function backfillTrialGrants(env, productFilter) {
  const products = productFilter ? [normalizeProduct(productFilter)] : null;
  const subjectWindows = new Map();
  const createdAt = new Date().toISOString();

  const etwRows = await env.DB.prepare(
    'SELECT machine, request_id FROM machine_trials WHERE machine LIKE ?',
  ).bind(`${ETW_PREFIX}%`).all();
  for (const row of etwRows.results || []) {
    const parsed = trialWindowFromEtwRow(row);
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
    if (!requestIsTrialGrantSource(row)) continue;
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

function closureSql(seedsSql) {
  return `
WITH RECURSIVE
seeds(kind, id) AS (
  ${seedsSql}
),
closure(kind, id) AS (
  SELECT kind, id FROM seeds
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
}

async function runClosureChunk(env, product, dkey, machineChunk, budget) {
  const spent = spendQueryBudget(budget);
  if (!spent.ok) return { limit: true };
  const seedParts = [`SELECT 'd' AS kind, ? AS id`];
  const binds = [dkey];
  for (const mh of machineChunk) {
    seedParts.push(`SELECT 'm', ?`);
    binds.push(mh);
  }
  const seedsSql = seedParts.join(' UNION ALL ');
  binds.push(product, product);
  const rows = await env.DB.prepare(closureSql(seedsSql)).bind(...binds).all();
  const deviceSet = new Set();
  const machineSet = new Set();
  for (const row of rows.results || []) {
    if (row.kind === 'd') deviceSet.add(String(row.id));
    else if (row.kind === 'm') machineSet.add(String(row.id));
  }
  return { limit: false, devices: deviceSet, machines: machineSet };
}

async function computeLinkedClosure(env, product, device, machines = [], budget = null) {
  const dkey = deviceKeyNorm(device);
  const seedMachines = [];
  for (const m of machines) {
    const mh = normalizeMachineHash(m);
    if (mh) seedMachines.push(mh);
  }

  const deviceSet = new Set();
  const machineSet = new Set();
  const reservedBinds = 3;
  const machineChunkSize = inChunkSize(reservedBinds);
  if (!seedMachines.length) {
    const part = await runClosureChunk(env, product, dkey, [], budget);
    if (part.limit) return { blocked: true, reason: 'link_limit' };
    for (const id of part.devices) deviceSet.add(id);
    for (const id of part.machines) machineSet.add(id);
  } else {
    for (let i = 0; i < seedMachines.length; i += machineChunkSize) {
      const chunk = seedMachines.slice(i, i + machineChunkSize);
      const part = await runClosureChunk(env, product, dkey, chunk, budget);
      if (part.limit) return { blocked: true, reason: 'link_limit' };
      for (const id of part.devices) deviceSet.add(id);
      for (const id of part.machines) machineSet.add(id);
    }
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
  const budget = { used: 0 };
  const closure = await computeLinkedClosure(env, product, device, machines, budget);
  if (closure.blocked) {
    return { devices: [], machines: [], deviceCodes: [], link_limit: true };
  }
  const codeResult = await deviceCodesForClosure(env, product, device, closure.devices, budget);
  if (codeResult.limit) {
    return { devices: [], machines: [], deviceCodes: [], link_limit: true };
  }
  return {
    devices: closure.devices,
    machines: closure.machines,
    deviceCodes: codeResult.codes,
    link_limit: false,
  };
}

function customerDeviceMatchSql() {
  return "upper(replace(device, '-', ''))";
}

function normalizedDeviceKeys(codes) {
  const keys = new Set();
  for (const raw of codes) {
    try {
      keys.add(deviceKeyNorm(raw));
    } catch {
      /* skip malformed display codes */
    }
  }
  return [...keys];
}

async function strongestTermOnClosure(env, product, devices, deviceCodes, budget) {
  let best = null;
  const chunk = inChunkSize(1);
  const custKeys = normalizedDeviceKeys(deviceCodes);
  if (custKeys.length) {
    for (let i = 0; i < custKeys.length; i += chunk) {
      const spent = spendQueryBudget(budget);
      if (!spent.ok) return { limit: true };
      const part = custKeys.slice(i, i + chunk);
      const ph = part.map(() => '?').join(', ');
      const custRows = await env.DB.prepare(
        `SELECT licence_tier, licence_expiry, kind, last_day FROM customers
         WHERE product = ? AND ${customerDeviceMatchSql()} IN (${ph})`,
      ).bind(product, ...part).all();
      for (const row of custRows.results || []) {
        best = pickStrongerTerm(best, termFromRow(row));
      }
    }
  }
  if (devices.length) {
    for (let i = 0; i < devices.length; i += chunk) {
      const spent = spendQueryBudget(budget);
      if (!spent.ok) return { limit: true };
      const part = devices.slice(i, i + chunk);
      const ph = part.map(() => '?').join(', ');
      const reqRows = await env.DB.prepare(
        `SELECT licence_tier, licence_expiry, kind FROM licence_requests
         WHERE product = ? AND device_key IN (${ph}) AND status IN ('issued', 'delivered')`,
      ).bind(product, ...part).all();
      for (const row of reqRows.results || []) {
        best = pickStrongerTerm(best, termFromRow(row));
      }
    }
  }
  return { limit: false, term: best };
}

async function earliestLedgerWindow(env, product, devices, machines, budget) {
  let best = null;
  const chunk = inChunkSize(1);
  for (let i = 0; i < devices.length; i += chunk) {
    const spent = spendQueryBudget(budget);
    if (!spent.ok) return { limit: true };
    const part = devices.slice(i, i + chunk);
    const ph = part.map(() => '?').join(', ');
    const row = await env.DB.prepare(
      `SELECT first_day, last_day FROM trial_grants
       WHERE product = ? AND subject_kind = 'd' AND subject IN (${ph})
       ORDER BY first_day ASC, last_day ASC LIMIT 1`,
    ).bind(product, ...part).first();
    if (row) {
      const win = { first: String(row.first_day), last: String(row.last_day) };
      if (isValidCalendarIso(win.first) && isValidCalendarIso(win.last)) {
        best = pickEarlierWindow(best, win);
      }
    }
  }
  for (let i = 0; i < machines.length; i += chunk) {
    const spent = spendQueryBudget(budget);
    if (!spent.ok) return { limit: true };
    const part = machines.slice(i, i + chunk);
    const ph = part.map(() => '?').join(', ');
    const row = await env.DB.prepare(
      `SELECT first_day, last_day FROM trial_grants
       WHERE product = ? AND subject_kind = 'm' AND subject IN (${ph})
       ORDER BY first_day ASC, last_day ASC LIMIT 1`,
    ).bind(product, ...part).first();
    if (row) {
      const win = { first: String(row.first_day), last: String(row.last_day) };
      if (isValidCalendarIso(win.first) && isValidCalendarIso(win.last)) {
        best = pickEarlierWindow(best, win);
      }
    }
  }
  return { limit: false, window: best };
}

async function deviceCodesForClosure(env, product, device, devices, budget) {
  const deviceCodes = new Set([String(device || '').trim()]);
  const chunk = inChunkSize(1);
  if (devices.length) {
    for (let i = 0; i < devices.length; i += chunk) {
      const spent = spendQueryBudget(budget);
      if (!spent.ok) return { limit: true, codes: [] };
      const part = devices.slice(i, i + chunk);
      const ph = part.map(() => '?').join(', ');
      const devRows = await env.DB.prepare(
        `SELECT DISTINCT device FROM licence_requests WHERE product = ? AND device_key IN (${ph})`,
      ).bind(product, ...part).all();
      for (const row of devRows.results || []) {
        if (row.device) deviceCodes.add(String(row.device));
      }
    }
  }
  const codes = [...deviceCodes];
  if (codes.length) {
    for (let i = 0; i < codes.length; i += chunk) {
      const spent = spendQueryBudget(budget);
      if (!spent.ok) return { limit: true, codes: [] };
      const part = codes.slice(i, i + chunk);
      const keys = normalizedDeviceKeys(part);
      if (!keys.length) continue;
      const kPh = keys.map(() => '?').join(', ');
      const custRows = await env.DB.prepare(
        `SELECT device FROM customers WHERE product = ? AND ${customerDeviceMatchSql()} IN (${kPh})`,
      ).bind(product, ...keys).all();
      for (const row of custRows.results || []) {
        if (row.device) deviceCodes.add(String(row.device));
      }
    }
  }
  return { limit: false, codes: [...deviceCodes] };
}

export async function resolveTrial(env, productId, device, machines = [], options = {}) {
  const product = normalizeProduct(productId);
  const today = options.today || calendarDateInTz(new Date(), hubCalendarTz(env)).iso;
  const budget = { used: 0 };
  const closure = await computeLinkedClosure(env, product, device, machines, budget);
  if (closure.blocked) {
    return { kind: 'blocked', reason: 'link_limit' };
  }
  const codeResult = await deviceCodesForClosure(env, product, device, closure.devices, budget);
  if (codeResult.limit) {
    return { kind: 'blocked', reason: 'link_limit' };
  }
  const deviceCodes = codeResult.codes;
  const termResult = await strongestTermOnClosure(env, product, closure.devices, deviceCodes, budget);
  if (termResult.limit) {
    return { kind: 'blocked', reason: 'link_limit' };
  }
  const strongTerm = termResult.term;
  const blockedBy = isActiveStrongTerm(strongTerm, env, today) ? 'downgrade_forbidden' : null;

  const ledgerResult = await earliestLedgerWindow(env, product, closure.devices, closure.machines, budget);
  if (ledgerResult.limit) {
    return { kind: 'blocked', reason: 'link_limit' };
  }
  const ledger = ledgerResult.window;
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

/**
 * When true, the last prepared statement from `trialGrantStatements` is the window guard.
 * PR B must run the full returned array in one D1 batch: ledger propagate inserts, then this
 * guard, then (in the same batch) the licence issue write. A guard failure means the batch
 * rolls back — re-resolve trial for the requested window and sign that existing window.
 */
export const TRIAL_GRANT_WINDOW_GUARD_LAST = true;

const GRANT_ROW_BINDS = 6;

function grantSubjectsWhereSql(mhList) {
  const deviceClause = "(tg.subject_kind = 'd' AND tg.subject = ?)";
  if (!mhList.length) {
    return { where: `tg.product = ? AND ${deviceClause}`, binds: (product, dkey) => [product, dkey] };
  }
  const mPh = mhList.map(() => '?').join(', ');
  return {
    where: `tg.product = ? AND (${deviceClause} OR (tg.subject_kind = 'm' AND tg.subject IN (${mPh})))`,
    binds: (product, dkey) => [product, dkey, ...mhList],
  };
}

function authoritativeEarliestSubquery(mhList) {
  const { where } = grantSubjectsWhereSql(mhList);
  return `(SELECT tg.first_day, tg.last_day FROM trial_grants tg
    WHERE ${where}
    ORDER BY tg.first_day ASC, tg.last_day ASC LIMIT 1)`;
}

function grantAuthBindCount(mhList) {
  return 2 + mhList.length;
}

function grantPropagateBindCount(rowCount, mhList) {
  return GRANT_ROW_BINDS * rowCount + grantAuthBindCount(mhList);
}

function maxMachineRowsPerPropagateStmt(mhList, includeDevice) {
  let best = -1;
  for (let machineRows = 0; machineRows <= mhList.length; machineRows += 1) {
    const rowCount = (includeDevice ? 1 : 0) + machineRows;
    if (rowCount === 0) continue;
    if (grantPropagateBindCount(rowCount, mhList) <= D1_STMT_BIND_MAX) {
      best = machineRows;
    }
  }
  return best;
}

function grantWindowGuardStatement(env, product, dkey, mhList, reqFirst, reqLast) {
  const { binds: authBinds } = grantSubjectsWhereSql(mhList);
  const auth = authoritativeEarliestSubquery(mhList);
  const sql = `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at)
    SELECT NULL, 'd', '', '', '', ''
    WHERE EXISTS (
      SELECT 1 FROM ${auth} AS auth
      WHERE auth.first_day <> ? OR auth.last_day <> ?
    )`;
  const bindArgs = [...authBinds(product, dkey), reqFirst, reqLast];
  if (bindArgs.length > D1_STMT_BIND_MAX) {
    throw new Error('link_limit');
  }
  return env.DB.prepare(sql).bind(...bindArgs);
}

function grantPropagateStatement(env, product, dkey, mhList, reqFirst, reqLast, createdAt, src, includeDevice, mhChunk) {
  const auth = authoritativeEarliestSubquery(mhList);
  const { binds: authBinds } = grantSubjectsWhereSql(mhList);
  const unions = [];
  const binds = [];
  if (includeDevice) {
    unions.push(
      `SELECT ? AS product, 'd' AS subject_kind, ? AS subject, ? AS req_first, ? AS req_last, ? AS created_at, ? AS source_request`,
    );
    binds.push(product, dkey, reqFirst, reqLast, createdAt, src);
  }
  for (const mh of mhChunk) {
    unions.push(
      `SELECT ? AS product, 'm' AS subject_kind, ? AS subject, ? AS req_first, ? AS req_last, ? AS created_at, ? AS source_request`,
    );
    binds.push(product, mh, reqFirst, reqLast, createdAt, src);
  }
  const sql = `INSERT OR IGNORE INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
    SELECT planned.product, planned.subject_kind, planned.subject,
      COALESCE(auth.first_day, planned.req_first),
      COALESCE(auth.last_day, planned.req_last),
      planned.created_at, planned.source_request
    FROM (${unions.join(' UNION ALL ')}) AS planned
    LEFT JOIN ${auth} AS auth ON 1 = 1`;
  const bindArgs = [...binds, ...authBinds(product, dkey)];
  if (bindArgs.length > D1_STMT_BIND_MAX) {
    throw new Error('link_limit');
  }
  return env.DB.prepare(sql).bind(...bindArgs);
}

/**
 * Insert-only trial ledger rows for a device and optional machine hashes.
 * Propagate inserts use the earliest window already stored for this device and listed hashes
 * (fallback: requested window). A final guard statement aborts the D1 batch when that
 * authoritative window still differs from the requested window after propagate (see README).
 */
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
  const mhList = [];
  const seen = new Set();
  for (const raw of machines || []) {
    const mh = normalizeMachineHash(raw);
    if (!mh || seen.has(mh)) continue;
    seen.add(mh);
    mhList.push(mh);
  }
  if (grantAuthBindCount(mhList) + 2 > D1_STMT_BIND_MAX) {
    throw new Error('link_limit');
  }
  const stmts = [];
  if (mhList.length === 0) {
    if (maxMachineRowsPerPropagateStmt(mhList, true) < 0) {
      throw new Error('link_limit');
    }
    stmts.push(
      grantPropagateStatement(env, product, dkey, mhList, first, last, createdAt, src, true, []),
    );
  } else {
    let offset = 0;
    const firstTake = maxMachineRowsPerPropagateStmt(mhList, true);
    if (firstTake < 0) {
      throw new Error('link_limit');
    }
    stmts.push(
      grantPropagateStatement(
        env, product, dkey, mhList, first, last, createdAt, src, true, mhList.slice(0, firstTake),
      ),
    );
    offset = firstTake;
    while (offset < mhList.length) {
      const take = maxMachineRowsPerPropagateStmt(mhList, false);
      if (take < 1) {
        throw new Error('link_limit');
      }
      stmts.push(
        grantPropagateStatement(
          env, product, dkey, mhList, first, last, createdAt, src, false, mhList.slice(offset, offset + take),
        ),
      );
      offset += take;
    }
  }
  stmts.push(grantWindowGuardStatement(env, product, dkey, mhList, first, last));
  return stmts;
}
