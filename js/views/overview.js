/* Trip Orders - Overview: greeting, live tiles, the next lesson of my learning path, getting-started list, trust colours, tips, system status. */
(function () {
  'use strict';
  var TO = window.TO;
  var STEPS = [
    { k: 1, icon: 'settings', page: 'settings' }, { k: 2, icon: 'layers', page: 'settings' }, { k: 3, icon: 'car', page: 'vehicles' },
    { k: 4, icon: 'users', page: 'people' }, { k: 5, icon: 'sheet', page: 'excel' }, { k: 6, icon: 'cloud', page: 'settings' }
  ];
  function greet() {
    var h = new Date().getHours();
    var k = h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening';
    var name = (TO.me.full_name || TO.me.username || '').split(' ')[0];
    return TO.t('ov.greet.' + k, { name: name });
  }
  function stepReady(k, facts, settings, tripCount) {
    facts = facts || {};
    switch (k) {
      case 1: return true; // Organisation editing is not shipped yet; the setup spec allows this step to start ready.
      case 2: return !!facts.categoriesAdded;
      case 3: return !!(facts.vehiclesAdded && facts.driversAdded);
      case 4: return !!(facts.peopleAdded && facts.placesAdded);
      case 5: return !!(facts.myImport || tripCount > 0);
      case 6: return !!facts.mailboxReady;
      default: return false;
    }
  }
  function stepsHTML(facts, settings, tripCount) {
    return STEPS.map(function (s) {
      var ready = stepReady(s.k, facts, settings, tripCount);
      return '<li><div class="grow"><a href="#/' + s.page + '" style="color:inherit;text-decoration:none;font-weight:600">' + TO.esc(TO.t('ov.start.' + s.k)) + '</a></div>' +
        '<span class="badge ' + (ready ? 'ok' : '') + '">' + TO.esc(TO.t(ready ? 'ov.done.tag' : 'ov.todo.tag')) + '</span></li>';
    }).join('');
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
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(greet()) + '</h1><p>' + TO.esc(TO.t('ov.sub')) + ' <span class="faint">' + TO.esc(TO.fmt.longDate()) + '</span></p></div>' +
        '<button class="btn" data-a="tour">' + TO.icon('play', 'sm') + TO.esc(TO.t('ov.tour.btn')) + '</button>' +
        '<button class="btn" data-a="slides">' + TO.icon('present', 'sm') + TO.esc(TO.t('ov.slides.btn')) + '</button></div>' +
        (TO.me && !TO.me.training ? '<section class="card lift train-card"><span class="tile-ic">' + TO.icon('play') + '</span><div class="grow"><h3>' + TO.esc(TO.t('train.title')) + '</h3>' +
          '<p class="muted">' + TO.esc(TO.t('train.body')) + '</p></div><button class="btn primary lg" data-act="training">' + TO.icon('play', 'sm') + TO.esc(TO.t('train.go')) + '</button></section>' : '') +
        '<div class="grid cols-4" data-tour="kpis">' + kpi(0, 'route', 'today') + kpi(1, 'gauge', 'road', true) + kpi(2, 'shield', 'review') + kpi(3, 'car', 'fleet') + '</div>' +
        '<section class="card lift path-card" data-pathcard style="margin-top:var(--gap)"></section>' +
        '<div class="grid split" style="margin-top:var(--gap)"><div class="stack">' +
          '<section class="card lift"><header><h3>' + TO.esc(TO.t('ov.start.title')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('ov.start.sub')) + '</p><ol class="steps" data-ov-steps><li class="skeleton" style="height:2.4rem"></li></ol></section>' +
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
      if (TO.guides) TO.guides.fillNext(root);   // the next lesson of my learning path (js/views/guides.js); hidden when complete
      var stepsEl = root.querySelector('[data-ov-steps]');
      function paintSteps(facts, settings, tripCount) {
        if (stepsEl) stepsEl.innerHTML = stepsHTML(facts, settings, tripCount);
      }
      TO.get('/api/guide-facts').then(function (facts) {
        return TO.data.load().then(function (D) {
          var settings = (D.state && D.state.settings) || {};
          var trips = D.list('trips');
          paintSteps(facts, settings, trips.length);
          var today = TO.ui.today();
          var v = {
            today: trips.filter(function (t) { return t.date === today && t.status !== 'cancelled'; }).length,
            road: trips.filter(function (t) { return t.status === 'started'; }).length,
            review: trips.filter(function (t) { var c = D.trust(t.id).trust; return t.status !== 'cancelled' && (c === 'red' || c === 'yellow'); }).length,
            fleet: D.list('vehicles').filter(function (x) { return x.active !== false; }).length
          };
          TO.$$('[data-count]', root).forEach(function (el) { TO.countUp(el, v[el.dataset.count]); });
          var rc = TO.$('#rec-count', root);
          if (rc) rc.textContent = TO.fmt.num(trips.length + D.list('vehicles').length + D.list('drivers').length + D.list('people').length);
        }, function () { paintSteps(facts, {}, 0); TO.$$('[data-count]', root).forEach(function (el) { el.textContent = '–'; }); });
      }, function () {
        if (stepsEl) stepsEl.innerHTML = stepsHTML({}, {}, 0);
        TO.$$('[data-count]', root).forEach(function (el) { el.textContent = '–'; });
      });
    }
  };
  TO.overviewStepReady = stepReady;
})();
