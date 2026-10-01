// Phase 3a - the cut: footage + stage events + read-back results -> cuts/film1.cut.js (what the composer draws).
// Every figure in the cut comes from the take's read-back result, and is checked against it. A mismatch stops everything.
// The cut also bakes the editing decisions that must be smooth: speed ramps (idle waits play faster, readings play at 1x),
// and one camera track per device (gentle push-ins on the action, slow pull-outs, smoothed so nothing ever jerks).
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
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const FPS = 60;

// ---- 0. the raw material: frames must carry device pixels (the screencast once gave CSS-size frames without a word)
function jpegSize(file) {
  const b = readFileSync(file);
  for (let i = 2; i < b.length - 9;) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1], len = b.readUInt16BE(i + 2);
    if (m >= 0xc0 && m <= 0xc3) return { h: b.readUInt16BE(i + 5), w: b.readUInt16BE(i + 7) };
    i += 2 + len;
  }
  return null;
}
for (const [name, ft] of [['office', fo], ['phone', fp]]) {
  const sz = jpegSize(join(TAKE, name, ft.frames[Math.floor(ft.frames.length / 2)].f));
  if (!sz || sz.w < ft.width * ft.scale * 0.95) throw new Error(`REFUSED - ${name} frames are ${sz && sz.w}px wide, the take asked for ${ft.width * ft.scale}px (run Chromium with --force-device-scale-factor)`);
}

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
  request: { device: 'office', kicker: '٠١', title: 'الطلب', speed: 1.1 },
  approve: { device: 'office', kicker: '٠٢', title: 'الموافقة', speed: 1.0 },
  link: { device: 'office', kicker: '٠٣', title: 'لينك السائق', speed: 1.0 },
  'phone-start': { device: 'phone', kicker: '٠٤', title: 'البداية على موبايل السائق', speed: 1.1 },
  'board-road': { device: 'office', kicker: '٠٥', title: 'المكتب شايف المشوار', speed: 1.0 },
  'phone-end': { device: 'phone', kicker: '٠٦', title: 'النهاية والورقة الموقّعة', speed: 1.1 },
  'board-done': { device: 'office', kicker: '٠٧', title: 'المشوار خلص', speed: 1.0 },
  proven: { device: 'office', kicker: '٠٨', title: 'موثّق بالأرقام والصور', speed: 1.0 },
  report: { device: 'office', kicker: '٠٩', title: 'تقرير الشهر', speed: 1.0 },
  excel: { device: 'office', kicker: '١٠', title: 'الإكسيل بنفس الشكل', speed: 1.0 },
};
const startOf = {};
for (const m of sceneMarks) startOf[m.data.id] = m.ts;
for (const id of order) if (!startOf[id]) fail('no scene mark for ' + id);
const endMark = sceneMarks.find((m) => m.data.id === 'end');
const ends = Object.fromEntries(order.map((id, i) => [id, i + 1 < order.length ? startOf[order[i + 1]] : (endMark ? endMark.ts + 0.8 : WALL_END)]));

// ---- 3. speed ramps: idle stretches (no event, no new frame) play up to 2.6x, readings after a result stay at 1x
const frameTs = { office: fo.frames.map((f) => f.ts), phone: fp.frames.map((f) => f.ts) };
const PROTECT = new Set(['trip-created', 'approved', 'link-sent', 'started', 'ended', 'trip-proven', 'report', 'excel', 'board', 'scroll', 'phone-card']);
function speedCurve(dev, a, b, base) {
  const dt = 1 / 120, n = Math.ceil((b - a) / dt) + 1, v = new Float64Array(n);
  const near = new Uint8Array(n);
  const mark = (ts, before, after) => { for (let i = Math.max(0, Math.floor((ts - before - a) / dt)); i <= Math.min(n - 1, Math.ceil((ts + after - a) / dt)); i++) near[i] = 1; };
  for (const e of events) {
    if (e.ts < a - 3 || e.ts > b + 1) continue;
    if (e.kind === 'mark' && PROTECT.has(e.name)) mark(e.ts, 0.2, 2.6);
    else if (e.kind === 'look') mark(e.ts, 0.3, 2.4);
    else if (e.page === dev && e.kind !== 'cur' && e.kind !== 'mark') mark(e.ts, 0.5, 0.7);
  }
  for (const ts of frameTs[dev]) if (ts >= a - 1 && ts <= b + 1) mark(ts, 0.15, 0.25);
  mark(a, 0, 0.6);                                              // every scene opens at 1x
  for (let i = 0; i < n; i++) v[i] = near[i] ? 1 : 2.6;
  // smooth the ramps (gaussian, sigma 0.3 s) so speed changes are never felt as jumps
  const sg = 0.3 / dt, r = Math.ceil(sg * 3), k = [];
  for (let j = -r; j <= r; j++) k.push(Math.exp(-(j * j) / (2 * sg * sg)));
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) { let s = 0, w = 0; for (let j = -r; j <= r; j++) { const q = clamp(i + j, 0, n - 1); s += v[q] * k[j + r]; w += k[j + r]; } out[i] = (s / w) * base; }
  return { dt, v: out };
}

const PRE = 3.6;                                                 // the opening composition before the first scene plays
let f = PRE;
const scenes = [];
for (const id of order) {
  const m = META[id], a = startOf[id], b = ends[id];
  const { dt, v } = speedCurve(m.device, a, b, m.speed);
  // integrate: wall -> film
  const film = [0];
  for (let i = 1; i < v.length; i++) film.push(film[i - 1] + dt / ((v[i - 1] + v[i]) / 2));
  const len = film[film.length - 1];
  // resample: film (1/FPS steps) -> wall offset
  const map = [];
  let j = 0;
  for (let q = 0; q * (1 / FPS) <= len + 1e-9; q++) {
    const tf = q / FPS;
    while (j < film.length - 2 && film[j + 1] < tf) j++;
    const u = clamp((tf - film[j]) / ((film[j + 1] - film[j]) || 1), 0, 1);
    map.push(Math.round(((j + u) * dt) * 1000) / 1000);
  }
  scenes.push({ id, device: m.device, kicker: m.kicker, title: m.title, src: [a, b], film: [f, f + len], map, _film: film, _dt: dt });
  f += len;
}
const wallToFilm = (wall) => {
  for (const s of scenes) if (wall >= s.src[0] && wall <= s.src[1]) { const i = Math.min(s._film.length - 1, Math.round((wall - s.src[0]) / s._dt)); return s.film[0] + s._film[i]; }
  let best = scenes[0], d = 1e9;
  for (const s of scenes) { const e = Math.min(Math.abs(wall - s.src[0]), Math.abs(wall - s.src[1])); if (e < d) { d = e; best = s; } }
  return wall < best.src[0] ? best.film[0] : best.film[1];
};
const inScene = (wall, dev) => scenes.some((s) => wall >= s.src[0] && wall <= s.src[1] && (!dev || s.device === dev));
const markT = (name, nth = 0) => { const m = marks.filter((x) => x.name === name)[nth]; if (!m) fail('no mark ' + name); return wallToFilm(m.ts); };
const S = (id) => scenes.find((s) => s.id === id);
const tEnd = f;

// ---- 4. the camera: one track per device, in the device's own CSS pixels (fx, fy = the point at the centre of the shot; z = push-in)
const DEV = {
  office: { w: 1280, h: 800, zmax: 1.4, ctx: [820, 520], wide: [640, 382] },
  phone: { w: 393, h: 851, zmax: 1.16, ctx: [312, 600], wide: [196.5, 425.5] },
};
function cameraTrack(dev) {
  const D = DEV[dev], n = Math.ceil((tEnd + 8) * FPS), target = [];
  for (let i = 0; i < n; i++) target.push([D.wide[0], D.wide[1], 1]);
  const held = new Int32Array(n);
  const evs = events.filter((e) => e.page === dev && inScene(e.ts, dev) && (
    (e.kind === 'click' && !/sidebar|pclose|data-new/.test(e.target)) || e.kind === 'point' || e.kind === 'look'));
  // clusters: actions close in time are framed together, the frame follows each action a little inside the cluster
  const clusters = [];
  for (const e of evs) {
    const last = clusters[clusters.length - 1];
    const sameScene = last && scenes.find((s) => e.ts >= s.src[0] && e.ts <= s.src[1]) === last.scene;
    if (last && sameScene && e.kind !== 'look' && last.kind !== 'look' && e.ts - last.t1 < 6) { last.items.push(e); last.t1 = e.ts; }
    else clusters.push({ kind: e.kind, items: [e], t0: e.ts, t1: e.ts, scene: scenes.find((s) => e.ts >= s.src[0] && e.ts <= s.src[1]) });
  }
  for (let c = 0; c < clusters.length; c++) {
    const C = clusters[c], next = clusters[c + 1];
    // a look frames its box; actions use a follow shot: a fixed push-in, the frame glides from one action to the next
    let z, cx, cy, follow;
    if (C.kind === 'look') {
      const e = C.items[0], fit = Math.min(D.w / e.w, D.h / e.h) * 0.92;
      z = clamp(e.zoom || Math.max(fit, 1.24), 1, D.zmax); cx = e.x; cy = e.y; follow = 0;
    } else {
      z = clamp(Math.min(D.w / D.ctx[0], D.h / D.ctx[1]) * 0.92, 1, D.zmax);
      cx = C.items.reduce((a, e) => a + e.x, 0) / C.items.length; cy = C.items.reduce((a, e) => a + e.y, 0) / C.items.length; follow = 0.85;
    }
    const typing = events.filter((e) => e.kind === 'type' && e.page === dev && e.ts >= C.t1 && e.ts <= C.t1 + 8);
    const tailWall = typing.length ? typing[typing.length - 1].ts : C.t1;
    const sceneEnd = C.scene.src[1];
    const hold = C.kind === 'look' ? 3.2 : 2.2;
    const from = wallToFilm(C.t0 - (C.kind === 'look' ? 0.2 : 0.7));
    let to = wallToFilm(Math.min(tailWall + hold, sceneEnd - 0.4));
    if (next) to = Math.min(to, wallToFilm(next.t0) - 0.1);
    for (let i = Math.floor(from * FPS); i <= Math.ceil(to * FPS) && i < n; i++) {
      if (i < 0) continue;
      // inside the cluster: the frame follows the action happening now
      let cur = C.items[0];
      for (const e of C.items) if (wallToFilm(e.ts) - 0.5 <= i / FPS) cur = e;
      target[i] = [cx + follow * (cur.x - cx), cy + follow * (cur.y - cy), z];
      held[i] = c + 1;
    }
  }
  // short gaps between two shots of one scene: the camera stays in and pans, instead of pumping out and back in
  for (let i = 0, last = -1; i < n; i++) {
    if (held[i]) { if (last >= 0 && i - last > 1 && i - last < 3.8 * FPS && held[last] !== held[i]) for (let j = last + 1; j < i; j++) target[j] = target[last].slice(); last = i; }
  }
  // smooth: gaussian, sigma 0.55 s (position) - the camera anticipates a little and always eases in and out
  const sg = 0.55 * FPS, rad = Math.ceil(sg * 3), k = [];
  for (let j = -rad; j <= rad; j++) k.push(Math.exp(-(j * j) / (2 * sg * sg)));
  const out = [];
  for (let i = 0; i < n; i++) {
    let x = 0, y = 0, lz = 0, w = 0;
    for (let j = -rad; j <= rad; j++) { const q = clamp(i + j, 0, n - 1), kk = k[j + rad]; x += target[q][0] * kk; y += target[q][1] * kk; lz += Math.log(target[q][2]) * kk; w += kk; }
    out.push([Math.round((x / w) * 10) / 10, Math.round((y / w) * 10) / 10, Math.round(Math.exp(lz / w) * 10000) / 10000]);
  }
  return out;
}
const camera = { office: cameraTrack('office'), phone: cameraTrack('phone') };

// ---- 5. the hands: the cursor path (office) and the finger taps (phone), drawn by the composer so they stay smooth and sharp
const cursor = fo.events.filter((e) => e.kind === 'cur').map((e) => [Math.round(e.ts * 1000) / 1000, e.x, e.y]);
const clicks = events.filter((e) => e.kind === 'click' && inScene(e.ts, e.page)).map((e) => ({ dev: e.page, t: wallToFilm(e.ts), x: e.x, y: e.y }));

// ---- 6. side text beside the phone, chips, captions, stamps
const side = {
  'phone-start': { k: 'على موبايل السائق', l: ['صفحة واحدة بتتفتح من اللينك.', 'مفيش برنامج يتنزّل.'] },
  'phone-end': { k: 'بعد الطريق', l: ['صورة العداد والقراءة،', 'وصورة الورقة الموقّعة.'] },
};
const t = {
  request: markT('trip-created'), approve: markT('approved'), link: markT('link-sent'), start: markT('started'), end: markT('ended'), proven: markT('trip-proven'),
  report: markT('report'), excel: markT('excel'),
};
const chips = [
  { label: 'طلب', t: t.request }, { label: 'موافقة', t: t.approve }, { label: 'لينك للسائق', t: t.link },
  { label: 'بداية', value: num(R.startKm), t: t.start }, { label: 'نهاية', value: num(R.endKm), t: t.end }, { label: 'ورقة موقّعة', t: t.end + 0.5 },
  { label: 'أخضر · موثّق', value: `${R.km} كم`, t: t.proven }, { label: 'تقرير الشهر', t: t.report }, { label: 'إكسيل', t: t.excel },
];
const firstShoot = events.find((e) => e.kind === 'click' && e.page === 'phone' && /shoot/.test(e.target));
const captions = [
  { t0: S('link').film[0] + 1.0, t1: S('link').film[1] + 0.3, text: 'بيتبعت للسائق على واتساب · واتساب مش متصوّر في الفيلم' },
  { t0: wallToFilm(firstShoot.ts) + 0.3, t1: wallToFilm(firstShoot.ts) + 4.6, text: 'صورة العداد صورة تجريبية' },
  { t0: S('phone-end').film[0] + 0.2, t1: S('phone-end').film[0] + 3.8, text: 'بعد ساعتين على الطريق · الوقت مضغوط في الفيلم' },
  { t0: S('proven').film[0] + 0.8, t1: S('proven').film[0] + 5.2, text: 'كل رقم هنا اتقرأ من البرنامج' },
  { t0: S('report').film[0] + 0.6, t1: S('report').film[0] + 4.8, text: 'أرقام الشهر من نفس المشاوير' },
  { t0: S('excel').film[0] + 0.6, t1: S('excel').film[1] - 0.2, text: 'نفس الشيتات ونفس المعادلات اللي بتشتغل بيها' },
];
const stamps = [
  { t0: t.start + 0.25, t1: t.start + 3.6, n: R.startKm, sep: true, label: 'عداد البداية · ' + ar(hh(R.startAt)) },
  { t0: t.end + 0.25, t1: t.end + 3.6, n: R.endKm, sep: true, label: 'عداد النهاية · ' + ar(hh(R.endAt)) },
  { t0: t.proven + 0.2, t1: t.proven + 4.4, n: R.km, unit: 'كم', label: `أخضر · موثّق · ${ar(hm)} ساعة` },
  { t0: t.report + 0.5, t1: t.report + 4.4, n: R.month.trips, unit: 'مشوار', label: `${num(R.month.km)} كم · تقرير أكتوبر` },
  { t0: t.excel + 0.3, t1: S('excel').film[1] + 0.2, n: 3, unit: 'شيتات', label: 'All Car · SUV Rent · Microbus Rent' },
];
for (const s of stamps) { const shown = s.sep ? num(s.n) : String(s.n); if (Number(shown.replace(/,/g, '')) !== s.n) fail('stamp ' + shown); }

const OUTRO = 6.4;
const CUT = {
  fps: FPS, pre: PRE, duration: tEnd + OUTRO,
  actor: { no: R.no, meta: [`${R.requester} · ${R.department}`, `${R.plate} · ${R.driver}`, R.destination] },
  scenes: scenes.map(({ _film, _dt, ...s }) => s), chips, captions, stamps, side, camera, cursor, clicks,
  outro: { t0: tEnd, a: ['جرّبه على', 'أسبوع واحد', 'من مشاويرك'], b: 'الفيلم كله بشركة وبيانات تجريبية · ساعة الاستوديو · صور العداد مرسومة', c: 'أوامر التشغيل' },
  frames: { office: fo.frames.map((x) => [x.ts, pathToFileURL(join(TAKE, 'office', x.f)).href]), phone: fp.frames.map((x) => [x.ts, pathToFileURL(join(TAKE, 'phone', x.f)).href]) },
  audio: {
    whooshes: scenes.slice(1).filter((s, i) => s.device !== scenes[i].device).map((s) => s.film[0]).concat([PRE - 0.6, tEnd]),
    swells: scenes.slice(1).filter((s, i) => s.device === scenes[i].device).map((s) => s.film[0]),
    clicks: clicks.map((c) => c.t),
    typing: events.filter((e) => e.kind === 'type' && inScene(e.ts, e.page)).map((e) => wallToFilm(e.ts)).filter((_, i) => i % 2 === 0),
    chimes: chips.map((c) => c.t),
    rolls: stamps.map((s) => s.t0),
  },
  figures: { ...R },
};
mkdirSync(join(HERE, 'cuts'), { recursive: true });
writeFileSync(join(HERE, 'cuts', 'film1.cut.js'), 'window.CUT = ' + JSON.stringify(CUT) + ';\n');
writeFileSync(join(HERE, 'cuts', 'film1.cut.json'), JSON.stringify({ ...CUT, frames: undefined, camera: undefined, cursor: undefined, scenes: CUT.scenes.map(({ map, ...s }) => s) }, null, 1));
console.log('cut ok: duration', CUT.duration.toFixed(1), 's; scenes', CUT.scenes.map((s) => `${s.id}@${s.film[0].toFixed(1)}`).join(' '));
console.log('figures verified:', JSON.stringify({ startKm: R.startKm, endKm: R.endKm, km: R.km, hours: R.hours, month: R.month }));
