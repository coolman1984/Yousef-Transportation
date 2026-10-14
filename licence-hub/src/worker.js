import {
  handleLicence, approveRequest, refuseRequest, issueOfflineCustomer, purgeStaleCodes,
  REASON_PAID_IN_STUDIO, ownerCapabilities, loadSigningKeys, products, defaultProduct, ownerProductsPayload,
  licencePathname, currentTerm,
} from './licence-api.js';
import {
  SESSION_COOKIE, CSRF_COOKIE, verifyPassword, parseCookies, cookieHeader, loadSession, createSession,
  destroySession, loginLimited, csrfOk,
} from './auth.js';

const HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
  'Cache-Control': 'no-store',
};

const now = () => Math.floor(Date.now() / 1000);

function withSecurityHeaders(response) {
  const headers = new Headers(response.headers);
  Object.entries(HEADERS).forEach(([k, v]) => headers.set(k, v));
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

function html(body, status = 200, extra = {}) {
  return new Response(body, { status, headers: { ...HEADERS, 'Content-Type': 'text/html; charset=utf-8', ...extra } });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...HEADERS, 'Content-Type': 'application/json; charset=utf-8' } });
}

async function fetchOwnerAsset(env, request, url) {
  const res = await env.ASSETS.fetch(request);
  return withSecurityHeaders(res);
}

async function ownerApi(request, env, url, session) {
  const path = url.pathname.replace(/^\/owner\/api/, '') || '/';

  if (path === '/session' && request.method === 'GET') {
    return json({ csrf: session.csrf, expires: session.expires_at });
  }
  if (path === '/capabilities' && request.method === 'GET') {
    return json(ownerCapabilities(env));
  }
  if (path === '/issued' && request.method === 'GET') {
    const id = url.searchParams.get('id') || '';
    if (!id) return json({ error: 'id' }, 400);
    const row = await env.DB.prepare('SELECT id, code, status, device, product, licence_tier FROM licence_requests WHERE id = ?').bind(id).first();
    if (!row || row.status !== 'issued' || !row.code) return json({ error: 'not_found' }, 404);
    return json({ ok: true, code: row.code, device: row.device });
  }
  if (path === '/undelivered' && request.method === 'GET') {
    const rows = await env.DB.prepare(
      "SELECT id, shop, device, code, product, licence_tier, updated_at FROM licence_requests WHERE status = 'issued' AND code IS NOT NULL ORDER BY updated_at DESC LIMIT 50",
    ).all();
    return json({ items: rows.results || [] });
  }
  if (path === '/pending' && request.method === 'GET') {
    const rows = await env.DB.prepare(
      "SELECT r.id, r.kind, r.product, r.shop, r.device, r.machine, r.version, r.created_at, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS has_customer FROM licence_requests r LEFT JOIN customers c ON c.device = r.device AND c.product = r.product WHERE r.status IN ('pending', 'approved') ORDER BY r.created_at ASC LIMIT 50",
    ).all();
    return json({ items: rows.results || [] });
  }
  if (path === '/customers' && request.method === 'GET') {
    const rows = await env.DB.prepare(
      `SELECT c.shop, c.device, c.product, c.kind, c.licence_tier, c.licence_expiry, c.last_day, c.created_at
       FROM customers c
       ORDER BY c.created_at DESC LIMIT 200`,
    ).bind().all();
    const items = [];
    for (const c of rows.results || []) {
      const term = await currentTerm(env, c.product, c.device);
      const licenceTier = term?.tier || c.licence_tier || c.kind || '';
      const licenceExpiry = term?.until || c.licence_expiry || c.last_day || '';
      const lastDay = licenceExpiry || c.last_day || '';
      let daysLeft = null;
      if (lastDay && licenceTier !== 'permanent') {
        const end = Date.parse(lastDay + 'T12:00:00Z');
        daysLeft = Math.max(0, Math.floor((end - Date.now()) / 86400000) + 1);
      }
      items.push({
        shop: c.shop,
        device: c.device,
        product: c.product,
        kind: licenceTier,
        licence_tier: licenceTier,
        licence_expiry: licenceExpiry,
        last_day: lastDay,
        created_at: c.created_at,
        days_left: daysLeft,
      });
    }
    return json({ items });
  }
  if (path === '/products' && request.method === 'GET') {
    const payload = ownerProductsPayload(env);
    if (!payload) return json({ error: 'config' }, 503);
    return json(payload);
  }

  if (request.method !== 'POST') return json({ error: 'method' }, 405);
  let body = {};
  try { body = await request.json(); } catch { body = {}; }
  if (!csrfOk(session, request, body)) return json({ error: 'csrf' }, 403);

  if (path === '/approve') {
    const reqRow = await env.DB.prepare('SELECT product FROM licence_requests WHERE id = ?').bind(body.id || '').first();
    const keys = await loadSigningKeys(env, reqRow?.product || defaultProduct(env));
    try {
      const signed = await approveRequest(env, body.id, keys, {
        force: body.force === true,
        reissue: body.reissue === true,
        confirm_downgrade: body.confirm_downgrade === true,
        grant: body.grant,
        preset: body.preset,
        paid_until: body.paid_until,
      });
      if (!signed) return json({ error: 'not_found' }, 404);
      if (signed.refused) {
        if (signed.reason === 'paid_signing_key_missing') {
          return json({ error: 'paid_key_missing' }, 503);
        }
        const msg = signed.reason === REASON_PAID_IN_STUDIO ? 'paid_in_studio' : signed.reason;
        return json({ error: signed.reason || REASON_PAID_IN_STUDIO, message: msg }, 400);
      }
      return json({ ok: true, code: signed.code });
    } catch (e) {
      if (e?.message === 'bad_device_code') return json({ error: 'bad_device', message: e.message }, 400);
      if (e?.message === 'bad_grant') return json({ error: 'bad_grant' }, 400);
      if (e?.message === 'date_out_of_range') return json({ error: 'date_out_of_range' }, 400);
      if (e?.message === 'paid_until_before_first') return json({ error: 'bad_paid_until', message: e.message }, 400);
      if (e?.message === 'downgrade') {
        return json({ error: 'downgrade', current: e.current || undefined }, 409);
      }
      if (e?.message === 'downgrade_forbidden') {
        return json({ error: 'downgrade_forbidden', current: e.current || undefined }, 409);
      }
      if (e?.message === 'reissue_confirm') return json({ error: 'reissue_confirm' }, 409);
      if (e?.message === 'trial_expired') return json({ error: 'trial_expired' }, 409);
      if (e?.message === 'no_signing_key') return json({ error: 'config' }, 503);
      throw e;
    }
  }
  if (path === '/refuse') {
    await refuseRequest(env, body.id, body.reason || 'refused');
    return json({ ok: true });
  }
  if (path === '/offline') {
    const device = String(body.device || '').trim();
    const shop = String(body.shop || '').trim();
    if (!device) return json({ error: 'device' }, 400);
    const allowed = products(env);
    if (!allowed) return json({ error: 'config' }, 503);
    const fallback = defaultProduct(env);
    if (!fallback) return json({ error: 'config' }, 503);
    const product = String(body.product || fallback).trim() || fallback;
    if (!allowed.has(product)) return json({ error: 'product' }, 400);
    const keys = await loadSigningKeys(env, product);
    try {
      const signed = await issueOfflineCustomer(env, keys, device, shop, product, {
        force: body.force === true,
        reissue: body.reissue === true,
        confirm_downgrade: body.confirm_downgrade === true,
        grant: body.grant,
        preset: body.preset,
        paid_until: body.paid_until,
      });
      return json({ ok: true, code: signed.code, device: signed.device });
    } catch (e) {
      if (e?.message === 'already_used') return json({ error: 'already_used' }, 400);
      if (e?.message === 'grant_conflict') return json({ error: 'grant_conflict' }, 409);
      if (e?.message === 'bad_device_code') return json({ error: 'bad_device' }, 400);
      if (e?.message === 'paid_signing_key_missing') return json({ error: 'paid_key_missing' }, 400);
      if (e?.message === 'bad_grant') return json({ error: 'bad_grant' }, 400);
      if (e?.message === 'date_out_of_range') return json({ error: 'date_out_of_range' }, 400);
      if (e?.message === 'paid_until_before_first') return json({ error: 'bad_paid_until', message: e.message }, 400);
      if (e?.message === 'downgrade') {
        return json({ error: 'downgrade', current: e.current || undefined }, 409);
      }
      if (e?.message === 'downgrade_forbidden') {
        return json({ error: 'downgrade_forbidden', current: e.current || undefined }, 409);
      }
      if (e?.message === 'reissue_confirm') return json({ error: 'reissue_confirm' }, 409);
      if (e?.message === 'trial_expired') return json({ error: 'trial_expired' }, 409);
      if (e?.message === 'no_signing_key') return json({ error: 'config' }, 503);
      throw e;
    }
  }
  return json({ error: 'not_found' }, 404);
}

const PUBLIC_OWNER_PATHS = new Set([
  '/owner/login.html',
  '/owner/login.js',
  '/owner/style.css',
]);

async function ownerPages(request, env, url) {
  const sessionSecret = env.SESSION_SECRET;
  if (!sessionSecret) return html('<p>SESSION_SECRET missing</p>', 503);

  if (url.pathname === '/owner/login' && request.method === 'POST') {
    const ip = request.headers.get('CF-Connecting-IP') || 'local';
    if (await loginLimited(env, ip)) return html('<p>Too many attempts</p>', 429);
    const form = await request.formData();
    const password = String(form.get('password') || '');
    if (!env.OWNER_PASSWORD_HASH || !(await verifyPassword(password, env.OWNER_PASSWORD_HASH))) {
      return Response.redirect(new URL('/owner/login.html?bad=1', url.origin).toString(), 303);
    }
    const hours = Number(env.SESSION_HOURS || 8);
    const sess = await createSession(env, sessionSecret, hours);
    const loginHeaders = new Headers({ Location: '/owner/' });
    loginHeaders.append('Set-Cookie', cookieHeader(SESSION_COOKIE, sess.signed, hours * 3600));
    loginHeaders.append('Set-Cookie', cookieHeader(CSRF_COOKIE, sess.csrf, hours * 3600, false));
    return new Response(null, { status: 303, headers: loginHeaders });
  }

  if (url.pathname === '/owner/logout' && request.method === 'POST') {
    const session = await loadSession(env, sessionSecret, request);
    if (session) await destroySession(env, session.id);
    const headers = { Location: '/owner/login.html' };
    if (session) headers['Set-Cookie'] = cookieHeader(SESSION_COOKIE, '', 0);
    return new Response(null, { status: 303, headers });
  }

  if (url.pathname.startsWith('/owner/api/')) {
    const session = await loadSession(env, sessionSecret, request);
    if (!session) return json({ error: 'auth' }, 401);
    return ownerApi(request, env, url, session);
  }

  if (url.pathname === '/owner/index.html') {
    return Response.redirect(new URL('/owner/', url.origin).toString(), 308);
  }

  if (url.pathname === '/owner/' || url.pathname === '/owner/customers.html' || url.pathname === '/owner/offline.html') {
    const session = await loadSession(env, sessionSecret, request);
    if (!session) return Response.redirect(new URL('/owner/login.html', url.origin).toString(), 302);
    const assetPath = url.pathname === '/owner/' ? '/owner/index.html' : url.pathname;
    return fetchOwnerAsset(env, new Request(new URL(assetPath, url.origin)), url);
  }

  if (url.pathname.startsWith('/owner/')) {
    if (PUBLIC_OWNER_PATHS.has(url.pathname)) {
      return fetchOwnerAsset(env, request, url);
    }
    const session = await loadSession(env, sessionSecret, request);
    if (!session) return Response.redirect(new URL('/owner/login.html', url.origin).toString(), 302);
    return fetchOwnerAsset(env, request, url);
  }
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      const licencePath = licencePathname(url.pathname);
      if (licencePath.startsWith('/licence/')) {
        const licUrl = new URL(url);
        licUrl.pathname = licencePath;
        const res = await handleLicence(request, env, licUrl);
        if (res) {
          Object.entries(HEADERS).forEach(([k, v]) => res.headers.set(k, v));
          return res;
        }
      }
      const owner = await ownerPages(request, env, url);
      if (owner) return owner;
      if (url.pathname === '/') return html('<p>Licence hub</p>');
      return new Response('Not found', { status: 404, headers: HEADERS });
    } catch (e) {
      return json({ error: 'server' }, 500);
    }
  },
  async scheduled(event, env) {
    await purgeStaleCodes(env);
  },
};
