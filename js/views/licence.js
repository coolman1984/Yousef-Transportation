/* Trip Orders - Settings -> Licence: simple trial activation (online hub or paste code) plus optional details. */
(function () {
  'use strict';
  var TO = window.TO;
  var TRIAL_BANNER_DAYS = 14;

  function trialDaysKey(n) {
    return n === 1 ? 'lic.trialDaysLeft.one' : 'lic.trialDaysLeft';
  }
  function trialBannerKey(n) {
    return n === 1 ? 'lic.trialBanner.one' : 'lic.trialBanner';
  }

  function trialCountdown(lic) {
    if (lic.state === 'trial' && lic.days_left != null) {
      return '<p class="lic-trial-count" role="status">' + TO.esc(TO.t(trialDaysKey(lic.days_left), { n: lic.days_left })) + '</p>';
    }
    if (lic.state === 'expired' && (lic.edition === 'trial' || lic.reason === 'expired')) {
      return '<p class="lic-trial-expired" role="status">' + TO.esc(TO.t('lic.trialExpired')) + '</p>';
    }
    return '';
  }

  function banner() {
    var host = TO.$('#lic-banner');
    if (!host) return;
    var lic = TO.me && TO.me.licence;
    var ciWarning = lic && lic.build_channel === 'ci-test' ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<b>' + TO.esc(TO.t('lic.ciTest')) + '</b></div>' : '';
    var parts = [ciWarning];
    if (lic && lic.state === 'trial' && lic.days_left != null && lic.days_left <= TRIAL_BANNER_DAYS) {
      parts.push('<div class="tip lic-banner lic-trial-banner">' + TO.icon('clock') + '<span>' + TO.esc(TO.t(trialBannerKey(lic.days_left), { n: lic.days_left })) +
        '</span><a class="btn sm" href="#/settings?tab=licence">' + TO.esc(TO.t('set.tab.licence')) + '</a></div>');
    }
    if (!lic || lic.full) { host.innerHTML = parts.join(''); return; }
    parts.push('<div class="tip lic-banner">' + TO.icon('alert') + '<span>' + TO.esc(TO.t('lic.banner')) + '</span><a class="btn sm" href="#/settings?tab=licence">' + TO.esc(TO.t('set.tab.licence')) + '</a></div>');
    host.innerHTML = parts.join('');
  }
  TO.licenceBanner = banner;
  TO.on('licence', function (lic) { if (TO.me && lic) { TO.me.licence = lic; banner(); } });
  TO.on('route', banner);

  TO.licenceTab = {
    render: function () { return '<section class="card" data-licence><div class="skeleton skeleton-block"></div></section>'; },
    mount: function (root) {
      var host = root.querySelector('[data-licence]'), timer = null, showDetails = false, defaultShop = '', draftCode = '', draftShop = '';
      var canEdit = TO.can(['settings.edit', 'users.manage']);
      function stop() { if (timer) { clearInterval(timer); timer = null; } }
      function reasonText(r) { return TO.has('lic.refused.' + r) ? TO.t('lic.refused.' + r) : TO.t('lic.refused.other'); }
      function shopValue() {
        var el = host.querySelector('#lic-shop');
        var typed = el ? el.value.trim() : '';
        return typed || draftShop || defaultShop;
      }
      function transientError(e) {
        return /^(offline|http_|busy|token|relay_off|recovery_unavailable)/.test(e || '');
      }
      function whenText(iso) {
        if (!iso) return '';
        try { return TO.ui.dt(iso); } catch (e) { return TO.esc(iso); }
      }
      function safeWhenMessage(key, iso) {
        var token = '\u0000when\u0000';
        var message = TO.esc(TO.t(key, { when: token }));
        return message.split(token).join('<bdi dir="ltr">' + whenText(iso) + '</bdi>');
      }
      function line(q) {
        var wait = q.status === 'sending' || q.status === 'waiting' || q.status === 'issued' || (q.status === 'failed' && transientError(q.error));
        var cls = 'busy', icon = 'clock', text = '', textHtml = '', meta = '';
        if (!q.available) { cls = ''; icon = 'info'; text = TO.t('lic.req.off'); }
        else if (q.status === 'sending') text = TO.t('lic.req.sending');
        else if (q.status === 'waiting' && !q.error) {
          text = TO.t(q.stage === 'approved' ? 'lic.req.approved' : 'lic.req.sentWaiting');
          if (q.created_at) meta += '<div class="small muted">' + safeWhenMessage('lic.req.sentAt', q.created_at) + '</div>';
          if (q.next_try) meta += '<div class="small muted">' + safeWhenMessage('lic.req.nextCheck', q.next_try) + '</div>';
        }
        else if (q.status === 'issued' && !q.error) {
          text = TO.t('lic.req.approved');
          if (q.created_at) meta += '<div class="small muted">' + safeWhenMessage('lic.req.sentAt', q.created_at) + '</div>';
          if (q.next_try) meta += '<div class="small muted">' + safeWhenMessage('lic.req.nextCheck', q.next_try) + '</div>';
        }
        else if (q.error === 'recovery_unavailable') { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.recoveryUnavailable'); }
        else if (wait) { cls = 'warn'; icon = 'alert'; textHtml = safeWhenMessage('lic.req.offline', q.next_try); }
        else if (q.status === 'failed') { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.codeBad'); }
        else if (q.status === 'refused') { cls = 'bad'; icon = 'x'; text = reasonText(q.reason); }
        else if (q.status === 'closed' && q.reason === 'manual') { cls = 'good'; icon = 'check'; text = TO.t('lic.req.closedManual'); }
        else if (q.status === 'closed') { cls = 'warn'; icon = 'alert'; text = TO.t('lic.req.closed'); }
        else if (q.status === 'activated') { cls = 'good'; icon = 'check'; text = TO.t('lic.req.activated'); }
        return { wait: wait, html: (text || textHtml) ? '<div class="lic-line ' + cls + '" role="status">' + TO.icon(icon) + '<div class="grow"><span>' + (textHtml || TO.esc(text)) + '</span>' + meta + '</div></div>' : '' };
      }
      function requestOpen(q) {
        return q.status === 'sending' || q.status === 'waiting' || q.status === 'issued' || (q.status === 'failed' && transientError(q.error));
      }
      function draw(lic) {
        var codeEl = host.querySelector('#lic-code');
        var shopEl = host.querySelector('#lic-shop');
        if (codeEl) draftCode = codeEl.value;
        if (shopEl) draftShop = shopEl.value;
        var q = lic.request || { status: 'none', available: false }, ln = line(q);
        var warn = lic.state === 'warning';
        var good = !warn && lic.full && ['trial', 'active', 'grace', 'contract'].indexOf(lic.state) >= 0;
        var showLicenceTools = canEdit && (lic.activation_ui || lic.enforced) && (!lic.full || lic.state === 'trial' || lic.state === 'expired' || lic.reason === 'no_keys');
        var canHubRequest = showLicenceTools && q.available && !lic.full && q.status === 'none';
        var showRequestLine = showLicenceTools && q.status !== 'none' && ln.html;
        var shopField = showLicenceTools && q.available ? '<div class="field"><label for="lic-shop">' + TO.esc(TO.t('lic.orgName')) + '</label><input id="lic-shop" class="input" maxlength="60" value="' + TO.esc(draftShop || defaultShop) + '"></div>' : '';
        host.innerHTML = (lic.build_channel === 'ci-test' ? '<div class="tip bad" role="alert">' + TO.icon('alert') + '<b>' + TO.esc(TO.t('lic.ciTest')) + '</b></div>' : '') +
          '<div class="lic ' + (good ? 'good' : '') + '">' +
          '<div class="lic-state">' + TO.icon(warn ? 'alert' : good ? 'shield' : 'lock') + '<div><b data-lic-state>' + TO.esc(TO.t('lic.state.' + lic.state)) + '</b>' +
          (lic.edition ? '<div class="small">' + TO.esc(TO.t('lic.kind.' + lic.edition)) + '</div>' : '') +
          (lic.last_day && lic.state !== 'trial' ? '<div class="small muted">' + TO.esc(TO.t('lic.until', { day: lic.last_day, n: lic.days_left })) + '</div>' : '') +
          trialCountdown(lic) + '</div></div>' +
          (lic.state === 'contract' ? '<p class="muted">' + TO.esc(TO.t('lic.contract')) + '</p>' : '') +
          (showLicenceTools ? '<div class="lic-simple">' +
            shopField +
            (showRequestLine ? ln.html : '') +
            (ln.wait ? '<button class="btn" data-retry>' + TO.esc(TO.t('lic.req.retry')) + '</button>' : '') +
            (['refused', 'closed', 'activated', 'failed'].indexOf(q.status) >= 0 && !ln.wait ? '<button class="btn" data-again>' + TO.esc(TO.t('lic.req.again')) + '</button>' : '') +
            '<div class="field lic-device-block"><span class="label">' + TO.esc(TO.t('lic.device')) + '</span>' +
            '<p class="help">' + TO.esc(TO.t('lic.sendDeviceCode')) + '</p>' +
            '<div class="row"><code class="num lic-device-big" id="dev" dir="ltr"><bdi>' + TO.esc(lic.device || '') + '</bdi></code>' +
            '<button class="btn sm" data-copy>' + TO.esc(TO.t('common.copy')) + '</button></div></div>' +
            '<div class="field"><label for="lic-code">' + TO.esc(TO.t('lic.pasteActivation')) + '</label>' +
            '<textarea id="lic-code" class="input code-box" dir="ltr" spellcheck="false" autocomplete="off">' + TO.esc(draftCode) + '</textarea>' +
            '<span class="err small" id="lic-err" role="alert"></span></div>' +
            '<button class="btn primary lic-simple-cta" data-activate>' + TO.esc(TO.t('lic.activate')) + '</button>' +
            '</div>' : '') +
          (showLicenceTools ? '<button type="button" class="btn ghost sm lic-details-toggle" data-details>' + TO.esc(TO.t('lic.details')) + '</button>' : '') +
          (showLicenceTools && showDetails ? '<div class="lic-details" data-lic-details>' +
            '<div class="field"><span class="label">' + TO.esc(TO.t('lic.device')) + '</span><div class="row"><code class="num" dir="ltr"><bdi>' + TO.esc(lic.device || '') + '</bdi></code></div>' +
            '<span class="help">' + TO.esc(TO.t('lic.deviceHint')) + '</span></div>' +
            '<div class="lic-auto" aria-live="polite"><div class="row wrap">' +
            (canHubRequest ? '<button class="btn" data-req="trial">' + TO.esc(TO.t('lic.req.trial')) + '</button>' : '') +
            (showLicenceTools && q.available && q.status === 'none' ? '<button class="btn" data-req="monthly">' + TO.esc(TO.t('lic.req.monthly')) + '</button><button class="btn" data-req="permanent">' + TO.esc(TO.t('lic.req.permanent')) + '</button>' : '') +
            (q.available ? '<button class="btn ghost sm" data-what>' + TO.esc(TO.t('lic.req.what')) + '</button>' : '') + '</div></div></div>' : '') +
          (!good ? '<div class="tip">' + TO.icon('info') + '<span>' + TO.esc(TO.t('lic.readOnly')) + '</span></div>' : '') + '</div>';
        var cp = host.querySelector('[data-copy]');
        if (cp) cp.addEventListener('click', function () { var d = host.querySelector('#dev'); try { navigator.clipboard.writeText(lic.device).then(function () { TO.toast(TO.t('link.copied')); }); } catch (e) { getSelection().selectAllChildren(d); } });
        var act = host.querySelector('[data-activate]');
        if (act) act.addEventListener('click', function () {
          var code = host.querySelector('#lic-code').value.trim();
          if (code) {
            TO.ui.run(TO.post('/api/licence/activate', { code: code }), 'lic.done', act).then(function (r) { TO.me.licence = r; banner(); draw(r); }, function (e) { host.querySelector('#lic-err').textContent = TO.ui.errorText(e); });
            return;
          }
          if (canHubRequest) {
            send('trial', act, shopValue());
            return;
          }
          host.querySelector('#lic-code').focus();
        });
        host.querySelectorAll('[data-req]').forEach(function (b) { b.addEventListener('click', function () { send(b.dataset.req, b, shopValue()); }); });
        [['[data-retry]', '/api/licence/request/retry'], ['[data-again]', '/api/licence/request/clear']].forEach(function (p) {
          var b = host.querySelector(p[0]); if (b) b.addEventListener('click', function () { TO.ui.run(TO.post(p[1], {}), null, b).then(refresh); });
        });
        var det = host.querySelector('[data-details]');
        if (det) det.addEventListener('click', function () { showDetails = !showDetails; draw(lic); });
        var what = host.querySelector('[data-what]');
        if (what) what.addEventListener('click', function () {
          TO.get('/api/licence/preview?kind=trial').then(function (p) {
            var sends = Object.assign({}, p.sends || {});
            var shop = shopValue();
            if (shop) sends.shop = shop.slice(0, 60);
            TO.dialog({ title: TO.t('lic.req.what'), body: '<p>' + TO.esc(TO.t('lic.req.whatBody')) + '</p><pre dir="ltr" class="report-preview">' + TO.esc(JSON.stringify(sends, null, 2)) + '</pre>', footer: '<button class="btn" data-close>' + TO.esc(TO.t('common.close')) + '</button>' });
          });
        });
        stop();
        if (requestOpen(q)) timer = setInterval(function () { if (!host.isConnected) { stop(); return; } refresh(); }, 15000);
      }
      function send(kind, btn, shop) {
        var body = { kind: kind };
        if (shop !== undefined && String(shop).trim()) body.shop = String(shop).trim().slice(0, 60);
        TO.ui.run(TO.post('/api/licence/request', body), null, btn).then(refresh, function () { /* the toast says why */ });
      }
      function refresh() {
        return TO.get('/api/licence').then(function (lic) {
          var wasWaiting = host.dataset.waiting === '1';
          TO.me.licence = lic;
          banner();
          draw(lic);
          host.dataset.waiting = requestOpen(lic.request || {}) ? '1' : '0';
          if (wasWaiting && lic.full && (lic.request || {}).status === 'activated') TO.toast(TO.t('lic.done'));
        }, function (e) { host.innerHTML = '<p>' + TO.esc(TO.ui.errorText(e)) + '</p>'; });
      }
      TO.get('/api/licence/preview?kind=trial').then(function (p) { defaultShop = (p.sends && p.sends.shop) || ''; refresh(); }, refresh);
    }
  };

  TO.views.licence = {
    render: function () {
      return '<div class="page-head"><div class="titles"><h1>' + TO.esc(TO.t('nav.licence')) + '</h1><p>' + TO.esc(TO.t('page.licence.d')) + '</p></div></div>' + TO.licenceTab.render();
    },
    mount: function (root) { TO.licenceTab.mount(root); }
  };
})();
