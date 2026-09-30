/* Trip Orders driver page - service worker. The page shell and app files are cached so a trip can be opened and finished
   without a network; the card is fetched network-first and the last copy is used when offline. Nothing else is cached. */
var VERSION = 'to-driver-1';
var SHELL = ['/app/style.css', '/app/i18n.js', '/app/outbox.js', '/app/camera.js', '/app/app.js', '/app/manifest.webmanifest', '/app/icon.svg'];

function cardKey(path) {
  return crypto.subtle.digest('SHA-256', new TextEncoder().encode(path)).then(function (h) {
    return '/c/' + Array.prototype.map.call(new Uint8Array(h), function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  });
}

self.addEventListener('install', function (e) {
  // the page shell is the same for every trip (no secrets in it), so it is fetched once under a neutral address
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(SHELL).then(function () { return fetch('/t/shell').then(function (r) { if (!r.ok) throw new Error('shell'); return c.put('/index.html', r); }); }); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) { return Promise.all(ks.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); })); }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  var req = e.request, url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.mode === 'navigate' && url.pathname.indexOf('/t/') === 0) {
    e.respondWith(fetch(req).then(function (r) { var copy = r.clone(); caches.open(VERSION).then(function (c) { c.put('/index.html', copy); }); return r; }, function () { return caches.match('/index.html'); }));
    return;
  }
  if (req.method !== 'GET') return;
  if (url.pathname.indexOf('/api/card/') === 0) {
    // cached under a hash of the path, so the token itself is not written into the cache index and two trips never mix
    e.respondWith(cardKey(url.pathname).then(function (key) {
      return fetch(req).then(function (r) { if (r.ok) { var copy = r.clone(); caches.open(VERSION).then(function (c) { c.put(key, copy); }); } return r; },
        function () { return caches.match(key).then(function (r) { return r || Response.error(); }); });
    }));
    return;
  }
  if (url.pathname.indexOf('/app/') === 0) {
    e.respondWith(caches.match(req).then(function (r) { return r || fetch(req); }));
  }
});
