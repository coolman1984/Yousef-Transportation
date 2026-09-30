/* Trip Orders - core helpers: namespace, escaping, icons, API, events, toasts, dialogs, count-up.
   All scripts share one global scope, so everything lives under window.TO. */
(function () {
  'use strict';
  var TO = window.TO = window.TO || {};
  TO.views = TO.views || {};
  TO.dict = TO.dict || {};

  TO.esc = function (s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  TO.$ = function (sel, root) { return (root || document).querySelector(sel); };
  TO.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ---------- tiny event bus ---------- */
  var handlers = {};
  TO.on = function (name, fn) { (handlers[name] = handlers[name] || []).push(fn); };
  TO.off = function (name, fn) { handlers[name] = (handlers[name] || []).filter(function (f) { return f !== fn; }); };
  TO.emit = function (name, arg) { (handlers[name] || []).slice().forEach(function (f) { try { f(arg); } catch (e) { console.error(e); } }); };

  /* ---------- icons (24x24, stroke) ---------- */
  var IC = {
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5h4v5"/>',
    route: '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8.2 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.8"/>',
    board: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18"/><path d="M8 4v5M8 13h3M8 16.5h6"/>',
    shield: '<path d="M12 3 4.5 6v5.5c0 4.4 3 7.8 7.5 9.5 4.5-1.7 7.5-5.1 7.5-9.5V6L12 3Z"/><path d="m8.7 12 2.3 2.3 4.3-4.6"/>',
    car: '<path d="M4 15.5V12l1.8-4.6A2 2 0 0 1 7.7 6h8.6a2 2 0 0 1 1.9 1.4L20 12v3.5"/><path d="M3.5 12h17V17a1 1 0 0 1-1 1h-1.7a1 1 0 0 1-1-1v-1H7.2v1a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1v-5Z"/><circle cx="7.5" cy="14" r=".6"/><circle cx="16.5" cy="14" r=".6"/>',
    wheel: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.2"/><path d="M12 14.2V21M9.9 11 4 9.4M14.1 11 20 9.4"/>',
    users: '<circle cx="9" cy="8.5" r="3.3"/><path d="M3 20c0-3.3 2.7-5.7 6-5.7s6 2.4 6 5.7"/><path d="M16 5.6a3.2 3.2 0 0 1 0 6"/><path d="M18.2 14.6c1.7.7 2.8 2.4 2.8 5.4"/>',
    pin: '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    sheet: '<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M4 9h16M4 15h16M10 9v12"/>',
    activity: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M4.5 7.4l2 1.2M17.5 15.4l2 1.2M4.5 16.6l2-1.2M17.5 8.6l2-1.2M2.8 12h2.4M18.8 12h2.4"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.2.9-1.2 1.8"/><circle cx="12" cy="16.9" r=".5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 3.8 5.6 3.8 9s-1.2 6.4-3.8 9c-2.6-2.6-3.8-5.6-3.8-9S9.4 5.6 12 3Z"/>',
    palette: '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1.3-1.2-1.5-1.2-2.7 0-1 .8-1.6 1.8-1.6H17a4 4 0 0 0 4-4C21 6.3 17 3 12 3Z"/><circle cx="7.5" cy="11" r=".8"/><circle cx="10" cy="7.2" r=".8"/><circle cx="14.5" cy="7.2" r=".8"/>',
    type: '<path d="M5 6.5V5h14v1.5M12 5v14M9 19h6"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    left: '<path d="m14.5 6-6 6 6 6"/>',
    right: '<path d="m9.5 6 6 6-6 6"/>',
    down: '<path d="m6 9.5 6 6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    alert: '<path d="M12 3.5 2.8 19.5h18.4L12 3.5Z"/><path d="M12 10v4.2"/><circle cx="12" cy="17" r=".5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".5"/>',
    sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M7.5 14h9"/>',
    bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2H4.5l1.5-2Z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
    spark: '<path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.8L12 18l-1.8-5.4L4.5 10.8 10.2 9 12 3.5Z"/><path d="M19 3v3M17.5 4.5h3"/>',
    upload: '<path d="M12 16V4.5M7.5 9 12 4.5 16.5 9M5 19.5h14"/>',
    download: '<path d="M12 4v11.5M7.5 11 12 15.5 16.5 11M5 19.5h14"/>',
    camera: '<path d="M4 8.5h3l1.5-2.5h7L17 8.5h3v10H4v-10Z"/><circle cx="12" cy="13.2" r="3.2"/>',
    chat: '<path d="M4 5.5h16v10H12l-4.5 3.5v-3.5H4v-10Z"/><path d="M8 9.5h8M8 12.5h5"/>',
    lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    logout: '<path d="M14 4.5h4.5a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5H14M10 8l-4 4 4 4M6 12h10"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    cloud: '<path d="M7 18.5a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 10.6a4 4 0 0 1-.6 7.9H7Z"/>',
    printer: '<path d="M7 9V4h10v5M7 17H4.5v-7h15v7H17"/><rect x="7" y="14" width="10" height="6" rx="1"/>',
    layers: '<path d="m12 3.5 9 4.8-9 4.8-9-4.8 9-4.8Z"/><path d="m3 12.3 9 4.8 9-4.8M3 16.3l9 4.8 9-4.8"/>',
    play: '<path d="M8 5.5v13l11-6.5-11-6.5Z"/>',
    present: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8M8 12l3-3 2 2 3-3"/>',
    book: '<path d="M5 4.5h11a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3V4.5Z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20c0-3.8 3.4-6 7.5-6s7.5 2.2 7.5 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.3l3.5 2"/>',
    flag: '<path d="M6 21V4M6 5h11l-2 4 2 4H6"/>',
    gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="m12 17 4-6"/><circle cx="12" cy="17" r="1"/>',
    wrench: '<path d="M14.5 6.5a4 4 0 0 0 4.8 4.8L21 13l-8 8-3-3 8-8-1.5-1.5Z" transform="translate(-4 -3) scale(.9)"/>',
    doc: '<path d="M6 3.5h8l4 4V20.5H6V3.5Z"/><path d="M14 3.5v4h4M9 12h6M9 15.5h6"/>',
    dot: '<circle cx="12" cy="12" r="2.5"/>',
    collapse: '<rect x="3.5" y="4" width="17" height="16" rx="2.5"/><path d="M9.5 4v16"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
    refresh: '<path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 10A7 7 0 0 0 6 7.5M5.5 14A7 7 0 0 0 18 16.5"/>',
    star: '<path d="m12 3.5 2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6L3.4 9.8l6-.8L12 3.5Z"/>',
    external: '<path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>'
  };
  TO.icon = function (name, cls) {
    return '<svg class="ic ' + (cls || '') + '" viewBox="0 0 24 24" aria-hidden="true">' + (IC[name] || IC.dot) + '</svg>';
  };
  TO.iconNames = function () { return Object.keys(IC); };

  /* ---------- API ---------- */
  function ApiError(code, msg, data) { this.code = code; this.message = msg; this.data = data; }
  ApiError.prototype = Object.create(Error.prototype);
  TO.ApiError = ApiError;
  TO.api = function (method, url, body, opts) {
    opts = opts || {};
    var init = { method: method, credentials: 'same-origin', headers: {} };
    if (body !== undefined && body !== null) {
      if (opts.raw) { init.body = body; init.headers['Content-Type'] = 'application/octet-stream'; }
      else { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
    }
    return fetch(url, init).then(function (r) {
      var ct = r.headers.get('Content-Type') || '';
      var p = opts.blob ? r.blob() : (ct.indexOf('json') >= 0 ? r.json() : r.text());
      return p.then(function (data) {
        if (!r.ok) {
          var msg = (data && data.error) || (typeof data === 'string' && data) || ('HTTP ' + r.status);
          if (r.status === 401 && url.indexOf('/api/auth/') !== 0) TO.emit('logged-out');
          throw new ApiError(r.status, msg, data);
        }
        return data;
      });
    });
  };
  TO.get = function (url) { return TO.api('GET', url); };
  TO.post = function (url, body) { return TO.api('POST', url, body === undefined ? {} : body); };

  /* ---------- toasts ---------- */
  TO.toast = function (msg, kind, ms) {
    var box = TO.$('#toasts');
    if (!box) return;
    var el = document.createElement('div');
    el.className = 'toast ' + (kind || '');
    el.setAttribute('role', 'status');
    el.innerHTML = TO.icon(kind === 'bad' ? 'alert' : 'check', 'sm') + '<span>' + TO.esc(msg) + '</span>';
    box.appendChild(el);
    setTimeout(function () { el.style.transition = 'opacity .25s, transform .25s'; el.style.opacity = '0'; el.style.transform = 'translateY(8px)'; setTimeout(function () { el.remove(); }, 260); }, ms || 3200);
  };

  /* ---------- dialog / overlay (one at a time) ---------- */
  var lastFocus = null;
  TO.overlay = {
    open: function (html, opts) {
      opts = opts || {};
      var o = TO.$('#overlay');
      lastFocus = document.activeElement;
      o.className = 'on' + (opts.center === false ? '' : ' center');
      o.innerHTML = html;
      o.onclick = function (e) { if (e.target === o && opts.dismiss !== false) TO.overlay.close(); };
      var f = o.querySelector('[autofocus],input,button');
      if (f) { f.focus(); setTimeout(function () { if (document.activeElement !== f && !o.contains(document.activeElement)) f.focus(); }, 30); }
      TO.overlay.isOpen = true;
      return o;
    },
    close: function () {
      var o = TO.$('#overlay');
      o.className = '';
      o.innerHTML = '';
      o.onclick = null;
      TO.overlay.isOpen = false;
      if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) { /* element is gone */ } }
      TO.emit('overlay-closed');
    },
    isOpen: false
  };
  TO.dialog = function (o) {
    var html = '<div class="dialog" role="dialog" aria-modal="true" aria-label="' + TO.esc(o.title) + '"' + (o.wide ? ' style="width:min(56rem,100%)"' : '') + '>' +
      '<header><h2>' + TO.esc(o.title) + '</h2><button class="icon-btn" data-close aria-label="' + TO.esc(TO.t('common.close')) + '">' + TO.icon('x') + '</button></header>' +
      '<div class="body">' + o.body + '</div>' + (o.footer ? '<footer>' + o.footer + '</footer>' : '') + '</div>';
    var el = TO.overlay.open(html);
    el.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', TO.overlay.close); });
    return el;
  };

  /* ---------- numbers count up (respects reduced motion) ---------- */
  TO.motionOff = function () {
    var d = document.documentElement.dataset.motion;
    if (d === 'off') return true;
    if (d === 'on') return false;
    return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  };
  TO.countUp = function (el, to, ms) {
    to = Number(to) || 0;
    if (TO.motionOff() || to === 0) { el.textContent = TO.fmt.num(to); return; }
    var t0 = performance.now(), dur = ms || 700;
    (function step(now) {
      var k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = TO.fmt.num(Math.round(to * e));
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  };

  /* ---------- debounce ---------- */
  TO.debounce = function (fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); }; };
})();
