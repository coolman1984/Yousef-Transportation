/* Trip Orders - Excel & Word: import with a review step, export (same as today / clean report), Word form and report, guide. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var TABS = ['import', 'export', 'word', 'guide'];
  var GK = 'imp.g', G = 12;                       // questions in the guide
  var S = null;                     // state of the page

  function fresh() { return { tab: 'import', pv: null, busy: false, err: null, done: null, filter: 'all', skip: {}, merge: {}, problems: false, category: '', shown: 150, ym: U.today().slice(0, 7), layout: 'today' }; }

  /* ---------- texts for messages the server sends in English with a code ---------- */
  function nums(s) { return (String(s || '').match(/\d+/g) || []); }
  function msgText(m) {
    var key = 'imp.m.' + m.code;
    if (!TO.has(key)) return TO.esc(m.text);
    var n = nums(m.text), q = String(m.text || '').match(/"([^"]*)"/g) || [];
    return TO.t(key, { a: n[0] || '', b: n[1] || '', x: (q[0] || '').replace(/"/g, ''), y: (q[1] || '').replace(/"/g, '') });
  }
  function alertText(a) { var k = 'imp.al.' + a.code; return TO.has(k) ? TO.t(k, { n: a.n }) : TO.esc(a.text); }
  function errText(e) {
    var m = (e && e.message) || '';
    var map = [['not a Word', 'imp.e.notdocx'], ['not an Excel', 'imp.e.notxlsx'], ['empty', 'imp.e.empty'], ['damaged', 'imp.e.damaged'], ['too large', 'imp.e.big'],
      ['No sheet with trip columns', 'imp.e.nocols'], ['no trips in them', 'imp.e.notrips'], ['expired', 'imp.e.expired'], ['nothing to import', 'imp.e.nothing'],
      ['No trip order form', 'imp.e.noform'], ['Choose the trip category', 'imp.e.cat'], ['password', 'imp.e.locked']];
    for (var i = 0; i < map.length; i++) if (m.indexOf(map[i][0]) >= 0) return TO.t(map[i][1]);
    return m ? TO.esc(m) : TO.esc(TO.t('common.error'));
  }

  /* ---------- download through fetch so a refusal shows a message instead of a broken page ---------- */
  function download(url, fallbackName, btn) {
    if (btn) btn.disabled = true;
    fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) return r.json().then(function (j) { throw new Error((j && j.error) || ('HTTP ' + r.status)); }, function () { throw new Error('HTTP ' + r.status); });
      var cd = r.headers.get('Content-Disposition') || '', m = /filename="([^"]+)"/.exec(cd);
      return r.blob().then(function (b) { return { b: b, name: m ? m[1] : fallbackName }; });
    }).then(function (f) {
      var a = document.createElement('a'); a.href = URL.createObjectURL(f.b); a.download = f.name; document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      TO.toast(TO.t('imp.downloaded'));
    }).catch(function (e) { TO.toast(errText(e), 'bad', 6000); }).then(function () { if (btn) btn.disabled = false; });
  }

  /* ---------- import ---------- */
  function dropzone() {
    var cats = TO.data.list('tripCategories').map(function (c) { return '<option value="' + TO.esc(c.name) + '"></option>'; }).join('');
    return '<section class="card"><header><h3>' + TO.icon('upload') + ' ' + TO.esc(TO.t('imp.pick')) + '</h3></header>' +
      '<p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('imp.pick.sub')) + '</p>' +
      '<label class="dropzone" id="dz" for="imp-file" tabindex="0"><span class="art">' + TO.icon('sheet', 'lg') + '</span><b>' + TO.esc(TO.t('imp.drop')) + '</b><span class="muted">' + TO.esc(TO.t('imp.drop.types')) + '</span></label>' +
      '<input type="file" id="imp-file" accept=".xlsx,.docx" hidden>' +
      '<div class="field" id="cat-field" hidden style="margin-top:1rem"><label for="imp-cat">' + TO.esc(TO.t('imp.cat')) + '</label><input class="input" id="imp-cat" list="dl-cat" autocomplete="off" value="' + TO.esc(S.category) + '"><datalist id="dl-cat">' + cats + '</datalist><span class="help">' + TO.esc(TO.t('imp.cat.help')) + '</span></div>' +
      (S.busy ? '<div class="skeleton" style="height:3rem;margin-top:1rem"></div>' : '') +
      (S.err ? '<div class="tip bad" role="alert" style="margin-top:1rem">' + TO.icon('alert') + '<span>' + S.err + '</span></div>' : '') + '</section>';
  }

  function kpi(icon, label, value, hint, tone) {
    return '<div class="card kpi' + (tone ? ' ' + tone : '') + '"><span class="label">' + TO.esc(label) + '<span class="tile-ic">' + TO.icon(icon) + '</span></span><span class="value num">' + TO.fmt.num(value) + '</span>' + (hint ? '<span class="hint">' + TO.esc(hint) + '</span>' : '') + '</div>';
  }

  function statusBadge(r) {
    var tone = r.status === 'new' ? 'ok' : r.status === 'duplicate' ? '' : 'bad';
    return '<span class="badge ' + tone + '">' + TO.esc(TO.t('imp.st.' + r.status)) + '</span>';
  }
  function rowId(r) { return r.sheet + '#' + r.row; }
  function visibleRows() {
    return S.pv.rows.filter(function (r) {
      if (S.filter === 'all') return true;
      if (S.filter === 'warn') return r.status !== 'duplicate' && r.messages.some(function (m) { return m.code !== 'dup_db' && m.code !== 'dup_file'; });
      return r.status === S.filter;
    });
  }

  function review() {
    var p = S.pv, st = p.stats, N = p.new || {};
    var made = ['drivers', 'vehicles', 'people', 'departments', 'categories', 'places'].filter(function (k) { return (N[k] || []).length; }).map(function (k) {
      return '<span class="badge info">' + TO.esc(TO.t('imp.new.' + k, { n: N[k].length })) + '</span>'; }).join(' ');
    var alerts = (p.alerts || []).map(function (a) {
      return '<div class="tip ' + (a.level === 'bad' ? 'bad' : a.level === 'warn' ? 'warn' : '') + '">' + TO.icon(a.level === 'info' ? 'info' : 'alert') + '<span>' + alertText(a) + '</span></div>'; }).join('');
    var sheets = (p.sheets || []).map(function (s) {
      return '<span class="badge ' + (s.used ? 'ok' : '') + '">' + TO.esc(s.sheet) + ' · ' + (s.used ? TO.fmt.num(s.rows) : TO.esc(TO.t('imp.sheet.skipped'))) + '</span>'; }).join(' ');
    var merges = (p.merges || []).map(function (m, i) {
      return '<label class="row merge"><span class="switch"><input type="checkbox" data-merge="' + i + '"' + (S.merge[i] !== false ? ' checked' : '') + '><span></span></span><span>' +
        TO.t('imp.merge.line', { main: m.canonical, others: m.variants.join('، ') }) + '</span></label>'; }).join('');
    var rows = visibleRows(), shown = rows.slice(0, S.shown);
    var filt = ['all', 'new', 'warn', 'problem', 'duplicate'].map(function (f) {
      return '<button data-f="' + f + '" aria-pressed="' + (S.filter === f) + '">' + TO.esc(TO.t('imp.f.' + f)) + '</button>'; }).join('');
    var importable = st.new + (S.problems ? st.problem : 0) - countSkipped();
    return '<div class="stack">' +
      '<div class="grid cols-4">' + kpi('route', TO.t('imp.k.rows'), st.total, p.filename, '') + kpi('check', TO.t('imp.k.new'), st.new, '', 'live') + kpi('doc', TO.t('imp.k.dup'), st.duplicate, TO.t('imp.k.dup.h'), '') +
      kpi('alert', TO.t('imp.k.problem'), st.problem, TO.t('imp.k.problem.h'), '') + '</div>' +
      '<div class="grid cols-2">' + kpi('wheel', TO.t('imp.k.km'), st.km, '', '') + kpi('clock', TO.t('imp.k.ot'), st.ot, TO.t('imp.k.ot.h'), '') + '</div>' +
      (alerts ? '<section class="card"><header><h3>' + TO.icon('shield') + ' ' + TO.esc(TO.t('imp.alerts')) + '</h3></header><div class="stack" style="gap:.6rem">' + alerts + '</div></section>' : '<div class="tip">' + TO.icon('check') + '<span>' + TO.esc(TO.t('imp.alerts.none')) + '</span></div>') +
      '<section class="card"><header><h3>' + TO.esc(TO.t('imp.will')) + '</h3></header><div class="chip-row">' + sheets + '</div>' +
      (made ? '<p class="muted" style="margin:.8rem 0 .4rem">' + TO.esc(TO.t('imp.new.h')) + '</p><div class="chip-row">' + made + '</div>' : '') + '</section>' +
      (merges ? '<section class="card"><header><h3>' + TO.icon('pin') + ' ' + TO.esc(TO.t('imp.merges')) + '</h3></header><p class="muted" style="margin:-.4rem 0 1rem">' + TO.esc(TO.t('imp.merges.sub')) + '</p><div class="stack" style="gap:.7rem">' + merges + '</div></section>' : '') +
      '<section class="card"><header><h3>' + TO.esc(TO.t('imp.rows')) + '</h3><div class="seg" role="group">' + filt + '</div></header>' +
      (st.problem ? '<label class="row" style="margin-bottom:.8rem"><span class="switch"><input type="checkbox" id="imp-problems"' + (S.problems ? ' checked' : '') + '><span></span></span><span>' + TO.esc(TO.t('imp.problems.opt')) + '</span></label>' : '') +
      (rows.length ? U.table([
        { h: 'imp.c.use', cell: function (r) { return r.status === 'duplicate' ? '' : '<input type="checkbox" data-use="' + TO.esc(rowId(r)) + '" aria-label="' + TO.esc(TO.t('imp.c.use')) + '"' + (S.skip[rowId(r)] ? '' : ' checked') + (r.status === 'problem' && !S.problems ? ' disabled' : '') + '>'; } },
        { h: 'imp.c.row', cell: function (r) { return '<span class="num faint">' + TO.esc(r.sheet) + ' · ' + r.row + '</span>'; } },
        { h: 'f.date', cell: function (r) { return r.date ? '<span class="num">' + U.day(r.date) + '</span>' : '<span class="faint">–</span>'; } },
        { h: 'f.driver', cell: function (r) { return TO.esc(r.driver || '–'); } },
        { h: 'f.plate', cell: function (r) { return U.plate(r.plateNorm || r.plate); } },
        { h: 'f.destination', cell: function (r) { return '<span>' + TO.esc(r.destination || '') + '</span>'; } },
        { h: 'f.km', cell: function (r) { return r.startKm != null && r.endKm != null ? '<span class="num">' + TO.fmt.num(r.endKm - r.startKm) + '</span>' : '<span class="faint">–</span>'; } },
        { h: 'f.status', cell: statusBadge },
        { h: 'imp.c.notes', cell: function (r) { return r.messages.length ? '<ul class="notes">' + r.messages.map(function (m) { return '<li>' + msgText(m) + '</li>'; }).join('') + '</ul>' : ''; } }
      ], shown) + (rows.length > shown.length ? '<div style="margin-top:1rem"><button class="btn" data-more>' + TO.esc(TO.t('imp.more', { n: rows.length - shown.length })) + '</button></div>' : '') : U.empty('search', TO.t('imp.f.none'))) + '</section>' +
      '<div class="actionbar"><button class="btn ghost" data-cancel>' + TO.esc(TO.t('common.cancel')) + '</button>' +
      '<button class="btn primary" data-commit' + (importable > 0 && TO.can('excel.import') ? '' : ' disabled') + '>' + TO.icon('check', 'sm') + TO.esc(TO.t('imp.commit', { n: Math.max(0, importable) })) + '</button></div></div>';
  }
  function countSkipped() {
    return S.pv.rows.filter(function (r) { return S.skip[rowId(r)] && (r.status === 'new' || (S.problems && r.status === 'problem')); }).length;
  }

  function doneView() {
    return '<section class="card"><div class="empty"><div class="art ok">' + TO.icon('check', 'lg') + '</div><h3>' + TO.esc(TO.t('imp.done.t', { n: S.done.trips })) + '</h3><p>' + TO.esc(TO.t('imp.done.b')) + '</p>' +
      '<div class="row" style="justify-content:center;gap:.6rem"><a class="btn primary" href="#/trips">' + TO.esc(TO.t('imp.done.trips')) + '</a><button class="btn" data-again>' + TO.esc(TO.t('imp.done.again')) + '</button></div></div></section>';
  }

  function importTab() {
    if (S.done) return doneView();
    if (S.pv) return review();
    return '<div class="grid split">' + dropzone() + '<section class="card"><header><h3>' + TO.icon('info') + ' ' + TO.esc(TO.t('imp.how')) + '</h3></header><ol class="steps">' +
      [1, 2, 3, 4].map(function (i) { return '<li>' + TO.esc(TO.t('imp.how.' + i)) + '</li>'; }).join('') + '</ol></section></div>';
  }

  /* ---------- export ---------- */
  function monthSummary() {
    var trips = TO.data.list('trips').filter(function (t) { return String(t.date || '').slice(0, 7) === S.ym && t.status !== 'cancelled'; });
    var km = 0, c = { green: 0, yellow: 0, red: 0, grey: 0 };
    trips.forEach(function (t) { var i = TO.data.trust(t.id); c[i.trust] = (c[i.trust] || 0) + 1; if (i.km > 0) km += i.km; });
    return { n: trips.length, km: km, c: c };
  }
  function exportTab() {
    var m = monthSummary();
    var can = TO.can('excel.export');
    return '<div class="grid split"><section class="card"><header><h3>' + TO.icon('download') + ' ' + TO.esc(TO.t('exp2.title')) + '</h3></header>' +
      '<div class="field"><label for="ex-ym">' + TO.esc(TO.t('exp2.month')) + '</label><input class="input" id="ex-ym" type="month" value="' + TO.esc(S.ym) + '" style="max-width:14rem"></div>' +
      '<div class="grid cols-2" style="margin:1rem 0">' +
      '<label class="choice"><input type="radio" name="layout" value="today"' + (S.layout === 'today' ? ' checked' : '') + '><span><b>' + TO.esc(TO.t('exp2.today')) + '</b><small>' + TO.esc(TO.t('exp2.today.d')) + '</small></span></label>' +
      '<label class="choice"><input type="radio" name="layout" value="clean"' + (S.layout === 'clean' ? ' checked' : '') + '><span><b>' + TO.esc(TO.t('exp2.clean')) + '</b><small>' + TO.esc(TO.t('exp2.clean.d')) + '</small></span></label></div>' +
      '<div class="row" style="gap:.6rem;flex-wrap:wrap"><button class="btn primary" data-dl="excel"' + (can ? '' : ' disabled') + '>' + TO.icon('download', 'sm') + TO.esc(TO.t('exp2.btn')) + '</button>' +
      '<button class="btn" data-dl="template"' + (can ? '' : ' disabled') + '>' + TO.icon('sheet', 'sm') + TO.esc(TO.t('exp2.template')) + '</button></div>' +
      '<div class="tip" style="margin-top:1.2rem">' + TO.icon('info') + '<span>' + TO.esc(TO.t('exp2.note')) + '</span></div></section>' +
      '<section class="card"><header><h3>' + TO.esc(TO.t('exp2.glance')) + '</h3></header>' + (m.n ? '<div class="stack" style="gap:.7rem">' +
        '<div class="row between"><span>' + TO.esc(TO.t('imp.k.rows')) + '</span><b class="num">' + TO.fmt.num(m.n) + '</b></div>' +
        '<div class="row between"><span>' + TO.esc(TO.t('imp.k.km')) + '</span><b class="num">' + TO.fmt.num(m.km) + '</b></div>' +
        ['green', 'yellow', 'red'].map(function (k) { return '<div class="row between"><span class="row" style="gap:.5rem"><span class="trust ' + k + '"></span>' + TO.esc(TO.t('trust.' + k)) + '</span><b class="num">' + TO.fmt.num(m.c[k]) + '</b></div>'; }).join('') +
        '</div>' : U.empty('route', TO.t('exp2.none'))) + '</section></div>';
  }

  /* ---------- word ---------- */
  function wordTab() {
    var can = TO.can('excel.export');
    return '<div class="grid cols-2"><section class="card"><header><h3>' + TO.icon('doc') + ' ' + TO.esc(TO.t('wd.form')) + '</h3></header><p class="muted">' + TO.esc(TO.t('wd.form.d')) + '</p>' +
      '<div class="row" style="gap:.6rem;flex-wrap:wrap;margin-top:1rem"><button class="btn primary" data-dl="form-ar">' + TO.icon('download', 'sm') + TO.esc(TO.t('wd.form.ar')) + '</button>' +
      '<button class="btn" data-dl="form-en">' + TO.icon('download', 'sm') + TO.esc(TO.t('wd.form.en')) + '</button></div></section>' +
      '<section class="card"><header><h3>' + TO.icon('chart') + ' ' + TO.esc(TO.t('wd.report')) + '</h3></header><p class="muted">' + TO.esc(TO.t('wd.report.d')) + '</p>' +
      '<div class="field"><label for="wd-ym">' + TO.esc(TO.t('exp2.month')) + '</label><input class="input" id="wd-ym" type="month" value="' + TO.esc(S.ym) + '" style="max-width:14rem"></div>' +
      '<div class="row" style="gap:.6rem;flex-wrap:wrap;margin-top:1rem"><button class="btn primary" data-dl="report-ar"' + (can ? '' : ' disabled') + '>' + TO.icon('download', 'sm') + TO.esc(TO.t('wd.report.ar')) + '</button>' +
      '<button class="btn" data-dl="report-en"' + (can ? '' : ' disabled') + '>' + TO.icon('download', 'sm') + TO.esc(TO.t('wd.report.en')) + '</button></div></section>' +
      '<section class="card" style="grid-column:1/-1"><header><h3>' + TO.icon('upload') + ' ' + TO.esc(TO.t('wd.import')) + '</h3></header><p class="muted">' + TO.esc(TO.t('wd.import.d')) + '</p>' +
      '<div style="margin-top:1rem"><button class="btn" data-goimport>' + TO.icon('upload', 'sm') + TO.esc(TO.t('wd.import.go')) + '</button></div></section></div>';
  }

  /* ---------- guide ---------- */
  function guideTab() {
    var items = [];
    for (var i = 1; i <= G; i++) items.push('<details><summary>' + TO.esc(TO.t(GK + i + '.q')) + '</summary><p>' + TO.esc(TO.t(GK + i + '.a')) + '</p></details>');
    var errs = ['notxlsx', 'notdocx', 'nocols', 'expired', 'nothing', 'big'].map(function (k) {
      return '<div class="errline"><b>' + TO.esc(TO.t('imp.e.' + k)) + '</b><span class="muted">' + TO.esc(TO.t('imp.e.' + k + '.fix')) + '</span></div>'; }).join('');
    return '<div class="stack"><section class="card"><header><h3>' + TO.icon('help') + ' ' + TO.esc(TO.t('imp.guide')) + '</h3></header><div class="faq">' + items.join('') + '</div></section>' +
      '<section class="card"><header><h3>' + TO.icon('alert') + ' ' + TO.esc(TO.t('imp.errors')) + '</h3></header><div class="stack" style="gap:.8rem">' + errs + '</div></section></div>';
  }

  /* ---------- page ---------- */
  function body() {
    return { import: importTab, export: exportTab, word: wordTab, guide: guideTab }[S.tab]();
  }
  function paint(root) {
    root.querySelector('#xl-body').innerHTML = body();
    TO.$$('.seg [data-tab]', root).forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.tab === S.tab); });
    wire(root);
  }

  function upload(file, root) {
    var isDoc = /\.docx$/i.test(file.name), isXl = /\.xlsx$/i.test(file.name);
    if (!isDoc && !isXl) { S.err = TO.t(/\.(doc|xls)$/i.test(file.name) ? 'imp.e.old' : 'imp.e.notxlsx'); paint(root); return; }
    if (isDoc) {
      S.category = (root.querySelector('#imp-cat') || {}).value || S.category;
      if (!S.category.trim()) { S.err = TO.t('imp.e.cat'); paint(root); var cf = root.querySelector('#cat-field'); if (cf) { cf.hidden = false; cf.querySelector('input').focus(); } S.pendingFile = file; return; }
    }
    S.busy = true; S.err = null; paint(root);
    file.arrayBuffer().then(function (buf) {
      var url = isDoc ? '/api/word/preview?category=' + encodeURIComponent(S.category) + '&name=' + encodeURIComponent(file.name) : '/api/excel/preview?name=' + encodeURIComponent(file.name);
      return TO.api('POST', url, buf, { raw: true });
    }).then(function (pv) { S.pv = pv; S.busy = false; S.skip = {}; S.merge = {}; S.filter = 'all'; S.shown = 150; paint(root); window.scrollTo(0, 0); },
      function (e) { S.busy = false; S.err = errText(e); paint(root); });
  }

  function wire(root) {
    var body = root.querySelector('#xl-body');
    var inp = body.querySelector('#imp-file'), dz = body.querySelector('#dz');
    if (inp) {
      inp.addEventListener('change', function () { if (inp.files[0]) { var f = inp.files[0]; inp.value = ''; S.pendingFile = null; if (/\.docx$/i.test(f.name)) { var cf = body.querySelector('#cat-field'); cf.hidden = false; S.pendingFile = f; if (S.category) upload(f, root); else cf.querySelector('input').focus(); } else upload(f, root); } });
      ['dragover', 'dragenter'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('over'); }); });
      ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function () { dz.classList.remove('over'); }); });
      dz.addEventListener('drop', function (e) { e.preventDefault(); var f = e.dataTransfer.files[0]; if (f) { if (/\.docx$/i.test(f.name)) { body.querySelector('#cat-field').hidden = false; S.pendingFile = f; if (S.category) upload(f, root); } else upload(f, root); } });
      dz.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inp.click(); } });
      var cat = body.querySelector('#imp-cat');
      cat.addEventListener('keydown', function (e) { if (e.key === 'Enter' && S.pendingFile && cat.value.trim()) { S.category = cat.value.trim(); upload(S.pendingFile, root); } });
      cat.addEventListener('change', function () { S.category = cat.value.trim(); if (S.pendingFile && S.category) upload(S.pendingFile, root); });
      if (S.pendingFile) body.querySelector('#cat-field').hidden = false;
    }
  }

  TO.views.excel = {
    render: function () {
      if (!S) S = fresh();
      var tabs = TABS.map(function (t) { return '<button data-tab="' + t + '" aria-pressed="' + (S.tab === t) + '">' + TO.esc(TO.t('imp.tab.' + t)) + '</button>'; }).join('');
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('nav.excel')) + '</h1><p>' + TO.esc(TO.t('page.excel.d')) + '</p></div><div class="seg" role="tablist">' + tabs + '</div></div><div id="xl-body">' + body() + '</div>';
    },
    mount: function (root) {
      if (!S) S = fresh();
      wire(root);
      root.addEventListener('click', function (e) {
        var t = e.target.closest('[data-tab]');
        if (t) { S.tab = t.dataset.tab; paint(root); return; }
        var f = e.target.closest('[data-f]');
        if (f) { S.filter = f.dataset.f; S.shown = 150; paint(root); return; }
        if (e.target.closest('[data-more]')) { S.shown += 300; paint(root); return; }
        if (e.target.closest('[data-cancel]')) { if (S.pv) { S.pv = null; S.err = null; paint(root); } return; }
        if (e.target.closest('[data-again]')) { S = fresh(); paint(root); return; }
        if (e.target.closest('[data-goimport]')) { S.tab = 'import'; paint(root); return; }
        if (e.target.closest('[data-commit]')) { commit(root, e.target.closest('[data-commit]')); return; }
        var d = e.target.closest('[data-dl]');
        if (d) {
          var k = d.dataset.dl, ym = k.indexOf('report') === 0 ? (root.querySelector('#wd-ym') || {}).value : S.ym;
          if (k === 'excel') download('/api/excel/export?ym=' + S.ym + '&layout=' + S.layout + '&lang=' + TO.lang, 'Trips.xlsx', d);
          else if (k === 'template') download('/api/excel/template', 'Trips_template.xlsx', d);
          else if (k.indexOf('form') === 0) download('/api/word/form?lang=' + k.slice(-2), 'Trip_order.docx', d);
          else download('/api/word/report?ym=' + encodeURIComponent(ym || S.ym) + '&lang=' + k.slice(-2), 'Trips_report.docx', d);
        }
      });
      root.addEventListener('change', function (e) {
        var el = e.target;
        if (el.id === 'ex-ym' || el.id === 'wd-ym') { if (el.value) { S.ym = el.value; if (el.id === 'ex-ym') paint(root); } return; }
        if (el.name === 'layout') { S.layout = el.value; return; }
        if (el.id === 'imp-problems') { S.problems = el.checked; paint(root); return; }
        if (el.dataset.use) { if (el.checked) delete S.skip[el.dataset.use]; else S.skip[el.dataset.use] = 1; paint(root); return; }
        if (el.dataset.merge !== undefined) { S.merge[el.dataset.merge] = el.checked; }
      });
    }
  };

  function commit(root, btn) {
    var p = S.pv, merges = (p.merges || []).filter(function (m, i) { return S.merge[i] !== false; }).map(function (m) { return { canonical: m.canonical, variants: m.variants }; });
    btn.disabled = true;
    TO.post('/api/excel/commit', { id: p.id, skip: Object.keys(S.skip), merges: merges, includeProblems: S.problems }).then(function (r) {
      S.done = r; S.pv = null; return TO.data.load();
    }).then(function () { paint(root); window.scrollTo(0, 0); }, function (e) { btn.disabled = false; TO.toast(errText(e), 'bad', 6000); });
  }
})();
