/* Trip Orders - sign in, first-start administrator setup, self sign-up, password reset, forced password change. */
(function () {
  'use strict';
  var TO = window.TO;
  var mode = 'login';

  function hero() {
    return '<div class="hero"><div class="row"><div class="brand" style="padding:0;min-height:0"><div class="mark">' + TO.icon('route', 'lg') + '</div><div class="name">' + TO.esc(TO.t('app.name')) + '</div></div>' +
      '<span class="grow"></span><button class="btn ghost sm" data-lang style="color:var(--side-ink)">' + TO.icon('globe', 'sm') + (TO.lang === 'ar' ? 'English' : 'العربية') + '</button></div>' +
      '<div><h1>' + TO.esc(TO.t('auth.hero.title')) + '</h1><p>' + TO.esc(TO.t('auth.hero.sub')) + '</p></div><div class="road" aria-hidden="true"></div></div>';
  }
  function field(id, label, type, extra) {
    return '<div class="field"><label for="' + id + '">' + TO.esc(label) + '</label><input class="input" id="' + id + '" name="' + id + '" type="' + type + '" ' + (extra || '') + '></div>';
  }
  function bindLang(root) {
    var b = root.querySelector('[data-lang]');
    if (b) b.addEventListener('click', function () { TO.prefs.toggleLang(); TO.emit('auth-rerender'); });
  }
  function fail(form, msg) {
    var e = form.querySelector('.err');
    e.hidden = false; e.textContent = msg;
  }
  function links() {
    return '<div class="row wrap" style="gap:.8rem;margin-top:.6rem;font-size:.9rem">' +
      '<button type="button" class="btn ghost sm" data-auth-mode="signup">' + TO.esc(TO.t('auth.link.signup')) + '</button>' +
      '<button type="button" class="btn ghost sm" data-auth-mode="forgot">' + TO.esc(TO.t('auth.link.forgot')) + '</button>' +
      '<button type="button" class="btn ghost sm" data-auth-mode="reset">' + TO.esc(TO.t('auth.link.reset')) + '</button></div>';
  }
  function loginForm() {
    return '<form id="auth-form"><div><h2>' + TO.esc(TO.t('auth.login.title')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.login.sub')) + '</p></div>' +
      field('username', TO.t('auth.username'), 'text', 'autofocus required autocapitalize="off" spellcheck="false" dir="ltr" autocomplete="username"') +
      field('password', TO.t('auth.password'), 'password', 'required dir="ltr" autocomplete="current-password"') +
      '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>' +
      '<button class="btn primary" type="submit">' + TO.esc(TO.t('auth.login.btn')) + '</button>' + links() + '</form>';
  }
  function signupForm() {
    return '<form id="auth-form"><div><h2>' + TO.esc(TO.t('auth.signup.title')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.signup.sub')) + '</p></div>' +
      field('full_name', TO.t('auth.fullname'), 'text', 'autofocus required') +
      field('username', TO.t('auth.username'), 'text', 'required autocapitalize="off" spellcheck="false" dir="ltr"') +
      field('password', TO.t('auth.password'), 'password', 'required dir="ltr"') +
      field('password2', TO.t('auth.password2'), 'password', 'required dir="ltr"') +
      field('title', TO.t('acc.title'), 'text', '') +
      '<p class="faint" style="font-size:.85rem">' + TO.esc(TO.t('auth.pw.hint')) + '</p>' +
      '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>' +
      '<div class="tip ok" hidden role="status" style="background:var(--good-soft);color:var(--good)"></div>' +
      '<button class="btn primary" type="submit">' + TO.esc(TO.t('auth.signup.btn')) + '</button>' +
      '<button type="button" class="btn ghost" data-auth-mode="login" style="margin-inline-start:.5rem">' + TO.esc(TO.t('auth.backLogin')) + '</button></form>';
  }
  function forgotForm() {
    return '<form id="auth-form"><div><h2>' + TO.esc(TO.t('auth.forgot.title')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.forgot.sub')) + '</p></div>' +
      field('username', TO.t('auth.username'), 'text', 'autofocus required autocapitalize="off" spellcheck="false" dir="ltr"') +
      '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>' +
      '<button class="btn primary" type="submit">' + TO.esc(TO.t('common.close')) + '</button>' +
      '<button type="button" class="btn ghost" data-auth-mode="login" style="margin-inline-start:.5rem">' + TO.esc(TO.t('auth.backLogin')) + '</button></form>';
  }
  function resetForm() {
    return '<form id="auth-form"><div><h2>' + TO.esc(TO.t('auth.reset.title')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.reset.sub')) + '</p></div>' +
      field('username', TO.t('auth.username'), 'text', 'autofocus required autocapitalize="off" spellcheck="false" dir="ltr"') +
      field('code', TO.t('auth.reset.code'), 'text', 'required dir="ltr" autocapitalize="characters" spellcheck="false"') +
      field('password', TO.t('auth.password'), 'password', 'required dir="ltr"') +
      field('password2', TO.t('auth.password2'), 'password', 'required dir="ltr"') +
      '<p class="faint" style="font-size:.85rem">' + TO.esc(TO.t('auth.pw.hint')) + '</p>' +
      '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>' +
      '<button class="btn primary" type="submit">' + TO.esc(TO.t('auth.reset.btn')) + '</button>' +
      '<button type="button" class="btn ghost" data-auth-mode="login" style="margin-inline-start:.5rem">' + TO.esc(TO.t('auth.backLogin')) + '</button></form>';
  }

  TO.views.auth = {
    show: function (status) {
      var root = TO.$('#root');
      var setup = !status.hasUsers;
      var body;
      if (setup && !status.local) {
        body = '<div class="empty"><div class="art">' + TO.icon('lock', 'lg') + '</div><h3>' + TO.esc(TO.t('auth.setup.title')) + '</h3><p>' + TO.esc(TO.t('auth.remote')) + '</p></div>';
      } else if (setup) {
        body = '<form id="auth-form" autocomplete="off"><div><h2>' + TO.esc(TO.t('auth.setup.title')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.setup.sub')) + '</p></div>' +
          field('full_name', TO.t('auth.fullname'), 'text', 'autofocus required') + field('username', TO.t('auth.username'), 'text', 'required autocapitalize="off" spellcheck="false" dir="ltr"') +
          field('password', TO.t('auth.password'), 'password', 'required dir="ltr"') + '<p class="faint" style="font-size:.85rem">' + TO.esc(TO.t('auth.pw.hint')) + '</p>' +
          '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div>' +
          '<button class="btn primary" type="submit">' + TO.esc(TO.t('auth.setup.btn')) + '</button></form>';
      } else {
        body = mode === 'signup' ? signupForm() : mode === 'forgot' ? forgotForm() : mode === 'reset' ? resetForm() : loginForm();
      }
      root.innerHTML = '<div class="auth">' + hero() + '<div class="panel">' + body + '</div></div><div id="overlay"></div><div id="toasts"></div>';
      bindLang(root);
      root.addEventListener('click', function (e) {
        var b = e.target.closest('[data-auth-mode]');
        if (b) { mode = b.dataset.authMode; TO.views.auth.show(status); }
      });
      var form = TO.$('#auth-form', root);
      if (!form) return;
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var d = {}; new FormData(form).forEach(function (v, k) { d[k] = String(v).trim(); });
        var btn = form.querySelector('button[type=submit]'); if (btn) btn.disabled = true;
        if (setup) {
          TO.post('/api/auth/setup', d).then(function () { TO.emit('logged-in'); }, function (err) {
            if (btn) btn.disabled = false;
            fail(form, err.code === 401 || err.code === 400 ? (err.message || TO.t('auth.failed')) : TO.t('common.error'));
          });
          return;
        }
        if (mode === 'signup') {
          if (d.password !== d.password2) { if (btn) btn.disabled = false; fail(form, TO.t('auth.pw.mismatch')); return; }
          TO.post('/api/auth/register', d).then(function (r) {
            var ok = form.querySelector('.ok');
            if (ok) { ok.hidden = false; ok.textContent = TO.t('auth.signup.done', { code: r.request_code || '' }); }
            if (btn) btn.disabled = false;
          }, function (err) { if (btn) btn.disabled = false; fail(form, err.message || TO.t('common.error')); });
          return;
        }
        if (mode === 'forgot') {
          if (btn) btn.disabled = false;
          TO.dialog({ title: TO.t('auth.forgot.title'), body: '<p>' + TO.esc(TO.t('auth.forgot.help')) + '</p>', footer: '<button class="btn primary" data-close>' + TO.esc(TO.t('common.close')) + '</button>' });
          return;
        }
        if (mode === 'reset') {
          if (d.password !== d.password2) { if (btn) btn.disabled = false; fail(form, TO.t('auth.pw.mismatch')); return; }
          TO.post('/api/auth/reset', { username: d.username, code: d.code, password: d.password }).then(function () {
            mode = 'login'; TO.toast(TO.t('auth.reset.done')); TO.views.auth.show(status);
          }, function (err) { if (btn) btn.disabled = false; fail(form, err.message || TO.t('common.error')); });
          return;
        }
        TO.post('/api/auth/login', d).then(function () { TO.emit('logged-in'); }, function (err) {
          if (btn) btn.disabled = false;
          fail(form, err.code === 401 || err.code === 400 ? (err.message || TO.t('auth.failed')) : TO.t('common.error'));
        });
      });
    },
    mustChange: function () {
      var root = TO.$('#root');
      root.innerHTML = '<div class="auth">' + hero() + '<div class="panel"><form id="auth-form"><div><h2>' + TO.esc(TO.t('auth.password')) + '</h2><p class="muted" style="margin-top:.4rem">' + TO.esc(TO.t('auth.pw.hint')) + '</p></div>' +
        field('old', TO.t('auth.password') + ' (1)', 'password', 'autofocus required dir="ltr"') + field('new', TO.t('auth.password') + ' (2)', 'password', 'required dir="ltr"') +
        '<div class="tip err" hidden role="alert" style="background:var(--bad-soft);color:var(--bad)"></div><button class="btn primary" type="submit">' + TO.esc(TO.t('common.save')) + '</button></form></div></div><div id="overlay"></div><div id="toasts"></div>';
      bindLang(root);
      var form = TO.$('#auth-form', root);
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        TO.post('/api/auth/password', { old: form.old.value, new: form.new.value }).then(function () { TO.emit('logged-in'); }, function (err) { fail(form, err.message); });
      });
    }
  };
  TO.on('auth-rerender', function () {
    TO.get('/api/auth/status').then(function (st) { if (!st.me) TO.views.auth.show(st); });
  });
})();
