// Studio only: the local mailbox (the real worker code) on the STUDIO CLOCK, read from STUDIO_CLOCK whenever the file changes.
import { statSync, readFileSync } from 'node:fs';
const CLOCK = process.env.STUDIO_CLOCK;
let mtime = -1, off = 0;
function offset() {
  try {
    const m = statSync(CLOCK).mtimeMs;
    if (m !== mtime) { off = JSON.parse(readFileSync(CLOCK, 'utf8')).offset * 1000; mtime = m; }
  } catch { /* keep the last value */ }
  return off;
}
const RealDate = Date;
class StudioDate extends RealDate {
  constructor(...a) { if (a.length) super(...a); else super(RealDate.now() + offset()); }
  static now() { return RealDate.now() + offset(); }
}
globalThis.Date = StudioDate;
const { serve, makeEnv } = await import('../../gateway/dev/server.js');
const s = await serve(makeEnv(), Number(process.env.PORT || 0));
console.log('READY ' + s.address().port);
