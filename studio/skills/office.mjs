// Office skills: each one works the real screens through the stage, then PROVES its result through the program's API.
// A take that cannot prove its result fails.
const nav = (page) => `css:#sidebar a[data-page="${page}"]`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function must(cond, msg) { if (!cond) throw new Error('proof failed: ' + msg); }

export async function login(page, set) {
  await page.goto(set.base + '/', { waitFor: () => document.querySelector('#auth-form') });
  await page.evaluate((u, p) => {
    const f = (id, v) => { const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); };
    f('username', u); f('password', p); document.querySelector('#auth-form button[type=submit]').click();
  }, set.admin.username, set.admin.password);
  await page.waitFor(() => document.querySelector('#app-shell') && window.TO && TO.data && TO.data.state, { what: 'the office to open' });
}

export async function goPage(stage, page) {
  await stage.click(nav(page), { expect: `location.hash.startsWith('#/${page}') && !document.querySelector('#view .skeleton')` });
}

export async function createTrip(stage, set) {
  const a = set.actor;
  await goPage(stage, 'trips');
  await stage.click('css:[data-new]', { expect: () => document.querySelector('#nt-form') });
  await stage.fill('السيارة', a.plate, { within: '#nt-form' });
  await stage.fill('السائق', a.driver, { within: '#nt-form' });
  await stage.fill('طالب المشوار', a.requester, { within: '#nt-form' });
  await stage.page.waitFor(() => document.querySelector('#nt-form [name="departmentId"]').value !== '', { what: 'the department to fill itself' });
  await stage.fill('الوجهة', a.destination, { within: '#nt-form' });
  await stage.pause(500);
  await stage.click('css:.dialog [data-save]', { expect: () => document.querySelector('.drawer [data-trip]') });
  // proof
  const st = await set.api.get('/api/state');
  const t = st.trips.filter((x) => x.vehicleId === a.vehicleId && x.destination === a.destination && x.date === set.clock.now().toISOString().slice(0, 10)).pop();
  must(t && t.status === 'draft' && t.driverId === a.driverId && t.requesterId === a.requesterId, 'the new trip is saved as a draft with the right car, driver and requester');
  stage.mark('trip-created', { no: t.no, id: t.id });
  return t;
}

export async function approve(stage, set, trip) {
  await stage.click('css:.drawer [data-a="approve"]', { expect: () => !document.querySelector('.drawer [data-a="approve"]') });
  const t = (await set.api.get('/api/state')).trips.find((x) => x.id === trip.id);
  must(t.gaApproved === 'yes' && (t.gaBy.includes(set.admin.full_name) || t.gaBy.includes(set.admin.username)), 'approved by the logged-in person');
  stage.mark('approved', { by: t.gaBy, at: t.gaAt });
  return t;
}

export async function sendLink(stage, set, trip) {
  // the WhatsApp button opens WhatsApp on a real PC; in the studio the page keeps the address instead (not filmed - the film says so)
  await stage.page.evaluate(() => { window.__waOpened = null; window.open = (u) => { window.__waOpened = u; return null; }; });
  await stage.click('css:.drawer [data-a="wa"]', { expect: () => window.__waOpened && document.querySelector('.drawer [data-a="newlink"]') });
  const wa = await stage.page.evaluate(() => window.__waOpened);
  const link = decodeURIComponent(wa.split('text=')[1]).match(/https?:\/\/\S+\/t\/[A-Za-z0-9_-]+/)[0];
  const t = (await set.api.get('/api/state')).trips.find((x) => x.id === trip.id);
  must(t.status === 'sent' && t.linkHash, 'the trip is marked sent and has a link');
  await set.api.post('/api/gateway/pull');      // the office hands the card to the mailbox (normally within a minute)
  const card = await fetch(set.gateway + '/api/card/' + link.split('/t/')[1]);
  must(card.status === 200, 'the mailbox has the trip card');
  stage.mark('link-sent', { status: t.status });
  return link;
}

export async function board(stage, set, trip, col) {
  await goPage(stage, 'board');
  await stage.page.waitFor((id, c) => { const card = document.querySelector('.board-card[data-id="' + id + '"]'); return card && card.closest('section') && card.closest('section').querySelector('header b').textContent.includes(c); }, { what: 'the trip card in its column' }, trip.id, col);
  const box = await stage.point(`css:.board-card[data-id="${trip.id}"]`);
  stage.mark('board', { column: col });
  return box;
}

export async function openTrip(stage, set, trip) {
  await goPage(stage, 'trips');
  await stage.click(trip.no, { expect: () => document.querySelector('.drawer [data-trip]') });
  const st = await set.api.get('/api/state'), ins = (await set.api.get('/api/insights'))[trip.id];
  const t = st.trips.find((x) => x.id === trip.id);
  const photos = st.tripPhotos.filter((p) => p.tripId === trip.id).map((p) => p.kind).sort();
  must(ins.trust === 'green' && !ins.reasons.length, 'the trip is green with no reasons');
  must(t.status === 'finished' && t.endKm - t.startKm === ins.km, 'km = end - start');
  stage.mark('trip-proven', { km: ins.km, hours: ins.hours, trust: ins.trust, photos });
  return { trip: t, insight: ins, photos };
}

export async function reports(stage, set) {
  await goPage(stage, 'reports');
  await stage.page.waitFor(() => document.querySelector('#rp-body .bar-row'), { what: 'the report to fill in' });
  const ym = set.clock.now().toISOString().slice(0, 7);
  const r = await set.api.get('/api/reports?ym=' + ym);
  const shown = await stage.page.evaluate(() => [...document.querySelectorAll('#rp-body .kpi .value')].map((e) => e.textContent.replace(/[^\d.]/g, '')));
  must(String(r.summary.total.trips) === shown[0] && String(r.summary.total.km) === shown[1], 'the screen shows the API totals');
  stage.mark('report', { trips: r.summary.total.trips, km: r.summary.total.km });
  return r;
}

export async function exportExcel(stage, set, trip, { python = 'python3' } = {}) {
  await goPage(stage, 'excel');
  await stage.click('css:[data-tab="export"]', { expect: () => document.querySelector('#ex-ym') });
  await stage.click('css:[data-dl="excel"]', { expect: () => [...document.querySelectorAll('#toasts *')].some((e) => /اتنزّل|downloaded/.test(e.textContent)) });
  // read the same file back and find the trip's row
  const ym = set.clock.now().toISOString().slice(0, 7);
  const bytes = await set.api.call('GET', `/api/excel/export?ym=${ym}&layout=today`);
  const { execFileSync } = await import('node:child_process');
  const { writeFileSync } = await import('node:fs');
  const f = set.root + '/export.xlsx';
  writeFileSync(f, bytes);
  const out = JSON.parse(execFileSync(python, ['-c', `
import sys, json; sys.path.insert(0, ${JSON.stringify(set.repo + '/server')})
import xlsx_read
wb = xlsx_read.read(open(${JSON.stringify(f)}, 'rb').read())
sh = wb.sheet('All Car')
rows = [[sh.value(r, c) for c in (3, 8, 10, 11, 12)] + [ (sh.cells.get((r, 12)) and sh.cells[(r, 12)].f) or '' ] for r in range(2, sh.max_row + 1)]
print(json.dumps({'sheets': [s.name for s in wb.sheets], 'rows': rows}, default=str))`], { encoding: 'utf8' }));
  const row = out.rows.find((r) => r[0] === trip.plate && r[2] === trip.startKm);
  must(out.sheets.join('|') === 'All Car|SUV Rent|Microbus Rent', 'the three sheets of the old workbook');
  must(row && row[3] === trip.endKm && row[4] === trip.endKm - trip.startKm && /End KM.*Strat KM/.test(row[5]), 'the trip row with the km formula');
  stage.mark('excel', { sheets: out.sheets, row });
  return { sheets: out.sheets, row };
}
