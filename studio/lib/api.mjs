// A tiny client for the office program's own API (keeps the session cookie), and for the local mailbox.
export class Api {
  constructor(base) { this.base = base; this.cookie = ''; }
  async call(method, path, body, { raw, headers } = {}) {
    const r = await fetch(this.base + path, {
      method, headers: { ...(raw ? { 'Content-Type': 'application/octet-stream' } : { 'Content-Type': 'application/json' }), ...(this.cookie ? { Cookie: this.cookie } : {}), ...(headers || {}) },
      body: raw || (body === undefined ? undefined : JSON.stringify(body)),
    });
    const sc = r.headers.get('set-cookie');
    if (sc) this.cookie = sc.split(';')[0];
    const ct = r.headers.get('content-type') || '';
    const data = ct.includes('json') ? await r.json() : Buffer.from(await r.arrayBuffer());
    if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${data && data.error ? data.error : ''}`);
    return data;
  }
  get(p) { return this.call('GET', p); }
  post(p, b = {}) { return this.call('POST', p, b); }
}

export const uuid = () => crypto.randomUUID();
export async function sha256Hex(buf) { return Buffer.from(await crypto.subtle.digest('SHA-256', buf)).toString('hex'); }
