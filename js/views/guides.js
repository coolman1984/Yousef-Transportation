/* Trip Orders - step-by-step guides, "Solve a problem" and the learning path per role (owner's request 2026-10-09: a
   brand-new person learns the program alone, in order; ported from the sibling Hessa, same engine).

   A guide is a list of steps; each step has a kind (open a page, click, type, choose, check, warning...) and, when it
   points at something on the screen, the page it lives on and a CSS selector. "Guide me" docks a small card at the side
   of the screen that stays while the person works: it opens the right page, outlines the button to press, and moves on
   when they press Next. Nothing is ever clicked or typed for them - they learn by doing it once.

   Words live in the dictionaries: gd.<id>.t (title), gd.<id>.d (what you get), gd.<id>.<n> (step n), gd.<id>.ok (how you
   know it worked) and gd.<id>.x (the usual mistake, optional). Inside a step, [[some.key]] shows that key's text in
   «quotes», so a step always names the button exactly as the screen does, in either language.
   Problems: sit.<id>.q / sit.<id>.a. Learning paths: path.<id>.t / path.<id>.d. Facts: server/tripsvc.py GUIDE_FACTS. */
(function () {
  'use strict';
  var TO = window.TO;

  // step kinds: icon + the small word in front of the step
  var KINDS = { go: 'route', click: 'pointer', type: 'pen', choose: 'sliders', check: 'eye', tip: 'info', warn: 'alert', done: 'flag' };
  var CATS = ['start', 'daily', 'review', 'office', 'admin'];

  function S(k, page, sel) { return { k: k, page: page || null, sel: sel || null }; }
  var OV = '#overlay', DR = '#panels .drawer:last-child', TRIP = 'trips', ROW = 'tr[data-id]';

  var GUIDES = [
    /* ---------- the first day: sign in, the screen, setting the office up ---------- */
    { id: 'first', cat: 'start', icon: 'flag', account: true, steps: [
      S('tip', 'overview'), S('click', null, '[data-act="account"]'), S('check', null, DR + ' .kv'), S('click', null, DR + ' [data-pw]'),
      S('type', null, '#pw-old'), S('type', null, '#pw-new'), S('click', null, OV + ' [data-ok]'), S('check')] },
    { id: 'tour', cat: 'start', icon: 'compass', steps: [
      S('go', 'overview'), S('check', 'overview', '[data-tour="nav"]'), S('check', 'overview', '[data-tour="search"]'), S('check', 'overview', '[data-tour="tools"]'),
      S('check', 'overview', '[data-tour="kpis"]'), S('check', 'overview', '[data-pathcard]'), S('tip', null, '[data-act="keys"]')] },
    { id: 'appearance', cat: 'start', icon: 'palette', steps: [
      S('go', 'settings'), S('choose', 'settings', '[data-pref="lang"]'), S('choose', 'settings', '[data-pref="theme"]'), S('choose', 'settings', '[data-pref="size"]'),
      S('check', 'settings', '.preview-box'), S('tip')] },
    { id: 'categories', cat: 'start', icon: 'layers', perm: 'categories.manage', steps: [
      S('go', 'settings?tab=rules'), S('click', 'settings?tab=rules', '[data-add]'), S('type', null, DR + ' [name="name"]'), S('type', null, DR + ' [name="nameAr"]'),
      S('choose', null, DR + ' [name="exportSheet"]'), S('type', null, DR + ' [name="ratePerKm"]'), S('type', null, DR + ' [name="openLimitHours"]'),
      S('click', null, DR + ' [data-save]'), S('check', 'settings?tab=rules', '.tbl')] },
    { id: 'vehicles', cat: 'start', icon: 'car', perm: 'vehicles.manage', steps: [
      S('go', 'vehicles'), S('click', 'vehicles', '[data-add]'), S('type', null, DR + ' [name="plate"]'), S('choose', null, DR + ' [name="categoryId"]'),
      S('choose', null, DR + ' [name="ownership"]'), S('type', null, DR + ' [name="startKm"]'), S('click', null, DR + ' [data-save]'), S('check', 'vehicles', '.tbl'), S('warn')] },
    { id: 'drivers', cat: 'start', icon: 'wheel', perm: 'drivers.manage', steps: [
      S('go', 'drivers'), S('click', 'drivers', '[data-add]'), S('type', null, DR + ' [name="name"]'), S('type', null, DR + ' [name="mobile"]'),
      S('type', null, DR + ' [name="licenseExpiry"]'), S('click', null, DR + ' [data-save]'), S('check', 'drivers', '.tbl'), S('tip')] },
    { id: 'people', cat: 'start', icon: 'users', perm: 'people.manage', steps: [
      S('go', 'people'), S('click', 'people', '[data-add]'), S('type', null, DR + ' [name="name"]'), S('type', null, DR + ' [name="departmentId"]'),
      S('choose', null, DR + ' [name="isRequester"]'), S('click', null, DR + ' [data-save]'), S('go', 'people?tab=departments'), S('check', 'people?tab=departments', '.tbl')] },
    { id: 'places', cat: 'start', icon: 'pin', perm: 'places.manage', steps: [
      S('go', 'places'), S('click', 'places', '[data-add]'), S('type', null, DR + ' [name="name"]'), S('type', null, DR + ' [name="nameAr"]'),
      S('type', null, DR + ' [name="aliases"]'), S('click', null, DR + ' [data-save]'), S('check', 'places', '.tbl'), S('tip')] },
    { id: 'staff', cat: 'admin', icon: 'user', perm: 'users.manage', account: true, steps: [
      S('go', 'settings?tab=access'), S('click', 'settings?tab=access', '[data-adduser]'), S('type', null, DR + ' [name="full_name"]'), S('choose', null, DR + ' [data-mode]'),
      S('type', null, DR + ' [name="username"]'), S('type', null, DR + ' [name="password"]'), S('choose', null, DR + ' [name="role"]'), S('choose', null, DR + ' [data-scope]'),
      S('warn'), S('click', null, DR + ' [data-save]'), S('check', 'settings?tab=access', '.tbl')] },
    { id: 'profiles', cat: 'admin', icon: 'shield', perm: 'users.manage', account: true, steps: [
      S('go', 'settings?tab=access'), S('click', 'settings?tab=access', '[data-profiles]'), S('check', null, OV + ' .dialog .card'), S('click', null, OV + ' [data-newprofile]'),
      S('type', null, '#pf-name'), S('check', null, OV + ' .perm-group'), S('choose', null, '#pf-apply'), S('click', null, OV + ' [data-ok]'), S('tip')] },
    { id: 'mailbox', cat: 'admin', icon: 'cloud', perm: 'gateway.manage', steps: [
      S('tip'), S('go', 'settings?tab=gateway'), S('type', 'settings?tab=gateway', '#gw-url'), S('click', 'settings?tab=gateway', '[data-gw="generate"], [data-gw="show"]'),
      S('check', 'settings?tab=gateway', '[data-select]'), S('tip'), S('click', 'settings?tab=gateway', '[data-gw="test"]'), S('check'), S('warn')] },

    /* ---------- every day: trip orders, driver links, the board ---------- */
    { id: 'newTrip', cat: 'daily', icon: 'plus', perm: 'trips.create', steps: [
      S('go', TRIP), S('click', TRIP, '[data-new]'), S('choose', null, '#f-date'), S('choose', null, '#f-categoryId'), S('choose', null, '#f-vehicleId'),
      S('choose', null, '#f-driverId'), S('type', null, '#f-requesterId'), S('type', null, '#f-passengersText'), S('type', null, '#f-destination'),
      S('click', null, OV + ' [data-save]'), S('check', null, DR), S('tip')] },
    { id: 'sendLink', cat: 'daily', icon: 'chat', perm: 'trips.send', steps: [
      S('go', TRIP), S('click', TRIP, ROW), S('check', null, DR + ' [data-trip]'), S('click', null, DR + ' [data-a="wa"]'), S('check'),
      S('click', null, DR + ' [data-a="copylink"]'), S('warn')] },
    { id: 'board', cat: 'daily', icon: 'board', perm: 'board.view', steps: [
      S('go', 'board'), S('check', 'board', '.grid'), S('click', 'board', '[data-day="1"]'), S('click', 'board', '[data-day="0"]'), S('click', 'board', '.board-card'), S('tip')] },
    { id: 'find', cat: 'daily', icon: 'search', perm: 'trips.view', steps: [
      S('go', TRIP), S('type', TRIP, '[data-f="q"]'), S('choose', TRIP, '[data-f="range"]'), S('choose', TRIP, '[data-f="status"]'), S('click', TRIP, '[data-trust]'),
      S('click', TRIP, ROW), S('tip')] },
    { id: 'approve', cat: 'daily', icon: 'check', perm: 'trips.approve', steps: [
      S('go', TRIP), S('choose', TRIP, '[data-f="range"]'), S('click', TRIP, ROW), S('check', null, DR + ' .kv'), S('click', null, DR + ' [data-a="approve"]'), S('check'), S('tip')] },
    { id: 'cancel', cat: 'daily', icon: 'x', perm: 'trips.cancel', steps: [
      S('go', TRIP), S('click', TRIP, ROW), S('click', null, DR + ' [data-a="cancel"]'), S('type', null, '#cf-reason'), S('click', null, OV + ' [data-ok]'), S('check'), S('warn')] },
    { id: 'print', cat: 'daily', icon: 'printer', perm: 'trips.view', steps: [
      S('go', TRIP), S('click', TRIP, ROW), S('click', null, DR + ' [data-a="print"]'), S('tip'), S('click', null, DR + ' a[download]'), S('check')] },

    /* ---------- checking and closing trips ---------- */
    { id: 'review', cat: 'review', icon: 'shield', perm: 'review.view', steps: [
      S('go', 'review'), S('check', 'review', 'article[data-id]'), S('check', 'review', '.chip-row'), S('click', 'review', 'article[data-id]'),
      S('check', null, DR + ' [data-trip]'), S('tip'), S('warn')] },
    { id: 'amend', cat: 'review', icon: 'wrench', perm: ['trips.amend', 'trips.review'], steps: [
      S('go', TRIP), S('click', TRIP, ROW), S('click', null, DR + ' [data-a="amend"]'), S('choose', null, '#am-f'), S('type', null, '#am-v'), S('type', null, '#am-r'),
      S('click', null, OV + ' [data-ok]'), S('check', null, DR + ' [data-trip]'), S('tip')] },
    { id: 'close', cat: 'review', icon: 'lock', perm: 'trips.review', steps: [
      S('go', TRIP), S('choose', TRIP, '[data-f="status"]'), S('click', TRIP, ROW), S('check', null, DR + ' [data-trip]'), S('click', null, DR + ' [data-a="amend"]'),
      S('choose', null, '#am-f'), S('choose', null, '#am-v'), S('type', null, '#am-r'), S('click', null, OV + ' [data-ok]'), S('warn')] },

    /* ---------- reports, Excel and Word ---------- */
    { id: 'reports', cat: 'office', icon: 'chart', perm: 'reports.view', steps: [
      S('go', 'reports'), S('choose', 'reports', '#rp-ym'), S('click', 'reports', '[data-g]'), S('check', 'reports', '#rp-body'), S('click', 'reports', '[data-present]'), S('tip')] },
    { id: 'excelExport', cat: 'office', icon: 'download', perm: 'excel.export', steps: [
      S('go', 'excel'), S('click', 'excel', '[data-tab="export"]'), S('choose', 'excel', '#ex-ym'), S('choose', 'excel', 'input[name="layout"]'), S('click', 'excel', '[data-dl="excel"]'),
      S('check'), S('tip', 'excel', '[data-tab="word"]')] },
    { id: 'import', cat: 'office', icon: 'upload', perm: 'excel.import', steps: [
      S('tip'), S('go', 'excel'), S('click', 'excel', '[data-tab="import"]'), S('click', 'excel', '#dz'), S('check', 'excel', '#xl-body'), S('choose', 'excel', '[data-f]'),
      S('click', 'excel', '[data-commit]'), S('check'), S('warn')] },

    /* ---------- safety and administration ---------- */
    { id: 'backup', cat: 'admin', icon: 'lock', perm: 'backups.manage', steps: [
      S('go', 'settings?tab=data'), S('click', 'settings?tab=data', '[data-backup]'), S('type', 'settings?tab=data', '#bk2-path'), S('click', 'settings?tab=data', '[data-folder-save]'),
      S('check', 'settings?tab=data', '[data-folders]'), S('warn')] },
    { id: 'bin', cat: 'admin', icon: 'refresh', perm: 'trash.restore', steps: [
      S('go', 'settings?tab=data'), S('check', 'settings?tab=data', '[data-restore]'), S('click', 'settings?tab=data', '[data-restore]'), S('check'), S('warn', 'settings?tab=data', '[data-brestore]')] },
    { id: 'activity', cat: 'admin', icon: 'activity', perm: 'logs.view', steps: [
      S('go', 'activity'), S('type', 'activity', '[data-q]'), S('check', 'activity', '.tbl'), S('tip')] },
    { id: 'pcs', cat: 'admin', icon: 'layers', steps: [
      S('go', 'overview'), S('check', 'overview', '#status-kv'), S('tip'), S('check', 'overview', '[data-tour="kpis"]'), S('warn')] }
  ];

  // problems that happen in a transport office, and exactly what to do (sit.<id>.q / .a); page = where to act; cat = group
  var SITUATIONS = [
    ['driverNoShow', 'trips', 'daily'], ['carBroke', 'trips', 'daily'], ['wrongDate', 'trips', 'daily'], ['duplicate', 'trips', 'daily'],
    ['approvedByMistake', 'trips', 'daily'], ['cancelledByMistake', 'trips', 'daily'], ['linkNotOpening', 'trips', 'daily'], ['newPhone', 'trips', 'daily'],
    ['noSignal', 'board', 'daily'], ['whatsappNotOpening', 'trips', 'daily'], ['noCategories', 'settings?tab=rules', 'daily'], ['unknownPassenger', 'people', 'daily'],
    ['newDriver', 'drivers', 'daily'], ['rentedCar', 'vehicles', 'daily'], ['licenceExpired', 'drivers', 'daily'],
    ['redTrip', 'review', 'review'], ['wrongKm', 'trips', 'review'], ['kmBackwards', 'review', 'review'], ['tripStillOpen', 'board', 'review'], ['photoUnclear', 'review', 'review'],
    ['monthToExcel', 'excel', 'office'], ['excelRefused', 'excel', 'office'], ['monthReport', 'reports', 'office'], ['paperForm', 'trips', 'office'],
    ['forgotPassword', 'settings?tab=access', 'admin'], ['personLeft', 'settings?tab=access', 'admin'], ['newEmployee', 'settings?tab=access', 'admin'],
    ['tooManyRights', 'settings?tab=access', 'admin'], ['deletedByMistake', 'settings?tab=data', 'admin'], ['pcBroken', 'settings?tab=data', 'admin'],
    ['powerCut', 'overview', 'admin'], ['networkDown', 'overview', 'admin'], ['mailboxRed', 'settings?tab=gateway', 'admin'], ['whoChanged', 'activity', 'admin'],
    ['wrongLanguage', 'settings', 'admin']
  ];
  // every problem offers "Guide me" through the guide that fixes it (situation id -> guide id)
  var SIT_GUIDE = { driverNoShow: 'cancel', carBroke: 'newTrip', wrongDate: 'amend', duplicate: 'cancel', approvedByMistake: 'amend', cancelledByMistake: 'amend',
    linkNotOpening: 'sendLink', newPhone: 'sendLink', noSignal: 'board', whatsappNotOpening: 'sendLink', noCategories: 'categories', unknownPassenger: 'people',
    newDriver: 'drivers', rentedCar: 'vehicles', licenceExpired: 'drivers', redTrip: 'review', wrongKm: 'amend', kmBackwards: 'review', tripStillOpen: 'close',
    photoUnclear: 'review', monthToExcel: 'excelExport', excelRefused: 'import', monthReport: 'reports', paperForm: 'print', forgotPassword: 'staff',
    personLeft: 'staff', newEmployee: 'staff', tooManyRights: 'profiles', deletedByMistake: 'bin', pcBroken: 'backup', powerCut: 'pcs', networkDown: 'pcs',
    mailboxRed: 'mailbox', whoChanged: 'activity', wrongLanguage: 'appearance' };

  /* ---------- the learning path (المنهج): ordered lessons per role, and where the person stands ----------
     A lesson is a guide; its fact (server/tripsvc.py GUIDE_FACTS) says whether it already happened in the real records; a
     lesson without a fact is done when its guide was finished on this PC. */
  function L(guide, fact) { return { guide: guide, fact: fact || null }; }
  var PATHS = [
    { id: 'admin', admin: true, icon: 'shield', roles: ['administrator'], lessons: [
      L('first', 'passwordChanged'), L('categories', 'categoriesAdded'), L('vehicles', 'vehiclesAdded'), L('drivers', 'driversAdded'), L('people', 'peopleAdded'),
      L('places', 'placesAdded'), L('staff', 'staffAdded'), L('profiles'), L('mailbox', 'mailboxReady'), L('newTrip', 'myTripCreated'), L('backup', 'backupFolder'),
      L('activity')] },
    // full access = every daily right but no administrator right: the setup lists and the daily work, without people and the mailbox
    { id: 'manager', icon: 'star', roles: ['full-access'], lessons: [
      L('first', 'passwordChanged'), L('categories', 'categoriesAdded'), L('vehicles', 'vehiclesAdded'), L('drivers', 'driversAdded'), L('people', 'peopleAdded'),
      L('places', 'placesAdded'), L('newTrip', 'myTripCreated'), L('sendLink', 'myLinkMade'), L('review'), L('close', 'myTripClosed'), L('reports'), L('activity')] },
    { id: 'dispatcher', icon: 'route', roles: ['dispatcher'], lessons: [
      L('first', 'passwordChanged'), L('tour'), L('newTrip', 'myTripCreated'), L('sendLink', 'myLinkMade'), L('board'), L('find'), L('cancel', 'myCancel'),
      L('print', 'myWordForm'), L('excelExport', 'myExcelExport')] },
    { id: 'approver', icon: 'check', roles: ['ga-approver'], lessons: [
      L('first', 'passwordChanged'), L('approve', 'myApproval'), L('board'), L('find'), L('print', 'myWordForm')] },
    { id: 'reviewer', icon: 'shield', roles: ['reviewer'], lessons: [
      L('first', 'passwordChanged'), L('review'), L('amend', 'myAmendment'), L('close', 'myTripClosed'), L('reports'), L('excelExport', 'myExcelExport')] },
    { id: 'finance', icon: 'chart', roles: ['finance'], lessons: [
      L('first', 'passwordChanged'), L('reports'), L('find'), L('excelExport', 'myExcelExport'), L('import', 'myImport')] },
    { id: 'viewer', icon: 'eye', roles: ['viewer'], lessons: [L('first', 'passwordChanged'), L('find'), L('board'), L('print', 'myWordForm')] }
  ];
  // ready-made profiles keep their English name on the person (server/auth.py BUILTIN_PROFILES)
  var ROLE_PATH = { 'Administrator': 'admin', 'Full access': 'manager', 'Dispatcher': 'dispatcher', 'GA Approver': 'approver', 'Reviewer': 'reviewer',
    'Finance': 'finance', 'Viewer': 'viewer' };
  var facts = null, factsAt = 0, factsFor = null;   // facts belong to the person signed in
  // the course and the lessons a person finished belong to that person, not to the PC (review: a shared office PC)
  function learner() {
    var all = TO.prefs.data.learn || (TO.prefs.data.learn = {}), id = (TO.me && TO.me.id) || '_';
    return all[id] || (all[id] = {});
  }
  function loadFacts(force) {
    var who = (TO.me && TO.me.id) || '_';
    if (!force && facts && factsFor === who && Date.now() - factsAt < 15000) return Promise.resolve(facts);
    return TO.get('/api/guide-facts').then(function (f) { facts = f || {}; factsAt = Date.now(); factsFor = who; return facts; }, function () { return (factsFor === who && facts) || {}; });   // on a failed fetch: never another person's facts
  }
  function defaultPath() {
    var me = TO.me || {}, id = ROLE_PATH[me.role];
    if (!id) id = TO.can('users.manage') ? 'admin' : TO.can('categories.manage') ? 'manager' : TO.can('trips.create') ? 'dispatcher' : TO.can('trips.review') ? 'reviewer' : TO.can('trips.approve') ? 'approver'
      : TO.can('finance.view') ? 'finance' : 'viewer';
    return id;
  }
  function pathOf(id) { return PATHS.filter(function (p) { return p.id === id; })[0] || PATHS.filter(function (p) { return p.id === defaultPath(); })[0]; }
  function myPath() { return pathOf(learner().path || defaultPath()); }
  function guideOf(id) { return GUIDES.filter(function (g) { return g.id === id; })[0]; }
  // the lessons this person may do (a guide they have no right for is left out), each with done / here
  function lessons(p, f) {
    var doneGuides = learner().guidesDone || {}, out = [], here = -1;
    p.lessons.forEach(function (x) {
      var g = guideOf(x.guide); if (!g || !allowed(g)) return;
      var done = x.fact ? !!(f || {})[x.fact] : !!doneGuides[x.guide];
      if (!done && here < 0) here = out.length;
      out.push({ g: g, fact: x.fact, done: done });
    });
    if (here >= 0) out[here].here = true;
    return out;
  }
  function pathHTML(p, f) {
    var ls = lessons(p, f), n = ls.filter(function (x) { return x.done; }).length, cur = ls.filter(function (x) { return x.here; })[0];
    return '<section class="card path" data-path="' + p.id + '"><header class="row"><span class="tile-ic">' + TO.icon(p.icon) + '</span><div class="grow"><small class="faint">' + TO.esc(TO.t('path.title')) + '</small>' +
        '<h2>' + TO.esc(TO.t('path.' + p.id + '.t')) + '</h2><p class="muted">' + TO.esc(TO.t('path.' + p.id + '.d')) + '</p></div>' +
        '<span class="badge ' + (cur ? 'signal' : 'ok') + ' num">' + TO.esc(TO.t('path.progress', { n: n, m: ls.length })) + '</span></header>' +
      '<div class="meter big" aria-hidden="true"><i style="width:' + (ls.length ? Math.round(n * 100 / ls.length) : 100) + '%"></i></div>' +
      (cur ? '' : '<div class="tip ok">' + TO.icon('flag') + '<span>' + TO.esc(TO.t('path.complete')) + '</span></div>') +
      '<ol class="path-list">' + ls.map(function (x, k) {
        return '<li class="' + (x.done ? 'ok' : x.here ? 'here' : '') + '"' + (x.here ? ' aria-current="step"' : '') + '><span class="tick">' + (x.done ? TO.icon('check', 'sm') : '<b class="num">' + (k + 1) + '</b>') + '</span>' +
          '<div class="grow"><b>' + TO.esc(TO.t('gd.' + x.g.id + '.t')) + '</b>' + (x.here ? ' <span class="badge signal">' + TO.esc(TO.t('path.here')) + '</span>' : '') +
          '<small class="muted">' + TO.esc(TO.t('gd.' + x.g.id + '.d')) + '</small></div>' +
          '<button class="btn sm' + (x.here ? ' primary' : '') + '" data-guide="' + x.g.id + '">' + TO.icon('compass', 'sm') + TO.esc(TO.t(x.done ? 'path.again' : 'path.start')) + '</button></li>';
      }).join('') + '</ol>' +
      '<footer class="row wrap"><label class="field-inline"><span class="faint">' + TO.esc(TO.t('path.choose')) + '</span><select class="input" data-pathpick>' +
        PATHS.map(function (q) { return '<option value="' + q.id + '"' + (q.id === p.id ? ' selected' : '') + '>' + TO.esc(TO.t('path.' + q.id + '.t')) + '</option>'; }).join('') +
      '</select></label></footer></section>';
  }
  // the first page: one card with the next lesson, until the path is complete (it can be hidden)
  function nextCardHTML(p, f) {
    var ls = lessons(p, f), cur = ls.filter(function (x) { return x.here; })[0];
    if (!cur || learner().pathHidden) return '';
    var n = ls.filter(function (x) { return x.done; }).length, k = ls.indexOf(cur) + 1;
    return '<div class="row wrap path-next"><span class="tile-ic">' + TO.icon('compass') + '</span><div class="grow"><b>' + TO.esc(TO.t('path.continue')) + '</b>' +
      '<small class="muted">' + TO.esc(TO.t('path.next', { n: k, m: ls.length, lesson: TO.t('gd.' + cur.g.id + '.t') })) + '</small>' +
      '<div class="meter" aria-hidden="true"><i style="width:' + Math.round(n * 100 / ls.length) + '%"></i></div></div>' +
      '<button class="btn primary sm" data-guide="' + cur.g.id + '">' + TO.icon('compass', 'sm') + TO.esc(TO.t('guide.start')) + '</button>' +
      '<a class="btn sm" href="#/help?view=path">' + TO.esc(TO.t('path.all')) + '</a><button class="btn ghost sm" data-pathhide>' + TO.esc(TO.t('path.hide')) + '</button></div>';
  }
  document.addEventListener('change', function (e) {
    var pick = e.target.closest && e.target.closest('[data-pathpick]'); if (!pick) return;
    learner().path = pick.value; TO.prefs.save(); if (TO.rerender) TO.rerender();
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest || !e.target.closest('[data-pathhide]')) return;
    learner().pathHidden = true; TO.prefs.save(); var c = e.target.closest('[data-pathcard]'); if (c) c.innerHTML = '';
  });

  function demo() { return !!(TO.me && TO.me.demo); }   // demo mode: no sign-in, so no passwords or user accounts to learn about
  function allowed(g) { return !(g.account && demo()) && (!g.perm || TO.can(g.perm)); }
  function guideFor(sid) { var id = SIT_GUIDE[sid]; return GUIDES.filter(function (g) { return g.id === id && allowed(g); })[0]; }
  function label(key) { return TO.has(key) ? TO.t(key) : key; }
  // a step's text: escaped, with [[dictionary.key]] shown as «that label» in bold
  function rich(text) {
    return TO.esc(text).replace(/\[\[([a-zA-Z0-9_.-]+)\]\]/g, function (_, k) { return '<b class="ui-name">«' + TO.esc(label(k)) + '»</b>'; });
  }
  function stepText(g, n) { return TO.t('gd.' + g.id + '.' + n); }
  function pageOf(page) { return String(page || '').split('?')[0].split('/')[0]; }

  /* ---------- the coach: a docked card that walks through a guide ---------- */
  var C = { g: null, i: 0, hot: null, timer: null };
  function host() {
    var h = document.getElementById('coach');
    if (!h) { h = document.createElement('aside'); h.id = 'coach'; h.setAttribute('aria-live', 'polite'); document.body.appendChild(h); }
    return h;
  }
  function unhot() {
    clearInterval(C.timer); C.timer = null;
    if (C.hot) { C.hot.classList.remove('coach-hot'); C.hot = null; }
  }
  function findTarget(sel) {
    if (!sel) return null;
    var list = document.querySelectorAll(sel);
    for (var i = 0; i < list.length; i++) { var r = list[i].getBoundingClientRect(); if (r.width || r.height) return list[i]; }
    return null;
  }
  // outline the thing to press; pages draw some parts a moment later, so keep looking for a few seconds
  function point(s) {
    unhot();
    if (!s.sel) return;
    var tries = 0;
    function look() {
      var el = findTarget(s.sel);
      if (el) {
        clearInterval(C.timer); C.timer = null;
        C.hot = el; el.classList.add('coach-hot');
        if (el.scrollIntoView) el.scrollIntoView({ block: 'center', behavior: TO.motionOff() ? 'auto' : 'smooth' });
        var miss = document.querySelector('#coach [data-miss]'); if (miss) miss.hidden = true;
        return true;
      }
      if (++tries > 16) { clearInterval(C.timer); C.timer = null; var m = document.querySelector('#coach [data-miss]'); if (m) m.hidden = false; }
      return false;
    }
    if (!look()) C.timer = setInterval(look, 250);
  }
  function here(page) {
    if (!page) return true;
    var r = TO.route ? TO.route() : { path: '', q: {} }, want = page.split('?'), q = want[1] ? want[1].split('=') : null;
    return r.path === pageOf(page) && (!q || (r.q && r.q[q[0]] === q[1]));
  }
  function draw() {
    var g = C.g; if (!g) return;
    var s = g.steps[C.i], n = g.steps.length, h = host(), away = s.page && !here(s.page);
    h.className = 'on';
    h.innerHTML = '<div class="coach-card" role="dialog" aria-label="' + TO.esc(TO.t('gd.' + g.id + '.t')) + '">' +
      '<header><span class="tile-ic">' + TO.icon(g.icon) + '</span><div class="grow"><small class="faint">' + TO.esc(TO.t('guide.coach')) + '</small><b>' + TO.esc(TO.t('gd.' + g.id + '.t')) + '</b></div>' +
        '<button class="icon-btn" data-cx aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x', 'sm') + '</button></header>' +
      '<div class="coach-bar" aria-hidden="true"><i style="width:' + Math.round((C.i + 1) / n * 100) + '%"></i></div>' +
      '<p class="coach-n faint">' + TO.esc(TO.t('guide.stepOf', { n: C.i + 1, m: n })) + ' · ' + TO.esc(TO.t('guide.k.' + s.k)) + '</p>' +
      '<div class="coach-step k-' + s.k + '"><span class="step-ic">' + TO.icon(KINDS[s.k]) + '</span><p>' + rich(stepText(g, C.i + 1)) + '</p></div>' +
      (away ? '<button class="btn sm" data-cgo>' + TO.icon('route', 'sm') + TO.esc(TO.t('guide.take', { page: TO.t('nav.' + pageOf(s.page)) })) + '</button>' : '') +
      '<p class="faint coach-miss" data-miss hidden>' + TO.esc(TO.t('guide.miss')) + '</p>' +
      (C.i === n - 1 ? '<div class="tip ok">' + TO.icon('check') + '<span>' + rich(TO.t('gd.' + g.id + '.ok')) + '</span></div>' : '') +
      '<footer><button class="btn ghost sm" data-cprev' + (C.i ? '' : ' disabled') + '>' + TO.icon('left', 'sm mirror') + TO.esc(TO.t('common.back')) + '</button><span class="grow"></span>' +
        '<button class="btn primary sm" data-cnext>' + TO.esc(C.i === n - 1 ? TO.t('common.done') : TO.t('common.next')) + (C.i === n - 1 ? '' : TO.icon('right', 'sm mirror')) + '</button></footer></div>';
    if (!away) point(s); else unhot();
  }
  var coach = TO.coach = {
    start: function (id) {
      var g = guideOf(id); if (!g) return;
      C.g = g; C.i = 0;
      if (TO.overlay && TO.overlay.isOpen) TO.overlay.close();
      var first = g.steps[0];
      if (first.page && !here(first.page)) TO.go(first.page);
      setTimeout(draw, 60);
    },
    next: function () { if (!C.g) return; if (C.i >= C.g.steps.length - 1) { coach.stop(true); return; } C.i++; draw(); },
    prev: function () { if (C.g && C.i > 0) { C.i--; draw(); } },
    stop: function (finished) {
      var g = C.g; if (!g) return;
      unhot(); C.g = null;
      var h = document.getElementById('coach'); if (h) { h.className = ''; h.innerHTML = ''; }
      if (finished) { factsAt = 0; var done = learner().guidesDone || {}; done[g.id] = 1; learner().guidesDone = done; TO.prefs.save(); TO.toast(TO.t('guide.finished')); }
    },
    active: function () { return !!C.g; },
    step: function () { return C.g ? { guide: C.g.id, i: C.i } : null; }
  };
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('#coach [data-cx]')) { coach.stop(); return; }
    if (e.target.closest('#coach [data-cnext]')) { coach.next(); return; }
    if (e.target.closest('#coach [data-cprev]')) { coach.prev(); return; }
    if (e.target.closest('#coach [data-cgo]')) { var s = C.g.steps[C.i]; TO.go(s.page); return; }
    var start = e.target.closest('[data-guide]'); if (start) { e.preventDefault(); coach.start(start.dataset.guide); }
  });
  // the page changed (the person clicked, or the coach took them): redraw the card and look for the target again
  TO.on('route', function () { if (C.g) setTimeout(draw, 80); });
  TO.on('lang-changed', function () { if (C.g) setTimeout(draw, 80); });
  TO.on('logged-out', function () { coach.stop(); facts = null; });

  /* ---------- the guide library (Help page) ---------- */
  function guideCard(g) {
    var done = (learner().guidesDone || {})[g.id];
    var steps = g.steps.map(function (s, k) {
      return '<li class="k-' + s.k + '"><span class="step-ic" title="' + TO.esc(TO.t('guide.k.' + s.k)) + '">' + TO.icon(KINDS[s.k]) + '</span><span>' + rich(stepText(g, k + 1)) + '</span></li>'; }).join('');
    return '<details class="guide" id="guide-' + g.id + '" data-gid="' + g.id + '"><summary><span class="tile-ic">' + TO.icon(g.icon) + '</span><span class="grow"><b>' + TO.esc(TO.t('gd.' + g.id + '.t')) + '</b>' +
        '<small class="muted">' + TO.esc(TO.t('gd.' + g.id + '.d')) + '</small></span>' + (done ? '<span class="badge ok">' + TO.icon('check', 'sm') + TO.esc(TO.t('guide.done')) + '</span>' : '') +
        '<span class="badge desk-only">' + TO.esc(TO.t('guide.steps', { n: g.steps.length })) + '</span>' +
        '<button class="btn sm" data-guide="' + g.id + '" title="' + TO.esc(TO.t('guide.start')) + '">' + TO.icon('compass', 'sm') + '<span class="desk-only">' + TO.esc(TO.t('guide.start')) + '</span></button></summary>' +
      '<div class="guide-body"><ol class="guide-steps">' + steps + '</ol>' +
        '<div class="tip ok">' + TO.icon('check') + '<span><b>' + TO.esc(TO.t('guide.ok')) + '</b> ' + rich(TO.t('gd.' + g.id + '.ok')) + '</span></div>' +
        (TO.has('gd.' + g.id + '.x') ? '<div class="tip warn">' + TO.icon('alert') + '<span><b>' + TO.esc(TO.t('guide.x')) + '</b> ' + rich(TO.t('gd.' + g.id + '.x')) + '</span></div>' : '') +
        '<button class="btn primary" data-guide="' + g.id + '">' + TO.icon('compass', 'sm') + TO.esc(TO.t('guide.start')) + '</button></div></details>';
  }
  function situationHTML(x) {
    var g = guideFor(x[0]);
    return '<details class="situation" data-sid="' + x[0] + '" data-scat="' + x[2] + '"><summary>' + TO.icon('life', 'sm') + '<span class="grow">' + TO.esc(TO.t('sit.' + x[0] + '.q')) + '</span></summary>' +
      '<div class="guide-body"><p>' + rich(TO.t('sit.' + x[0] + '.a')) + '</p><div class="row wrap"><a class="btn sm" href="#/' + x[1] + '">' + TO.esc(TO.t('help.open')) + TO.icon('right', 'sm mirror') + '</a>' +
      (g ? '<button class="btn sm primary" data-guide="' + g.id + '">' + TO.icon('compass', 'sm') + TO.esc(TO.t('guide.start')) + '</button>' : '') + '</div></div></details>';
  }
  TO.guides = {
    list: GUIDES, situations: SITUATIONS, sitGuide: SIT_GUIDE, cats: CATS, kinds: KINDS, rich: rich, paths: PATHS, roles: ROLE_PATH,
    lessons: lessons, myPath: myPath, loadFacts: loadFacts, defaultPath: defaultPath,
    // the Help page's first view: my path, filled once the facts arrive
    pathShell: function () { return '<div data-pathfull><div class="skeleton" style="height:16rem"></div></div>'; },
    fillPath: function (root) {
      var box = root.querySelector('[data-pathfull]'); if (!box) return;
      loadFacts(true).then(function (f) { if (box.isConnected !== false) box.innerHTML = pathHTML(myPath(), f); });
    },
    // the overview card: next lesson of my path
    fillNext: function (root) {
      var box = root.querySelector('[data-pathcard]'); if (!box) return;
      loadFacts().then(function (f) { if (box.isConnected !== false) box.innerHTML = nextCardHTML(myPath(), f); });
    },
    pathHTML: pathHTML, nextCardHTML: nextCardHTML,
    // guides that act on this page first, then the rest; each category in its own block
    html: function (forPage) {
      var list = GUIDES.filter(allowed), mine = forPage ? list.filter(function (g) { return g.steps.some(function (s) { return pageOf(s.page) === forPage; }); }) : [];
      var done = learner().guidesDone || {}, count = list.filter(function (g) { return done[g.id]; }).length;
      return '<div class="guide-intro card"><div class="row wrap"><span class="tile-ic">' + TO.icon('compass') + '</span><div class="grow"><h2>' + TO.esc(TO.t('guide.title')) + '</h2><p class="muted">' + TO.esc(TO.t('guide.sub')) + '</p></div>' +
          '<span class="badge ' + (count === list.length ? 'ok' : '') + '">' + TO.esc(TO.t('guide.progress', { n: count, m: list.length })) + '</span></div>' +
          '<ul class="kind-legend">' + Object.keys(KINDS).map(function (k) { return '<li class="k-' + k + '"><span class="step-ic">' + TO.icon(KINDS[k]) + '</span>' + TO.esc(TO.t('guide.k.' + k)) + '</li>'; }).join('') + '</ul></div>' +
        (mine.length ? '<section class="guide-cat"><h3>' + TO.esc(TO.t('guide.here', { page: TO.t('nav.' + forPage) })) + '</h3>' + mine.map(guideCard).join('') + '</section>' : '') +
        CATS.map(function (c) {
          var gs = list.filter(function (g) { return g.cat === c && mine.indexOf(g) < 0; });
          return gs.length ? '<section class="guide-cat"><h3>' + TO.esc(TO.t('guide.cat.' + c)) + '</h3>' + gs.map(guideCard).join('') + '</section>' : '';
        }).join('');
    },
    situationsHTML: function () {
      return '<div class="guide-intro card"><div class="row wrap"><span class="tile-ic">' + TO.icon('life') + '</span><div class="grow"><h2>' + TO.esc(TO.t('sit.title')) + '</h2><p class="muted">' + TO.esc(TO.t('sit.sub')) + '</p></div></div></div>' +
        CATS.filter(function (c) { return c !== 'start'; }).map(function (c) {
          var xs = SITUATIONS.filter(function (x) { return x[2] === c && !(demo() && x[1] === 'settings?tab=access'); });
          return xs.length ? '<section class="guide-cat"><h3>' + TO.esc(TO.t('sit.cat.' + c)) + '</h3>' + xs.map(situationHTML).join('') + '</section>' : '';
        }).join('');
    }
  };
})();
