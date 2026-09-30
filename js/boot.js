/* Trip Orders - runs before the first paint: applies the saved appearance (theme, font, size, density, language) so
   the page never flashes in the wrong colours. Must stay small and dependency-free (the server allows no inline scripts). */
(function () {
  'use strict';
  var p = {};
  try { p = JSON.parse(localStorage.getItem('to.prefs') || '{}') || {}; } catch (e) { p = {}; }
  var h = document.documentElement;
  var theme = p.theme || 'auto';
  if (theme === 'auto') theme = (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches) ? 'night' : 'daylight';
  var lang = p.lang === 'en' ? 'en' : 'ar';
  h.dataset.theme = theme;
  h.dataset.font = p.font || 'plex';
  h.dataset.size = p.size || 'm';
  h.dataset.density = p.density || 'comfortable';
  if (p.motion === 'off' || p.motion === 'on') h.dataset.motion = p.motion;
  h.lang = lang;
  h.dir = lang === 'ar' ? 'rtl' : 'ltr';
})();
