/* Trip Orders - appearance preferences (language, theme, font, size, density, animations, menu state).
   Stored on this device; js/boot.js applies them before the first paint. */
(function () {
  'use strict';
  var TO = window.TO;
  var DEFAULTS = { lang: 'ar', theme: 'auto', font: 'plex', size: 'm', density: 'comfortable', motion: 'auto', collapsed: false, tours: {}, welcomed: false };
  var KEY = 'to.prefs';
  var P = TO.prefs = { data: {} };

  P.load = function () {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }
    P.data = Object.assign({}, DEFAULTS, saved);
    return P.data;
  };
  P.save = function () {
    try { localStorage.setItem(KEY, JSON.stringify(P.data)); } catch (e) { /* private window: settings just are not remembered */ }
  };
  P.resolvedTheme = function () {
    if (P.data.theme !== 'auto') return P.data.theme;
    return (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches) ? 'night' : 'daylight';
  };
  P.isDark = function () { return ['night', 'asphalt'].indexOf(P.resolvedTheme()) >= 0; };
  P.apply = function () {
    var h = document.documentElement, d = P.data;
    h.dataset.theme = P.resolvedTheme();
    h.dataset.font = d.font;
    h.dataset.size = d.size;
    h.dataset.density = d.density;
    if (d.motion === 'auto') delete h.dataset.motion; else h.dataset.motion = d.motion;
    if (TO.lang !== d.lang) TO.setLang(d.lang);
    TO.emit('prefs-applied', d);
  };
  P.set = function (key, value) {
    P.data[key] = value;
    P.save();
    P.apply();
  };
  P.reset = function () {
    var keep = { tours: P.data.tours, welcomed: P.data.welcomed, collapsed: P.data.collapsed };
    P.data = Object.assign({}, DEFAULTS, keep);
    P.save();
    P.apply();
  };
  P.toggleTheme = function () { P.set('theme', P.isDark() ? 'daylight' : 'night'); };
  P.toggleLang = function () { P.set('lang', TO.lang === 'ar' ? 'en' : 'ar'); };

  if (window.matchMedia) {
    var mq = matchMedia('(prefers-color-scheme: dark)');
    var follow = function () { if (P.data.theme === 'auto') P.apply(); };
    if (mq.addEventListener) mq.addEventListener('change', follow); else if (mq.addListener) mq.addListener(follow);
  }
  P.load();
})();
