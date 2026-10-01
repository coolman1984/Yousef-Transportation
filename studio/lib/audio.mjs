// The sound, made in code (no licences): a soft music bed, one whoosh per transition (nothing below ~200 Hz), quiet clicks on real clicks,
// very light typing ticks. Output: a 48 kHz 16-bit stereo WAV.
import { writeFileSync } from 'node:fs';

const SR = 48000;
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }

export function makeAudio({ duration, clicks = [], typing = [], whooshes = [], music = true, seed = 7 }) {
  const n = Math.ceil(duration * SR), L = new Float32Array(n), R = new Float32Array(n), rnd = rng(seed);
  const add = (t, f) => { const i0 = Math.max(0, Math.floor(t * SR)); f(i0); };
  // ---- music bed: a calm pad (A minor 9 -> F maj7 -> C -> G), slow tremolo, a light pulse; mixed low
  if (music) {
    const chords = [[220, 261.63, 329.63, 493.88], [174.61, 220, 261.63, 329.63], [261.63, 329.63, 392, 493.88], [196, 246.94, 293.66, 392]];
    const bar = 7.5;
    for (let i = 0; i < n; i++) {
      const t = i / SR, c = chords[Math.floor(t / bar) % 4], within = (t % bar) / bar;
      const env = Math.min(1, within * 6) * Math.min(1, (1 - within) * 6);
      let v = 0;
      for (let k = 0; k < c.length; k++) {
        const f = c[k] * (k === 0 ? 0.5 : 1), det = 1 + 0.0018 * (k - 1.5);
        v += Math.sin(2 * Math.PI * f * det * t + 0.3 * Math.sin(2 * Math.PI * 0.2 * t + k)) * (k === 0 ? 0.55 : 0.32);
      }
      v *= (0.05 + 0.012 * Math.sin(2 * Math.PI * 0.12 * t)) * env;
      const beat = t % 0.5, pulse = Math.exp(-beat * 22) * Math.sin(2 * Math.PI * 523.25 * t) * 0.010 * (0.4 + 0.6 * Math.sin(Math.PI * Math.min(1, t / 8)));
      const open = Math.min(1, t / 3) * Math.min(1, (duration - t) / 3);
      L[i] += (v + pulse) * open; R[i] += (v + pulse * 0.8) * open;
    }
  }
  // ---- whooshes: band-passed noise, 0.35 s, 200 Hz and up
  for (const w of whooshes) {
    const len = Math.floor(0.35 * SR), i0 = Math.floor((w - 0.12) * SR);
    let lp = 0, hp = 0, lp2 = 0;
    for (let j = 0; j < len; j++) {
      const u = j / len, env = Math.sin(Math.PI * u) ** 2;
      const x = (rnd() * 2 - 1);
      const fc = 400 + 5200 * u;                       // the sweep rises
      const a = 1 - Math.exp(-2 * Math.PI * fc / SR);
      lp += a * (x - lp); lp2 += a * (lp - lp2);
      const a2 = 1 - Math.exp(-2 * Math.PI * 220 / SR);
      hp += a2 * (lp2 - hp);
      const y = (lp2 - hp) * env * 0.16, i = i0 + j;
      if (i >= 0 && i < n) { L[i] += y * (1 - u * 0.4); R[i] += y * (0.6 + u * 0.4); }
    }
  }
  // ---- clicks: a short, soft tick
  for (const t of clicks) add(t, (i0) => {
    for (let j = 0; j < 1400; j++) { const i = i0 + j; if (i >= n) break; const e = Math.exp(-j / 170), y = (Math.sin(2 * Math.PI * 1800 * j / SR) * 0.6 + (rnd() * 2 - 1) * 0.25) * e * 0.07; L[i] += y; R[i] += y; }
  });
  // ---- typing ticks: lighter and a little random in pitch
  for (const t of typing) add(t, (i0) => {
    const f = 2400 + rnd() * 900;
    for (let j = 0; j < 700; j++) { const i = i0 + j; if (i >= n) break; const e = Math.exp(-j / 80), y = Math.sin(2 * Math.PI * f * j / SR) * e * 0.022; L[i] += y; R[i] += y * 0.9; }
  });
  return { L, R };
}

export function writeWav(path, { L, R }) {
  const n = L.length, buf = Buffer.alloc(44 + n * 4);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) { buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(L[i] * 32767))), 44 + i * 4); buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(R[i] * 32767))), 46 + i * 4); }
  writeFileSync(path, buf);
}
