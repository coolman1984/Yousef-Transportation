// The agent's visible hands: a drawn cursor that travels on an eased path, a ring on click, typing character by character,
// and an event log (point, click, type, say, mark) with wall-clock times that the editor lines up with the recorded frames.
import { sleep } from './cdp.mjs';

const CURSOR = `(() => {
  if (document.getElementById('__studio_cursor')) return true;
  const c = document.createElement('div');
  c.id = '__studio_cursor';
  c.innerHTML = '<svg width="26" height="30" viewBox="0 0 26 30"><path d="M2 2 L2 24 L8 18.5 L12.5 28 L16.5 26.2 L12 17 L20 17 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg><i></i>';
  c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))';
  const ring = c.querySelector('i');
  ring.style.cssText = 'position:absolute;left:-14px;top:-14px;width:30px;height:30px;border-radius:50%;border:3px solid #f2a900;opacity:0;transform:scale(.4)';
  document.documentElement.appendChild(c);
  window.__studioCursor = (x, y) => { c.style.transform = 'translate(' + x + 'px,' + y + 'px)'; };
  window.__studioPulse = () => { ring.animate([{ opacity: .95, transform: 'scale(.4)' }, { opacity: 0, transform: 'scale(1.8)' }], { duration: 520, easing: 'cubic-bezier(.2,.7,.2,1)' }); };
  return true;
})()`;

// finds the smallest visible element that matches a visible text / label / selector; returns its centre (CSS px) after scrolling it into view
const FIND = function (target, opts) {
  const vis = (el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05;
  };
  const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const root = opts.within ? document.querySelector(opts.within) : document;
  if (!root) return null;
  let cands = [];
  if (target.startsWith('css:')) cands = [...root.querySelectorAll(target.slice(4))];
  else {
    const want = norm(target);
    const all = root.querySelectorAll(opts.field ? 'input,select,textarea' : 'button,a,[role=button],[data-a],[data-tab],label,input,select,textarea,summary,tr,td,th,li,span,b,div,h1,h2,h3,p,option,[tabindex]');
    for (const el of all) {
      if (el.id === '__studio_cursor' || el.closest('#__studio_cursor')) continue;
      let texts = [el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('placeholder')];
      if (opts.field) {
        if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) texts.push(l.textContent); }
        const lw = el.closest('label'); if (lw) texts.push(lw.textContent);
        const fld = el.closest('.field'); if (fld) { const l = fld.querySelector('label'); if (l) texts.push(l.textContent); }
      } else texts.push(el.innerText);
      texts = texts.map(norm).filter(Boolean).map((t) => t.replace(/\s*\*$/, ''));
      if (texts.some((t) => (opts.exact ? t === want : t === want || t.includes(want)))) cands.push(el);
    }
  }
  cands = cands.filter(vis);
  if (!cands.length) return null;
  cands.sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return ra.width * ra.height - rb.width * rb.height; });
  let el = cands[0];
  if (!opts.field) { const btn = el.closest('button,a,[role=button],[data-a],[data-tab],label,tr,summary'); if (btn && vis(btn)) el = btn; }
  el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  const r = el.getBoundingClientRect();
  window.__studioTarget = el;
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height), tag: el.tagName, text: norm(el.innerText || el.value || '').slice(0, 60) };
};

const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);

export class Stage {
  constructor(page, { name = 'page', speed = 1 } = {}) {
    this.page = page; this.name = name; this.speed = speed;
    this.pos = { x: page.width * 0.5, y: page.height * 0.62 };
    this.events = [];
  }

  emit(kind, data = {}) {
    const ev = { kind, ts: Date.now() / 1000, page: this.name, ...data };   // ts, never "at": a field named like the time once overwrote it
    this.events.push(ev);
    return ev;
  }

  say(text, { hold = 0 } = {}) { this.emit('say', { text, hold }); }
  mark(name, data = {}) { this.emit('mark', { name, data }); }
  async pause(ms) { await sleep(ms / this.speed); }

  async ensureCursor() {
    await this.page.evaluate(CURSOR);
    await this.page.evaluate((x, y) => window.__studioCursor(x, y), this.pos.x, this.pos.y);
  }

  async find(target, opts = {}, timeout = 15000) {
    return this.page.waitFor(FIND, { timeout, what: 'to find "' + target + '"' }, target, opts);
  }

  async moveTo(x, y) {
    await this.ensureCursor();
    const from = { ...this.pos }, dist = Math.hypot(x - from.x, y - from.y);
    const ms = Math.min(900, 260 + dist * 0.9) / this.speed, steps = Math.max(8, Math.round(ms / 16));
    // a gentle curve, not a straight robotic line
    const bend = Math.min(60, dist * 0.12), nx = -(y - from.y) / (dist || 1), ny = (x - from.x) / (dist || 1);
    const t0 = Date.now();
    for (let i = 1; i <= steps; i++) {
      const u = ease(i / steps), arc = Math.sin(Math.PI * (i / steps)) * bend;
      const px = from.x + (x - from.x) * u + nx * arc, py = from.y + (y - from.y) * u + ny * arc;
      await this.page.evaluate((a, b) => window.__studioCursor(a, b), px, py);
      await this.page.mouse('mouseMoved', px, py);
      const due = t0 + (ms * i) / steps - Date.now();
      if (due > 0) await sleep(due);
    }
    this.pos = { x, y };
  }

  async point(target, opts = {}) {
    const box = await this.find(target, opts);
    await this.moveTo(box.x, box.y);
    this.emit('point', { target, x: box.x, y: box.y });
    return box;
  }

  /** click(target, { expect }) - expect: a page function (string or fn) that must become true afterwards */
  async click(target, { expect, within, exact, timeout = 20000, settle = 250 } = {}) {
    const box = await this.find(target, { within, exact });
    await this.moveTo(box.x, box.y);
    await this.pause(120);
    await this.page.evaluate(() => window.__studioPulse && window.__studioPulse());
    // dispatch on the element we found (the drawn cursor sits on top and must never take the click)
    await this.page.clickAt(box.x, box.y);
    this.emit('click', { target, x: box.x, y: box.y, w: box.w, h: box.h });
    if (expect) await this.page.waitFor(expect, { timeout, what: 'after clicking "' + target + '"' });
    await this.pause(settle);
    return box;
  }

  /** fill(field, value) - types like a person, then reads the value back */
  async fill(field, value, { within, perChar = 55, clear = true } = {}) {
    const box = await this.find(field, { field: true, within });
    await this.moveTo(box.x, box.y);
    await this.page.clickAt(box.x, box.y);
    this.emit('click', { target: field, x: box.x, y: box.y, w: box.w, h: box.h });
    await this.page.evaluate((c) => { const el = window.__studioTarget; el.focus(); if (c) { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); } }, clear);
    for (const ch of String(value)) {
      await this.page.type(ch);
      this.emit('type', { ch });
      await sleep((perChar * (0.7 + Math.random() * 0.6)) / this.speed);
    }
    await this.page.evaluate(() => { const el = window.__studioTarget; el.dispatchEvent(new Event('change', { bubbles: true })); });
    const got = await this.page.evaluate(() => window.__studioTarget.value);
    if (String(got) !== String(value)) throw new Error(`fill "${field}": typed "${value}" but the field holds "${got}"`);
    return got;
  }

  /** choose(select, label) - picks an option by its visible label, never by index */
  async choose(field, label, { within } = {}) {
    const box = await this.find(field, { field: true, within });
    await this.moveTo(box.x, box.y);
    await this.page.evaluate(() => window.__studioPulse && window.__studioPulse());
    this.emit('click', { target: field, x: box.x, y: box.y, w: box.w, h: box.h });
    const ok = await this.page.evaluate((lab) => {
      const el = window.__studioTarget, norm = (s) => String(s || '').replace(/\s+/g, ' ').trim();
      if (el.tagName !== 'SELECT') return 'not a select';
      const o = [...el.options].find((x) => norm(x.text) === norm(lab)) || [...el.options].find((x) => norm(x.text).includes(norm(lab)));
      if (!o) return 'no option ' + lab;
      el.value = o.value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }, label);
    if (ok !== true) throw new Error(`choose "${field}" = "${label}": ${ok}`);
    this.emit('choose', { target: field, label });
    await this.pause(200);
  }

  async press(key, code, keyCode) { await this.page.key(key, code, keyCode); this.emit('key', { key }); }
}
