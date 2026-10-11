/* Trip Orders - the role-based guide, the first-sign-in consent card, consented usage counts, error reports and the problem report.
   The factory files in js/vendor/ (af-guide, af-consent, af-telemetry) are not edited; this file only connects them to the program.
   The browser never talks to the vendor: everything goes to this program's own server (/api/guide, /api/consent, /api/telemetry). */
(function () {
  'use strict';
  var TO = window.TO;
  var files = null, ctl = null, tel = null, allowed = false, generation = 0, live = false, listeners = [];

  function loadFiles() {
    if (!files) {
      files = Promise.all(['catalogue', 'ar', 'en'].map(function (n) {
        return fetch('/guide/' + n + '.json', { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error('guide'); return r.json(); });
      })).then(function (a) { return { catalogue: a[0], ar: a[1], en: a[2] }; }, function (e) { files = null; throw e; });
    }
    return files;
  }
  function request(method, url, body) { return method === 'GET' ? TO.get(url) : TO.post(url, body); }

  /* ---- usage counts and error fingerprints: only after both agreements; the server decides again ---- */
  function startTelemetry() {
    if (tel || !window.AFTelemetry) return tel;
    tel = window.AFTelemetry.init({
      lang: TO.lang,
      page: function () { return live ? TO.route().path : 'signin'; },
      request: function (method, url, body) {
        if (url.indexOf('/events') >= 0 && (!allowed || !live)) return Promise.resolve({ queued: 0 });   // nothing is even sent to our own server without consent
        return request(method, url, body);
      }
    });
    return tel;
  }
  function track(type, data) { if (tel && allowed && live) tel.track(type, data); }
  function refreshConsent() {
    allowed = false;
    if (!live) return Promise.resolve(false);
    return TO.get('/api/consent/status').then(function (s) { allowed = !!s.tracking; return allowed; }, function () { return false; });
  }

  /* ---- the problem report: every page, with the exact preview; works without tracking consent ---- */
  function report(ctx) {
    if (!window.AFTelemetry || !live) return;
    // a dialog in the screen's language; its own timers and listeners are switched off, only the report calls reach the server
    var once = window.AFTelemetry.init({
      lang: TO.lang,
      page: function () { return TO.route().path; },
      request: function (method, url, body) {
        if (url.indexOf('/events') >= 0) return Promise.resolve({ queued: 0 });
        return request(method, url, body).then(function (r) {
          if (url.indexOf('/feedback') >= 0 && url.indexOf('/preview') < 0) {
            TO.toast(TO.t(r && r.sending ? 'report.queued' : 'report.saved'), 'ok', 6000);
            TO.emit('report-sent', r);
          }
          return r;
        });
      }
    });
    once.stop();
    var dlg = once.report(Object.assign({ page: TO.route().path }, ctx || {}));
    if (dlg && dlg.setAttribute) dlg.setAttribute('data-guide-dialog', 'report');
    return dlg;
  }

  /* ---- the first-sign-in consent card: two equal buttons, Esc does not decide ---- */
  function maybeConsent() {
    if (!live || !window.AFConsent) return Promise.resolve(null);
    var gen = generation;
    return TO.get('/api/consent/prompt?lang=' + TO.lang).then(function (p) {
      if (gen !== generation || !p || !p.ask || document.querySelector('[data-afc="card"]')) return null;
      return window.AFConsent.ask(p, function (decision) {
        return TO.post('/api/consent/decide', { decision: decision, text_id: p.text_id, lang: p.lang, scope: p.scope }).then(function () {
          return refreshConsent().then(function () { return TO.guide.refreshStates(); });
        }, function (e) { TO.toast(e.message, 'bad', 6000); return new Promise(function () { /* the card stays: the person decides again */ }); });
      });
    }, function () { return null; });
  }

  function attachHelp() {
    if (!ctl) return;
    TO.$$('[data-guide-slot]').forEach(function (slot) { if (!slot.firstChild) slot.appendChild(ctl.helpButton()); });
  }

  function unmount() {
    generation++;
    live = false; allowed = false;
    if (ctl) { try { ctl.stop(); } catch (e) { /* already gone */ } }
    listeners.forEach(function (l) { l[0].removeEventListener(l[1], l[2], l[3]); });
    listeners = [];
    TO.$$('[data-afg]').forEach(function (n) { n.remove(); });
    TO.$$('[data-afc="card"], [data-aft="dialog"]').forEach(function (n) { n.remove(); });
    ctl = null;
  }

  function mount() {
    unmount();
    var gen = generation;
    live = true;
    startTelemetry();
    return Promise.all([loadFiles(), TO.get('/api/guide/state')]).then(function (r) {
      if (gen !== generation || !window.AFGuide || !TO.me) return null;
      var pack = r[0], st = r[1];
      // the factory exposes stop() but no destroy(): remember its two global listeners so a new sign-in leaves nothing of the old person behind
      var targets = [document, window], originals = targets.map(function (t) { return t.addEventListener; });
      try {
        targets.forEach(function (t, i) {
          t.addEventListener = function (type, fn, opts) { listeners.push([t, type, fn, opts]); originals[i].call(t, type, fn, opts); };
        });
        ctl = window.AFGuide.init({
          catalogue: pack.catalogue, texts: { ar: pack.ar, en: pack.en }, role: st.role, person: TO.me.id,
          ui: function (key, lang) { var d = TO.dict[lang] || {}; return d[key] !== undefined ? d[key] : (TO.dict.en || {})[key]; },
          uiLang: function () { return TO.lang; },
          route: function () { return TO.route().path; },
          go: function (page) { TO.go(page); },
          can: function (perm) { return TO.can(perm); },
          track: track, onReport: report, request: request, api: '/api/guide'
        });
      } finally { targets.forEach(function (t, i) { t.addEventListener = originals[i]; }); }
      attachHelp();
      return ctl.ready.then(function () { return refreshConsent(); }).then(maybeConsent);
    }, function () { return null; });
  }

  TO.guide = {
    mount: mount, unmount: unmount, report: report, refreshConsent: refreshConsent, maybeConsent: maybeConsent, attachHelp: attachHelp,
    open: function (page) { if (ctl) ctl.open(page); },
    control: function () { return ctl; },
    /* the server confirmed an action: move the coach on, then refresh the lessons the data itself has already finished */
    signal: function (name) {
      if (!ctl) return;
      ctl.signal(name);
      TO.guide.refreshStates();
    },
    refreshStates: function () {
      if (!ctl || !live) return Promise.resolve();
      return TO.get('/api/guide/state').then(function (st) { if (ctl && Array.isArray(st.states)) ctl.setStates(st.states); }, function () { /* the coach already moved on the event */ });
    },
    /* an error answer with a problem entry gets a «What do I do?» button (HELP-09) */
    explain: function (err) {
      var code = err && err.data && err.data.key;
      return !!(ctl && code && ctl.explain(code));
    },
    errorButton: function (err) { var code = err && err.data && err.data.key; return ctl && code ? ctl.errorButton(code) : null; }
  };
  TO.on('route', function () { if (ctl) { ctl.routeChanged(); attachHelp(); } if (tel && allowed && live) track('use.page', { page: TO.route().path }); });
  TO.on('lang-changed', function () { if (ctl) setTimeout(attachHelp, 0); });
})();
