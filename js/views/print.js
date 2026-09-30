/* Trip Orders - the printable trip order: the paper form's fields on one A4 page, prefilled, with the trip number as a QR code. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var FIELDS = [['passenger', 'department'], ['gaOk', 'gaSign'], ['gaDate'], ['driver', 'plate'], ['carType'], ['startKm', 'startPoint'], ['startTime', 'startDate'], ['route'], ['endKm', 'endPoint'], ['endTime', 'endDate'], ['passSign', 'driverSign']];
  var WIDE = { route: 1, gaDate: 1, carType: 1 };

  function qr(text) {
    try { var q = window.qrcode(0, 'M'); q.addData(text); q.make(); return q.createSvgTag({ cellSize: 3, margin: 0, scalable: true }); } catch (e) { return ''; }
  }
  function settingsValue(id) {
    var v = ((TO.data.state && TO.data.state.settings) || {})[id];
    return v ? String(v) : '';
  }
  function values(t) {
    var v = TO.data.get('vehicles', t.vehicleId) || {};
    var pax = TO.data.list('tripPassengers').filter(function (p) { return p.tripId === t.id; }).map(function (p) { return p.personId ? TO.data.name('people', p.personId) : p.freeText; }).filter(Boolean);
    var req = TO.data.name('people', t.requesterId);
    if (req && pax.indexOf(req) < 0) pax.unshift(req);
    return { passenger: pax.join('، '), department: TO.data.name('departments', t.departmentId), driver: TO.data.name('drivers', t.driverId), plate: v.plate || '',
      carType: v.type || TO.data.catName(t.categoryId), startDate: U.day(t.date), route: t.destination || '', gaOk: TO.t('form.yesno') };
  }
  function sheet(t) {
    var val = values(t), name = settingsValue('systemName'), legal = settingsValue('legalText');
    var rows = FIELDS.map(function (pair) {
      if (pair.length === 1 || WIDE[pair[0]]) return '<tr><th>' + TO.esc(TO.t('form.' + pair[0])) + '</th><td colspan="3">' + TO.esc(val[pair[0]] || '') + '</td></tr>';
      return '<tr><th>' + TO.esc(TO.t('form.' + pair[0])) + '</th><td>' + TO.esc(val[pair[0]] || '') + '</td><th>' + TO.esc(TO.t('form.' + pair[1])) + '</th><td>' + TO.esc(val[pair[1]] || '') + '</td></tr>';
    }).join('');
    return '<div class="ps-head"><div>' + (name ? '<div class="ps-org">' + TO.esc(name) + '</div>' : '') + '<h1>' + TO.esc(TO.t('form.title')) + '</h1><div class="ps-no">' + TO.esc(TO.t('form.no')) + ': <b dir="ltr">' + TO.esc(t.no) + '</b></div></div>' +
      '<div class="ps-qr" aria-hidden="true">' + qr(t.no) + '</div></div><table class="ps-table">' + rows + '</table>' + (legal ? '<p class="ps-legal">' + TO.esc(legal) + '</p>' : '');
  }
  TO.printTrip = function (t) {
    var el = document.createElement('div');
    el.id = 'print-sheet';
    el.innerHTML = sheet(t);
    document.body.appendChild(el);
    document.body.classList.add('printing');
    var done = function () { document.body.classList.remove('printing'); el.remove(); window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done);
    setTimeout(function () { window.print(); }, 60);
  };
})();
