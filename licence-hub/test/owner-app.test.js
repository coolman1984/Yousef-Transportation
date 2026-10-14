import { test } from 'node:test';
import assert from 'node:assert/strict';
import { showIssuedCode, readGrant, tierPickerHtml, presetPaidUntil } from '../public/owner/app.js';

function panelEl() {
  const listeners = {};
  return {
    hidden: true,
    innerHTML: '',
    dataset: {},
    querySelector(sel) {
      if (sel === '[data-copy]') return { addEventListener: (ev, fn) => { listeners.copy = fn; } };
      if (sel === '[data-dismiss]') return { addEventListener: (ev, fn) => { listeners.dismiss = fn; } };
      return null;
    },
    listeners,
  };
}

test('issued code panel is outside the pending list and stays after refresh', () => {
  const pending = { innerHTML: '<li>old</li>' };
  const issued = panelEl();
  const host = {
    querySelector(sel) {
      if (sel === '[data-pending]') return pending;
      if (sel === '[data-issued]') return issued;
      return null;
    },
  };
  showIssuedCode(host, 'CODE-123', 'req-1');
  assert.equal(issued.hidden, false);
  assert.match(issued.innerHTML, /CODE-123/);
  pending.innerHTML = '<li class="muted">لا توجد طلبات معلّقة.</li>';
  assert.match(issued.innerHTML, /CODE-123/);
  assert.equal(issued.dataset.requestId, 'req-1');
});

test('tier picker uses unique radio group names per request', () => {
  const a = tierPickerHtml(false, '', 'req-a');
  const b = tierPickerHtml(false, '', 'req-b');
  assert.match(a, /name="tier-req-a"/);
  assert.match(b, /name="tier-req-b"/);
});

test('readGrant uses the checked radio inside its card', () => {
  const root = {
    querySelector(sel) {
      if (sel === '[data-tier-form]') return form;
      return null;
    },
  };
  const form = {
    querySelector(sel) {
      if (sel === 'input[type="radio"]:checked') return { value: 'paid' };
      if (sel === '[data-paid-until]') return { value: '2027-01-15' };
      return null;
    },
  };
  assert.deepEqual(readGrant(root), { grant: 'paid', paid_until: '2027-01-15' });
});

test('presetPaidUntil clamps month overflow from Cairo today', () => {
  const orig = Date.prototype.toLocaleDateString;
  Date.prototype.toLocaleDateString = function (locales, opts) {
    if (opts && opts.timeZone === 'Africa/Cairo') return '2026-01-31';
    return orig.call(this, locales, opts);
  };
  assert.equal(presetPaidUntil('1m'), '2026-02-28');
  Date.prototype.toLocaleDateString = orig;
});
