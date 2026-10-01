/* The composer: renderAt(t) places everything for film time t (seconds). Pure: no timers, no running CSS animations.
   A still frame (1920x1080). The devices move under one camera: the cut bakes a smoothed track (fx, fy, z) per device,
   here it only becomes transforms. The rail on the right carries the chapter, the trip we follow, its steps and the proof. */
(function () {
  'use strict';
  const C = window.CUT, $ = (id) => document.getElementById(id), FPS = C.fps;
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, u) => a + (b - a) * u;
  const outCubic = (u) => 1 - Math.pow(1 - clamp(u), 3);
  const outQuint = (u) => 1 - Math.pow(1 - clamp(u), 5);
  const outExpo = (u) => { u = clamp(u); return u >= 1 ? 1 : 1 - Math.pow(2, -10 * u); };
  const inOutCubic = (u) => { u = clamp(u); return u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
  const inOutSine = (u) => -(Math.cos(Math.PI * clamp(u)) - 1) / 2;
  const outBack = (u) => { u = clamp(u); const c1 = 1.6, c3 = c1 + 1; return 1 + c3 * Math.pow(u - 1, 3) + c1 * Math.pow(u - 1, 2); };
  const f3 = (x) => x.toFixed(3), f1 = (x) => x.toFixed(1);

  // ---------- geometry
  const ZONE = { cx: 750, cy: 540 };                         // the shot's centre (the rail takes x > 1500)
  const OFF = { s0: 1.05, bar: 36, w: 1280, h: 800 };
  const PH = { s0: 1.09, pad: 14, w: 393, h: 851, cx: 1010, cy: 540 };
  const runs = [];                                           // consecutive scenes on one device
  for (const s of C.scenes) { const r = runs[runs.length - 1]; if (r && r.device === s.device) { r.b = s.film[1]; r.scenes.push(s); } else runs.push({ device: s.device, a: s.film[0], b: s.film[1], scenes: [s] }); }
  runs.forEach((r, i) => { r.first = i === 0; r.last = i === runs.length - 1; });

  // ---------- footage: frames by wall-clock time; scene time maps (speed ramps) baked by the cut
  function frameAt(dev, wall) {
    const fr = C.frames[dev];
    if (wall <= fr[0][0]) return fr[0][1];
    let lo = 0, hi = fr.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (fr[m][0] <= wall) lo = m; else hi = m - 1; }
    return fr[lo][1];
  }
  function wallAt(s, t) {
    const q = clamp((t - s.film[0]) * FPS, 0, s.map.length - 1), i = Math.floor(q), u = q - i;
    return s.src[0] + lerp(s.map[i], s.map[Math.min(i + 1, s.map.length - 1)], u);
  }
  function deviceWall(dev, t) {
    let pick = null;
    for (const s of C.scenes) if (s.device === dev && (t >= s.film[0] || !pick)) pick = s;
    return wallAt(pick, t);
  }
  function cam(dev, t) {
    const tr = C.camera[dev], q = clamp(t * FPS, 0, tr.length - 1), i = Math.floor(q), u = q - i, a = tr[i], b = tr[Math.min(i + 1, tr.length - 1)];
    // a breath of life on top of the track: never more than a few pixels, never felt as shake
    return [lerp(a[0], b[0], u) + 2.4 * Math.sin(t * 0.41), lerp(a[1], b[1], u) + 1.8 * Math.sin(t * 0.33 + 1.3), lerp(a[2], b[2], u) * (1 + 0.004 * Math.sin(t * 0.27 + .5))];
  }
  function setImg(el, src) {
    if (el.dataset.src === src) return Promise.resolve();
    el.dataset.src = src;
    return new Promise((ok) => { el.onload = el.onerror = () => ok(); el.src = src; }).then(() => (el.decode ? el.decode().catch(() => {}) : null));
  }

  // ---------- words that rise out of a mask
  const words = (txt) => txt.split(' ').map((w) => '<span class="w"><span>' + w + '</span></span>').join(' ');
  function rise(el, t0, t, { stagger = 0.065, dur = 0.8, dist = 105, out = null } = {}) {
    const ws = el.querySelectorAll('.w > span');
    ws.forEach((w, i) => {
      const k = outExpo((t - t0 - i * stagger) / dur);
      let y = dist * (1 - k), o = clamp(k * 1.6);
      if (out != null) { const x = inOutCubic((t - out - i * 0.03) / 0.45); y -= 70 * x; o *= 1 - x; }
      w.style.transform = `translateY(${f1(y)}%)`; w.style.opacity = f3(o);
    });
  }

  // ---------- build once
  $('ano').textContent = C.actor.no;
  $('ameta').innerHTML = C.actor.meta.join('<br>');
  $('steps').innerHTML = '<div class="rail-line" id="rl"></div><div class="rail-fill" id="rf"></div><div class="halo" id="halo"></div>' + C.chips.map((c, i) =>
    '<li id="st' + i + '"><span class="dot"><span class="fill"></span><svg viewBox="0 0 12 12"><path d="M2 6.5 L5 9 L10 3"/></svg></span><span class="lab">' + c.label + '</span><span class="val">' + (c.value || '') + '</span></li>').join('');
  const STEP_H = 39;
  $('rl').style.height = ((C.chips.length - 1) * STEP_H) + 'px';
  $('rf').style.height = ((C.chips.length - 1) * STEP_H) + 'px';
  $('oa').innerHTML = words('أمر تشغيل واحد') + '<br><span class="am">' + words('من الطلب للتقرير') + '</span>';
  $('ea').innerHTML = words(C.outro.a[0]) + '<br><span class="am">' + words(C.outro.a[1]) + '</span><br>' + words(C.outro.a[2]);
  $('eb').textContent = C.outro.b; $('ect').textContent = C.outro.c;
  (function grain() {
    const cv = $('grain'); cv.width = 1024; cv.height = 604; cv.style.width = '2048px'; cv.style.height = '1208px';
    const g = cv.getContext('2d'), im = g.createImageData(1024, 604); let s = 12345;
    for (let i = 0; i < im.data.length; i += 4) { s = (s * 1664525 + 1013904223) >>> 0; const v = s >>> 24; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
    g.putImageData(im, 0, 0);
  })();
  let titleKey = '', stampKey = '', sideKey = '';
  const rollCols = [];
  function buildStamp(st) {
    const txt = st.sep ? Number(st.n).toLocaleString('en-US') : String(st.n);
    rollCols.length = 0;
    let html = '<span class="digits">';
    [...txt].forEach((ch) => {
      if (/\d/.test(ch)) { html += '<span class="col"><div>' + Array.from({ length: 20 }, (_, k) => '<span>' + (k % 10) + '</span>').join('') + '</div></span>'; rollCols.push(+ch); }
      else html += '<span>' + ch + '</span>';
    });
    html += '</span>' + (st.unit ? '<span class="unit">' + st.unit + '</span>' : '');
    $('sv').innerHTML = html; $('sl').textContent = st.label;
  }

  window.renderAt = async function (t) {
    const jobs = [];
    const tEnd = C.outro.t0;
    // ---------- background life
    $('b1').style.transform = `translate(${f1(980 + 120 * Math.sin(t * 0.07))}px, ${f1(-120 + 80 * Math.cos(t * 0.05))}px)`;
    $('b2').style.transform = `translate(${f1(-200 + 160 * Math.cos(t * 0.045))}px, ${f1(420 + 90 * Math.sin(t * 0.06))}px)`;
    $('grain').style.transform = `translate(${-(Math.floor(t * 24) * 37 % 64)}px, ${-(Math.floor(t * 24) * 53 % 64)}px)`;

    // ---------- devices: presence, entrances, exits
    const pres = { office: { v: 0, mode: '', k: 0 }, phone: { v: 0, mode: '', k: 0 } };
    for (const r of runs) {
      const P = pres[r.device];
      let inK, outK = 0;
      if (r.first) inK = inOutCubic((t - 2.0) / 2.1);                           // the opening fly-in
      else inK = outExpo((t - (r.a - 0.25)) / 1.05);
      if (r.last) outK = inOutCubic((t - (r.b + 0.15)) / 1.5);                     // the closing pull-away
      else outK = inOutCubic((t - (r.b - 0.3)) / 0.75);
      const v = Math.min(inK, 1 - outK);
      if (t >= (r.first ? 0 : r.a - 0.3) && t <= r.b + (r.last ? 1.7 : 0.5) && v > P.v - 1e-6) {
        P.v = v; P.mode = inK < 1 ? 'in' : outK > 0 ? 'out' : 'on'; P.k = inK < 1 ? inK : outK; P.first = r.first; P.last = r.last;
      }
    }
    const fadeEnd = 1 - outCubic((t - tEnd - 0.2) / 1.0);

    // office
    {
      const P = pres.office, rig = $('rigO');
      rig.classList.toggle('hide', P.v < 0.002);
      if (P.v >= 0.002) {
        let [fx, fy, z] = cam('office', t);
        const S = OFF.s0 * z;
        const hx = (ZONE.cx - 70) / S, hy = (ZONE.cy - 54) / S;                      // keep the window filling the shot when pushed in
        fx = hx < OFF.w / 2 ? clamp(fx, hx, OFF.w - hx) : OFF.w / 2;
        let vy = fy + OFF.bar; vy = hy < (OFF.h + OFF.bar) / 2 ? clamp(vy, hy, OFF.h + OFF.bar - hy) : (OFF.h + OFF.bar) / 2;
        $('win').style.transform = `translate3d(${f1(ZONE.cx - fx * S)}px, ${f1(ZONE.cy - vy * S)}px, 0) scale(${S.toFixed(4)})`;
        let tf = '', op = 1;
        if (P.mode === 'in' && P.first) { const k = P.k; tf = `translate3d(0, ${f1(90 * (1 - k))}px, ${f1(-900 * (1 - k))}px) rotateX(${f1(24 * (1 - k))}deg) rotateY(${f1(-16 * (1 - k))}deg)`; op = clamp(k * 2.2); }
        else if (P.mode === 'in') { const k = P.k; tf = `translate3d(${f1(-60 * (1 - k))}px, 0, ${f1(-260 * (1 - k))}px)`; op = clamp(k * 1.4); }
        else if (P.mode === 'out' && P.last) { const k = P.k; tf = `translate3d(0, ${f1(-40 * k)}px, ${f1(-700 * k)}px) rotateX(${f1(14 * k)}deg)`; op = 1 - k; }
        else if (P.mode === 'out') { const k = P.k; tf = `translate3d(${f1(-120 * k)}px, 0, ${f1(-420 * k)}px) rotateY(${f1(10 * k)}deg)`; op = 1 - k; }
        rig.style.transformOrigin = `${ZONE.cx}px ${ZONE.cy}px`;
        rig.style.transform = tf; rig.style.opacity = f3(op);
        const wall = deviceWall('office', t);
        jobs.push(setImg($('ofr'), frameAt('office', wall)));
        // the cursor follows the recorded path at the same wall time as the picture
        const cu = C.cursor; let x = null, y = null;
        if (cu.length && wall >= cu[0][0]) {
          let lo = 0, hi = cu.length - 1;
          while (lo < hi) { const m = (lo + hi + 1) >> 1; if (cu[m][0] <= wall) lo = m; else hi = m - 1; }
          const a = cu[lo], b = cu[Math.min(lo + 1, cu.length - 1)], u = b[0] > a[0] ? clamp((wall - a[0]) / (b[0] - a[0])) : 0;
          x = lerp(a[1], b[1], u); y = lerp(a[2], b[2], u);
        }
        let press = 1, rip = null;
        for (const c of C.clicks) if (c.dev === 'office') {
          const d = t - c.t;
          if (d > -0.12 && d < 0.3) press = Math.min(press, 1 - 0.16 * Math.sin(Math.PI * clamp((d + 0.12) / 0.42)));
          if (d >= 0 && d < 0.7) rip = { c, d };
        }
        $('cursor').style.display = x == null ? 'none' : '';
        if (x != null) $('cursor').style.transform = `translate(${f1(x - 2)}px, ${f1(y - 2)}px) scale(${f3(press)})`;
        const R = $('rip');
        if (rip) { const k = outCubic(rip.d / 0.7); R.style.display = ''; R.style.transform = `translate(${f1(rip.c.x)}px, ${f1(rip.c.y)}px) scale(${f3(0.3 + 0.9 * k)})`; R.style.opacity = f3(0.95 * (1 - k)); }
        else R.style.display = 'none';
      }
    }
    // phone
    {
      const P = pres.phone, rig = $('rigP');
      rig.classList.toggle('hide', P.v < 0.002);
      if (P.v >= 0.002) {
        let [fx, fy, z] = cam('phone', t);
        const S = PH.s0 * z, W = PH.w + 2 * PH.pad, H = PH.h + 2 * PH.pad;
        const hy = (ZONE.cy - 36) / S;
        let vy = fy + PH.pad; vy = hy < H / 2 ? clamp(vy, hy, H - hy) : H / 2;
        const vx = W / 2 + 0.25 * (fx + PH.pad - W / 2);
        $('phone').style.transform = `translate3d(${f1(PH.cx - vx * S)}px, ${f1(PH.cy - vy * S)}px, 0) scale(${S.toFixed(4)})`;
        let tf = '', op = 1;
        if (P.mode === 'in') { const k = P.k; tf = `translate3d(0, ${f1(220 * (1 - k))}px, ${f1(-300 * (1 - k))}px) rotateX(${f1(-16 * (1 - k))}deg)`; op = clamp(k * 1.6); }
        else if (P.mode === 'out') { const k = P.k; tf = `translate3d(${f1(80 * k)}px, ${f1(40 * k)}px, ${f1(-380 * k)}px) rotateY(${f1(-10 * k)}deg)`; op = 1 - k; }
        rig.style.transformOrigin = `${PH.cx}px ${PH.cy}px`;
        rig.style.transform = tf; rig.style.opacity = f3(op);
        jobs.push(setImg($('pfr'), frameAt('phone', deviceWall('phone', t))));
        let tap = null;
        for (const c of C.clicks) if (c.dev === 'phone') { const d = t - c.t; if (d > -0.18 && d < 0.55) tap = { c, d }; }
        const T = $('tap');
        if (tap) {
          const d = tap.d, k = d < 0 ? outCubic((d + 0.18) / 0.18) : 1, g = d > 0 ? outCubic(d / 0.55) : 0;
          T.style.display = ''; T.style.transform = `translate(${f1(tap.c.x)}px, ${f1(tap.c.y)}px) scale(${f3(0.55 + 0.45 * k + 0.5 * g)})`; T.style.opacity = f3(Math.min(k, 1 - g));
        } else T.style.display = 'none';
      }
    }
    // the light behind whichever device is on
    const gx = pres.phone.v > pres.office.v ? PH.cx : ZONE.cx;
    $('glow').style.transform = `translate(${f1(gx - 750)}px, ${f1(ZONE.cy - 450 + 60)}px)`;
    $('glow').style.opacity = f3(Math.max(pres.office.v, pres.phone.v) * 0.9);

    // ---------- current scene
    let s = C.scenes[0]; for (const x of C.scenes) if (t >= x.film[0] - 0.05) s = x;
    const si = C.scenes.indexOf(s), next = C.scenes[si + 1];

    // ---------- opening
    {
      const o = $('open'), out = inOutCubic((t - 1.85) / 0.8);
      o.classList.toggle('hide', t > 2.7);
      if (t <= 2.7) {
        rise($('oa'), 0.25, t, { stagger: 0.06, dur: 0.9 });
        $('os').style.opacity = f3(outCubic((t - 0.8) / 0.7));
        o.style.opacity = f3(1 - out);
        o.style.transform = `translateY(${f1(-60 * out)}px) scale(${f3(1 + 0.05 * out)})`;
      }
    }

    // ---------- rail
    const railIn = outExpo((t - (C.pre - 0.7)) / 1.1) * fadeEnd;
    $('rail').style.opacity = f3(clamp(railIn * 1.3));
    $('rail').style.transform = `translateX(${f1(-60 * (1 - railIn))}px)`;
    if (titleKey !== s.id) { titleKey = s.id; $('ttl').innerHTML = words(s.title); $('kn').textContent = s.kicker; $('kof').textContent = '/ ' + C.scenes[C.scenes.length - 1].kicker; }
    rise($('ttl'), s.film[0] - 0.05, t, { stagger: 0.06, dur: 0.85, out: next ? next.film[0] - 0.4 : null });
    const kk = outExpo((t - s.film[0]) / 0.9);
    $('kl').style.transform = `scaleX(${f3(kk)})`;
    $('kn').style.opacity = f3(clamp(kk * 1.4) * (next ? 1 - inOutCubic((t - (next.film[0] - 0.4)) / 0.4) : 1));
    // steps
    let last = -1;
    C.chips.forEach((c, i) => {
      const el = $('st' + i), d = t - c.t, on = d >= 0;
      if (on) last = i;
      el.classList.toggle('on', on);
      el.querySelector('.fill').style.transform = `scale(${f3(on ? outBack(d / 0.45) : 0)})`;
      el.querySelector('path').style.strokeDashoffset = f1(on ? 20 * (1 - outCubic((d - 0.12) / 0.35)) : 20);
      const v = el.querySelector('.val');
      v.style.opacity = f3(on ? outCubic((d - 0.15) / 0.5) : 0);
      v.style.transform = `translateX(${f1(on ? -14 * (1 - outExpo((d - 0.15) / 0.7)) : -14)}px)`;
    });
    C.chips.forEach((c, i) => $('st' + i).classList.toggle('cur', i === last));
    let fillTo = 0;
    if (last >= 0) { const prev = last > 0 ? last - 1 : 0, k = outExpo((t - C.chips[last].t) / 0.9); fillTo = lerp(prev, last, last > 0 ? k : 1) / (C.chips.length - 1); }
    $('rf').style.transform = `scaleY(${f3(fillTo)})`;
    const H = $('halo');
    if (last >= 0) { const d = t - C.chips[last].t, k = outCubic(d / 0.9); H.style.top = (last * STEP_H + 1) + 'px'; H.style.opacity = f3(d < 0.9 ? 1 - k : 0); H.style.transform = `scale(${f3(0.6 + 0.8 * k)})`; }
    else H.style.opacity = '0';
    // stamp
    let st = null; for (const x of C.stamps) if (t >= x.t0 - 0.05 && t <= x.t1 + 0.5) st = x;
    const S = $('stamp');
    if (st) {
      const key = st.t0 + ':' + st.n;
      if (key !== stampKey) { stampKey = key; buildStamp(st); }
      const ink = outExpo((t - st.t0) / 0.8), outk = inOutCubic((t - st.t1) / 0.45);
      S.style.opacity = f3(clamp(ink * 1.5) * (1 - outk) * fadeEnd);
      S.style.transform = `translateY(${f1(40 * (1 - ink) + 30 * outk)}px) scale(${f3(0.94 + 0.06 * ink)})`;
      S.querySelectorAll('.col > div').forEach((d, i) => {
        const n = rollCols.length, k = outQuint((t - st.t0 - 0.1 - (n - 1 - i) * 0.07) / 1.25);
        const start = 0, end = 10 + rollCols[i];
        d.style.transform = `translateY(${f1(-62 * lerp(start, end, k))}px)`;
      });
      $('sheen').style.transform = `translateX(${f1(lerp(420, -520, inOutSine((t - st.t0 - 0.9) / 0.9)))}px) rotate(18deg)`;
    } else S.style.opacity = '0';

    // ---------- captions
    let cap = null; for (const c of C.captions) if (t >= c.t0 - 0.05 && t <= c.t1 + 0.45) cap = c;
    const cv = cap ? outExpo((t - cap.t0) / 0.6) * (1 - inOutCubic((t - cap.t1) / 0.4)) * fadeEnd : 0;
    if (cap) $('capt').textContent = cap.text;
    $('cap').style.opacity = f3(cv);
    $('cap').style.transform = `translateY(${f1(18 * (1 - clamp(cv)))}px)`;

    // ---------- side text by the phone
    const sd = C.side[s.id];
    const side = $('side');
    if (sd && s.device === 'phone') {
      if (sideKey !== s.id) { sideKey = s.id; side.innerHTML = '<div class="k">' + sd.k + '</div>' + sd.l.map((l) => '<div class="ln">' + words(l) + '</div>').join(''); }
      side.style.opacity = '1';
      rise(side, s.film[0] + 0.45, t, { stagger: 0.05, dur: 0.9, out: s.film[1] - 0.45 });
      side.querySelector('.k').style.opacity = f3(outCubic((t - s.film[0] - 0.3) / 0.6) * (1 - inOutCubic((t - (s.film[1] - 0.45)) / 0.4)));
    } else side.style.opacity = '0';

    // ---------- end
    const E = $('end'), te = t - tEnd;
    E.classList.toggle('hide', te < 0.4);
    if (te >= 0.4) {
      rise($('ea'), tEnd + 0.75, t, { stagger: 0.075, dur: 1.0 });
      $('eb').style.opacity = f3(outCubic((te - 1.9) / 0.9));
      const ck = outExpo((te - 2.4) / 1.0);
      $('ec').style.opacity = f3(ck); $('ec').style.transform = `translateY(${f1(20 * (1 - ck))}px)`;
    }
    $('black').style.opacity = f3(Math.max(1 - outCubic(t / 0.7), inOutSine((t - (C.duration - 1.1)) / 1.1)));
    await Promise.all(jobs);
    return true;
  };
  window.FILM = { duration: C.duration, fps: C.fps };
})();
