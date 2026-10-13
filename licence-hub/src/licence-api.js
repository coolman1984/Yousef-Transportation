import { issueTrialCode, normalize } from './afcodes.js';
import { hex } from './auth.js';

const enc = new TextEncoder();
const now = () => Math.floor(Date.now() / 1000);
const WINDOW = 600;

const REQUIRED = ['product', 'kind', 'device', 'machine', 'nonce', 'shop', 'ref', 'version'];

async function sha256Hex(data) {
  const buf = typeof data === 'string' ? enc.encode(data) : data;
  return hex(await crypto.subtle.digest('SHA-256', buf));
}

async function limited(env, key, max) {
  const w = Math.floor(now() / WINDOW);
  const r = await env.DB.prepare('INSERT INTO rate(key, window, count) VALUES(?, ?, 1) ON CONFLICT(key, window) DO UPDATE SET count = count + 1 RETURNING count').bind(key, w).first();
  return r.count > max;
}

function products(env) {
  return new Set(String(env.LICENCE_PRODUCTS || 'trip-orders').split(',').map((s) => s.trim()).filter(Boolean));
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra },
  });
}

export async function handleLicence(request, env, url) {
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  if (await limited(env, 'lic:ip:' + ip, 120)) return json({ error: 'rate' }, 429);

  if (url.pathname === '/licence/request' && request.method === 'POST') {
    let body;
    try { body = await request.json(); } catch { return json({ error: 'json' }, 400); }
    for (const f of REQUIRED) {
      if (typeof body[f] !== 'string') return json({ field: f }, 400);
    }
    if (!products(env).has(body.product)) return json({ field: 'product' }, 400);
    if (!['trial', 'monthly', 'permanent'].includes(body.kind)) return json({ field: 'kind' }, 400);
    try { normalize(body.device.replace(/-/g, '')); } catch { return json({ field: 'device' }, 400); }

    const existing = await env.DB.prepare('SELECT id, poll_token_hash, status, reason FROM licence_requests WHERE nonce = ?').bind(body.nonce).first();
    if (existing) {
      return json({ replay: true, id: existing.id, status: existing.status, reason: existing.reason || '' });
    }

    if (body.kind === 'trial') {
      const used = await env.DB.prepare('SELECT machine FROM machine_trials WHERE machine = ?').bind(body.machine).first();
      if (used) {
        const id = crypto.randomUUID();
        const poll = 'lp_' + crypto.randomUUID().replace(/-/g, '');
        const pollHash = await sha256Hex(poll);
        const t = now();
        await env.DB.prepare(
          'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, machine, nonce, shop, ref, version, status, reason, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ).bind(id, pollHash, body.product, body.kind, body.device, body.machine, body.nonce, body.shop.slice(0, 60), body.ref.slice(0, 60), body.version.slice(0, 40), 'refused', 'already_used', t, t).run();
        return json({ id, poll_token: poll, status: 'refused', reason: 'already_used' });
      }
    }

    const id = crypto.randomUUID();
    const poll = 'lp_' + crypto.randomUUID().replace(/-/g, '');
    const pollHash = await sha256Hex(poll);
    const t = now();
    await env.DB.prepare(
      'INSERT INTO licence_requests(id, poll_token_hash, product, kind, device, machine, nonce, shop, ref, version, status, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind(id, pollHash, body.product, body.kind, body.device, body.machine, body.nonce, body.shop.slice(0, 60), body.ref.slice(0, 60), body.version.slice(0, 40), 'pending', t, t).run();

    await notifyOwner(env, body);
    return json({ id, poll_token: poll, status: 'pending' });
  }

  if (url.pathname === '/licence/status' && request.method === 'GET') {
    const id = url.searchParams.get('id') || '';
    const auth = request.headers.get('Authorization') || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (!id || !token) return json({}, 401);
    const pollHash = await sha256Hex(token);
    const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ? AND poll_token_hash = ?').bind(id, pollHash).first();
    if (!row) return json({}, 401);
    if (row.status === 'pending') return json({ status: 'pending', stage: row.stage || '' });
    if (row.status === 'approved') return json({ status: 'pending', stage: 'approved' });
    if (row.status === 'issued' && row.code) return json({ status: 'issued', code: row.code });
    if (row.status === 'refused') return json({ status: 'refused', reason: row.reason || 'refused' });
    if (row.status === 'expired') return json({ status: 'expired' });
    if (row.status === 'delivered') return json({ status: 'delivered' });
    return json({ status: row.status });
  }

  if (url.pathname === '/licence/ack' && request.method === 'POST') {
    let body;
    try { body = await request.json(); } catch { return json({ error: 'json' }, 400); }
    const id = body.id || '';
    const auth = request.headers.get('Authorization') || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (!id || !token) return json({}, 401);
    const pollHash = await sha256Hex(token);
    await env.DB.prepare('UPDATE licence_requests SET status = ?, updated_at = ? WHERE id = ? AND poll_token_hash = ?').bind('delivered', now(), id, pollHash).run();
    return json({ ok: true });
  }

  return null;
}

async function notifyOwner(env, body) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const chat = env.TELEGRAM_CHAT_ID;
  if (!token || !chat) return;
  const text = `طلب ترخيص جديد\n${body.kind} · ${body.shop || '—'}\nجهاز: ${body.device}`;
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text }),
    });
  } catch { /* optional */ }
}

export async function approveRequest(env, requestId, privateKey) {
  const row = await env.DB.prepare('SELECT * FROM licence_requests WHERE id = ?').bind(requestId).first();
  if (!row || row.status === 'refused' || row.status === 'delivered') return null;
  const days = Number(env.TRIAL_DAYS || 14);
  const signed = await issueTrialCode(privateKey, row.product, row.device, days);
  const t = now();
  await env.DB.prepare('UPDATE licence_requests SET status = ?, stage = ?, code = ?, updated_at = ? WHERE id = ?')
    .bind('issued', 'approved', signed.code, t, requestId).run();
  if (row.kind === 'trial') {
    await env.DB.prepare('INSERT INTO machine_trials(machine, request_id, at) VALUES(?, ?, ?) ON CONFLICT(machine) DO NOTHING')
      .bind(row.machine, requestId, t).run();
  }
  await env.DB.prepare(
    'INSERT INTO customers(id, shop, device, kind, serial, first_day, last_day, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(crypto.randomUUID(), row.shop || '—', row.device, row.kind, signed.serial, signed.first_day, signed.last_day, t).run();
  return signed;
}

export async function refuseRequest(env, requestId, reason = 'refused') {
  await env.DB.prepare('UPDATE licence_requests SET status = ?, reason = ?, updated_at = ? WHERE id = ?')
    .bind('refused', reason, now(), requestId).run();
}

export async function issueOfflineCustomer(env, privateKey, device, shop, productId) {
  const days = Number(env.TRIAL_DAYS || 14);
  const signed = await issueTrialCode(privateKey, productId, device, days);
  const t = now();
  await env.DB.prepare(
    'INSERT INTO customers(id, shop, device, kind, serial, first_day, last_day, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(crypto.randomUUID(), shop.slice(0, 60) || '—', signed.device, 'trial', signed.serial, signed.first_day, signed.last_day, t).run();
  return signed;
}
