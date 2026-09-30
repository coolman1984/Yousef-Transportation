/* Trip Orders - Overview: greeting, live tiles, getting-started list, trust colours, tips, system status. */
(function () {
  'use strict';
  var TO = window.TO;
  var STEPS = [
    { k: 1, icon: 'settings', page: 'settings', ready: true }, { k: 2, icon: 'layers', page: 'settings' }, { k: 3, icon: 'car', page: 'vehicles' },
    { k: 4, icon: 'users', page: 'people' }, { k: 5, icon: 'sheet', page: 'excel' }, { k: 6, icon: 'cloud', page: 'settings' }
  ];
  function greet() {
    var h = new Date().getHours();
    var k = h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening';
    var name = (TO.me.full_name || TO.me.username || '').split(' ')[0];
    return TO.t('ov.greet.' + k, { name: name });
  }
  function kpi(i, icon, key, live) {
    return '<div class="card kpi' + (live ? ' live' : '') + '" style="--i:' + i + '"><div class="label">' + TO.esc(TO.t('ov.kpi.' + key)) +
      '<span class="tile-ic">' + TO.icon(icon) + '</span></div><div class="value" data-count="' + key + '"><span class="skeleton" style="display:inline-block;width:3rem;height:2rem"></span></div>' +
      '<div class="hint">' + (live ? '<span class="pulse-dot"></span> ' : '') + TO.esc(TO.t('ov.kpi.hint.' + key)) + '</div></div>';
  }
  function trustRow(c) {
    return '<div class="row" style="align-items:flex-start;gap:.9rem"><span class="trust ' + c + '" style="margin-top:.4rem"></span><div><b>' + TO.esc(TO.t('ov.trust.' + ({ green: 'green', yellow: 'yellow', red: 'red' })[c])) + '</b><div class="muted">' + TO.esc(TO.t('ov.trust.' + c + '.d')) + '</div></div></div>';
  }
  function kbd(k) { return '<i class="kbd">' + k + '</i>'; }

  TO.views.overview = {
    render: function () {
      var steps = STEPS.map(function (s) {
        var ready = s.ready;
        return '<li><div class="grow"><a href="#/' + s.page + '" style="color:inherit;text-decoration:none;font-weight:600">' + TO.esc(TO.t('ov.start.' + s.k)) + '</a></div>' +
          '<span class="badge ' + (ready ? 'ok' : '') + '">' + TO.esc(TO.t(ready ? 'ov.now.tag' : 'ov.soon.tag')) + '</span></li>';
      }).join('');
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(greet()) + '</h1><p>' + TO.esc(TO.t('ov.sub')) + ' <span class="faint">' + TO.esc(TO.fmt.longDate()) + '</span></p></div>' +
        '<button class="btn" data-a="tour">' + TO.icon('play', 'sm') + TO.esc(TO.t('ov.tour.btn')) + '</button>' +
        '<button class="btn" data-a="slides">' + TO.icon('present', 'sm') + TO.esc(TO.t('ov.slides.btn')) + '</button></div>' +
        '<div class="grid cols-4" data-tour="kpis">' + kpi(0, 'route', 'today') + kpi(1, 'gauge', 'road', true) + kpi(2, 'shield', 'review') + kpi(3, 'car', 'fleet') + '</div>' +
        '<div class="grid split" style="margin-top:var(--gap)"><div class="stack">' +
          '<section class="card lift"><header><h3>' + TO.esc(TO.t('ov.start.title')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('ov.start.sub')) + '</p><ol class="steps">' + steps + '</ol></section>' +
          '<section class="card"><header><h3>' + TO.esc(TO.t('ov.trust.title')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('ov.trust.sub')) + '</p><div class="stack" style="gap:.9rem">' + trustRow('green') + trustRow('yellow') + trustRow('red') + '</div></section>' +
        '</div><div class="stack">' +
          '<section class="card lift" style="border-color:var(--signal-line)"><header><span class="tile-ic" style="width:2.4rem;height:2.4rem;border-radius:.7rem;display:grid;place-items:center;background:var(--signal-soft);color:var(--ink)">' + TO.icon('sheet') + '</span><h3>' + TO.esc(TO.t('ov.demo.title')) + '</h3></header><p class="muted">' + TO.esc(TO.t('ov.demo.body')) + '</p>' +
            '<div style="margin-top:1rem"><a class="btn primary" href="#/excel">' + TO.icon('upload', 'sm') + TO.esc(TO.t('ov.demo.btn')) + '</a></div></section>' +
          '<section class="card"><header><h3>' + TO.esc(TO.t('ov.tips.title')) + '</h3></header><div class="stack" style="gap:.8rem">' +
            '<div class="row" style="align-items:flex-start">' + TO.icon('search') + '<span>' + TO.t('ov.tip.search', { k: '\u0000' }).replace('\u0000', kbd('Ctrl K')) + '</span></div>' +
            '<div class="row" style="align-items:flex-start">' + TO.icon('route') + '<span>' + TO.t('ov.tip.go', { k: '\u0000' }).replace('\u0000', kbd('G')) + '</span></div>' +
            '<div class="row" style="align-items:flex-start">' + TO.icon('keyboard') + '<span>' + TO.t('ov.tip.help', { k: '\u0000' }).replace('\u0000', kbd('?')) + '</span></div>' +
            '<a class="btn sm" href="#/help" style="justify-self:start">' + TO.icon('book', 'sm') + TO.esc(TO.t('ov.guide.btn')) + '</a></div></section>' +
          '<section class="card"><header><h3>' + TO.esc(TO.t('ov.status.title')) + '</h3></header><dl class="kv" id="status-kv">' +
            '<dt>' + TO.icon('cloud', 'sm') + ' ' + TO.esc(TO.t('ov.status.mailbox')) + '</dt><dd><span class="badge warn">' + TO.esc(TO.t('ov.status.mailbox.v')) + '</span></dd>' +
            '<dt>' + TO.icon('lock', 'sm') + ' ' + TO.esc(TO.t('ov.status.backup')) + '</dt><dd><span class="badge ok">' + TO.esc(TO.t('ov.status.backup.v')) + '</span></dd>' +
            '<dt>' + TO.icon('layers', 'sm') + ' ' + TO.esc(TO.t('ov.status.sync')) + '</dt><dd><span class="badge">' + TO.esc(TO.t('ov.status.sync.v')) + '</span></dd>' +
            '<dt>' + TO.icon('doc', 'sm') + ' ' + TO.esc(TO.t('ov.status.data')) + '</dt><dd><span class="num" id="rec-count">…</span></dd></dl></section>' +
        '</div></div>';
    },
    mount: function (root) {
      root.querySelector('[data-a="tour"]').addEventListener('click', function () { TO.tour.start(); });
      root.querySelector('[data-a="slides"]').addEventListener('click', function () { TO.slides.open(); });
      TO.data.load().then(function (D) {
        var today = TO.ui.today(), trips = D.list('trips');
        var v = {
          today: trips.filter(function (t) { return t.date === today && t.status !== 'cancelled'; }).length,
          road: trips.filter(function (t) { return t.status === 'started'; }).length,
          review: trips.filter(function (t) { var c = D.trust(t.id).trust; return t.status !== 'cancelled' && (c === 'red' || c === 'yellow'); }).length,
          fleet: D.list('vehicles').filter(function (x) { return x.active !== false; }).length
        };
        TO.$$('[data-count]', root).forEach(function (el) { TO.countUp(el, v[el.dataset.count]); });
        var rc = TO.$('#rec-count', root);
        if (rc) rc.textContent = TO.fmt.num(trips.length + D.list('vehicles').length + D.list('drivers').length + D.list('people').length);
      }, function () {
        TO.$$('[data-count]', root).forEach(function (el) { el.textContent = '–'; });
      });
    }
  };
})();
