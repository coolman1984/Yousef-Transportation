/* Trip Orders - start-up: decides between the sign-in screen and the application. */
(function () {
  'use strict';
  var TO = window.TO;
  var keepAlive = null;

  function start() {
    TO.get('/api/auth/status').then(function (s) {
      TO.status = s;
      if (s.me) {
        TO.me = s.me;
        if (s.me.must_change) { TO.views.auth.mustChange(); return; }
        TO.data.load().then(function () { TO.shell.start(); TO.data.startPolling(); TO.guide.mount(); }, function () { TO.shell.start(); TO.guide.mount(); });
        clearInterval(keepAlive);
        keepAlive = setInterval(function () { TO.get('/api/version').catch(function () { /* a 401 signs out through TO.api */ }); }, 45000);
      } else {
        TO.me = null; clearInterval(keepAlive);
        TO.views.auth.show(s);
      }
    }, function () {
      TO.$('#root').innerHTML = '<div class="auth"><div class="panel"><div class="empty"><div class="art">' + TO.icon('alert', 'lg') + '</div><h3>' + TO.esc(TO.t('common.error')) + '</h3>' +
        '<button class="btn primary" id="retry-start">' + TO.esc(TO.t('common.retry')) + '</button></div></div></div>';
      var retry = TO.$('#retry-start');             // no inline onclick: the page's content security policy forbids it
      if (retry) retry.addEventListener('click', function () { location.reload(); });
    });
  }
  TO.on('logged-in', start);
  TO.on('logged-out', function () { TO.guide.unmount(); TO.shell.stop(); TO.data.stopPolling(); TO.data.state = null; start(); });
  TO.on('auth-rerender', function () { if (TO.status) TO.views.auth.show(TO.status); });

  document.addEventListener('DOMContentLoaded', function () {
    TO.prefs.apply();
    document.title = TO.t('app.name');
    start();
  });
})();
