/* Trip Orders - Activity log: every change with who, when and from which PC (from the signed history). */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var q = '';
  var FIELD_KEYS = { destination: 'f.destination', status: 'f.status', startKm: 'f.startKm', endKm: 'f.endKm', startAt: 'f.startAt', endAt: 'f.endAt',
    date: 'f.date', driverId: 'f.driver', vehicleId: 'f.vehicle', requesterId: 'f.requester', departmentId: 'f.department', categoryId: 'f.category',
    notes: 'f.notes', gaApproved: 'f.ga', billableKm: 'f.billableKm', purpose: 'f.purpose', seq: 'f.seq' };
  function fieldLabel(name) {
    var k = FIELD_KEYS[name];
    return k && TO.has(k) ? TO.t(k) : name;
  }
  function translatedType(type) {
    var aliases = { start: 'start_odo', end: 'end_odo' };
    var k = 'photo.' + (aliases[type] || type);
    return TO.has(k) ? TO.t(k) : type;
  }
  function safeMessage(key, vars, ltrNames, rich) {
    if (!rich) return TO.t(key, vars);
    var marked = {}, values = {}, names = Object.keys(vars || {});
    names.forEach(function (name, i) {
      var token = '\u0000' + i + '\u0000';
      marked[name] = token;
      values[token] = { value: vars[name], ltr: (ltrNames || []).indexOf(name) >= 0 };
    });
    var out = TO.esc(TO.t(key, marked));
    Object.keys(values).forEach(function (token) {
      var value = TO.esc(values[token].value == null ? '' : String(values[token].value));
      if (values[token].ltr) value = '<bdi dir="ltr">' + value + '</bdi>';
      out = out.split(token).join(value);
    });
    return out;
  }
  function auditLabel(label, rich) {
    if (!label) return '';
    var m, k;
    m = label.match(/^New trip (.+)$/); if (m) return safeMessage('act.label.newTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^Closed trip (.+)$/); if (m) return safeMessage('act.label.closedTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^Started trip (.+)$/); if (m) return safeMessage('act.label.startedTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^Amend trip ([^:]+): (.+)$/); if (m) return safeMessage('act.label.amendTrip', { no: m[1], field: fieldLabel(m[2].trim()) }, ['no'], rich);
    m = label.match(/^Reviewed trip (.+)$/); if (m) return safeMessage('act.label.reviewedTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^GA approved trip (.+)$/); if (m) return safeMessage('act.label.gaApprovedTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^GA declined trip (.+)$/); if (m) return safeMessage('act.label.gaDeclinedTrip', { no: m[1] }, ['no'], rich);
    m = label.match(/^Driver link for trip (.+?) replaced$/); if (m) return safeMessage('act.label.driverLinkReplaced', { no: m[1] }, ['no'], rich);
    m = label.match(/^Driver link for trip (.+)$/); if (m) return safeMessage('act.label.driverLink', { no: m[1] }, ['no'], rich);
    m = label.match(/^Driver link ([^:]+): (.+)$/); if (m) return safeMessage('act.label.driverEvents', { no: m[1], events: m[2].split(',').map(function (x) { return translatedType(x.trim()); }).join('، ') }, ['no'], rich);
    m = label.match(/^Driver photo (.+) for (.+)$/); if (m) return safeMessage('act.label.driverPhoto', { kind: translatedType(m[1]), no: m[2] }, ['no'], rich);
    m = label.match(/^Released the phone of trip (.+)$/); if (m) return safeMessage('act.label.releasedPhone', { no: m[1] }, ['no'], rich);
    m = label.match(/^(Word|Excel) import(.*) \((\d+) trips\)$/);
    if (m) return safeMessage(m[1] === 'Word' ? 'act.label.wordImportWithCount' : 'act.label.excelImportWithCount',
      { detail: m[2], n: m[3] }, ['n'], rich);
    if (label.indexOf('Restore backup of') === 0) return (rich ? TO.esc(TO.t('act.label.restoreBackupOf') + label.slice(18)) : TO.t('act.label.restoreBackupOf') + label.slice(18));
    if (label.indexOf('Restore deleted:') === 0) return (rich ? TO.esc(TO.t('act.label.restoreDeleted') + label.slice(16)) : TO.t('act.label.restoreDeleted') + label.slice(16));
    if (label.indexOf('Word import') === 0) return (rich ? TO.esc(TO.t('act.label.wordImport') + label.slice(11)) : TO.t('act.label.wordImport') + label.slice(11));
    if (label.indexOf('Excel import') === 0) return (rich ? TO.esc(TO.t('act.label.excelImport') + label.slice(12)) : TO.t('act.label.excelImport') + label.slice(12));
    k = 'act.label.exact.' + label;
    return rich ? TO.esc(TO.has(k) ? TO.t(k) : label) : (TO.has(k) ? TO.t(k) : label);
  }
  function auditEntity(entity) {
    var k = 'act.entity.' + entity;
    if (TO.has(k)) return TO.t(k);
    k = 'err.entity.' + entity;
    return TO.has(k) ? TO.t(k) : (entity || '');
  }
  function auditOp(op) {
    var k = 'act.op.' + op;
    return TO.has(k) ? TO.t(k) : (op || '');
  }
  function matches(row, needle) {
    if (!needle) return true;
    needle = needle.toLocaleLowerCase();
    return [auditLabel(row.label || ''), auditEntity(row.entity || ''), auditOp(row.op || ''),
      row.user || '', row.node_name || '', U.dt(row.ts)].some(function (value) {
      return String(value).toLocaleLowerCase().indexOf(needle) >= 0;
    });
  }
  function rowsHTML(rows) {
    if (!rows.length) return U.empty('activity', TO.t('act.none.t'), TO.t('act.none.b'));
    return U.table([
      { h: 'f.time', cell: function (r) { return '<span class="num"><bdi dir="ltr">' + U.dt(r.ts) + '</bdi></span>'; } },
      { h: 'f.user', cell: function (r) { return TO.esc(r.user || ''); } },
      { h: 'f.pc', cell: function (r) { return TO.esc(r.node_name || ''); } },
      { h: 'f.action', cell: function (r) { return auditLabel(r.label || '', true); } },
      { h: 'f.what', cell: function (r) { return '<span class="badge">' + TO.esc(auditEntity(r.entity || '')) + '</span> <span class="faint">' + TO.esc(auditOp(r.op || '')) + '</span>'; } }
    ], rows);
  }
  TO.views.activity = {
    render: function () {
      return TO.pageHead('nav.activity', 'page.activity.d') + '<div class="toolbar"><input class="input" data-q type="search" placeholder="' + TO.esc(TO.t('list.search')) + '" style="max-width:22rem"></div><div data-body><div class="skeleton" style="height:12rem"></div></div>';
    },
    mount: function (root) {
      var body = root.querySelector('[data-body]'), input = root.querySelector('[data-q]');
      function load() {
        TO.get('/api/audit?limit=1000').then(function (r) {
          body.innerHTML = rowsHTML((r.rows || []).filter(function (row) { return matches(row, q); }));
        }, function (e) { body.innerHTML = U.empty('lock', TO.t('common.error'), U.errorText(e)); });
      }
      input.value = q;
      input.addEventListener('input', TO.debounce(function () { q = input.value.trim(); load(); }, 250));
      load();
    }
  };
  TO.auditLabel = auditLabel;
  TO.activityMatches = matches;
})();
