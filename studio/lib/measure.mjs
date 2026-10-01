// The numbers about a rendered film: loudness, true peak, frozen time, and a contact sheet. We report them; we do not argue with them.
import { spawnSync } from 'node:child_process';
import { FFMPEG } from './render.mjs';

export function loudness(file) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-nostats', '-i', file, '-af', 'ebur128=peak=true', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 28 });
  const t = r.stderr;
  const I = /I:\s+(-?[\d.]+) LUFS/g, TP = /Peak:\s+(-?[\d.]+) dBFS/g, LRA = /LRA:\s+([\d.]+) LU/g;
  const last = (re) => { let m, v = null; while ((m = re.exec(t))) v = +m[1]; return v; };
  return { integratedLUFS: last(I), truePeakdBFS: last(TP), LRA: last(LRA) };
}

/** seconds per 30 s window where the picture does not change at all */
export function frozen(file, duration) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-i', file, '-vf', 'freezedetect=n=-60dB:d=0.4', '-an', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 28 });
  const spans = []; let start = null;
  for (const line of r.stderr.split('\n')) {
    let m;
    if ((m = /freeze_start: ([\d.]+)/.exec(line))) start = +m[1];
    if ((m = /freeze_end: ([\d.]+)/.exec(line)) && start !== null) { spans.push([start, +m[1]]); start = null; }
  }
  if (start !== null) spans.push([start, duration]);
  const perWindow = [];
  for (let w = 0; w < duration; w += 30) {
    let s = 0;
    for (const [a, b] of spans) s += Math.max(0, Math.min(b, w + 30) - Math.max(a, w));
    perWindow.push({ from: w, frozenSeconds: +s.toFixed(1) });
  }
  return { spans, perWindow };
}

export function contactSheet(file, out, { every = 4, cols = 6, w = 320 } = {}) {
  const r = spawnSync(FFMPEG, ['-y', '-hide_banner', '-loglevel', 'error', '-i', file, '-vf', `fps=1/${every},scale=${w}:-1,tile=${cols}x6:padding=6:color=0x0b1a33`, '-frames:v', '1', out], { encoding: 'utf8' });
  return r.status === 0;
}
