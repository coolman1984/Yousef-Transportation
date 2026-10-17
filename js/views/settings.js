/* Trip Orders - Settings. Phase 1 ships the Appearance tab (language, theme, font, size, density, animations) with a live preview. */
(function () {
  'use strict';
  var TO = window.TO;
  var THEMES = ['auto', 'daylight', 'night', 'asphalt', 'highway', 'contrast'];   // their sample colours live in css/tokens.css (.sw[data-sample])
  var FONTS = ['plex', 'cairo', 'tajawal', 'kufi', 'system'];                       // the font of each sample is set by [data-font-sample] in css/base.css
  var ALL_TABS = ['appearance', 'rules', 'gateway', 'access', 'data', 'privacy'];   // the organisation and money tabs are not built yet and are not shown (N1)
  // demo mode has no sign-in, so there are no user accounts to manage
  function tabs() { return ALL_TABS.filter(function (t) { return !(t === 'access' && TO.me && TO.me.demo); }); }

  function sw(name) {
    return '<div class="sw" data-sample="' + name + '"><i></i><b><em></em><em></em></b></div>';
  }
  function seg(key, values, labelKey, current) {
    return '<div class="seg" role="group">' + values.map(function (v) {
      return '<button type="button" data-pref="' + key + '" data-v="' + v + '" aria-pressed="' + (String(current) === v) + '">' + TO.esc(TO.t(labelKey + v)) + '</button>';
    }).join('') + '</div>';
  }
  function block(title, help, body) {
    return '<div class="field set-block"><label>' + TO.esc(title) + '</label><span class="help">' + TO.esc(help) + '</span><div class="set-block-body">' + body + '</div></div>';
  }
  function appearance() {
    var d = TO.prefs.data;
    var themes = '<div class="swatches">' + THEMES.map(function (k) {
      return '<button type="button" class="swatch" data-pref="theme" data-v="' + k + '" aria-pressed="' + (d.theme === k) + '">' + sw(k) + '<small>' + TO.esc(TO.t('ap.theme.' + k)) + '</small></button>';
    }).join('') + '</div>';
    var fonts = '<div class="swatches">' + FONTS.map(function (k) {
      return '<button type="button" class="swatch swatch-font" data-pref="font" data-v="' + k + '" aria-pressed="' + (d.font === k) + '"><div class="font-sample" data-font-sample="' + k + '">أبجد Abc<br><span>١٢٣ 123</span></div><small>' + TO.esc(TO.t('ap.font.' + k)) + '</small></button>';
    }).join('') + '</div>';
    return block(TO.t('ap.language'), TO.t('ap.language.d'), '<div class="seg" role="group"><button type="button" data-pref="lang" data-v="ar" aria-pressed="' + (d.lang === 'ar') + '">العربية</button><button type="button" data-pref="lang" data-v="en" aria-pressed="' + (d.lang === 'en') + '">English</button></div>') +
      block(TO.t('ap.theme'), TO.t('ap.theme.d'), themes) +
      block(TO.t('ap.font'), TO.t('ap.font.d'), fonts) +
      block(TO.t('ap.size'), TO.t('ap.size.d'), seg('size', ['s', 'm', 'l', 'xl'], 'ap.size.', d.size)) +
      block(TO.t('ap.density'), TO.t('ap.density.d'), seg('density', ['comfortable', 'compact'], 'ap.density.', d.density)) +
      block(TO.t('ap.motion'), TO.t('ap.motion.d'), seg('motion', ['auto', 'on', 'off'], 'ap.motion.', d.motion)) +
      '<div class="row set-reset"><button class="btn" data-reset>' + TO.icon('refresh', 'sm') + TO.esc(TO.t('ap.reset')) + '</button><span class="faint">' + TO.esc(TO.t('ap.saved.local')) + '</span></div>';
  }
  function preview() {
    return '<aside class="card sticky-card"><header><h3>' + TO.esc(TO.t('ap.preview')) + '</h3></header>' +
      '<div class="preview-box"><div class="row wrap"><b>' + TO.esc(TO.t('ap.preview.title')) + ' <span class="num">26-A-00233</span></b><span class="grow"></span><span class="badge ok"><i class="trust green"></i>' + TO.esc(TO.t('ap.preview.status')) + '</span></div>' +
      '<div class="muted">' + TO.esc(TO.t('ap.preview.body')) + '</div>' +
      '<div class="row wrap"><span class="plate"><b>ط و ي</b><i>6829</i></span><span class="grow"></span><span class="muted">' + TO.esc(TO.t('ap.preview.km')) + '</span><b class="num">291,382 → 291,747</b></div>' +
      '<div class="row wrap"><button class="btn primary sm" type="button">' + TO.icon('chat', 'sm') + TO.esc(TO.t('common.save')) + '</button><button class="btn sm" type="button">' + TO.esc(TO.t('common.cancel')) + '</button><span class="badge warn">' + TO.esc(TO.t('ov.trust.yellow')) + '</span><span class="badge bad">' + TO.esc(TO.t('ov.trust.red')) + '</span></div></div></aside>';
  }

  TO.views.settings = {
    render: function (ctx) {
      var TABS = tabs(), tab = TABS.indexOf(ctx.route.q.tab) >= 0 ? ctx.route.q.tab : 'appearance';
      var bar = '<div class="seg seg-scroll" role="group" data-lab-scroll aria-label="' + TO.esc(TO.t('set.title')) + '">' + TABS.map(function (t) {
        return '<button type="button" data-tab="' + t + '" aria-pressed="' + (t === tab) + '">' + TO.esc(TO.t('set.tab.' + t)) + '</button>';
      }).join('') + '</div>';
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('set.title')) + '</h1><p>' + TO.esc(TO.t('set.sub')) + '</p></div></div>' +
        '<div class="toolbar">' + bar + '</div>' +
        (tab === 'appearance' ? '<div class="grid two-col"><section class="card">' + appearance() + '</section>' + preview() + '</div>'
          : tab === 'access' ? TO.accessTab.render()
          : tab === 'data' ? TO.dataTab.render()
          : tab === 'gateway' ? TO.mailboxTab.render()
          : tab === 'privacy' ? TO.privacyTab.render()
          : tab === 'rules' ? (TO.data.state ? '<h2 class="set-h2">' + TO.esc(TO.t('set.cats')) + '</h2>' + TO.listPage(TO.lists.tripCategories) : '<div class="skeleton skeleton-block"></div>')
          : '');
    },
    mount: function (root, ctx) {
      if (ctx.route.q.tab === 'data') TO.dataTab.mount(root);
      if (ctx.route.q.tab === 'gateway') TO.mailboxTab.mount(root);
      if (ctx.route.q.tab === 'privacy') TO.privacyTab.mount(root);
      if (ctx.route.q.tab === 'access' && tabs().indexOf('access') >= 0) {
        (TO.data.state ? Promise.resolve() : TO.data.load()).then(function () { TO.accessTab.mount(root); });
      }
      if (ctx.route.q.tab === 'rules') { if (!TO.data.state) { TO.data.load().then(function () { TO.rerender(); }); return; } TO.mountList(root, TO.lists.tripCategories); }
      root.addEventListener('click', function (e) {
        var b = e.target.closest('[data-pref]');
        if (b) { var v = b.dataset.v; TO.prefs.set(b.dataset.pref, v); if (b.dataset.pref !== 'lang') TO.rerender(); return; }
        var t = e.target.closest('[data-tab]');
        if (t) { TO.go('settings?tab=' + t.dataset.tab); return; }
        if (e.target.closest('[data-reset]')) { TO.prefs.reset(); TO.rerender(); }
      });
    }
  };
})();
