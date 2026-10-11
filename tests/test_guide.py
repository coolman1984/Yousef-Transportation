"""I1: role-based Arabic guide with progress saved on the server. The catalogue is checked by the factory engine in release mode against
the real permissions, profiles, menu pages, UI dictionaries and every error key the server can send (HELP-07..11); every target is a real
control of the pages; progress follows the person to a second browser (HELP-07)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from harness import ADMIN, ApiError, Server, make_authority

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import afguide  # noqa: E402
import assist  # noqa: E402
import errkeys  # noqa: E402
from test_access_gate import catalogue as access_catalogue, words  # noqa: E402

GUIDE = os.path.join(ROOT, 'guide')
LICENCE_CODES = ['lic.' + r for r in ('no_code', 'other_device', 'expired', 'bad_signature', 'wrong_length', 'bad_character', 'unknown_key', 'wrong_product',
                                      'unknown_version', 'invalid', 'no_keys', 'trial_off', 'have_licence', 'unbound_perpetual', 'unknown_edition')]
PAIR = re.compile(r"""'([\w.\-]+)':\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def server_error_codes():
    """Every code the server can put on an error answer: the keys of errkeys.py plus the licence reasons."""
    return set(errkeys.KEYS) | set(LICENCE_CODES)


def ui(lang):
    return {k: a or b for k, a, b in PAIR.findall(open(os.path.join(ROOT, 'js', 'i18n', lang + '.js'), encoding='utf-8').read())}


def load():
    return afguide.load_dir(GUIDE)


class CatalogueTest(unittest.TestCase):
    def test_release_check_against_the_real_program(self):
        cat, texts = load()
        access = access_catalogue(words('ar'))
        found = afguide.errors(cat, texts, ui={'ar': ui('ar'), 'en': ui('en')}, access=access, error_codes=sorted(server_error_codes()), release=True)
        self.assertEqual(found, [], [f'{f.code} {f.where}: {f.message}' for f in found])

    def test_every_error_the_server_sends_has_a_problem_entry(self):
        cat, _ = load()
        explained = {c for p in cat['problems'] for c in p['errors']}
        self.assertEqual(explained, server_error_codes())

    def test_cli_check_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {'ui-ar.json': ui('ar'), 'ui-en.json': ui('en'), 'access.json': access_catalogue(words('ar')), 'errors.json': sorted(server_error_codes())}
            for name, obj in files.items():
                with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    json.dump(obj, f)
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'server', 'afguide.py'), 'check', 'guide', '--ui', os.path.join(tmp, 'ui-ar.json'),
                                '--ui', os.path.join(tmp, 'ui-en.json'), '--access', os.path.join(tmp, 'access.json'), '--errors', os.path.join(tmp, 'errors.json'),
                                '--release'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('0 errors', r.stdout)

    def test_every_target_is_a_real_control(self):
        cat, _ = load()
        blob = '\n'.join(open(os.path.join(d, f), encoding='utf-8').read() for d, _, fs in os.walk(os.path.join(ROOT, 'js'))
                         for f in fs if f.endswith('.js') and 'vendor' not in d)
        missing = []
        for tid, spec in cat['targets'].items():
            sel = spec['sel']
            hook = re.search(r'data-guide="([^"]+)"', sel)
            tab = re.search(r'data-tab="([^"]+)"', sel)
            field = re.search(r'\[name="([^"]+)"\]', sel)
            if hook:
                ok = f'data-guide="{hook.group(1)}"' in blob
            elif tab:
                ok = f"'{tab.group(1)}'" in blob and 'data-tab=' in blob
            elif field:
                ok = f"key: '{field.group(1)}'" in blob or f"'{field.group(1)}'" in blob
            else:
                ok = False
            if not ok:
                missing.append(tid)
        self.assertEqual(missing, [])

    def test_signals_the_catalogue_waits_for_are_sent_by_the_pages(self):
        cat, _ = load()
        events = {s['until']['event'] for g in cat['guides'] for s in g['steps'] if 'event' in s.get('until', {})}
        blob = '\n'.join(open(os.path.join(d, f), encoding='utf-8').read() for d, _, fs in os.walk(os.path.join(ROOT, 'js')) for f in fs if f.endswith('.js'))
        for e in events:
            self.assertRegex(blob, r"guide\.signal\('%s'\)" % re.escape(e), e)

    def test_the_arabic_reads_like_the_factory_standard(self):
        cat, texts = load()
        self.assertEqual([f for f in afguide.lint(texts['ar'], 'ar')], [])
        self.assertEqual([f for f in afguide.lint(texts['en'], 'en')], [])
        self.assertFalse(re.search('[٠-٩]', json.dumps(texts['ar'], ensure_ascii=False)))

    def test_every_built_in_profile_has_a_course(self):
        cat, _ = load()
        access = access_catalogue(words('ar'))
        in_roles = {p for r in cat['roles'] for p in r['profiles']}
        self.assertEqual(in_roles, {p['id'] for p in access['profiles']})

    def test_the_server_maps_a_profile_to_its_course(self):
        access = access_catalogue(words('ar'))
        cat, _ = load()
        for p in access['profiles']:
            mapped = assist.guide_role(p['perms'])
            role = next(r for r in cat['roles'] if r['id'] == mapped)
            self.assertIn(p['id'], role['profiles'], f'{p["id"]} -> {mapped}')
        self.assertEqual(assist.guide_role([]), 'viewer')
        self.assertEqual(assist.guide_role(['trips.approve', 'trips.view']), 'ga-approver')
        self.assertEqual(assist.guide_role(['finance.view', 'reports.view']), 'finance')
        self.assertEqual(set(assist.ROLES), {r['id'] for r in cat['roles']})

    def test_files_are_served_to_the_page(self):
        S = Server('guidefiles').start()
        try:
            make_authority(S)
            c = S.client()
            c.login(*ADMIN)
            for name in ('catalogue', 'ar', 'en'):
                self.assertTrue(c.get(f'/guide/{name}.json'))
            with self.assertRaises(ApiError):
                c.get('/guide/../server/app.py')
        finally:
            S.cleanup()


class ProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('guideprogress').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_a_progress_is_saved_on_the_server_and_follows_the_person_to_a_second_browser(self):
        st = self.ac.get('/api/guide/state')
        self.assertEqual(st['role'], 'administrator')
        self.assertEqual(st['course']['done'], 0)
        first = st['course']['next']
        self.assertEqual(first, 'first-look')
        self.ac.post('/api/guide/progress', {'update': {'op': 'step', 'guide': 'create-trip', 'step': 2}})
        self.ac.post('/api/guide/progress', {'update': {'op': 'done', 'guide': 'first-look'}})
        other = self.S.client()                                    # a second browser of the same person
        other.login(*ADMIN)
        st2 = other.get('/api/guide/state')
        self.assertEqual(st2['progress']['current'], {'guide': 'create-trip', 'step': 2}, 'resume at the saved step')
        self.assertIn('first-look', st2['progress']['done'])
        self.assertTrue(next(i for i in st2['course']['items'] if i['id'] == 'first-look')['done'])

    def test_b_live_states_tick_lessons_by_themselves(self):
        self.ac.post('/api/commit', {'label': 'cat', 'ops': [{'e': 'tripCategories', 'id': 'catg', 'op': 'put', 'row': {'name': 'Manager car'}}]})
        st = self.ac.get('/api/guide/state')
        self.assertIn('setup.done', st['states'])
        item = next(i for i in st['course']['items'] if i['id'] == 'set-up-lists')
        self.assertTrue(item['done'] and item['auto'])

    def test_c_junk_progress_is_a_calm_400(self):
        for body in ({'update': 5}, {'update': {'op': 5}}, {'update': {'op': 'step', 'guide': 'nope', 'step': 1}}, {'update': None}, {}):
            with self.assertRaises(ApiError) as e:
                self.ac.post('/api/guide/progress', body)
            self.assertEqual(e.exception.code, 400, body)

    def test_d_each_person_has_their_own_progress_and_course(self):
        prof = next(p for p in self.ac.get('/api/users')['profiles'] if p['id'] == 'ga-approver')
        self.ac.post('/api/users/save', {'username': 'gaa', 'full_name': 'GA Person', 'password': 'Quarter-pass77', 'must_change': False,
                                         'role': prof['name'], 'perms': prof['perms'], 'scopes': None})
        c = self.S.client()
        c.login('gaa', 'Quarter-pass77')
        st = c.get('/api/guide/state')
        self.assertEqual(st['role'], 'ga-approver')
        self.assertEqual(st['course']['done'], 0, 'not the administrator\'s progress')
        self.assertEqual([i['id'] for i in st['course']['items']][:3], ['first-look', 'read-board', 'approve-trip'])


if __name__ == '__main__':
    unittest.main()
