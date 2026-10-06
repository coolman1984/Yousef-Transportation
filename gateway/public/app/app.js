/* Trip Orders - driver page. Five steps: your trip, start, on the road, end, paper. Works without a network:
   every step is saved on the phone first and sent when possible. */
(function () {
  'use strict';
  var D = window.D, app = document.getElementById('app');
  var m = location.pathname.match(/^\/t\/([A-Za-z0-9_-]{16,64})/);
  D.token = m ? m[1] : '';
  var KEY = 'trip:' + D.token;
  var STEPS = ['trip', 'start', 'road', 'end', 'paper'];
  var S = { card: null, draft: null, photo: null, error: null, second: false, low: false, clockOff: false, tick: null, device: '' };

  function $(sel, root) { return (root || app).querySelector(sel); }
  function isoLocal(d) {
    var p = function (n) { return ('0' + n).slice(-2); }, o = -d.getTimezoneOffset(), sg = o >= 0 ? '+' : '-'; o = Math.abs(o);
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) + sg + p(Math.floor(o / 60)) + ':' + p(o % 60);
  }
  function save() { return D.outbox.saveDraft(S.draft); }
  function go(stage) { S.draft.stage = stage; S.photo = null; S.low = false; save(); draw(); window.scrollTo(0, 0); }
  function fmtTime(iso) { var d = new Date(iso); return isNaN(d) ? '' : ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function elapsed(iso) {
    var ms = Date.now() - new Date(iso).getTime(); if (!(ms > 0)) return '0:00';
    var mins = Math.floor(ms / 60000); return Math.floor(mins / 60) + ':' + ('0' + (mins % 60)).slice(-2);
  }

  /* ---------- pieces ---------- */
  function head() {
    var c = S.card || {};
    return '<header class="top"><div class="ttl"><b>' + D.esc(D.t('title')) + '</b>' + (c.no ? '<span class="no" dir="ltr">' + D.esc(c.no) + '</span>' : '') + '</div>' +
      '<div class="tools"><button class="chip" data-a="hc" aria-pressed="' + (document.documentElement.dataset.hc === '1') + '">' + D.esc(D.t('contrast')) + '</button>' +
      '<button class="chip" data-a="lang">' + D.esc(D.t('lang')) + '</button></div></header>';
  }
  function stepper(stage) {
    var idx = stage === 'done' ? STEPS.length : STEPS.indexOf(stage);
    return '<ol class="steps" aria-label="progress">' + STEPS.map(function (s, i) {
      return '<li class="' + (i < idx ? 'done' : i === idx ? 'now' : '') + '"' + (i === idx ? ' aria-current="step"' : '') + '><i>' + (i < idx ? '✓' : i + 1) + '</i><span>' + D.esc(D.t(s)) + '</span></li>';
    }).join('') + '</ol>';
  }
  function row(k, v) { return v ? '<div class="kv"><span>' + D.esc(D.t(k)) + '</span><b>' + D.esc(v) + '</b></div>' : ''; }
  function banners() {
    var b = '';
    if (S.second || D.secondDevice) b += '<div class="note warn" role="status"><b>' + D.esc(D.t('second')) + '</b><span>' + D.esc(D.t('second_b')) + '</span></div>';
    if (S.clockOff) b += '<div class="note warn" role="status">' + D.esc(D.t('server_time_off')) + '</div>';
    return b;
  }
  function photoBox(kind, labelKey) {
    var ph = S.photo;
    return '<div class="photo">' + (ph ? '<img alt="" src="' + ph.url + '"><div class="ok">✓ ' + D.esc(D.t('photo_ok')) + (ph.fallback ? ' · ' + D.esc(D.t('cam_gallery')) : '') + '</div>' : '') +
      '<button class="btn ' + (ph ? 'ghost' : 'big') + '" data-a="shoot" data-kind="' + kind + '">' + D.esc(D.t(ph ? 'retake' : labelKey)) + '</button>' +
      '<p class="hint">' + D.esc(D.t('stamp')) + '</p></div>';
  }
  function kmField(id, labelKey, val) {
    return '<label class="field" for="' + id + '"><span>' + D.esc(D.t(labelKey)) + '</span><input id="' + id + '" class="km" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" dir="ltr" value="' + D.esc(val || '') + '"><small>' + D.esc(D.t('km_hint')) + '</small></label>';
  }

  /* ---------- screens ---------- */
  function screenTrip() {
    var c = S.card, pax = (c.passengers || []).join('، ');
    return '<section class="card"><h1>' + D.esc(D.t('trip')) + '</h1>' + row('date', c.date) + row('driver', c.driverName) + row('car', [c.plate, c.vehicleType].filter(Boolean).join(' · ')) +
      row('dest', c.destination) + row('stops', (c.stops || []).join(' ← ')) + row('pax', pax || '') + '</section>' +
      '<p class="hint">' + D.esc(D.t('begin_hint')) + '</p><button class="btn big" data-a="begin">' + D.esc(D.t('begin')) + '</button>';
  }
  function screenStart() {
    return '<section class="card"><h1>' + D.esc(D.t('start')) + '</h1>' + photoBox('start_odo', 'odo_start') + kmField('km', 'km_start', S.draft.kmInput) + '</section>' +
      (S.error ? '<div class="note bad" role="alert">' + D.esc(S.error) + '</div>' : '') +
      '<button class="btn big" data-a="start">' + D.esc(D.t('confirm_start')) + '</button>' +
      (S.photo ? '' : '<button class="link" data-a="start-nophoto">' + D.esc(D.t('skip_photo')) + '</button>');
  }
  function screenRoad() {
    var d = S.draft;
    return '<section class="card live"><h1><span class="pulse"></span>' + D.esc(D.t('running')) + '</h1>' + row('since', fmtTime(d.startAt)) +
      '<div class="kv"><span>' + D.esc(D.t('elapsed')) + '</span><b id="el" dir="ltr">' + elapsed(d.startAt) + '</b></div>' + row('km_start', d.startKm != null ? String(d.startKm) : '') +
      row('dest', S.card.destination) + '</section>' +
      '<div id="notebox"></div><button class="btn ghost" data-a="note">' + D.esc(D.t('note')) + '</button>' +
      '<button class="btn big" data-a="finish">' + D.esc(D.t('finish')) + '</button>';
  }
  function screenEnd() {
    var d = S.draft, route = d.routeInput != null ? d.routeInput : (S.card.destination || '');
    return '<section class="card"><h1>' + D.esc(D.t('end')) + '</h1>' + photoBox('end_odo', 'odo_end') + kmField('km', 'km_end', d.kmInput) +
      '<label class="field" for="route"><span>' + D.esc(D.t('route')) + '</span><textarea id="route" rows="2">' + D.esc(route) + '</textarea><small>' + D.esc(D.t('route_hint')) + '</small></label></section>' +
      (S.low ? '<div class="note warn" role="alert"><b>' + D.esc(D.t('end_low')) + '</b></div><button class="btn ghost" data-a="check">' + D.esc(D.t('check_km')) + '</button><button class="btn big" data-a="end-force">' + D.esc(D.t('end_low_send')) + '</button>' :
        (S.error ? '<div class="note bad" role="alert">' + D.esc(S.error) + '</div>' : '') + '<button class="btn big" data-a="end">' + D.esc(D.t('confirm_end')) + '</button>' +
        (S.photo ? '' : '<button class="link" data-a="end-nophoto">' + D.esc(D.t('skip_photo')) + '</button>'));
  }
  function screenPaper() {
    return '<section class="card"><h1>' + D.esc(D.t('paper_t')) + '</h1><p class="hint">' + D.esc(D.t('paper_hint')) + '</p>' + photoBox('paper', 'paper_t') + '</section>' +
      (S.photo ? '<button class="btn big" data-a="paper">' + D.esc(D.t('send')) + '</button>' : '') + '<button class="link" data-a="skip-paper">' + D.esc(D.t('skip_paper')) + '</button>';
  }
  function screenDone() {
    var d = S.draft;
    return '<section class="card centre"><div class="big-ok">✓</div><h1>' + D.esc(D.t('thanks')) + '</h1><p>' + D.esc(D.t('thanks_b')) + '</p>' +
      (d.paperDone ? '' : '<div class="note warn">' + D.esc(D.t('paper_missing')) + '</div><button class="btn big" data-a="to-paper">' + D.esc(D.t('paper_t')) + '</button>') + '</section><div id="items"></div>';
  }
  function screenGone(why) {
    var k = why === 'cancelled' ? ['cancelled', 'cancelled_b'] : why === 'expired' ? ['expired', 'expired_b'] : ['unknown', 'unknown_b'];
    return '<section class="card centre"><div class="big-ok bad">!</div><h1>' + D.esc(D.t(k[0])) + '</h1><p>' + D.esc(D.t(k[1])) + '</p></section>';
  }

  /* ---------- sync bar ---------- */
  function syncBar() {
    var box = $('#sync'); if (!box) return;
    D.outbox.items(KEY).then(function (items) {
      var waiting = items.filter(function (i) { return !i.sentAt && !i.error; }).length, failed = items.filter(function (i) { return i.error; }).length, sent = items.filter(function (i) { return i.sentAt; }).length;
      var atOffice = items.filter(function (i) { return i.officeAt; }).length;       // sent = in the mailbox; atOffice = the office has stored it
      var off = !navigator.onLine || D.outbox.online === false;
      var html;
      if (failed) html = '<button class="sync bad" data-a="retry">! ' + D.esc(D.t('failed')) + '</button>';
      else if (waiting) html = '<div class="sync wait">✓ ' + D.esc(D.t('saved_here')) + ' · ' + D.esc(D.t('n_waiting', { n: waiting })) + (off ? '<br><small>' + D.esc(D.t('offline')) + '</small>' : '') + '</div>';
      else if (sent && atOffice === sent) html = '<div class="sync ok">✓✓✓ ' + D.esc(D.t('all_sent')) + '</div>';
      else if (sent) html = '<div class="sync wait">✓✓ ' + D.esc(D.t('all_at_mailbox')) + '</div>';
      else html = '';
      box.innerHTML = html;
      var list = $('#items');
      if (list) list.innerHTML = items.map(function (i) {
        var st = i.officeAt ? '✓✓✓ ' + D.t('received') : i.sentAt ? '✓✓ ' + D.t('at_mailbox') : i.error ? '! ' + D.t('failed') : '✓ ' + D.t('saved_here');
        var name = i.kind === 'photo' ? ({ start_odo: D.t('odo_start'), end_odo: D.t('odo_end'), paper: D.t('paper_t') }[i.photoKind] || i.photoKind) : ({ start: D.t('start'), end: D.t('end'), note: D.t('note'), route: D.t('route') }[JSON.parse(i.json).type] || '');
        return '<div class="item ' + (i.officeAt ? 'ok' : i.error ? 'bad' : 'wait') + '"><span>' + D.esc(name) + '</span><b>' + D.esc(st) + '</b></div>';
      }).join('');
    });
  }

  /* ---------- drawing ---------- */
  function draw() {
    clearInterval(S.tick);
    if (D.gone) { app.innerHTML = head() + '<main>' + screenGone(D.goneWhy) + '</main>'; return; }
    var st = S.draft.stage, body = { trip: screenTrip, start: screenStart, road: screenRoad, end: screenEnd, paper: screenPaper, done: screenDone }[st]();
    app.innerHTML = head() + '<main>' + stepper(st) + banners() + body + '</main><footer id="sync" aria-live="polite"></footer>';
    if (st === 'road') S.tick = setInterval(function () { var e = $('#el'); if (e) e.textContent = elapsed(S.draft.startAt); }, 20000);
    syncBar();
  }

  /* ---------- actions ---------- */
  function newEvent(type, data) {
    var e = { uuid: D.outbox.uuid(), v: 1, type: type, tripId: S.card.tripId || '', deviceId: S.device, seq: (S.draft.seq = (S.draft.seq || 0) + 1), phoneAt: isoLocal(new Date()), queued: false, data: data };
    return D.outbox.add({ kind: 'event', uuid: e.uuid, token: D.token, tripKey: KEY, json: JSON.stringify(e) }).then(function () { return e; });
  }
  function addPhoto(kind, ph, eventUuid) {
    return D.outbox.add({ kind: 'photo', uuid: D.outbox.uuid(), token: D.token, tripKey: KEY, photoKind: kind, blob: ph.blob, sha: ph.sha, fallback: ph.fallback, eventUuid: eventUuid });
  }
  function readKm() {
    var el = $('#km'); if (!el) return null;
    var v = D.digits(el.value).replace(/[^0-9]/g, ''); return v === '' ? null : parseInt(v, 10);
  }
  function fail(msg) { S.error = D.t(msg); draw(); }

  var actions = {
    lang: function () { D.setLang(D.lang === 'ar' ? 'en' : 'ar'); draw(); },
    reload: function () { location.reload(); },
    hc: function () { var on = document.documentElement.dataset.hc !== '1'; document.documentElement.dataset.hc = on ? '1' : '0'; try { localStorage.setItem('to.hc', on ? '1' : '0'); } catch (e) { /* ignore */ } draw(); },
    begin: function () { go('start'); },
    shoot: function (btn) {
      var kind = btn.dataset.kind;
      D.camera.capture({ no: S.card.no, plate: S.card.plate }).then(function (ph) {
        if (S.photo && S.photo.url) URL.revokeObjectURL(S.photo.url);
        S.photo = ph; S.error = null;
        var km = $('#km'), route = $('#route'); if (km) S.draft.kmInput = km.value; if (route) S.draft.routeInput = route.value;
        draw();
      }, function (e) { if (e && e.message !== 'cancel') S.error = D.t('cam_denied'); draw(); });
    },
    start: function () { doStart(true); },
    'start-nophoto': function () { doStart(false); },
    finish: function () { S.draft.kmInput = ''; go('end'); },
    check: function () { S.low = false; draw(); },
    end: function () { doEnd(false, true); },
    'end-nophoto': function () { doEnd(false, false); },
    'end-force': function () { doEnd(true, !!S.photo); },
    paper: function () { addPhoto('paper', S.photo, null).then(function () { S.draft.paperDone = true; go('done'); }); },
    'skip-paper': function () { go('done'); },
    'to-paper': function () { go('paper'); },
    retry: function () { D.outbox.retryFailed(KEY); },
    note: function () {
      var box = $('#notebox');
      box.innerHTML = '<label class="field"><span>' + D.esc(D.t('note')) + '</span><textarea id="notetxt" rows="2" placeholder="' + D.esc(D.t('note_ph')) + '"></textarea></label><button class="btn" data-a="note-send">' + D.esc(D.t('send')) + '</button>';
      $('#notetxt').focus();
    },
    'note-send': function () {
      var t = ($('#notetxt') || {}).value || ''; if (!t.trim()) return;
      newEvent('note', { text: t.trim().slice(0, 500) }).then(function () { save(); $('#notebox').innerHTML = ''; syncBar(); });
    },
  };
  function doStart(withPhoto) {
    var km = readKm();
    if (km === null) return fail('km_required');
    S.error = null;
    var ph = withPhoto ? S.photo : null;
    newEvent('start', { startKm: km }).then(function (e) {
      S.draft.startKm = km; S.draft.startAt = e.phoneAt; S.draft.kmInput = '';
      return ph ? addPhoto('start_odo', ph, e.uuid) : null;
    }).then(function () { go('road'); });
  }
  function doEnd(force, withPhoto) {
    var km = readKm(), route = ($('#route') || {}).value || '';
    if (km === null) return fail('km_required');
    S.draft.routeInput = route;
    if (!force && S.draft.startKm != null && km < S.draft.startKm) { S.low = true; S.draft.kmInput = String(km); draw(); return; }
    S.error = null;
    var ph = withPhoto ? S.photo : null;
    var stops = route.split(/\s*[-←>،,]\s*/).filter(Boolean).slice(0, 12);
    newEvent('end', { endKm: km, routeText: route.trim().slice(0, 300), stops: stops }).then(function (e) {
      S.draft.endKm = km; S.draft.endAt = e.phoneAt;
      return ph ? addPhoto('end_odo', ph, e.uuid) : null;
    }).then(function () { go('paper'); });
  }

  app.addEventListener('click', function (e) {
    var b = e.target.closest('[data-a]'); if (!b || !actions[b.dataset.a]) return;
    actions[b.dataset.a](b);
  });
  app.addEventListener('input', function (e) {
    if (!S.draft) return;
    if (e.target.id === 'km') { S.draft.kmInput = e.target.value; save(); }
    if (e.target.id === 'route') { S.draft.routeInput = e.target.value; save(); }
  });
  D.outbox.onchange(function () { if (D.gone && S.draft) draw(); else syncBar(); });
  window.addEventListener('online', syncBar); window.addEventListener('offline', syncBar);

  /* ---------- start ---------- */
  function boot() {
    try { if (localStorage.getItem('to.hc') === '1') document.documentElement.dataset.hc = '1'; } catch (e) { /* ignore */ }
    if (!D.token) { app.innerHTML = head() + '<main>' + screenGone('unknown') + '</main>'; return; }
    app.innerHTML = head() + '<main><p class="boot">' + D.esc(D.t('loading')) + '</p></main>';
    Promise.all([D.outbox.deviceId(), D.outbox.getDraft(KEY)]).then(function (r) {
      S.device = r[0]; S.draft = r[1];
      // offline: the copy of the card kept on this phone with the draft is enough to carry on
      return fetch('/api/card/' + D.token, { cache: 'no-cache' }).catch(function (e) { if (S.draft && S.draft.card) return { offlineCard: true }; throw e; });
    }).then(function (res) {
      if (res.offlineCard) return { card: S.draft.card };
      if (res.status === 404) { app.innerHTML = head() + '<main>' + screenGone('unknown') + '</main>'; return null; }
      if (res.status === 410) return res.json().then(function (j) { D.gone = true; D.goneWhy = j.cancelled ? 'cancelled' : 'expired'; draw0(); return null; });
      return res.json();
    }).then(function (j) {
      if (!j) return;
      S.card = j.card;
      if (j.serverTime && Math.abs(Date.now() - new Date(j.serverTime).getTime()) > 10 * 60000) S.clockOff = true;
      if (!S.draft) {
        var st = S.card.status;
        S.draft = { key: KEY, stage: st === 'started' ? 'road' : (st === 'finished' || st === 'closed') ? 'done' : 'trip', startAt: S.card.startAt || null, startKm: S.card.startKm != null ? S.card.startKm : null };
        if (S.draft.stage === 'done') S.draft.paperDone = true;
      }
      return fetch('/api/bind/' + D.token, { method: 'POST', body: JSON.stringify({ deviceId: S.device }) }).then(function (r) { return r.json(); }).then(function (b) { if (b && b.secondDevice) S.second = true; }, function () { /* offline: bound with the first event */ });
    }).then(function () {
      if (!S.card) return;
      S.draft.card = S.card; save(); draw(); D.outbox.kick(true);
    }, function () {
      app.innerHTML = head() + '<main><section class="card centre"><div class="big-ok bad">!</div><h1>' + D.esc(D.t('offline')) + '</h1><button class="btn big" data-a="reload">' + D.esc(D.t('tryagain')) + '</button></section></main>';
    });
  }
  function draw0() { app.innerHTML = head() + '<main>' + screenGone(D.goneWhy) + '</main>'; }
  app.addEventListener('click', function (e) { var b = e.target.closest('[data-a="lang"],[data-a="hc"]'); if (b && !S.draft) { actions[b.dataset.a](); if (!S.card) boot(); } });

  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () { /* the page works without it */ });
  boot();
})();
