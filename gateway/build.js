// Builds dist/trip-orders-gateway.js: the worker and the driver page in ONE file, so it can be pasted in the Cloudflare
// dashboard without installing anything.   node build.js
import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, copyFileSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pub = join(here, 'public');
const assets = {};
(function walk(dir) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p);
    else assets['/' + relative(pub, p).split('\\').join('/')] = readFileSync(p, 'utf8');
  }
})(pub);
let src = readFileSync(join(here, 'src', 'worker.js'), 'utf8');
if (!src.includes('let EMBEDDED_ASSETS = null;')) throw new Error('worker.js changed: the EMBEDDED_ASSETS marker is missing');
src = src.replace('let EMBEDDED_ASSETS = null;', 'const EMBEDDED_ASSETS = ' + JSON.stringify(assets) + ';');
mkdirSync(join(here, 'dist'), { recursive: true });
writeFileSync(join(here, 'dist', 'trip-orders-gateway.js'), src);
copyFileSync(join(here, 'schema.sql'), join(here, 'dist', 'schema.sql'));
console.log('built dist/trip-orders-gateway.js', (src.length / 1024).toFixed(0) + ' KB,', Object.keys(assets).length, 'files');
