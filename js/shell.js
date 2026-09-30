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
    { id: 'reports', icon: 'chart', group: 'insight', perm: 'reports.view', key: 'e', phase: 6 },
    { id: 'excel', icon: 'sheet', group: 'insight', perm: ['excel.import', 'excel.export'], key: 'x', phase: 3 },
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
        '<header class="topbar">' +
          '<button class="icon-btn menu-btn" data-act="menu" aria-label="' + TO.esc(TO.t('top.menu')) + '">' + TO.icon('menu') + '</button>' +
          '<div class="crumbs" id="crumbs"></div>' +
          '<span class="grow"></span>' +
          '<button class="search-trigger" data-act="palette" data-tour="search">' + TO.icon('search', 'sm') + '<span>' + TO.esc(TO.t('top.search')) + '</span><i class="kbd">Ctrl K</i></button>' +
          '<span class="grow" style="flex:0 0 0"></span>' +
          '<span data-tour="tools" class="row" style="gap:.2rem">' +
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
      window.addEventListener('hashchange', renderRoute);
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
    if (!page || !TO.can(page.perm)) { TO.go('overview'); return; }
    TO.$$('#sidebar a[data-page]').forEach(function (a) { if (a.dataset.page === page.id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    TO.$('#crumbs').innerHTML = '<span class="mut">' + TO.esc(TO.t('app.name')) + '</span><span class="mut faint">/</span><b>' + TO.esc(TO.t('nav.' + page.id)) + '</b>';
    document.title = TO.t('nav.' + page.id) + ' · ' + TO.t('app.name');
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
      { icon: 'play', label: TO.t('act.tour'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.tour.start(); } },
      { icon: 'present', label: TO.t('act.slides'), group: TO.t('pal.g.actions'), hint: '', run: function () { TO.slides.open(); } },
      { icon: 'info', label: TO.t('act.about'), group: TO.t('pal.g.actions'), hint: '', run: function () { openAbout(); } },
      { icon: 'logout', label: TO.t('act.logout'), group: TO.t('pal.g.actions'), hint: '', run: function () { logout(); } }
    );
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
      footer: '<button class="btn" data-logout>' + TO.icon('logout', 'sm') + TO.esc(TO.t('auth.logout')) + '</button>',
      mount: function (el) { el.querySelector('[data-logout]').addEventListener('click', logout); } });
  }

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
      var app = TO.$('#app-shell'); if (app && app.dataset.menu === '1') app.dataset.menu = 0;
      return;
    }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || TO.overlay.isOpen) return;
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

  /* ---------- guided tour (spotlight) ---------- */
  var TOUR = [
    { sel: '[data-tour="nav"]', k: 1 }, { sel: '[data-tour="search"]', k: 2 }, { sel: '[data-tour="tools"]', k: 3 },
    { sel: '[data-tour="kpis"]', k: 4, page: 'overview' }, { sel: '[data-act="account"]', k: 5 }
  ];
  TO.tour = {
    active: false,
    start: function () {
      var steps = TOUR.filter(function (s) { return TO.$(s.sel); });
      if (!steps.length) return;
      var i = 0, host = TO.$('#tour');
      TO.tour.active = true;
      host.style.pointerEvents = 'auto';
      function show() {
        var s = steps[i], el = TO.$(s.sel);
        el.scrollIntoView({ block: 'center' });
        var r = el.getBoundingClientRect(), pad = 6;
        var pw = Math.min(352, window.innerWidth - 32), ph = 210, gap = 16, vw = window.innerWidth, vh = window.innerHeight;
        var top, left, tall = r.height > vh * 0.5;
        var clampX = function (x) { return Math.min(Math.max(12, x), vw - pw - 12); };
        var clampY = function (y) { return Math.min(Math.max(12, y), vh - ph - 12); };
        if (!tall && r.bottom + gap + ph <= vh) { top = r.bottom + gap; left = clampX(r.left + r.width / 2 - pw / 2); }
        else if (!tall && r.top - gap - ph >= 0) { top = r.top - gap - ph; left = clampX(r.left + r.width / 2 - pw / 2); }
        else if (r.left - gap - pw >= 12) { left = r.left - gap - pw; top = clampY(r.top + 24); }
        else if (r.right + gap + pw <= vw - 12) { left = r.right + gap; top = clampY(r.top + 24); }
        else { left = clampX(12); top = clampY(vh - ph - 12); }
        host.innerHTML = '<div class="hole" style="top:' + (r.top - pad) + 'px;left:' + (r.left - pad) + 'px;width:' + (r.width + pad * 2) + 'px;height:' + (r.height + pad * 2) + 'px"></div>' +
          '<div class="pop" role="dialog" style="top:' + top + 'px;left:' + left + 'px"><h3>' + TO.esc(TO.t('tour.' + s.k + '.t')) + '</h3><p class="muted">' + TO.esc(TO.t('tour.' + s.k + '.b')) + '</p>' +
          '<div class="row"><span class="dots">' + steps.map(function (_, n) { return '<i class="' + (n === i ? 'on' : '') + '"></i>'; }).join('') + '</span><span class="faint num">' + TO.t('tour.of', { n: i + 1, m: steps.length }) + '</span>' +
          '<span class="grow"></span><button class="btn ghost sm" data-tskip>' + TO.esc(TO.t('common.skip')) + '</button><button class="btn primary sm" data-tnext>' + TO.esc(i === steps.length - 1 ? TO.t('common.done') : TO.t('common.next')) + '</button></div></div>';
        host.querySelector('[data-tskip]').onclick = TO.tour.stop;
        host.querySelector('[data-tnext]').onclick = function () { if (i === steps.length - 1) TO.tour.stop(); else { i++; show(); } };
      }
      show();
    },
    stop: function () {
      var host = TO.$('#tour');
      TO.tour.active = false;
      if (host) { host.innerHTML = ''; host.style.pointerEvents = 'none'; }
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
      host.innerHTML = '<button class="btn x" data-sclose aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x', 'sm') + '</button><div class="track">' +
        SLIDE_ICONS.map(function (ic, k) { return '<section><div class="big">' + TO.icon(ic) + '</div><h2>' + TO.esc(TO.t('slide.' + (k + 1) + '.t')) + '</h2><p>' + TO.esc(TO.t('slide.' + (k + 1) + '.b')) + '</p></section>'; }).join('') +
        '</div><div class="nav-s"><button class="btn" data-sprev aria-label="' + TO.esc(TO.t('common.back')) + '">' + TO.icon('left', 'sm mirror') + '</button><span class="dots">' + SLIDE_ICONS.map(function () { return '<i></i>'; }).join('') + '</span>' +
        '<button class="btn primary" data-snext>' + TO.esc(TO.t('common.next')) + '</button></div>';
      var track = host.querySelector('.track'), dots = host.querySelectorAll('.dots i'), next = host.querySelector('[data-snext]');
      function go(k) {
        TO.slides.i = Math.max(0, Math.min(n - 1, k));
        var dir = document.documentElement.dir === 'rtl' ? 1 : -1;
        track.style.transform = 'translateX(' + (dir * TO.slides.i * 100) + '%)';
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
