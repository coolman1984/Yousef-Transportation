// Phase 3a - the cut: footage + stage events + read-back results -> cuts/film1.cut.js (what the composer draws).
// Every figure in the cut comes from the take's read-back result, and is checked against it. A mismatch stops everything.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const TAKE = join(HERE, 'takes', 'film1');
const read = (p) => JSON.parse(readFileSync(p, 'utf8'));
const fo = read(join(TAKE, 'office', 'footage.json')), fp = read(join(TAKE, 'phone', 'footage.json'));
const R = read(join(TAKE, 'result.json'));
const num = (n) => Number(n).toLocaleString('en-US');
const ar = (n) => String(n).replace(/\d/g, (d) => '٠١٢٣٤٥٦٧٨٩'[d]);
const fail = (m) => { throw new Error('REFUSED - figure mismatch: ' + m); };

// ---- 1. the figures: every one is checked before it can be drawn
if (R.endKm - R.startKm !== R.km) fail(`end ${R.endKm} - start ${R.startKm} != km ${R.km}`);
if (R.km !== 118) fail('the story says 118 km, the take read ' + R.km);
if (R.trust !== 'green') fail('trust is ' + R.trust);
if (R.status !== 'finished') fail('status ' + R.status);
if ([...R.photos].sort().join() !== 'end_odo,paper,start_odo') fail('photos ' + R.photos);
if (R.excel.row[4] !== R.km || R.excel.row[3] !== R.endKm || R.excel.row[2] !== R.startKm) fail('the exported row differs from the trip');
if (R.excel.sheets.join('|') !== 'All Car|SUV Rent|Microbus Rent') fail('sheets ' + R.excel.sheets);
if (R.month.trips < 1 || R.month.km < R.km) fail('month totals');
if (R.phoneNo !== R.no) fail(`the phone showed ${R.phoneNo}, the office ${R.no}`);
const hh = (iso) => iso.slice(11, 16);
const mins = (Date.parse(R.endAt) - Date.parse(R.startAt)) / 60000;
if (Math.abs(mins / 60 - R.hours) > 0.06) fail(`duration ${mins} min vs ${R.hours} h`);
const hm = `${Math.floor(mins / 60)}:${String(Math.round(mins % 60)).padStart(2, '0')}`;

// ---- 2. scenes: contiguous slices of the shared wall clock
const events = [...fo.events, ...fp.events].sort((a, b) => a.ts - b.ts);
const marks = events.filter((e) => e.kind === 'mark');
const sceneMarks = marks.filter((m) => m.name === 'scene');
const WALL_END = Math.max(fo.t1, fp.t1);
const order = ['request', 'approve', 'link', 'phone-start', 'board-road', 'phone-end', 'board-done', 'proven', 'report', 'excel'];
const META = {
  request: { device: 'office', kicker: '١', title: 'الطلب', speed: 1.35 },
  approve: { device: 'office', kicker: '٢', title: 'الموافقة', speed: 1.0 },
  link: { device: 'office', kicker: '٣', title: 'لينك السائق', speed: 1.0 },
  'phone-start': { device: 'phone', kicker: '٤', title: 'البداية — على موبايل السائق', speed: 1.25 },
  'board-road': { device: 'office', kicker: '٥', title: 'المكتب شايف', speed: 1.0 },
  'phone-end': { device: 'phone', kicker: '٦', title: 'النهاية والورقة', speed: 1.3 },
  'board-done': { device: 'office', kicker: '٧', title: 'خلّص', speed: 1.0 },
  proven: { device: 'office', kicker: '٨', title: 'موثّق بالأرقام والصور', speed: 1.0 },
  report: { device: 'office', kicker: '٩', title: 'تقرير الشهر', speed: 1.0 },
  excel: { device: 'office', kicker: '١٠', title: 'الإكسيل بنفس الشكل', speed: 1.0 },
};
const startOf = {};
for (const m of sceneMarks) startOf[m.data.id] = m.ts;
for (const id of order) if (!startOf[id]) fail('no scene mark for ' + id);
const endMark = sceneMarks.find((m) => m.data.id === 'end');
const ends = { ...Object.fromEntries(order.map((id, i) => [id, i + 1 < order.length ? startOf[order[i + 1]] : (endMark ? endMark.ts : WALL_END)])) };
ends.excel = endMark ? endMark.ts : WALL_END;

const OPEN = 5.2;                                      // the opening composition stays up while the first scene plays
let f = 0;
const scenes = [];
for (const id of order) {
  const m = META[id], a = startOf[id], b = ends[id];
  // trim long waiting at the start of a scene (the studio waits for the page to settle, the viewer should not)
  const len = (b - a) / m.speed;
  const hold = Math.min(len, id === 'request' ? 99 : 99);
  scenes.push({ id, device: m.device, kicker: m.kicker, title: m.title, src: [a, b], speed: m.speed, film: [f, f + hold], enter: 0.3, leave: 0.3 });
  f += hold;
}
const wallToFilm = (wall) => {
  for (const s of scenes) if (wall >= s.src[0] && wall <= s.src[1]) return s.film[0] + (wall - s.src[0]) / s.speed;
  let best = scenes[0], d = 1e9;
  for (const s of scenes) { const e = Math.min(Math.abs(wall - s.src[0]), Math.abs(wall - s.src[1])); if (e < d) { d = e; best = s; } }
  return wall < best.src[0] ? best.film[0] : best.film[1];
};
const inScene = (wall) => scenes.some((s) => wall >= s.src[0] && wall <= s.src[1]);
const markT = (name, nth = 0) => { const m = marks.filter((x) => x.name === name)[nth]; if (!m) fail('no mark ' + name); return wallToFilm(m.ts); };

// ---- 3. side text beside the phone
scenes.find((s) => s.id === 'phone-start').side = '<b>على موبايل السائق</b>صفحة واحدة تتفتح من اللينك.<br>مفيش برنامج يتنزّل.';
scenes.find((s) => s.id === 'phone-end').side = '<b>بعد الطريق</b>صورة العداد، القراءة،<br>وصورة الورقة الموقّعة.';

// ---- 4. chips (the actor's path, filled when the step was proven), captions, stamps
const t = {
  request: markT('trip-created'), approve: markT('approved'), link: markT('link-sent'), start: markT('started'), end: markT('ended'), proven: markT('trip-proven'),
  report: markT('report'), excel: markT('excel'),
};
const chips = [
  { label: 'طلب', value: '✓', t: t.request }, { label: 'موافقة', value: '✓', t: t.approve }, { label: 'لينك للسائق', value: '✓', t: t.link },
  { label: 'بداية', value: num(R.startKm), t: t.start }, { label: 'نهاية', value: num(R.endKm), t: t.end }, { label: 'ورقة موقّعة', value: '✓', t: t.end + 0.9 },
  { label: 'أخضر', value: `${R.km} كم`, t: t.proven }, { label: 'تقرير الشهر', value: '✓', t: t.report }, { label: 'إكسيل', value: '✓', t: t.excel },
];
const firstShoot = events.find((e) => e.kind === 'click' && e.page === 'phone' && /shoot/.test(e.target));
const S = (id) => scenes.find((s) => s.id === id);
const captions = [
  { t0: S('link').film[0] + 1.2, t1: S('link').film[1] + 0.2, text: 'بيتبعت للسائق على واتساب<br><small>(واتساب مش متصوّر في الفيلم)</small>' },
  { t0: wallToFilm(firstShoot.ts) + 0.3, t1: wallToFilm(firstShoot.ts) + 4.4, text: 'صورة العداد صورة تجريبية' },
  { t0: S('phone-end').film[0] + 0.1, t1: S('phone-end').film[0] + 3.6, text: 'بعد ساعتين على الطريق<br><small>الوقت مضغوط في الفيلم · ساعة الاستوديو</small>' },
  { t0: S('proven').film[0] + 0.8, t1: S('proven').film[0] + 5.2, text: 'كل رقم هنا اتقرأ من البرنامج' },
  { t0: S('report').film[0] + 0.6, t1: S('report').film[0] + 4.6, text: 'أرقام الشهر من نفس المشاوير' },
  { t0: S('excel').film[0] + 0.6, t1: S('excel').film[1] - 0.2, text: 'نفس الشيتات ونفس المعادلات اللي بتشتغل بيها' },
];
const stamps = [
  { t0: t.start + 0.3, t1: t.start + 3.4, value: num(R.startKm), label: 'عداد البداية · ' + ar(hh(R.startAt)) },
  { t0: t.end + 0.3, t1: t.end + 3.4, value: num(R.endKm), label: 'عداد النهاية · ' + ar(hh(R.endAt)) },
  { t0: t.proven + 0.2, t1: t.proven + 4.2, value: `${R.km} كم`, label: `أخضر · موثّق · ${ar(hm)} ساعة` },
  { t0: t.report + 0.6, t1: t.report + 4.2, value: `${R.month.trips} مشوار`, label: `${num(R.month.km)} كم · تقرير أكتوبر` },
  { t0: t.excel + 0.4, t1: S('excel').film[1] - 0.1, value: '3 شيتات', label: 'All Car · SUV Rent · Microbus Rent' },
];

const tEnd = f + 0.6;
const CUT = {
  fps: 30, open: { t1: OPEN }, duration: tEnd + 7.2,
  actor: { no: R.no, meta: `${R.requester} · ${R.department}<br>${R.plate} · ${R.driver}<br>${R.destination}` },
  scenes, chips, captions, stamps, focus: [],
  outro: { t0: tEnd, a: 'جرّبه على <span>أسبوع واحد</span><br>من مشاويرك', b: 'الفيلم كله بشركة وبيانات تجريبية · ساعة الاستوديو · صور العداد مرسومة', c: 'أوامر التشغيل' },
  frames: { office: fo.frames.map((x) => [x.ts, pathToFileURL(join(TAKE, 'office', x.f)).href]), phone: fp.frames.map((x) => [x.ts, pathToFileURL(join(TAKE, 'phone', x.f)).href]) },
  audio: {
    whooshes: scenes.slice(1).map((s) => s.film[0]).concat([tEnd]),
    clicks: events.filter((e) => e.kind === 'click' && inScene(e.ts)).map((e) => wallToFilm(e.ts)),
    typing: events.filter((e) => e.kind === 'type' && inScene(e.ts)).map((e) => wallToFilm(e.ts)).filter((_, i) => i % 2 === 0),
  },
  figures: { ...R },
};
mkdirSync(join(HERE, 'cuts'), { recursive: true });
writeFileSync(join(HERE, 'cuts', 'film1.cut.js'), 'window.CUT = ' + JSON.stringify(CUT) + ';\n');
writeFileSync(join(HERE, 'cuts', 'film1.cut.json'), JSON.stringify({ ...CUT, frames: undefined }, null, 1));
console.log('cut ok: duration', CUT.duration.toFixed(1), 's; scenes', scenes.map((s) => `${s.id}@${s.film[0].toFixed(1)}`).join(' '));
console.log('figures verified:', JSON.stringify({ startKm: R.startKm, endKm: R.endKm, km: R.km, hours: R.hours, month: R.month }));
