// Renders the composer page frame by frame (t / 30 s) and pipes the pictures into ffmpeg: H.264 1920x1080 30 fps, AAC 256k.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { Browser } from './cdp.mjs';

export const FFMPEG = process.env.FFMPEG || (() => {
  const c = ['ffmpeg', '/opt/pw-browsers/ffmpeg-1011/ffmpeg-linux'];
  const py = spawnSync('python3', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8' }).stdout.trim();
  if (py) c.unshift(py);
  for (const p of c) { const r = spawnSync(p, ['-version'], { encoding: 'utf8' }); if (r.status === 0 && /libx264/.test(spawnSync(p, ['-encoders'], { encoding: 'utf8' }).stdout)) return p; }
  throw new Error('ffmpeg with libx264 was not found (set FFMPEG)');
})();

/** @param {{composerUrl:string, wav:string, out:string, duration:number, fps?:number, from?:number, to?:number}} o */
export async function render(o) {
  const fps = o.fps || 30, from = o.from ?? 0, to = o.to ?? o.duration;
  const browser = await Browser.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ width: 1920, height: 1080, scale: 1 });
  await page.goto(o.composerUrl);
  await page.waitFor(() => typeof window.renderAt === 'function', { what: 'the composer to load' });
  await page.evaluate(() => document.fonts.ready.then(() => true));
  const n = Math.round((to - from) * fps);
  const args = ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
    ...(o.wav ? ['-ss', String(from), '-t', String(to - from), '-i', o.wav] : []),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', String(fps), '-movflags', '+faststart',
    ...(o.wav ? ['-af', 'alimiter=limit=0.89:level=false,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.84:level=false', '-ar', '48000', '-c:a', 'aac', '-b:a', '256k', '-shortest'] : ['-an']),
    o.out];
  const ff = spawn(FFMPEG, args, { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, bad) => { ff.on('exit', (c) => (c === 0 ? ok() : bad(new Error('ffmpeg exited ' + c)))); });
  for (let i = 0; i < n; i++) {
    const t = from + i / fps;
    await page.evaluate((x) => window.renderAt(x), t);
    const { data } = await page.send('Page.captureScreenshot', { format: 'jpeg', quality: 94 });
    if (!ff.stdin.write(Buffer.from(data, 'base64'))) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % 150 === 0) console.log('render', t.toFixed(1) + 's /', to.toFixed(0) + 's');
  }
  ff.stdin.end();
  await done;
  await browser.close();
}
