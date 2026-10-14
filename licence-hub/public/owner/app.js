'use strict';

async function api(path, opts) {
  const r = await fetch('/owner/api' + path, { credentials: 'same-origin', ...opts });
  if (r.status === 401) { location.href = '/owner/login.html'; return null; }
  return r.json();
}

let csrf = '';
let paidAvailable = false;

async function session() {
  const s = await api('/session');
  if (s) csrf = s.csrf || '';
  const cap = await api('/capabilities');
  if (cap) paidAvailable = Boolean(cap.paid_available);
  return s;
}

function headers() {
  return { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf };
}

function escape(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function kindLabelAr(kind) {
  if (kind === 'trial') return 'تجربة';
  if (kind === 'monthly') return 'اشتراك مدفوع';
  if (kind === 'permanent') return 'دائم';
  return kind;
}

function tierPickerHtml(disabledPaid, customDate) {
  const paidOff = disabledPaid ? ' disabled' : '';
  const paidMsg = disabledPaid
    ? '<p class="err">إصدار المدفوع غير متاح — أضف PAID_SIGNING_KEY في Cloudflare.</p>' : '';
  return paidMsg + '<fieldset class="tier-pick" data-tier-form>' +
    '<legend>نوع الترخيص</legend>' +
    '<label class="tier-opt"><input type="radio" name="tier" value="trial" checked> تجربة ١٤ يوماً</label>' +
    '<label class="tier-opt"><input type="radio" name="tier" value="paid"' + paidOff + '> مدفوع حتى تاريخ</label>' +
    '<div class="tier-paid" data-paid-opts hidden>' +
    '<div class="row wrap">' +
    '<button type="button" class="btn sm" data-preset="1m">شهر</button>' +
    '<button type="button" class="btn sm" data-preset="3m">٣ أشهر</button>' +
    '<button type="button" class="btn sm" data-preset="6m">٦ أشهر</button>' +
    '<button type="button" class="btn sm" data-preset="1y">سنة</button>' +
    '</div>' +
    '<div class="field"><label>تاريخ الانتهاء</label><input type="date" data-paid-until dir="ltr" value="' + escape(customDate || '') + '"></div>' +
    '</div>' +
    '<label class="tier-opt"><input type="radio" name="tier" value="permanent"' + paidOff + '> دائم</label>' +
    '</fieldset>';
}

function wireTierForm(root) {
  const form = root.querySelector('[data-tier-form]');
  if (!form) return;
  const paidBox = form.querySelector('[data-paid-opts]');
  form.querySelectorAll('input[name="tier"]').forEach((radio) => {
    radio.addEventListener('change', () => {
      if (paidBox) paidBox.hidden = form.querySelector('input[value="paid"]:checked') == null;
    });
  });
  form.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const preset = btn.getAttribute('data-preset');
      const months = { '1m': 1, '3m': 3, '6m': 6, '1y': 12 }[preset];
      const d = new Date();
      d.setUTCMonth(d.getUTCMonth() + months);
      const iso = d.toISOString().slice(0, 10);
      const inp = form.querySelector('[data-paid-until]');
      if (inp) inp.value = iso;
      const paidRadio = form.querySelector('input[value="paid"]');
      if (paidRadio) paidRadio.checked = true;
      if (paidBox) paidBox.hidden = false;
    });
  });
}

function readGrant(root) {
  const form = root.querySelector('[data-tier-form]');
  if (!form) return { grant: 'trial' };
  const tier = form.querySelector('input[name="tier"]:checked');
  const val = tier ? tier.value : 'trial';
  if (val === 'permanent') return { grant: 'permanent' };
  if (val === 'paid') {
    const until = form.querySelector('[data-paid-until]');
    return { grant: 'paid', paid_until: until ? until.value : '' };
  }
  return { grant: 'trial' };
}

export function showIssuedCode(host, code, requestId) {
  const panel = host.querySelector('[data-issued]');
  if (!panel) return;
  panel.hidden = false;
  panel.innerHTML = '<p class="muted">اقرأ هذا الكود للعميل:</p><p class="big-code" dir="ltr">' + escape(code) + '</p><button type="button" class="btn" data-copy>نسخ</button><button type="button" class="btn" data-dismiss>إغلاق</button>';
  panel.querySelector('[data-copy]').addEventListener('click', () => navigator.clipboard.writeText(code));
  panel.querySelector('[data-dismiss]').addEventListener('click', () => { panel.hidden = true; panel.innerHTML = ''; });
  if (requestId) panel.dataset.requestId = requestId;
}

export async function loadUndelivered(host) {
  await session();
  const data = await api('/undelivered');
  if (!data) return;
  const wrap = host.querySelector('[data-undelivered-wrap]');
  const ul = host.querySelector('[data-undelivered]');
  if (!wrap || !ul) return;
  ul.innerHTML = '';
  if (!data.items.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  data.items.forEach((item) => {
    const li = document.createElement('li');
    const when = new Date(item.updated_at * 1000).toLocaleString('ar-EG');
    li.innerHTML = '<div><strong>' + escape(item.shop || '—') + '</strong><div class="muted" dir="ltr">' + escape(item.device) + '</div><div class="muted">' + when + '</div></div>';
    const btn = document.createElement('button');
    btn.className = 'btn primary';
    btn.type = 'button';
    btn.textContent = 'عرض الكود';
    btn.addEventListener('click', () => showIssuedCode(host, item.code, item.id));
    li.append(btn);
    ul.append(li);
  });
}

export async function loadPending(host) {
  await session();
  await loadUndelivered(host);
  const data = await api('/pending');
  if (!data) return;
  const ul = host.querySelector('[data-pending]');
  ul.innerHTML = '';
  if (!data.items.length) {
    ul.innerHTML = '<li class="muted">لا توجد طلبات معلّقة.</li>';
    return;
  }
  const disablePaid = !paidAvailable;
  data.items.forEach((item) => {
    const li = document.createElement('li');
    const when = new Date(item.created_at * 1000).toLocaleString('ar-EG');
    const kindLabel = kindLabelAr(item.kind);
    const usedNote = item.has_customer ? '<div class="err">هذا الجهاز لديه عميل مسجّل — استخدم «إعادة إصدار» إن فُقد الكود.</div>' : '';
    li.innerHTML = '<div><strong>' + escape(item.shop || '—') + '</strong><div class="muted">' + escape(kindLabel) + ' · <span dir="ltr">' + escape(item.device) + '</span></div>' + usedNote + '<div class="muted">' + when + '</div></div>';
    li.innerHTML += tierPickerHtml(disablePaid);
    wireTierForm(li);
    const row = document.createElement('div');
    row.className = 'row';
    const ok = document.createElement('button');
    ok.className = 'btn primary';
    ok.type = 'button';
    ok.textContent = 'موافقة — إصدار الكود';
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      const grant = readGrant(li);
      const force = item.has_customer && confirm('إعادة إصدار لهذا الجهاز؟ (فقدان الكود فقط)');
      const res = await api('/approve', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ id: item.id, csrf, force, ...grant }),
      });
      if (res && res.message === 'paid_key_missing') {
        alert('إصدار المدفوع غير متاح على الخادم — راجع PAID_SIGNING_KEY.');
        ok.disabled = false;
        return;
      }
      if (res && res.error === 'bad_device') {
        alert('رمز الجهاز غير صالح — ارفض الطلب.');
        ok.disabled = false;
        return;
      }
      if (res && res.error && !res.ok) {
        alert('تعذّرت الموافقة: ' + res.error);
        ok.disabled = false;
        return;
      }
      if (res && res.ok && res.code) showIssuedCode(host, res.code, item.id);
      loadPending(host);
    });
    const no = document.createElement('button');
    no.className = 'btn bad';
    no.type = 'button';
    no.textContent = 'رفض';
    no.addEventListener('click', async () => {
      no.disabled = true;
      await api('/refuse', { method: 'POST', headers: headers(), body: JSON.stringify({ id: item.id, csrf }) });
      loadPending(host);
    });
    row.append(ok, no);
    li.append(row);
    ul.append(li);
  });
}

export async function loadCustomers(host) {
  await session();
  const data = await api('/customers');
  if (!data) return;
  const ul = host.querySelector('[data-customers]');
  ul.innerHTML = '';
  data.items.forEach((item) => {
    const li = document.createElement('li');
    const left = item.days_left != null ? (' · باقي ' + item.days_left + ' يوم') : '';
    li.innerHTML = '<div><strong>' + escape(item.shop) + '</strong><div class="muted" dir="ltr">' + escape(item.device) + left + '</div></div>';
    ul.append(li);
  });
}

export function wireOffline(form, out, tierHost) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await session();
    out.hidden = true;
    const device = form.device.value.trim();
    const shop = form.shop.value.trim();
    const grant = readGrant(tierHost || form.closest('.card') || document);
    const data = await api('/offline', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ device, shop, csrf, ...grant }),
    });
    if (!data || !data.ok) {
      out.textContent = data && data.error === 'paid_key_missing'
        ? 'إصدار المدفوع غير متاح — أضف PAID_SIGNING_KEY.'
        : 'تعذّر إصدار الكود.';
      out.hidden = false;
      return;
    }
    out.innerHTML = '<p class="muted">اقرأ هذا الكود للعميل:</p><p class="big-code" id="issued-code"></p><button type="button" class="btn" data-copy>نسخ</button>';
    out.querySelector('#issued-code').textContent = data.code;
    out.querySelector('[data-copy]').addEventListener('click', () => navigator.clipboard.writeText(data.code));
    out.hidden = false;
  });
}

export function mountOfflineTier(host) {
  const slot = host.querySelector('[data-tier-slot]');
  if (!slot) return;
  session().then(() => {
    slot.innerHTML = tierPickerHtml(!paidAvailable);
    wireTierForm(slot);
  });
}
