import { normalize } from './afcodes.js';
import { calendarDateInTz, isValidCalendarIso, shiftCalendarDays } from './calendar.js';

const LINK_CLOSURE_CAP = 256;
const D1_STMT_BIND_MAX = 90;
const RESOLVE_QUERY_BUDGET = 50;
const ETW_PREFIX = 'etw|';
const BACKFILL_PAGE_SIZE_DEFAULT = 500;
const BACKFILL_INSERT_BATCH_SIZE_DEFAULT = 50;
const BACKFILL_INSERT_BINDS_PER_ROW = 7;

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

function requestHasIssuedTrialEvidence(row) {
  const kind = String(row?.kind ?? '').trim().toLowerCase();
  if (kind !== 'trial') return false;
  const last = String(row?.licence_expiry ?? '').trim();
  if (last && isValidCalendarIso(last)) return true;
  const tier = String(row?.licence_tier ?? '').trim().toLowerCase();
  if (tier === 'trial') return true;
  return false;
}

function requestIsTrialGrantSource(row) {
  const status = String(row?.status ?? '').trim().toLowerCase();
  const reason = String(row?.reason ?? '').trim().toLowerCase();
  if (status === 'expired' && reason === 'pending_timeout') return false;
  if (status === 'pending' || status === 'pending_timeout') return false;
  if (!['issued', 'delivered', 'expired', 'refused', 'approved'].includes(status)) return false;

  const last = String(row?.licence_expiry ?? '').trim();
  const hasExpiry = last !== '' && isValidCalendarIso(last);

  if (status === 'refused' || status === 'approved') {
    if (!requestHasIssuedTrialEvidence(row)) return false;
  }

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

async function forEachTablePage(env, baseSql, binds, pageSize, onRow) {
  let afterRowid = 0;
  for (;;) {
    const sql = /\bwhere\b/i.test(baseSql)
      ? `${baseSql} AND rowid > ? ORDER BY rowid LIMIT ?`
      : `${baseSql} WHERE rowid > ? ORDER BY rowid LIMIT ?`;
    const page = await env.DB.prepare(sql).bind(...binds, afterRowid, pageSize).all();
    const rows = page.results || [];
    if (!rows.length) break;
    for (const row of rows) {
      afterRowid = row.rowid;
      onRow(row);
    }
    if (rows.length < pageSize) break;
  }
}

async function flushBackfillInserts(env, stmts, insertBatchSize) {
  if (!stmts.length) return;
  for (let i = 0; i < stmts.length; i += insertBatchSize) {
    await env.DB.batch(stmts.slice(i, i + insertBatchSize));
  }
}

export async function backfillTrialGrants(env, productFilter, options = {}) {
  const products = productFilter ? [normalizeProduct(productFilter)] : null;
  const pageSize = Math.max(
    1,
    Number(options.pageSize ?? env.TRIAL_BACKFILL_PAGE_SIZE ?? BACKFILL_PAGE_SIZE_DEFAULT) || BACKFILL_PAGE_SIZE_DEFAULT,
  );
  const insertBatchSize = Math.min(
    BACKFILL_INSERT_BATCH_SIZE_DEFAULT,
    Math.max(
      1,
      Number(options.insertBatchSize ?? env.TRIAL_BACKFILL_INSERT_BATCH ?? BACKFILL_INSERT_BATCH_SIZE_DEFAULT)
        || BACKFILL_INSERT_BATCH_SIZE_DEFAULT,
    ),
  );
  if (BACKFILL_INSERT_BINDS_PER_ROW > 100) {
    throw new Error('backfill_insert_batch_too_large');
  }
  const subjectWindows = new Map();
  const createdAt = new Date().toISOString();

  await forEachTablePage(
    env,
    `SELECT rowid, machine, request_id FROM machine_trials WHERE machine LIKE ?`,
    [`${ETW_PREFIX}%`],
    pageSize,
    (row) => {
      const parsed = trialWindowFromEtwRow(row);
      if (!parsed) return;
      if (products && !products.includes(parsed.product)) return;
      recordSubject(subjectWindows, parsed.product, parsed.kind, parsed.subject, parsed, parsed.source);
    },
  );

  const reqStatusList = `('issued', 'delivered', 'expired', 'refused', 'approved')`;
  const reqBase = products
    ? `SELECT rowid, * FROM licence_requests WHERE product = ? AND status IN ${reqStatusList}`
    : `SELECT rowid, * FROM licence_requests WHERE status IN ${reqStatusList}`;
  const reqBinds = products ? [products[0]] : [];
  await forEachTablePage(env, reqBase, reqBinds, pageSize, (row) => {
    if (!requestIsTrialGrantSource(row)) return;
    const win = windowFromRequestRowForBackfill(row, env);
    if (!win) return;
    const product = normalizeProduct(row.product);
    if (products && !products.includes(product)) return;
    let dkey;
    try {
      dkey = String(row.device_key || '').trim() || deviceKeyNorm(row.device);
    } catch {
      return;
    }
    recordSubject(subjectWindows, product, 'd', dkey, win, win.source);
    const mh = normalizeMachineHash(row.machine);
    if (mh) recordSubject(subjectWindows, product, 'm', mh, win, win.source);
  });

  const custBase = products
    ? 'SELECT rowid, * FROM customers WHERE product = ?'
    : 'SELECT rowid, * FROM customers';
  const custBinds = products ? [products[0]] : [];
  await forEachTablePage(env, custBase, custBinds, pageSize, (row) => {
    const win = windowFromCustomerRow(row);
    if (!win) return;
    const product = normalizeProduct(row.product);
    if (products && !products.includes(product)) return;
    let dkey;
    try {
      dkey = deviceKeyNorm(row.device);
    } catch {
      return;
    }
    recordSubject(subjectWindows, product, 'd', dkey, win, win.source);
  });

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
  await flushBackfillInserts(env, stmts, insertBatchSize);
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
  const machinesJson = JSON.stringify(
    machineChunk.map((mh) => String(mh || '').toLowerCase()).filter(Boolean),
  );
  const seedsSql = `SELECT 'd' AS kind, ? AS id
    UNION ALL
    SELECT 'm', lower(j.value)
    FROM json_each(?) AS j`;
  const binds = [dkey, machinesJson, product, product];
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
  const part = await runClosureChunk(env, product, dkey, seedMachines, budget);
  if (part.limit) return { blocked: true, reason: 'link_limit' };
  for (const id of part.devices) deviceSet.add(id);
  for (const id of part.machines) machineSet.add(id);

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

/** SQL expression matching `afcodes.js` `normalize()` for device codes (strip, upper, O/I/L). */
function deviceCodeNormSql(column) {
  const stripped = `replace(replace(replace(replace(replace(replace(replace(${column}, '-', ''), ' ', ''), char(9), ''), char(10), ''), char(13), ''), '_', ''), '.', '')`;
  return `replace(replace(replace(upper(${stripped}), 'O', '0'), 'I', '1'), 'L', '1')`;
}

function customerDeviceMatchSql() {
  return deviceCodeNormSql('device');
}

function ledgerDeviceSubjectMatchSql() {
  return deviceCodeNormSql('subject');
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
       WHERE product = ? AND subject_kind = 'd' AND ${ledgerDeviceSubjectMatchSql()} IN (${ph})
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

/** Max subjects per propagate INSERT (JSON payload size guard; binds stay at six). */
const GRANT_PROPAGATE_ROWS_PER_STMT = 256;

function closureGrantSubjects(devices, machines) {
  const rows = [];
  const seen = new Set();
  for (const d of devices) {
    const id = String(d || '').trim();
    if (!id || seen.has(`d:${id}`)) continue;
    seen.add(`d:${id}`);
    rows.push({ kind: 'd', subject: id });
  }
  for (const mh of machines) {
    const id = String(mh || '').trim();
    if (!id || seen.has(`m:${id}`)) continue;
    seen.add(`m:${id}`);
    rows.push({ kind: 'm', subject: id });
  }
  return rows;
}

function grantWindowGuardStatement(env, reqFirst, reqLast, authWin) {
  const sql = `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at)
    SELECT NULL, 'd', '', '', '', ''
    WHERE ? = 1 AND (? <> ? OR ? <> ?)`;
  if (!authWin) {
    return env.DB.prepare(sql).bind(0, '', reqFirst, '', reqLast);
  }
  const mismatch = authWin.first !== reqFirst || authWin.last !== reqLast;
  return env.DB.prepare(sql).bind(
    mismatch ? 1 : 0,
    authWin.first,
    reqFirst,
    authWin.last,
    reqLast,
  );
}

function grantPropagateStatement(env, product, subjectRows, winFirst, winLast, createdAt, src) {
  const payload = JSON.stringify(
    subjectRows.map((row) => ({ kind: row.kind, subject: row.subject })),
  );
  const sql = `INSERT OR IGNORE INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
    SELECT ? AS product,
           json_extract(j.value, '$.kind') AS subject_kind,
           json_extract(j.value, '$.subject') AS subject,
           ? AS first_day,
           ? AS last_day,
           ? AS created_at,
           ? AS source_request
    FROM json_each(?) AS j`;
  const binds = [product, winFirst, winLast, createdAt, src, payload];
  if (binds.length > D1_STMT_BIND_MAX) {
    throw new Error('link_limit');
  }
  return env.DB.prepare(sql).bind(...binds);
}

/**
 * Insert-only trial ledger rows for the device↔machine closure (same subject set as resolveTrial).
 * Propagate inserts the closure-wide earliest window (min first_day, tie min last_day) for every
 * linked subject lacking a row (INSERT OR IGNORE; later rows on other subjects are untouched).
 * A final guard aborts the D1 batch when that authoritative window exists and differs from the
 * requested window (see README).
 */
export async function trialGrantStatements(env, productId, device, machines, window, sourceRequest) {
  const product = normalizeProduct(productId);
  const first = String(window?.first_day || window?.first || '').trim();
  const last = String(window?.last_day || window?.last || '').trim();
  if (!isValidCalendarIso(first) || !isValidCalendarIso(last)) {
    throw new Error('bad_trial_window');
  }
  const createdAt = new Date().toISOString();
  const src = sourceRequest || null;
  const budget = { used: 0 };
  const closure = await computeLinkedClosure(env, product, device, machines, budget);
  if (closure.blocked) {
    throw new Error('link_limit');
  }
  const ledgerResult = await earliestLedgerWindow(env, product, closure.devices, closure.machines, budget);
  if (ledgerResult.limit) {
    throw new Error('link_limit');
  }
  const authWin = ledgerResult.window;
  const insertFirst = authWin ? authWin.first : first;
  const insertLast = authWin ? authWin.last : last;
  const subjects = closureGrantSubjects(closure.devices, closure.machines);
  if (!subjects.length) {
    throw new Error('link_limit');
  }
  const stmts = [];
  for (let i = 0; i < subjects.length; i += GRANT_PROPAGATE_ROWS_PER_STMT) {
    const chunk = subjects.slice(i, i + GRANT_PROPAGATE_ROWS_PER_STMT);
    stmts.push(
      grantPropagateStatement(env, product, chunk, insertFirst, insertLast, createdAt, src),
    );
  }
  stmts.push(grantWindowGuardStatement(env, first, last, authWin));
  return stmts;
}
