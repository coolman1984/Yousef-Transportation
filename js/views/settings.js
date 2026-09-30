/* Trip Orders - Settings. Phase 1 ships the Appearance tab (language, theme, font, size, density, animations) with a live preview. */
(function () {
  'use strict';
  var TO = window.TO;
  var THEMES = {
    auto: null,
    daylight: ['#13294b', '#e8edf4', '#ffffff', '#f2a900'], night: ['#0d1524', '#0a1120', '#121a2c', '#ffc23d'], asphalt: ['#101010', '#161616', '#202020', '#ffc23d'],
    highway: ['#0b3d2e', '#e4eee9', '#ffffff', '#f2a900'], contrast: ['#000000', '#f2f2f2', '#ffffff', '#ffd000']
  };
  var FONTS = { plex: "'TO Plex Arabic','TO Plex'", cairo: "'TO Cairo'", tajawal: "'TO Tajawal'", kufi: "'TO Kufi'", system: "'Segoe UI',Tahoma,sans-serif" };
  var TABS = ['appearance', 'organisation', 'rules', 'money', 'gateway', 'access', 'data'];

  function sw(colors) {
    if (!colors) return '<div class="sw" style="grid-template-columns:1fr 1fr"><i style="background:linear-gradient(90deg,#13294b 0 30%,#e8edf4 30% 100%)"></i><i style="background:linear-gradient(90deg,#0d1524 0 30%,#0a1120 30% 100%)"></i></div>';
    return '<div class="sw"><i style="background:' + colors[0] + '"></i><b style="background:' + colors[1] + '"><em style="background:' + colors[2] + ';height:.9rem"></em><em style="background:' + colors[3] + ';width:60%"></em></b></div>';
  }
  function seg(key, values, labelKey, current) {
    return '<div class="seg" role="group">' + values.map(function (v) {
      return '<button type="button" data-pref="' + key + '" data-v="' + v + '" aria-pressed="' + (String(current) === v) + '">' + TO.esc(TO.t(labelKey + v)) + '</button>';
    }).join('') + '</div>';
  }
  function block(title, help, body) {
    return '<div class="field" style="padding-block:1.1rem;border-bottom:1px solid var(--line-2)"><label>' + TO.esc(title) + '</label><span class="help">' + TO.esc(help) + '</span><div style="margin-top:.5rem">' + body + '</div></div>';
  }
  function appearance() {
    var d = TO.prefs.data;
    var themes = '<div class="swatches">' + Object.keys(THEMES).map(function (k) {
      return '<button type="button" class="swatch" data-pref="theme" data-v="' + k + '" aria-pressed="' + (d.theme === k) + '">' + sw(THEMES[k]) + '<small>' + TO.esc(TO.t('ap.theme.' + k)) + '</small></button>';
    }).join('') + '</div>';
    var fonts = '<div class="swatches">' + Object.keys(FONTS).map(function (k) {
      return '<button type="button" class="swatch" data-pref="font" data-v="' + k + '" aria-pressed="' + (d.font === k) + '" style="width:8.6rem"><div style="font-family:' + FONTS[k] + ';font-size:1.5rem;padding:.4rem .2rem;line-height:1.1">أبجد Abc<br><span style="font-size:.95rem">١٢٣ 123</span></div><small>' + TO.esc(TO.t('ap.font.' + k)) + '</small></button>';
    }).join('') + '</div>';
    return block(TO.t('ap.language'), TO.t('ap.language.d'), '<div class="seg" role="group"><button type="button" data-pref="lang" data-v="ar" aria-pressed="' + (d.lang === 'ar') + '">العربية</button><button type="button" data-pref="lang" data-v="en" aria-pressed="' + (d.lang === 'en') + '">English</button></div>') +
      block(TO.t('ap.theme'), TO.t('ap.theme.d'), themes) +
      block(TO.t('ap.font'), TO.t('ap.font.d'), fonts) +
      block(TO.t('ap.size'), TO.t('ap.size.d'), seg('size', ['s', 'm', 'l', 'xl'], 'ap.size.', d.size)) +
      block(TO.t('ap.density'), TO.t('ap.density.d'), seg('density', ['comfortable', 'compact'], 'ap.density.', d.density)) +
      block(TO.t('ap.motion'), TO.t('ap.motion.d'), seg('motion', ['auto', 'on', 'off'], 'ap.motion.', d.motion)) +
      '<div class="row" style="padding-top:1rem"><button class="btn" data-reset>' + TO.icon('refresh', 'sm') + TO.esc(TO.t('ap.reset')) + '</button><span class="faint">' + TO.esc(TO.t('ap.saved.local')) + '</span></div>';
  }
  function preview() {
    return '<aside class="card" style="position:sticky;top:calc(var(--topbar-h) + 1rem)"><header><h3>' + TO.esc(TO.t('ap.preview')) + '</h3></header>' +
      '<div class="preview-box"><div class="row"><b>' + TO.esc(TO.t('ap.preview.title')) + ' <span class="num">26-A-00233</span></b><span class="grow"></span><span class="badge ok"><i class="trust green"></i>' + TO.esc(TO.t('ap.preview.status')) + '</span></div>' +
      '<div class="muted">' + TO.esc(TO.t('ap.preview.body')) + '</div>' +
      '<div class="row"><span class="plate"><b>ط و ي</b><i>6829</i></span><span class="grow"></span><span class="muted">' + TO.esc(TO.t('ap.preview.km')) + '</span><b class="num">291,382 → 291,747</b></div>' +
      '<div class="row wrap"><button class="btn primary sm" type="button">' + TO.icon('chat', 'sm') + TO.esc(TO.t('common.save')) + '</button><button class="btn sm" type="button">' + TO.esc(TO.t('common.cancel')) + '</button><span class="badge warn">' + TO.esc(TO.t('ov.trust.yellow')) + '</span><span class="badge bad">' + TO.esc(TO.t('ov.trust.red')) + '</span></div></div></aside>';
  }
  function later(tab) {
    return '<div class="empty"><div class="art">' + TO.icon('lock', 'lg') + '</div><h3>' + TO.esc(TO.t('set.tab.' + tab)) + '</h3><p>' + TO.esc(TO.t('set.later')) + ' · ' + TO.esc(TO.t('set.admin.only')) + '</p></div>';
  }

  TO.views.settings = {
    render: function (ctx) {
      var tab = TABS.indexOf(ctx.route.q.tab) >= 0 ? ctx.route.q.tab : 'appearance';
      var tabs = '<div class="seg" role="tablist" style="max-width:100%;overflow:auto">' + TABS.map(function (t) {
        return '<button type="button" role="tab" data-tab="' + t + '" aria-pressed="' + (t === tab) + '">' + TO.esc(TO.t('set.tab.' + t)) + '</button>';
      }).join('') + '</div>';
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('set.title')) + '</h1><p>' + TO.esc(TO.t('set.sub')) + '</p></div></div>' +
        '<div class="toolbar">' + tabs + '</div>' +
        (tab === 'appearance' ? '<div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(16rem,22rem);align-items:start"><section class="card">' + appearance() + '</section>' + preview() + '</div>'
          : '<section class="card">' + later(tab) + '</section>');
    },
    mount: function (root, ctx) {
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
