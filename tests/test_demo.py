"""No sign-in and training mode (owner requests, 17 October 2026).

The program opens without signing in and has no licence or activation. The real work starts empty; one big button opens a separate
training copy (its own port and data folder) full of sample data, and a button inside it goes back to the real work.
Runs the real server with sign-in off, as in the shipped config.json."""
import collections
import json
import os
import shutil
import tempfile
import unittest

from harness import ApiError, Client, Server, free_port, make_authority

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NoSignInTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix=f'to-home-{os.getpid()}-')   # the training copy lives under the program's home folder
        cls.old_home = os.environ.get('TO_HOME')
        os.environ['TO_HOME'] = cls.home
        cls.tport = free_port()
        cls.S = Server('nosign', extra_cfg={'sign_in': False, 'training_port': cls.tport}).start()
        cls.c = cls.S.client()        # no cookie, no setup, no login

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()               # stops the server and its whole process group, the training copy included
        if cls.old_home is None:
            os.environ.pop('TO_HOME', None)
        else:
            os.environ['TO_HOME'] = cls.old_home
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_a_the_program_opens_as_the_built_in_administrator(self):
        st = self.c.get('/api/auth/status')
        self.assertTrue(st['hasUsers'])
        me = st['me']
        self.assertFalse(me['signIn'])
        self.assertFalse(me['training'])
        self.assertTrue(me['admin'])
        self.assertFalse(me['must_change'])
        self.assertEqual(self.c.get('/api/me')['username'], 'admin')

    def test_b_the_real_work_starts_empty(self):
        st = self.c.get('/api/state')
        self.assertEqual(st['trips'], [])
        self.assertEqual(st['vehicles'], [])

    def test_c_work_is_saved_without_signing_in(self):
        self.c.post('/api/commit', {'label': 'lists', 'ops': [
            {'e': 'tripCategories', 'id': 'rc1', 'op': 'put', 'row': {'id': 'rc1', 'name': 'Real car', 'exportSheet': 'All'}},
            {'e': 'vehicles', 'id': 'rv1', 'op': 'put', 'row': {'id': 'rv1', 'plate': 'REAL 1', 'plateKey': 'real1', 'active': True}}]})
        trip = self.c.post('/api/trips/new', {'categoryId': 'rc1', 'vehicleId': 'rv1', 'destination': 'Real trip'})
        self.assertTrue(trip['no'])
        self.assertEqual([t['destination'] for t in self.c.get('/api/state')['trips']], ['Real trip'])

    def test_d_there_is_no_licence(self):
        with self.assertRaises(ApiError) as e:
            self.c.get('/api/licence')
        self.assertEqual(e.exception.code, 404)
        self.assertNotIn('licence', self.c.get('/api/me'))

    def test_e_training_opens_a_separate_copy_with_sample_data(self):
        port = self.c.post('/api/training/open', {})['port']
        self.assertEqual(port, self.tport)
        t = Client(f'http://127.0.0.1:{port}')
        me = t.get('/api/auth/status')['me']
        self.assertTrue(me['training'])
        self.assertEqual(me['realPort'], self.S.port, 'the "back to real work" button needs the real port')
        st = t.get('/api/state')
        for entity in ('tripCategories', 'vehicles', 'drivers', 'departments', 'people', 'places', 'routes', 'trips', 'tripPassengers', 'tripAmendments'):
            self.assertTrue(st[entity], f'no sample {entity}')
        status = collections.Counter(x['status'] for x in st['trips'])
        for s in ('draft', 'closed', 'cancelled'):
            self.assertTrue(status[s], f'no sample trip that is {s}: {status}')
        self.assertTrue(any(x.get('reviewedAt') for x in st['trips']), 'some trips were reviewed')
        self.assertTrue(any(not x.get('reviewedAt') and x['status'] == 'closed' for x in st['trips']), 'some wait in the review queue')
        self.assertTrue({x.get('gaApproved') for x in st['trips']} >= {'yes', 'no'}, 'approved and declined examples')
        self.assertTrue(t.get('/api/insights'))
        self.assertTrue(t.get('/api/reports?month=' + max(x['date'] for x in st['trips'])[:7]))
        self.assertNotIn('Real trip', [x['destination'] for x in st['trips']], 'the real work never shows in training')
        self.assertTrue(os.path.isdir(os.path.join(self.home, 'training', 'data')))
        self.assertFalse(t.get('/api/consent/prompt?lang=ar')['ask'], 'the remote-help card does not cover the training copy')

        # practise, then make sure the real work did not change
        t.post('/api/trips/new', {'categoryId': st['tripCategories'][0]['id'], 'vehicleId': st['vehicles'][0]['id'], 'destination': 'Practice trip'})
        self.assertIn('Practice trip', [x['destination'] for x in t.get('/api/state')['trips']])
        self.assertNotIn('Practice trip', [x['destination'] for x in self.c.get('/api/state')['trips']])
        self.assertEqual(self.c.post('/api/training/open', {})['port'], port, 'a second press reuses the running copy')
        with self.assertRaises(ApiError) as e:
            t.post('/api/training/open', {})
        self.assertEqual(e.exception.code, 400, 'the training copy does not open another one')

        # start again: the practice is gone and the samples are back
        samples = len(st['trips'])
        self.assertEqual(self.c.post('/api/training/reset', {})['port'], port)
        again = Client(f'http://127.0.0.1:{port}').get('/api/state')['trips']
        self.assertEqual(len(again), samples)
        self.assertNotIn('Practice trip', [x['destination'] for x in again])

    def test_f_a_restart_keeps_the_real_data(self):
        before = len(self.c.get('/api/state')['trips'])
        self.S.start()
        self.assertEqual(len(self.S.client().get('/api/state')['trips']), before)


class TrainingWatchTest(unittest.TestCase):
    def test_the_training_copy_stops_when_the_real_program_is_gone(self):
        import sys
        import threading
        sys.path.insert(0, os.path.join(ROOT, 'server'))
        import training
        stopped = threading.Event()
        training.watch_real(free_port(), stopped.set, every=0.05, misses=2).join(5)   # nobody listens on that port
        self.assertTrue(stopped.is_set())


class SignInTest(unittest.TestCase):
    """With "sign_in": true the program asks for the first administrator and a sign-in, and starts empty."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('signin', extra_cfg={'sign_in': True}).start()

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
        self.assertTrue(ac.get('/api/me')['signIn'])
        self.assertEqual(ac.get('/api/state')['trips'], [])


class UpgradeFromSignInTest(unittest.TestCase):
    """An office that used sign-in before (administrator "boss", not "admin") opens without signing in after the update."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('upgrade', extra_cfg={'sign_in': True}).start()

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_the_existing_administrator_is_used(self):
        ac = make_authority(self.S)
        ac.post('/api/commit', {'label': 'lists', 'ops': [
            {'e': 'tripCategories', 'id': 'uc1', 'op': 'put', 'row': {'id': 'uc1', 'name': 'Old car', 'exportSheet': 'All'}}]})
        self.S.set_cfg(sign_in=False)
        self.S.start()
        c = self.S.client()                                   # no cookie
        me = c.get('/api/auth/status')['me']
        self.assertEqual(me['username'], 'boss')
        self.assertFalse(me['must_change'])
        self.assertEqual([x['name'] for x in c.get('/api/state')['tripCategories']], ['Old car'])
        self.assertEqual([u['username'] for u in c.get('/api/users')['users']], ['boss'], 'no second built-in administrator')


class ShippedConfigTest(unittest.TestCase):
    def test_sign_in_is_off_and_the_licence_hub_is_gone(self):
        with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertIs(cfg.get('sign_in'), False)
        self.assertNotIn('training', cfg, 'only the training copy writes "training": true in its own config')
        self.assertNotIn('licence_hub_url', cfg)
        for gone in ('server/licence.py', 'server/afcodes.py', 'server/hub_time.py', 'js/views/licence.js', 'licence-hub'):
            self.assertFalse(os.path.exists(os.path.join(ROOT, gone)), gone)


if __name__ == '__main__':
    unittest.main()
