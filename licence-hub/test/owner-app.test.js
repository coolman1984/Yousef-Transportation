import { test } from 'node:test';
import assert from 'node:assert/strict';
import { showIssuedCode } from '../public/owner/app.js';

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
