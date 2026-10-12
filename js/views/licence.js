/* Trip Orders - Settings -> Licence: the state of the licence, the device code for the manual way, a box for a pasted code, and asking the
   company from this screen (online activation through the factory hub). Without a working code everything can still be read, printed,
   exported and backed up; only changes to the business data wait. */
(function () {
  'use strict';
  var TO = window.TO;

  function banner() {
    var host = TO.$('#lic-banner');
    if (!host) return;
    var lic = TO.me && TO.me.licence;
    var ciWarning = lic && lic.build_channel === 'ci-test' ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<b>' + TO.esc(TO.t('lic.ciTest')) + '</b></div>' : '';
    if (!lic || lic.full) { host.innerHTML = ciWarning; return; }
    host.innerHTML = ciWarning + '<div class="tip lic-banner">' + TO.icon('alert') + '<span>' + TO.esc(TO.t('lic.banner')) + '</span><a class="btn sm" href="#/settings?tab=licence">' + TO.esc(TO.t('set.tab.licence')) + '</a></div>';
  }
  TO.licenceBanner = banner;
  TO.on('licence', function (lic) { if (TO.me && lic) { TO.me.licence = lic; banner(); } });
  TO.on('route', banner);

  TO.licenceTab = {
    render: function () { return '<section class="card" data-licence><div class="skeleton skeleton-block"></div></section>'; },
    mount: function (root) {
      var host = root.querySelector('[data-licence]'), timer = null;
      var canEdit = TO.can(['settings.edit', 'users.manage']);
      function stop() { if (timer) { clearInterval(timer); timer = null; } }
      function reasonText(r) { return TO.has('lic.refused.' + r) ? TO.t('lic.refused.' + r) : TO.t('lic.refused.other'); }
      function line(q) {
        var wait = q.status === 'sending' || q.status === 'waiting' || (q.status === 'failed' && /^(offline|http_|busy|token|relay_off)/.test(q.error || ''));
        var cls = 'busy', icon = 'clock', text = '';
        if (!q.available) { cls = ''; icon = 'info'; text = TO.t('lic.req.off'); }
        else if (q.status === 'sending') text = TO.t('lic.req.sending');
        else if (q.status === 'waiting' && !q.error) text = TO.t(q.stage === 'approved' ? 'lic.req.approved' : 'lic.req.waiting');
        else if (wait) { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.offline', { when: q.next_try || '' }); }
        else if (q.status === 'failed') { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.codeBad'); }
        else if (q.status === 'refused') { cls = 'bad'; icon = 'x'; text = reasonText(q.reason); }
        else if (q.status === 'closed' && q.reason === 'manual') { cls = 'good'; icon = 'check'; text = TO.t('lic.req.closedManual'); }
        else if (q.status === 'closed') { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.closed'); }
        else if (q.status === 'activated') { cls = 'good'; icon = 'check'; text = TO.t('lic.req.activated'); }
        return { wait: wait, html: text ? '<div class="lic-line ' + cls + '" role="status">' + TO.icon(icon) + '<span>' + TO.esc(text) + '</span></div>' : '' };
      }
      function draw(lic) {
        var q = lic.request || { status: 'none', available: false }, ln = line(q);
        var good = ['trial', 'active', 'grace', 'contract'].indexOf(lic.state) >= 0;
        host.innerHTML = (lic.build_channel === 'ci-test' ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<b>' + TO.esc(TO.t('lic.ciTest')) + '</b></div>' : '') + '<div class="lic ' + (good ? 'good' : '') + '"><div class="lic-state">' + TO.icon(good ? 'shield' : 'lock') + '<div><b data-lic-state>' + TO.esc(TO.t('lic.state.' + lic.state)) + '</b>' +
          (lic.edition ? '<div class="small">' + TO.esc(TO.t('lic.kind.' + lic.edition)) + '</div>' : '') +
          (lic.last_day ? '<div class="small muted">' + TO.esc(TO.t('lic.until', { day: lic.last_day, n: lic.days_left })) + '</div>' : '') + '</div></div>' +
          (lic.state === 'contract' ? '<p class="muted">' + TO.esc(TO.t('lic.contract')) + '</p>' : '') +
          '<div class="field"><span class="label">' + TO.esc(TO.t('lic.device')) + '</span><div class="row"><code class="num" id="dev">' + TO.esc(lic.device || '') + '</code><button class="btn sm" data-copy>' + TO.esc(TO.t('common.copy')) + '</button></div><span class="help">' + TO.esc(TO.t('lic.deviceHint')) + '</span></div>' +
          (lic.enforced && canEdit ? '<div class="field"><label for="lic-code">' + TO.esc(TO.t('lic.paste')) + '</label><textarea id="lic-code" class="input code-box" dir="ltr" spellcheck="false" autocomplete="off"></textarea><span class="err small" id="lic-err" role="alert"></span></div><button class="btn primary" data-activate>' + TO.esc(TO.t('lic.activate')) + '</button>' : '') +
          (lic.enforced && canEdit ? '<div class="lic-auto" aria-live="polite">' + ln.html + '<div class="row wrap">' +
            (q.available && q.status === 'none' && !lic.full ? '<button class="btn primary" data-req="trial">' + TO.esc(TO.t('lic.req.trial')) + '</button>' : '') +
            (q.available && q.status === 'none' ? '<button class="btn" data-req="monthly">' + TO.esc(TO.t('lic.req.monthly')) + '</button><button class="btn" data-req="permanent">' + TO.esc(TO.t('lic.req.permanent')) + '</button>' : '') +
            (ln.wait ? '<button class="btn" data-retry>' + TO.esc(TO.t('lic.req.retry')) + '</button>' : '') +
            (['refused', 'closed', 'activated', 'failed'].indexOf(q.status) >= 0 && !ln.wait ? '<button class="btn" data-again>' + TO.esc(TO.t('lic.req.again')) + '</button>' : '') +
            (q.available ? '<button class="btn ghost sm" data-what>' + TO.esc(TO.t('lic.req.what')) + '</button>' : '') + '</div></div>' : '') +
          (!good ? '<div class="tip">' + TO.icon('info') + '<span>' + TO.esc(TO.t('lic.readOnly')) + '</span></div>' : '') + '</div>';
        var cp = host.querySelector('[data-copy]');
        if (cp) cp.addEventListener('click', function () { var d = host.querySelector('#dev'); try { navigator.clipboard.writeText(lic.device).then(function () { TO.toast(TO.t('link.copied')); }); } catch (e) { getSelection().selectAllChildren(d); } });
        var act = host.querySelector('[data-activate]');
        if (act) act.addEventListener('click', function () {
          var code = host.querySelector('#lic-code').value.trim();
          if (!code) { host.querySelector('#lic-code').focus(); return; }
          TO.ui.run(TO.post('/api/licence/activate', { code: code }), 'lic.done', act).then(function (r) { TO.me.licence = r; banner(); draw(r); }, function (e) { host.querySelector('#lic-err').textContent = TO.ui.errorText(e); });
        });
        host.querySelectorAll('[data-req]').forEach(function (b) { b.addEventListener('click', function () { send(b.dataset.req, b); }); });
        [['[data-retry]', '/api/licence/request/retry'], ['[data-again]', '/api/licence/request/clear']].forEach(function (p) {
          var b = host.querySelector(p[0]); if (b) b.addEventListener('click', function () { TO.ui.run(TO.post(p[1], {}), null, b).then(refresh); });
        });
        var what = host.querySelector('[data-what]');
        if (what) what.addEventListener('click', function () {
          TO.get('/api/licence/preview?kind=trial').then(function (p) {
            TO.dialog({ title: TO.t('lic.req.what'), body: '<p>' + TO.esc(TO.t('lic.req.whatBody')) + '</p><pre dir="ltr" class="report-preview">' + TO.esc(JSON.stringify(p.sends, null, 2)) + '</pre>', footer: '<button class="btn" data-close>' + TO.esc(TO.t('common.close')) + '</button>' });
          });
        });
        stop();
        if (q.status === 'sending' || q.status === 'waiting') timer = setInterval(function () { if (!host.isConnected) { stop(); return; } refresh(); }, 8000);
      }
      function send(kind, btn) {
        TO.ui.run(TO.post('/api/licence/request', { kind: kind }), null, btn).then(refresh, function () { /* the toast says why */ });
      }
      function refresh() {
        return TO.get('/api/licence').then(function (lic) { TO.me.licence = lic; banner(); draw(lic); }, function (e) { host.innerHTML = '<p>' + TO.esc(TO.ui.errorText(e)) + '</p>'; });
      }
      refresh();
    }
  };
})();
