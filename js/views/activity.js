/* Trip Orders - Activity log: every change with who, when and from which PC (from the signed history). */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var q = '';
  var FIELD_KEYS = { destination: 'f.destination', status: 'f.status', startKm: 'f.startKm', endKm: 'f.endKm', startAt: 'f.startAt', endAt: 'f.endAt',
    date: 'f.date', driverId: 'f.driver', vehicleId: 'f.vehicle', requesterId: 'f.requester', departmentId: 'f.department', categoryId: 'f.category',
    notes: 'f.notes', gaApproved: 'f.gaApproved', purpose: 'f.purpose', seq: 'f.seq' };
  function fieldLabel(name) {
    var k = FIELD_KEYS[name];
    return k && TO.has(k) ? TO.t(k) : name;
  }
  function auditLabel(label) {
    if (!label || TO.lang === 'en') return label || '';
    var m, k;
    m = label.match(/^New trip (.+)$/); if (m) return TO.t('act.label.newTrip', { no: m[1] });
    m = label.match(/^Closed trip (.+)$/); if (m) return TO.t('act.label.closedTrip', { no: m[1] });
    m = label.match(/^Started trip (.+)$/); if (m) return TO.t('act.label.startedTrip', { no: m[1] });
    m = label.match(/^Amend trip ([^:]+): (.+)$/); if (m) return TO.t('act.label.amendTrip', { no: m[1], field: fieldLabel(m[2].trim()) });
    m = label.match(/^Reviewed trip (.+)$/); if (m) return TO.t('act.label.reviewedTrip', { no: m[1] });
    m = label.match(/^Driver link for trip (.+)$/); if (m) return TO.t('act.label.driverLink', { no: m[1] });
    if (label.indexOf('Restore deleted:') === 0) return TO.t('act.label.restoreDeleted') + label.slice(16);
    if (label === 'Excel export') return TO.t('act.label.excelExport');
    if (label === 'Word export') return TO.t('act.label.wordExport');
    if (label === 'Full Excel export') return TO.t('act.label.fullExcelExport');
    if (label === 'Backup created') return TO.t('act.label.backupCreated');
    if (label.indexOf('Restored backup') === 0) return TO.t('act.label.restoredBackup');
    if (label.indexOf('Excel import') >= 0) return TO.t('act.label.excelImport');
    k = 'act.label.exact.' + label;
    return TO.has(k) ? TO.t(k) : label;
  }
  function auditEntity(entity) {
    var k = 'err.entity.' + entity;
    return TO.has(k) ? TO.t(k) : (entity || '');
  }
  function auditOp(op) {
    var k = 'act.op.' + op;
    return TO.has(k) ? TO.t(k) : (op || '');
  }
  function rowsHTML(rows) {
    if (!rows.length) return U.empty('activity', TO.t('act.none.t'), TO.t('act.none.b'));
    return U.table([
      { h: 'f.time', cell: function (r) { return '<span class="num">' + U.dt(r.ts) + '</span>'; } },
      { h: 'f.user', cell: function (r) { return TO.esc(r.user || ''); } },
      { h: 'f.pc', cell: function (r) { return TO.esc(r.node_name || ''); } },
      { h: 'f.action', cell: function (r) { return TO.esc(auditLabel(r.label || '')); } },
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
        TO.get('/api/audit?limit=200&q=' + encodeURIComponent(q)).then(function (r) { body.innerHTML = rowsHTML(r.rows || []); }, function (e) { body.innerHTML = U.empty('lock', TO.t('common.error'), U.errorText(e)); });
      }
      input.value = q;
      input.addEventListener('input', TO.debounce(function () { q = input.value.trim(); load(); }, 250));
      load();
    }
  };
})();
