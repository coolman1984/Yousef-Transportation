import { handleLicence, approveRequest, refuseRequest, issueOfflineCustomer } from './licence-api.js';
import { importSigningKey } from './afcodes.js';
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

function html(body, status = 200, extra = {}) {
  return new Response(body, { status, headers: { ...HEADERS, 'Content-Type': 'text/html; charset=utf-8', ...extra } });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...HEADERS, 'Content-Type': 'application/json; charset=utf-8' } });
}

async function signingKey(env) {
  if (!env.LICENCE_SIGNING_KEY) throw new Error('no_signing_key');
  return importSigningKey(env.LICENCE_SIGNING_KEY);
}

async function ownerApi(request, env, url, session) {
  const path = url.pathname.replace(/^\/owner\/api/, '') || '/';

  if (path === '/session' && request.method === 'GET') {
    return json({ csrf: session.csrf, expires: session.expires_at });
  }
  if (path === '/pending' && request.method === 'GET') {
    const rows = await env.DB.prepare(
      "SELECT id, kind, shop, device, machine, version, created_at FROM licence_requests WHERE status IN ('pending', 'approved') ORDER BY created_at DESC LIMIT 50",
    ).all();
    return json({ items: rows.results || [] });
  }
  if (path === '/customers' && request.method === 'GET') {
    const rows = await env.DB.prepare('SELECT shop, device, kind, first_day, last_day, created_at FROM customers ORDER BY created_at DESC LIMIT 200').all();
    const items = (rows.results || []).map((r) => {
      let daysLeft = null;
      if (r.last_day) {
        const end = Date.parse(r.last_day + 'T12:00:00Z');
        daysLeft = Math.max(0, Math.floor((end - Date.now()) / 86400000) + 1);
      }
      return { ...r, days_left: daysLeft };
    });
    return json({ items });
  }

  if (request.method !== 'POST') return json({ error: 'method' }, 405);
  let body = {};
  try { body = await request.json(); } catch { body = {}; }
  if (!csrfOk(session, request, body)) return json({ error: 'csrf' }, 403);

  if (path === '/approve') {
    const key = await signingKey(env);
    const signed = await approveRequest(env, body.id, key);
    if (!signed) return json({ error: 'not_found' }, 404);
    return json({ ok: true, code: signed.code });
  }
  if (path === '/refuse') {
    await refuseRequest(env, body.id, body.reason || 'refused');
    return json({ ok: true });
  }
  if (path === '/offline') {
    const device = String(body.device || '').trim();
    const shop = String(body.shop || '').trim();
    if (!device) return json({ error: 'device' }, 400);
    const key = await signingKey(env);
    const signed = await issueOfflineCustomer(env, key, device, shop, 'trip-orders');
    return json({ ok: true, code: signed.code, device: signed.device });
  }
  return json({ error: 'not_found' }, 404);
}

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
    return new Response(null, {
      status: 303,
      headers: {
        Location: '/owner/login.html',
        'Set-Cookie': cookieHeader(SESSION_COOKIE, '', 0),
      },
    });
  }

  if (url.pathname.startsWith('/owner/api/')) {
    const session = await loadSession(env, sessionSecret, request);
    if (!session) return json({ error: 'auth' }, 401);
    return ownerApi(request, env, url, session);
  }

  if (url.pathname === '/owner/' || url.pathname === '/owner/index.html') {
    const session = await loadSession(env, sessionSecret, request);
    if (!session) return Response.redirect(new URL('/owner/login.html', url.origin).toString(), 302);
    return env.ASSETS.fetch(new URL('/owner/index.html', url.origin));
  }
  if (url.pathname.startsWith('/owner/')) {
    return env.ASSETS.fetch(request);
  }
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith('/licence/')) {
        const res = await handleLicence(request, env, url);
        if (res) {
          Object.entries(HEADERS).forEach(([k, v]) => res.headers.set(k, v));
          return res;
        }
      }
      const owner = await ownerPages(request, env, url);
      if (owner) return owner;
      if (url.pathname === '/') return html('<p>Trip Orders licence hub</p>');
      return new Response('Not found', { status: 404, headers: HEADERS });
    } catch (e) {
      return json({ error: 'server' }, 500);
    }
  },
};
