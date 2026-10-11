/* Trip Orders - Settings -> Privacy & help: the two agreements (installation, person), what is and is never sent, the problem report with its
   queue state, what was sent, and (for whoever may change settings) the help-service address and token. Everything here is optional:
   with no agreement and no address nothing leaves this PC. */
(function () {
  'use strict';
  var TO = window.TO;

  function row(label, value) { return '<dt>' + TO.esc(label) + '</dt><dd>' + TO.esc(value) + '</dd>'; }

  TO.privacyTab = {
    render: function () {
      return '<div class="grid two-col" data-privacy><section class="card"><div class="skeleton skeleton-block"></div></section></div>';
    },
    mount: function (root) {
      var host = root.querySelector('[data-privacy]');
      var canEdit = TO.can('settings.edit');
      function load() {
        return Promise.all([
          TO.get('/api/consent/status'), TO.get('/api/consent/prompt?lang=' + TO.lang), TO.get('/api/telemetry/queue'), TO.get('/api/telemetry/sent'),
          canEdit ? TO.get('/api/telemetry/receiver') : Promise.resolve(null)
        ]).then(function (r) { draw({ status: r[0], prompt: r[1], queue: r[2], sent: r[3].sent || [], receiver: r[4] }); }, function (e) {
          host.innerHTML = '<section class="card"><p>' + TO.esc(TO.ui.errorText(e)) + '</p></section>';
        });
      }
      function decide(scope, decision, prompt) {
        return TO.ui.run(TO.post('/api/consent/decide', { decision: decision, text_id: prompt.text_id, lang: prompt.lang, scope: scope }), 'privacy.saved')
          .then(function () { return TO.guide.refreshConsent(); }).then(function () { TO.guide.refreshStates(); return load(); }, function () { /* the toast says why */ });
      }
      function installCard(d) {
        var inst = d.status.install;
        var h = '<h3>' + TO.esc(TO.t('privacy.install.t')) + '</h3>';
        if (!inst) h += '<p>' + TO.esc(TO.t('privacy.install.none')) + '</p>';
        else h += '<p data-install-state>' + TO.esc(TO.t(inst.decision === 'agree' ? 'privacy.install.on' : 'privacy.install.off')) + ' <span class="faint">' + TO.esc(inst.at) + '</span></p>';
        if (canEdit) {
          h += '<p class="muted">' + TO.esc(d.prompt.text) + '</p><p class="muted">' + TO.esc(d.prompt.more) + '</p><div class="row wrap">' +
            (!inst || inst.decision !== 'agree' ? '<button class="btn primary" data-install="agree">' + TO.esc(d.prompt.agree) + '</button>' : '') +
            (!inst || inst.decision === 'agree' ? '<button class="btn" data-install="' + (inst ? 'withdraw' : 'decline') + '">' + TO.esc(inst ? TO.t('privacy.withdraw') : d.prompt.decline) + '</button>' : '') + '</div>';
        } else h += '<p class="muted">' + TO.esc(TO.t('privacy.install.ask')) + '</p>';
        return '<section class="card" data-install-card>' + h + '</section>';
      }
      function neverCard() {
        var sent = ['page', 'actions', 'errors', 'ids'], never = ['passwords', 'people', 'money', 'screen', 'trips'];
        return '<section class="card"><h3>' + TO.esc(TO.t('privacy.sent.t')) + '</h3><ul>' + sent.map(function (k) { return '<li>' + TO.esc(TO.t('privacy.sent.' + k)) + '</li>'; }).join('') +
          '</ul><h3>' + TO.esc(TO.t('privacy.never.t')) + '</h3><ul>' + never.map(function (k) { return '<li>' + TO.esc(TO.t('privacy.never.' + k)) + '</li>'; }).join('') + '</ul></section>';
      }
      function queueCard(d) {
        var q = d.queue, rec = d.receiver;
        var state = !q.configured ? 'privacy.q.local' : q.lastError ? 'privacy.q.retry' : q.waiting ? 'privacy.q.waiting' : 'privacy.q.sent';
        return '<section class="card" data-queue-card><h3>' + TO.esc(TO.t('privacy.report.t')) + '</h3><p class="muted">' + TO.esc(TO.t('privacy.report.b')) + '</p>' +
          '<div class="row wrap"><button class="btn primary" data-report>' + TO.icon('alert', 'sm') + TO.esc(TO.t('report.open')) + '</button>' +
          (canEdit ? '<button class="btn" data-flush>' + TO.esc(TO.t('privacy.q.now')) + '</button>' : '') + '</div>' +
          '<dl class="kv" data-queue>' + row(TO.t('privacy.q.state'), TO.t(state)) + row(TO.t('privacy.q.waiting.n'), String(q.waiting)) +
          row(TO.t('privacy.q.last'), q.lastSent || '–') + (q.lastError ? row(TO.t('privacy.q.err'), q.lastError) : '') + (q.dead ? row(TO.t('privacy.q.dead'), String(q.dead)) : '') + '</dl>' +
          (rec ? '' : '') + '</section>';
      }
      function receiverCard(d) {
        var r = d.receiver;
        if (!r) return '';
        return '<section class="card" data-receiver-card><h3>' + TO.esc(TO.t('privacy.hub.t')) + '</h3><p class="muted">' + TO.esc(TO.t('privacy.hub.b')) + '</p>' +
          '<div class="field"><label for="hub-url">' + TO.esc(TO.t('privacy.hub.url')) + '</label><input class="input" id="hub-url" dir="ltr" autocomplete="off" value="' + TO.esc(r.url) + '"' + (r.urlFromEnvironment ? ' readonly' : '') + '>' +
          (r.urlFromEnvironment ? '<span class="help">' + TO.esc(TO.t('privacy.hub.env')) + '</span>' : '') + '</div>' +
          '<div class="field"><label for="hub-token">' + TO.esc(TO.t('privacy.hub.token')) + '</label><input class="input" id="hub-token" type="password" dir="ltr" autocomplete="off" placeholder="' + TO.esc(r.hasToken ? TO.t('privacy.hub.token.set') : '') + '">' +
          '<span class="help">' + TO.esc(TO.t('privacy.hub.token.h')) + '</span></div>' +
          '<div class="row wrap"><button class="btn primary" data-hub-save>' + TO.esc(TO.t('common.save')) + '</button>' + (r.hasToken ? '<button class="btn" data-hub-clear>' + TO.esc(TO.t('privacy.hub.clear')) + '</button>' : '') + '</div></section>';
      }
      function sentCard(d) {
        var list = d.sent.length ? '<ul class="plain">' + d.sent.map(function (e) { return '<li><b>' + TO.esc(e.type) + '</b> <span class="faint">' + TO.esc(e.ts || '') + '</span></li>'; }).join('') + '</ul>' : '<p class="muted">' + TO.esc(TO.t('privacy.sent.none')) + '</p>';
        return '<section class="card"><h3>' + TO.esc(TO.t('privacy.log.t')) + '</h3>' + list + '</section>';
      }
      function draw(d) {
        host.innerHTML = '<div class="stack">' + installCard(d) + '<section class="card" data-person-card></section>' + neverCard() + '</div><div class="stack">' + queueCard(d) + receiverCard(d) + sentCard(d) + '</div>';
        var box = host.querySelector('[data-person-card]');
        if (window.AFConsent) {
          window.AFConsent.settings(box, { status: d.status, prompt: d.prompt, decide: function (decision) { decide('person', decision, d.prompt); }, showSent: function () { box.scrollIntoView(); } });
        }
        host.querySelectorAll('[data-install]').forEach(function (b) { b.addEventListener('click', function () { decide('install', b.dataset.install, d.prompt); }); });
        var rep = host.querySelector('[data-report]'); if (rep) rep.addEventListener('click', function () { TO.guide.report({}); });
        var fl = host.querySelector('[data-flush]'); if (fl) fl.addEventListener('click', function () { TO.ui.run(TO.post('/api/telemetry/flush', {}), null, fl).then(function () { setTimeout(load, 1500); }); });
        var save = host.querySelector('[data-hub-save]');
        if (save) save.addEventListener('click', function () {
          var body = { url: host.querySelector('#hub-url').value.trim(), token: host.querySelector('#hub-token').value };
          TO.ui.run(TO.post('/api/telemetry/receiver', body), 'privacy.saved', save).then(load, function () { /* the toast says why */ });
        });
        var clr = host.querySelector('[data-hub-clear]');
        if (clr) clr.addEventListener('click', function () { TO.ui.run(TO.post('/api/telemetry/receiver', { url: host.querySelector('#hub-url').value.trim(), clearToken: true }), 'privacy.saved', clr).then(load); });
      }
      TO.on('report-sent', function () { if (host.isConnected) load(); });
      load();
    }
  };
})();
