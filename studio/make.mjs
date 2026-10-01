// One command for the whole film:   node make.mjs [--skip-shoot]
//   shoot (real screens, two devices) -> cut (figures checked) -> sound -> render (picture, then film + music-only) -> measure
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { makeAudio, writeWav } from './lib/audio.mjs';
import { render, mux, share } from './lib/render.mjs';
import { loudness, frozen, contactSheet } from './lib/measure.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, 'out'); mkdirSync(OUT, { recursive: true });
const run = (args) => { const r = spawnSync('node', ['--no-warnings', ...args], { cwd: HERE, stdio: 'inherit' }); if (r.status !== 0) throw new Error('step failed: ' + args.join(' ')); };

if (!process.argv.includes('--skip-shoot')) run(['shoot.mjs']);
run(['cut.mjs']);                                         // refuses to continue when a figure differs from the take's read-back
const cut = JSON.parse(readFileSync(join(HERE, 'cuts', 'film1.cut.json'), 'utf8'));

const A = cut.audio, common = { duration: cut.duration, start: cut.pre, end: cut.outro.t0, whooshes: A.whooshes, swells: A.swells };
writeWav(join(OUT, 'full.wav'), makeAudio({ ...common, clicks: A.clicks, typing: A.typing, chimes: A.chimes, rolls: A.rolls }));
writeWav(join(OUT, 'music.wav'), makeAudio({ ...common }));

await render({ composerUrl: pathToFileURL(join(HERE, 'composer.html')).href, out: join(OUT, 'picture.mp4'), duration: cut.duration, fps: cut.fps, workers: 3 });
mux(join(OUT, 'picture.mp4'), join(OUT, 'full.wav'), join(OUT, 'film1.mp4'));
mux(join(OUT, 'picture.mp4'), join(OUT, 'music.wav'), join(OUT, 'film1-music-only.mp4'));

const m = { film: loudness(join(OUT, 'film1.mp4')), music: loudness(join(OUT, 'film1-music-only.mp4')), frozen: frozen(join(OUT, 'film1.mp4'), cut.duration), duration: cut.duration };
contactSheet(join(OUT, 'film1.mp4'), join(OUT, 'film1-contact-sheet.png'));
// a copy small enough to send in a chat (two-pass, about 27 MB), the master stays as rendered
for (const name of ['film1', 'film1-music-only']) share(join(OUT, name + '.mp4'), join(OUT, name + '-share.mp4'), 27);
writeFileSync(join(OUT, 'measure.json'), JSON.stringify(m, null, 1));
console.log(JSON.stringify({ duration: m.duration, film: m.film, music: m.music, frozen: m.frozen.perWindow }));
