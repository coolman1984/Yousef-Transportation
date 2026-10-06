/* Trip Orders - Settings -> Data & backups: Recycle Bin (restore deleted records), backups (make, list, restore), complete export. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var state = null;

  function load() {
    var jobs = [TO.can('trash.restore') ? TO.get('/api/trash') : Promise.resolve([]), TO.can(['backups.manage', 'backups.restore']) ? TO.get('/api/backups') : Promise.resolve([]),
      TO.can('backups.manage') ? TO.get('/api/backups/folder').catch(function () { return null; }) : Promise.resolve(null)];
    return Promise.all(jobs).then(function (r) { state = { trash: r[0], backups: r[1], status: r[2] && r[2].status }; });
  }
  function trashCard() {
    if (!TO.can('trash.restore')) return '';
    var rows = state.trash;
    return '<section class="card"><header><h3>' + TO.icon('refresh') + ' ' + TO.esc(TO.t('bin.title')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('bin.sub')) + '</p>' +
      (rows.length ? U.table([
        { h: 'f.time', cell: function (r) { return '<span class="num">' + U.dt(r.ts) + '</span>'; } },
        { h: 'f.user', cell: function (r) { return TO.esc(r.user || ''); } },
        { h: 'f.what', cell: function (r) { return TO.esc((r.names || []).join('، ') || r.label || ''); } },
        { h: 'f.action', cell: function (r) { return '<button class="btn sm" data-restore="' + TO.esc(r.txn) + '">' + TO.esc(TO.t('bin.restore')) + '</button>'; } }
      ], rows.slice(0, 100)) : U.empty('check', TO.t('bin.empty.t'), TO.t('bin.empty.b'))) + '</section>';
  }
  function backupCard() {
    if (!TO.can(['backups.manage', 'backups.restore'])) return '';
    var rows = state.backups.slice(0, 30), st = state.status || {};
    var warn = st.lastError ? '<div class="tip bad" role="alert" data-bk-warn>' + TO.icon('alert') + '<div>' + TO.esc(TO.t('bk.failed')) + ' <span class="faint">' + TO.esc(st.lastError) + '</span></div></div>' :
      st.stale ? '<div class="tip warn" role="status" data-bk-warn>' + TO.icon('alert') + '<div>' + TO.esc(TO.t('bk.stale')) + '</div></div>' : '';
    return '<section class="card"><header><h3>' + TO.icon('lock') + ' ' + TO.esc(TO.t('bk.title')) + '</h3>' +
      (TO.can('backups.manage') ? '<button class="btn primary sm" data-backup>' + TO.icon('plus', 'sm') + TO.esc(TO.t('bk.make')) + '</button>' : '') + '</header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('bk.sub')) + '</p>' + warn + (warn ? '<div style="height:1rem"></div>' : '') +
      (rows.length ? U.table([
        { h: 'f.time', cell: function (b) { return '<span class="num">' + U.dt(b.time) + '</span>'; } },
        { h: 'f.type', cell: function (b) { return '<span class="badge">' + TO.esc(b.kind || '') + '</span>'; } },
        { h: 'bk.size', cell: function (b) { return b.size ? '<span class="num">' + TO.fmt.num(Math.round(b.size / 1024)) + '</span> KB' : '–'; } },
        { h: 'f.action', cell: function (b) { return TO.can('backups.restore') ? '<button class="btn sm danger" data-brestore="' + TO.esc(b.name) + '">' + TO.esc(TO.t('bk.restore')) + '</button>' : ''; } }
      ], rows) : U.empty('lock', TO.t('bk.empty'))) + '</section>';
  }
  TO.dataTab = {
    render: function () {
      if (!state) return '<div class="skeleton" style="height:12rem"></div>';
      return '<div class="stack">' + trashCard() + backupCard() +
        (TO.can('report.full') ? '<section class="card"><header><h3>' + TO.icon('download') + ' ' + TO.esc(TO.t('exp.title')) + '</h3></header><p class="muted">' + TO.esc(TO.t('exp.sub')) + '</p><div style="margin-top:1rem"><a class="btn" href="/api/export.xlsx">' + TO.icon('download', 'sm') + TO.esc(TO.t('exp.btn')) + '</a></div></section>' : '') + '</div>';
    },
    mount: function (root) {
      if (!state) { load().then(function () { TO.rerender(); }, function () { root.innerHTML = U.empty('alert', TO.t('common.error')); }); return; }
      root.addEventListener('click', function (e) {
        var r = e.target.closest('[data-restore]');
        if (r) { U.run(TO.post('/api/trash/restore', { txn: r.dataset.restore }), 'bin.restored', r).then(function () { state = null; return TO.data.load(); }).then(function () { TO.rerender(); }); return; }
        if (e.target.closest('[data-backup]')) { U.run(TO.post('/api/backups'), 'bk.made').then(function () { state = null; TO.rerender(); }); return; }
        var b = e.target.closest('[data-brestore]');
        if (b) U.confirm({ title: TO.t('bk.restore'), body: TO.t('bk.restore.body'), danger: true, ok: TO.t('bk.restore') }).then(function (ok) {
          if (ok) U.run(TO.post('/api/backups/restore', { name: b.dataset.brestore }), 'bk.restored').then(function () { state = null; return TO.data.load(); }).then(function () { TO.rerender(); });
        });
      });
    },
    reset: function () { state = null; }
  };
})();
