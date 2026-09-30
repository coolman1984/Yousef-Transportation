/* Trip Orders - Settings -> People & access: users, personal links, permission tick boxes, profiles.
   The administrator controls everything here; every right is also checked by the server on each request. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var cache = null;

  function slug(g) { return g.toLowerCase().replace(/[^a-z]+/g, ' ').trim().split(' ').slice(0, 2).join('_'); }
  function permLabel(id, fallback) { return TO.has('perm.' + id) ? TO.t('perm.' + id) : fallback; }
  function groupLabel(g) { var k = 'permgroup.' + slug(g); return TO.has(k) ? TO.t(k) : g; }
  function load() {
    return Promise.all([TO.get('/api/users'), TO.get('/api/quick-links')]).then(function (r) { cache = { users: r[0], links: r[1] }; return cache; });
  }
  function linkFor(uid) { return (cache.links.users || []).filter(function (l) { return l.id === uid; })[0] || {}; }
  function linkUrl(l) { return l.token ? location.origin + '/k/' + l.token : ''; }

  /* ---------- the list ---------- */
  function table() {
    var users = cache.users.users.filter(function (u) { return !u.deleted; });
    return U.table([
      { h: 'f.name', cell: function (u) { return '<b>' + TO.esc(u.full_name) + '</b><div class="muted" style="font-size:.85rem">@' + TO.esc(u.username) + (u.title ? ' · ' + TO.esc(u.title) : '') + '</div>'; } },
      { h: 'acc.profile', cell: function (u) { return '<span class="badge ' + (u.role === 'Administrator' ? 'signal' : '') + '">' + TO.esc(u.role || 'Custom') + '</span>'; } },
      { h: 'acc.login', cell: function (u) { var l = linkFor(u.id); return l.login === 'link' ? '<span class="badge info">' + TO.icon('chat', 'sm') + TO.esc(TO.t('acc.login.link')) + '</span>' : '<span class="badge">' + TO.icon('lock', 'sm') + TO.esc(TO.t('acc.login.pw')) + '</span>'; } },
      { h: 'acc.cats', cell: function (u) { return u.scopes ? '<span class="badge warn">' + TO.fmt.num(u.scopes.length) + ' ' + TO.esc(TO.t('acc.catsOnly')) + '</span>' : '<span class="muted">' + TO.esc(TO.t('acc.allCats')) + '</span>'; } },
      { h: 'acc.last', cell: function (u) { return u.last_login ? '<span class="num">' + U.dt(u.last_login) + '</span>' : '<span class="faint">–</span>'; } },
      { h: 'f.active', cell: function (u) { return u.active ? '<span class="badge ok">' + TO.esc(TO.t('f.activeYes')) + '</span>' : '<span class="badge">' + TO.esc(TO.t('f.inactive')) + '</span>'; } }
    ], users, { click: true, rowAttr: function (u) { return 'data-uid="' + TO.esc(u.id) + '"'; } });
  }

  /* ---------- permission ticks ---------- */
  function ticks(perms, admin) {
    return cache.users.permissions.map(function (g) {
      var isAdmin = g[0].indexOf('Administrator') === 0;
      return '<fieldset class="perm-group' + (isAdmin ? ' admin' : '') + '"><legend>' + TO.esc(groupLabel(g[0])) + (isAdmin ? ' <span class="badge warn">' + TO.esc(TO.t('acc.adminGroup')) + '</span>' : '') + '</legend>' +
        '<div class="perm-grid">' + g[1].map(function (p) {
          return '<label class="perm"><input type="checkbox" data-perm="' + p[0] + '"' + (perms.indexOf(p[0]) >= 0 ? ' checked' : '') + '><span>' + TO.esc(permLabel(p[0], p[1])) + '</span></label>'; }).join('') + '</div></fieldset>';
    }).join('');
  }
  function checked(root) { return TO.$$('[data-perm]', root).filter(function (c) { return c.checked; }).map(function (c) { return c.dataset.perm; }); }

  /* ---------- user form ---------- */
  function openUser(u) {
    var isNew = !u, l = u ? linkFor(u.id) : {}, profiles = cache.users.profiles, cats = TO.data.list('tripCategories');
    var perms = u ? u.perms : (profiles.filter(function (p) { return p.id === 'viewer'; })[0] || { perms: [] }).perms;
    var mode = l.login === 'link' ? 'link' : 'password';
    var scoped = !!(u && u.scopes);
    TO.panel.open({ title: isNew ? TO.t('acc.add') : u.full_name,
      body: '<form id="u-form" autocomplete="off" class="stack">' +
        '<div class="field"><label>' + TO.esc(TO.t('f.name')) + ' <span class="faint">*</span></label><input class="input" name="full_name" value="' + TO.esc(u ? u.full_name : '') + '" required></div>' +
        '<div class="field"><label>' + TO.esc(TO.t('acc.loginHow')) + '</label><div class="seg" role="group"><button type="button" data-mode="password" aria-pressed="' + (mode === 'password') + '">' + TO.esc(TO.t('acc.login.pw')) + '</button><button type="button" data-mode="link" aria-pressed="' + (mode === 'link') + '">' + TO.esc(TO.t('acc.login.link')) + '</button></div><span class="help">' + TO.esc(TO.t('acc.loginHow.h')) + '</span></div>' +
        '<div data-pwbox class="stack"><div class="field"><label>' + TO.esc(TO.t('auth.username')) + '</label><input class="input" name="username" dir="ltr" value="' + TO.esc(u ? u.username : '') + '" autocapitalize="off" spellcheck="false"></div>' +
        (isNew ? '<div class="field"><label>' + TO.esc(TO.t('auth.password')) + '</label><input class="input" name="password" type="text" dir="ltr" autocomplete="off"><span class="help">' + TO.esc(TO.t('acc.pw.h')) + '</span></div>' : '') + '</div>' +
        '<div class="field"><label>' + TO.esc(TO.t('acc.title')) + '</label><input class="input" name="title" value="' + TO.esc(u ? u.title : '') + '"></div>' +
        '<div class="field"><label>' + TO.esc(TO.t('acc.profile')) + '</label><select class="input" name="role">' + profiles.map(function (p) { return '<option value="' + TO.esc(p.name) + '"' + (u && u.role === p.name ? ' selected' : '') + '>' + TO.esc(p.name) + '</option>'; }).join('') + '<option value="Custom"' + (u && (!u.role || u.role === 'Custom') ? ' selected' : '') + '>' + TO.esc(TO.t('acc.custom')) + '</option></select><span class="help">' + TO.esc(TO.t('acc.profile.h')) + '</span></div>' +
        '<div class="field"><label>' + TO.esc(TO.t('acc.cats')) + '</label><div class="seg" role="group"><button type="button" data-scope="all" aria-pressed="' + (!scoped) + '">' + TO.esc(TO.t('acc.allCats')) + '</button><button type="button" data-scope="some" aria-pressed="' + scoped + '">' + TO.esc(TO.t('acc.catsOnly')) + '</button></div>' +
          '<div data-cats class="chip-row" style="margin-top:.4rem"' + (scoped ? '' : ' hidden') + '>' + cats.map(function (c) { return '<label class="perm"><input type="checkbox" data-cat="' + TO.esc(c.id) + '"' + (u && u.scopes && u.scopes.indexOf(c.id) >= 0 ? ' checked' : '') + '><span>' + TO.esc(TO.data.catName(c.id)) + '</span></label>'; }).join('') + '</div></div>' +
        '<div class="field"><div class="row"><span class="switch"><input type="checkbox" name="active"' + (!u || u.active ? ' checked' : '') + '><span></span></span><label style="font-weight:600">' + TO.esc(TO.t('f.active')) + '</label></div></div>' +
        (u && mode === 'link' ? linkBox(u, l) : '') +
        '<div class="field"><label>' + TO.esc(TO.t('acc.perms')) + '</label><div class="row wrap"><button type="button" class="btn sm" data-all>' + TO.esc(TO.t('acc.selectAll')) + '</button><button type="button" class="btn sm ghost" data-none>' + TO.esc(TO.t('acc.clearAll')) + '</button></div></div>' + ticks(perms) +
        '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div></form>',
      footer: (u ? '<div class="row wrap" style="margin-inline-end:auto"><button class="btn sm" data-reset>' + TO.esc(TO.t('acc.reset')) + '</button><button class="btn sm" data-logout>' + TO.esc(TO.t('acc.logout')) + '</button><button class="btn sm danger" data-del>' + TO.esc(TO.t('common.delete')) + '</button></div>' : '') +
        '<button class="btn ghost" data-cancel>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-save>' + TO.esc(TO.t('common.save')) + '</button>',
      mount: function (el) { mountUser(el, u, mode, profiles); } });
  }
  function linkBox(u, l) {
    return '<div class="card" style="background:var(--surface-2)"><b>' + TO.esc(TO.t('acc.link')) + '</b>' + (l.on && l.token ? '<div class="row" style="margin-top:.6rem"><input class="input" readonly dir="ltr" value="' + TO.esc(linkUrl(l)) + '" data-linkurl><button type="button" class="btn sm" data-copy>' + TO.esc(TO.t('common.copy')) + '</button></div>' +
      '<div class="row wrap" style="margin-top:.6rem"><button type="button" class="btn sm" data-newlink>' + TO.esc(TO.t('acc.link.new')) + '</button><button type="button" class="btn sm ghost" data-linkoff>' + TO.esc(TO.t('acc.link.off')) + '</button></div>' :
      '<p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('acc.link.none')) + '</p><button type="button" class="btn sm primary" data-newlink style="margin-top:.5rem">' + TO.esc(TO.t('acc.link.make')) + '</button>') + '</div>';
  }
  function mountUser(el, u, mode, profiles) {
    var form = el.querySelector('#u-form'), err = el.querySelector('.err');
    function showErr(m) { err.hidden = false; err.textContent = m; }
    function sync() { el.querySelector('[data-pwbox]').style.display = mode === 'password' ? '' : 'none'; TO.$$('[data-mode]', el).forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.mode === mode); }); }
    sync();
    el.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.dataset.mode) { mode = b.dataset.mode; sync(); }
      else if (b.dataset.scope) { TO.$$('[data-scope]', el).forEach(function (x) { x.setAttribute('aria-pressed', x === b); }); el.querySelector('[data-cats]').hidden = b.dataset.scope === 'all'; }
      else if (b.hasAttribute('data-all')) TO.$$('[data-perm]', el).forEach(function (c) { if (!c.closest('.admin')) c.checked = true; });
      else if (b.hasAttribute('data-none')) TO.$$('[data-perm]', el).forEach(function (c) { c.checked = false; });
      else if (b.hasAttribute('data-copy')) { var inp = el.querySelector('[data-linkurl]'); inp.select(); try { document.execCommand('copy'); TO.toast(TO.t('common.saved')); } catch (x) { /* the user can still copy by hand */ } }
      else if (b.hasAttribute('data-newlink')) U.run(TO.post('/api/quick-links/set', { id: u.id, on: true }), 'acc.link.done').then(function () { return load(); }).then(function () { TO.panel.close(); openUser(cache.users.users.filter(function (x) { return x.id === u.id; })[0]); });
      else if (b.hasAttribute('data-linkoff')) U.run(TO.post('/api/quick-links/set', { id: u.id, on: false }), 'acc.link.offdone').then(function () { return load(); }).then(function () { TO.panel.close(); openUser(cache.users.users.filter(function (x) { return x.id === u.id; })[0]); });
      else if (b.hasAttribute('data-cancel')) TO.panel.close();
      else if (b.hasAttribute('data-reset')) U.confirm({ title: TO.t('acc.reset'), body: TO.t('acc.reset.body'), reason: TO.t('auth.password'), ok: TO.t('common.save') }).then(function (pw) { if (pw) U.run(TO.post('/api/users/reset', { id: u.id, password: pw }), 'acc.reset.done'); });
      else if (b.hasAttribute('data-logout')) U.run(TO.post('/api/users/logout', { id: u.id }), 'acc.logout.done');
      else if (b.hasAttribute('data-del')) U.confirm({ title: TO.t('common.delete'), body: TO.t('acc.delete.body', { n: u.full_name }), danger: true, ok: TO.t('common.delete') }).then(function (ok) { if (ok) U.run(TO.post('/api/users/delete', { id: u.id }), 'list.deleted.toast').then(function () { TO.panel.close(); TO.rerender(); }); });
      else if (b.hasAttribute('data-save')) save();
    });
    el.querySelector('[name="role"]').addEventListener('change', function (e) {   // choosing a profile fills the ticks
      var p = profiles.filter(function (x) { return x.name === e.target.value; })[0];
      if (p) TO.$$('[data-perm]', el).forEach(function (c) { c.checked = p.perms.indexOf(c.dataset.perm) >= 0; });
    });
    el.addEventListener('change', function (e) { if (e.target.dataset && e.target.dataset.perm) el.querySelector('[name="role"]').value = 'Custom'; });
    function save() {
      var f = function (n) { return (form.querySelector('[name="' + n + '"]') || {}).value || ''; };
      var scopes = el.querySelector('[data-scope="some"]').getAttribute('aria-pressed') === 'true' ? TO.$$('[data-cat]', el).filter(function (c) { return c.checked; }).map(function (c) { return c.dataset.cat; }) : null;
      var body = { id: u ? u.id : undefined, full_name: f('full_name').trim(), username: mode === 'password' ? f('username').trim() : (u ? u.username : ''), title: f('title').trim(), role: f('role'), login: mode,
        perms: checked(el), scopes: scopes, active: form.querySelector('[name="active"]').checked, must_change: !u };
      if (!u && mode === 'password') body.password = f('password');
      if (!body.full_name) return showErr(TO.t('form.missing', { f: TO.t('f.name') }));
      U.run(TO.post('/api/users/save', body), 'common.saved', el.querySelector('[data-save]')).then(function (r) {
        return load().then(function () {
          TO.panel.close(); TO.rerender();
          if (r && r.token) TO.toast(TO.t('acc.link.done'));
        });
      }, function (e) { showErr(U.errorText(e)); });
    }
  }

  /* ---------- profiles ---------- */
  function openProfiles() {
    var list = cache.users.profiles;
    var el = TO.dialog({ title: TO.t('acc.profiles'), wide: true,
      body: '<p class="muted">' + TO.esc(TO.t('acc.profiles.h')) + '</p><div class="stack">' + list.map(function (p) {
        return '<div class="card row" style="justify-content:space-between"><div><b>' + TO.esc(p.name) + '</b><div class="muted" style="font-size:.85rem">' + TO.fmt.num(p.perms.length) + ' ' + TO.esc(TO.t('acc.perms.count')) + '</div></div>' +
          (p.id === 'administrator' ? '<span class="badge signal">' + TO.icon('lock', 'sm') + TO.esc(TO.t('acc.locked')) + '</span>' : '<button class="btn sm" data-edit="' + TO.esc(p.id) + '">' + TO.esc(TO.t('common.open')) + '</button>') + '</div>'; }).join('') + '</div>',
      footer: '<button class="btn primary" data-newprofile>' + TO.icon('plus', 'sm') + TO.esc(TO.t('acc.profile.add')) + '</button>' });
    el.addEventListener('click', function (e) {
      if (e.target.closest('[data-newprofile]')) { TO.overlay.close(); editProfile(null); }
      var b = e.target.closest('[data-edit]'); if (b) { TO.overlay.close(); editProfile(list.filter(function (p) { return p.id === b.dataset.edit; })[0]); }
    });
  }
  function editProfile(p) {
    var el = TO.dialog({ title: p ? p.name : TO.t('acc.profile.add'), wide: true,
      body: '<div class="field"><label>' + TO.esc(TO.t('f.name')) + '</label><input class="input" id="pf-name" value="' + TO.esc(p ? p.name : '') + '"></div><div class="field"><div class="row"><span class="switch"><input type="checkbox" id="pf-apply" checked><span></span></span><label for="pf-apply" style="font-weight:600">' + TO.esc(TO.t('acc.profile.apply')) + '</label></div></div>' + ticks(p ? p.perms : []) + '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>',
      footer: (p ? '<button class="btn danger" data-del style="margin-inline-end:auto">' + TO.esc(TO.t('common.delete')) + '</button>' : '') + '<button class="btn ghost" data-close>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-ok>' + TO.esc(TO.t('common.save')) + '</button>' });
    el.querySelector('[data-ok]').addEventListener('click', function () {
      var err = el.querySelector('.err');
      U.run(TO.post('/api/profiles/save', { id: p ? p.id : undefined, name: el.querySelector('#pf-name').value.trim(), perms: checked(el), apply: el.querySelector('#pf-apply').checked }), 'common.saved').then(function () { return load(); }).then(function () { TO.overlay.close(); TO.rerender(); }, function (e) { err.hidden = false; err.textContent = U.errorText(e); });
    });
    var del = el.querySelector('[data-del]');
    if (del) del.addEventListener('click', function () { U.run(TO.post('/api/profiles/delete', { id: p.id }), 'list.deleted.toast').then(function () { return load(); }).then(function () { TO.overlay.close(); TO.rerender(); }); });
  }

  /* ---------- the tab ---------- */
  TO.accessTab = {
    render: function () {
      if (!TO.can('users.manage')) return '<section class="card">' + U.empty('lock', TO.t('acc.noperm.t'), TO.t('acc.noperm.b')) + '</section>';
      if (!cache) return '<div class="skeleton" style="height:12rem"></div>';
      var auth = cache.users.authority;
      return (auth ? '' : '<div class="tip" style="margin-bottom:1rem;background:var(--warn-soft)">' + TO.icon('alert') + '<span>' + TO.esc(cache.users.authorityHint || TO.t('acc.notAuth')) + '</span></div>') +
        '<div class="toolbar"><h2 class="grow">' + TO.esc(TO.t('acc.title.users')) + '</h2><button class="btn" data-profiles>' + TO.icon('layers', 'sm') + TO.esc(TO.t('acc.profiles')) + '</button>' +
        (auth ? '<button class="btn primary" data-adduser>' + TO.icon('plus', 'sm') + TO.esc(TO.t('acc.add')) + '</button>' : '') + '</div>' + table();
    },
    mount: function (root) {
      if (!TO.can('users.manage')) return;
      if (!cache) { load().then(function () { TO.rerender(); }, function () { root.innerHTML = U.empty('alert', TO.t('common.error')); }); return; }
      root.addEventListener('click', function (e) {
        if (e.target.closest('[data-adduser]')) { openUser(null); return; }
        if (e.target.closest('[data-profiles]')) { openProfiles(); return; }
        var tr = e.target.closest('tr[data-uid]'); if (tr && cache.users.authority) openUser(cache.users.users.filter(function (u) { return u.id === tr.dataset.uid; })[0]);
      });
    },
    reset: function () { cache = null; }
  };
})();
