"""Demo mode (owner request, 17 October 2026): the program opens without signing in, a new data folder starts with sample data
on every page, and there is no licence or activation. Runs the real server (demo_mode on, as in the shipped config.json)."""
import collections
import json
import os
import unittest

from harness import ApiError, Server, make_authority

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DemoModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('demo', extra_cfg={'demo_mode': True}).start()
        cls.c = cls.S.client()        # no cookie, no setup, no login

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_a_the_program_opens_as_the_built_in_administrator(self):
        st = self.c.get('/api/auth/status')
        self.assertTrue(st['hasUsers'])
        me = st['me']
        self.assertTrue(me['demo'])
        self.assertTrue(me['admin'])
        self.assertFalse(me['must_change'])
        self.assertEqual(self.c.get('/api/me')['username'], 'admin')

    def test_b_every_page_has_sample_rows(self):
        st = self.c.get('/api/state')
        for entity in ('tripCategories', 'vehicles', 'drivers', 'departments', 'people', 'places', 'routes', 'trips', 'tripPassengers', 'tripAmendments'):
            self.assertTrue(st[entity], f'no sample {entity}')
        status = collections.Counter(t['status'] for t in st['trips'])
        for s in ('draft', 'closed', 'cancelled'):
            self.assertTrue(status[s], f'no sample trip that is {s}: {status}')
        self.assertTrue(any(t.get('reviewedAt') for t in st['trips']), 'some trips were reviewed')
        self.assertTrue(any(not t.get('reviewedAt') and t['status'] == 'closed' for t in st['trips']), 'some wait in the review queue')
        self.assertTrue({t.get('gaApproved') for t in st['trips']} >= {'yes', 'no'}, 'approved and declined examples')
        self.assertTrue(self.c.get('/api/insights'))
        self.assertTrue(self.c.get('/api/reports?month=' + max(t['date'] for t in st['trips'])[:7]))

    def test_c_work_is_saved_without_signing_in(self):
        st = self.c.get('/api/state')
        trip = self.c.post('/api/trips/new', {'categoryId': st['tripCategories'][0]['id'], 'vehicleId': st['vehicles'][0]['id'], 'destination': 'Learner trip'})
        self.assertTrue(trip['no'])
        self.assertIn('Learner trip', [t['destination'] for t in self.c.get('/api/state')['trips']])

    def test_d_there_is_no_licence(self):
        with self.assertRaises(ApiError) as e:
            self.c.get('/api/licence')
        self.assertEqual(e.exception.code, 404)
        self.assertNotIn('licence', self.c.get('/api/me'))

    def test_e_a_restart_keeps_the_data_and_does_not_load_the_samples_twice(self):
        before = len(self.c.get('/api/state')['trips'])
        self.S.start()
        self.assertEqual(len(self.S.client().get('/api/state')['trips']), before)


class DemoOffTest(unittest.TestCase):
    """With "demo_mode": false the program asks for the first administrator and a sign-in, and starts empty."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('demo-off', extra_cfg={'demo_mode': False}).start()

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_sign_in_is_needed_and_there_is_no_sample_data(self):
        c = self.S.client()
        self.assertFalse(c.get('/api/auth/status')['hasUsers'])
        with self.assertRaises(ApiError) as e:
            c.get('/api/state')
        self.assertEqual(e.exception.code, 401)
        ac = make_authority(self.S)
        self.assertFalse(ac.get('/api/me')['demo'])
        self.assertEqual(ac.get('/api/state')['trips'], [])


class ShippedConfigTest(unittest.TestCase):
    def test_demo_mode_is_on_and_the_licence_hub_is_gone(self):
        with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertIs(cfg.get('demo_mode'), True)
        self.assertNotIn('licence_hub_url', cfg)
        for gone in ('server/licence.py', 'server/afcodes.py', 'server/hub_time.py', 'js/views/licence.js', 'licence-hub'):
            self.assertFalse(os.path.exists(os.path.join(ROOT, gone)), gone)


if __name__ == '__main__':
    unittest.main()
