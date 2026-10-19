// One-command deploy of the Trip Orders gateway to Cloudflare. Safe to run again (every step is idempotent).
//   Needs: Node 20+, a free Cloudflare account, and the office secret copied from the program
//   (Settings -> Mailbox -> Make the secrets).
//   Windows: double-click deploy.bat      Others: OFFICE_SECRET=... node deploy.mjs
// Login: either `npx wrangler login` once (browser) or CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID in the environment.
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline/promises';

const here = dirname(fileURLToPath(import.meta.url));
const toml = join(here, 'wrangler.toml');
const DB_NAME = 'trip-orders';
const WRANGLER = 'wrangler@4.45.0';
const shell = process.platform === 'win32';

function wr(args, input) {
  const r = spawnSync('npx', ['--yes', WRANGLER, ...args], { cwd: here, encoding: 'utf8', input, shell });
  return { ok: r.status === 0, out: (r.stdout || '') + (r.stderr || '') };
}
function step(msg) { console.log('\n== ' + msg); }
function fail(msg, out) { console.error('\nFAILED: ' + msg + (out ? '\n' + out.trim().split('\n').slice(-12).join('\n') : '')); process.exit(1); }

let secret = process.env.OFFICE_SECRET || '';
if (!secret) {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  secret = (await rl.question('Paste the office secret from the program (Settings > Mailbox): ')).trim();
  rl.close();
}
if (secret.length < 24) fail('The office secret looks too short. Copy it again from the program.');

step('1/5 Build the single-file gateway');
let r = spawnSync('node', ['build.js'], { cwd: here, encoding: 'utf8', shell });
if (r.status !== 0) fail('build.js failed', r.stdout + r.stderr);

step('2/5 Database (D1) "' + DB_NAME + '"');
let cfg = readFileSync(toml, 'utf8');
let m = cfg.match(/database_id\s*=\s*"([^"]+)"/);
if (!m || m[1].startsWith('REPLACE')) {
  let id = null;
  const list = wr(['d1', 'list', '--json']);
  if (list.ok) {
    try { id = (JSON.parse(list.out.slice(list.out.indexOf('['))).find((d) => d.name === DB_NAME) || {}).uuid || null; } catch { /* fall through to create */ }
  }
  if (!id) {
    const c = wr(['d1', 'create', DB_NAME]);
    if (!c.ok) fail('Could not create the database. Are you logged in? (npx wrangler login)', c.out);
    id = (c.out.match(/database_id"?\s*[:=]\s*"([0-9a-f-]{36})"/i) || [])[1] || null;
    if (!id) { const l2 = wr(['d1', 'list', '--json']); try { id = JSON.parse(l2.out.slice(l2.out.indexOf('['))).find((d) => d.name === DB_NAME).uuid; } catch { /* below */ } }
  }
  if (!id) fail('Database was created but its id could not be read. Put it in wrangler.toml by hand (database_id).');
  cfg = cfg.replace(/database_id\s*=\s*"[^"]+"/, 'database_id = "' + id + '"');
  writeFileSync(toml, cfg);
  console.log('database id saved in wrangler.toml (not a secret)');
} else console.log('database already configured');

step('3/5 Tables (schema.sql is safe to re-run)');
r = wr(['d1', 'execute', DB_NAME, '--remote', '--file=schema.sql']);
if (!r.ok) fail('Could not apply schema.sql', r.out);

step('4/5 Deploy the Worker');
r = wr(['deploy']);
if (!r.ok) fail('Deploy failed', r.out);
const url = (r.out.match(/https:\/\/[^\s]+\.workers\.dev/) || [''])[0];

step('5/6 Office secret (stored encrypted at Cloudflare, never in a file)');
r = wr(['secret', 'put', 'OFFICE_SECRET'], secret + '\n');
if (!r.ok) fail('Could not set OFFICE_SECRET');   // do not print wrangler's output: it might echo the secret

step('6/6 Master key for new installs (only when MASTER_KEY is already in the environment)');
// Never generate a key here: a second run would replace it and every office that connected by itself would be locked out.
// Never print the value. Create it once with: npx wrangler secret put MASTER_KEY
if (process.env.MASTER_KEY) {
  r = wr(['secret', 'put', 'MASTER_KEY'], process.env.MASTER_KEY + '\n');
  if (!r.ok) fail('Could not set MASTER_KEY');   // do not print wrangler's output: it might echo the secret
  console.log('MASTER_KEY updated from the environment (the value was not printed).');
} else {
  console.log('MASTER_KEY was not in the environment, so the existing Cloudflare secret was left as it is.');
  console.log('First auto-connect deploy only: npx wrangler secret put MASTER_KEY   (once, a long random value, never again).');
}

console.log('\nDONE. Gateway address: ' + (url || '(see the line "https://...workers.dev" above)'));
console.log('A new office program connects by itself. An office that already has a mailbox keeps it.');
