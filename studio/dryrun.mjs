// Runs the whole storyboard once WITHOUT recording and saves screenshots at each beat - to check the stage before shooting.
import { Browser } from './lib/cdp.mjs';
import { Stage } from './lib/stage.mjs';
import { fakeCameraScript } from './lib/clock.mjs';
import { buildSet } from './sets/film1.mjs';
import * as office from './skills/office.mjs';
import * as driver from './skills/driver.mjs';
import { mkdirSync } from 'node:fs';

const out = new URL('./takes/_dryrun/', import.meta.url).pathname;
mkdirSync(out, { recursive: true });
const set = await buildSet({ root: new URL('./takes/_dryrun/set', import.meta.url).pathname });
const browser = await Browser.launch({ args: ['--use-fake-ui-for-media-stream'] });
const prefs = `try { localStorage.setItem('to.prefs', JSON.stringify({ lang: 'ar', welcomed: true, theme: 'daylight' })) } catch (e) {}`;
let n = 0;
const T0 = Date.now();
const shot = async (p, name) => { console.log(((Date.now() - T0) / 1000).toFixed(0) + 's', name); return p.screenshot(`${out}/${String(++n).padStart(2, '0')}-${name}.png`); };
try {
  const op = await browser.newPage({ width: 1280, height: 800, scale: 1.5, initScripts: [set.clock.initScript(), prefs] });
  await op.send('Emulation.setTimezoneOverride', { timezoneId: set.tz });
  set.clock.attach(op);
  const os_ = new Stage(op, { name: 'office' });
  await office.login(op, set);
  const trip = await office.createTrip(os_, set); await shot(op, 'created');
  await office.approve(os_, set, trip); await shot(op, 'approved');
  const link = await office.sendLink(os_, set, trip); await shot(op, 'link');
  console.log('trip', trip.no, 'link ok');

  const pp = await browser.newPage({ width: 393, height: 851, scale: 2, mobile: true, initScripts: [set.clock.initScript(), fakeCameraScript(), `try { localStorage.setItem('to.lang','ar') } catch (e) {}`] });
  await pp.send('Emulation.setTimezoneOverride', { timezoneId: set.tz });
  set.clock.attach(pp);
  const ps = new Stage(pp, { name: 'phone' });
  await driver.openLink(ps, set, link); await shot(pp, 'phone-card');
  const t1 = await driver.startTrip(ps, set, trip); await shot(pp, 'phone-started');
  console.log('started', t1.startKm, t1.startAt);
  console.log('-> board'); await office.board(os_, set, trip, 'على الطريق'); await shot(op, 'board');
  await set.clock.jump(2 * 3600 + 5 * 60);
  const t2 = await driver.endTrip(ps, set, trip); await shot(pp, 'phone-done');
  console.log('ended', t2.endKm, t2.endAt);
  console.log('-> open trip'); const proven = await office.openTrip(os_, set, trip); await shot(op, 'trip-green');
  console.log('proven', proven.insight.km, proven.insight.hours, proven.photos);
  const r = await office.reports(os_, set); await shot(op, 'report');
  console.log('report', r.summary.total);
  const x = await office.exportExcel(os_, set, { ...proven.trip, plate: set.actor.plate }); await shot(op, 'excel');
  console.log('excel', x.row);
  console.log('events', os_.events.length, ps.events.length);
} finally {
  await browser.close();
  await set.stop();
}
