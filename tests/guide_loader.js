'use strict';
// Loads the real page scripts (index.html order) into a sandbox without a browser, for the guide tests.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script src="([^"]+)">/g)].map((m) => m[1]);   // the page's own script order (a test helper, not a sanitiser)

function startup(lang) {
  const noop = () => {};
  const ctx = vm.createContext({
    document: { documentElement: { lang, dataset: {} }, addEventListener: noop, querySelector: () => null, querySelectorAll: () => [] },
    localStorage: { getItem: () => null, setItem: noop },
    console, Intl, URLSearchParams, addEventListener: noop, removeEventListener: noop, setTimeout, clearTimeout, setInterval, clearInterval,
  });
  ctx.window = ctx;
  for (const file of scripts) {
    if (file === 'lib/qrcode.min.js' || file === 'js/boot.js') continue;   // QR codes and the first-paint script need a real browser
    vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), ctx, { filename: file });
  }
  const TO = ctx.TO;
  TO.lang = lang;
  return TO;
}
module.exports = { startup, scripts, root };
