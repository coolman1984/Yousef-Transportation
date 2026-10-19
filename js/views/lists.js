/* Trip Orders - list pages driven by a small configuration: vehicles, drivers, people (+ departments), places (+ standard routes),
   trip categories (in Settings). One table, one side-panel form, soft delete, search - the same for every list. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;

  var OWN = function () { return [{ v: 'own', l: TO.t('own.own') }, { v: 'rent', l: TO.t('own.rent') }]; };
  var SHEETS = ['All Car', 'SUV Rent', 'Microbus Rent'].map(function (x) { return { v: x, l: x }; });

  // each list: entity, title key, manage permission, columns, form fields, searchable text, new-record defaults, sort
  var LISTS = {
    vehicles: {
      entity: 'vehicles', perm: 'vehicles.manage', icon: 'car', add: 'list.add.vehicle', import: true,
      cols: [
        { h: 'f.plate', cell: function (r) { return TO.ui.plate(r.plate); } },
        { h: 'f.type', cell: function (r) { return TO.esc(r.type || ''); } },
        { h: 'f.category', cell: function (r) { return TO.esc(TO.data.catName(r.categoryId)); } },
        { h: 'f.ownership', cell: function (r) { return r.ownership ? '<span class="badge ' + (r.ownership === 'rent' ? 'info' : '') + '">' + TO.esc(TO.t('own.' + r.ownership)) + '</span>' : ''; } },
        { h: 'f.vendor', cell: function (r) { return TO.esc(r.vendor || ''); } },
        { h: 'f.trips', cell: function (r) { return U.num(TO.data.list('trips').filter(function (t) { return t.vehicleId === r.id && t.status !== 'cancelled'; }).length); } },
        { h: 'f.active', cell: function (r) { return activeBadge(r); } }
      ],
      fields: function () { return [
        { key: 'plate', label: 'f.plate', required: true, help: 'help.plate' },
        { key: 'type', label: 'f.type' },
        { key: 'categoryId', label: 'f.category', type: 'ref', entity: 'tripCategories' },
        { key: 'ownership', label: 'f.ownership', type: 'select', options: OWN() },
        { key: 'vendor', label: 'f.vendor' },
        { key: 'startKm', label: 'f.baselineKm', type: 'number', ltr: true, help: 'help.baselineKm' },
        { key: 'notes', label: 'f.notes', type: 'textarea' },
        { key: 'active', label: 'f.active', type: 'bool' }]; },
      text: function (r) { return [r.plate, r.type, r.vendor, TO.data.catName(r.categoryId)].join(' '); },
      defaults: { active: true, ownership: 'own' },
      title: function (r) { return r.plate; }
    },
    drivers: {
      entity: 'drivers', perm: 'drivers.manage', icon: 'wheel', add: 'list.add.driver', import: true,
      cols: [
        { h: 'f.name', cell: function (r) { return '<b>' + TO.esc(r.name) + '</b>'; } },
        { h: 'f.mobile', cell: function (r) { return r.mobile ? '<span class="num">' + TO.esc(r.mobile) + '</span>' : '<span class="faint">–</span>'; } },
        { h: 'f.vendor', cell: function (r) { return TO.esc(r.vendor || ''); } },
        { h: 'f.licenseExpiry', cell: function (r) { return licenseCell(r); } },
        { h: 'f.trips', cell: function (r) { return U.num(TO.data.list('trips').filter(function (t) { return t.driverId === r.id && t.status !== 'cancelled'; }).length); } },
        { h: 'f.active', cell: function (r) { return activeBadge(r); } }
      ],
      fields: function () { return [
        { key: 'name', label: 'f.name', required: true },
        { key: 'mobile', label: 'f.mobile', type: 'tel', ltr: true, help: 'help.mobile' },
        { key: 'vendor', label: 'f.vendor' },
        { key: 'licenseNo', label: 'f.licenseNo', ltr: true },
        { key: 'licenseExpiry', label: 'f.licenseExpiry', type: 'date' },
        { key: 'active', label: 'f.active', type: 'bool' }]; },
      text: function (r) { return [r.name, r.mobile, r.vendor].join(' '); },
      defaults: { active: true },
      title: function (r) { return r.name; }
    },
    people: {
      entity: 'people', perm: 'people.manage', icon: 'users', add: 'list.add.person',
      cols: [
        { h: 'f.name', cell: function (r) { return '<b>' + TO.esc(r.name) + '</b>'; } },
        { h: 'f.department', cell: function (r) { return TO.esc(TO.data.name('departments', r.departmentId)); } },
        { h: 'f.role', cell: function (r) { return (r.isRequester ? '<span class="badge info">' + TO.esc(TO.t('role.requester')) + '</span> ' : '') + (r.isPassenger ? '<span class="badge">' + TO.esc(TO.t('role.passenger')) + '</span>' : ''); } },
        { h: 'f.mobile', cell: function (r) { return r.mobile ? '<span class="num">' + TO.esc(r.mobile) + '</span>' : '<span class="faint">–</span>'; } },
        { h: 'f.trips', cell: function (r) { return U.num(TO.data.list('trips').filter(function (t) { return t.requesterId === r.id; }).length); } },
        { h: 'f.active', cell: function (r) { return activeBadge(r); } }
      ],
      fields: function () { return [
        { key: 'name', label: 'f.name', required: true },
        { key: 'departmentId', label: 'f.department', type: 'ref', entity: 'departments', allowNew: true },
        { key: 'mobile', label: 'f.mobile', type: 'tel', ltr: true },
        { key: 'isRequester', label: 'role.requester', type: 'bool' },
        { key: 'isPassenger', label: 'role.passenger', type: 'bool' },
        { key: 'active', label: 'f.active', type: 'bool' }]; },
      text: function (r) { return [r.name, r.mobile, TO.data.name('departments', r.departmentId)].join(' '); },
      defaults: { active: true, isRequester: true, isPassenger: true },
      title: function (r) { return r.name; },
      dupWarn: true
    },
    departments: {
      entity: 'departments', perm: 'people.manage', icon: 'layers', add: 'list.add.department',
      cols: [
        { h: 'f.name', cell: function (r) { return '<b>' + TO.esc(r.name) + '</b>'; } },
        { h: 'f.code', cell: function (r) { return TO.esc(r.code || ''); } },
        { h: 'f.people', cell: function (r) { return U.num(TO.data.list('people').filter(function (p) { return p.departmentId === r.id; }).length); } },
        { h: 'f.trips', cell: function (r) { return U.num(TO.data.list('trips').filter(function (t) { return t.departmentId === r.id && t.status !== 'cancelled'; }).length); } },
        { h: 'f.active', cell: function (r) { return activeBadge(r); } }
      ],
      fields: function () { return [{ key: 'name', label: 'f.name', required: true }, { key: 'code', label: 'f.code', ltr: true }, { key: 'active', label: 'f.active', type: 'bool' }]; },
      text: function (r) { return [r.name, r.code].join(' '); },
      defaults: { active: true },
      title: function (r) { return r.name; }
    },
    places: {
      entity: 'places', perm: 'places.manage', icon: 'pin', add: 'list.add.place',
      cols: [
        { h: 'f.name', cell: function (r) { return '<b>' + TO.esc(r.name) + '</b>'; } },
        { h: 'f.nameAr', cell: function (r) { return TO.esc(r.nameAr || ''); } },
        { h: 'f.aliases', cell: function (r) { return (r.aliases || []).slice(0, 4).map(function (a) { return '<span class="badge">' + TO.esc(a) + '</span>'; }).join(' '); } },
        { h: 'f.active', cell: function (r) { return activeBadge(r); } }
      ],
      fields: function () { return [
        { key: 'name', label: 'f.name', required: true },
        { key: 'nameAr', label: 'f.nameAr' },
        { key: 'aliases', label: 'f.aliases', type: 'textarea', help: 'help.aliases' },
        { key: 'active', label: 'f.active', type: 'bool' }]; },
      toForm: function (r) { return Object.assign({}, r, { aliases: (r.aliases || []).join('\n') }); },
      fromForm: function (v) { v.aliases = String(v.aliases || '').split(/\n|,|،/).map(function (x) { return x.trim(); }).filter(Boolean); return v; },
      text: function (r) { return [r.name, r.nameAr, (r.aliases || []).join(' ')].join(' '); },
      defaults: { active: true, aliases: [] },
      title: function (r) { return r.name; }
    },
    tripCategories: {
      entity: 'tripCategories', perm: 'categories.manage', icon: 'layers', add: 'list.add.category',
      cols: [
        { h: 'f.name', cell: function (r) { return '<b>' + TO.esc(r.name) + '</b>' + (r.nameAr ? ' <span class="muted">' + TO.esc(r.nameAr) + '</span>' : ''); } },
        { h: 'f.exportSheet', cell: function (r) { return '<span class="badge info">' + TO.esc(r.exportSheet || '') + '</span>'; } },
        { h: 'f.openLimit', cell: function (r) { return r.openLimitHours ? '<span class="num">' + r.openLimitHours + '</span> h' : '<span class="faint">–</span>'; } },
        { h: 'f.ratePerKm', cell: function (r) { return U.num(r.ratePerKm); } },
        { h: 'f.vendor', cell: function (r) { return TO.esc(r.vendor || ''); } },
        { h: 'f.trips', cell: function (r) { return U.num(TO.data.list('trips').filter(function (t) { return t.categoryId === r.id && t.status !== 'cancelled'; }).length); } }
      ],
      fields: function () { return [
        { key: 'name', label: 'f.name', required: true },
        { key: 'nameAr', label: 'f.nameAr' },
        { key: 'exportSheet', label: 'f.exportSheet', type: 'select', options: SHEETS, help: 'help.exportSheet' },
        { key: 'hasSequence', label: 'f.hasSequence', type: 'bool', help: 'help.hasSequence' },
        { key: 'openLimitHours', label: 'f.openLimit', type: 'number', ltr: true, help: 'help.openLimit' },
        { key: 'ratePerKm', label: 'f.ratePerKm', type: 'number', ltr: true, help: 'help.rateHistory' },
        { key: 'ratePerOtHour', label: 'f.ratePerOt', type: 'number', ltr: true },
        { key: 'vendor', label: 'f.vendor' }]; },
      text: function (r) { return [r.name, r.nameAr, r.exportSheet, r.vendor].join(' '); },
      defaults: { exportSheet: 'All Car', openLimitHours: 16 },
      title: function (r) { return r.name; }
    }
  };
  TO.lists = LISTS;

  function activeBadge(r) { return r.active === false ? '<span class="badge">' + TO.esc(TO.t('f.inactive')) + '</span>' : '<span class="badge ok">' + TO.esc(TO.t('f.activeYes')) + '</span>'; }
  function licenseCell(r) {
    if (!r.licenseExpiry) return '<span class="faint">–</span>';
    var days = Math.round((new Date(r.licenseExpiry + 'T00:00:00') - new Date()) / 86400000);
    var tone = days < 0 ? 'bad' : days < 30 ? 'warn' : '';
    return '<span class="badge ' + tone + '">' + TO.esc(U.day(r.licenseExpiry)) + '</span>';
  }

  /* ---------- the form in a side panel ---------- */
  function openForm(cfg, rec) {
    var fields = cfg.fields();
    var values = rec ? (cfg.toForm ? cfg.toForm(rec) : rec) : cfg.defaults;
    var title = rec ? cfg.title(rec) : TO.t(cfg.add);
    TO.panel.open({
      title: title,
      body: '<form id="rec-form" autocomplete="off" class="stack">' + U.fields(fields, values) + '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div></form>',
      footer: (rec && TO.can(cfg.perm) ? '<button class="btn danger" data-del style="margin-inline-end:auto">' + TO.icon('x', 'sm') + TO.esc(TO.t('common.delete')) + '</button>' : '') +
        '<button class="btn ghost" data-cancel>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn primary" data-save>' + TO.esc(TO.t('common.save')) + '</button>',
      mount: function (el) {
        var form = el.querySelector('#rec-form'), err = el.querySelector('.err');
        function save() {
          var r = U.read(form, fields);
          if (r.missing.length) { err.hidden = false; err.textContent = TO.t('form.missing', { f: r.missing.join('، ') }); return; }
          var row = Object.assign({}, rec || {}, cfg.fromForm ? cfg.fromForm(r.values) : r.values);
          delete row.ver; delete row.id;
          var ops = [];
          r.newRefs.forEach(function (n) {   // a typed department that does not exist yet is created in the same save
            var nid = TO.data.newId(n.entity.slice(0, 2)); ops.push({ e: n.entity, id: nid, op: 'put', row: { name: n.text, active: true } }); row[n.field] = nid;
          });
          var id = rec ? rec.id : TO.data.newId(cfg.entity.slice(0, 2));
          ops.push({ e: cfg.entity, id: id, op: 'put', ver: rec ? rec.ver : null, row: row });
          var btn = el.querySelector('[data-save]');
          U.run(TO.data.commit(TO.t(rec ? 'list.saved.edit' : 'list.saved.new', { n: cfg.title(row) }), ops), 'common.saved', btn).then(function () { TO.panel.close(); TO.rerender(); }, function (e) { err.hidden = false; err.textContent = U.errorText(e); });
        }
        form.addEventListener('submit', function (e) { e.preventDefault(); save(); });
        el.querySelector('[data-save]').addEventListener('click', save);
        el.querySelector('[data-cancel]').addEventListener('click', function () { TO.panel.close(); });
        var del = el.querySelector('[data-del]');
        if (del) del.addEventListener('click', function () {
          U.confirm({ title: TO.t('common.delete'), body: TO.t('list.delete.body', { n: cfg.title(rec) }), danger: true, ok: TO.t('common.delete') }).then(function (ok) {
            if (ok) U.run(TO.data.remove(cfg.entity, rec.id, TO.t('list.deleted', { n: cfg.title(rec) })), 'list.deleted.toast').then(function () { TO.panel.close(); TO.rerender(); });
          });
        });
        var first = form.querySelector('input,select,textarea'); if (first) first.focus();
      }
    });
  }
  TO.openListForm = openForm;

  /* ---------- Excel import for vehicles and drivers (one sheet, preview, then one save) ---------- */
  var fleet = null;
  var FILE_CODE = { empty: 'imp.e.empty', unknown: 'imp.e.unknown', damaged: 'imp.e.damaged', big: 'imp.e.big', encrypted: 'imp.e.locked',
    xlsb: 'imp.e.xlsb', old: 'imp.e.oldoffice', pdf: 'imp.e.pdf', image: 'imp.e.picture', drm: 'imp.e.drm', wordGiven: 'imp.e.wordgiven' };
  var FIELD_KEY = { plate: 'f.plate', type: 'f.type', category: 'f.category', vendor: 'f.vendor', notes: 'f.notes', name: 'f.name',
    licenseNo: 'f.licenseNo', mobile: 'f.mobile', ownership: 'f.ownership', active: 'f.active', startKm: 'f.baselineKm' };

  function fleetButtons(cfg) {
    if (!cfg.import || !TO.can(cfg.perm)) return '';
    return '<button type="button" class="btn ghost" data-template>' + TO.icon('download', 'sm') + TO.esc(TO.t('flt.template')) + '</button>' +
      '<button type="button" class="btn" data-import>' + TO.icon('upload', 'sm') + TO.esc(TO.t('flt.import')) + '</button>';
  }
  function downloadTemplate(kind, btn) {
    if (btn) btn.disabled = true;
    fetch('/api/fleet/template?kind=' + encodeURIComponent(kind), { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) return r.json().then(function (j) { var er = new Error((j && j.error) || ('HTTP ' + r.status)); er.data = j; throw er; }, function () { throw new Error('HTTP ' + r.status); });
      var cd = r.headers.get('Content-Disposition') || '', m = /filename="([^"]+)"/.exec(cd);
      return r.blob().then(function (b) { return { b: b, name: m ? m[1] : (kind === 'drivers' ? 'Drivers_template.xlsx' : 'Vehicles_template.xlsx') }; });
    }).then(function (f) {
      var a = document.createElement('a'); a.href = URL.createObjectURL(f.b); a.download = f.name; document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      TO.toast(TO.t('imp.downloaded'));
    }).catch(function (e) { TO.toast(fileErr(e), 'bad', 6000); }).then(function () { if (btn) btn.disabled = false; });
  }
  function fileErr(e) {
    var data = (e && e.data) || {}, mapped = FILE_CODE[data.code];
    if (mapped && TO.has(mapped)) return TO.t(mapped);
    if (data.key && TO.has(data.key)) return TO.t(data.key, data.vars || {});
    return (e && e.message) || TO.t('common.error');
  }
  function reasonText(m) {
    var key = 'flt.m.' + (m && m.code), vars = {};
    if (!TO.has(key)) return TO.esc((m && m.code) || '');
    Object.keys((m && m.vars) || {}).forEach(function (name) { vars[name] = m.vars[name]; });
    if (vars.field && FIELD_KEY[vars.field]) vars.field = TO.t(FIELD_KEY[vars.field]);
    return TO.t(key, vars);
  }
  function startFleet(cfg) {
    fleet = { entity: cfg.entity, phase: 'pick', err: '', pv: null, done: null, spent: false, token: {} };
    TO.rerender();
  }
  function kpi(icon, label, value, hint) {
    return '<div class="card kpi"><span class="label">' + TO.esc(label) + '<span class="tile-ic">' + TO.icon(icon) + '</span></span><span class="value num">' +
      TO.fmt.num(value) + '</span>' + (hint ? '<span class="hint">' + TO.esc(hint) + '</span>' : '') + '</div>';
  }
  function fleetHTML(cfg) {
    var title = TO.t('flt.title.' + cfg.entity);
    var back = '<button type="button" class="btn ghost" data-back>' + TO.esc(TO.t('flt.back')) + '</button>';
    if (fleet.phase === 'busy' || fleet.phase === 'saving') {
      return '<section class="card"><header><h3>' + TO.esc(title) + '</h3></header><p>' + TO.esc(TO.t(fleet.phase === 'saving' ? 'flt.saving' : 'flt.busy')) +
        '</p><div class="skeleton" style="height:8rem"></div></section>';
    }
    if (fleet.phase === 'done' && fleet.done) {
      var d = fleet.done, lines = [TO.t('flt.done.new', { n: d.new }), TO.t('flt.done.update', { n: d.updated })];
      if (d.skipped) lines.push(TO.t('flt.done.skip', { n: d.skipped }));
      if (d.same) lines.push(TO.t('flt.done.same', { n: d.same }));
      if (d.blank) lines.push(TO.t('flt.done.blank', { n: d.blank }));
      return '<section class="card"><div class="empty"><div class="art ok">' + TO.icon('check', 'lg') + '</div><h3>' + TO.esc(TO.t('flt.done.t')) + '</h3><p>' +
        lines.map(function (line) { return '<span class="badge">' + line + '</span>'; }).join(' ') + '</p><p>' + TO.esc(TO.t('flt.done.b')) + '</p>' +
        '<div class="row" style="justify-content:center">' + back + '</div></div></section>';
    }
    if (fleet.phase === 'preview' && fleet.pv) return previewHTML(cfg);
    return '<div class="grid split"><section class="card"><header><h3>' + TO.icon('upload') + ' ' + TO.esc(TO.t('flt.pick')) + '</h3>' + back + '</header>' +
      '<p class="muted">' + TO.esc(TO.t('flt.pick.sub')) + '</p>' +
      '<label class="dropzone" id="flt-dz" for="flt-file" tabindex="0"><span class="art">' + TO.icon('sheet', 'lg') + '</span><b>' + TO.esc(TO.t('flt.drop')) +
      '</b><span class="muted">' + TO.esc(TO.t('flt.types')) + '</span></label><input type="file" id="flt-file" accept=".xlsx,.xlsm,.xls,.csv,.txt,.ods" hidden>' +
      (fleet.err ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<span>' + TO.esc(fleet.err) + '</span></div>' : '') +
      '<div class="row"><button type="button" class="btn ghost" data-template>' + TO.icon('download', 'sm') + TO.esc(TO.t('flt.template')) + '</button></div></section>' +
      '<section class="card"><header><h3>' + TO.icon('info') + ' ' + TO.esc(title) + '</h3></header><ol class="steps">' +
      [1, 2, 3].map(function (i) { return '<li>' + TO.esc(TO.t('flt.how.' + i)) + '</li>'; }).join('') + '</ol></section></div>';
  }
  function previewHTML(cfg) {
    var p = fleet.pv, st = p.stats, many = (p.sheets || []).length > 1;
    var extra = [];
    if (st.same) extra.push(TO.t('flt.sameLine', { n: st.same }));
    if (st.blank) extra.push(TO.t('flt.blankLine', { n: st.blank }));
    var shown = (p.errors || []).slice(0, 80);
    var samples = p.samples || [];
    var cols = [{ h: 'flt.c.row', cell: function (r) { return '<span class="num">' + TO.fmt.num(r.row) + '</span>'; } }];
    if (many) cols.push({ h: 'flt.c.sheet', cell: function (r) { return TO.esc(r.sheet || ''); } });
    cols.push({ h: 'flt.c.item', cell: function (r) {
      if (!r.label) return '<span class="faint">–</span>';
      return cfg.entity === 'vehicles' ? U.plate(r.label) : TO.esc(r.label);
    } });
    cols.push({ h: 'flt.c.reason', cell: function (r) { return (r.messages || []).map(reasonText).join('<br>'); } });
    return '<div class="stack"><div class="toolbar"><h2>' + TO.esc(TO.t('flt.title.' + cfg.entity)) + '</h2><span class="grow"></span>' +
      '<button type="button" class="btn ghost" data-back>' + TO.esc(TO.t('flt.back')) + '</button></div>' +
      (p.filename ? '<p class="muted"><bdi dir="ltr">' + TO.esc(p.filename) + '</bdi></p>' : '') +
      '<div class="grid cols-3">' + kpi('plus', TO.t('flt.k.new'), st.new, TO.t('flt.k.new.h')) + kpi('pen', TO.t('flt.k.update'), st.update, TO.t('flt.k.update.h')) +
      kpi('alert', TO.t('flt.k.error'), st.error, TO.t('flt.k.error.h')) + '</div>' +
      (extra.length ? '<p class="muted">' + extra.join(' · ') + '</p>' : '') +
      (samples.length ? '<section class="card"><header><h3>' + TO.esc(TO.t('flt.will')) + '</h3></header>' + U.table([
        { h: 'flt.c.row', cell: function (r) { return '<span class="num">' + TO.fmt.num(r.row) + '</span>'; } },
        { h: 'flt.will', cell: function (r) { return cfg.entity === 'vehicles' ? U.plate(r.label) : TO.esc(r.label || ''); } },
        { h: 'f.status', cell: function (r) { return '<span class="badge ' + (r.status === 'new' ? 'ok' : 'info') + '">' + TO.esc(TO.t('flt.st.' + r.status)) + '</span>'; } }
      ], samples) + ((st.new + st.update) > samples.length ? '<p class="muted">' + TO.esc(TO.t('flt.more', { n: st.new + st.update - samples.length })) + '</p>' : '') + '</section>' : '') +
      (st.error ? '<section class="card"><header><h3>' + TO.esc(TO.t('flt.err.title')) + '</h3></header>' + U.table(cols, shown) +
        (p.errors.length > shown.length ? '<p class="muted">' + TO.esc(TO.t('flt.more', { n: p.errors.length - shown.length })) + '</p>' : '') + '</section>' : '') +
      (fleet.err ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<span>' + TO.esc(fleet.err) + '</span></div>' : '') +
      '<div class="actionbar"><button type="button" class="btn ghost" data-again>' + TO.esc(TO.t('flt.again')) + '</button>' +
      '<button type="button" class="btn primary" data-commit' + (p.ready > 0 && !fleet.spent ? '' : ' disabled') + '>' + TO.icon('check', 'sm') + TO.esc(TO.t('flt.commit', { n: p.ready })) + '</button></div>' +
      (fleet.err ? '' : '<p class="muted">' + TO.esc(TO.t(p.ready > 0 ? 'flt.note' : 'flt.none')) + '</p>') + '</div>';
  }
  function sendFile(cfg, file) {
    if (!file) return;
    var token = {};
    fleet = { entity: cfg.entity, phase: 'busy', err: '', pv: null, done: null, spent: false, token: token };
    TO.rerender();
    var name = file.name || 'file';
    TO.api('POST', '/api/fleet/preview?kind=' + encodeURIComponent(cfg.entity) + '&name=' + encodeURIComponent(name), file, { raw: true }).then(function (pv) {
      if (!fleet || fleet.token !== token) return;
      fleet.phase = 'preview'; fleet.pv = pv; fleet.err = '';
      TO.rerender();
    }, function (e) {
      if (!fleet || fleet.token !== token) return;
      fleet.phase = 'pick'; fleet.err = fileErr(e);
      TO.rerender();
    });
  }
  function commitFleet(cfg) {
    if (!fleet || fleet.phase === 'saving' || fleet.spent || !fleet.pv || !fleet.pv.ready) return;
    var token = fleet.token, id = fleet.pv.id;
    fleet.phase = 'saving';
    TO.rerender();
    TO.post('/api/fleet/commit', { id: id }).then(function (r) {
      if (!fleet || fleet.token !== token) return;
      return TO.data.load().then(function () {
        if (!fleet || fleet.token !== token) return;
        fleet.phase = 'done';
        fleet.done = { new: r.new, updated: r.updated, skipped: r.skipped, same: r.same, blank: r.blank };
        TO.rerender();
      });
    }, function (e) {
      if (!fleet || fleet.token !== token) return;
      fleet.phase = 'preview'; fleet.spent = true; fleet.err = fileErr(e);
      TO.toast(fleet.err, 'bad', 6000);
      TO.rerender();
    });
  }
  function mountFleet(root, cfg) {
    root.addEventListener('click', function (e) {
      if (e.target.closest('[data-back]')) { fleet = null; TO.rerender(); return; }
      if (e.target.closest('[data-again]')) { startFleet(cfg); return; }
      if (e.target.closest('[data-template]')) { downloadTemplate(cfg.entity, e.target.closest('[data-template]')); return; }
      if (e.target.closest('[data-commit]')) { commitFleet(cfg); }
    });
    var input = root.querySelector('#flt-file'), zone = root.querySelector('#flt-dz');
    if (input) input.addEventListener('change', function () { if (input.files && input.files[0]) sendFile(cfg, input.files[0]); });
    if (zone) {
      zone.addEventListener('dragover', function (e) { e.preventDefault(); zone.classList.add('over'); });
      zone.addEventListener('dragleave', function () { zone.classList.remove('over'); });
      zone.addEventListener('drop', function (e) { e.preventDefault(); zone.classList.remove('over'); var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; if (f) sendFile(cfg, f); });
    }
  }

  /* ---------- the page ---------- */
  function tableHTML(cfg, q) {
    var rows = TO.data.list(cfg.entity).slice();
    var n = U.key(q);
    if (n) rows = rows.filter(function (r) { return U.key(cfg.text(r)).indexOf(n) >= 0; });
    rows.sort(function (a, b) { return String(cfg.title(a)).localeCompare(String(cfg.title(b)), TO.lang); });
    if (!rows.length) return U.empty(cfg.icon, TO.t(q ? 'list.none.search' : 'list.none.title'), TO.t(q ? 'list.none.search.b' : 'list.none.body'),
      !q && TO.can(cfg.perm) ? '<button type="button" class="btn primary" data-add>' + TO.icon('plus', 'sm') + TO.esc(TO.t(cfg.add)) + '</button>' : '');
    return U.table(cfg.cols, rows, { click: true, rowAttr: function (r) { return 'data-id="' + TO.esc(r.id) + '"'; } });
  }
  function listPage(cfg) {
    return '<div class="toolbar"><input class="input" data-q type="search" placeholder="' + TO.esc(TO.t('list.search')) + '" style="max-width:22rem" aria-label="' + TO.esc(TO.t('list.search')) + '">' +
      '<span class="grow"></span><span class="muted"><span class="num" data-count>' + TO.data.list(cfg.entity).length + '</span></span>' +
      fleetButtons(cfg) +
      (TO.can(cfg.perm) ? '<button type="button" class="btn primary" data-add>' + TO.icon('plus', 'sm') + TO.esc(TO.t(cfg.add)) + '</button>' : '') + '</div><div data-body>' + tableHTML(cfg, '') + '</div>';
  }
  function mountList(root, cfg) {
    var body = root.querySelector('[data-body]'), q = root.querySelector('[data-q]');
    function open(id) { var r = TO.data.get(cfg.entity, id); if (r) openForm(cfg, r); }
    root.addEventListener('click', function (e) {
      if (e.target.closest('[data-template]')) { downloadTemplate(cfg.entity, e.target.closest('[data-template]')); return; }
      if (e.target.closest('[data-import]')) { if (TO.can(cfg.perm)) startFleet(cfg); return; }
      if (e.target.closest('[data-add]')) { if (TO.can(cfg.perm)) openForm(cfg); return; }
      var tr = e.target.closest('tr[data-id]'); if (tr) open(tr.dataset.id);
    });
    root.addEventListener('keydown', function (e) { if (e.key === 'Enter') { var tr = e.target.closest && e.target.closest('tr[data-id]'); if (tr) open(tr.dataset.id); } });
    q.addEventListener('input', TO.debounce(function () { body.innerHTML = tableHTML(cfg, q.value); }, 120));
  }

  function head(titleKey, descKey, extra) {
    return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t(titleKey)) + '</h1><p>' + TO.esc(TO.t(descKey)) + '</p></div>' + (extra || '') + '</div>';
  }
  function tabs(active, ids, base) {
    return '<div class="toolbar"><div class="seg" role="group" data-tablist>' + ids.map(function (t) {
      return '<button type="button" data-tab="' + t + '" aria-pressed="' + (t === active) + '">' + TO.esc(TO.t('tab.' + t)) + '</button>'; }).join('') + '</div></div>';
  }
  function needData(fn) {
    return function (ctx) {
      if (!TO.data.state) return '<div class="stack">' + [1, 2, 3, 4].map(function () { return '<div class="skeleton" style="height:3rem"></div>'; }).join('') + '</div>';
      return fn(ctx);
    };
  }
  function withData(view) {
    return {
      render: needData(view.render),
      mount: function (root, ctx) {
        if (!TO.data.state) { TO.data.load().then(function () { TO.rerender(); }); return; }
        view.mount(root, ctx);
      }
    };
  }
  TO.withData = withData;
  TO.pageHead = head;

  function grouped(pageId, ids, descFor) {   // a page with tabs, one list per tab
    return withData({
      render: function (ctx) {
        var tab = ids.indexOf(ctx.route.q.tab) >= 0 ? ctx.route.q.tab : ids[0];
        if (fleet && fleet.entity !== tab) fleet = null;
        return head('nav.' + pageId, descFor(tab)) + (ids.length > 1 ? tabs(tab, ids) : '') +
          (fleet && fleet.entity === tab ? fleetHTML(LISTS[tab]) : listPage(LISTS[tab]));
      },
      mount: function (root, ctx) {
        var tab = ids.indexOf(ctx.route.q.tab) >= 0 ? ctx.route.q.tab : ids[0];
        var tl = root.querySelector('[data-tablist]');
        if (tl) tl.addEventListener('click', function (e) { var b = e.target.closest('[data-tab]'); if (b) { fleet = null; TO.go(pageId + '?tab=' + b.dataset.tab); } });
        if (fleet && fleet.entity === tab) mountFleet(root, LISTS[tab]);
        else mountList(root, LISTS[tab]);
      }
    });
  }
  TO.views.vehicles = grouped('vehicles', ['vehicles'], function () { return 'page.vehicles.d'; });
  TO.views.drivers = grouped('drivers', ['drivers'], function () { return 'page.drivers.d'; });
  TO.views.people = grouped('people', ['people', 'departments'], function () { return 'page.people.d'; });
  TO.views.places = grouped('places', ['places'], function () { return 'page.places.d'; });
  // the tabs bar of single-list pages is hidden by CSS (one tab is not a choice)
  TO.listTable = tableHTML;
  TO.listPage = listPage;
  TO.mountList = mountList;
})();
