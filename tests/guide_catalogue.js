'use strict';
// Writes Trip Orders' help in the factory's af-guide format (Apps-Factory packages/af-guide, catalogue "format": 1), so the
// factory checker and its «العربية الميسّرة» lint read every guide, course and problem. Trip Orders keeps the coach it shares
// with Hessa (js/views/guides.js); this file only translates it. Used by tests/test_guide_gate.py: node guide_catalogue.js out.json
const { startup } = require('./guide_loader.js');
const LANGS = ['ar', 'en'];
const by = {};
for (const lang of LANGS) by[lang] = startup(lang);
const G = by.ar.guides;
const page = (p) => String(p || '').split('?')[0].split('/')[0] || null;
const kebab = (s) => s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
const ACTION = { click: 1, type: 1, choose: 1, check: 1 };

const targets = {}, states = [...new Set(G.paths.flatMap((p) => p.lessons.map((l) => l.fact)).filter(Boolean))];
const doneOf = {};
G.paths.forEach((p) => p.lessons.forEach((l) => { if (l.fact && !doneOf[l.guide]) doneOf[l.guide] = l.fact; }));
const guides = G.list.map((g) => {
  let at = null;
  const steps = g.steps.map((s, i) => {
    const pg = page(s.page);
    if (pg) at = pg;
    const out = { k: s.k };
    if (pg) out.page = pg;
    if (s.sel) { const id = 'to.' + kebab(g.id) + '.' + (i + 1); targets[id] = { page: pg || at, sel: s.sel }; out.target = id; }
    else if (ACTION[s.k]) out.k = 'tip';   // "check that it worked" without a control: a sentence to read
    return out;
  });
  steps.push({ k: 'done' });
  const perm = Array.isArray(g.perm) ? g.perm[0] : g.perm || '*';
  return { id: kebab(g.id), cat: g.cat, perm, minutes: Math.max(1, Math.min(15, Math.ceil(g.steps.length / 2))), requires: [],
    ...(doneOf[g.id] ? { done: { state: doneOf[g.id] } } : {}), steps };
});
const problems = G.situations.map((x) => ({ id: kebab(x[0]), cat: x[2] || 'daily', page: page(x[1]),
  ...(G.sitGuide[x[0]] ? { guide: kebab(G.sitGuide[x[0]]) } : {}), errors: [], roles: [] }));
const roles = G.paths.map((p) => ({ id: p.id, profiles: p.roles,
  path: p.lessons.map((l) => kebab(l.guide)).filter((v, i, a) => a.indexOf(v) === i) }));

function texts(lang) {
  const D = by[lang].dict[lang], t = (k) => (D[k] !== undefined ? D[k] : '');
  const out = {};
  G.paths.forEach((p) => { out['role.' + p.id + '.title'] = t('path.' + p.id + '.t'); out['role.' + p.id + '.intro'] = t('path.' + p.id + '.d'); });
  G.list.forEach((g) => {
    const k = 'guide.' + kebab(g.id) + '.';
    out[k + 'title'] = t('gd.' + g.id + '.t'); out[k + 'why'] = t('gd.' + g.id + '.d'); out[k + 'ok'] = t('gd.' + g.id + '.ok');
    g.steps.forEach((_, i) => { out[k + (i + 1)] = t('gd.' + g.id + '.' + (i + 1)); });
    out[k + (g.steps.length + 1)] = t('gd.' + g.id + '.ok');
    if (D['gd.' + g.id + '.x'] !== undefined) out[k + 'mistake'] = t('gd.' + g.id + '.x');
  });
  G.situations.forEach((x) => {
    const k = 'problem.' + kebab(x[0]) + '.', a = t('sit.' + x[0] + '.a');
    const cut = a.search(/[.؟!]\s/);   // the first sentence says why, the rest says what to do
    out[k + 'see'] = t('sit.' + x[0] + '.q');
    out[k + 'why'] = cut > 0 ? a.slice(0, cut + 1) : a;
    out[k + 'do.1'] = cut > 0 ? a.slice(cut + 2) : a;
  });
  // every other help text (questions, tour, slides) only for the lint
  Object.keys(D).filter((k) => ['hq.', 'help.', 'guide.', 'sup.', 'tour.', 'slide.'].some((p) => k.startsWith(p)))
    .forEach((k) => { out['other.' + k] = t(k); });
  return out;
}
const cat = { product: 'trip-orders', format: 1, languages: LANGS, defaultLang: 'ar', uiLanguages: LANGS, unguided: ['help', 'licence'],
  states, checklist: [], targets, guides, roles, problems };
require('fs').writeFileSync(process.argv[2], JSON.stringify({ cat, texts: { ar: texts('ar'), en: texts('en') },
  ui: { ar: by.ar.dict.ar, en: by.en.dict.en } }));
