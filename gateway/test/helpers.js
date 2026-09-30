import worker, { hmacHex, sha256Hex } from '../src/worker.js';
import { makeEnv } from '../dev/server.js';
import { randomUUID, randomBytes } from 'node:crypto';

export const SECRET = 'test-secret-0123456789abcdef';
export const newEnv = () => makeEnv({ OFFICE_SECRET: SECRET });
export const call = (env, method, path, { body, headers } = {}) =>
  worker.fetch(new Request('http://gw.test' + path, { method, headers: { 'CF-Connecting-IP': '9.9.9.9', ...(headers || {}) }, body }), env);

export async function office(env, method, path, obj, over = {}) {
  const body = obj === undefined ? undefined : (obj instanceof Uint8Array ? obj : JSON.stringify(obj));
  const t = String(over.time ?? Math.floor(Date.now() / 1000)), nonce = over.nonce ?? randomBytes(16).toString('hex');
  const bytes = body === undefined ? new Uint8Array(0) : (typeof body === 'string' ? new TextEncoder().encode(body) : body);
  const sig = over.sig ?? await hmacHex(over.secret ?? SECRET, [method, path, t, nonce, await sha256Hex(bytes)].join('\n'));
  return call(env, method, path, { body, headers: { 'X-TO-Time': t, 'X-TO-Nonce': nonce, 'X-TO-Sig': sig } });
}

export const TOKEN = 'Tk_abcdefghijklmnopqrstuv';
export async function putCard(env, extra = {}) {
  const tokenHash = await sha256Hex(TOKEN);
  const r = await office(env, 'PUT', '/office/cards', { cards: [{ tokenHash, tripId: 'tr1', body: { no: '26-A-00001', driverName: 'Ali' }, expiresAt: Math.floor(Date.now() / 1000) + 86400, ...extra }] });
  if (r.status !== 200) throw new Error('card ' + r.status);
  return tokenHash;
}
export const ev = (over = {}) => ({ uuid: randomUUID(), v: 1, type: 'start', tripId: 'tr1', deviceId: 'device-0001', seq: 1, phoneAt: new Date().toISOString(), data: { startKm: 1000 }, ...over });
export const postEvent = (env, e, token = TOKEN) => call(env, 'POST', '/api/event/' + token, { body: JSON.stringify(e), headers: { 'Content-Type': 'application/json' } });
export const jpeg = (n = 5000) => { const b = new Uint8Array(n); b[0] = 0xff; b[1] = 0xd8; for (let i = 2; i < n; i++) b[i] = (i * 31) & 255; return b; };
export async function putPhoto(env, id, bytes, over = {}, token = TOKEN) {
  return call(env, 'PUT', `/api/photo/${token}/${id}`, { body: bytes, headers: { 'X-Kind': 'start_odo', 'X-Sha256': over.sha ?? await sha256Hex(bytes), ...(over.headers || {}) } });
}
