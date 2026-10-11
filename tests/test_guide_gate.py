"""Factory help gate (Apps-Factory packages/af-guide 0.1.4, controls HELP-04, HELP-07, HELP-09, HELP-11; owner 2026-10-09).

Trip Orders keeps the coach it shares with Hessa (js/views/guides.js); tests/guide_catalogue.js writes its guides, courses and
problems in the factory format and the vendored factory checker (server/afguide.py) reads all of it: every guide complete in both
languages with real button names, a course per ready-made profile whose lessons the profile is allowed to do (role-perm), the
states the server reports (tripsvc.GUIDE_FACTS), every page covered, every problem linked to a guide, and every Arabic text in
«العربية الميسّرة» (release lint: short sentences, no street words, no stiff office words, digits 0-9). The facts are computed
from the real rows: the office's for the setup lessons, the person's own for daily work."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import afguide  # noqa: E402
import auth  # noqa: E402
import tripsvc  # noqa: E402
from harness import ApiError, Server, make_authority  # noqa: E402
from test_access_gate import catalogue as access_catalogue, words  # noqa: E402

NODE = shutil.which('node')


def help_catalogue():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'guide.json')
        subprocess.run([NODE, os.path.join(ROOT, 'tests', 'guide_catalogue.js'), out], cwd=ROOT, check=True, stdout=subprocess.DEVNULL, timeout=120)
        with open(out, encoding='utf-8') as f:
            return json.load(f)


@unittest.skipUnless(NODE, 'node is needed to read the guides')
class GuideGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = help_catalogue()
        cls.cat, cls.texts, cls.ui = data['cat'], data['texts'], data['ui']
        cls.access = access_catalogue(words('ar'))

    def findings(self, cat=None):
        return afguide.check(cat or self.cat, self.texts, ui=self.ui, access=self.access, release=True)

    def test_catalogue_passes_the_factory_gate(self):
        self.assertGreaterEqual(len(self.cat['guides']), 25)
        self.assertGreaterEqual(len(self.cat['problems']), 30)
        self.assertEqual([str(f) for f in self.findings() if f.level == 'error'], [])

    def test_states_are_what_the_server_reports(self):
        self.assertLessEqual(set(self.cat['states']), set(tripsvc.GUIDE_FACTS))

    def test_every_ready_made_profile_has_a_course(self):
        covered = {p for r in self.cat['roles'] for p in r['profiles']}
        self.assertEqual(covered, {p[0] for p in auth.BUILTIN_PROFILES})

    def test_gate_catches_a_lesson_the_role_cannot_do(self):
        cat = json.loads(json.dumps(self.cat))
        next(r for r in cat['roles'] if r['id'] == 'viewer')['path'].append('staff')
        self.assertIn('role-perm', {f.code for f in self.findings(cat)})

    def test_every_problem_offers_guide_me(self):
        self.assertEqual([p['id'] for p in self.cat['problems'] if not p.get('guide')], [])

    def test_the_whole_help_is_easy_to_read(self):
        self.assertGreater(len([k for k in self.texts['ar'] if k.startswith('other.')]), 30)
        for lang in ('ar', 'en'):
            self.assertEqual([str(f) for f in afguide.lint(self.texts[lang], lang)], [], lang)

    def test_guides_and_problems_in_the_browser_code(self):
        r = subprocess.run([NODE, '--test', os.path.join(ROOT, 'tests', 'test_guides_frontend.js')], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])


class GuideFactsApiTest(unittest.TestCase):
    """The facts come from the real rows: the office's for setup, the person's own for daily work."""
    @classmethod
    def setUpClass(cls):
        cls.S = Server('guidefacts').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_guide_facts_follow_the_real_records(self):
        f = self.ac.get('/api/guide-facts')
        self.assertEqual(set(f), set(tripsvc.GUIDE_FACTS))
        self.assertTrue(f['passwordChanged'])
        self.assertFalse(f['categoriesAdded'] or f['myTripCreated'] or f['staffAdded'])
        put = lambda e, i, **row: {'e': e, 'id': i, 'op': 'put', 'row': row}  # noqa: E731
        self.ac.post('/api/commit', {'label': 'lists', 'ops': [put('tripCategories', 'c1', name='Car', exportSheet='All Car'),
                                                                put('vehicles', 'v1', plate='ABC 123', active=True)]})
        self.ac.post('/api/trips/new', {'categoryId': 'c1', 'vehicleId': 'v1', 'destination': 'Airport'})
        f = self.ac.get('/api/guide-facts')
        self.assertTrue(f['categoriesAdded'] and f['vehiclesAdded'] and f['myTripCreated'])
        self.assertFalse(f['driversAdded'])
        # a fresh dispatcher: the office's setup is done, their own daily work is not
        perms = next(p[2] for p in auth.BUILTIN_PROFILES if p[0] == 'dispatcher')
        self.ac.post('/api/users/save', {'full_name': 'Second Person', 'username': 'second', 'password': 'Another-pass2', 'role': 'Dispatcher',
                                         'login': 'password', 'perms': perms, 'scopes': None, 'active': True, 'must_change': False})
        me = self.S.client()
        me.login('second', 'Another-pass2')
        f = me.get('/api/guide-facts')
        self.assertTrue(f['categoriesAdded'] and f['staffAdded'] and f['passwordChanged'])
        self.assertFalse(f['myTripCreated'] or f['myCancel'] or f['myExcelExport'])
        t = me.post('/api/trips/new', {'categoryId': 'c1', 'vehicleId': 'v1', 'destination': 'Port'})
        me.post('/api/trips/cancel', {'id': t['id'], 'reason': 'entered twice'})
        f = me.get('/api/guide-facts')
        self.assertTrue(f['myTripCreated'] and f['myCancel'])
        self.assertFalse(f['myApproval'])

    def test_facts_need_a_signed_in_person(self):
        with self.assertRaises(ApiError) as e:
            self.S.client().get('/api/guide-facts')
        self.assertEqual(e.exception.code, 401)


if __name__ == '__main__':
    unittest.main()
