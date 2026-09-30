/* Trip Orders - Activity log: every change with who, when and from which PC (from the signed history). */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var q = '';
  function rowsHTML(rows) {
    if (!rows.length) return U.empty('activity', TO.t('act.none.t'), TO.t('act.none.b'));
    return U.table([
      { h: 'f.time', cell: function (r) { return '<span class="num">' + U.dt(r.ts) + '</span>'; } },
      { h: 'f.user', cell: function (r) { return TO.esc(r.user || ''); } },
      { h: 'f.pc', cell: function (r) { return TO.esc(r.node_name || ''); } },
      { h: 'f.action', cell: function (r) { return TO.esc(r.label || ''); } },
      { h: 'f.what', cell: function (r) { return '<span class="badge">' + TO.esc(r.entity || '') + '</span> <span class="faint">' + TO.esc(r.op || '') + '</span>'; } }
    ], rows);
  }
  TO.views.activity = {
    render: function () {
      return TO.pageHead('nav.activity', 'page.activity.d') + '<div class="toolbar"><input class="input" data-q type="search" placeholder="' + TO.esc(TO.t('list.search')) + '" style="max-width:22rem"></div><div data-body><div class="skeleton" style="height:12rem"></div></div>';
    },
    mount: function (root) {
      var body = root.querySelector('[data-body]'), input = root.querySelector('[data-q]');
      function load() {
        TO.get('/api/audit?limit=200&q=' + encodeURIComponent(q)).then(function (r) { body.innerHTML = rowsHTML(r.rows || []); }, function (e) { body.innerHTML = U.empty('lock', TO.t('common.error'), U.errorText(e)); });
      }
      input.value = q;
      input.addEventListener('input', TO.debounce(function () { q = input.value.trim(); load(); }, 250));
      load();
    }
  };
})();
