// Records a page with Page.startScreencast: every frame is saved as a JPEG with its wall-clock time.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export class Recorder {
  constructor(page, dir, { quality = 82 } = {}) {
    this.page = page; this.dir = dir; this.quality = quality; this.frames = []; this.n = 0;
    mkdirSync(join(dir, 'frames'), { recursive: true });
  }
  async start() {
    this.off = this.page.on('Page.screencastFrame', (f) => {
      const name = `frames/${String(++this.n).padStart(5, '0')}.jpg`;
      writeFileSync(join(this.dir, name), Buffer.from(f.data, 'base64'));
      this.frames.push({ f: name, ts: f.metadata.timestamp });
      this.page.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
    });
    const w = Math.round(this.page.width * this.page.scale), h = Math.round(this.page.height * this.page.scale);
    await this.page.send('Page.startScreencast', { format: 'jpeg', quality: this.quality, maxWidth: w, maxHeight: h, everyNthFrame: 1 });
    this.t0 = Date.now() / 1000;
  }
  /** a tiny repaint so the screencast always has a fresh frame (it only sends frames when something changes) */
  async poke() { await this.page.evaluate(() => { document.documentElement.style.outline = document.documentElement.style.outline ? '' : '0px solid transparent'; }); }
  async stop() {
    await this.page.send('Page.stopScreencast').catch(() => {});
    if (this.off) this.off();
    this.t1 = Date.now() / 1000;
  }
  save(extra) {
    writeFileSync(join(this.dir, 'footage.json'), JSON.stringify({ t0: this.t0, t1: this.t1, width: this.page.width, height: this.page.height, scale: this.page.scale, frames: this.frames, ...extra }, null, 1));
  }
}
