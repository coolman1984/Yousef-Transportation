// One command for the whole film:   node make.mjs [--skip-shoot]
//   shoot (real screens, two devices) -> cut (figures checked) -> sound -> render (picture, then film + music-only) -> measure
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { makeAudio, writeWav } from './lib/audio.mjs';
import { render, mux } from './lib/render.mjs';
import { loudness, frozen, contactSheet } from './lib/measure.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, 'out'); mkdirSync(OUT, { recursive: true });
const run = (args) => { const r = spawnSync('node', ['--no-warnings', ...args], { cwd: HERE, stdio: 'inherit' }); if (r.status !== 0) throw new Error('step failed: ' + args.join(' ')); };

if (!process.argv.includes('--skip-shoot')) run(['shoot.mjs']);
run(['cut.mjs']);                                         // refuses to continue when a figure differs from the take's read-back
const cut = JSON.parse(readFileSync(join(HERE, 'cuts', 'film1.cut.json'), 'utf8'));

const common = { duration: cut.duration, whooshes: cut.audio.whooshes };
writeWav(join(OUT, 'full.wav'), makeAudio({ ...common, clicks: cut.audio.clicks, typing: cut.audio.typing, music: true }));
writeWav(join(OUT, 'music.wav'), makeAudio({ ...common, clicks: [], typing: [], music: true }));

await render({ composerUrl: pathToFileURL(join(HERE, 'composer.html')).href, out: join(OUT, 'picture.mp4'), duration: cut.duration });
mux(join(OUT, 'picture.mp4'), join(OUT, 'full.wav'), join(OUT, 'film1.mp4'));
mux(join(OUT, 'picture.mp4'), join(OUT, 'music.wav'), join(OUT, 'film1-music-only.mp4'));

const m = { film: loudness(join(OUT, 'film1.mp4')), music: loudness(join(OUT, 'film1-music-only.mp4')), frozen: frozen(join(OUT, 'film1.mp4'), cut.duration), duration: cut.duration };
contactSheet(join(OUT, 'film1.mp4'), join(OUT, 'film1-contact-sheet.png'));
writeFileSync(join(OUT, 'measure.json'), JSON.stringify(m, null, 1));
console.log(JSON.stringify({ duration: m.duration, film: m.film, music: m.music, frozen: m.frozen.perWindow }));
