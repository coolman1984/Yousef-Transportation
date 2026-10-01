// The set of film 1: the real office program (temporary database) and the real mailbox code, both on the studio clock,
// and an invented sample world built ONLY through the program's own API. On camera, only the screens do the work.
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { Api, uuid, sha256Hex } from '../lib/api.mjs';
import { StudioClock } from '../lib/clock.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
export const TZ = 'Africa/Cairo';
export const STUDIO_DAY = '2026-10-06';                       // a Tuesday; the clock starts at 07:00 for the off-camera morning
export const ADMIN = { username: 'nora', full_name: 'نورا – إدارة الحركة', password: 'Studio-Pass-2026' };
export const ACTOR = { requester: 'منى سامي', department: 'المشتريات', driver: 'كريم فؤاد', plate: 'ن ج ع 4821', vehicleType: 'سيدان', category: 'سيارات الإدارة',
  destination: 'المصنع - المطار - المصنع', km: 118 };

function waitLine(proc, re, what) {
  return new Promise((ok, bad) => {
    let buf = '';
    const t = setTimeout(() => bad(new Error(what + ' did not start: ' + buf.slice(-600))), 60000);
    const on = (d) => { buf += d; const m = re.exec(buf); if (m) { clearTimeout(t); ok(m); } };
    proc.stdout.on('data', on); proc.stderr.on('data', on);
    proc.on('exit', (c) => { clearTimeout(t); bad(new Error(what + ' exited ' + c + ': ' + buf.slice(-600))); });
  });
}
/** what a phone in Cairo sends: local time with its offset */
const cairoIso = (d) => new Date(d.getTime() + 3 * 3600e3).toISOString().slice(0, 19) + '+03:00';
const freePort = () => 20000 + Math.floor(Math.random() * 30000);

/** a tiny real JPEG (grey square) for the off-camera drivers' photos */
const TINY_JPEG = Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAAQABABAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAA/AKp//9k=', 'base64');

export async function buildSet({ root }) {
  rmSync(root, { recursive: true, force: true });
  mkdirSync(root, { recursive: true });
  const clock = new StudioClock(join(root, 'clock.json'), `${STUDIO_DAY}T07:00:00+03:00`);
  const env = { ...process.env, TZ, STUDIO_CLOCK: clock.file, PYTHONUNBUFFERED: '1' };

  // ---- the mailbox (real worker code, local D1 stand-in)
  const secret = randomBytes(24).toString('hex'), linkSecret = randomBytes(24).toString('hex');
  const gw = spawn('node', ['--no-warnings', join(HERE, '..', 'shims', 'gateway_clock.mjs')], { env: { ...env, OFFICE_SECRET: secret, PORT: String(freePort()) } });
  const gwPort = (await waitLine(gw, /READY (\d+)/, 'mailbox'))[1];
  const gateway = `http://127.0.0.1:${gwPort}`;

  // ---- the office program on a temporary database
  const port = freePort();
  const cfg = { port, host: '127.0.0.1', data_dir: join(root, 'data'), backup_dir: join(root, 'backups'), open_browser: false, sync_port: freePort(),
    device_name: 'studio', backup_interval_hours: 100000, session_idle_minutes: 100000, session_max_hours: 100000 };
  writeFileSync(join(root, 'config.json'), JSON.stringify(cfg));
  const office = spawn('python3', [join(HERE, '..', 'shims', 'office_clock.py'), join(REPO, 'server', 'app.py')], { env: { ...env, TO_CONFIG: join(root, 'config.json') } });
  const base = `http://127.0.0.1:${port}`;
  const api = new Api(base);
  for (let i = 0; ; i++) {
    try { await api.get('/api/auth/status'); break; } catch (e) { if (i > 150) throw e; await new Promise((r) => setTimeout(r, 200)); }
  }
  await api.post('/api/auth/setup', ADMIN);

  // ---- lists (invented)
  const put = (e, id, row) => ({ e, id, op: 'put', row });
  await api.post('/api/commit', { label: 'studio: sample company', ops: [
    put('settings', 'systemName', { value: 'شركة الواحة للخدمات (شركة تجريبية)' }),
    put('departments', 'dep_buy', { name: 'المشتريات', active: true }), put('departments', 'dep_fin', { name: 'المالية', active: true }),
    put('departments', 'dep_hr', { name: 'الموارد البشرية', active: true }), put('departments', 'dep_mnt', { name: 'الصيانة', active: true }),
    put('departments', 'dep_sal', { name: 'المبيعات', active: true }),
    put('tripCategories', 'cat_adm', { name: 'سيارات الإدارة', exportSheet: 'All Car', openLimitHours: 16 }),
  ] });
  // ---- September history through the program's own Excel import
  const hist = join(root, 'september.xlsx');
  const out = execFileSync('python3', [join(HERE, '..', 'shims', 'make_history.py'), hist], { encoding: 'utf8' });
  const lastOdo = Object.fromEntries(out.split('\n').filter((l) => l.startsWith('ODO ')).map((l) => { const p = l.slice(4).trim().split(' '); return [p.slice(0, -1).join(' '), +p.at(-1)]; }));
  const pv = await api.call('POST', '/api/import/preview?name=september.xlsx', undefined, { raw: readFileSync(hist) });
  await api.post('/api/excel/commit', { id: pv.id, merges: pv.merges || [] });
  let st = await api.get('/api/state');
  const id = (list, key, val) => (st[list].find((r) => r[key] === val) || {}).id;
  // details the import cannot know
  const veh = st.vehicles.find((v) => v.plate === ACTOR.plate);
  await api.post('/api/commit', { label: 'studio: car types', ops: st.vehicles.map((v) => ({ e: 'vehicles', id: v.id, op: 'put', ver: v.ver, row: { ...v, ver: undefined, type: 'سيدان', categoryId: id('tripCategories', 'name', ACTOR.category) } })) });

  if (!st.vehicles.some((v) => v.plate === 'ه د ب 7045')) {
    await api.post('/api/commit', { label: 'studio: fourth car', ops: [put('vehicles', 'veh_4', { plate: 'ه د ب 7045', type: 'سيدان', active: true, ownership: 'own', categoryId: id('tripCategories', 'name', ACTOR.category) })] });
  }

  // ---- the mailbox connected (the same setup code an administrator pastes)
  const code = Buffer.from(JSON.stringify({ v: 1, u: gateway, o: secret, l: linkSecret })).toString('base64url');
  await api.post('/api/gateway/code', { code });

  // ---- the morning, off camera: other drivers' trips through the real phone API, with the studio clock moving
  st = await api.get('/api/state');
  const cat = id('tripCategories', 'name', ACTOR.category);
  const morning = [
    { plate: 'س ط ر 1937', driver: 'حسام نبيل', req: 'أحمد ربيع', dep: 'المالية', dest: 'المصنع - البنك - المصنع', km: 34, start: '07:10', end: '08:05' },
    { plate: 'م ل ك 5520', driver: 'وليد شاكر', req: 'ياسر عادل', dep: 'الصيانة', dest: 'المصنع - المستودع - المصنع', km: 46, start: '07:40', end: '09:05' },
    { plate: 'ه د ب 7045', driver: 'طارق منير', req: 'دينا حسن', dep: 'المبيعات', dest: 'المصنع - المكتب الرئيسي - المصنع', km: 72, start: '09:12', end: null },
  ];
  const at = async (hhmm) => { const target = Date.parse(`${STUDIO_DAY}T${hhmm}:00+03:00`); const delta = (target - clock.now().getTime()) / 1000; if (delta > 0) await clock.jump(delta); };
  const phone = async (token, type, data, dev) => {
    const ev = { uuid: uuid(), v: 1, type, deviceId: dev, seq: 1, phoneAt: cairoIso(clock.now()), queued: false, data };
    const r = await fetch(`${gateway}/api/event/${token}`, { method: 'POST', body: JSON.stringify(ev), headers: { 'Content-Type': 'application/json' } });
    if (!r.ok) throw new Error('phone event ' + r.status);
    return ev;
  };
  const photo = async (token, kind, ev) => {
    const r = await fetch(`${gateway}/api/photo/${token}/${uuid()}`, { method: 'PUT', body: TINY_JPEG, headers: { 'X-Kind': kind, 'X-Sha256': await sha256Hex(TINY_JPEG), 'X-Fallback': '0', 'X-Event': ev || '' } });
    if (!r.ok) throw new Error('phone photo ' + r.status);
  };
  const timeline = [];
  for (const m of morning) {
    const t = await api.post('/api/trips/new', { date: STUDIO_DAY, categoryId: cat, vehicleId: id('vehicles', 'plate', m.plate), driverId: id('drivers', 'name', m.driver),
      requesterId: id('people', 'name', m.req), departmentId: id('departments', 'name', m.dep), destination: m.dest });
    await api.post('/api/trips/approve', { id: t.id, yes: true });
    const link = await api.post('/api/trips/link', { id: t.id, sent: true });
    m.trip = t; m.token = link.url.split('/t/')[1]; m.dev = 'dev-' + randomBytes(8).toString('hex'); m.startKm = lastOdo[m.plate];
    timeline.push({ t: m.start, m, act: 'start' });
    if (m.end) timeline.push({ t: m.end, m, act: 'end' });
  }
  await api.post('/api/gateway/pull');
  for (const s of timeline.sort((a, b) => a.t.localeCompare(b.t))) {
    await at(s.t);
    if (s.act === 'start') { const ev = await phone(s.m.token, 'start', { startKm: s.m.startKm }, s.m.dev); await photo(s.m.token, 'start_odo', ev.uuid); }
    else { const ev = await phone(s.m.token, 'end', { endKm: s.m.startKm + s.m.km, routeText: s.m.dest }, s.m.dev); await photo(s.m.token, 'end_odo', ev.uuid); await photo(s.m.token, 'paper'); }
    await api.post('/api/gateway/pull');
  }
  await at('09:30');                                       // the shoot starts here
  await api.post('/api/gateway/pull');

  const actor = { ...ACTOR, vehicleId: veh.id, startKm: lastOdo[ACTOR.plate],          // the car stood at the office since its last trip: no km without an order driverId: id('drivers', 'name', ACTOR.driver), requesterId: id('people', 'name', ACTOR.requester) };
  actor.endKm = actor.startKm + ACTOR.km;
  return {
    root, repo: REPO, clock, api, base, gateway, actor, admin: ADMIN, tz: TZ,
    async stop() { for (const p of [office, gw]) { try { p.kill('SIGINT'); } catch { /* gone */ } } await new Promise((r) => setTimeout(r, 800)); for (const p of [office, gw]) { try { p.kill('SIGKILL'); } catch { /* gone */ } } },
  };
}
