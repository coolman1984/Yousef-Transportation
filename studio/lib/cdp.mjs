// Chrome DevTools Protocol over a websocket - launch Chromium with its own profile, open pages, evaluate, wait, type, click.
// Plain Node (>= 22: global WebSocket), no packages.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const CHROME = process.env.STUDIO_CHROME || ['/opt/pw-browsers/chromium', '/usr/bin/chromium', '/usr/bin/google-chrome'].find((p) => existsSync(p));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class Browser {
  static async launch({ headless = true, args = [], profile } = {}) {
    const dir = profile || mkdtempSync(join(tmpdir(), 'studio-profile-'));
    const proc = spawn(CHROME, [
      headless ? '--headless=new' : '', '--remote-debugging-port=0', `--user-data-dir=${dir}`, '--no-first-run', '--no-default-browser-check',
      '--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--mute-audio', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
      '--disable-backgrounding-occluded-windows', '--font-render-hinting=none', '--lang=ar', ...args, 'about:blank',
    ].filter(Boolean), { stdio: ['ignore', 'ignore', 'pipe'] });
    const url = await new Promise((ok, bad) => {
      let buf = '';
      const t = setTimeout(() => bad(new Error('Chromium did not start: ' + buf.slice(-400))), 20000);
      proc.stderr.on('data', (d) => {
        buf += d;
        const m = /DevTools listening on (ws:\/\/\S+)/.exec(buf);
        if (m) { clearTimeout(t); ok(m[1]); }
      });
      proc.on('exit', (c) => bad(new Error('Chromium exited ' + c + ': ' + buf.slice(-400))));
    });
    const b = new Browser(proc, dir, !profile);
    await b._connect(url);
    return b;
  }

  constructor(proc, dir, ownDir) { this.proc = proc; this.dir = dir; this.ownDir = ownDir; this.id = 0; this.wait = new Map(); this.listeners = new Map(); }

  _connect(url) {
    return new Promise((ok, bad) => {
      this.ws = new WebSocket(url);
      this.ws.onopen = () => ok();
      this.ws.onerror = (e) => bad(e);
      this.ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.id && this.wait.has(msg.id)) {
          const { ok: res, bad: rej, method } = this.wait.get(msg.id);
          this.wait.delete(msg.id);
          msg.error ? rej(new Error(method + ': ' + msg.error.message)) : res(msg.result);
        } else if (msg.method) {
          for (const fn of this.listeners.get((msg.sessionId || '') + '|' + msg.method) || []) fn(msg.params);
        }
      };
    });
  }

  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((ok, bad) => {
      this.wait.set(id, { ok, bad, method });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }

  on(sessionId, method, fn) {
    const k = (sessionId || '') + '|' + method;
    if (!this.listeners.has(k)) this.listeners.set(k, []);
    this.listeners.get(k).push(fn);
    return () => this.listeners.set(k, this.listeners.get(k).filter((f) => f !== fn));
  }

  async newPage({ width = 1280, height = 800, scale = 1.5, mobile = false, initScripts = [] } = {}) {
    const { targetId } = await this.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await this.send('Target.attachToTarget', { targetId, flatten: true });
    const p = new Page(this, sessionId, targetId);
    await p.send('Page.enable');
    await p.send('Runtime.enable');
    await p.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile, screenWidth: width, screenHeight: height });
    if (mobile) await p.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
    for (const s of initScripts) await p.send('Page.addScriptToEvaluateOnNewDocument', { source: s });
    p.width = width; p.height = height; p.scale = scale;
    return p;
  }

  async close() {
    try { await this.send('Browser.close'); } catch { /* already gone */ }
    await sleep(300);
    try { this.proc.kill('SIGKILL'); } catch { /* gone */ }
    if (this.ownDir) rmSync(this.dir, { recursive: true, force: true });
  }
}

export class Page {
  constructor(browser, sessionId, targetId) { this.b = browser; this.sid = sessionId; this.targetId = targetId; }
  send(method, params) { return this.b.send(method, params, this.sid); }
  on(method, fn) { return this.b.on(this.sid, method, fn); }

  async goto(url, { waitFor } = {}) {
    const loaded = new Promise((r) => { const off = this.on('Page.loadEventFired', () => { off(); r(); }); });
    await this.send('Page.navigate', { url });
    await Promise.race([loaded, sleep(15000)]);
    if (waitFor) await this.waitFor(waitFor);
  }

  /** Run a function in the page: evaluate((a, b) => ..., a, b). Strings are evaluated as expressions. */
  async evaluate(fn, ...args) {
    const expression = typeof fn === 'function' ? `(${fn})(...${JSON.stringify(args)})` : fn;
    const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (r.exceptionDetails) throw new Error('page error: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  }

  /** Poll until fn returns a truthy value (never a fixed sleep). */
  async waitFor(fn, { timeout = 20000, every = 100, what } = {}, ...args) {
    const end = Date.now() + timeout;
    let last;
    while (Date.now() < end) {
      try { last = await this.evaluate(fn, ...args); if (last) return last; } catch (e) { last = e.message; }
      await sleep(every);
    }
    throw new Error('waited too long for ' + (what || String(fn).slice(0, 120)) + (last ? ' (last: ' + String(last).slice(0, 120) + ')' : ''));
  }

  async mouse(type, x, y, extra = {}) {
    await this.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: type === 'mouseMoved' ? 0 : 1, ...extra });
  }

  async clickAt(x, y) {
    await this.mouse('mouseMoved', x, y);
    await this.mouse('mousePressed', x, y);
    await this.mouse('mouseReleased', x, y);
  }

  async type(ch) { await this.send('Input.insertText', { text: ch }); }

  async key(key, code, keyCode) {
    await this.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code: code || key, windowsVirtualKeyCode: keyCode || 0 });
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code: code || key, windowsVirtualKeyCode: keyCode || 0 });
  }

  async screenshot(path) {
    const { data } = await this.send('Page.captureScreenshot', { format: 'png' });
    if (path) (await import('node:fs')).writeFileSync(path, Buffer.from(data, 'base64'));
    return data;
  }
}

export { sleep };
