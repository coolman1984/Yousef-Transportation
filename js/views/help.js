/* Trip Orders - Help & guide: searchable questions and answers, tour and slides. */
(function () {
  'use strict';
  var TO = window.TO;
  var N = 8;
  TO.views.help = {
    render: function () {
      var items = [];
      for (var i = 1; i <= N; i++) items.push('<details data-i="' + i + '"><summary>' + TO.esc(TO.t('help.q' + i)) + '</summary><p>' + TO.esc(TO.t('help.a' + i)) + '</p></details>');
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('help.title')) + '</h1><p>' + TO.esc(TO.t('help.sub')) + '</p></div>' +
        '<button class="btn" data-a="tour">' + TO.icon('play', 'sm') + TO.esc(TO.t('help.tour.start')) + '</button>' +
        '<button class="btn" data-a="slides">' + TO.icon('present', 'sm') + TO.esc(TO.t('help.slides.start')) + '</button></div>' +
        '<div class="toolbar"><input class="input" id="help-q" type="search" placeholder="' + TO.esc(TO.t('help.search')) + '" style="max-width:32rem" aria-label="' + TO.esc(TO.t('help.search')) + '"></div>' +
        '<div class="faq" id="faq">' + items.join('') + '</div><div class="empty" id="faq-none" hidden><div class="art">' + TO.icon('search', 'lg') + '</div><p>' + TO.esc(TO.t('help.none')) + '</p></div>';
    },
    mount: function (root) {
      root.querySelector('[data-a="tour"]').addEventListener('click', function () { TO.go('overview'); setTimeout(TO.tour.start, 350); });
      root.querySelector('[data-a="slides"]').addEventListener('click', function () { TO.slides.open(); });
      var q = root.querySelector('#help-q');
      q.addEventListener('input', function () {
        var n = q.value.trim().toLowerCase(), shown = 0;
        TO.$$('#faq details', root).forEach(function (d) {
          var hit = !n || d.textContent.toLowerCase().indexOf(n) >= 0;
          d.hidden = !hit; if (hit) shown++;
        });
        root.querySelector('#faq-none').hidden = shown > 0;
      });
    }
  };
})();
