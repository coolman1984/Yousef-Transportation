// Local gateway for development and tests: the real worker code + the D1 stand-in + the public folder.
//   node dev/server.js            (PORT, OFFICE_SECRET, GATEWAY_DB are read from the environment)
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname, normalize } from 'node:path';
import worker from '../src/worker.js';
import { D1 } from './d1.js';

const here = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(here, '..', 'public');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml' };

export function makeEnv(extra = {}) {
  return {
    DB: new D1(process.env.GATEWAY_DB || ':memory:'),
    OFFICE_SECRET: process.env.OFFICE_SECRET || '',
    RETENTION_DAYS: '30',
    ASSETS: {
      async fetch(req) {
        const p = normalize(decodeURIComponent(new URL(req.url).pathname)).replace(/^([/\\])+/, '');
        try {
          const data = await readFile(join(PUBLIC, p));
          return new Response(data, { status: 200, headers: { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' } });
        } catch { return new Response('Not found', { status: 404 }); }
      },
    },
    ...extra,
  };
}

export function serve(env, port = 0) {
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers.set(k, v);
    headers.set('CF-Connecting-IP', headers.get('x-test-ip') || req.socket.remoteAddress || 'local');
    const request = new Request(`http://${req.headers.host}${req.url}`, { method: req.method, headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : body });
    const r = await worker.fetch(request, env);
    res.writeHead(r.status, Object.fromEntries(r.headers));
    res.end(Buffer.from(await r.arrayBuffer()));
  });
  return new Promise((ok) => server.listen(port, '127.0.0.1', () => ok(server)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const s = await serve(makeEnv(), Number(process.env.PORT || 8787));
  console.log('READY ' + s.address().port);
}
