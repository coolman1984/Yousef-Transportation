'use strict';

async function api(path, opts) {
  const r = await fetch('/owner/api' + path, { credentials: 'same-origin', ...opts });
  if (r.status === 401) { location.href = '/owner/login.html'; return null; }
  return r.json();
}

let csrf = '';

async function session() {
  const s = await api('/session');
  if (s) csrf = s.csrf || '';
  return s;
}

function headers() {
  return { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf };
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
  data.items.forEach((item) => {
    const li = document.createElement('li');
    const when = new Date(item.created_at * 1000).toLocaleString('ar-EG');
    const kindLabel = kindLabelAr(item.kind);
    const paidNote = item.kind !== 'trial' ? '<div class="err">الاشتراك الشهري والدائم يُصدر من Licence Studio فقط — لا يمكن الموافقة من هنا.</div>' : '';
    const usedNote = item.has_customer ? '<div class="err">هذا الجهاز لديه عميل مسجّل — الموافقة العادية مرفوضة؛ استخدم «إعادة إصدار» إن فُقد الكود.</div>' : '';
    li.innerHTML = '<div><strong>' + escape(item.shop || '—') + '</strong><div class="muted">' + escape(kindLabel) + ' · ' + escape(item.device) + '</div>' + paidNote + usedNote + '<div class="muted">' + when + '</div></div>';
    const row = document.createElement('div');
    row.className = 'row';
    const ok = document.createElement('button');
    ok.className = 'btn primary';
    ok.type = 'button';
    ok.textContent = 'موافق — تجربة';
    ok.disabled = item.kind !== 'trial';
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      const force = item.has_customer && confirm('إعادة إصدار تجربة لهذا الجهاز؟ (فقدان الكود فقط)');
      const res = await api('/approve', { method: 'POST', headers: headers(), body: JSON.stringify({ id: item.id, csrf, force }) });
      if (res && res.error === 'paid_in_licence_studio') {
        alert('هذا الطلب اشتراك مدفوع — استخدم Licence Studio على جهاز المكتب.');
      } else if (res && res.error === 'bad_device') {
        alert('رمز الجهاز غير صالح — ارفض الطلب.');
        ok.disabled = false;
        return;
      } else if (res && res.error && !res.ok) {
        alert('تعذّرت الموافقة: ' + res.error);
        ok.disabled = false;
        return;
      }
      if (res && res.ok && res.code) {
        showIssuedCode(host, res.code, item.id);
      }
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

export function wireOffline(form, out) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await session();
    out.hidden = true;
    const device = form.device.value.trim();
    const shop = form.shop.value.trim();
    const data = await api('/offline', { method: 'POST', headers: headers(), body: JSON.stringify({ device, shop, csrf }) });
    if (!data || !data.ok) {
      out.textContent = 'تعذّر إصدار الكود.';
      out.hidden = false;
      return;
    }
    out.innerHTML = '<p class="muted">اقرأ هذا الكود للعميل:</p><p class="big-code" id="issued-code"></p><button type="button" class="btn" id="copy-code">نسخ</button>';
    out.querySelector('#issued-code').textContent = data.code;
    out.querySelector('#copy-code').addEventListener('click', () => {
      navigator.clipboard.writeText(data.code);
    });
    out.hidden = false;
  });
}

function escape(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function kindLabelAr(kind) {
  if (kind === 'trial') return 'تجربة';
  if (kind === 'monthly') return 'شهري (Licence Studio)';
  if (kind === 'permanent') return 'دائم (Licence Studio)';
  return kind;
}
