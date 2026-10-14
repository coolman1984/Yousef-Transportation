import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { newD1 } from './d1-mock.js';
import { deviceKey, deviceLockKey, machineLockKey } from '../src/licence-api.js';
import {
  normalizeMachineHash,
  backfillTrialGrants,
  linkedSubjects,
  resolveTrial,
  trialGrantStatements,
  isActiveStrongTerm,
} from '../src/trial-grants.js';
import { shiftCalendarDays } from '../src/calendar.js';
import { applyMigrations } from '../scripts/apply-migrations.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const PRODUCT = 'trip-orders';
const DEVICE_A = '7KD2M-QX9TP';
const DEVICE_B = 'ABCDE-FGHJK';
const DEVICE_C = 'WXYZ2-ABCDE';
const DKEY_A = deviceKey(DEVICE_A);
const DKEY_B = deviceKey(DEVICE_B);
const DKEY_C = deviceKey(DEVICE_C);
const MACHINE_A = 'a'.repeat(64);
const MACHINE_A_UPPER = MACHINE_A.toUpperCase();
const MACHINE_B = 'b'.repeat(64);
const MACHINE_M1 = '1'.repeat(64);
const MACHINE_M2 = '2'.repeat(64);

function env(over = {}) {
  return {
    DB: newD1(),
    TRIAL_DAYS: '14',
    LICENCE_CALENDAR_TZ: 'Africa/Cairo',
    ...over,
  };
}

function countingEnv(over = {}) {
  let queries = 0;
  const inner = newD1();
  const DB = {
    prepare(sql) {
      const stmt = inner.prepare(sql);
      return {
        bind(...args) {
          const bound = stmt.bind(...args);
          return {
            async run() {
              queries += 1;
              return bound.run();
            },
            async first() {
              queries += 1;
              return bound.first();
            },
            async all() {
              queries += 1;
              return bound.all();
            },
          };
        },
      };
    },
    batch: (stmts) => inner.batch(stmts),
  };
  return {
    e: { DB, TRIAL_DAYS: '14', LICENCE_CALENDAR_TZ: 'Africa/Cairo', ...over },
    queryCount: () => queries,
  };
}

function trialWindow(lastDay, days = 14) {
  const first = shiftCalendarDays(lastDay, -(days - 1));
  return { first, last: lastDay };
}

async function insertRequest(e, {
  id,
  device = DEVICE_A,
  dkey = DKEY_A,
  machine = MACHINE_A,
  status = 'delivered',
  tier = 'trial',
  kind = 'trial',
  expiry = '2026-06-14',
  product = PRODUCT,
  created_at = 100,
}) {
  await e.DB.prepare(
    `INSERT INTO licence_requests(
      id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, licence_tier, licence_expiry, created_at, updated_at
    ) VALUES(?, 'h', ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, ?, ?, ?)`,
  ).bind(id, product, kind, device, dkey, machine, 'n-' + id, status, tier, expiry, created_at, created_at).run();
}

test('normalizeMachineHash is lowercase 64-hex only (no trim)', () => {
  assert.equal(normalizeMachineHash(MACHINE_A_UPPER), MACHINE_A);
  assert.equal(normalizeMachineHash('  ' + MACHINE_A + '  '), null);
  assert.equal(normalizeMachineHash('not-a-hash'), null);
});

test('insert-only: second grant with different dates keeps the first row', async () => {
  const e = env();
  const win1 = { first_day: '2026-01-01', last_day: '2026-01-14' };
  const win2 = { first_day: '2026-02-01', last_day: '2026-02-14' };
  await e.DB.batch(trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], win1, 'req-1'));
  await e.DB.batch(trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], win2, 'req-2'));
  const row = await e.DB.prepare(
    'SELECT first_day, last_day, source_request FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_A).first();
  assert.equal(row.first_day, '2026-01-01');
  assert.equal(row.last_day, '2026-01-14');
  assert.equal(row.source_request, 'req-1');
});

test('trial_grants rejects update and delete', async () => {
  const e = env();
  await e.DB.batch(trialGrantStatements(e, PRODUCT, DEVICE_A, [], { first_day: '2026-01-01', last_day: '2026-01-14' }, null));
  await assert.rejects(
    () => e.DB.prepare('UPDATE trial_grants SET last_day = ? WHERE subject = ?').bind('2099-01-01', DKEY_A).run(),
    /insert-only/i,
  );
  await assert.rejects(
    () => e.DB.prepare('DELETE FROM trial_grants WHERE subject = ?').bind(DKEY_A).run(),
    /insert-only/i,
  );
});

const priorSources = ['etw_d', 'etw_m', 'lock', 'request', 'customer'];
const hashCases = ['lower', 'upper'];
const rowStatuses = ['issued', 'delivered', 'expired', 'pending', 'refused'];
const paidStates = ['none', 'active_paid', 'expired_paid', 'active_permanent', 'pending_permanent', 'refused_permanent'];
const linkShapes = ['same', 'peer', 'two_hop'];

function priorSetup(source, e, rowStatus, lastDay = '2026-06-20') {
  const { first, last } = trialWindow(lastDay);
  switch (source) {
    case 'etw_d':
      return e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|d|${DKEY_A}`, `${first}|${last}`, 1).run()
        .then(() => backfillTrialGrants(e, PRODUCT));
    case 'etw_m':
      return e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|m|${MACHINE_A}`, `${first}|${last}`, 1).run()
        .then(() => backfillTrialGrants(e, PRODUCT))
        .then(() => insertRequest(e, {
          id: 'etw-m-anchor', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A, status: rowStatus, expiry: last,
        }));
    case 'lock':
      return insertRequest(e, { id: 'lk', expiry: last, status: rowStatus }).then(() =>
        e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
          .bind(machineLockKey(MACHINE_A), 'lk', 1).run(),
      ).then(() => backfillTrialGrants(e, PRODUCT));
    case 'request':
      return insertRequest(e, { id: 'rq', expiry: last, status: rowStatus })
        .then(() => backfillTrialGrants(e, PRODUCT));
    case 'customer':
      return e.DB.prepare(
        `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
         VALUES(?, ?, '', ?, 'trial', ?, ?, 'trial', 1)`,
      ).bind('c-mx', PRODUCT, DEVICE_A, first, last).run().then(() => backfillTrialGrants(e, PRODUCT));
    default:
      return Promise.resolve();
  }
}

async function linkBridge(e, linkShape) {
  if (linkShape === 'peer') {
    await insertRequest(e, { id: 'bridge-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  }
  if (linkShape === 'two_hop') {
    await insertRequest(e, { id: 'hop-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_M1 });
    await insertRequest(e, { id: 'hop-b1', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M1 });
    await insertRequest(e, { id: 'hop-b2', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M2 });
    await insertRequest(e, { id: 'hop-c', device: DEVICE_C, dkey: DKEY_C, machine: MACHINE_M2 });
  }
}

async function paidSetup(e, paidState, linkShape) {
  if (paidState === 'none') return;
  const targetDevice = linkShape === 'same' ? DEVICE_A : (linkShape === 'peer' ? DEVICE_B : DEVICE_C);
  const targetDkey = deviceKey(targetDevice);
  const machine = linkShape === 'two_hop' ? MACHINE_M2 : MACHINE_B;
  let kind = 'monthly';
  let tier = 'paid';
  let expiry = '2026-12-31';
  let status = 'delivered';
  if (paidState === 'expired_paid') expiry = '2025-01-01';
  if (paidState === 'active_permanent') {
    kind = 'permanent';
    tier = 'permanent';
    expiry = '';
  }
  if (paidState === 'pending_permanent') {
    kind = 'permanent';
    tier = 'permanent';
    expiry = '';
    status = 'pending';
  }
  if (paidState === 'refused_permanent') {
    kind = 'permanent';
    tier = 'permanent';
    expiry = '';
    status = 'refused';
  }
  if (paidState === 'active_paid') status = 'delivered';
  await insertRequest(e, {
    id: `paid-${paidState}-${linkShape}`,
    device: targetDevice,
    dkey: targetDkey,
    machine,
    kind,
    tier,
    expiry,
    status,
  });
  if (linkShape === 'peer') {
    await insertRequest(e, { id: 'peer-bridge', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  }
}

for (const prior of priorSources) {
  for (const hashCase of hashCases) {
    for (const rowStatus of rowStatuses) {
      for (const paidState of paidStates) {
        for (const linkShape of linkShapes) {
          if (prior === 'customer' && linkShape !== 'same') continue;
          if (['etw_d', 'etw_m', 'customer'].includes(prior) && rowStatus !== 'delivered') continue;
          const blocks = ['active_paid', 'active_permanent'].includes(paidState);
          const pendingNoBlock = ['pending_permanent', 'refused_permanent'].includes(paidState);
          const expectExisting = ['etw_d', 'etw_m', 'customer'].includes(prior)
            || (['lock', 'request'].includes(prior) && ['issued', 'delivered', 'expired'].includes(rowStatus));
          test(`matrix: prior=${prior} hash=${hashCase} status=${rowStatus} paid=${paidState} link=${linkShape}`, async () => {
            const e = env();
            await priorSetup(prior, e, rowStatus);
            await linkBridge(e, linkShape);
            await paidSetup(e, paidState, linkShape);
            const machines = hashCase === 'upper' ? [MACHINE_A_UPPER] : [MACHINE_A];
            const resolveMachines = linkShape === 'same' ? machines : (linkShape === 'peer' ? [] : [MACHINE_M1]);
            const result = await resolveTrial(e, PRODUCT, DEVICE_A, resolveMachines, { today: '2026-03-01' });
            if (!expectExisting) {
              if (blocks) {
                assert.equal(result.kind, 'blocked');
                assert.equal(result.reason, 'downgrade_forbidden');
              } else {
                assert.equal(result.kind, 'eligible');
              }
              return;
            }
            assert.equal(result.kind, 'existing');
            assert.ok(result.first_day && result.last_day);
            if (blocks) {
              assert.equal(result.blocked_by, 'downgrade_forbidden');
            } else if (pendingNoBlock || paidState === 'expired_paid' || paidState === 'none') {
              assert.equal(result.blocked_by, null);
            }
          });
        }
      }
    }
  }
}

const resolveMatrix = [
  {
    name: 'no prior window',
    setup: async () => {},
    device: DEVICE_A,
    machines: [MACHINE_A],
    today: '2026-03-01',
    expect: { kind: 'eligible' },
  },
  {
    name: 'etw device row',
    setup: async (e) => {
      const { first, last } = trialWindow('2026-05-20');
      await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|d|${DKEY_A}`, `${first}|${last}`, 1).run();
      await backfillTrialGrants(e, PRODUCT);
    },
    today: '2026-05-10',
    expect: { kind: 'existing', first_day: trialWindow('2026-05-20').first, last_day: '2026-05-20', active: true },
  },
  {
    name: 'peer device shares machine ledger without peer machine in args',
    setup: async (e) => {
      const { last } = trialWindow('2026-08-01');
      await insertRequest(e, { id: 'peer', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A, expiry: last });
      await insertRequest(e, {
        id: 'self', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A,
        kind: 'monthly', tier: 'paid', expiry: '2025-01-01', status: 'delivered',
      });
      await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(machineLockKey(MACHINE_A), 'peer', 1).run();
      await backfillTrialGrants(e, PRODUCT);
    },
    device: DEVICE_A,
    machines: [],
    today: '2026-07-20',
    expect: { kind: 'existing', first_day: trialWindow('2026-08-01').first, last_day: '2026-08-01', active: true },
  },
  {
    name: 'active permanent on linked device blocks trial',
    setup: async (e) => {
      await insertRequest(e, {
        id: 'perm', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B,
        kind: 'permanent', tier: 'permanent', expiry: '',
      });
      await insertRequest(e, { id: 'bridge', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_B });
    },
    device: DEVICE_A,
    machines: [],
    today: '2026-03-01',
    expect: { kind: 'blocked', reason: 'downgrade_forbidden' },
  },
  {
    name: 'pending paid does not block',
    setup: async (e) => {
      await insertRequest(e, {
        id: 'paid', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B,
        kind: 'monthly', tier: 'paid', expiry: '2026-03-15', status: 'pending',
      });
      await insertRequest(e, { id: 'bridge', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_B });
    },
    device: DEVICE_A,
    machines: [],
    today: '2026-03-15',
    expect: { kind: 'eligible' },
  },
  {
    name: 'pending permanent does not block',
    setup: async (e) => {
      await insertRequest(e, {
        id: 'pp', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B,
        kind: 'permanent', tier: 'permanent', expiry: '', status: 'pending',
      });
      await insertRequest(e, { id: 'bridge', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_B });
    },
    device: DEVICE_A,
    machines: [],
    today: '2026-03-01',
    expect: { kind: 'eligible' },
  },
];

for (const row of resolveMatrix) {
  test(`resolveTrial: ${row.name}`, async () => {
    const e = env();
    await row.setup(e);
    const result = await resolveTrial(
      e,
      PRODUCT,
      row.device || DEVICE_A,
      row.machines || [MACHINE_A],
      { today: row.today },
    );
    assert.equal(result.kind, row.expect.kind);
    if (row.expect.reason) assert.equal(result.reason, row.expect.reason);
    if (row.expect.first_day) assert.equal(result.first_day, row.expect.first_day);
    if (row.expect.last_day) assert.equal(result.last_day, row.expect.last_day);
    if (row.expect.active !== undefined) assert.equal(result.active, row.expect.active);
    if (row.expect.blocked_by) assert.equal(result.blocked_by, row.expect.blocked_by);
  });
}

test('regression: 64 expired rows still find issued permanent', async () => {
  const e = env();
  for (let i = 0; i < 64; i++) {
    await insertRequest(e, {
      id: `exp-${i}`, status: 'expired', tier: 'trial', expiry: '2020-01-01',
      machine: MACHINE_A, dkey: DKEY_A,
    });
  }
  await insertRequest(e, {
    id: 'perm-win', status: 'issued', kind: 'permanent', tier: 'permanent', expiry: '',
    machine: MACHINE_A, dkey: DKEY_A,
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(r.kind, 'blocked');
  assert.equal(r.reason, 'downgrade_forbidden');
});

test('regression: 65 devices on one machine still see device-only grant', async () => {
  const e = env();
  const orphanDevice = 'ZBAA2-AAAAA';
  const orphanKey = deviceKey(orphanDevice);
  const sharedMachine = 'c'.repeat(64);
  for (let i = 0; i < 65; i++) {
    const code = `DEV${String(i).padStart(2, '0')}-AAAAA`;
    const dk = deviceKey(code);
    await insertRequest(e, {
      id: `many-${i}`, device: code, dkey: dk, machine: sharedMachine, expiry: '2026-01-01',
    });
  }
  const { first, last } = trialWindow('2026-09-01');
  await e.DB.prepare(
    `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at)
     VALUES(?, 'd', ?, ?, ?, '2026-01-01')`,
  ).bind(PRODUCT, orphanKey, first, last).run();
  await insertRequest(e, {
    id: 'orphan', device: orphanDevice, dkey: orphanKey, machine: sharedMachine, expiry: '2026-01-01',
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [sharedMachine], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, last);
});

test('regression: two-hop A-M1-B-M2-C grant on C only', async () => {
  const e = env();
  await insertRequest(e, { id: 'a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_M1 });
  await insertRequest(e, { id: 'b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M1 });
  await insertRequest(e, { id: 'b2', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M2 });
  await insertRequest(e, { id: 'c', device: DEVICE_C, dkey: DKEY_C, machine: MACHINE_M2 });
  const win = trialWindow('2026-10-01');
  await e.DB.batch(trialGrantStatements(e, PRODUCT, DEVICE_C, [], win, 'c'));
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_M1], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, win.last);
});

test('regression: overwritten trial backfills from kind=trial paid replace', async () => {
  const e = env();
  const { last } = trialWindow('2025-01-01');
  await insertRequest(e, {
    id: 'replaced', kind: 'trial', tier: 'paid', expiry: '2025-01-01', status: 'delivered',
  });
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(deviceLockKey(DKEY_A), 'replaced', 1).run();
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(machineLockKey(MACHINE_A), 'replaced', 1).run();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
     VALUES('cp', ?, '', ?, 'paid', '2025-01-01', '2025-01-01', 'paid', 1)`,
  ).bind(PRODUCT, DEVICE_A).run();
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.ok(n >= 1);
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.active, false);
});

test('backfill skips bad device rows', async () => {
  const e = env();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
     VALUES('bad', ?, '', '!!!', 'trial', '2026-01-01', '2026-01-14', 'trial', 1)`,
  ).bind(PRODUCT).run();
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.equal(n, 0);
});

test('resolveTrial query count stays under 50 for large linkage', async () => {
  const base = env();
  const shared = 'd'.repeat(64);
  for (let i = 0; i < 20; i++) {
    const code = `MCH${String(i).padStart(2, '0')}-AAAAA`;
    await insertRequest(base, { id: `m-${i}`, device: code, dkey: deviceKey(code), machine: shared });
  }
  for (let i = 0; i < 60; i++) {
    await base.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
      .bind(`lock-${i}`, `m-${i % 20}`, i).run();
  }
  const { e, queryCount } = countingEnv();
  e.DB = base.DB;
  await resolveTrial(e, PRODUCT, 'MCH00-AAAAA', [shared], { today: '2026-03-01' });
  assert.ok(queryCount() < 50, `queries=${queryCount()}`);
});

test('backfill query count under 50 for 60 locks and 20 machines', async () => {
  const base = env();
  const shared = 'e'.repeat(64);
  for (let i = 0; i < 60; i++) {
    const code = `7KD${String(i).padStart(2, '0')}-QX9TP`;
    await insertRequest(base, {
      id: `bf-${i}`, device: code, dkey: deviceKey(code), machine: shared, expiry: '2026-06-01',
    });
    await base.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
      .bind(deviceLockKey(deviceKey(code)), `bf-${i}`, i).run();
  }
  const { e, queryCount } = countingEnv();
  e.DB = base.DB;
  await backfillTrialGrants(e, PRODUCT);
  assert.ok(queryCount() < 50, `queries=${queryCount()}`);
});

test('apply-migrations creates triggers when trial_grants table pre-exists', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(join(root, 'schema.sql'), 'utf8'));
  db.exec('DROP TRIGGER IF EXISTS trial_grants_no_update');
  db.exec('DROP TRIGGER IF EXISTS trial_grants_no_delete');
  db.prepare('DELETE FROM schema_migrations WHERE id = ?').run('0004_trial_grants');
  applyMigrations(db);
  const tr = db.prepare(
    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'trial_grants_%'",
  ).all();
  assert.equal(tr.length, 2);
});

test('backfill picks earliest window and is idempotent', async () => {
  const e = env();
  const early = trialWindow('2026-03-01');
  const late = trialWindow('2026-09-01');
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(`etw|${PRODUCT}|d|${DKEY_A}`, `${late.first}|${late.last}`, 1).run();
  await insertRequest(e, { id: 'req-early', expiry: early.last });
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(deviceLockKey(DKEY_A), 'req-early', 2).run();
  const n1 = await backfillTrialGrants(e, PRODUCT);
  assert.ok(n1 >= 1);
  const row1 = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_A).first();
  assert.equal(row1.first_day, early.first);
  const n2 = await backfillTrialGrants(e, PRODUCT);
  assert.ok(n2 >= 1);
  const dCount = await e.DB.prepare(
    'SELECT COUNT(*) AS n FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_A).first();
  assert.equal(dCount.n, 1);
});

test('linkedSubjects merges machines across devices', async () => {
  const e = env();
  await insertRequest(e, { id: 'a1', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'b1', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  const linked = await linkedSubjects(e, PRODUCT, DEVICE_A, [MACHINE_A_UPPER]);
  assert.ok(linked.devices.includes(DKEY_A));
  assert.ok(linked.devices.includes(DKEY_B));
  assert.ok(linked.machines.includes(MACHINE_A));
});

test('isActiveStrongTerm treats paid_until equal to today as active', () => {
  const e = env();
  assert.equal(isActiveStrongTerm({ tier: 'paid', until: '2026-03-15' }, e, '2026-03-15'), true);
  assert.equal(isActiveStrongTerm({ tier: 'paid', until: '2026-03-14' }, e, '2026-03-15'), false);
});

test('empty expiry on paid row does not block', async () => {
  const e = env();
  await insertRequest(e, {
    id: 'paid-empty', tier: 'paid', kind: 'monthly', expiry: '', status: 'delivered',
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(r.kind, 'eligible');
});
