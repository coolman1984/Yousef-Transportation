/* Trip Orders - translations (English + Arabic), number/date formatting.
   Every visible word comes from js/i18n/en.js and js/i18n/ar.js through TO.t('key'). Missing keys fall back to English. */
(function () {
  'use strict';
  var TO = window.TO;
  TO.lang = document.documentElement.lang === 'en' ? 'en' : 'ar';

  TO.t = function (key, vars) {
    var d = TO.dict[TO.lang] || {};
    var s = d[key];
    if (s === undefined) s = (TO.dict.en || {})[key];
    if (s === undefined) return key;
    if (vars) s = s.replace(/\{(\w+)\}/g, function (m, n) { var v = vars[n]; return v === undefined ? m : (v && v.html !== undefined ? v.html : TO.esc(v)); });
    return s;
  };
  TO.has = function (key) { return ((TO.dict[TO.lang] || {})[key] !== undefined) || ((TO.dict.en || {})[key] !== undefined); };

  TO.setLang = function (lang) {
    TO.lang = lang === 'en' ? 'en' : 'ar';
    var h = document.documentElement;
    h.lang = TO.lang;
    h.dir = TO.lang === 'ar' ? 'rtl' : 'ltr';
    document.title = TO.t('app.name');
    TO.emit('lang-changed', TO.lang);
  };

  /* Western digits in both languages (km, times and plates read the same everywhere). */
  var nf = new Intl.NumberFormat('en-US');
  TO.fmt = {
    num: function (n) { return nf.format(Number(n) || 0); },
    pad: function (n) { return String(n).padStart(2, '0'); },
    date: function (d) {
      d = d instanceof Date ? d : new Date(d);
      if (isNaN(d)) return '';
      return TO.fmt.pad(d.getDate()) + '/' + TO.fmt.pad(d.getMonth() + 1) + '/' + d.getFullYear();
    },
    time: function (d) {
      d = d instanceof Date ? d : new Date(d);
      if (isNaN(d)) return '';
      return TO.fmt.pad(d.getHours()) + ':' + TO.fmt.pad(d.getMinutes());
    },
    dayName: function (d) {
      return new Intl.DateTimeFormat(TO.lang === 'ar' ? 'ar-EG-u-nu-latn' : 'en-GB', { weekday: 'long' }).format(d || new Date());
    },
    longDate: function (d) {
      return new Intl.DateTimeFormat(TO.lang === 'ar' ? 'ar-EG-u-nu-latn' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(d || new Date());
    }
  };
})();
