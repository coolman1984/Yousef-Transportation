// AF licence codes — byte-compatible with server/afcodes.py (verify in Trip Orders with the matching public key).
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const DOMAIN = new TextEncoder().encode('AF-LICENCE-CODE/1');
const VERSION = 1;
const EPOCH_MS = Date.UTC(2024, 0, 1);
const EDITION_TRIAL = 1;
const PAYLOAD_LEN = 26;
const CODE_LEN = PAYLOAD_LEN + 64;

const enc = new TextEncoder();

function b32(data) {
  const bits = BigInt('0x' + [...data].map((b) => b.toString(16).padStart(2, '0')).join(''));
  const n = Math.ceil((data.length * 8) / 5);
  const shifted = bits << BigInt(n * 5 - data.length * 8);
  let out = '';
  for (let i = 0; i < n; i++) {
    const shift = 5 * (n - 1 - i);
    out += ALPHABET[Number((shifted >> BigInt(shift)) & 31n)];
  }
  return out;
}

export function normalize(text) {
  if (typeof text !== 'string') throw new Error('bad_character');
  let out = '';
  for (const ch of text.toUpperCase()) {
    if (' -_\t\r\n.'.includes(ch)) continue;
    const mapped = { O: '0', I: '1', L: '1' }[ch] || ch;
    if (!ALPHABET.includes(mapped)) throw new Error('bad_character');
    out += mapped;
  }
  return out;
}

export function group(text, size = 6) {
  const parts = [];
  for (let i = 0; i < text.length; i += size) parts.push(text.slice(i, i + size));
  return parts.join('-');
}

function productTag(productId) {
  return crypto.subtle.digest('SHA-256', enc.encode('AF-PRODUCT/1|' + productId)).then((d) => new Uint8Array(d).slice(0, 4));
}

function deviceTag(code) {
  const norm = normalize(code);
  if (norm.length !== 10) throw new Error('bad_device_code');
  return crypto.subtle.digest('SHA-256', enc.encode('AF-DEVICE-TAG/1|' + norm)).then((d) => new Uint8Array(d).slice(0, 6));
}

function dayNum(d) {
  const n = Math.floor((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - EPOCH_MS) / 86400000);
  if (n < 0 || n > 65535) throw new Error('date_out_of_range');
  return n;
}

function packPayload(fields) {
  const buf = new ArrayBuffer(PAYLOAD_LEN);
  const view = new DataView(buf);
  let off = 0;
  view.setUint8(off, fields.version); off += 1;
  new Uint8Array(buf, off, 4).set(fields.productTag); off += 4;
  view.setUint8(off, fields.edition); off += 1;
  view.setUint16(off, fields.issued, false); off += 2;
  view.setUint16(off, fields.first, false); off += 2;
  view.setUint16(off, fields.last, false); off += 2;
  view.setUint8(off, fields.grace); off += 1;
  new Uint8Array(buf, off, 6).set(fields.deviceTag); off += 6;
  new Uint8Array(buf, off, 4).set(fields.serial); off += 4;
  view.setUint8(off, fields.seats); off += 1;
  new Uint8Array(buf, off, 2).set(fields.keyTag);
  return new Uint8Array(buf);
}

export async function importSigningKey(secret) {
  const raw = secret.trim();
  if (raw.includes('BEGIN')) {
    const pem = raw.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
    const der = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
    return crypto.subtle.importKey('pkcs8', der, { name: 'Ed25519' }, true, ['sign']);
  }
  const pad = raw + '='.repeat((4 - (raw.length % 4)) % 4);
  const seed = Uint8Array.from(atob(pad.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
  if (seed.length !== 32) throw new Error('bad_signing_key');
  return crypto.subtle.importKey('raw', seed, { name: 'Ed25519' }, true, ['sign']);
}

export async function publicKeyB64Url(privateKey) {
  const jwk = await crypto.subtle.exportKey('jwk', privateKey);
  return jwk.x;
}

async function keyTagFromPrivate(privateKey) {
  const jwk = await crypto.subtle.exportKey('jwk', privateKey);
  const raw = Uint8Array.from(atob(jwk.x.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', raw));
  return hash.slice(0, 2);
}

/** Sign a device-bound trial code (edition trial, `days` calendar days inclusive). */
export async function issueTrialCode(privateKey, productId, device, days = 14, firstDay = new Date()) {
  const issued = new Date();
  const first = new Date(Date.UTC(firstDay.getUTCFullYear(), firstDay.getUTCMonth(), firstDay.getUTCDate()));
  const last = new Date(first);
  last.setUTCDate(last.getUTCDate() + days - 1);
  const serial = crypto.getRandomValues(new Uint8Array(4));
  const [ptag, dtag, ktag] = await Promise.all([
    productTag(productId),
    deviceTag(device),
    keyTagFromPrivate(privateKey),
  ]);
  const payload = packPayload({
    version: VERSION,
    productTag: ptag,
    edition: EDITION_TRIAL,
    issued: dayNum(issued),
    first: dayNum(first),
    last: dayNum(last),
    grace: 0,
    deviceTag: dtag,
    serial,
    seats: 1,
    keyTag: ktag,
  });
  const msg = new Uint8Array(DOMAIN.length + payload.length);
  msg.set(DOMAIN, 0);
  msg.set(payload, DOMAIN.length);
  const sig = new Uint8Array(await crypto.subtle.sign('Ed25519', privateKey, msg));
  const raw = new Uint8Array(CODE_LEN);
  raw.set(payload, 0);
  raw.set(sig, PAYLOAD_LEN);
  const norm = b32(raw);
  const code = group(norm);
  return {
    code,
    serial: [...serial].map((b) => b.toString(16).padStart(2, '0')).join('').toUpperCase(),
    first_day: first.toISOString().slice(0, 10),
    last_day: last.toISOString().slice(0, 10),
    edition: 'trial',
    product: productId,
    device: group(normalize(device), 5),
  };
}

export function codeCharLength() {
  return Math.ceil((CODE_LEN * 8) / 5);
}
