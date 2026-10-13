import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issueTrialCode, importSigningKey, codeCharLength, normalize, group } from '../src/afcodes.js';
import { createPrivateKey, createPublicKey } from 'node:crypto';

function pemFromSeed(seed32) {
  const seed = Buffer.from(seed32);
  const pk = createPrivateKey({ key: Buffer.concat([
    Buffer.from('302e020100300506032b657004220420', 'hex'),
    seed,
  ]), format: 'der', type: 'pkcs8' });
  return pk.export({ type: 'pkcs8', format: 'pem' });
}

test('trial code length and device binding', async () => {
  const seed = Buffer.alloc(32, 7);
  const pem = pemFromSeed(seed);
  const privateKey = await importSigningKey(pem);
  const device = group(normalize('7KD2MQX9TP'), 5);
  const signed = await issueTrialCode(privateKey, 'trip-orders', device, 14);
  const norm = normalize(signed.code);
  assert.equal(norm.length, codeCharLength());
  assert.match(signed.code, /^[0-9A-Z-]+$/);
  assert.equal(signed.edition, 'trial');
});
