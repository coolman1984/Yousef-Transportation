// Renders the composer page frame by frame (t / 60 s), lossless PNG into ffmpeg: H.264 1920x1080 60 fps; the sound is put under it by mux().
import { spawn, spawnSync } from 'node:child_process';
import { writeFileSync, unlinkSync } from 'node:fs';
import { Browser } from './cdp.mjs';

export const FFMPEG = process.env.FFMPEG || (() => {
  const c = ['ffmpeg', '/opt/pw-browsers/ffmpeg-1011/ffmpeg-linux'];
  const py = spawnSync('python3', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8' }).stdout.trim();
  if (py) c.unshift(py);
  for (const p of c) { const r = spawnSync(p, ['-version'], { encoding: 'utf8' }); if (r.status === 0 && /libx264/.test(spawnSync(p, ['-encoders'], { encoding: 'utf8' }).stdout)) return p; }
  throw new Error('ffmpeg with libx264 was not found (set FFMPEG)');
})();

/** renders [from, to) of the composer into one H.264 file (lossless PNG frames in, x264 CRF 14 out) */
async function renderRange(o, from, to, out, tag) {
  const fps = o.fps || 60;
  const browser = await Browser.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ width: 1920, height: 1080, scale: 1 });
  await page.goto(o.composerUrl);
  await page.waitFor(() => typeof window.renderAt === 'function', { what: 'the composer to load' });
  await page.evaluate(() => document.fonts.ready.then(() => true));
  const i0 = Math.round(from * fps), i1 = Math.round(to * fps);
  const args = ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    '-r', String(fps), '-an', out];
  const ff = spawn(FFMPEG, args, { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, bad) => { ff.on('exit', (c) => (c === 0 ? ok() : bad(new Error('ffmpeg exited ' + c)))); });
  for (let i = i0; i < i1; i++) {
    await page.evaluate((x) => window.renderAt(x), i / fps);
    const { data } = await page.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true });
    if (!ff.stdin.write(Buffer.from(data, 'base64'))) await new Promise((r) => ff.stdin.once('drain', r));
    if ((i - i0) % 300 === 0) console.log('render', tag, (i / fps).toFixed(1) + 's');
  }
  ff.stdin.end();
  await done;
  await browser.close();
}

/** @param {{composerUrl:string, out:string, duration:number, fps?:number, workers?:number}} o - renders in parallel slices, then joins them without re-encoding */
export async function render(o) {
  const fps = o.fps || 60, n = o.workers || 3, total = Math.round(o.duration * fps), per = Math.ceil(total / n);
  const parts = [];
  for (let k = 0; k < n; k++) {
    const a = k * per, b = Math.min(total, (k + 1) * per);
    if (a < b) parts.push({ from: a / fps, to: b / fps, out: o.out.replace(/\.mp4$/, `.part${k}.mp4`) });
  }
  await Promise.all(parts.map((p, k) => renderRange({ ...o, fps }, p.from, p.to, p.out, 'w' + k)));
  const list = o.out.replace(/\.mp4$/, '.parts.txt');
  writeFileSync(list, parts.map((p) => `file '${p.out}'`).join('\n'));
  const r = spawnSync(FFMPEG, ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', o.out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('concat failed: ' + r.stderr);
  for (const p of parts) unlinkSync(p.out);
  unlinkSync(list);
}

/** puts a soundtrack under a finished picture (no re-encode of the picture): loudness chain limiter -> loudnorm -> limiter, AAC 256k */
export function mux(video, wav, out) {
  const r = spawnSync(FFMPEG, ['-y', '-hide_banner', '-loglevel', 'error', '-i', video, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
    '-af', 'alimiter=limit=0.89:level=false,loudnorm=I=-16:TP=-1.5:LRA=11:linear=false,alimiter=limit=0.84:level=false', '-ar', '48000', '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('mux failed: ' + r.stderr);
}

/** a two-pass H.264 copy that fits in about `mb` megabytes (picture re-encoded, sound copied) */
export function share(input, out, mb) {
  const probe = spawnSync(FFMPEG, ['-hide_banner', '-i', input], { encoding: 'utf8' }).stderr;
  const d = probe.match(/Duration: (\d+):(\d+):([\d.]+)/), dur = +d[1] * 3600 + +d[2] * 60 + +d[3];
  const kbps = Math.floor((mb * 8 * 1024 * 0.97) / dur - 256);
  const base = ['-y', '-hide_banner', '-loglevel', 'error', '-i', input, '-c:v', 'libx264', '-preset', 'slow', '-b:v', kbps + 'k', '-maxrate', Math.round(kbps * 2.2) + 'k', '-bufsize', Math.round(kbps * 4) + 'k', '-pix_fmt', 'yuv420p', '-passlogfile', out + '.log'];
  let r = spawnSync(FFMPEG, [...base, '-pass', '1', '-an', '-f', 'mp4', '/dev/null'], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('share pass 1: ' + r.stderr);
  r = spawnSync(FFMPEG, [...base, '-pass', '2', '-c:a', 'copy', '-movflags', '+faststart', out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('share pass 2: ' + r.stderr);
  for (const f of [out + '.log-0.log', out + '.log-0.log.mbtree']) try { unlinkSync(f); } catch (e) {}
}
