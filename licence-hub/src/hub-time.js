/** Signed hub business calendar day — verified by the office app (trial-hub or paid kid). */
const enc = new TextEncoder();

function b64url(buf) {
  const b = typeof buf === 'string' ? enc.encode(buf) : buf;
  let s = '';
  for (const byte of b) s += String.fromCharCode(byte);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function hubTimeMessage(calendarDay, kid) {
  return `AF-LICENCE-HUB-TIME/1|${calendarDay}|${kid}`;
}

export function hubTimeMessageV2(calendarDay, serverTime, kid, nonce = null) {
  const base = `AF-LICENCE-HUB-TIME/2|${calendarDay}|${serverTime}|${kid}`;
  return nonce ? `${base}|${nonce}` : base;
}

/** @returns {{ calendar_day: string, kid: string, sig: string, server_time: number, sig2: string, serverTime: number, signed: true, nonce?: string }} */
export async function signHubCalendar(privateKey, kid, calendarDay, serverTime, options = {}) {
  const nonce = options.nonce || null;
  const msg1 = enc.encode(hubTimeMessage(calendarDay, kid));
  const sig = new Uint8Array(await crypto.subtle.sign('Ed25519', privateKey, msg1));
  const msg2 = enc.encode(hubTimeMessageV2(calendarDay, serverTime, kid, nonce));
  const sig2 = new Uint8Array(await crypto.subtle.sign('Ed25519', privateKey, msg2));
  const out = {
    calendar_day: calendarDay,
    kid,
    sig: b64url(sig),
    server_time: serverTime,
    sig2: b64url(sig2),
    serverTime,
    signed: true,
  };
  if (nonce) out.nonce = nonce;
  return out;
}
