'use strict';
// Guides, problems and learning paths are complete in both languages and point at real things (run by test_guide_gate.py).
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { startup } = require('./guide_loader.js');

test('every guide and problem is complete in both languages and names real buttons', () => {
  for (const lang of ['ar', 'en']) {
    const TO = startup(lang); TO.prefs.data = {}; TO.data.state = {};
    const G = TO.guides, d = TO.dict[lang];
    assert.ok(G.list.length >= 20 && G.situations.length >= 25);
    const ids = new Set(), texts = [];
    for (const g of G.list) {
      assert.ok(!ids.has(g.id), 'duplicate guide ' + g.id); ids.add(g.id);
      assert.ok(G.cats.includes(g.cat), g.id);
      for (const k of ['t', 'd', 'ok']) { assert.ok(d['gd.' + g.id + '.' + k], lang + ' gd.' + g.id + '.' + k); texts.push(d['gd.' + g.id + '.' + k]); }
      assert.ok(d['gd.' + g.id + '.' + (g.steps.length + 1)] === undefined, 'text for a step that does not exist: ' + g.id);
      g.steps.forEach((s, i) => {
        assert.ok(G.kinds[s.k], g.id + ' kind ' + s.k);
        assert.ok(d['gd.' + g.id + '.' + (i + 1)], lang + ' gd.' + g.id + '.' + (i + 1)); texts.push(d['gd.' + g.id + '.' + (i + 1)]);
        if (s.page) assert.ok(TO.pages.some((p) => p.id === s.page.split('?')[0]), g.id + ' page ' + s.page);
      });
    }
    for (const x of G.situations) {
      for (const k of ['q', 'a']) { assert.ok(d['sit.' + x[0] + '.' + k], lang + ' sit.' + x[0]); texts.push(d['sit.' + x[0] + '.' + k]); }
      assert.ok(TO.pages.some((p) => p.id === x[1].split('?')[0]), 'take me there: ' + x[1]);
    }
    for (const t of texts) for (const m of t.matchAll(/\[\[([^\]]+)\]\]/g)) assert.ok(d[m[1]] !== undefined, lang + ': [[' + m[1] + ']] is not a dictionary key');
    // the library: escaped, permission-aware, nothing missing
    TO.me = { perms: ['trips.view', 'trips.create', 'trips.send', 'board.view'] };
    const html = G.html('trips');
    assert.ok(html.includes('data-guide="newTrip"') && html.includes('data-guide="sendLink"'));
    assert.ok(!html.includes('data-guide="staff"'));                     // administrator guides only for administrators
    assert.ok(!/undefined|\[\[|gd\.[a-zA-Z]+\.\d/.test(html), 'missing text in the guide library');
    assert.ok(G.rich('<b>[[trip.new]]</b>').startsWith('&lt;b&gt;<b class="ui-name">«' + TO.esc(TO.t('trip.new'))));
    const sit = G.situationsHTML();
    assert.ok(!/undefined|\[\[|sit\.[a-zA-Z]+\.[qa]/.test(sit));
  }
});

test('every problem\'s "Guide me" points to a real guide', () => {
  const TO = startup('ar');
  const guides = new Set(TO.guides.list.map((g) => g.id)), sits = TO.guides.situations.map((x) => x[0]);
  for (const sid of sits) assert.ok(guides.has(TO.guides.sitGuide[sid]), 'no guide for ' + sid);
  for (const sid of Object.keys(TO.guides.sitGuide)) assert.ok(sits.includes(sid), 'unknown situation ' + sid);
});

test('the path marks where the person stands, and the home card hides when the path is complete', () => {
  const TO = startup('en'); TO.prefs.data = {};
  TO.me = { role: 'Dispatcher', perms: ['overview.view', 'trips.view', 'board.view', 'trips.create', 'trips.send', 'trips.cancel', 'excel.export', 'print'] };
  const p = TO.guides.myPath();
  assert.equal(p.id, 'dispatcher');
  const html = TO.guides.pathHTML(p, { passwordChanged: true });
  assert.match(html, /<li class="here" aria-current="step">.*?data-guide="tour"/);
  assert.equal((html.match(/aria-current="step"/g) || []).length, 1);
  TO.prefs.data.guidesDone = { tour: 1, board: 1, find: 1 };
  const all = { passwordChanged: true, myTripCreated: true, myLinkMade: true, myCancel: true, myWordForm: true, myExcelExport: true };
  assert.equal(TO.guides.nextCardHTML(p, all), '');
  assert.ok(!TO.guides.pathHTML(p, all).includes('aria-current'));
  TO.prefs.data.guidesDone = {};
  assert.ok(TO.guides.nextCardHTML(p, { passwordChanged: true }).includes('data-guide="tour"'));
  TO.me = { role: 'Full access', perms: ['categories.manage'] };
  assert.equal(TO.guides.myPath().id, 'manager');
});
