/* Trip Orders - Help & guide. Four ways in (owner 2026-10-09: a new person learns alone, in order):
   1. "Your path" (default): the ordered lessons of my role, with "You are here" and Start (js/views/guides.js);
   2. "Step-by-step guides": every daily job, each with "Guide me";
   3. "Solve a problem": real situations of a transport office, each with "Take me there" and "Guide me";
   4. "Questions": short answers with a search, plus the tour and the welcome slides. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var N = 9;   // help.q1..q9 / help.a1..a9
  var VIEWS = ['path', 'guides', 'situations', 'faq'];
  var VIEW_ICON = { path: 'flag', guides: 'compass', situations: 'life', faq: 'help' };

  function faqHTML(q) {
    var items = [];
    for (var i = 1; i <= N; i++) items.push('<details data-i="' + i + '"><summary>' + TO.esc(TO.t('help.q' + i)) + '</summary><p>' + TO.esc(TO.t('help.a' + i)) + '</p></details>');
    return '<div class="toolbar"><input class="input" id="help-q" type="search" placeholder="' + TO.esc(TO.t('help.search')) + '" style="max-width:32rem" aria-label="' + TO.esc(TO.t('help.search')) + '" value="' + TO.esc(q || '') + '"></div>' +
      '<div class="faq" id="faq">' + items.join('') + '</div><div class="empty" id="faq-none" hidden><div class="art">' + TO.icon('search', 'lg') + '</div><p>' + TO.esc(TO.t('help.none')) + '</p></div>';
  }

  TO.views.help = {
    render: function (ctx) {
      var q = (ctx && ctx.route && ctx.route.q) || {};
      var view = VIEWS.indexOf(q.view) >= 0 ? q.view : (q.q ? 'faq' : 'path');
      var seg = '<div class="seg help-views" role="tablist">' + VIEWS.map(function (v) {
        return '<button type="button" role="tab" data-hview="' + v + '" aria-pressed="' + (v === view) + '">' + TO.icon(VIEW_ICON[v], 'sm') + TO.esc(TO.t('help.view.' + v)) + '</button>'; }).join('') + '</div>';
      var head = '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('help.title')) + '</h1><p>' + TO.esc(TO.t('help.sub')) + '</p></div>' +
        '<button class="btn" data-a="tour">' + TO.icon('play', 'sm') + TO.esc(TO.t('help.tour.start')) + '</button>' +
        (TO.can('vehicles.manage') || TO.can('drivers.manage') ? '<button class="btn" data-a="fleet-tour">' + TO.icon('sheet', 'sm') + TO.esc(TO.t('help.tour.fleet')) + '</button>' : '') +
        '<button class="btn" data-a="slides">' + TO.icon('present', 'sm') + TO.esc(TO.t('help.slides.start')) + '</button></div>' + seg;
      if (view === 'path') return head + '<div class="stack">' + TO.guides.pathShell() + '</div>';
      if (view === 'guides') return head + '<div class="stack">' + TO.guides.html(q.for || '') + '</div>';
      if (view === 'situations') return head + '<div class="stack">' + TO.guides.situationsHTML() + '</div>';
      return head + faqHTML(q.q);
    },
    mount: function (root, ctx) {
      var q = (ctx && ctx.route && ctx.route.q) || {};
      root.addEventListener('click', function (e) {
        var v = e.target.closest('[data-hview]'); if (v) { TO.go('help?view=' + v.dataset.hview); return; }
        if (e.target.closest('[data-a="tour"]')) { TO.go('overview'); setTimeout(TO.tour.start, 350); return; }
        if (e.target.closest('[data-a="fleet-tour"]')) { TO.tour.start('fleet'); return; }
        if (e.target.closest('[data-a="slides"]')) TO.slides.open();
      });
      TO.guides.fillPath(root);
      var g = q.guide && document.getElementById('guide-' + q.guide);   // an id from the address: never a CSS selector
      if (g) { g.open = true; setTimeout(function () { if (g.scrollIntoView) g.scrollIntoView({ block: 'start' }); }, 50); }
      var input = root.querySelector('#help-q');
      if (!input) return;
      function filter() {
        var n = U.key(input.value), shown = 0;   // U.key: أ/ا, ة/ه, ى/ي and Arabic digits match their plain forms
        TO.$$('#faq details', root).forEach(function (d) {
          var hit = !n || U.key(d.textContent).indexOf(n) >= 0;
          d.hidden = !hit; if (hit) { shown++; if (n) d.open = true; }
        });
        root.querySelector('#faq-none').hidden = shown > 0;
      }
      input.addEventListener('input', TO.debounce(filter, 100));
      if (input.value) filter();
    }
  };
})();
