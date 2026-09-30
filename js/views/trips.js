/* Trip Orders - the trip list, the trip side panel (details, photos, amendments, actions) and the new-trip dialog. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;

  /* ---------- helpers ---------- */
  function person(id) { return TO.data.name('people', id); }
  function vehiclePlate(id) { var v = TO.data.get('vehicles', id); return v ? v.plate : ''; }
  function passengers(t) {
    return TO.data.list('tripPassengers').filter(function (p) { return p.tripId === t.id; }).map(function (p) { return p.personId ? person(p.personId) : p.freeText; }).filter(Boolean);
  }
  function tripText(t) {
    return [t.no, vehiclePlate(t.vehicleId), TO.data.name('drivers', t.driverId), person(t.requesterId), t.destination, passengers(t).join(' '), TO.data.name('departments', t.departmentId)].join(' ');
  }
  TO.tripText = tripText;
  TO.tripLabel = function (t) { return t.no + ' · ' + (vehiclePlate(t.vehicleId) || '–') + ' · ' + (t.destination || ''); };

  function range(kind) {
    var now = new Date(), y = now.getFullYear(), m = now.getMonth(), iso = function (d) { return d.getFullYear() + '-' + TO.fmt.pad(d.getMonth() + 1) + '-' + TO.fmt.pad(d.getDate()); };
    if (kind === 'today') return [iso(now), iso(now)];
    if (kind === 'yesterday') { var yd = new Date(y, m, now.getDate() - 1); return [iso(yd), iso(yd)]; }
    if (kind === 'week') { var s = new Date(y, m, now.getDate() - ((now.getDay() + 1) % 7)); return [iso(s), iso(now)]; }
    if (kind === 'month') return [iso(new Date(y, m, 1)), iso(new Date(y, m + 1, 0))];
    if (kind === 'lastmonth') return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))];
    return ['0000-00-00', '9999-99-99'];
  }
  var RANGES = ['today', 'yesterday', 'week', 'month', 'lastmonth', 'all'];

  /* ---------- fields of a trip ---------- */
  function tripFields(withPassengers) {
    var f = [
      { key: 'date', label: 'f.date', type: 'date', required: true },
      { key: 'categoryId', label: 'f.category', type: 'ref', entity: 'tripCategories', required: true },
      { key: 'vehicleId', label: 'f.vehicle', type: 'ref', entity: 'vehicles' },
      { key: 'driverId', label: 'f.driver', type: 'ref', entity: 'drivers' },
      { key: 'requesterId', label: 'f.requester', type: 'ref', entity: 'people', allowNew: true },
      { key: 'departmentId', label: 'f.department', type: 'ref', entity: 'departments', allowNew: true }
    ];
    if (withPassengers) f.push({ key: 'passengersText', label: 'f.passengers', help: 'help.passengers' });
    f.push({ key: 'destination', label: 'f.destination', suggest: destinations, help: 'help.destination' },
      { key: 'purpose', label: 'f.purpose', help: 'help.purpose' }, { key: 'notes', label: 'f.notes', type: 'textarea' });
    return f;
  }
  function destinations() {
    var seen = {}, out = [];
    TO.data.list('trips').forEach(function (t) { var k = U.key(t.destination); if (t.destination && !seen[k]) { seen[k] = 1; out.push(t.destination); } });
    TO.data.list('routes').forEach(function (r) { if (r.name) out.push(r.name); });
    return out.sort();
  }

  /* ---------- new trip ---------- */
  function newTrip() {
    if (!TO.can('trips.create')) { TO.toast(TO.t('err.noPerm'), 'bad'); return; }
    if (!TO.data.state) return;
    if (!TO.data.list('tripCategories').length) {
      TO.dialog({ title: TO.t('trip.new'), body: U.empty('layers', TO.t('trip.needCats.t'), TO.t('trip.needCats.b'), TO.can('categories.manage') ? '<a class="btn primary" href="#/settings?tab=rules" data-close>' + TO.esc(TO.t('trip.needCats.go')) + '</a>' : '') });
      return;
    }
    var fields = tripFields(true);
    var last = TO.data.list('tripCategories')[0];
    var el = TO.dialog({ title: TO.t('trip.new'), wide: true,
      body: '<form id="nt-form" autocomplete="off" class="grid cols-2">' + U.fields(fields, { date: U.today(), categoryId: last && TO.data.list('tripCategories').length === 1 ? last.id : '' }) + '</form><div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>',
      footer: '<span class="faint grow">' + TO.esc(TO.t('trip.new.hint')) + '</span><button class="btn ghost" data-close>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-save>' + TO.icon('check', 'sm') + TO.esc(TO.t('trip.new.save')) + '</button>' });
    var form = el.querySelector('#nt-form'), err = el.querySelector('.err');
    // choosing a requester fills their department
    form.querySelector('[name="requesterId"]').addEventListener('change', function () {
      var r = U.read(form, fields).values, p = TO.data.get('people', r.requesterId), dep = form.querySelector('[name="departmentId"]');
      if (p && p.departmentId && !dep.value) dep.value = TO.data.name('departments', p.departmentId);
    });
    function save() {
      var r = U.read(form, fields);
      if (r.missing.length) { err.hidden = false; err.textContent = TO.t('form.missing', { f: r.missing.join('، ') }); return; }
      var v = r.values, ops = [], made = {};
      r.newRefs.forEach(function (n) {
        var nid = TO.data.newId(n.entity.slice(0, 2)); made[n.field] = nid;
        ops.push({ e: n.entity, id: nid, op: 'put', row: n.entity === 'people' ? { name: n.text, active: true, isRequester: true, isPassenger: true } : { name: n.text, active: true } });
      });
      var people = TO.data.list('people'), byKey = {};
      people.forEach(function (p) { byKey[U.key(p.name)] = p.id; });
      var pax = String(v.passengersText || '').split(/\s+-\s+|\n|,|،/).map(function (x) { return x.trim(); }).filter(Boolean).map(function (name) {
        return byKey[U.key(name)] ? { personId: byKey[U.key(name)] } : { freeText: name };
      });
      var body = Object.assign({}, v, made); delete body.passengersText; body.passengers = pax;
      var btn = el.querySelector('[data-save]'); btn.disabled = true;
      var pre = ops.length ? TO.data.commit(TO.t('trip.people.added'), ops) : Promise.resolve();
      pre.then(function () { return TO.post('/api/trips/new', body); }).then(function (res) {
        return TO.data.load().then(function () { TO.overlay.close(); TO.toast(TO.t('trip.created', { no: res.no })); TO.rerender(); openTrip(res.id); });
      }, function (e) { btn.disabled = false; err.hidden = false; err.textContent = U.errorText(e); });
    }
    form.addEventListener('submit', function (e) { e.preventDefault(); save(); });
    el.querySelector('[data-save]').addEventListener('click', save);
  }
  TO.newTrip = newTrip;

  /* ---------- amend ---------- */
  var AMEND = [
    ['date', 'date'], ['categoryId', 'ref:tripCategories'], ['vehicleId', 'ref:vehicles'], ['driverId', 'ref:drivers'], ['requesterId', 'ref:people'],
    ['departmentId', 'ref:departments'], ['destination', 'text'], ['purpose', 'text'], ['status', 'status'], ['startKm', 'number'], ['endKm', 'number'],
    ['startAt', 'datetime'], ['endAt', 'datetime'], ['billableKm', 'number'], ['notes', 'text']
  ];
  var FIELD_KEY = { date: 'f.date', categoryId: 'f.category', vehicleId: 'f.vehicle', driverId: 'f.driver', requesterId: 'f.requester', departmentId: 'f.department', destination: 'f.destination',
    purpose: 'f.purpose', status: 'f.status', startKm: 'f.startKm', endKm: 'f.endKm', startAt: 'f.startAt', endAt: 'f.endAt', billableKm: 'f.billableKm', notes: 'f.notes', seq: 'f.seq', gaApproved: 'f.ga' };
  function amendDialog(t) {
    var el = TO.dialog({ title: TO.t('amend.title'),
      body: '<p class="muted">' + TO.esc(TO.t('amend.body')) + '</p><div class="field"><label for="am-f">' + TO.esc(TO.t('amend.field')) + '</label><select class="input" id="am-f">' +
        AMEND.map(function (a) { return '<option value="' + a[0] + '">' + TO.esc(TO.t(FIELD_KEY[a[0]])) + '</option>'; }).join('') + '</select></div><div id="am-v"></div>' +
        '<div class="field"><label for="am-r">' + TO.esc(TO.t('amend.reason')) + ' <span class="faint">*</span></label><input class="input" id="am-r" autocomplete="off"></div><div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>',
      footer: '<button class="btn ghost" data-close>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-ok>' + TO.esc(TO.t('amend.save')) + '</button>' });
    var sel = el.querySelector('#am-f'), holder = el.querySelector('#am-v'), err = el.querySelector('.err'), current;
    function draw() {
      var a = AMEND.filter(function (x) { return x[0] === sel.value; })[0], kind = a[1], f;
      var cur = t[sel.value];
      if (kind.indexOf('ref:') === 0) f = { key: 'v', label: 'amend.new', type: 'ref', entity: kind.slice(4) };
      else if (kind === 'status') f = { key: 'v', label: 'amend.new', type: 'select', options: ['draft', 'sent', 'started', 'finished', 'closed', 'cancelled'].map(function (s) { return { v: s, l: TO.t('status.' + s) }; }), blank: false };
      else f = { key: 'v', label: 'amend.new', type: kind };
      holder.innerHTML = '<div class="tip" style="margin-bottom:.8rem">' + TO.icon('info') + '<span>' + TO.esc(TO.t('amend.current')) + ': <b>' + display(sel.value, cur) + '</b></span></div>' + U.field(f, cur);
      current = f;
    }
    sel.addEventListener('change', draw); draw();
    el.querySelector('[data-ok]').addEventListener('click', function () {
      var r = U.read(holder, [current]), reason = el.querySelector('#am-r').value.trim();
      if (r.missing.length && current.type === 'ref') { err.hidden = false; err.textContent = TO.t('form.missing', { f: r.missing.join('، ') }); return; }
      if (reason.length < 3) { err.hidden = false; err.textContent = TO.t('amend.needReason'); el.querySelector('#am-r').focus(); return; }
      var btn = el.querySelector('[data-ok]');
      U.run(TO.post('/api/trips/amend', { id: t.id, field: sel.value, value: r.values.v, reason: reason }), 'amend.done', btn).then(function () {
        return TO.data.load().then(function () { TO.overlay.close(); TO.rerender(); refreshPanel(t.id); });
      }, function (e) { err.hidden = false; err.textContent = U.errorText(e); });
    });
  }
  function display(field, v) {
    if (v === undefined || v === null || v === '') return '–';
    var m = { categoryId: function () { return TO.data.catName(v); }, vehicleId: function () { return vehiclePlate(v); }, driverId: function () { return TO.data.name('drivers', v); },
      requesterId: function () { return person(v); }, departmentId: function () { return TO.data.name('departments', v); }, status: function () { return TO.t('status.' + v); },
      startAt: function () { return U.dt(v); }, endAt: function () { return U.dt(v); }, date: function () { return U.day(v); } };
    return TO.esc(m[field] ? m[field]() : v);
  }

  /* ---------- driver link, print, Word ---------- */
  function linkCard(t) {
    var open = t.status !== 'cancelled' && !t.locked, ready = TO.data.state && TO.data.state.gateway, can = TO.can('trips.send');
    var body = '';
    if (open && can) {
      if (!ready) body += '<div class="tip">' + TO.icon('info') + '<span>' + TO.esc(TO.t('link.notset')) + '</span></div>';
      else {
        body += '<p class="muted">' + TO.esc(t.linkHash ? (t.boundDevice ? TO.t('link.bound') : TO.t('link.made')) : TO.t('link.none')) + '</p>' +
          '<div class="row wrap" style="gap:.5rem"><button class="btn primary" data-a="wa">' + TO.icon('chat', 'sm') + TO.esc(TO.t('link.wa')) + '</button>' +
          '<button class="btn" data-a="copylink">' + TO.icon('copy', 'sm') + TO.esc(TO.t('link.copy')) + '</button>' +
          (t.linkHash ? '<button class="btn" data-a="newlink">' + TO.esc(TO.t('link.new')) + '</button>' : '') +
          (t.boundDevice && TO.can('trips.amend') ? '<button class="btn" data-a="release">' + TO.esc(TO.t('link.release')) + '</button>' : '') + '</div>';
      }
    }
    body += '<div class="row wrap" style="gap:.5rem;margin-top:.8rem"><button class="btn" data-a="print">' + TO.icon('doc', 'sm') + TO.esc(TO.t('link.print')) + '</button>' +
      '<a class="btn" href="/api/word/form?lang=' + TO.lang + '&trip=' + encodeURIComponent(t.id) + '" download>' + TO.icon('download', 'sm') + TO.esc(TO.t('link.word')) + '</a></div>';
    return '<section class="card"><h3 style="margin-bottom:.8rem">' + TO.esc(TO.t('link.title')) + '</h3>' + body + '</section>';
  }
  function linkDialog(url) {
    var el = TO.dialog({ title: TO.t('link.copy'), body: '<div class="field"><input class="input" id="lk" readonly dir="ltr" value="' + TO.esc(url) + '"><span class="help">' + TO.esc(TO.t('link.copy.help')) + '</span></div>',
      footer: '<button class="btn ghost" data-close>' + TO.esc(TO.t('common.close')) + '</button><button class="btn primary" data-copy>' + TO.esc(TO.t('common.copy')) + '</button>' });
    var inp = el.querySelector('#lk'); inp.focus(); inp.select();
    el.querySelector('[data-copy]').addEventListener('click', function () {
      var ok = function () { TO.toast(TO.t('link.copied')); };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(url).then(ok, function () { inp.select(); document.execCommand('copy'); ok(); });
      else { inp.select(); try { document.execCommand('copy'); ok(); } catch (e) { /* the text stays selected for Ctrl+C */ } }
    });
  }
  function waMessage(t, r) {
    var v = TO.data.get('vehicles', t.vehicleId) || {};
    return TO.t('wa.msg', { no: t.no, date: U.day(t.date), plate: v.plate || '–', dest: t.destination || '–', link: r.url });
  }
  function sendLink(t, replace, sent, then) {
    return TO.post('/api/trips/link', { id: t.id, replace: !!replace, sent: !!sent }).then(function (r) { return TO.data.load().then(function () { then(r); refreshPanel(t.id); TO.rerender(); }); },
      function (e) { TO.toast(U.errorText(e), 'bad', 6000); });
  }

  /* ---------- the trip panel ---------- */
  var openId = null;
  function panelHTML(t) {
    var ins = TO.data.trust(t.id), photos = TO.data.list('tripPhotos').filter(function (p) { return p.tripId === t.id; });
    var ams = TO.data.list('tripAmendments').filter(function (a) { return a.tripId === t.id; }).sort(function (a, b) { return String(b.at).localeCompare(String(a.at)); });
    var pax = passengers(t);
    var reasons = (ins.reasons || []).map(function (r) { return '<li><span class="badge ' + (r.charAt(0) === 'R' ? 'bad' : 'warn') + '">' + TO.esc(TO.t('why.' + r)) + '</span></li>'; }).join('');
    var chain = ins.chain ? (ins.chain.backstep ? '<div class="tip" style="background:var(--bad-soft)">' + TO.icon('alert') + '<span>' + TO.t('chain.backstep', { km: { html: '<b class="num">' + TO.fmt.num(ins.chain.backstep) + '</b>' } }) + '</span></div>' : ins.chain.gap ? '<div class="tip">' + TO.icon('info') + '<span>' + TO.t('chain.gap', { km: { html: '<b class="num">' + TO.fmt.num(ins.chain.gap) + '</b>' } }) + '</span></div>' : '') : '';
    var kv = function (k, v) { return '<dt>' + TO.esc(TO.t(k)) + '</dt><dd>' + v + '</dd>'; };
    return '<div class="row wrap" style="gap:.6rem">' + U.trust(ins.trust, ins.reasons) + '<b>' + TO.esc(TO.t('trust.' + ins.trust)) + '</b><span class="grow"></span>' + U.status(t.status) + (t.locked ? '<span class="badge">' + TO.icon('lock', 'sm') + TO.esc(TO.t('trip.locked')) + '</span>' : '') + '</div>' +
      (reasons ? '<ul class="chip-row" style="list-style:none;margin:0;padding:0">' + reasons + '</ul>' : '') + chain +
      '<section class="card"><h3 style="margin-bottom:.8rem">' + TO.esc(TO.t('trip.section.trip')) + '</h3><dl class="kv">' +
        kv('f.date', U.day(t.date)) + kv('f.category', TO.esc(TO.data.catName(t.categoryId))) + kv('f.vehicle', U.plate(vehiclePlate(t.vehicleId))) +
        kv('f.driver', TO.esc(TO.data.name('drivers', t.driverId)) || '–') + kv('f.requester', TO.esc(person(t.requesterId)) || '–') +
        kv('f.department', TO.esc(TO.data.name('departments', t.departmentId)) || '–') + kv('f.passengers', TO.esc(pax.join('، ')) || '–') +
        kv('f.destination', TO.esc(t.destination || '–')) + (t.purpose ? kv('f.purpose', TO.esc(t.purpose)) : '') + (t.notes ? kv('f.notes', TO.esc(t.notes)) : '') +
        kv('f.ga', t.gaApproved === 'yes' ? '<span class="badge ok">' + TO.esc(TO.t('ga.yes')) + '</span> <span class="muted">' + TO.esc(t.gaBy || '') + '</span>' : t.gaApproved === 'no' ? '<span class="badge bad">' + TO.esc(TO.t('ga.no')) + '</span>' : '<span class="badge">' + TO.esc(TO.t('ga.pending')) + '</span>') +
      '</dl></section>' +
      linkCard(t) +
      '<section class="card"><h3 style="margin-bottom:.8rem">' + TO.esc(TO.t('trip.section.odo')) + '</h3><dl class="kv">' +
        kv('f.startKm', U.num(t.startKm)) + kv('f.endKm', U.num(t.endKm)) + kv('f.km', ins.km === null || ins.km === undefined ? '–' : '<b class="num">' + TO.fmt.num(ins.km) + '</b>') +
        (t.billableKm ? kv('f.billableKm', U.num(t.billableKm)) : '') + kv('f.startAt', U.dt(t.startAt)) + kv('f.endAt', U.dt(t.endAt)) +
        kv('f.hours', ins.hours === null || ins.hours === undefined ? '–' : '<span class="num">' + ins.hours + '</span>') + kv('f.ot', ins.otHours ? '<b class="num">' + ins.otHours + '</b>' : '<span class="faint">–</span>') +
      '</dl></section>' +
      '<section class="card"><h3 style="margin-bottom:.8rem">' + TO.esc(TO.t('trip.section.photos')) + '</h3>' + (photos.length ? '<div class="grid cols-3" style="grid-template-columns:repeat(auto-fill,minmax(8rem,1fr))">' + photos.map(function (p) {
        return '<a href="' + TO.esc(p.src) + '" target="_blank" rel="noopener"><img src="' + TO.esc(p.src) + '" alt="' + TO.esc(TO.t('photo.' + p.kind)) + '" style="width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:.6rem;border:1px solid var(--line)"><small class="muted">' + TO.esc(TO.t('photo.' + p.kind)) + '</small></a>'; }).join('') + '</div>' : '<p class="muted">' + TO.esc(TO.t('trip.photos.none')) + '</p>') + '</section>' +
      '<section class="card"><h3 style="margin-bottom:.8rem">' + TO.esc(TO.t('trip.section.history')) + '</h3>' + (ams.length ? '<ol class="steps" style="counter-reset:none;gap:.9rem">' + ams.map(function (a) {
        return '<li style="display:block"><b>' + TO.esc(TO.t(FIELD_KEY[a.field] || 'f.notes')) + '</b>: <span class="muted">' + display(a.field, a.old) + '</span> → <b>' + display(a.field, a.new) + '</b><div class="muted" style="font-size:.85rem">' + TO.esc(a.reason) + ' · ' + TO.esc(a.by || '') + ' · ' + U.dt(a.at) + '</div></li>'; }).join('') + '</ol>' : '<p class="muted">' + TO.esc(TO.t('trip.history.none')) + '</p>') + '</section>';
  }
  function footerHTML(t) {
    var b = '';
    if (t.status !== 'cancelled') {
      if (TO.can('trips.cancel')) b += '<button class="btn danger" data-a="cancel" style="margin-inline-end:auto">' + TO.esc(TO.t('trip.cancel')) + '</button>';
      if (TO.can('trips.approve') && t.gaApproved !== 'yes') b += '<button class="btn" data-a="approve">' + TO.icon('check', 'sm') + TO.esc(TO.t('trip.approve')) + '</button>';
      if (t.locked ? TO.can(['trips.amend', 'trips.review']) : TO.can(['trips.edit', 'trips.amend', 'trips.review'])) b += '<button class="btn primary" data-a="amend">' + TO.esc(TO.t('trip.amend')) + '</button>';
    }
    return b;
  }
  function openTrip(id) {
    var t = TO.data.get('trips', id); if (!t) return;
    openId = id;
    TO.panel.open({ title: t.no, ltr: true, body: '<div class="stack" data-trip>' + panelHTML(t) + '</div>', footer: footerHTML(t),
      mount: function (el) {
        el.addEventListener('click', function (e) {
          var a = e.target.closest('[data-a]'); if (!a) return;
          var cur = TO.data.get('trips', id);
          if (a.dataset.a === 'amend') amendDialog(cur);
          else if (a.dataset.a === 'print') TO.printTrip(cur);
          else if (a.dataset.a === 'copylink') sendLink(cur, false, false, function (r) { linkDialog(r.url); });
          else if (a.dataset.a === 'wa') sendLink(cur, false, true, function (r) { var d = String(r.mobile || '').replace(/\D/g, ''); window.open('https://wa.me/' + d + '?text=' + encodeURIComponent(waMessage(cur, r)), '_blank', 'noopener'); });
          else if (a.dataset.a === 'newlink') U.confirm({ title: TO.t('link.new'), body: TO.t('link.new.body'), danger: true, ok: TO.t('link.new') }).then(function (ok) { if (ok) sendLink(cur, true, false, function (r) { linkDialog(r.url); }); });
          else if (a.dataset.a === 'release') U.run(TO.post('/api/trips/release-device', { id: id }), 'link.released').then(function () { return TO.data.load(); }).then(function () { refreshPanel(id); TO.rerender(); });
          else if (a.dataset.a === 'approve') U.run(TO.post('/api/trips/approve', { id: id, yes: true }), 'trip.approved').then(function () { return TO.data.load(); }).then(function () { refreshPanel(id); TO.rerender(); });
          else if (a.dataset.a === 'cancel') U.confirm({ title: TO.t('trip.cancel'), body: TO.t('trip.cancel.body'), reason: TO.t('amend.reason'), danger: true, ok: TO.t('trip.cancel') }).then(function (reason) {
            if (reason) U.run(TO.post('/api/trips/cancel', { id: id, reason: reason }), 'trip.cancelled').then(function () { return TO.data.load(); }).then(function () { refreshPanel(id); TO.rerender(); });
          });
        });
      } });
  }
  function refreshPanel(id) {
    var t = TO.data.get('trips', id); if (!t) return;
    var body = document.querySelector('[data-trip]');
    if (body) { body.innerHTML = panelHTML(t); var foot = body.closest('.drawer').querySelector('footer'); if (foot) foot.innerHTML = footerHTML(t); }
  }
  TO.openTrip = openTrip;
  TO.paletteRecords = function (text) {
    var n = U.key(text), out = [];
    TO.data.list('trips').forEach(function (t) { if (out.length < 8 && TO.can('trips.view') && U.key(tripText(t)).indexOf(n) >= 0) out.push({ icon: 'route', label: TO.tripLabel(t), group: TO.t('pal.g.trips'), hint: '', run: function () { TO.go('trips'); setTimeout(function () { openTrip(t.id); }, 80); } }); });
    TO.data.list('vehicles').forEach(function (v) { if (out.length < 8 && U.key(v.plate).indexOf(n) >= 0) out.push({ icon: 'car', label: v.plate, group: TO.t('nav.vehicles'), hint: '', run: function () { TO.go('vehicles'); } }); });
    TO.data.list('drivers').forEach(function (d) { if (out.length < 8 && U.key(d.name).indexOf(n) >= 0) out.push({ icon: 'wheel', label: d.name, group: TO.t('nav.drivers'), hint: '', run: function () { TO.go('drivers'); } }); });
    return out;
  };

  /* ---------- the list ---------- */
  var F = { q: '', range: 'month', cat: '', status: '', trust: '' };
  function filtered() {
    var r = range(F.range), n = U.key(F.q);
    return TO.data.list('trips').filter(function (t) {
      var d = String(t.date || '');
      if (d < r[0] || d > r[1]) return false;
      if (F.cat && t.categoryId !== F.cat) return false;
      if (F.status && t.status !== F.status) return false;
      if (F.trust && TO.data.trust(t.id).trust !== F.trust) return false;
      return !n || U.key(tripText(t)).indexOf(n) >= 0;
    }).sort(function (a, b) { return String(b.date).localeCompare(String(a.date)) || String(b.no).localeCompare(String(a.no)); });
  }
  function summary(rows) {
    var km = 0, ot = 0, c = { green: 0, yellow: 0, red: 0 };
    rows.forEach(function (t) { var i = TO.data.trust(t.id); if (t.status !== 'cancelled') { km += i.km > 0 ? i.km : 0; ot += i.otHours || 0; } if (c[i.trust] !== undefined) c[i.trust]++; });
    return '<div class="row wrap" style="gap:.6rem;margin-bottom:1rem">' +
      '<span class="badge">' + TO.esc(TO.t('sum.trips')) + ' <b class="num">' + TO.fmt.num(rows.length) + '</b></span>' +
      '<span class="badge">' + TO.esc(TO.t('sum.km')) + ' <b class="num">' + TO.fmt.num(km) + '</b></span>' +
      '<span class="badge">' + TO.esc(TO.t('sum.ot')) + ' <b class="num">' + Math.round(ot * 100) / 100 + '</b></span>' +
      ['green', 'yellow', 'red'].map(function (k) { return '<button class="badge ' + ({ green: 'ok', yellow: 'warn', red: 'bad' })[k] + '" data-trust="' + k + '" style="border:0;cursor:pointer" aria-pressed="' + (F.trust === k) + '"><i class="trust ' + k + '" style="width:.55rem;height:.55rem;box-shadow:none"></i> <b class="num">' + c[k] + '</b></button>'; }).join('') + '</div>';
  }
  function tableRows(rows) {
    if (!rows.length) return U.empty('route', TO.t(TO.data.list('trips').length ? 'trips.none.filter' : 'trips.none.title'), TO.t(TO.data.list('trips').length ? 'trips.none.filter.b' : 'trips.none.body'),
      TO.can('trips.create') && !TO.data.list('trips').length ? '<button class="btn primary" data-new>' + TO.icon('plus', 'sm') + TO.esc(TO.t('trip.new')) + '</button>' : '');
    return U.table([
      { h: 'f.trust', cell: function (t) { var i = TO.data.trust(t.id); return U.trust(i.trust, i.reasons); } },
      { h: 'f.no', cell: function (t) { return '<b class="num">' + TO.esc(t.no) + '</b>'; } },
      { h: 'f.date', cell: function (t) { return U.day(t.date); } },
      { h: 'f.category', cell: function (t) { return TO.esc(TO.data.catName(t.categoryId)); } },
      { h: 'f.vehicle', cell: function (t) { return U.plate(vehiclePlate(t.vehicleId)); } },
      { h: 'f.driver', cell: function (t) { return TO.esc(TO.data.name('drivers', t.driverId)); } },
      { h: 'f.requester', cell: function (t) { return TO.esc(person(t.requesterId)); } },
      { h: 'f.destination', cell: function (t) { return '<span class="ellipsis" style="display:block;max-width:22rem">' + TO.esc(t.destination || '') + '</span>'; } },
      { h: 'f.km', cell: function (t) { var i = TO.data.trust(t.id); return U.num(i.km); } },
      { h: 'f.status', cell: function (t) { return U.status(t.status); } }
    ], rows.slice(0, 400), { click: true, rowAttr: function (t) { return 'data-id="' + TO.esc(t.id) + '"'; } }) + (rows.length > 400 ? '<p class="muted" style="margin-top:.6rem">' + TO.esc(TO.t('trips.more', { n: rows.length - 400 })) + '</p>' : '');
  }

  TO.views.trips = TO.withData({
    render: function () {
      var cats = TO.data.list('tripCategories');
      var opt = function (list, cur, lab) { return list.map(function (o) { return '<option value="' + TO.esc(o.v) + '"' + (cur === o.v ? ' selected' : '') + '>' + TO.esc(o.l) + '</option>'; }).join(''); };
      return TO.pageHead('nav.trips', 'page.trips.d', TO.can('trips.create') ? '<button class="btn primary" data-new>' + TO.icon('plus', 'sm') + TO.esc(TO.t('trip.new')) + ' <i class="kbd">N</i></button>' : '') +
        '<div class="toolbar"><input class="input" data-f="q" type="search" value="' + TO.esc(F.q) + '" placeholder="' + TO.esc(TO.t('trips.search')) + '" style="max-width:20rem" aria-label="' + TO.esc(TO.t('trips.search')) + '">' +
        '<select class="input" data-f="range" style="width:auto">' + opt(RANGES.map(function (r) { return { v: r, l: TO.t('range.' + r) }; }), F.range) + '</select>' +
        '<select class="input" data-f="cat" style="width:auto"><option value="">' + TO.esc(TO.t('f.category')) + ': ' + TO.esc(TO.t('common.all')) + '</option>' + opt(cats.map(function (c) { return { v: c.id, l: TO.data.catName(c.id) }; }), F.cat) + '</select>' +
        '<select class="input" data-f="status" style="width:auto"><option value="">' + TO.esc(TO.t('f.status')) + ': ' + TO.esc(TO.t('common.all')) + '</option>' + opt(['draft', 'sent', 'started', 'finished', 'closed', 'cancelled'].map(function (s) { return { v: s, l: TO.t('status.' + s) }; }), F.status) + '</select></div>' +
        '<div data-sum></div><div data-rows></div>';
    },
    mount: function (root, ctx) {
      function paint() { var rows = filtered(); root.querySelector('[data-sum]').innerHTML = summary(rows); root.querySelector('[data-rows]').innerHTML = tableRows(rows); }
      paint();
      root.addEventListener('input', TO.debounce(function (e) { var f = e.target.dataset && e.target.dataset.f; if (f === 'q') { F.q = e.target.value; paint(); } }, 120));
      root.addEventListener('change', function (e) { var f = e.target.dataset && e.target.dataset.f; if (f && f !== 'q') { F[f] = e.target.value; paint(); } });
      root.addEventListener('click', function (e) {
        if (e.target.closest('[data-new]')) { newTrip(); return; }
        var tb = e.target.closest('[data-trust]'); if (tb) { F.trust = F.trust === tb.dataset.trust ? '' : tb.dataset.trust; paint(); return; }
        var tr = e.target.closest('tr[data-id]'); if (tr) openTrip(tr.dataset.id);
      });
      root.addEventListener('keydown', function (e) { if (e.key === 'Enter') { var tr = e.target.closest && e.target.closest('tr[data-id]'); if (tr) openTrip(tr.dataset.id); } });
      if (ctx.route.q.open) openTrip(ctx.route.q.open);
    }
  });
})();
