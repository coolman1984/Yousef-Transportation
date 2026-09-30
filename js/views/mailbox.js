/* Trip Orders - Settings -> Mailbox: connect the office to the internet mailbox (the gateway) that carries driver links. Administrators only. */
(function () {
  'use strict';
  var TO = window.TO, U = TO.ui;
  var GWK = 'gw.g', st = null, secrets = null, testing = null;

  function load() { return TO.get('/api/gateway').then(function (s) { st = s; }); }
  function when(iso) { return iso ? U.dt(iso) : '–'; }

  function statusCard() {
    var badge = !st.configured ? '<span class="badge">' + TO.esc(TO.t('gw.st.off')) + '</span>' : st.lastError ? '<span class="badge bad">' + TO.esc(TO.t('gw.st.bad')) + '</span>' : st.lastOk ? '<span class="badge ok">' + TO.esc(TO.t('gw.st.ok')) + '</span>' : '<span class="badge info">' + TO.esc(TO.t('gw.st.wait')) + '</span>';
    return '<section class="card"><header><h3>' + TO.icon('cloud') + ' ' + TO.esc(TO.t('gw.status')) + '</h3>' + badge + '</header>' +
      (st.configured ? '<dl class="kv"><dt>' + TO.esc(TO.t('gw.lastok')) + '</dt><dd>' + when(st.lastOk) + '</dd><dt>' + TO.esc(TO.t('gw.waiting')) + '</dt><dd class="num">' + TO.fmt.num(st.waiting || 0) + '</dd><dt>' + TO.esc(TO.t('gw.applied')) + '</dt><dd class="num">' + TO.fmt.num(st.applied || 0) + '</dd></dl>' : '<p class="muted">' + TO.esc(TO.t('gw.off.body')) + '</p>') +
      (st.lastError ? '<div class="tip bad" role="alert" style="margin-top:1rem">' + TO.icon('alert') + '<span>' + TO.esc(st.lastError) + '</span></div>' : '') +
      (testing ? '<div class="tip ' + (testing.ok ? '' : 'bad') + '" style="margin-top:1rem">' + TO.icon(testing.ok ? 'check' : 'alert') + '<span>' + (testing.ok ? TO.esc(TO.t('gw.test.ok')) + ' · ' + TO.esc(TO.t('gw.test.counts', { e: testing.events, p: testing.photos, c: testing.cards })) : TO.esc(testing.error)) + '</span></div>' : '') +
      '<div class="row wrap" style="gap:.6rem;margin-top:1rem"><button class="btn" data-gw="test"' + (st.configured ? '' : ' disabled') + '>' + TO.icon('refresh', 'sm') + TO.esc(TO.t('gw.test')) + '</button>' +
      '<button class="btn" data-gw="pull"' + (st.configured ? '' : ' disabled') + '>' + TO.icon('download', 'sm') + TO.esc(TO.t('gw.pull')) + '</button></div></section>';
  }
  function settingsCard() {
    return '<section class="card"><header><h3>' + TO.icon('settings') + ' ' + TO.esc(TO.t('gw.settings')) + '</h3></header>' +
      '<div class="field"><label for="gw-url">' + TO.esc(TO.t('gw.url')) + '</label><input class="input" id="gw-url" dir="ltr" placeholder="https://trip-orders.name.workers.dev" value="' + TO.esc(st.url || '') + '"><span class="help">' + TO.esc(TO.t('gw.url.help')) + '</span></div>' +
      '<div class="field"><label for="gw-poll">' + TO.esc(TO.t('gw.poll')) + '</label><input class="input" id="gw-poll" type="number" min="15" max="600" style="max-width:9rem" dir="ltr" value="' + TO.esc(st.pollSeconds || 60) + '"><span class="help">' + TO.esc(TO.t('gw.poll.help')) + '</span></div>' +
      '<div class="row wrap" style="gap:.6rem"><button class="btn primary" data-gw="save">' + TO.esc(TO.t('common.save')) + '</button>' +
      '<button class="btn" data-gw="' + (st.configured ? 'show' : 'generate') + '">' + TO.icon('lock', 'sm') + TO.esc(TO.t(st.configured ? 'gw.secret.show' : 'gw.secret.make')) + '</button></div>' +
      (secrets ? '<div class="stack" style="margin-top:1rem;gap:.8rem"><div class="tip warn">' + TO.icon('alert') + '<span>' + TO.esc(TO.t('gw.secret.warn')) + '</span></div>' +
        '<div class="field"><label>' + TO.esc(TO.t('gw.secret.office')) + '</label><input class="input" readonly dir="ltr" value="' + TO.esc(secrets.officeSecret) + '" data-select></div>' +
        '<div class="field"><label>' + TO.esc(TO.t('gw.secret.code')) + '</label><textarea class="input" rows="3" readonly dir="ltr" data-select>' + TO.esc(secrets.setupCode) + '</textarea><span class="help">' + TO.esc(TO.t('gw.secret.code.help')) + '</span></div></div>' : '') +
      '</section>';
  }
  function otherPcCard() {
    return '<section class="card"><header><h3>' + TO.icon('users') + ' ' + TO.esc(TO.t('gw.code.title')) + '</h3></header><p class="muted">' + TO.esc(TO.t('gw.code.body')) + '</p>' +
      '<div class="field"><textarea class="input" id="gw-code" rows="2" dir="ltr" placeholder="' + TO.esc(TO.t('gw.code.ph')) + '"></textarea></div><button class="btn" data-gw="code">' + TO.esc(TO.t('gw.code.apply')) + '</button></section>';
  }
  function guideCard() {
    return '<section class="card"><header><h3>' + TO.icon('help') + ' ' + TO.esc(TO.t('gw.guide')) + '</h3></header><ol class="steps">' + [1, 2, 3, 4, 5].map(function (i) { return '<li>' + TO.esc(TO.t(GWK + i)) + '</li>'; }).join('') + '</ol></section>';
  }

  TO.mailboxTab = {
    render: function () {
      if (!TO.can('gateway.manage')) return '<section class="card">' + U.empty('lock', TO.t('set.tab.gateway'), TO.t('set.admin.only')) + '</section>';
      if (!st) return '<div class="skeleton" style="height:12rem"></div>';
      return '<div class="grid split"><div class="stack">' + statusCard() + settingsCard() + otherPcCard() + '</div>' + guideCard() + '</div>';
    },
    mount: function (root) {
      if (!TO.can('gateway.manage')) return;
      if (!st) { load().then(function () { TO.rerender(); }, function () { root.innerHTML = U.empty('alert', TO.t('common.error')); }); return; }
      root.addEventListener('focusin', function (e) { if (e.target.hasAttribute && e.target.hasAttribute('data-select')) e.target.select(); });
      root.addEventListener('click', function (e) {
        var b = e.target.closest('[data-gw]'); if (!b) return;
        var a = b.dataset.gw, done = function () { return load().then(function () { TO.data.load(); TO.rerender(); }); };
        if (a === 'save') U.run(TO.post('/api/gateway/save', { url: (root.querySelector('#gw-url') || {}).value, pollSeconds: (root.querySelector('#gw-poll') || {}).value }), 'common.saved', b).then(done);
        else if (a === 'generate') U.run(TO.post('/api/gateway/save', { url: (root.querySelector('#gw-url') || {}).value, pollSeconds: (root.querySelector('#gw-poll') || {}).value }).then(function () { return TO.post('/api/gateway/generate', {}); }), 'gw.made', b)
          .then(function () { return TO.get('/api/gateway/secrets'); }).then(function (s) { secrets = s; return done(); });
        else if (a === 'show') TO.get('/api/gateway/secrets').then(function (s) { secrets = secrets ? null : s; TO.rerender(); }, function (er) { TO.toast(U.errorText(er), 'bad'); });
        else if (a === 'test') { b.disabled = true; TO.post('/api/gateway/test', {}).then(function (r) { testing = r; }, function (er) { testing = { ok: false, error: U.errorText(er) }; }).then(function () { TO.rerender(); }); }
        else if (a === 'pull') { b.disabled = true; TO.post('/api/gateway/pull', {}).then(function () { TO.toast(TO.t('gw.pulled')); return TO.data.load(); }, function (er) { TO.toast(U.errorText(er), 'bad', 6000); }).then(done); }
        else if (a === 'code') U.run(TO.post('/api/gateway/code', { code: (root.querySelector('#gw-code') || {}).value }), 'gw.code.done', b).then(done);
      });
    },
    reset: function () { st = null; secrets = null; testing = null; }
  };
})();
