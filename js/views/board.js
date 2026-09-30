/* Trip Orders - Today board (who is on the road) and Review queue (yellow and red trips only). */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var day = null, ticker = null;

  function vehiclePlate(id) { var v = TO.data.get('vehicles', id); return v ? v.plate : ''; }
  function elapsed(t) {
    var st = t.startAt ? new Date(t.startAt) : null; if (!st || isNaN(st)) return '';
    var m = Math.max(0, Math.round((Date.now() - st) / 60000));
    return Math.floor(m / 60) + ':' + TO.fmt.pad(m % 60);
  }
  function card(t) {
    var i = TO.data.trust(t.id);
    return '<button class="card lift board-card" data-id="' + TO.esc(t.id) + '" style="text-align:start;width:100%;display:grid;gap:.5rem;cursor:pointer">' +
      '<div class="row">' + U.trust(i.trust, i.reasons) + '<b class="num">' + TO.esc(t.no) + '</b><span class="grow"></span>' + (t.status === 'started' ? '<span class="badge signal"><span class="pulse-dot" style="width:.5rem;height:.5rem"></span><span class="num" data-elapsed="' + TO.esc(t.id) + '">' + elapsed(t) + '</span></span>' : U.status(t.status)) + '</div>' +
      '<div class="row">' + U.plate(vehiclePlate(t.vehicleId)) + '<span class="muted ellipsis">' + TO.esc(TO.data.name('drivers', t.driverId)) + '</span></div>' +
      '<div class="muted ellipsis">' + TO.esc(t.destination || '') + '</div></button>';
  }
  var COLS = [
    { k: 'todo', icon: 'clock', match: function (t) { return t.status === 'draft' || t.status === 'sent'; } },
    { k: 'road', icon: 'gauge', match: function (t) { return t.status === 'started'; } },
    { k: 'done', icon: 'check', match: function (t) { return (t.status === 'finished' || t.status === 'closed') && TO.data.trust(t.id).trust === 'green'; } },
    { k: 'attn', icon: 'shield', match: function (t) { var c = TO.data.trust(t.id).trust; return t.status !== 'cancelled' && (c === 'red' || c === 'yellow'); } }
  ];
  function shift(d, n) { var x = new Date(d + 'T00:00:00'); x.setDate(x.getDate() + n); return x.getFullYear() + '-' + TO.fmt.pad(x.getMonth() + 1) + '-' + TO.fmt.pad(x.getDate()); }

  TO.views.board = TO.withData({
    render: function () {
      day = day || U.today();
      var trips = TO.data.list('trips').filter(function (t) { return t.date === day && t.status !== 'cancelled'; });
      return TO.pageHead('nav.board', 'page.board.d', '<div class="row"><button class="icon-btn" data-day="-1" aria-label="' + TO.esc(TO.t('keys.day')) + '">' + TO.icon('left', 'mirror') + '</button><b class="num" style="min-width:6.5rem;text-align:center">' + U.day(day) + '</b><button class="icon-btn" data-day="1" aria-label="' + TO.esc(TO.t('keys.day')) + '">' + TO.icon('right', 'mirror') + '</button>' +
          (day !== U.today() ? '<button class="btn sm" data-day="0">' + TO.esc(TO.t('range.today')) + '</button>' : '') + '</div>') +
        '<div class="grid cols-4" style="align-items:start">' + COLS.map(function (c, n) {
          var rows = trips.filter(c.match);
          return '<section class="stack" style="gap:.7rem"><header class="row" style="padding-inline:.2rem">' + TO.icon(c.icon) + '<b>' + TO.esc(TO.t('board.' + c.k)) + '</b><span class="badge num">' + rows.length + '</span></header>' +
            (rows.length ? rows.map(card).join('') : '<div class="preview-box muted" style="text-align:center;padding:1.4rem">' + TO.esc(TO.t('board.empty')) + '</div>') + '</section>'; }).join('') + '</div>';
    },
    mount: function (root) {
      root.addEventListener('click', function (e) {
        var b = e.target.closest('[data-day]'); if (b) { day = b.dataset.day === '0' ? U.today() : shift(day, Number(b.dataset.day)); TO.rerender(); return; }
        var c = e.target.closest('[data-id]'); if (c) TO.openTrip(c.dataset.id);
      });
      clearInterval(ticker);
      ticker = setInterval(function () {
        var els = document.querySelectorAll('[data-elapsed]');
        if (!els.length) { clearInterval(ticker); return; }
        els.forEach(function (el) { var t = TO.data.get('trips', el.dataset.elapsed); if (t) el.textContent = elapsed(t); });
      }, 15000);
    }
  });
  TO.boardShift = function (n) { if (location.hash.indexOf('#/board') === 0) { day = shift(day || U.today(), n); TO.rerender(); return true; } return false; };

  TO.views.review = TO.withData({
    render: function () {
      var rows = TO.data.list('trips').filter(function (t) { var c = TO.data.trust(t.id).trust; return t.status !== 'cancelled' && (c === 'red' || c === 'yellow'); })
        .sort(function (a, b) { var ra = TO.data.trust(a.id).trust === 'red' ? 0 : 1, rb = TO.data.trust(b.id).trust === 'red' ? 0 : 1; return ra - rb || String(b.date).localeCompare(String(a.date)); });
      if (!rows.length) return TO.pageHead('nav.review', 'page.review.d') + U.empty('shield', TO.t('review.none.t'), TO.t('review.none.b'));
      return TO.pageHead('nav.review', 'page.review.d') + '<div class="stack">' + rows.slice(0, 200).map(function (t) {
        var i = TO.data.trust(t.id);
        return '<article class="card lift" data-id="' + TO.esc(t.id) + '" tabindex="0" role="button" style="cursor:pointer;display:grid;gap:.6rem;border-inline-start:4px solid var(--' + (i.trust === 'red' ? 'bad' : 'warn') + ')">' +
          '<div class="row wrap">' + U.trust(i.trust, i.reasons) + '<b class="num">' + TO.esc(t.no) + '</b><span class="muted">' + U.day(t.date) + '</span>' + U.plate(vehiclePlate(t.vehicleId)) + '<span>' + TO.esc(TO.data.name('drivers', t.driverId)) + '</span><span class="grow"></span>' + U.status(t.status) + '</div>' +
          '<div class="muted">' + TO.esc(t.destination || '') + (i.km !== null && i.km !== undefined ? ' · <span class="num">' + TO.fmt.num(i.km) + '</span> ' + TO.esc(TO.t('unit.km')) : '') + '</div>' +
          '<div class="chip-row">' + i.reasons.map(function (r) { return '<span class="badge ' + (r.charAt(0) === 'R' ? 'bad' : 'warn') + '">' + TO.esc(TO.t('why.' + r)) + '</span>'; }).join('') + '</div></article>'; }).join('') + '</div>';
    },
    mount: function (root) {
      root.addEventListener('click', function (e) { var c = e.target.closest('[data-id]'); if (c) TO.openTrip(c.dataset.id); });
      root.addEventListener('keydown', function (e) { if (e.key === 'Enter') { var c = e.target.closest && e.target.closest('[data-id]'); if (c) TO.openTrip(c.dataset.id); } });
    }
  });
})();
