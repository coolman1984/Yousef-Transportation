// Phase 2 - the shoot: the whole story on the real screens, two devices recorded at once, with reading holds,
// then every figure the film will show is read back from the program and stored with the footage.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { Browser, sleep } from './lib/cdp.mjs';
import { Stage } from './lib/stage.mjs';
import { Recorder } from './lib/record.mjs';
import { fakeCameraScript } from './lib/clock.mjs';
import { buildSet } from './sets/film1.mjs';
import * as office from './skills/office.mjs';
import * as driver from './skills/driver.mjs';

const OUT = new URL('./takes/film1/', import.meta.url).pathname;
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

const set = await buildSet({ root: OUT + 'set' });
log('set ready', set.base);
// the screencast only sends device pixels when the browser itself runs at that scale (setDeviceMetricsOverride alone gives CSS-size frames)
const ob = await Browser.launch({ args: ['--force-device-scale-factor=1.5'] }), pb = await Browser.launch({ args: ['--use-fake-ui-for-media-stream', '--force-device-scale-factor=2'] });
const prefs = `try { localStorage.setItem('to.prefs', JSON.stringify({ lang: 'ar', welcomed: true, theme: 'daylight', motion: 'on' })) } catch (e) {}`;
const op = await ob.newPage({ width: 1280, height: 800, scale: 1.5, initScripts: [set.clock.initScript(), prefs] });
await op.send('Emulation.setTimezoneOverride', { timezoneId: set.tz });
const pp = await pb.newPage({ width: 393, height: 851, scale: 2, mobile: true, initScripts: [set.clock.initScript(), fakeCameraScript(), `try { localStorage.setItem('to.lang','ar') } catch (e) {}`] });
await pp.send('Emulation.setTimezoneOverride', { timezoneId: set.tz });
set.clock.attach(op); set.clock.attach(pp);
const os_ = new Stage(op, { name: 'office' }), ps = new Stage(pp, { name: 'phone' });
const scene = (st, id) => st.mark('scene', { id });
const hold = (ms) => sleep(ms);

await office.login(op, set);
await office.goPage(os_, 'trips').catch(() => {});
await op.evaluate(() => { location.hash = '#/trips'; });
await op.waitFor(() => document.querySelector('#view tbody tr'));
await pp.goto('about:blank');

const recO = new Recorder(op, OUT + 'office'), recP = new Recorder(pp, OUT + 'phone');
await recO.start(); await recP.start();
const R = {};
try {
  // 1 - the request
  scene(os_, 'request'); await os_.ensureCursor(); await hold(1500);
  const trip = await office.createTrip(os_, set); R.no = trip.no; await hold(700); await os_.look('.drawer.on [data-trip]'); await hold(1500);
  // 2 - approval
  scene(os_, 'approve'); await hold(600);
  const ap = await office.approve(os_, set, trip); R.gaBy = ap.gaBy; R.gaAt = ap.gaAt; await hold(500); await os_.look('.drawer.on [data-trip]'); await hold(1300);
  // 3 - the link
  scene(os_, 'link'); await hold(500);
  const link = await office.sendLink(os_, set, trip); await hold(1800);
  // 4 - the phone: start
  scene(ps, 'phone-start'); await ps.ensureCursor().catch(() => {});
  R.phoneNo = await driver.openLink(ps, set, link); await ps.ensureCursor(); await hold(1800);
  const t1 = await driver.startTrip(ps, set, trip); R.startKm = t1.startKm; R.startAt = t1.startAt; await hold(1800);
  // 5 - the office sees it (board)
  scene(os_, 'board-road'); await office.board(os_, set, trip, 'على الطريق'); await os_.look(`.board-card[data-id="${trip.id}"]`, { pad: 70 }); await hold(3500);
  // 6 - two hours later: the end and the paper
  scene(ps, 'phone-end'); await set.clock.jump(2 * 3600 + 5 * 60); await recP.poke(); await hold(1200);
  const t2 = await driver.endTrip(ps, set, trip); R.endKm = t2.endKm; R.endAt = t2.endAt; await hold(2500);
  // 7 - the office: the board moved, the trip is proven
  scene(os_, 'board-done'); await office.board(os_, set, trip, 'خلصت'); await os_.look(`.board-card[data-id="${trip.id}"]`, { pad: 70 }); await hold(2500);
  scene(os_, 'proven');
  const pr = await office.openTrip(os_, set, trip); R.km = pr.insight.km; R.hours = pr.insight.hours; R.trust = pr.insight.trust; R.photos = pr.photos; await hold(600); await os_.look('.drawer.on [data-trip]'); await hold(1100);
  await op.evaluate(() => { const h = [...document.querySelectorAll('.drawer.on .body h3')].find((x) => /الصور/.test(x.textContent)); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  os_.mark('scroll', { to: 'photos' }); await hold(900); await os_.look('.drawer.on .body img'); await hold(2600);
  await op.evaluate(() => { const h = [...document.querySelectorAll('.drawer.on .body h3')].find((x) => /العداد/.test(x.textContent)); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  os_.mark('scroll', { to: 'odo' }); await hold(900); await os_.look('.drawer.on .body'); await hold(2600);
  // 8 - the month
  scene(os_, 'report'); const rp = await office.reports(os_, set); R.month = { trips: rp.summary.total.trips, km: rp.summary.total.km, green: rp.summary.total.green }; await hold(400); await os_.look('#rp-body .kpi'); await hold(3600);
  scene(os_, 'excel'); const x = await office.exportExcel(os_, set, { ...pr.trip, plate: set.actor.plate }); R.excel = { sheets: x.sheets, row: x.row }; await os_.look('#toasts > *', { pad: 40 }); await hold(2500);
  scene(os_, 'end'); await hold(1500);
} finally {
  await recO.stop(); await recP.stop();
}
const st = await set.api.get('/api/state');
const t = st.trips.find((x) => x.no === R.no);
R.plate = set.actor.plate; R.driver = set.actor.driver; R.requester = set.actor.requester; R.department = set.actor.department; R.destination = t.destination;
R.status = t.status; R.studioDay = '2026-10-06';
recO.save({ events: os_.events, result: R }); recP.save({ events: ps.events, result: R });
writeFileSync(OUT + 'result.json', JSON.stringify(R, null, 1));
log('result', JSON.stringify(R));
log('frames', recO.frames.length, recP.frames.length);
await ob.close(); await pb.close(); await set.stop();
