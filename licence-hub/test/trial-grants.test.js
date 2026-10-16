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
import { assertD1CompoundSelectCap, maxCompoundSelectTerms } from './sql-limits.js';

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

function sqlCaptureEnv(innerDb, over = {}) {
  const captured = [];
  const inner = innerDb || newD1();
  const DB = {
    prepare(sql) {
      captured.push(sql);
      const stmt = inner.prepare(sql);
      return {
        bind(...args) {
          return stmt.bind(...args);
        },
      };
    },
    batch: (stmts) => inner.batch(stmts),
  };
  return {
    e: { DB, TRIAL_DAYS: '14', LICENCE_CALENDAR_TZ: 'Africa/Cairo', ...over },
    sql: captured,
  };
}

function countingEnv(innerDb, over = {}) {
  let queries = 0;
  const inner = innerDb || newD1();
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
  reason = null,
}) {
  await e.DB.prepare(
    `INSERT INTO licence_requests(
      id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, licence_tier, licence_expiry, reason, created_at, updated_at
    ) VALUES(?, 'h', ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, ?, ?, ?, ?)`,
  ).bind(id, product, kind, device, dkey, machine, 'n-' + id, status, tier, expiry, reason ?? '', created_at, created_at).run();
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
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], win1, 'req-1'));
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], win2, 'req-2')),
    /NOT NULL constraint failed/i,
  );
  const row = await e.DB.prepare(
    'SELECT first_day, last_day, source_request FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_A).first();
  assert.equal(row.first_day, '2026-01-01');
  assert.equal(row.last_day, '2026-01-14');
  assert.equal(row.source_request, 'req-1');
});

test('trial_grants rejects update and delete', async () => {
  const e = env();
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [], { first_day: '2026-01-01', last_day: '2026-01-14' }, null));
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
const rowStatuses = ['issued', 'delivered', 'expired', 'expired_pending_timeout', 'pending', 'refused'];
const paidStates = ['none', 'active_paid', 'expired_paid', 'active_permanent', 'pending_permanent', 'refused_permanent'];
const linkShapes = ['same', 'peer', 'two_hop'];

function machineForHash(machine, hashCase) {
  return hashCase === 'upper' ? machine.toUpperCase() : machine;
}

function deviceForHash(device, hashCase) {
  return hashCase === 'upper' ? device.toUpperCase() : device.toLowerCase();
}

function priorTarget(linkShape, hashCase) {
  if (linkShape === 'peer') {
    return {
      device: DEVICE_B,
      dkey: DKEY_B,
      machine: machineForHash(MACHINE_A, hashCase),
    };
  }
  if (linkShape === 'two_hop') {
    return {
      device: DEVICE_C,
      dkey: DKEY_C,
      machine: machineForHash(MACHINE_M2, hashCase),
    };
  }
  return {
    device: DEVICE_A,
    dkey: DKEY_A,
    machine: machineForHash(MACHINE_A, hashCase),
  };
}

function priorSetup(source, e, rowStatus, linkShape, hashCase, lastDay = '2026-06-20') {
  const { first, last } = trialWindow(lastDay);
  const target = priorTarget(linkShape, hashCase);
  const timeoutExpired = rowStatus === 'expired_pending_timeout';
  const status = timeoutExpired ? 'expired' : rowStatus;
  const expiry = timeoutExpired ? null : last;
  const extra = timeoutExpired ? { tier: '', kind: 'trial', reason: 'pending_timeout' } : {};
  switch (source) {
    case 'etw_d':
      return e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|d|${deviceForHash(target.device, hashCase)}`, `${first}|${last}`, 1).run()
        .then(() => backfillTrialGrants(e, PRODUCT));
    case 'etw_m':
      return e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|m|${target.machine.toLowerCase()}`, `${first}|${last}`, 1).run()
        .then(() => backfillTrialGrants(e, PRODUCT))
        .then(() => insertRequest(e, {
          id: 'etw-m-anchor',
          device: target.device,
          dkey: target.dkey,
          machine: target.machine,
          status,
          expiry,
          ...extra,
        }));
    case 'lock':
      return insertRequest(e, {
        id: 'lk',
        device: target.device,
        dkey: target.dkey,
        machine: target.machine,
        expiry,
        status,
        ...extra,
      }).then(() =>
        e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
          .bind(machineLockKey(target.machine.toLowerCase()), 'lk', 1).run(),
      ).then(() => backfillTrialGrants(e, PRODUCT));
    case 'request':
      return insertRequest(e, {
        id: 'rq',
        device: target.device,
        dkey: target.dkey,
        machine: target.machine,
        expiry,
        status,
        ...extra,
      }).then(() => backfillTrialGrants(e, PRODUCT));
    case 'customer':
      return e.DB.prepare(
        `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
         VALUES(?, ?, '', ?, 'trial', ?, ?, 'trial', 1)`,
      ).bind('c-mx', PRODUCT, deviceForHash(target.device, hashCase), first, last).run().then(() => backfillTrialGrants(e, PRODUCT));
    default:
      return Promise.resolve();
  }
}

async function linkBridge(e, linkShape) {
  const bridgeReq = {
    kind: 'monthly',
    tier: 'paid',
    expiry: '2020-01-01',
    status: 'delivered',
  };
  if (linkShape === 'peer') {
    await insertRequest(e, { id: 'bridge-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A, ...bridgeReq });
    await insertRequest(e, { id: 'bridge-b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A, ...bridgeReq });
  }
  if (linkShape === 'two_hop') {
    await insertRequest(e, { id: 'hop-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_M1, ...bridgeReq });
    await insertRequest(e, { id: 'hop-b1', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M1, ...bridgeReq });
    await insertRequest(e, { id: 'hop-b2', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_M2, ...bridgeReq });
    await insertRequest(e, { id: 'hop-c', device: DEVICE_C, dkey: DKEY_C, machine: MACHINE_M2, ...bridgeReq });
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
          if (['etw_d', 'etw_m', 'customer'].includes(prior) && rowStatus !== 'delivered') continue;
          const blocks = ['active_paid', 'active_permanent'].includes(paidState);
          const pendingNoBlock = ['pending_permanent', 'refused_permanent'].includes(paidState);
          const matrixLastDay = '2026-06-20';
          const matrixWin = trialWindow(matrixLastDay);
          const expectExisting = ['etw_d', 'etw_m', 'customer'].includes(prior)
            || (['lock', 'request'].includes(prior)
              && ['issued', 'delivered', 'expired', 'refused', 'approved'].includes(rowStatus));
          if (rowStatus === 'expired_pending_timeout') {
            assert.ok(!expectExisting);
          }
          test(`matrix: prior=${prior} hash=${hashCase} status=${rowStatus} paid=${paidState} link=${linkShape}`, async () => {
            const e = env();
            await linkBridge(e, linkShape);
            await priorSetup(prior, e, rowStatus, linkShape, hashCase);
            await paidSetup(e, paidState, linkShape);
            const resolveMachines = linkShape === 'same'
              ? [machineForHash(MACHINE_A, hashCase)]
              : (linkShape === 'peer' ? [] : [machineForHash(MACHINE_M1, hashCase)]);
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
            assert.equal(result.first_day, matrixWin.first);
            assert.equal(result.last_day, matrixWin.last);
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
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_C, [], win, 'c'));
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_M1], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, win.last);
});

test('regression: paid-only rows with locks produce zero ledger rows', async () => {
  const e = env();
  await insertRequest(e, {
    id: 'replaced',
    kind: 'monthly',
    tier: 'paid',
    expiry: '2025-01-01',
    status: 'delivered',
    created_at: 1_700_000_000,
  });
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(deviceLockKey(DKEY_A), 'replaced', 1).run();
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(machineLockKey(MACHINE_A), 'replaced', 1).run();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('cp', ?, '', ?, 'paid', '2025-01-01', '2025-01-01', 'paid', '2025-01-01', 1)`,
  ).bind(PRODUCT, DEVICE_A).run();
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.equal(n, 0);
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(r.kind, 'eligible');
});

test('regression: active paid blocks trial; eligible after paid expiry', async () => {
  const e = env();
  await insertRequest(e, {
    id: 'paid-active',
    kind: 'monthly',
    tier: 'paid',
    expiry: '2026-12-31',
    status: 'delivered',
  });
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(deviceLockKey(DKEY_A), 'paid-active', 1).run();
  await backfillTrialGrants(e, PRODUCT);
  const blocked = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-12-31' });
  assert.equal(blocked.kind, 'blocked');
  assert.equal(blocked.reason, 'downgrade_forbidden');
  const after = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2027-01-01' });
  assert.equal(after.kind, 'eligible');
});

test('regression: pending_timeout expired request does not backfill or resolve as trial', async () => {
  const e = env();
  const created = Math.floor(Date.parse('2026-03-01T12:00:00Z') / 1000);
  await e.DB.prepare(
    `INSERT INTO licence_requests(
      id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, licence_tier, licence_expiry, reason, created_at, updated_at
    ) VALUES(?, 'h', ?, 'trial', ?, ?, ?, ?, '', '', '', 'expired', '', NULL, 'pending_timeout', ?, ?)`,
  ).bind('to', PRODUCT, DEVICE_A, DKEY_A, MACHINE_A, 'n-to', created, created).run();
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.equal(n, 0);
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(r.kind, 'eligible');
});

test('regression: etw grants with same window do not link unrelated devices', async () => {
  const e = env();
  const win = trialWindow('2026-01-01');
  const etwKey = `${win.first}|${win.last}`;
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(`etw|${PRODUCT}|d|${DKEY_A}`, etwKey, 1).run();
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(`etw|${PRODUCT}|d|${DKEY_B}`, etwKey, 1).run();
  await backfillTrialGrants(e, PRODUCT);
  await insertRequest(e, {
    id: 'perm-b',
    device: DEVICE_B,
    dkey: DKEY_B,
    machine: MACHINE_B,
    kind: 'permanent',
    tier: 'permanent',
    expiry: '',
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.blocked_by, null);
});

test('regression: D1 bind cap chunks earliestLedgerWindow (99 devices)', async () => {
  const sharedMachine = 'f'.repeat(64);
  let queries = 0;
  const inner = newD1();
  const DB = {
    prepare(sql) {
      const stmt = inner.prepare(sql);
      return {
        bind(...args) {
          if (args.length > 100) {
            throw new Error(`bind_limit_exceeded:${args.length}`);
          }
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
  const e = { DB, TRIAL_DAYS: '14', LICENCE_CALENDAR_TZ: 'Africa/Cairo' };
  for (let i = 0; i < 99; i++) {
    const code = `D99${String(i).padStart(2, '0')}-AAAAA`;
    const dk = deviceKey(code);
    await insertRequest(e, {
      id: `cap-${i}`,
      device: code,
      dkey: dk,
      machine: sharedMachine,
      expiry: '2026-01-01',
    });
  }
  const { first, last } = trialWindow('2026-09-01');
  await e.DB.prepare(
    `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at)
     VALUES(?, 'd', ?, ?, ?, '2026-01-01')`,
  ).bind(PRODUCT, DKEY_A, first, last).run();
  await insertRequest(e, {
    id: 'cap-anchor',
    device: DEVICE_A,
    dkey: DKEY_A,
    machine: sharedMachine,
    expiry: '2026-01-01',
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [sharedMachine], { today: '2026-03-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, last);
  assert.ok(queries > 1);
});

test('regression: closure chunks 99 machine seeds under bind cap; paid peer blocks', async () => {
  const inner = newD1();
  const DB = {
    prepare(sql) {
      const stmt = inner.prepare(sql);
      return {
        bind(...args) {
          if (args.length > 100) {
            throw new Error(`bind_limit_exceeded:${args.length}`);
          }
          return stmt.bind(...args);
        },
      };
    },
    batch: (stmts) => inner.batch(stmts),
  };
  const e = { DB, TRIAL_DAYS: '14', LICENCE_CALENDAR_TZ: 'Africa/Cairo' };
  const machines = [];
  for (let i = 0; i < 99; i++) {
    const mh = String(i).padStart(64, 'a');
    machines.push(mh);
    await insertRequest(e, {
      id: `seed-${i}`,
      device: DEVICE_A,
      dkey: DKEY_A,
      machine: mh,
      kind: 'trial',
      tier: 'trial',
      expiry: '2026-06-14',
      status: 'delivered',
    });
  }
  await insertRequest(e, {
    id: 'paid-peer',
    device: DEVICE_B,
    dkey: DKEY_B,
    machine: machines[90],
    kind: 'monthly',
    tier: 'paid',
    expiry: '2026-12-31',
    status: 'delivered',
  });
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, machines, { today: '2026-06-01' });
  assert.equal(r.kind, 'blocked');
  assert.equal(r.reason, 'downgrade_forbidden');
});

test('customer blank licence_expiry falls back to last_day for paid block like NULL', async () => {
  const e = env();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('ce', ?, '', ?, 'paid', '2025-01-01', '2026-12-31', 'paid', '', 1)`,
  ).bind(PRODUCT, DEVICE_A).run();
  const blocked = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(blocked.kind, 'blocked');
  assert.equal(blocked.reason, 'downgrade_forbidden');
  await e.DB.prepare('UPDATE customers SET licence_expiry = NULL WHERE id = ?').bind('ce').run();
  const stillBlocked = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(stillBlocked.kind, 'blocked');
  assert.equal(stillBlocked.reason, 'downgrade_forbidden');
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
  const { e, queryCount } = countingEnv(base.DB);
  await resolveTrial(e, PRODUCT, 'MCH00-AAAAA', [shared], { today: '2026-03-01' });
  const q = queryCount();
  assert.ok(q > 0, `queries=${q}`);
  assert.ok(q < 50, `queries=${q}`);
});

test('backfill query count under 50 for 40 trial requests on shared machine', async () => {
  const base = env();
  const shared = 'e'.repeat(64);
  for (let i = 0; i < 40; i++) {
    const code = `7KD${String(i).padStart(2, '0')}-QX9TP`;
    await insertRequest(base, {
      id: `bf-${i}`, device: code, dkey: deviceKey(code), machine: shared, expiry: '2026-06-01',
    });
  }
  const { e, queryCount } = countingEnv(base.DB);
  await backfillTrialGrants(e, PRODUCT);
  const q = queryCount();
  assert.ok(q > 0, `queries=${q}`);
  assert.ok(q < 50, `queries=${q}`);
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
  assert.ok(Array.isArray(linked.deviceCodes));
  assert.equal(linked.link_limit, false);
  assert.ok(linked.deviceCodes.includes(DEVICE_B));
});

test('linkedSubjects fails closed when closure query budget is exceeded', async () => {
  const e = env();
  const machines = [];
  for (let i = 0; i < 4351; i++) {
    machines.push(i.toString(16).padStart(64, '0'));
  }
  const linked = await linkedSubjects(e, PRODUCT, DEVICE_A, machines);
  assert.equal(linked.link_limit, true);
  assert.ok(Array.isArray(linked.deviceCodes));
  assert.equal(linked.deviceCodes.length, 0);
  assert.equal(linked.devices.length, 0);
});

test('permanent customer with spaced device blocks hyphenated resolveTrial', async () => {
  const e = env();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('perm-sp', ?, '', ?, 'permanent', '2025-01-01', '', 'permanent', '', 1)`,
  ).bind(PRODUCT, '7KD2M QX9TP').run();
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [], { today: '2026-03-01' });
  assert.equal(r.kind, 'blocked');
  assert.equal(r.reason, 'downgrade_forbidden');
});

test('trial customer with spaced device is found by backfill and linkedSubjects', async () => {
  const e = env();
  const win = trialWindow('2026-04-01');
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
     VALUES('trial-sp', ?, '', ?, 'trial', ?, ?, 'trial', 1)`,
  ).bind(PRODUCT, '7KD2M QX9TP', win.first, win.last).run();
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.ok(n >= 1);
  const linked = await linkedSubjects(e, PRODUCT, DEVICE_A, []);
  assert.ok(linked.deviceCodes.some((c) => c.replace(/[\s-]/g, '').toUpperCase() === '7KD2MQX9TP'));
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [], { today: '2026-03-15' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, win.last);
});

test('backfill paging and insert batches match single-pass ledger', async () => {
  const e = env();
  const win = trialWindow('2026-05-01');
  for (let i = 0; i < 5; i++) {
    const code = `7KD${String(i).padStart(2, '0')}-QX9TP`;
    await insertRequest(e, {
      id: `page-req-${i}`,
      device: code,
      dkey: deviceKey(code),
      machine: MACHINE_A,
      expiry: win.last,
    });
  }
  const full = await backfillTrialGrants(e, PRODUCT);
  const fullRows = await e.DB.prepare(
    'SELECT subject_kind, subject, first_day, last_day FROM trial_grants ORDER BY subject_kind, subject',
  ).bind().all();
  const e2 = env();
  for (let i = 0; i < 5; i++) {
    const code = `7KD${String(i).padStart(2, '0')}-QX9TP`;
    await insertRequest(e2, {
      id: `page-req-${i}`,
      device: code,
      dkey: deviceKey(code),
      machine: MACHINE_A,
      expiry: win.last,
    });
  }
  const paged = await backfillTrialGrants(e2, PRODUCT, { pageSize: 2, insertBatchSize: 2 });
  assert.equal(paged, full);
  const pagedRows = await e2.DB.prepare(
    'SELECT subject_kind, subject, first_day, last_day FROM trial_grants ORDER BY subject_kind, subject',
  ).bind().all();
  assert.deepEqual(pagedRows.results, fullRows.results);
});

test('backfill includes refused and approved rows with issued trial evidence', async () => {
  const e = env();
  const win = trialWindow('2026-06-01');
  await insertRequest(e, {
    id: 'refused-trial',
    device: DEVICE_B,
    dkey: DKEY_B,
    machine: MACHINE_B,
    status: 'refused',
    tier: 'trial',
    kind: 'trial',
    expiry: win.last,
  });
  await insertRequest(e, {
    id: 'approved-trial',
    device: DEVICE_C,
    dkey: DKEY_C,
    machine: MACHINE_B,
    status: 'approved',
    tier: 'trial',
    kind: 'trial',
    expiry: win.last,
  });
  await insertRequest(e, {
    id: 'refused-perm',
    device: DEVICE_A,
    dkey: DKEY_A,
    machine: MACHINE_A,
    status: 'refused',
    tier: 'permanent',
    kind: 'permanent',
    expiry: '',
  });
  await insertRequest(e, {
    id: 'pending-trial',
    device: 'ZBAA2-AAAAA',
    dkey: deviceKey('ZBAA2-AAAAA'),
    machine: MACHINE_A,
    status: 'pending',
    tier: 'trial',
    kind: 'trial',
    expiry: win.last,
  });
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.ok(n >= 2);
  const bRow = await e.DB.prepare(
    'SELECT last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bRow.last_day, win.last);
  const cRow = await e.DB.prepare(
    'SELECT last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_C).first();
  assert.equal(cRow.last_day, win.last);
});

test('etw d subject with hyphenated device code normalizes on backfill', async () => {
  const e = env();
  const { first, last } = trialWindow('2026-01-14');
  await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
    .bind(`etw|${PRODUCT}|d|${DEVICE_A}`, `${first}|${last}`, 1).run();
  await backfillTrialGrants(e, PRODUCT);
  const r = await resolveTrial(e, PRODUCT, DEVICE_A, [], { today: '2026-01-10' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.last_day, last);
});

test('delivered kind trial with paid tier is not trial backfill evidence', async () => {
  const e = env();
  await insertRequest(e, {
    id: 'trial-kind-paid-tier',
    kind: 'trial',
    tier: 'paid',
    expiry: '2026-12-31',
    status: 'delivered',
  });
  const n = await backfillTrialGrants(e, PRODUCT);
  assert.equal(n, 0);
  const rows = await e.DB.prepare('SELECT COUNT(*) AS n FROM trial_grants').bind().first();
  assert.equal(rows.n, 0);
});

test('second device grant does not store a different window when machine row exists', async () => {
  const e = env();
  await insertRequest(e, { id: 'ga', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'gb', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  const win1 = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const win2 = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], win1, 'req-a'));
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], win2, 'req-b')),
    /NOT NULL constraint failed/i,
  );
  const bRow = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bRow.first_day, '2026-06-01');
  assert.equal(bRow.last_day, '2026-06-14');
  const mRow = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('m', MACHINE_A).first();
  assert.equal(mRow.first_day, '2026-06-01');
  assert.equal(mRow.last_day, '2026-06-14');
});

test('regression: window guard rolls back July grant; re-grant propagates June to all subjects', async () => {
  const e = env();
  await insertRequest(e, { id: 'ga', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'gb', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  await insertRequest(e, { id: 'gc', device: DEVICE_C, dkey: DKEY_C, machine: MACHINE_B });
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'req-a'));
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A, MACHINE_B], winJuly, 'req-b')),
    /NOT NULL constraint failed/i,
  );
  const bDevice = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bDevice.first_day, winJune.first_day);
  assert.equal(bDevice.last_day, winJune.last_day);
  const julyB = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('m', MACHINE_B).first();
  assert.equal(julyB, null);
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A, MACHINE_B], winJune, 'req-b2'));
  for (const subj of [
    ['d', DKEY_B],
    ['m', MACHINE_A],
    ['m', MACHINE_B],
  ]) {
    const row = await e.DB.prepare(
      'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
    ).bind(...subj).first();
    assert.equal(row.first_day, winJune.first_day);
    assert.equal(row.last_day, winJune.last_day);
  }
  const r = await resolveTrial(e, PRODUCT, DEVICE_C, [MACHINE_B], { today: '2026-07-01' });
  assert.equal(r.kind, 'existing');
  assert.equal(r.first_day, winJune.first_day);
});

test('regression: device-only grant then device+hash grant propagates machine row with device window', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [], winJune, 'dev-only'));
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJuly, 'bad-window')),
    /NOT NULL constraint failed/i,
  );
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'with-hash'));
  const mRow = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('m', MACHINE_A).first();
  assert.equal(mRow.first_day, winJune.first_day);
  assert.equal(mRow.last_day, winJune.last_day);
});

test('regression: window guard failure rolls back following batch statements', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'anchor'));
  const grantStmts = await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJuly, 'mismatch');
  const tail = e.DB.prepare(
    `INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, licence_tier, licence_expiry, reason, created_at, updated_at)
     VALUES('tail', 'h', ?, 'trial', ?, ?, ?, 'n', '', '', '', 'delivered', 'trial', '2026-07-14', '', 1, 1)`,
  ).bind(PRODUCT, DEVICE_B, DKEY_B, MACHINE_A);
  await assert.rejects(
    () => e.DB.batch([...grantStmts, tail]),
    /NOT NULL constraint failed/i,
  );
  const tailRow = await e.DB.prepare('SELECT id FROM licence_requests WHERE id = ?').bind('tail').first();
  assert.equal(tailRow, null);
  const bDev = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bDev, null);
});

test('regression: paid customer blocks resolveTrial with lowercase device code', async () => {
  const e = env();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('paid-lo', ?, '', ?, 'paid', '2025-01-01', '2026-12-31', 'paid', '2026-12-31', 1)`,
  ).bind(PRODUCT, DEVICE_A).run();
  await insertRequest(e, {
    id: 'delivered-lo',
    device: '7kd2m-qx9tp',
    dkey: DKEY_A,
    machine: MACHINE_A,
    status: 'delivered',
    tier: 'trial',
    kind: 'trial',
    expiry: '2026-06-14',
  });
  const blocked = await resolveTrial(e, PRODUCT, '7kd2m-qx9tp', [MACHINE_A], { today: '2026-06-01' });
  assert.equal(blocked.kind, 'blocked');
  assert.equal(blocked.reason, 'downgrade_forbidden');
});

test('trialGrantStatements fails closed when closure ledger lookup exceeds query budget (link_limit)', async () => {
  const e = env();
  const hashes = [];
  for (let i = 0; i < 4200; i++) {
    hashes.push(String(i).padStart(64, 'f'));
  }
  const win = { first_day: '2026-06-01', last_day: '2026-06-14' };
  await assert.rejects(
    () => trialGrantStatements(e, PRODUCT, DEVICE_A, hashes, win, 'big'),
    /link_limit/,
  );
});

test('regression probe A: July grant on linked closure refused; June retry propagates', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [], winJune, 'dev-june'));
  await insertRequest(e, { id: 'link-b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  await insertRequest(e, { id: 'link-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  const resolved = await resolveTrial(e, PRODUCT, DEVICE_B, [MACHINE_B], { today: '2026-07-01' });
  assert.equal(resolved.kind, 'existing');
  assert.equal(resolved.first_day, winJune.first_day);
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_B], winJuly, 'july-b')),
    /NOT NULL constraint failed/i,
  );
  const julyB = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('m', MACHINE_B).first();
  assert.equal(julyB, null);
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_B], winJune, 'june-b'));
  for (const subj of [['d', DKEY_B], ['m', MACHINE_B]]) {
    const row = await e.DB.prepare(
      'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
    ).bind(...subj).first();
    assert.equal(row.first_day, winJune.first_day);
    assert.equal(row.last_day, winJune.last_day);
  }
});

test('regression probe: stale July batch aborts when June commits before batch (live guard)', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await insertRequest(e, { id: 'race-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'race-b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  const julyStmts = await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJuly, 'july-stale');
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'june-race'));
  await assert.rejects(
    () => e.DB.batch(julyStmts),
    /NOT NULL constraint failed/i,
  );
  const julyB = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ? AND first_day = ?',
  ).bind('d', DKEY_B, winJuly.first_day).first();
  assert.equal(julyB, null);
  const julyM = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ? AND first_day = ?',
  ).bind('m', MACHINE_A, winJuly.first_day).first();
  assert.equal(julyM, null);
  const bJune = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bJune?.first_day, winJune.first_day);
});

test('regression probe: stale batch succeeds when concurrent commit matches requested window', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  await insertRequest(e, { id: 'same-a', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'same-b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  const grantStmts = await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJune, 'b-pending');
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'a-first'));
  await e.DB.batch(grantStmts);
  const bRow = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bRow.first_day, winJune.first_day);
  assert.equal(bRow.last_day, winJune.last_day);
});

test('regression probe: stale June batch succeeds when concurrent commit adds later window only', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winAugust = { first_day: '2026-08-01', last_day: '2026-08-14' };
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('trial-a', ?, '', ?, 'trial', ?, ?, 'trial', ?, 1)`,
  ).bind(PRODUCT, DEVICE_A, winJune.first_day, winJune.last_day, winJune.last_day).run();
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [], winJune, 'cust-a'));
  await insertRequest(e, { id: 'late-b', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  await insertRequest(e, { id: 'link-ab', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  const juneStmts = await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJune, 'june-pending');
  await e.DB.prepare(
    `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
     VALUES (?, 'd', ?, ?, ?, '1970-01-01T00:00:00.000Z', 'aug-concurrent')`,
  ).bind(PRODUCT, DKEY_B, winAugust.first_day, winAugust.last_day).run();
  await e.DB.batch(juneStmts);
  const mJune = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('m', MACHINE_A).first();
  assert.equal(mJune.first_day, winJune.first_day);
  assert.equal(mJune.last_day, winJune.last_day);
  const bAugust = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bAugust.first_day, winAugust.first_day);
});

test('regression probe B: June grant converges across mixed closure windows', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winAugust = { first_day: '2026-08-01', last_day: '2026-08-14' };
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('trial-a', ?, '', ?, 'trial', ?, ?, 'trial', ?, 1)`,
  ).bind(PRODUCT, DEVICE_A, winJune.first_day, winJune.last_day, winJune.last_day).run();
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [], winJune, 'cust-a'));
  await insertRequest(e, {
    id: 'del-b',
    device: DEVICE_B,
    dkey: DKEY_B,
    machine: MACHINE_A,
    expiry: winAugust.last_day,
  });
  await e.DB.prepare(
    `INSERT INTO trial_grants(product, subject_kind, subject, first_day, last_day, created_at, source_request)
     VALUES (?, 'd', ?, ?, ?, '1970-01-01T00:00:00.000Z', 'aug-b'),
            (?, 'm', ?, ?, ?, '1970-01-01T00:00:00.000Z', 'aug-b')`,
  ).bind(PRODUCT, DKEY_B, winAugust.first_day, winAugust.last_day, PRODUCT, MACHINE_A, winAugust.first_day, winAugust.last_day).run();
  await insertRequest(e, { id: 'link-ab', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'link-bc', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B });
  await insertRequest(e, { id: 'link-c', device: DEVICE_C, dkey: DKEY_C, machine: MACHINE_B });
  const resolved = await resolveTrial(e, PRODUCT, DEVICE_B, [MACHINE_A], { today: '2026-07-01' });
  assert.equal(resolved.kind, 'existing');
  assert.equal(resolved.first_day, winJune.first_day);
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJune, 'sync-june'));
  for (const subj of [['d', DKEY_C], ['m', MACHINE_B]]) {
    const row = await e.DB.prepare(
      'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
    ).bind(...subj).first();
    assert.equal(row.first_day, winJune.first_day);
    assert.equal(row.last_day, winJune.last_day);
  }
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_B, [MACHINE_A], winJune, 'sync-june-retry'));
  const after = await resolveTrial(e, PRODUCT, DEVICE_C, [MACHINE_B], { today: '2026-07-01' });
  assert.equal(after.kind, 'existing');
  assert.equal(after.first_day, winJune.first_day);
  assert.notEqual(after.kind, 'eligible');
});

test('resolve then grant with resolved window converges in one retry', async () => {
  const e = env();
  const winJune = { first_day: '2026-06-01', last_day: '2026-06-14' };
  const winJuly = { first_day: '2026-07-01', last_day: '2026-07-14' };
  await insertRequest(e, { id: 'ga', device: DEVICE_A, dkey: DKEY_A, machine: MACHINE_A });
  await insertRequest(e, { id: 'gb', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A });
  await e.DB.batch(await trialGrantStatements(e, PRODUCT, DEVICE_A, [MACHINE_A], winJune, 'anchor'));
  const first = await resolveTrial(e, PRODUCT, DEVICE_B, [MACHINE_A], { today: '2026-07-01' });
  assert.equal(first.kind, 'existing');
  await assert.rejects(
    async () => e.DB.batch(await trialGrantStatements(
      e, PRODUCT, DEVICE_B, [MACHINE_A], winJuly, 'wrong',
    )),
    /NOT NULL constraint failed/i,
  );
  const retry = await resolveTrial(e, PRODUCT, DEVICE_B, [MACHINE_A], { today: '2026-07-01' });
  assert.equal(retry.first_day, first.first_day);
  await e.DB.batch(await trialGrantStatements(
    e, PRODUCT, DEVICE_B, [MACHINE_A],
    { first_day: retry.first_day, last_day: retry.last_day },
    'retry',
  ));
  const bRow = await e.DB.prepare(
    'SELECT first_day, last_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_B).first();
  assert.equal(bRow.first_day, winJune.first_day);
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

test('closure SQL stays within D1 compound SELECT cap for 99 machine seeds', async () => {
  const base = env();
  const machines = [];
  for (let i = 0; i < 99; i++) {
    machines.push(String(i).padStart(64, 'a'));
    await insertRequest(base, {
      id: `cmp-${i}`,
      device: DEVICE_A,
      dkey: DKEY_A,
      machine: machines[i],
      expiry: '2026-06-14',
    });
  }
  const { e, sql } = sqlCaptureEnv(base.DB);
  await resolveTrial(e, PRODUCT, DEVICE_A, machines, { today: '2026-06-01' });
  const closureSqls = sql.filter((s) => s.includes('WITH RECURSIVE') && s.includes('seeds(kind, id)'));
  assert.ok(closureSqls.length >= 1);
  for (const stmt of closureSqls) {
    assertD1CompoundSelectCap(stmt);
    assert.ok(maxCompoundSelectTerms(stmt) <= 5);
  }
});

for (const nDevices of [5, 6, 12, 50, 99]) {
  test(`resolveTrial with device and ${nDevices} machine seeds respects compound SELECT cap`, async () => {
    const base = env();
    const machines = [];
    for (let i = 0; i < nDevices; i++) {
      machines.push(String(i + 1).padStart(64, 'b'));
      await insertRequest(base, {
        id: `dev-${nDevices}-${i}`,
        device: DEVICE_A,
        dkey: DKEY_A,
        machine: machines[i],
        expiry: '2026-06-14',
      });
    }
    const { e, sql } = sqlCaptureEnv(base.DB);
    await resolveTrial(e, PRODUCT, DEVICE_A, machines, { today: '2026-06-01' });
    const closureSqls = sql.filter((s) => s.includes('WITH RECURSIVE'));
    assert.ok(closureSqls.length >= 1);
    for (const stmt of closureSqls) {
      assertD1CompoundSelectCap(stmt);
    }
  });
}

async function propagateSubjectSetup(e, devicesOnShared) {
  const shared = '9'.repeat(64);
  const codes = [];
  for (let i = 0; i < devicesOnShared; i++) {
    const code = `PRP${String(i).padStart(2, '0')}-AAAAA`;
    codes.push(code);
    await insertRequest(e, {
      id: `prp-${devicesOnShared}-${i}`,
      device: code,
      dkey: deviceKey(code),
      machine: shared,
      expiry: '2026-01-01',
    });
  }
  return { shared, grantDevice: codes[0] };
}

for (const subjectCount of [6, 12, 50]) {
  test(`trialGrantStatements propagate ${subjectCount} subjects within compound SELECT cap`, async () => {
    const base = env();
    const { shared, grantDevice } = await propagateSubjectSetup(base, subjectCount - 1);
    const { e, sql } = sqlCaptureEnv(base.DB);
    const win = { first_day: '2026-06-01', last_day: '2026-06-14' };
    const stmts = await trialGrantStatements(e, PRODUCT, grantDevice, [shared], win, `prop-${subjectCount}`);
    assert.ok(stmts.length >= 1);
    for (const stmt of stmts) {
      if (typeof stmt === 'object' && stmt.bind) {
        /* D1 mock stmt — SQL already captured on prepare */
      }
    }
    const propagateSqls = sql.filter((s) => s.includes('json_each') && s.includes('trial_grants'));
    assert.ok(propagateSqls.length >= 1);
    for (const stmt of propagateSqls) {
      assertD1CompoundSelectCap(stmt);
    }
    await base.DB.batch(stmts);
    const n = await base.DB.prepare('SELECT COUNT(*) AS n FROM trial_grants').bind().first();
    assert.equal(n.n, subjectCount);
  });
}

test('customer device with underscore matches hyphenated resolveTrial', async () => {
  const e = env();
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('us', ?, '', ?, 'paid', '2025-01-01', '2026-12-31', 'paid', '2026-12-31', 1)`,
  ).bind(PRODUCT, '7kd2m_qx9tp').run();
  const blocked = await resolveTrial(e, PRODUCT, DEVICE_A, [MACHINE_A], { today: '2026-03-01' });
  assert.equal(blocked.kind, 'blocked');
  assert.equal(blocked.reason, 'downgrade_forbidden');
});

test('customer device I/L/O aliases match normalized resolveTrial device', async () => {
  const e = env();
  const aliasDevice = 'IKD2M-QX9TP';
  const canonical = '1KD2M-QX9TP';
  assert.equal(deviceKey(aliasDevice), deviceKey(canonical));
  await e.DB.prepare(
    `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, licence_expiry, created_at)
     VALUES('alias', ?, '', ?, 'permanent', '2025-01-01', '', 'permanent', '', 1)`,
  ).bind(PRODUCT, aliasDevice).run();
  const blocked = await resolveTrial(e, PRODUCT, canonical, [], { today: '2026-03-01' });
  assert.equal(blocked.kind, 'blocked');
  assert.equal(blocked.reason, 'downgrade_forbidden');
});

test('PR B r3: owner backfill completion call stays within D1 free query cap', async () => {
  const win = trialWindow('2026-09-01');
  const { e, queryCount } = countingEnv();
  for (let i = 0; i < 200; i++) {
    const hex = i.toString(16).padStart(8, '0').toUpperCase();
    const device = `${hex.slice(0, 4)}A-${hex.slice(4, 8)}B`;
    await insertRequest(e, {
      id: `owner-cap-${i}`,
      device,
      dkey: deviceKey(device),
      machine: MACHINE_A,
      expiry: win.last,
    });
  }
  const { runTrialGrantsBackfillToCompletion, isTrialGrantsBackfillComplete } = await import('../src/trial-grants.js');
  const start = queryCount();
  const out = await runTrialGrantsBackfillToCompletion(e, { maxSteps: 999 });
  const used = queryCount() - start;
  assert.ok(out.steps <= 2);
  assert.ok(used <= 50);
  while (!(await isTrialGrantsBackfillComplete(e))) {
    const stepStart = queryCount();
    await runTrialGrantsBackfillToCompletion(e, { maxSteps: 999 });
    assert.ok(queryCount() - stepStart <= 50);
  }
});

test('PR B r2: stepped backfill for 1200 trials stays within query budget and matches one-shot', async () => {
  const win = trialWindow('2026-09-01');
  const { e: eFull } = countingEnv();
  const bulkDevice = (i) => {
    const hex = i.toString(16).padStart(8, '0').toUpperCase();
    return `${hex.slice(0, 4)}A-${hex.slice(4, 8)}B`;
  };
  for (let i = 0; i < 1200; i++) {
    const device = bulkDevice(i);
    await insertRequest(eFull, {
      id: `bulk-${i}`,
      device,
      dkey: deviceKey(device),
      machine: MACHINE_A,
      expiry: win.last,
    });
  }
  const fullCount = await backfillTrialGrants(eFull, PRODUCT);
  const fullRows = await eFull.DB.prepare(
    'SELECT product, subject_kind, subject, first_day, last_day FROM trial_grants ORDER BY subject_kind, subject',
  ).bind().all();

  const { e: eStep, queryCount } = countingEnv();
  for (let i = 0; i < 1200; i++) {
    const device = bulkDevice(i);
    await insertRequest(eStep, {
      id: `bulk-${i}`,
      device,
      dkey: deviceKey(device),
      machine: MACHINE_A,
      expiry: win.last,
    });
  }

  const {
    trialGrantsBackfillStep,
    isTrialGrantsBackfillComplete,
    assertTrialGrantsBackfillReady,
  } = await import('../src/trial-grants.js');

  await assert.rejects(() => assertTrialGrantsBackfillReady(eStep), /backfill_in_progress/);

  let steps = 0;
  while (!(await isTrialGrantsBackfillComplete(eStep))) {
    const startQ = queryCount();
    const out = await trialGrantsBackfillStep(eStep);
    const used = queryCount() - startQ;
    assert.ok(out.queriesUsed <= 20);
    assert.ok(used <= 50);
    steps += 1;
    assert.ok(steps < 5000);
  }
  assert.ok(fullCount > 0);
  const steppedRows = await eStep.DB.prepare(
    'SELECT product, subject_kind, subject, first_day, last_day FROM trial_grants ORDER BY subject_kind, subject',
  ).bind().all();
  assert.deepEqual(steppedRows.results, fullRows.results);
});
