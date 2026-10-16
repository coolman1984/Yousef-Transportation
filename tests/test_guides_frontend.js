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
  TO.prefs.data.learn = { _: { guidesDone: { tour: 1, board: 1, find: 1 } } };   // a person with no id yet: '_'
  const all = { passwordChanged: true, myTripCreated: true, myLinkMade: true, myCancel: true, myWordForm: true, myExcelExport: true };
  assert.equal(TO.guides.nextCardHTML(p, all), '');
  assert.ok(!TO.guides.pathHTML(p, all).includes('aria-current'));
  TO.prefs.data.learn = {};
  assert.ok(TO.guides.nextCardHTML(p, { passwordChanged: true }).includes('data-guide="tour"'));
  TO.me = { role: 'Full access', perms: ['categories.manage'] };
  assert.equal(TO.guides.myPath().id, 'manager');
});

test('the course and the finished lessons belong to the person, not to the PC (review: shared office PC)', () => {
  const TO = startup('en'); TO.prefs.data = { learn: { a: { path: 'viewer', guidesDone: { find: 1 } } } }; TO.data.state = {};
  const G = TO.guides, perms = ['trips.view', 'board.view', 'trips.create', 'trips.send', 'trips.cancel', 'excel.export'];
  TO.me = { id: 'a', perms };
  assert.equal(G.myPath().id, 'viewer');
  assert.ok(G.lessons(G.myPath(), {}).find((x) => x.g.id === 'find').done);
  TO.me = { id: 'b', role: 'Dispatcher', perms };
  assert.equal(G.myPath().id, 'dispatcher');
  assert.ok(!G.lessons(G.myPath(), {}).find((x) => x.g.id === 'find').done);
});

test('overview checklist tags exist and step readiness follows guide facts', () => {
  const TO = startup('ar');
  assert.ok(TO.t('ov.todo.tag') && TO.t('ov.done.tag'));
  assert.equal(typeof TO.overviewStepReady, 'function');
  const facts = { categoriesAdded: true, vehiclesAdded: true, driversAdded: true, peopleAdded: false, placesAdded: true, myImport: false, mailboxReady: false };
  assert.equal(TO.overviewStepReady(1, facts, {}, 0), true);
  assert.equal(TO.overviewStepReady(2, facts, {}, 0), true);
  assert.equal(TO.overviewStepReady(4, facts, {}, 0), false);
  assert.equal(TO.overviewStepReady(5, facts, {}, 3), true);
});

test('a failed facts fetch after a change of person never shows the previous person\'s facts (review)', async () => {
  const TO = startup('en'); TO.prefs.data = {};
  TO.me = { id: 'a', perms: [] };
  TO.get = () => Promise.resolve({ myTripCreated: true });
  assert.equal((await TO.guides.loadFacts(true)).myTripCreated, true);
  TO.me = { id: 'b', perms: [] };
  TO.get = () => Promise.reject(new Error('offline'));
  assert.equal(Object.keys(await TO.guides.loadFacts()).length, 0);
});

test('activity labels search and render the displayed Arabic safely', () => {
  const TO = startup('ar');
  const row = { label: 'Closed trip 26-A-00001', entity: 'trips', op: 'update', user: 'u', node_name: 'PC', ts: '2026-10-16T09:30:00Z' };
  assert.equal(TO.activityMatches(row, 'قفل مشوار'), true);
  assert.equal(TO.activityMatches(row, 'missing'), false);
  assert.match(TO.auditLabel('Driver link 26-A-00001: start, end', false), /عداد البداية.*عداد النهاية/);
  assert.match(TO.auditLabel('Driver photo start_odo for 26-A-00001', false), /عداد البداية/);
  assert.match(TO.auditLabel('Excel import sheet.xlsx (3 trips)', false), /3 مشاوير/);
  const html = TO.auditLabel('New trip 26-A-00001<img src=x>', true);
  assert.match(html, /<bdi dir="ltr">26-A-00001&lt;img src=x&gt;<\/bdi>/);
  assert.ok(!html.includes('<img src=x>'));
});
