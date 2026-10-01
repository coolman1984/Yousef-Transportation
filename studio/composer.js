/* The composer: renderAt(t) places everything for film time t (seconds). Pure: no timers, no running CSS animations. */
(function () {
  'use strict';
  const C = window.CUT, $ = (id) => document.getElementById(id);
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const ease = (u) => 1 - Math.pow(1 - clamp(u), 3);
  const easeIO = (u) => { u = clamp(u); return u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
  const spring = (u) => { u = clamp(u); return 1 - Math.exp(-6 * u) * Math.cos(7 * u); };          // soft settle
  const win = (t, a, b, fi = .5, fo = .5) => Math.min(ease((t - a) / fi), 1 - ease((t - (b - fo)) / fo));  // 0..1 visibility in [a, b]

  // frames of each device, by wall-clock time
  function frameAt(dev, wall) {
    const fr = C.frames[dev];
    let lo = 0, hi = fr.length - 1;
    if (wall <= fr[0][0]) return fr[0][1];
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (fr[m][0] <= wall) lo = m; else hi = m - 1; }
    return fr[lo][1];
  }
  const sceneAt = (t) => { let s = C.scenes[0]; for (const x of C.scenes) if (t >= x.film[0]) s = x; return s; };
  const wallAt = (s, t) => s.src[0] + clamp(t - s.film[0], 0, s.film[1] - s.film[0]) * (s.speed || 1);
  function deviceWall(dev, t) {
    // the latest scene of this device that has started (or the first one), so a device keeps its last picture when off screen
    let pick = null;
    for (const s of C.scenes) if (s.device === dev && (t >= s.film[0] || !pick)) pick = s;
    return wallAt(pick, t);
  }

  const imgs = {};
  function setImg(el, src) {
    if (el.dataset.src === src) return Promise.resolve();
    el.dataset.src = src;
    return new Promise((ok) => { el.onload = el.onerror = () => ok(); el.src = src; }).then(() => el.decode ? el.decode().catch(() => {}) : null);
  }

  // build the chips once
  $('chips').innerHTML = C.chips.map((c, i) => '<li id="chip' + i + '"><i>' + (i + 1) + '</i><span>' + c.label + '</span><em>' + (c.value || '') + '</em></li>').join('');
  $('ano').textContent = C.actor.no;
  $('ameta').innerHTML = C.actor.meta;

  window.renderAt = async function (t) {
    const s = sceneAt(t), jobs = [];
    // ---- which device is on screen, and the slide between them (the foreground is the transition)
    const devs = { office: 0, phone: 0 };
    for (const x of C.scenes) {
      const v = win(t, x.film[0] - (x.enter || 0), x.film[1] + (x.leave || 0), .6, .6);
      devs[x.device] = Math.max(devs[x.device], v);
    }
    const tEnd = C.outro.t0;
    const fadeEnd = 1 - ease((t - tEnd) / .8);
    const O = devs.office * fadeEnd, P = devs.phone * fadeEnd;
    // a slow push over the reading holds (max 3 %)
    const push = 1 + 0.03 * easeIO((t - s.film[0]) / Math.max(1, s.film[1] - s.film[0]));
    const w = $('win');
    w.style.opacity = O.toFixed(3);
    w.style.transform = `translateX(${(-80 * (1 - O)).toFixed(1)}px) scale(${(0.97 + 0.03 * O).toFixed(4)})`;
    w.classList.toggle('hide', O < 0.002);
    const ph = $('phone');
    ph.style.opacity = P.toFixed(3);
    ph.style.transform = `translateY(${(60 * (1 - P)).toFixed(1)}px)`;
    ph.classList.toggle('hide', P < 0.002);
    if (O > 0.002) jobs.push(setImg($('ofr'), frameAt('office', deviceWall('office', t))));
    if (P > 0.002) jobs.push(setImg($('pfr'), frameAt('phone', deviceWall('phone', t))));
    // camera: still and wide; the gentle push, and at most a soft 3-4 % look at a detail
    let z = push, ox = 50, oy = 50;
    for (const f of C.focus || []) {
      const k = spring((t - f.t0) / 1.2) * (1 - easeIO((t - (f.t1 - 1.0)) / 1.0));
      if (t >= f.t0 && t <= f.t1) { z = push * (1 + (f.s - 1) * clamp(k)); ox = f.x; oy = f.y; }
    }
    $('ofr').style.transformOrigin = ox + '% ' + oy + '%';
    $('ofr').style.transform = `scale(${z.toFixed(4)})`;
    // ---- the side text next to the phone
    const side = $('side');
    side.innerHTML = s.side || '';
    side.style.left = '1000px';
    side.style.opacity = (P * (s.side ? 1 : 0)).toFixed(3);
    // ---- opening: frame 0 is already a finished composition
    const op = 1 - ease((t - C.open.t1) / .7);
    $('open').style.opacity = op.toFixed(3);
    $('open').style.transform = `translateY(${(-30 * (1 - op)).toFixed(1)}px)`;
    // ---- chapter title: enters while the previous scene is still leaving
    const title = $('title');
    const tv = win(t, s.film[0] - .25, s.film[1] + .1, .55, .35) * (t < C.open.t1 ? 0 : 1) * fadeEnd;
    $('tk').textContent = s.kicker || ''; $('tt').textContent = s.title || '';
    title.style.opacity = tv.toFixed(3);
    title.style.transform = `translateY(${(14 * (1 - tv)).toFixed(1)}px)`;
    // ---- captions
    let cap = null;
    for (const c of C.captions) if (t >= c.t0 && t <= c.t1) cap = c;
    const cv = cap ? win(t, cap.t0, cap.t1, .35, .35) * fadeEnd : 0;
    $('cap').innerHTML = cap ? cap.text : '';
    $('cap').style.opacity = cv.toFixed(3);
    $('cap').style.transform = `translateY(${(-10 * (1 - cv)).toFixed(1)}px)`;
    // ---- the actor card (stays all film) and its chips (filled when the step was proven)
    const av = ease((t - C.open.t1 + .2) / .8) * fadeEnd;
    $('actor').style.opacity = av.toFixed(3);
    $('actor').style.transform = `translateX(${(40 * (1 - av)).toFixed(1)}px)`;
    C.chips.forEach((c, i) => {
      const el = $('chip' + i), on = t >= c.t;
      el.classList.toggle('on', on);
      const k = on ? spring((t - c.t) / .6) : 0;
      el.style.transform = on ? `scale(${(1 + 0.06 * (1 - clamp(k))).toFixed(3)})` : '';
    });
    // ---- stamps (one at a time), in their own zone under the card
    let st = null;
    for (const x of C.stamps) if (t >= x.t0 && t <= x.t1) st = x;
    const sv = st ? win(t, st.t0, st.t1, .45, .4) * fadeEnd : 0;
    const top = 150 + $('actor').offsetHeight + 22;
    $('stamp').style.top = top + 'px';
    $('sv').textContent = st ? st.value : ''; $('sl').textContent = st ? st.label : '';
    $('stamp').style.opacity = sv.toFixed(3);
    $('stamp').style.transform = st ? `translateY(${(24 * (1 - spring((t - st.t0) / .7))).toFixed(1)}px)` : '';
    // ---- end card, then the only fade of the film
    const ev = ease((t - tEnd - .3) / .9);
    $('ea').innerHTML = C.outro.a; $('eb').textContent = C.outro.b; $('ec').textContent = C.outro.c;
    $('end').style.opacity = ev.toFixed(3);
    $('end').style.transform = `translateY(${(20 * (1 - ev)).toFixed(1)}px)`;
    $('black').style.opacity = ease((t - (C.duration - 1.0)) / 1.0).toFixed(3);
    await Promise.all(jobs);
    return true;
  };
  window.FILM = { duration: C.duration, fps: C.fps };
})();
