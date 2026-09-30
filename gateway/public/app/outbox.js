/* Driver page storage and sending: everything the driver does is written to IndexedDB first, then sent; it stays
   until the gateway answered "ok". Retries with backoff, on going online, on coming back to the page, and on open. */
(function () {
  'use strict';
  var D = window.D;
  var dbp = null, timer = null, delay = 1000, busy = false, listeners = [];

  function open() {
    if (dbp) return dbp;
    dbp = new Promise(function (ok, bad) {
      var r = indexedDB.open('to-driver', 1);
      r.onupgradeneeded = function () {
        var db = r.result;
        db.createObjectStore('meta', { keyPath: 'key' });
        db.createObjectStore('drafts', { keyPath: 'key' });
        var o = db.createObjectStore('outbox', { keyPath: 'id', autoIncrement: true });
        o.createIndex('trip', 'tripKey');
      };
      r.onsuccess = function () { ok(r.result); };
      r.onerror = function () { bad(r.error); };
    });
    return dbp;
  }
  function tx(store, mode, fn) {
    return open().then(function (db) {
      return new Promise(function (ok, bad) {
        var t = db.transaction(store, mode), s = t.objectStore(store), out = fn(s);
        t.oncomplete = function () { ok(out && out.result !== undefined ? out.result : undefined); };
        t.onerror = t.onabort = function () { bad(t.error); };
      });
    });
  }
  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    var b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  function emit() { listeners.forEach(function (f) { try { f(); } catch (e) { /* ignore */ } }); }

  D.outbox = {
    uuid: uuid,
    onchange: function (f) { listeners.push(f); },
    deviceId: function () {
      return tx('meta', 'readonly', function (s) { return s.get('device'); }).then(function (r) {
        if (r && r.value) return r.value;
        var id = 'd' + uuid().replace(/-/g, '');
        return tx('meta', 'readwrite', function (s) { return s.put({ key: 'device', value: id }); }).then(function () { return id; });
      }).catch(function () { return 'volatile-' + uuid().replace(/-/g, '').slice(0, 20); });
    },
    getDraft: function (key) { return tx('drafts', 'readonly', function (s) { return s.get(key); }).catch(function () { return null; }); },
    saveDraft: function (d) { return tx('drafts', 'readwrite', function (s) { return s.put(d); }).catch(function () { /* storage full or blocked: the page still works in memory */ }); },
    add: function (item) {
      item.tries = 0; item.sentAt = null; item.error = null;
      return tx('outbox', 'readwrite', function (s) { return s.add(item); }).then(function (id) { emit(); D.outbox.kick(); return id; });
    },
    items: function (tripKey) {
      return open().then(function (db) {
        return new Promise(function (ok, bad) {
          var r = db.transaction('outbox').objectStore('outbox').index('trip').getAll(tripKey);
          r.onsuccess = function () { ok(r.result); }; r.onerror = function () { bad(r.error); };
        });
      }).catch(function () { return []; });
    },
    retryFailed: function (tripKey) {
      return D.outbox.items(tripKey).then(function (all) {
        return Promise.all(all.filter(function (i) { return i.error; }).map(function (i) { i.error = null; return tx('outbox', 'readwrite', function (s) { return s.put(i); }); }));
      }).then(function () { delay = 1000; D.outbox.kick(true); });
    },
    kick: function (now) {
      clearTimeout(timer);
      timer = setTimeout(flush, now ? 0 : 50);
    },
    online: true,
  };

  function send(item, token) {
    var isPhoto = item.kind === 'photo', url, init;
    if (isPhoto) {
      url = '/api/photo/' + token + '/' + item.uuid;
      init = { method: 'PUT', body: item.blob, headers: { 'X-Kind': item.photoKind, 'X-Sha256': item.sha, 'X-Fallback': item.fallback ? '1' : '0', 'X-Event': item.eventUuid || '' } };
    } else {
      var body = JSON.parse(item.json);
      if (item.tries > 0) body.queued = true;
      url = '/api/event/' + token;
      init = { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } };
    }
    return fetch(url, init);
  }

  function flush() {
    if (busy) return;
    busy = true;
    var token = D.token;
    open().then(function (db) {
      return new Promise(function (ok, bad) {
        var r = db.transaction('outbox').objectStore('outbox').getAll();
        r.onsuccess = function () { ok(r.result); }; r.onerror = function () { bad(r.error); };
      });
    }).then(function (all) {
      var todo = all.filter(function (i) { return !i.sentAt && !i.error && i.token === token; }).sort(function (a, b) { return a.id - b.id; });
      var chain = Promise.resolve(true);
      todo.forEach(function (item) {
        chain = chain.then(function (goOn) {
          if (!goOn) return false;
          return send(item, token).then(function (r) {
            item.tries++;
            if (r.ok) {
              return r.json().then(function (j) {
                item.sentAt = j.recvAt || new Date().toISOString(); delete item.blob; if (j.secondDevice) D.secondDevice = true;
                D.outbox.online = true; delay = 1000;
                return tx('outbox', 'readwrite', function (s) { return s.put(item); }).then(function () { emit(); return true; });
              });
            }
            if (r.status === 410) { D.gone = true; return r.json().catch(function () { return {}; }).then(function (j) { D.goneWhy = j.cancelled ? 'cancelled' : 'expired'; emit(); return false; }); }
            if (r.status === 429 || r.status >= 500) return tx('outbox', 'readwrite', function (s) { return s.put(item); }).then(function () { throw new Error('retry'); });
            item.error = 'HTTP ' + r.status;
            return tx('outbox', 'readwrite', function (s) { return s.put(item); }).then(function () { emit(); return true; });
          }, function (err) {
            item.tries++;           // it did not go through: from now on it is marked "queued" (sent late) when it finally does
            return tx('outbox', 'readwrite', function (s) { return s.put(item); }).then(function () { throw err; });
          });
        });
      });
      return chain;
    }).then(function () { busy = false; emit(); }, function () {
      busy = false; D.outbox.online = false; emit();
      delay = Math.min(delay * 2, 300000);
      clearTimeout(timer); timer = setTimeout(flush, delay);
    });
  }

  window.addEventListener('online', function () { delay = 1000; D.outbox.kick(true); });
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') { delay = 1000; D.outbox.kick(true); } });
})();
