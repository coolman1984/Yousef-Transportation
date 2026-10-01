// renders single frames of the film (to check the composition before a full render): node preview.mjs 0 12 30 ...
import { Browser } from './lib/cdp.mjs';
import { mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const out = new URL('./takes/preview/', import.meta.url).pathname; mkdirSync(out, { recursive: true });
const b = await Browser.launch({ args: ['--allow-file-access-from-files'] });
const p = await b.newPage({ width: 1920, height: 1080, scale: 1 });
await p.goto(pathToFileURL(new URL('./composer.html', import.meta.url).pathname).href);
await p.waitFor(() => typeof window.renderAt === 'function');
await p.evaluate(() => document.fonts.ready.then(() => true));
for (const t of process.argv.slice(2).map(Number)) {
  await p.evaluate((x) => window.renderAt(x), t);
  await p.screenshot(`${out}/t${String(t).padStart(5, '0')}.png`);
  console.log('frame', t);
}
await b.close();
