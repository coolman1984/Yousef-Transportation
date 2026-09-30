/* Trip Orders - shared interface pieces: plates, trust dots, status badges, confirm dialog, forms, tables, name matching. */
(function () {
  'use strict';
  var TO = window.TO;
  var U = TO.ui = {};

  /* ---------- name matching (mirrors server/domain.py key_text) ---------- */
  U.key = function (s) {
    return String(s || '').normalize('NFKC').replace(/ـ/g, '').replace(/[ً-ٰٟ]/g, '')
      .replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه').replace(/ؤ/g, 'و').replace(/ئ/g, 'ي')
      .replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 1632; }).toLowerCase().replace(/[^\w؀-ۿ\s-]/g, ' ').replace(/\s+/g, ' ').trim();
  };

  /* ---------- small pieces ---------- */
  U.plate = function (p) {
    if (!p) return '<span class="faint">–</span>';
    var m = /^(.*?)\s*(\d+)\s*$/.exec(String(p));
    if (!m || !m[1]) return '<span class="plate"><b>' + TO.esc(p) + '</b></span>';
    return '<span class="plate" dir="rtl"><b>' + TO.esc(m[1]) + '</b><i>' + TO.esc(m[2]) + '</i></span>';
  };
  U.trust = function (colour, reasons) {
    var tip = (reasons || []).map(function (r) { return TO.t('why.' + r); }).join(' · ') || TO.t('trust.' + colour);
    return '<span class="trust ' + colour + '" title="' + TO.esc(tip) + '" role="img" aria-label="' + TO.esc(TO.t('trust.' + colour)) + '"></span>';
  };
  var STATUS_TONE = { draft: '', sent: 'info', started: 'signal', finished: 'ok', closed: 'ok', cancelled: 'bad' };
  U.status = function (s) {
    s = s || 'draft';
    return '<span class="badge ' + (STATUS_TONE[s] || '') + '">' + (s === 'started' ? '<span class="pulse-dot" style="width:.5rem;height:.5rem"></span>' : '') + TO.esc(TO.t('status.' + s)) + '</span>';
  };
  U.empty = function (icon, title, text, action) {
    return '<div class="empty"><div class="art">' + TO.icon(icon, 'lg') + '</div><h3>' + TO.esc(title) + '</h3>' + (text ? '<p>' + TO.esc(text) + '</p>' : '') + (action || '') + '</div>';
  };
  U.dt = function (s) { if (!s) return '–'; var d = new Date(s); return isNaN(d) ? TO.esc(s) : TO.fmt.date(d) + ' ' + TO.fmt.time(d); };
  U.day = function (s) { if (!s) return '–'; var d = new Date(String(s).length <= 10 ? s + 'T00:00:00' : s); return isNaN(d) ? TO.esc(s) : TO.fmt.date(d); };
  U.today = function () { var d = new Date(); return d.getFullYear() + '-' + TO.fmt.pad(d.getMonth() + 1) + '-' + TO.fmt.pad(d.getDate()); };
  U.num = function (n) { return n === null || n === undefined || n === '' ? '<span class="faint">–</span>' : '<span class="num">' + TO.fmt.num(n) + '</span>'; };

  U.confirm = function (o) {
    return new Promise(function (resolve) {
      var el = TO.dialog({ title: o.title, body: '<p>' + TO.esc(o.body || '') + '</p>' + (o.reason ? '<div class="field"><label for="cf-reason">' + TO.esc(o.reason) + '</label><input class="input" id="cf-reason" autocomplete="off"></div>' : ''),
        footer: '<button class="btn ghost" data-close>' + TO.esc(TO.t('common.cancel')) + '</button><button class="btn ' + (o.danger ? 'danger' : 'primary') + '" data-ok>' + TO.esc(o.ok || TO.t('common.done')) + '</button>' });
      var done = false;
      el.querySelector('[data-ok]').addEventListener('click', function () {
        var r = el.querySelector('#cf-reason');
        if (r && r.value.trim().length < 3) { r.focus(); r.style.borderColor = 'var(--bad)'; return; }
        done = true; var val = r ? r.value.trim() : true; TO.overlay.close(); resolve(val);
      });
      var off = function () { TO.off('overlay-closed', off); if (!done) resolve(false); };
      TO.on('overlay-closed', off);
    });
  };

  U.errorText = function (e) { return (e && e.message) || TO.t('common.error'); };

  /* ---------- forms ---------- */
  // field: { key, label, type: text|number|tel|date|datetime|select|bool|textarea|ref, entity, options, required, help, ltr, placeholder, allowNew }
  function refOptions(f) {
    var rows = TO.data.list(f.entity).filter(function (r) { return r.active !== false; });
    return rows.map(function (r) { return { v: r.id, l: f.entity === 'vehicles' ? r.plate : f.entity === 'tripCategories' ? TO.data.catName(r.id) : f.entity === 'places' ? TO.data.placeName(r) : r.name }; })
      .sort(function (a, b) { return String(a.l).localeCompare(String(b.l), TO.lang); });
  }
  U.field = function (f, value) {
    var id = 'f-' + f.key, lab = TO.t(f.label), val = value === undefined || value === null ? '' : value;
    var attrs = (f.required ? ' required' : '') + (f.ltr ? ' dir="ltr"' : '') + (f.placeholder ? ' placeholder="' + TO.esc(TO.t(f.placeholder)) + '"' : '');
    var input;
    if (f.type === 'select') {
      input = '<select class="input" id="' + id + '" name="' + f.key + '">' + (f.blank !== false ? '<option value="">–</option>' : '') + f.options.map(function (o) {
        return '<option value="' + TO.esc(o.v) + '"' + (String(val) === String(o.v) ? ' selected' : '') + '>' + TO.esc(o.l) + '</option>'; }).join('') + '</select>';
    } else if (f.type === 'ref') {
      var opts = refOptions(f), cur = opts.filter(function (o) { return o.v === val; })[0];
      input = '<input class="input" id="' + id + '" name="' + f.key + '" list="dl-' + id + '" autocomplete="off" value="' + TO.esc(cur ? cur.l : '') + '"' + attrs + ' data-ref="' + f.entity + '">' +
        '<datalist id="dl-' + id + '">' + opts.map(function (o) { return '<option value="' + TO.esc(o.l) + '"></option>'; }).join('') + '</datalist>';
    } else if (f.type === 'bool') {
      return '<div class="field"><div class="row"><span class="switch"><input type="checkbox" id="' + id + '" name="' + f.key + '"' + (val ? ' checked' : '') + '><span></span></span><label for="' + id + '" style="font-weight:600">' + TO.esc(lab) + '</label></div>' +
        (f.help ? '<span class="help">' + TO.esc(TO.t(f.help)) + '</span>' : '') + '</div>';
    } else if (f.type === 'textarea') {
      input = '<textarea class="input" id="' + id + '" name="' + f.key + '" rows="3"' + attrs + '>' + TO.esc(val) + '</textarea>';
    } else {
      var type = f.type === 'datetime' ? 'datetime-local' : (f.type || 'text');
      input = '<input class="input" id="' + id + '" name="' + f.key + '" type="' + type + '"' + (type === 'number' ? ' inputmode="numeric" step="any"' : '') + ' value="' + TO.esc(type === 'datetime-local' ? String(val).slice(0, 16) : val) + '"' + attrs + (f.suggest ? ' list="dl-' + id + '" autocomplete="off"' : '') + '>' +
        (f.suggest ? '<datalist id="dl-' + id + '">' + f.suggest().map(function (x) { return '<option value="' + TO.esc(x) + '"></option>'; }).join('') + '</datalist>' : '');
    }
    return '<div class="field"><label for="' + id + '">' + TO.esc(lab) + (f.required ? ' <span class="faint">*</span>' : '') + '</label>' + input + (f.help ? '<span class="help">' + TO.esc(TO.t(f.help)) + '</span>' : '') + '</div>';
  };
  U.fields = function (fields, values) { return fields.map(function (f) { return U.field(f, (values || {})[f.key]); }).join(''); };

  // returns { values, missing: [labels], newRefs: [{field, entity, text}] }
  U.read = function (root, fields) {
    var values = {}, missing = [], newRefs = [];
    fields.forEach(function (f) {
      var el = root.querySelector('[name="' + f.key + '"]');
      if (!el) return;
      var v;
      if (f.type === 'bool') v = el.checked;
      else if (f.type === 'number') v = el.value === '' ? null : Number(el.value);
      else if (f.type === 'datetime') v = el.value ? el.value + ':00' : '';
      else if (f.type === 'ref') {
        var text = el.value.trim(), hit = refOptions(f).filter(function (o) { return U.key(o.l) === U.key(text); })[0];
        if (hit) v = hit.v; else if (text && f.allowNew) { v = ''; newRefs.push({ field: f.key, entity: f.entity, text: text }); } else { v = ''; if (text) missing.push(TO.t(f.label)); }
      } else v = el.value.trim();
      if (f.required && (v === '' || v === null)) missing.push(TO.t(f.label));
      values[f.key] = v;
    });
    return { values: values, missing: missing, newRefs: newRefs };
  };

  /* ---------- table ---------- */
  // cols: [{ h: headerKey, cell: function(row) -> html, cls }]
  U.table = function (cols, rows, opts) {
    opts = opts || {};
    return '<div class="table-wrap"><table class="tbl"><thead><tr>' + cols.map(function (c) { return '<th' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + TO.esc(TO.t(c.h)) + '</th>'; }).join('') + '</tr></thead><tbody>' +
      rows.map(function (r, i) {
        return '<tr style="--i:' + Math.min(i, 14) + '"' + (opts.rowAttr ? ' ' + opts.rowAttr(r) : '') + (opts.click ? ' tabindex="0" role="button" style="cursor:pointer;--i:' + Math.min(i, 14) + '"' : '') + '>' +
          cols.map(function (c) { return '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + c.cell(r) + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
  };

  /* ---------- run a save with the standard feedback ---------- */
  U.run = function (promise, okKey, btn) {
    if (btn) btn.disabled = true;
    return promise.then(function (r) { if (okKey) TO.toast(TO.t(okKey)); return r; }, function (e) {
      if (btn) btn.disabled = false;
      TO.toast(U.errorText(e), 'bad', 5000);
      throw e;
    });
  };
})();
