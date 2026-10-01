// The sound, made in code (no licences). A calm, modern score (96 BPM): warm pad, a plucked arpeggio with a room,
// a soft low end and light percussion once the story starts; sound design on the picture's own beats: whooshes on device
// changes, soft swells on chapter changes, quiet clicks and typing, a chime per proven step, a counter roll per stamp,
// a riser into the opening and a soft hit on the end card. Output: a 48 kHz 16-bit stereo WAV.
import { writeFileSync } from 'node:fs';

const SR = 48000, TAU = Math.PI * 2;
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);

/** a small stereo room (Schroeder: 4 combs + 2 allpasses per side) */
function reverb(inp, n, { mix = 0.28, size = 1 } = {}) {
  const outL = new Float32Array(n), outR = new Float32Array(n);
  const side = (out, combs, aps) => {
    const cb = combs.map((d) => ({ b: new Float32Array(Math.round(d * size)), i: 0, f: 0 })), ab = aps.map((d) => ({ b: new Float32Array(d), i: 0 }));
    for (let i = 0; i < n; i++) {
      let y = 0;
      for (const c of cb) { const o = c.b[c.i]; c.f = o * 0.8 + c.f * 0.2; c.b[c.i] = inp[i] + c.f * 0.82; c.i = (c.i + 1) % c.b.length; y += o; }
      y *= 0.25;
      for (const a of ab) { const o = a.b[a.i], v = y + o * 0.5; a.b[a.i] = v; a.i = (a.i + 1) % a.b.length; y = o - v * 0.5; }
      out[i] = y * mix;
    }
  };
  side(outL, [1557, 1617, 1491, 1422], [225, 556]); side(outR, [1580, 1640, 1514, 1445], [248, 579]);
  return [outL, outR];
}

export function makeAudio({ duration, start = 3.6, end = duration - 6.4, clicks = [], typing = [], whooshes = [], swells = [], chimes = [], rolls = [], music = true, seed = 7 }) {
  const n = Math.ceil(duration * SR), L = new Float32Array(n), R = new Float32Array(n), rnd = rng(seed);
  const put = (i, l, r) => { if (i >= 0 && i < n) { L[i] += l; R[i] += r; } };
  if (music) {
    const beat = 60 / 96, bar = beat * 4;
    // Fmaj9 - Am7 - Dm9 - Gsus (two bars each); then the end resolves on F
    const prog = [[53, 57, 60, 64, 67], [57, 60, 64, 67, 71], [50, 57, 60, 64, 65], [55, 60, 62, 67, 69]];
    const chordAt = (t) => (t >= end ? [53, 57, 60, 64, 67] : prog[Math.floor(t / (bar * 2)) % 4]);
    const master = (t) => Math.min(1, t / 2.2) * Math.min(1, Math.max(0, (duration - 0.3 - t) / 2.5));
    const groove = (t) => Math.min(1, Math.max(0, (t - start + 0.2) / 1.5)) * (1 - Math.min(1, Math.max(0, (t - end) / 1.2)));
    // pad: detuned, soft harmonics, slow breathing filter
    for (let i = 0; i < n; i++) {
      const t = i / SR, ch = chordAt(t), m = master(t);
      if (m <= 0) continue;
      const br = 0.75 + 0.25 * Math.sin(TAU * 0.07 * t);
      let l = 0, r = 0;
      for (let k = 0; k < ch.length; k++) {
        const f = mtof(ch[k]);
        for (let h = 1; h <= 4; h++) {
          const a = (1 / (h * h)) * (h === 1 ? 1 : br);
          l += Math.sin(TAU * f * h * 1.0015 * t + k) * a; r += Math.sin(TAU * f * h * 0.9985 * t + k * 1.7) * a;
        }
      }
      const g = 0.020 * m;
      L[i] += l * g; R[i] += r * g;
    }
    // low end: a soft root on beats 1 and 3 (from the first scene)
    for (let b = Math.ceil(start / beat); b * beat < Math.min(duration, end + 2); b++) {
      if (b % 2) continue;
      const t0 = b * beat, f = mtof(chordAt(t0)[0] - 12), i0 = Math.floor(t0 * SR), len = Math.floor(beat * 1.9 * SR), gv = groove(t0) * 0.11 * master(t0);
      for (let j = 0; j < len; j++) { const e = Math.min(1, j / 400) * Math.exp(-j / (SR * 0.55)), y = Math.sin(TAU * f * j / SR) * e * gv; put(i0 + j, y, y); }
    }
    // percussion: a round kick on 1 and 3, a closed hat on the off-beats, all quiet
    for (let b = Math.ceil(start / beat); b * beat < end; b++) {
      const t0 = b * beat, gv = groove(t0) * master(t0), i0 = Math.floor(t0 * SR);
      if (b % 2 === 0) for (let j = 0; j < 9000; j++) { const tt = j / SR, f = 48 + 90 * Math.exp(-tt * 28), y = Math.sin(TAU * f * tt) * Math.exp(-tt * 9) * 0.16 * gv; put(i0 + j, y, y); }
      const h0 = Math.floor((t0 + beat / 2) * SR);
      let hp = 0, prev = 0;
      for (let j = 0; j < 2600; j++) { const x = rnd() * 2 - 1; hp = 0.85 * (hp + x - prev); prev = x; const y = hp * Math.exp(-j / 420) * 0.022 * gv; put(h0 + j, y * 0.8, y); }
    }
    // pluck arpeggio (eighths), sent into the room
    const send = new Float32Array(n);
    const pat = [0, 2, 1, 3, 4, 3, 2, 1];
    for (let q = Math.ceil((start - 1.2) / (beat / 2)); q * beat / 2 < end + 1; q++) {
      const t0 = q * beat / 2, ch = chordAt(t0), note = ch[pat[q % 8] % ch.length] + 12, f = mtof(note), gv = Math.min(1, Math.max(0, (t0 - start + 1.2) / 2)) * master(t0) * (1 - Math.min(1, Math.max(0, (t0 - end) / 1.5)));
      if (gv <= 0) continue;
      const i0 = Math.floor(t0 * SR), len = Math.floor(0.9 * SR), pan = q % 2 ? 0.35 : -0.35, acc = q % 4 === 0 ? 1 : 0.7;
      for (let j = 0; j < len; j++) {
        const tt = j / SR, e = Math.min(1, j / 120) * Math.exp(-tt * 5.5);
        const y = (Math.sin(TAU * f * tt) + 0.35 * Math.sin(TAU * 2 * f * tt) * Math.exp(-tt * 9) + 0.12 * Math.sin(TAU * 3 * f * tt) * Math.exp(-tt * 14)) * e * 0.05 * gv * acc;
        put(i0 + j, y * (1 - pan), y * (1 + pan)); if (i0 + j < n) send[i0 + j] += y;
      }
    }
    const [rl, rr] = reverb(send, n, { mix: 0.9, size: 1.15 });
    for (let i = 0; i < n; i++) { L[i] += rl[i]; R[i] += rr[i]; }
  }
  // ---- riser into the opening, soft hit on the end card
  {
    const i0 = Math.floor(0.6 * SR), len = Math.floor((start - 0.75) * SR);
    let lp = 0;
    for (let j = 0; j < len; j++) { const u = j / len, a = 1 - Math.exp(-TAU * (300 + 4000 * u * u) / SR); lp += a * ((rnd() * 2 - 1) - lp); const y = lp * u * u * 0.11; put(i0 + j, y, y); }
    for (const [t0, gain] of [[start - 0.1, 0.5], [end + 0.7, 0.8]]) {
      const i1 = Math.floor(t0 * SR);
      for (let j = 0; j < SR * 2.5; j++) {
        const tt = j / SR, y = (Math.sin(TAU * (55 + 30 * Math.exp(-tt * 6)) * tt) * Math.exp(-tt * 2.2) * 0.22 + Math.sin(TAU * 1760 * tt) * Math.exp(-tt * 3) * 0.012 + Math.sin(TAU * 2637 * tt) * Math.exp(-tt * 4) * 0.008) * gain;
        put(i1 + j, y, y);
      }
    }
  }
  // ---- whooshes (device changes): band-passed noise, 0.6 s, rising, moving across the stereo field
  const whoosh = (w, dur, gain) => {
    const len = Math.floor(dur * SR), i0 = Math.floor((w - dur * 0.45) * SR);
    let lp = 0, lp2 = 0, hp = 0;
    for (let j = 0; j < len; j++) {
      const u = j / len, env = Math.pow(Math.sin(Math.PI * u), 2.2), x = rnd() * 2 - 1, fc = 300 + 4200 * Math.sin(Math.PI * u);
      const a = 1 - Math.exp(-TAU * fc / SR); lp += a * (x - lp); lp2 += a * (lp - lp2);
      hp += (1 - Math.exp(-TAU * 220 / SR)) * (lp2 - hp);
      const y = (lp2 - hp) * env * gain; put(i0 + j, y * (1.2 - u), y * (0.2 + u));
    }
  };
  for (const w of whooshes) whoosh(w, 0.75, 0.22);
  for (const w of swells) whoosh(w, 0.5, 0.09);
  // ---- clicks: short, soft, a little woody
  for (const t of clicks) {
    const i0 = Math.floor(t * SR);
    for (let j = 0; j < 1600; j++) { const e = Math.exp(-j / 160), y = (Math.sin(TAU * 1500 * j / SR) * 0.6 + Math.sin(TAU * 3100 * j / SR) * 0.25 + (rnd() * 2 - 1) * 0.2) * e * 0.06; put(i0 + j, y, y); }
  }
  for (const t of typing) {
    const i0 = Math.floor(t * SR), f = 2300 + rnd() * 900;
    for (let j = 0; j < 700; j++) { const e = Math.exp(-j / 70), y = Math.sin(TAU * f * j / SR) * e * 0.018; put(i0 + j, y, y * 0.9); }
  }
  // ---- chimes (a step is proven): two soft bell partials
  for (const t of chimes) {
    const i0 = Math.floor((t + 0.05) * SR);
    for (let j = 0; j < SR * 1.2; j++) { const tt = j / SR, y = (Math.sin(TAU * 1318.5 * tt) * Math.exp(-tt * 4) + 0.5 * Math.sin(TAU * 1975.5 * tt) * Math.exp(-tt * 6) + 0.2 * Math.sin(TAU * 2637 * tt) * Math.exp(-tt * 9)) * Math.min(1, j / 60) * 0.035; put(i0 + j, y * 0.8, y); }
  }
  // ---- counter rolls (a stamp's digits): fast ticks that slow down
  for (const t of rolls) {
    let tt = 0.1, gap = 0.028;
    while (tt < 1.3) {
      const i0 = Math.floor((t + tt) * SR);
      for (let j = 0; j < 500; j++) { const y = Math.sin(TAU * 3400 * j / SR) * Math.exp(-j / 55) * 0.022; put(i0 + j, y, y); }
      tt += gap; gap *= 1.11;
    }
  }
  // soft saturation keeps peaks round before the loudness chain
  for (let i = 0; i < n; i++) { L[i] = Math.tanh(L[i] * 1.2) / 1.2; R[i] = Math.tanh(R[i] * 1.2) / 1.2; }
  return { L, R };
}

export function writeWav(path, { L, R }) {
  const n = L.length, buf = Buffer.alloc(44 + n * 4);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) { buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(L[i] * 32767))), 44 + i * 4); buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(R[i] * 32767))), 46 + i * 4); }
  writeFileSync(path, buf);
}
