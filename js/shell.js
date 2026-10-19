/* Trip Orders - the application shell: side menu, top bar, router, side panels, command palette, keyboard shortcuts,
   guided tour and welcome slides. Pages plug in through TO.views[id] = { render(ctx) -> html, mount(root, ctx) }. */
(function () {
  'use strict';
  var TO = window.TO;

  /* ---------- page registry (order = menu order) ---------- */
  // perm: permission (or list) that shows the page; key: the letter after "G" that jumps there; phase: when it is built
  var PAGES = [
    { id: 'overview', icon: 'home', group: 'ops', perm: 'overview.view', key: 'o', phase: 1 },
    { id: 'trips', icon: 'route', group: 'ops', perm: 'trips.view', key: 't', phase: 2 },
    { id: 'board', icon: 'board', group: 'ops', perm: 'board.view', key: 'b', phase: 2 },
    { id: 'review', icon: 'shield', group: 'ops', perm: 'review.view', key: 'r', phase: 2 },
    { id: 'vehicles', icon: 'car', group: 'fleet', perm: 'fleet.view', key: 'v', phase: 2 },
    { id: 'drivers', icon: 'wheel', group: 'fleet', perm: 'fleet.view', key: 'd', phase: 2 },
    { id: 'people', icon: 'users', group: 'fleet', perm: 'people.view', key: 'p', phase: 2 },
    { id: 'places', icon: 'pin', group: 'fleet', perm: 'people.view', key: 'l', phase: 2 },
    { id: 'reports', icon: 'chart', group: 'insight', perm: 'reports.view', key: 'e', phase: 1 },
    { id: 'excel', icon: 'sheet', group: 'insight', perm: ['excel.import', 'excel.export'], key: 'x', phase: 1 },
    { id: 'activity', icon: 'activity', group: 'control', perm: 'logs.view', key: 'a', phase: 2 },
    { id: 'settings', icon: 'settings', group: 'control', perm: null, key: 's', phase: 1 },
    { id: 'help', icon: 'help', group: 'control', perm: null, key: 'h', phase: 1 }
  ];
  var GROUPS = ['ops', 'fleet', 'insight', 'control'];
  TO.pages = PAGES;

  TO.can = function (perm) {
    var me = TO.me;
    if (!perm) return true;
    if (!me) return false;
    var list = Array.isArray(perm) ? perm : [perm];
    return list.some(function (p) { return (me.perms || []).indexOf(p) >= 0; });
  };
  function visiblePages() { return PAGES.filter(function (p) { return TO.can(p.perm); }); }

  /* ---------- router ---------- */
  TO.route = function () {
    var h = location.hash.replace(/^#\/?/, '');
    var qi = h.indexOf('?');
    var path = qi >= 0 ? h.slice(0, qi) : h;
    var q = {};
    if (qi >= 0) h.slice(qi + 1).split('&').forEach(function (kv) { if (kv) { var a = kv.split('='); q[decodeURIComponent(a[0])] = decodeURIComponent(a[1] || ''); } });
    var parts = path.split('/').filter(Boolean);
    return { path: parts[0] || 'overview', parts: parts, q: q };
  };
  TO.go = function (path) { location.hash = '#/' + path.replace(/^#?\/?/, ''); };

  /* ---------- shell ---------- */
  var shellReady = false;
  function shellHTML() {
    var me = TO.me;
    var groups = GROUPS.map(function (g) {
      var items = visiblePages().filter(function (p) { return p.group === g; });
      if (!items.length) return '';
      return '<div class="nav-group"><span>' + TO.esc(TO.t('nav.g.' + g)) + '</span>' + items.map(function (p) {
        return '<a href="#/' + p.id + '" data-page="' + p.id + '" class="' + (p.phase > 1 ? 'soon' : '') + '" title="' + TO.esc(TO.t('nav.' + p.id)) + '">' +
          TO.icon(p.icon) + '<span>' + TO.esc(TO.t('nav.' + p.id)) + '</span><i class="kbd kbd-hint">' + p.key.toUpperCase() + '</i></a>';
      }).join('') + '</div>';
    }).join('');
    var initials = (me.full_name || me.username || '?').trim().split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
    return '<div class="app" id="app-shell" data-collapsed="' + (TO.prefs.data.collapsed ? 1 : 0) + '">' +
      '<aside class="sidebar" id="sidebar" aria-label="' + TO.esc(TO.t('top.menu')) + '">' +
        '<div class="brand"><div class="mark">' + TO.icon('route', 'lg') + '</div><div class="name">' + TO.esc(TO.t('app.name')) + '<small>' + TO.esc(TO.t('app.tagline')) + '</small></div></div>' +
        '<nav class="nav" data-tour="nav">' + groups + '</nav>' +
        '<div class="side-foot"><button class="icon-btn" data-act="account" aria-label="' + TO.esc(TO.t('top.account')) + '" style="background:var(--side-active);color:var(--side-ink);font-weight:700;border-radius:50%">' + TO.esc(initials) + '</button>' +
          '<div class="who"><b>' + TO.esc(me.full_name || me.username) + '</b><small>' + TO.esc(me.role || '') + '</small></div>' +
          '<button class="icon-btn mirror-ic" data-act="collapse" aria-label="' + TO.esc(TO.t('top.collapse')) + '" title="' + TO.esc(TO.t('top.collapse')) + ' ([)">' + TO.icon('collapse') + '</button></div>' +
      '</aside>' +
      '<div class="main">' +
        (me.training ? '<div class="train-bar" role="status">' + TO.icon('info') + '<span class="grow">' + TO.esc(TO.t('train.bar')) + '</span>' +
          '<button class="btn primary" data-act="real">' + TO.icon('route', 'sm') + TO.esc(TO.t('train.back')) + '</button></div>' : '') +
        '<header class="topbar">' +
          '<button class="icon-btn menu-btn" data-act="menu" aria-label="' + TO.esc(TO.t('top.menu')) + '">' + TO.icon('menu') + '</button>' +
          '<div class="crumbs" id="crumbs"></div>' +
          (me.training ? '' : '<button class="btn sm train-btn desk-only" data-act="training" title="' + TO.esc(TO.t('train.title')) + '">' + TO.icon('play', 'sm') + TO.esc(TO.t('train.btn')) + '</button>') +
          '<span class="grow"></span>' +
          '<button class="search-trigger" data-act="palette" data-tour="search" aria-label="' + TO.esc(TO.t('top.search')) + '">' + TO.icon('search', 'sm') + '<span>' + TO.esc(TO.t('top.search')) + '</span><i class="kbd">Ctrl K</i></button>' +
          '<span class="grow" style="flex:0 0 0"></span>' +
          '<span data-tour="tools" class="row" style="gap:.2rem">' +
          '<span data-guide-slot class="row"></span>' +
          '<button class="icon-btn" data-act="report" data-guide="report" aria-label="' + TO.esc(TO.t('report.open')) + '" title="' + TO.esc(TO.t('report.open')) + '">' + TO.icon('alert') + '</button>' +
          '<button class="icon-btn" data-act="lang" aria-label="' + TO.esc(TO.t('top.lang')) + '" title="' + TO.esc(TO.t('top.lang')) + ' (L)">' + TO.icon('globe') + '</button>' +
          '<button class="icon-btn" data-act="theme" id="theme-btn" aria-label="' + TO.esc(TO.t('top.theme')) + '" title="' + TO.esc(TO.t('top.theme')) + ' (T)"></button>' +
          '<button class="icon-btn" data-act="keys" aria-label="' + TO.esc(TO.t('top.shortcuts')) + '" title="' + TO.esc(TO.t('top.shortcuts')) + ' (?)">' + TO.icon('keyboard') + '</button>' +
          '</span>' +
        '</header>' +
        '<main class="content" id="view" tabindex="-1"></main>' +
      '</div>' +
      '<div id="panels" aria-live="polite"></div>' +
      '</div>';
  }

  TO.shell = {
    start: function () {
      var root = TO.$('#root');
      root.innerHTML = shellHTML() + '<div id="overlay"></div><div id="toasts" aria-live="polite"></div><div id="tour"></div><div id="slides"></div>';
      shellReady = true;
      refreshThemeButton();
      var lastPage = location.hash.split('?')[0];
      window.addEventListener('hashchange', function () {
        var page = location.hash.split('?')[0];     // moving to another page closes the side panel and any open dialog; a filter change on the same page does not
        if (page !== lastPage) { lastPage = page; if (TO.panel.count()) TO.panel.close(); if (TO.overlay.isOpen) TO.overlay.close(); }
        renderRoute();
      });
      renderRoute();
      if (!TO.prefs.data.welcomed) setTimeout(function () { TO.slides.open(true); }, 500);
    },
    stop: function () { shellReady = false; }
  };

  function refreshThemeButton() {
    var b = TO.$('#theme-btn');
    if (b) b.innerHTML = TO.icon(TO.prefs.isDark() ? 'sun' : 'moon');
  }

  function renderRoute() {
    if (!shellReady) return;
    var r = TO.route();
    var page = PAGES.filter(function (p) { return p.id === r.path; })[0];
    if (!page || !TO.can(page.perm)) {
      if (r.path && !PAGES.some(function (p) { return p.id === r.path; })) {
        var host = TO.$('#view'), old = host.cloneNode(false);
        host.replaceWith(old);
        old.innerHTML = TO.pageHead ? TO.pageHead('err.pageNotFound', 'err.pageNotFound.d') : '<div class="card"><h2>' + TO.esc(TO.t('err.pageNotFound')) + '</h2></div>';
        document.title = trainTitle() + TO.t('err.pageNotFound') + ' · ' + TO.t('app.name');
        return;
      }
      TO.go('overview'); return;
    }
    TO.$$('#sidebar a[data-page]').forEach(function (a) { if (a.dataset.page === page.id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    TO.$('#crumbs').innerHTML = '<span class="mut">' + TO.esc(TO.t('app.name')) + '</span><span class="mut faint">/</span><b>' + TO.esc(TO.t('nav.' + page.id)) + '</b>';
    document.title = trainTitle() + TO.t('nav.' + page.id) + ' · ' + TO.t('app.name');
    var view = TO.views[page.id] || TO.views.soon;
    var old = TO.$('#view'), host = old.cloneNode(false);   // a fresh element: no listeners of the previous page stay behind, and the page-in animation replays
    old.replaceWith(host);
    var ctx = { page: page, route: r, me: TO.me };
    host.innerHTML = view.render(ctx);
    if (view.mount) view.mount(host, ctx);
    window.scrollTo(0, 0);
    TO.emit('route', r);
  }
  TO.rerender = function () { renderRoute(); };

  /* ---------- rebuild everything when language or theme changes ---------- */
  TO.on('lang-changed', function () { if (shellReady) { rebuildShell(); } });
  TO.on('prefs-applied', function () { if (shellReady) refreshThemeButton(); });
  function rebuildShell() {
    var collapsed = TO.prefs.data.collapsed;
    var root = TO.$('#root');
    var panelsOpen = panelStack.slice();
    root.innerHTML = shellHTML() + '<div id="overlay"></div><div id="toasts" aria-live="polite"></div><div id="tour"></div><div id="slides"></div>';
    TO.$('#app-shell').dataset.collapsed = collapsed ? 1 : 0;
    refreshThemeButton();
    panelStack = [];
    renderRoute();
    panelsOpen.forEach(function (p) { TO.panel.open(p.opts, true); });
  }

  /* ---------- side panels (stackable, Esc closes the top one) ---------- */
  var panelStack = [];
  TO.panel = {
    open: function (opts, instant) {
      var host = TO.$('#panels');
      if (!host) return;
      if (!panelStack.length) {
        var sc = document.createElement('div');
        sc.className = 'drawer-scrim';
        sc.addEventListener('click', function () { TO.panel.close(); });
        host.appendChild(sc);
        requestAnimationFrame(function () { sc.classList.add('on'); });
      }
      panelStack.forEach(function (p) { p.el.classList.add('behind'); });
      var el = document.createElement('aside');
      el.className = 'drawer';
      el.setAttribute('role', 'dialog');
      el.setAttribute('aria-label', opts.title);
      el.innerHTML = '<header><h2>' + (opts.ltr ? '<bdi dir="ltr">' + TO.esc(opts.title) + '</bdi>' : TO.esc(opts.title)) + '</h2><button class="icon-btn" data-pclose aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x') + '</button></header>' +
        '<div class="body">' + opts.body + '</div>' + (opts.footer ? '<footer>' + opts.footer + '</footer>' : '');
      host.appendChild(el);
      el.querySelector('[data-pclose]').addEventListener('click', function () { TO.panel.close(); });
      panelStack.push({ el: el, opts: opts });
      if (instant) el.classList.add('on'); else requestAnimationFrame(function () { requestAnimationFrame(function () { el.classList.add('on'); }); });
      if (opts.mount) opts.mount(el);
      host.style.pointerEvents = 'auto';
      return el;
    },
    close: function () {
      var top = panelStack.pop();
      if (!top) return false;
      var host = TO.$('#panels');
      top.el.classList.remove('on');
      setTimeout(function () { top.el.remove(); }, 260);
      if (panelStack.length) panelStack[panelStack.length - 1].el.classList.remove('behind');
      else {
        var sc = host.querySelector('.drawer-scrim');
        if (sc) { sc.classList.remove('on'); setTimeout(function () { sc.remove(); }, 260); }
        host.style.pointerEvents = 'none';
      }
      return true;
    },
    count: function () { return panelStack.length; }
  };

  /* ---------- command palette ---------- */
  function norm(s) {
    return String(s || '').toLowerCase().replace(/[ً-ٰٟ]/g, '').replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه');
  }
  function paletteItems() {
    var items = visiblePages().map(function (p) {
      return { icon: p.icon, label: TO.t('nav.' + p.id), group: TO.t('pal.g.pages'), hint: 'G ' + p.key.toUpperCase(), run: function () { TO.go(p.id); } };
    });
    items.push(
      { icon: 'plus', label: TO.t('act.newtrip'), group: TO.t('pal.g.actions'), hint: 'N', run: function () { TO.newTrip(); } },
      { icon: 'moon', label: TO.t('act.theme.toggle'), group: TO.t('pal.g.appearance'), hint: 'T', run: function () { TO.prefs.toggleTheme(); } },
      { icon: 'globe', label: TO.t('act.lang.toggle'), group: TO.t('pal.g.appearance'), hint: 'L', run: function () { TO.prefs.toggleLang(); } },
      { icon: 'collapse', label: TO.t('act.collapse'), group: TO.t('pal.g.appearance'), hint: '[', run: function () { toggleCollapse(); } },
      { icon: 'keyboard', label: TO.t('act.shortcuts'), group: TO.t('pal.g.actions'), hint: '?', run: function () { showKeys(); } },
      { icon: 'alert', label: TO.t('report.open'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.guide.report({}); } },
      { icon: 'help', label: TO.t('guide.open'), group: TO.t('pal.g.actions'), hint: 'F1', run: function () { TO.guide.open(); } },
      { icon: 'play', label: TO.t('act.tour'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.tour.start(); } },
      { icon: 'present', label: TO.t('act.slides'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.slides.open(); } },
      { icon: 'info', label: TO.t('act.about'), group: TO.t('pal.g.actions'), hint: '', run: function () { openAbout(); } }
    );
    if (TO.can('vehicles.manage') || TO.can('drivers.manage')) items.push({ icon: 'sheet', label: TO.t('act.tour.fleet'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.tour.start('fleet'); } });
    if (TO.me.training) items.push({ icon: 'route', label: TO.t('train.back'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.training.back(); } });
    else items.push({ icon: 'play', label: TO.t('train.btn'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.training.open(); } });
    if (TO.me.signIn) items.push({ icon: 'logout', label: TO.t('act.logout'), group: TO.t('pal.g.actions'), hint: '', run: function () { logout(); } });
    return items;
  }
  function openPalette() {
    var all = paletteItems(), sel = 0, list = all;
    var o = TO.overlay.open('<div class="dialog palette" role="dialog" aria-modal="true" aria-label="' + TO.esc(TO.t('top.search')) + '">' +
      '<input id="pal-q" type="text" autocomplete="off" spellcheck="false" placeholder="' + TO.esc(TO.t('pal.placeholder')) + '" aria-label="' + TO.esc(TO.t('top.search')) + '">' +
      '<ul id="pal-list" role="listbox"></ul>' +
      '<div class="foot"><span><i class="kbd">↑</i> <i class="kbd">↓</i> ' + TO.esc(TO.t('pal.move')) + '</span><span><i class="kbd">↵</i> ' + TO.esc(TO.t('pal.open')) + '</span><span><i class="kbd">Esc</i> ' + TO.esc(TO.t('pal.close')) + '</span></div></div>', { center: false });
    var q = TO.$('#pal-q', o), ul = TO.$('#pal-list', o);
    function paint() {
      if (!list.length) { ul.innerHTML = '<li class="faint" style="cursor:default">' + TO.esc(TO.t('pal.none')) + '</li>'; return; }
      ul.innerHTML = list.map(function (it, i) {
        return '<li role="option" data-i="' + i + '" aria-selected="' + (i === sel) + '">' + TO.icon(it.icon) + '<span>' + TO.esc(it.label) + '</span>' +
          '<span class="grp">' + (it.hint ? '<i class="kbd">' + TO.esc(it.hint) + '</i> ' : '') + TO.esc(it.group) + '</span></li>';
      }).join('');
      var cur = ul.querySelector('[aria-selected="true"]');
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
    }
    function run(i) { var it = list[i]; if (!it) return; TO.overlay.close(); setTimeout(it.run, 30); }
    q.addEventListener('input', function () {
      var n = norm(q.value);
      list = all.filter(function (it) { return !n || norm(it.label).indexOf(n) >= 0 || norm(it.group).indexOf(n) >= 0; });
      if (n.length >= 2 && TO.data && TO.data.state && TO.paletteRecords) list = list.concat(TO.paletteRecords(q.value).slice(0, 8));
      sel = 0; paint();
    });
    q.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { sel = Math.min(list.length - 1, sel + 1); paint(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); paint(); e.preventDefault(); }
      else if (e.key === 'Enter') { run(sel); e.preventDefault(); }
    });
    ul.addEventListener('click', function (e) { var li = e.target.closest('li[data-i]'); if (li) run(Number(li.dataset.i)); });
    paint();
  }
  TO.palette = { open: openPalette };

  /* ---------- keyboard shortcuts sheet ---------- */
  function showKeys() {
    var rows = [
      ['Ctrl K', 'keys.search'], ['?', 'keys.help'], ['G + O T B R V D P L E X A S H', 'keys.go'], ['T', 'keys.theme'], ['L', 'keys.lang'],
      ['[', 'keys.collapse'], ['Esc', 'keys.close'], ['N', 'keys.new'], ['[ ]', 'keys.day']
    ];
    rows[8][0] = '← →';
    TO.dialog({ title: TO.t('keys.title'), wide: true,
      body: '<div class="keys">' + rows.map(function (r) { return '<div><span>' + TO.esc(TO.t(r[1])) + '</span><span>' + r[0].split(' ').map(function (k) { return k === '+' ? '+' : '<i class="kbd">' + TO.esc(k) + '</i>'; }).join(' ') + '</span></div>'; }).join('') + '</div>' +
        '<p class="faint">' + TO.esc(TO.t('keys.note')) + '</p>' });
  }
  TO.showKeys = showKeys;

  function openAbout() {
    TO.get('/api/auth/status').then(function (s) {
      var a = s.about || {};
      TO.panel.open({ title: TO.t('panel.about'), body:
        '<div class="card"><div class="row"><div class="brand" style="padding:0;min-height:0"><div class="mark" style="background:var(--signal)">' + TO.icon('route', 'lg') + '</div></div><div><h3>' + TO.esc(TO.t('app.name')) + '</h3><span class="muted">' + TO.esc(TO.t('common.version')) + ' <span class="num">' + TO.esc(a.version || '') + '</span></span></div></div>' +
        '<p style="margin-top:.9rem">' + TO.esc(TO.t('panel.about.body')) + '</p></div>' +
        '<div class="tip">' + TO.icon('info') + '<span>' + TO.esc(TO.t('panel.sheet')) + '</span></div>' +
        '<dl class="kv"><dt>©</dt><dd>' + TO.esc((a.copyright || '').replace('©', '').trim()) + '</dd></dl>' });
    });
  }

  function openAccount() {
    var me = TO.me;
    TO.panel.open({ title: TO.t('panel.account'), body:
      '<div class="card"><h3>' + TO.esc(me.full_name || me.username) + '</h3><span class="muted">@' + TO.esc(me.username) + '</span>' +
      '<dl class="kv" style="margin-top:1rem"><dt>' + TO.esc(TO.t('panel.account.role')) + '</dt><dd>' + TO.esc(me.role || '') + '</dd>' +
      '<dt>' + TO.esc(TO.t('panel.account.node')) + '</dt><dd>' + TO.esc(me.node ? me.node.name : '') + '</dd>' +
      '<dt>' + TO.esc(TO.t('panel.account.perms')) + '</dt><dd><span class="num">' + (me.perms || []).length + '</span></dd></dl></div>',
      footer: !me.signIn ? '' : (me.viaLink ? '' : '<button class="btn" data-pw>' + TO.icon('lock', 'sm') + TO.esc(TO.t('pw.change')) + '</button>') +
        '<button class="btn" data-logout>' + TO.icon('logout', 'sm') + TO.esc(TO.t('auth.logout')) + '</button>',
      mount: function (el) {
        var out = el.querySelector('[data-logout]'); if (out) out.addEventListener('click', logout);
        var pw = el.querySelector('[data-pw]'); if (pw) pw.addEventListener('click', changePassword);
      } });
  }
  // the person changes their own password (the administrator gave a temporary one; the guide "first" walks through it)
  function changePassword() {
    var el = TO.dialog({ title: TO.t('pw.change'),
      body: '<p class="muted">' + TO.esc(TO.t('pw.change.d')) + '</p>' +
        '<div class="field"><label for="pw-old">' + TO.esc(TO.t('pw.old')) + '</label><input class="input" id="pw-old" type="password" dir="ltr" autocomplete="current-password"></div>' +
        '<div class="field"><label for="pw-new">' + TO.esc(TO.t('pw.new')) + '</label><input class="input" id="pw-new" type="password" dir="ltr" autocomplete="new-password"><span class="help">' + TO.esc(TO.t('auth.pw.hint')) + '</span></div>' +
        '<div class="tip bad err" hidden role="alert"></div>',
      footer: '<button class="btn ghost" data-close>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-ok>' + TO.esc(TO.t('common.save')) + '</button>' });
    el.querySelector('[data-ok]').addEventListener('click', function () {
      var err = el.querySelector('.err'), btn = el.querySelector('[data-ok]');
      btn.disabled = true;
      TO.post('/api/auth/password', { old: el.querySelector('#pw-old').value, new: el.querySelector('#pw-new').value }).then(function () {
        TO.overlay.close(); TO.toast(TO.t('pw.changed'));
      }, function (e) { btn.disabled = false; err.hidden = false; err.textContent = TO.ui.errorText(e); });
    });
  }

  /* ---------- training mode (server/training.py): a separate copy with sample data, one button in and one button back ---------- */
  function trainTitle() { return TO.me && TO.me.training ? TO.t('train.btn') + ' · ' : ''; }   // the training tab never looks like the real one
  function portUrl(port) { return 'http://' + location.hostname + ':' + port + '/'; }   // both copies listen on plain http ports, also behind an https front
  TO.training = {
    open: function () {
      var el = TO.dialog({ title: TO.t('train.title'),
        body: '<p>' + TO.esc(TO.t('train.body')) + '</p><div class="tip">' + TO.icon('info') + '<span>' + TO.esc(TO.t('train.how')) + '</span></div>' +
          '<div class="tip bad err" hidden role="alert"></div>',
        footer: '<button class="btn ghost" data-train-reset title="' + TO.esc(TO.t('train.reset.d')) + '">' + TO.icon('refresh', 'sm') + TO.esc(TO.t('train.reset')) + '</button>' +
          '<span class="grow"></span><button class="btn primary lg" data-train-go>' + TO.icon('play', 'sm') + TO.esc(TO.t('train.go')) + '</button>' });
      function go(path) {
        var btns = el.querySelectorAll('footer .btn'), err = el.querySelector('.err');
        btns.forEach(function (b) { b.disabled = true; });
        el.querySelector('[data-train-go]').textContent = TO.t('train.wait');
        TO.post(path).then(function (r) { location.href = portUrl(r.port); }, function (e) {
          btns.forEach(function (b) { b.disabled = false; });
          el.querySelector('[data-train-go]').textContent = TO.t('train.go');
          err.hidden = false; err.textContent = TO.ui.errorText(e);
        });
      }
      el.querySelector('[data-train-go]').addEventListener('click', function () { go('/api/training/open'); });
      el.querySelector('[data-train-reset]').addEventListener('click', function () { go('/api/training/reset'); });
    },
    back: function () { if (TO.me && TO.me.realPort) location.href = portUrl(TO.me.realPort); }
  };

  function logout() {
    TO.post('/api/auth/logout').then(function () { TO.emit('logged-out'); }, function () { TO.emit('logged-out'); });
  }
  function toggleCollapse() {
    var v = !TO.prefs.data.collapsed;
    TO.prefs.data.collapsed = v; TO.prefs.save();
    var app = TO.$('#app-shell'); if (app) app.dataset.collapsed = v ? 1 : 0;
  }

  /* ---------- clicks and keys ---------- */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (!b || !shellReady) return;
    var a = b.dataset.act;
    if (a === 'palette') openPalette();
    else if (a === 'theme') TO.prefs.toggleTheme();
    else if (a === 'lang') TO.prefs.toggleLang();
    else if (a === 'keys') showKeys();
    else if (a === 'collapse') toggleCollapse();
    else if (a === 'account') openAccount();
    else if (a === 'report') TO.guide.report({});
    else if (a === 'training') TO.training.open();
    else if (a === 'real') TO.training.back();
    else if (a === 'menu') { var app = TO.$('#app-shell'); app.dataset.menu = app.dataset.menu === '1' ? 0 : 1; }
  });
  document.addEventListener('click', function (e) {   // on a phone the menu closes after choosing a page
    if (e.target.closest('#sidebar a[data-page]')) { var app = TO.$('#app-shell'); if (app) app.dataset.menu = 0; }
    else if (e.target.id === 'app-shell' || (e.target.closest && e.target.closest('.app[data-menu="1"]') && !e.target.closest('#sidebar') && !e.target.closest('[data-act="menu"]'))) {
      var ap = TO.$('#app-shell'); if (ap && ap.dataset.menu === '1' && e.target.closest('.main') === null) ap.dataset.menu = 0;
    }
  });

  var goPending = 0;
  document.addEventListener('keydown', function (e) {
    if (!shellReady) return;
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.code === 'KeyK') { e.preventDefault(); if (TO.overlay.isOpen) TO.overlay.close(); else openPalette(); return; }
    if (e.key === 'Escape') {
      if (TO.overlay.isOpen) { TO.overlay.close(); return; }
      if (TO.tour.active) { TO.tour.stop(); return; }
      if (TO.slides.active) { TO.slides.close(); return; }
      if (TO.panel.count()) { TO.panel.close(); return; }
      if (TO.coach && TO.coach.active()) { TO.coach.stop(); return; }
      var app = TO.$('#app-shell'); if (app && app.dataset.menu === '1') app.dataset.menu = 0;
      return;
    }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || TO.overlay.isOpen) return;
    if (TO.tour.active) {
      var tourRtl = document.documentElement.dir === 'rtl';
      var tourNext = tourRtl ? 'ArrowLeft' : 'ArrowRight', tourPrev = tourRtl ? 'ArrowRight' : 'ArrowLeft';
      if (e.key === tourNext) { e.preventDefault(); TO.tour.next(); return; }
      if (e.key === tourPrev) { e.preventDefault(); TO.tour.prev(); return; }
      return;
    }
    if (TO.slides.active) { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === ' ') TO.slides.key(e); return; }
    var code = e.code || '';
    if (goPending && Date.now() - goPending < 1300) {
      goPending = 0;
      var letter = code.replace('Key', '').toLowerCase();
      var page = visiblePages().filter(function (p) { return p.key === letter; })[0];
      if (page) { e.preventDefault(); TO.go(page.id); }
      return;
    }
    if (e.key === '?' || (e.shiftKey && code === 'Slash')) { e.preventDefault(); showKeys(); }
    else if (code === 'KeyG') { goPending = Date.now(); }
    else if (code === 'KeyT') { TO.prefs.toggleTheme(); }
    else if (code === 'KeyL') { TO.prefs.toggleLang(); }
    else if (code === 'KeyN') { if (TO.can('trips.create')) { e.preventDefault(); TO.newTrip(); } }
    else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && TO.boardShift) { var rtl = document.documentElement.dir === 'rtl'; if (TO.boardShift((e.key === 'ArrowRight') === rtl ? -1 : 1)) e.preventDefault(); }
    else if (e.key === '[') { toggleCollapse(); }
    else if (e.key === '/') { e.preventDefault(); openPalette(); }
  });

  /* ---------- guided tour (spotlight) ----------
     The hole and the card are placed with physical viewport coordinates from getBoundingClientRect.
     Those coordinates do not flip in Arabic: inset-inline-start would put the hole on the wrong side.
     The welcome steps are unchanged. The fleet tour walks Vehicles and Drivers and may open a lesson
     preview that saves nothing. */
  var WELCOME = [
    { sel: '[data-tour="nav"]', k: '1' }, { sel: '[data-tour="search"]', k: '2' }, { sel: '[data-tour="tools"]', k: '3' },
    { sel: '[data-tour="kpis"]', k: '4', page: 'overview' }, { sel: '[data-act="account"]', k: '5' }
  ];
  var FLEET = [
    { sel: '[data-import]', page: 'vehicles', k: 'flt.v.btn' },
    { sel: '[data-template]', page: 'vehicles', k: 'flt.v.tpl' },
    { sel: '[data-tour="flt-cols"]', page: 'vehicles', k: 'flt.v.cols', lesson: 'pick' },
    { sel: '[data-tour="flt-mistakes"]', page: 'vehicles', k: 'flt.v.bad', lesson: 'pick' },
    { sel: '#flt-dz', page: 'vehicles', k: 'flt.v.file', lesson: 'pick' },
    { sel: '[data-tour="flt-new"]', page: 'vehicles', k: 'flt.v.new', lesson: 'preview' },
    { sel: '[data-tour="flt-update"]', page: 'vehicles', k: 'flt.v.upd', lesson: 'preview' },
    { sel: '[data-tour="flt-errors"]', page: 'vehicles', k: 'flt.v.err', lesson: 'preview' },
    { sel: '[data-tour="flt-errors"]', page: 'vehicles', k: 'flt.v.fix', lesson: 'preview' },
    { sel: '[data-commit]', page: 'vehicles', k: 'flt.v.ok', lesson: 'preview' },
    { sel: '[data-tour="flt-done"]', page: 'vehicles', k: 'flt.v.done', lesson: 'done' },
    { sel: '[data-import]', page: 'drivers', k: 'flt.d.btn' },
    { sel: '[data-template]', page: 'drivers', k: 'flt.d.tpl' },
    { sel: '[data-tour="flt-cols"]', page: 'drivers', k: 'flt.d.cols', lesson: 'pick' },
    { sel: '[data-tour="flt-mistakes"]', page: 'drivers', k: 'flt.d.bad', lesson: 'pick' },
    { sel: '#flt-dz', page: 'drivers', k: 'flt.d.file', lesson: 'pick' },
    { sel: '[data-tour="flt-new"]', page: 'drivers', k: 'flt.d.new', lesson: 'preview' },
    { sel: '[data-tour="flt-update"]', page: 'drivers', k: 'flt.d.upd', lesson: 'preview' },
    { sel: '[data-tour="flt-errors"]', page: 'drivers', k: 'flt.d.err', lesson: 'preview' },
    { sel: '[data-tour="flt-errors"]', page: 'drivers', k: 'flt.d.fix', lesson: 'preview' },
    { sel: '[data-commit]', page: 'drivers', k: 'flt.d.ok', lesson: 'preview' },
    { sel: '[data-tour="flt-done"]', page: 'drivers', k: 'flt.d.done', lesson: 'done' }
  ];
  var PRACTICE = [
    { kind: 'vehicles', sel: '[data-tour="flt-new"]', page: 'vehicles', k: 'flt.p.v.new' },
    { kind: 'vehicles', sel: '[data-tour="flt-update"]', page: 'vehicles', k: 'flt.p.v.upd' },
    { kind: 'vehicles', sel: '[data-tour="flt-errors"]', page: 'vehicles', k: 'flt.p.v.err' },
    { kind: 'vehicles', sel: '[data-tour="flt-errors"]', page: 'vehicles', k: 'flt.p.v.fix' },
    { kind: 'vehicles', sel: '[data-commit]', page: 'vehicles', k: 'flt.p.v.ok' },
    { kind: 'drivers', sel: '[data-tour="flt-new"]', page: 'drivers', k: 'flt.p.d.new' },
    { kind: 'drivers', sel: '[data-tour="flt-update"]', page: 'drivers', k: 'flt.p.d.upd' },
    { kind: 'drivers', sel: '[data-tour="flt-errors"]', page: 'drivers', k: 'flt.p.d.err' },
    { kind: 'drivers', sel: '[data-tour="flt-errors"]', page: 'drivers', k: 'flt.p.d.fix' },
    { kind: 'drivers', sel: '[data-commit]', page: 'drivers', k: 'flt.p.d.ok' }
  ];
  function placePop(rect, pop, view) {
    var gap = 16, margin = 12;
    var vw = Math.max(0, view.w || 0), vh = Math.max(0, view.h || 0);
    var pw = Math.min(Math.max(0, pop.w || 0), Math.max(0, vw - margin * 2));
    var ph = Math.max(0, pop.h || 0);
    var rw = rect.width || 0, rh = rect.height || 0;
    var right = rect.right != null ? rect.right : (rect.left || 0) + rw;
    var bottom = rect.bottom != null ? rect.bottom : (rect.top || 0) + rh;
    var left0 = rect.left || 0, top0 = rect.top || 0;
    function clamp(n, lo, hi) { return Math.min(Math.max(n, lo), Math.max(lo, hi)); }
    var maxLeft = Math.max(margin, vw - pw - margin);
    var maxTop = Math.max(margin, vh - ph - margin);
    var tall = rh > vh * 0.55;
    var top, left, where;
    if (!tall && bottom + gap + ph <= vh - margin) {
      where = 'below'; top = bottom + gap; left = clamp(left0 + rw / 2 - pw / 2, margin, maxLeft);
    } else if (!tall && top0 - gap - ph >= margin) {
      where = 'above'; top = top0 - gap - ph; left = clamp(left0 + rw / 2 - pw / 2, margin, maxLeft);
    } else if (left0 - gap - pw >= margin) {
      where = 'west'; left = left0 - gap - pw; top = clamp(top0, margin, maxTop);
    } else if (right + gap + pw <= vw - margin) {
      where = 'east'; left = right + gap; top = clamp(top0, margin, maxTop);
    } else {
      where = 'over'; left = clamp(margin, margin, maxLeft); top = clamp(vh - ph - margin, margin, maxTop);
    }
    return { top: Math.round(top), left: Math.round(left), where: where, pw: Math.round(pw), ph: Math.round(ph) };
  }
  function pointArrow(arrow, where, box, rect) {
    if (!arrow) return;
    arrow.hidden = !where || where === 'over';
    arrow.style.cssText = '';
    if (arrow.hidden) return;
    var along = Math.min(Math.max(18, (rect.left + rect.width / 2) - box.left), Math.max(18, box.pw - 18));
    var down = Math.min(Math.max(18, (rect.top + rect.height / 2) - box.top), Math.max(18, box.ph - 18));
    arrow.style.position = 'absolute';
    arrow.style.width = '0';
    arrow.style.height = '0';
    arrow.style.border = '.45rem solid transparent';
    if (where === 'below') { arrow.style.left = (along - 7) + 'px'; arrow.style.top = '-.8rem'; arrow.style.borderBottomColor = 'var(--raised)'; }
    else if (where === 'above') { arrow.style.left = (along - 7) + 'px'; arrow.style.bottom = '-.8rem'; arrow.style.borderTopColor = 'var(--raised)'; }
    else if (where === 'west') { arrow.style.right = '-.8rem'; arrow.style.top = (down - 7) + 'px'; arrow.style.borderLeftColor = 'var(--raised)'; }
    else { arrow.style.left = '-.8rem'; arrow.style.top = (down - 7) + 'px'; arrow.style.borderRightColor = 'var(--raised)'; }
  }
  var session = null;
  function onTourGeom() { if (session) placeNow(); }
  function rectOf(el) {
    var box = el && el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    if (!box || (!box.width && !box.height)) return null;
    return { top: box.top, left: box.left, width: box.width, height: box.height, right: box.right, bottom: box.bottom };
  }
  function armLesson(step) {
    if (!TO.fleetLesson) return;
    var changed = false;
    if (step.lesson) { TO.fleetLesson.show(step.page, step.lesson); changed = true; }
    else if (TO.fleetLesson.reset) changed = TO.fleetLesson.reset();
    var path = TO.route ? TO.route().path : '';
    if (step.page && path !== step.page) TO.go(step.page);
    else if (changed && TO.rerender) TO.rerender();
  }
  function waitTarget(sel, tries, done) {
    var n = 0;
    (function look() {
      if (!session) return;
      var el = sel ? TO.$(sel) : null;
      if (rectOf(el)) { done(el); return; }
      if (++n > tries) { done(null); return; }
      setTimeout(look, 50);
    })();
  }
  function buildCard(el) {
    var host = TO.$('#tour'); if (!host || !session) return;
    var s = session.steps[session.i], n = session.steps.length, i = session.i;
    session.built = i;
    session.miss = !el;
    host.innerHTML = '<div class="hole"' + (el ? '' : ' hidden') + '></div><div class="pop" role="dialog" aria-labelledby="tour-title" style="visibility:hidden">' +
      '<i class="arrow" aria-hidden="true"></i><h3 id="tour-title">' + TO.esc(TO.t('tour.' + s.k + '.t')) + '</h3>' +
      '<p class="muted">' + TO.esc(TO.t('tour.' + s.k + '.b')) + '</p>' +
      (el ? '' : '<p class="faint">' + TO.esc(TO.t('tour.miss')) + '</p>') +
      (n > 8 ? '' : '<div class="dots">' + session.steps.map(function (_, k) { return '<i class="' + (k === i ? 'on' : '') + '"></i>'; }).join('') + '</div>') +
      '<p class="faint tour-count num">' + TO.t('tour.of', { n: i + 1, m: n }) + '</p>' +
      '<div class="tour-actions"><button type="button" class="btn ghost sm" data-tprev' + (i ? '' : ' disabled') + '>' + TO.esc(TO.t('common.back')) + '</button>' +
      '<button type="button" class="btn ghost sm" data-trestart>' + TO.esc(TO.t('tour.restart')) + '</button><span class="grow"></span>' +
      '<button type="button" class="btn ghost sm" data-tskip>' + TO.esc(TO.t('common.skip')) + '</button>' +
      '<button type="button" class="btn primary sm" data-tnext>' + TO.esc(i === n - 1 ? TO.t('common.done') : TO.t('common.next')) + '</button></div></div>';
    host.querySelector('[data-tskip]').onclick = function () { TO.tour.stop(); };
    host.querySelector('[data-trestart]').onclick = function () { TO.tour.restart(); };
    host.querySelector('[data-tprev]').onclick = function () { TO.tour.prev(); };
    host.querySelector('[data-tnext]').onclick = function () { TO.tour.next(); };
    var next = host.querySelector('[data-tnext]');
    if (next && next.focus) next.focus();
  }
  function placeNow() {
    if (!session) return;
    var host = TO.$('#tour'); if (!host) return;
    var s = session.steps[session.i];
    var el = s.sel ? TO.$(s.sel) : null;
    var have = !!rectOf(el);
    if (have === !!session.miss) buildCard(have ? el : null);
    var hole = host.querySelector('.hole'), pop = host.querySelector('.pop');
    if (!pop) return;
    var rect = rectOf(el) || { top: window.innerHeight / 2, left: window.innerWidth / 2, width: 0, height: 0, right: window.innerWidth / 2, bottom: window.innerHeight / 2 };
    if (hole) {
      hole.hidden = !have;
      if (have) {
        var pad = 6;
        hole.style.top = (rect.top - pad) + 'px';
        hole.style.left = (rect.left - pad) + 'px';
        hole.style.width = Math.max(0, rect.width + pad * 2) + 'px';
        hole.style.height = Math.max(0, rect.height + pad * 2) + 'px';
      }
    }
    var positioned = placePop(rect, { w: pop.offsetWidth || Math.min(352, window.innerWidth - 32), h: pop.offsetHeight || 180 }, { w: window.innerWidth, h: window.innerHeight });
    pop.style.top = positioned.top + 'px';
    pop.style.left = positioned.left + 'px';
    pop.dataset.place = positioned.where;
    pop.style.visibility = '';
    pointArrow(pop.querySelector('.arrow'), have ? positioned.where : 'over', positioned, rect);
  }
  function showStep(scroll) {
    if (!session) return;
    var s = session.steps[session.i];
    if (session.follow) armLesson(s);
    session.built = -1;
    waitTarget(s.sel, session.follow ? 40 : 8, function (el) {
      if (!session) return;
      buildCard(el);
      if (el && scroll && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: TO.motionOff && TO.motionOff() ? 'auto' : 'smooth' });
      if (window.requestAnimationFrame) requestAnimationFrame(placeNow);
      else placeNow();
    });
  }
  function stepsFor(id, opt) {
    if (id === 'fleet') {
      return { follow: true, steps: FLEET.filter(function (s) {
        if (s.page === 'drivers') return TO.can('drivers.manage');
        if (s.page === 'vehicles') return TO.can('vehicles.manage');
        return true;
      }) };
    }
    if (id === 'practice') {
      var kind = opt.kind === 'drivers' ? 'drivers' : 'vehicles';
      return { follow: false, steps: PRACTICE.filter(function (s) { return s.kind === kind; }) };
    }
    return { follow: false, steps: WELCOME.filter(function (s) { return TO.$(s.sel); }) };
  }
  TO.tour = {
    active: false,
    catalog: { welcome: WELCOME, fleet: FLEET, practice: PRACTICE },
    stepsFor: stepsFor,
    place: placePop,
    start: function (id, opt) {
      var host = TO.$('#tour');
      if (!host) return;
      if (TO.tour.active) TO.tour.stop();
      var picked = stepsFor(id, opt || {});
      if (!picked.steps.length) return;
      session = { id: id || 'welcome', steps: picked.steps, i: 0, follow: picked.follow, built: -1, miss: false };
      TO.tour.active = true;
      host.style.pointerEvents = 'auto';
      window.addEventListener('resize', onTourGeom);
      document.addEventListener('scroll', onTourGeom, true);
      showStep(true);
    },
    next: function () {
      if (!session) return;
      if (session.i >= session.steps.length - 1) { TO.tour.stop(); return; }
      session.i++;
      showStep(true);
    },
    prev: function () {
      if (!session || session.i <= 0) return;
      session.i--;
      showStep(true);
    },
    restart: function () {
      if (!session) return;
      session.i = 0;
      showStep(true);
    },
    stop: function () {
      var host = TO.$('#tour');
      var lesson = TO.fleetLesson && TO.fleetLesson.active && TO.fleetLesson.active();
      session = null;
      TO.tour.active = false;
      window.removeEventListener('resize', onTourGeom);
      document.removeEventListener('scroll', onTourGeom, true);
      if (host) { host.innerHTML = ''; host.style.pointerEvents = 'none'; }
      if (lesson && TO.fleetLesson.clear()) { if (TO.rerender) TO.rerender(); }
    }
  };

  /* ---------- welcome slides ---------- */
  var SLIDE_ICONS = ['route', 'chat', 'camera', 'shield', 'sheet', 'lock'];
  TO.slides = {
    active: false, i: 0,
    open: function (first) {
      var host = TO.$('#slides'), n = SLIDE_ICONS.length;
      TO.slides.active = true; TO.slides.i = 0;
      host.className = 'on';
      host.innerHTML = '<button class="btn x" data-sclose aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x', 'sm') + '</button><p class="slide-hint muted">' + TO.esc(TO.t('slide.dismiss')) + '</p><div class="track">' +
        SLIDE_ICONS.map(function (ic, k) { return '<section><div class="big">' + TO.icon(ic) + '</div><h2>' + TO.esc(TO.t('slide.' + (k + 1) + '.t')) + '</h2><p>' + TO.esc(TO.t('slide.' + (k + 1) + '.b')) + '</p></section>'; }).join('') +
        '</div><div class="nav-s"><button class="btn" data-sprev aria-label="' + TO.esc(TO.t('common.back')) + '">' + TO.icon('left', 'sm mirror') + '</button><span class="dots">' + SLIDE_ICONS.map(function () { return '<i></i>'; }).join('') + '</span>' +
        '<button class="btn primary" data-snext>' + TO.esc(TO.t('common.next')) + '</button></div>';
      var track = host.querySelector('.track'), dots = host.querySelectorAll('.dots i'), next = host.querySelector('[data-snext]');
      function go(k) {
        TO.slides.i = Math.max(0, Math.min(n - 1, k));
        track.style.transform = 'translateX(' + (-TO.slides.i * 100) + '%)';   // the track is always laid out left to right
        dots.forEach(function (d, j) { d.className = j === TO.slides.i ? 'on' : ''; });
        next.textContent = TO.slides.i === n - 1 ? TO.t('slide.start') : TO.t('common.next');
      }
      TO.slides._go = go;
      host.querySelector('[data-sprev]').onclick = function () { go(TO.slides.i - 1); };
      next.onclick = function () { if (TO.slides.i === n - 1) TO.slides.close(); else go(TO.slides.i + 1); };
      host.querySelector('[data-sclose]').onclick = TO.slides.close;
      go(0);
      if (first) { TO.prefs.data.welcomed = true; TO.prefs.save(); }
    },
    key: function (e) {
      var rtl = document.documentElement.dir === 'rtl';
      if (e.key === ' ' || e.key === (rtl ? 'ArrowLeft' : 'ArrowRight')) { e.preventDefault(); if (TO.slides.i === SLIDE_ICONS.length - 1) TO.slides.close(); else TO.slides._go(TO.slides.i + 1); }
      else { e.preventDefault(); TO.slides._go(TO.slides.i - 1); }
    },
    close: function () {
      var host = TO.$('#slides');
      TO.slides.active = false;
      if (host) { host.className = ''; host.innerHTML = ''; }
    }
  };
})();
