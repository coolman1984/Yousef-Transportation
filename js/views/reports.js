/* Trip Orders - Reports: numbers for finance and management (one month or all), bar charts, reconciliation with the vendor,
   cost per department, overtime, things to check, and a presentation mode with slides made from the live numbers. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var S = null;
  var GROUPS = ['byVehicle', 'byDriver', 'byDepartment', 'byCategory'];

  function bars(rows, key, limit) {
    rows = rows.slice(0, limit || 8);
    var max = Math.max.apply(null, rows.map(function (r) { return r[key] || 0; }).concat([1]));
    return '<div class="bars">' + rows.map(function (r) {
      var w = Math.max(2, Math.round((r[key] || 0) / max * 100));
      return '<div class="bar-row"><span class="bar-l">' + TO.esc(r.label) + '</span><span class="bar-t"><i style="width:' + w + '%"></i></span><b class="num">' + TO.fmt.num(r[key] || 0) + '</b></div>';
    }).join('') + '</div>';
  }
  function kpi(icon, label, v) {
    return '<div class="card kpi"><span class="label">' + TO.esc(TO.t(label)) + '<span class="tile-ic">' + TO.icon(icon) + '</span></span><span class="value num">' + TO.fmt.num(v) + '</span></div>';
  }
  function groupTable(rows) {
    return U.table([
      { h: 'f.name', cell: function (r) { return TO.esc(r.label); } },
      { h: 'f.trips', cell: function (r) { return U.num(r.trips); } },
      { h: 'f.km', cell: function (r) { return U.num(r.km); } },
      { h: 'rp.avg', cell: function (r) { return U.num(r.avgKm); } },
      { h: 'rp.ot', cell: function (r) { return U.num(r.ot); } },
      { h: 'rp.trust', cell: function (r) { return '<span class="badge ok">' + r.green + '</span> <span class="badge warn">' + r.yellow + '</span> <span class="badge bad">' + r.red + '</span>'; } }
    ], rows.slice(0, 40));
  }
  function view() {
    var d = S.data, t = d.summary.total;
    var tabs = GROUPS.map(function (g) { return '<button data-g="' + g + '" aria-pressed="' + (S.group === g) + '">' + TO.esc(TO.t('rp.' + g)) + '</button>'; }).join('');
    var rec = d.reconciliation.length ? U.table([
      { h: 'f.category', cell: function (r) { return TO.esc(r.category); } }, { h: 'f.vendor', cell: function (r) { return TO.esc(r.vendor || ''); } },
      { h: 'f.trips', cell: function (r) { return U.num(r.trips); } }, { h: 'rp.actual', cell: function (r) { return U.num(r.actualKm); } },
      { h: 'rp.billed', cell: function (r) { return U.num(r.billedKm); } },
      { h: 'rp.diff', cell: function (r) { return '<b class="num ' + (r.diffKm ? 'neg' : '') + '">' + TO.fmt.num(r.diffKm) + '</b>'; } },
      { h: 'rp.money', cell: function (r) { return U.num(r.diffMoney); } }], d.reconciliation) : U.empty('check', TO.t('rp.rec.none'));
    var alloc = d.allocation.some(function (a) { return a.total; }) ? U.table([
      { h: 'f.department', cell: function (r) { return TO.esc(r.department); } }, { h: 'f.trips', cell: function (r) { return U.num(r.trips); } }, { h: 'f.km', cell: function (r) { return U.num(r.km); } },
      { h: 'rp.kmCost', cell: function (r) { return U.num(r.kmCost); } }, { h: 'rp.otCost', cell: function (r) { return U.num(r.otCost); } }, { h: 'rp.total', cell: function (r) { return '<b class="num">' + TO.fmt.num(r.total) + '</b>'; } }], d.allocation) : '<p class="muted">' + TO.esc(TO.t('rp.alloc.none')) + '</p>';
    var an = d.anomalies.length ? U.table([
      { h: 'f.date', cell: function (r) { return '<span class="num">' + U.day(r.date) + '</span>'; } }, { h: 'f.trip', cell: function (r) { return '<span class="num" dir="ltr">' + TO.esc(r.no || '') + '</span>'; } },
      { h: 'f.plate', cell: function (r) { return U.plate(r.plate); } }, { h: 'f.driver', cell: function (r) { return TO.esc(r.driver); } },
      { h: 'rp.why', cell: function (r) { var k = 'why.' + r.code; return '<span class="badge ' + (r.level === 'bad' ? 'bad' : 'warn') + '">' + TO.esc(TO.has(k) ? TO.t(k) : r.code) + '</span>'; } }], d.anomalies.slice(0, 60)) : U.empty('check', TO.t('rp.anom.none'));
    var ot = d.overtime.length ? U.table([{ h: 'f.driver', cell: function (r) { return TO.esc(r.driver); } }, { h: 'rp.ot', cell: function (r) { return '<b class="num">' + TO.fmt.num(r.total) + '</b>'; } },
      { h: 'rp.days', cell: function (r) { return U.num(r.days.length); } }], d.overtime.slice(0, 20)) : '<p class="muted">' + TO.esc(TO.t('rp.ot.none')) + '</p>';
    return '<div class="grid cols-4">' + kpi('route', 'f.trips', t.trips) + kpi('wheel', 'f.km', t.km) + kpi('clock', 'rp.hours', t.hours) + kpi('clock', 'rp.ot', t.ot) + '</div>' +
      '<div class="grid cols-2" style="margin-top:var(--gap)"><section class="card"><header><h3>' + TO.esc(TO.t('rp.top.vehicles')) + '</h3></header>' + bars(d.summary.byVehicle, 'km') + '</section>' +
      '<section class="card"><header><h3>' + TO.esc(TO.t('rp.top.departments')) + '</h3></header>' + bars(d.summary.byDepartment, 'km') + '</section></div>' +
      '<section class="card" style="margin-top:var(--gap)"><header><h3>' + TO.esc(TO.t('rp.breakdown')) + '</h3><div class="seg" role="group">' + tabs + '</div></header>' + groupTable(d.summary[S.group]) + '</section>' +
      '<section class="card" style="margin-top:var(--gap)"><header><h3>' + TO.icon('shield') + ' ' + TO.esc(TO.t('rp.rec')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('rp.rec.sub')) + '</p>' + rec + '</section>' +
      '<div class="grid cols-2" style="margin-top:var(--gap)"><section class="card"><header><h3>' + TO.esc(TO.t('rp.alloc')) + '</h3></header>' + alloc + '</section>' +
      '<section class="card"><header><h3>' + TO.esc(TO.t('rp.ovt')) + '</h3></header>' + ot + '</section></div>' +
      '<section class="card" style="margin-top:var(--gap)"><header><h3>' + TO.icon('alert') + ' ' + TO.esc(TO.t('rp.anom')) + '</h3></header>' + an + '</section>';
  }
  function paint(root) {
    var body = root.querySelector('#rp-body');
    body.innerHTML = S.data ? (S.data.summary.total.trips ? view() : U.empty('route', TO.t('exp2.none'))) : '<div class="skeleton" style="height:12rem"></div>';
  }
  var seq = 0;
  function fetchData(root) {
    var mine = ++seq;      // an older answer that arrives late must never replace the newer one
    S.data = null; paint(root);
    TO.get('/api/reports?ym=' + encodeURIComponent(S.ym)).then(function (d) { if (mine === seq) { S.data = d; paint(root); } }, function (e) { if (mine === seq) root.querySelector('#rp-body').innerHTML = U.empty('alert', U.errorText(e)); });
  }

  /* ---------- presentation mode: slides from the live numbers ---------- */
  function present() {
    var d = S.data; if (!d || !d.summary.total.trips) return;
    var t = d.summary.total, top = function (rows, n) { return rows.slice(0, n || 5); };
    var slides = [
      '<h2>' + TO.esc(TO.t('rp.slide.month', { m: S.ym || TO.t('rp.all') })) + '</h2><div class="big-row">' + [['f.trips', t.trips], ['f.km', t.km], ['rp.hours', t.hours], ['rp.ot', t.ot]].map(function (x) { return '<div><b class="num">' + TO.fmt.num(x[1]) + '</b><span>' + TO.esc(TO.t(x[0])) + '</span></div>'; }).join('') + '</div>',
      '<h2>' + TO.esc(TO.t('rp.slide.trust')) + '</h2><div class="big-row">' + ['green', 'yellow', 'red'].map(function (k) { return '<div><b class="num">' + TO.fmt.num(t[k]) + '</b><span><i class="trust ' + k + '"></i> ' + TO.esc(TO.t('trust.' + k)) + '</span></div>'; }).join('') + '</div>',
      '<h2>' + TO.esc(TO.t('rp.top.vehicles')) + '</h2>' + bars(top(d.summary.byVehicle), 'km'),
      '<h2>' + TO.esc(TO.t('rp.top.departments')) + '</h2>' + bars(top(d.summary.byDepartment), 'km'),
      '<h2>' + TO.esc(TO.t('rp.rec')) + '</h2>' + (d.reconciliation.length ? '<div class="big-row">' + d.reconciliation.slice(0, 3).map(function (r) { return '<div><b class="num">' + TO.fmt.num(r.diffKm) + '</b><span>' + TO.esc(r.category + ' · ' + TO.t('rp.diff')) + '</span></div>'; }).join('') + '</div>' : '<p>' + TO.esc(TO.t('rp.rec.none')) + '</p>'),
      '<h2>' + TO.esc(TO.t('rp.anom')) + '</h2><div class="big-row"><div><b class="num">' + TO.fmt.num(d.anomalies.length) + '</b><span>' + TO.esc(TO.t('rp.anom.n')) + '</span></div></div>'
    ];
    var el = document.createElement('div'); el.className = 'present'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
    var i = 0;
    function draw() {
      el.innerHTML = '<button class="icon-btn px" aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x') + '</button><section class="ps">' + slides[i] + '</section><div class="pn">' + TO.esc((i + 1) + ' / ' + slides.length) + '</div>';
      el.querySelector('.px').onclick = close;
    }
    function key(e) {
      var rtl = document.documentElement.dir === 'rtl';
      if (e.key === 'Escape') close();
      else if (e.key === ' ' || e.key === (rtl ? 'ArrowLeft' : 'ArrowRight')) { i = Math.min(slides.length - 1, i + 1); draw(); }
      else if (e.key === (rtl ? 'ArrowRight' : 'ArrowLeft')) { i = Math.max(0, i - 1); draw(); }
      e.stopPropagation();
    }
    function close() { document.removeEventListener('keydown', key, true); el.remove(); }
    document.addEventListener('keydown', key, true);
    el.addEventListener('click', function (e) { if (!e.target.closest('.px')) { i = Math.min(slides.length - 1, i + 1); draw(); } });
    draw(); document.body.appendChild(el);
  }

  TO.views.reports = {
    render: function () {
      if (!S) S = { ym: U.today().slice(0, 7), group: 'byVehicle', data: null };
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('nav.reports')) + '</h1><p>' + TO.esc(TO.t('page.reports.d')) + '</p></div>' +
        '<div class="row wrap" style="gap:.6rem"><input class="input" type="month" id="rp-ym" value="' + TO.esc(S.ym) + '" aria-label="' + TO.esc(TO.t('exp2.month')) + '" style="width:auto">' +
        '<button class="btn" data-all>' + TO.esc(TO.t('rp.all')) + '</button><button class="btn primary" data-present>' + TO.icon('present', 'sm') + TO.esc(TO.t('rp.present')) + '</button></div></div><div id="rp-body"></div>';
    },
    mount: function (root) {
      fetchData(root);
      root.addEventListener('change', function (e) { if (e.target.id === 'rp-ym') { S.ym = e.target.value; fetchData(root); } });
      root.addEventListener('click', function (e) {
        if (e.target.closest('[data-all]')) { S.ym = ''; root.querySelector('#rp-ym').value = ''; fetchData(root); return; }
        if (e.target.closest('[data-present]')) { present(); return; }
        var g = e.target.closest('[data-g]'); if (g) { S.group = g.dataset.g; paint(root); }
      });
    }
  };
})();
