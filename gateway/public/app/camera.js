/* Camera: live capture (getUserMedia) when possible; otherwise a file chooser, which is marked "fallback" so the office knows.
   Every photo is resized (long side 1280), stamped along the bottom with order no., plate and time, and compressed to ~250 KB. */
(function () {
  'use strict';
  var D = window.D;
  var MAX_SIDE = 1280, TARGET = 250 * 1024;

  function stampText(s) {
    var d = new Date(), p = function (n) { return ('0' + n).slice(-2); };
    return [s.no, s.plate, d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())].filter(Boolean).join('  ·  ');
  }
  function toJpeg(source, w, h, stamp) {
    var scale = Math.min(1, MAX_SIDE / Math.max(w, h)), cw = Math.round(w * scale), ch = Math.round(h * scale);
    var c = document.createElement('canvas'); c.width = cw; c.height = ch;
    var g = c.getContext('2d'); g.drawImage(source, 0, 0, cw, ch);
    var band = Math.max(34, Math.round(ch * 0.07));
    g.fillStyle = 'rgba(0,0,0,.62)'; g.fillRect(0, ch - band, cw, band);
    g.fillStyle = '#fff'; g.font = 'bold ' + Math.round(band * 0.56) + 'px sans-serif'; g.textBaseline = 'middle'; g.direction = 'ltr'; g.textAlign = 'left';
    g.fillText(stampText(stamp), 12, ch - band / 2);
    return new Promise(function (ok) {
      var q = 0.82;
      (function step() {
        c.toBlob(function (b) {
          if (b.size > TARGET && q > 0.4) { q -= 0.1; step(); } else ok(b);
        }, 'image/jpeg', q);
      })();
    });
  }
  function sha256(blob) {
    return blob.arrayBuffer().then(function (buf) { return crypto.subtle.digest('SHA-256', buf); }).then(function (h) {
      return Array.prototype.map.call(new Uint8Array(h), function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
    });
  }
  function finish(source, w, h, stamp, fallback) {
    return toJpeg(source, w, h, stamp).then(function (blob) { return sha256(blob).then(function (sha) { return { blob: blob, sha: sha, fallback: !!fallback, url: URL.createObjectURL(blob) }; }); });
  }
  function fromFile(stamp) {
    return new Promise(function (ok, bad) {
      var inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.setAttribute('capture', 'environment'); inp.style.display = 'none';
      document.body.appendChild(inp);
      inp.addEventListener('change', function () {
        var f = inp.files && inp.files[0]; inp.remove();
        if (!f) { bad(new Error('cancel')); return; }
        createImageBitmap(f).then(function (bmp) { return finish(bmp, bmp.width, bmp.height, stamp, true); }).then(ok, bad);
      });
      inp.click();
    });
  }
  function live(stamp) {
    return new Promise(function (ok, bad) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { bad(new Error('nocamera')); return; }
      navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } }, audio: false }).then(function (stream) {
        var box = document.createElement('div'); box.className = 'cam';
        box.innerHTML = '<video playsinline muted autoplay></video><div class="cam-bar"><button type="button" class="btn ghost" data-x>' + D.esc(D.t('cam_cancel')) + '</button><button type="button" class="shutter" data-s aria-label="' + D.esc(D.t('cam_take')) + '"></button><button type="button" class="btn ghost" data-g>' + D.esc(D.t('cam_gallery')) + '</button></div>';
        document.body.appendChild(box);
        var v = box.querySelector('video'); v.srcObject = stream;
        var stop = function () { stream.getTracks().forEach(function (t) { t.stop(); }); box.remove(); };
        box.querySelector('[data-x]').onclick = function () { stop(); bad(new Error('cancel')); };
        box.querySelector('[data-g]').onclick = function () { stop(); fromFile(stamp).then(ok, bad); };
        box.querySelector('[data-s]').onclick = function () {
          if (!v.videoWidth) return;
          finish(v, v.videoWidth, v.videoHeight, stamp, false).then(function (r) { stop(); ok(r); }, function (e) { stop(); bad(e); });
        };
      }, function () { bad(new Error('nocamera')); });
    });
  }
  /* capture({no, plate}) -> {blob, sha, fallback, url}; rejects with Error('cancel') when the driver backs out */
  D.camera = {
    capture: function (stamp) {
      return live(stamp).catch(function (e) {
        if (e && e.message === 'cancel') throw e;
        return fromFile(stamp);
      });
    },
  };
})();
