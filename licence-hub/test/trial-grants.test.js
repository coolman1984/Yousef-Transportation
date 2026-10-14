import { test } from 'node:test';
import assert from 'node:assert/strict';
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

const PRODUCT = 'trip-orders';
const DEVICE_A = '7KD2M-QX9TP';
const DEVICE_B = 'ABCDE-FGHJK';
const DKEY_A = deviceKey(DEVICE_A);
const DKEY_B = deviceKey(DEVICE_B);
const MACHINE_A = 'a'.repeat(64);
const MACHINE_A_UPPER = MACHINE_A.toUpperCase();
const MACHINE_B = 'b'.repeat(64);

function env(over = {}) {
  return {
    DB: newD1(),
    TRIAL_DAYS: '14',
    LICENCE_CALENDAR_TZ: 'Africa/Cairo',
    ...over,
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
}) {
  const t = 100;
  await e.DB.prepare(
    `INSERT INTO licence_requests(
      id, poll_token_hash, product, kind, device, device_key, machine, nonce, shop, ref, version,
      status, licence_tier, licence_expiry, created_at, updated_at
    ) VALUES(?, 'h', ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, ?, ?, ?)`,
  ).bind(id, product, kind, device, dkey, machine, 'n-' + id, status, tier, expiry, t, t).run();
}

test('normalizeMachineHash is the single lowercase entry point', () => {
  assert.equal(normalizeMachineHash(MACHINE_A_UPPER), MACHINE_A);
  assert.equal(normalizeMachineHash('  ' + MACHINE_A + '  '), MACHINE_A);
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
    name: 'etw machine row hash case',
    setup: async (e) => {
      const { first, last } = trialWindow('2026-04-10');
      await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(`etw|${PRODUCT}|m|${MACHINE_A}`, `${first}|${last}`, 1).run();
      await backfillTrialGrants(e, PRODUCT);
    },
    machines: [MACHINE_A_UPPER],
    today: '2026-04-01',
    expect: { kind: 'existing', first_day: trialWindow('2026-04-10').first, last_day: '2026-04-10', active: true },
  },
  {
    name: 'lock row via delivered request',
    setup: async (e) => {
      const { first, last } = trialWindow('2026-07-01');
      await insertRequest(e, { id: 'lock-req', expiry: last });
      await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(machineLockKey(MACHINE_A), 'lock-req', 1).run();
      await backfillTrialGrants(e, PRODUCT);
    },
    today: '2026-06-15',
    expect: { kind: 'existing', first_day: trialWindow('2026-07-01').first, last_day: '2026-07-01', active: true },
  },
  {
    name: 'request row expired status',
    setup: async (e) => {
      const { last } = trialWindow('2025-12-31');
      await insertRequest(e, { id: 'exp-req', status: 'expired', expiry: last });
      await backfillTrialGrants(e, PRODUCT);
    },
    today: '2026-03-01',
    expect: { kind: 'existing', first_day: trialWindow('2025-12-31').first, last_day: '2025-12-31', active: false },
  },
  {
    name: 'customer trial dates',
    setup: async (e) => {
      await e.DB.prepare(
        `INSERT INTO customers(id, product, shop, device, kind, first_day, last_day, licence_tier, created_at)
         VALUES(?, ?, '', ?, 'trial', ?, ?, 'trial', 1)`,
      ).bind('c1', PRODUCT, DEVICE_A, '2026-02-01', '2026-02-14').run();
      await backfillTrialGrants(e, PRODUCT);
    },
    today: '2026-02-10',
    expect: { kind: 'existing', first_day: '2026-02-01', last_day: '2026-02-14', active: true },
  },
  {
    name: 'peer device shares machine ledger',
    setup: async (e) => {
      const { first, last } = trialWindow('2026-08-01');
      await insertRequest(e, { id: 'peer', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_A, expiry: last });
      await e.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?)')
        .bind(machineLockKey(MACHINE_A), 'peer', 1).run();
      await backfillTrialGrants(e, PRODUCT);
    },
    device: DEVICE_A,
    machines: [MACHINE_A],
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
    },
    device: DEVICE_A,
    machines: [MACHINE_B],
    today: '2026-03-01',
    expect: { kind: 'blocked', reason: 'downgrade_forbidden' },
  },
  {
    name: 'active paid until today blocks',
    setup: async (e) => {
      await insertRequest(e, {
        id: 'paid', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B,
        kind: 'monthly', tier: 'paid', expiry: '2026-03-15', status: 'pending',
      });
    },
    device: DEVICE_A,
    machines: [MACHINE_B],
    today: '2026-03-15',
    expect: { kind: 'blocked', reason: 'downgrade_forbidden' },
  },
  {
    name: 'expired paid does not block',
    setup: async (e) => {
      await insertRequest(e, {
        id: 'paid-old', device: DEVICE_B, dkey: DKEY_B, machine: MACHINE_B,
        kind: 'monthly', tier: 'paid', expiry: '2025-01-01', status: 'refused',
      });
    },
    device: DEVICE_A,
    machines: [MACHINE_B],
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
  });
}

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
  const dRow = await e.DB.prepare(
    'SELECT first_day FROM trial_grants WHERE subject_kind = ? AND subject = ?',
  ).bind('d', DKEY_A).first();
  assert.equal(dRow.first_day, early.first);
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
