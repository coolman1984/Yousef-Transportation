"""Regression tests for Yousef QA report v1.1.4 (YT-01..YT-18) and auth flows (v1.1.5)."""
import concurrent.futures
import json
import os
import socket
import threading
import unittest

from harness import ADMIN, ApiError, Server, make_authority

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class YT115(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('yt115').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'seed', 'ops': [
            put('tripCategories', 'cat1', name='Office', exportSheet='All'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True),
            put('drivers', 'd1', name='Driver One', active=True)]})

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_YT03_register_pending_until_approved(self):
        r = self.S.client().post('/api/auth/register', {'username': 'newhire', 'full_name': 'New Hire', 'password': 'Office-pass88'})
        self.assertEqual(len(r['request_code']), 6)
        with self.assertRaises(ApiError) as e:
            self.S.client().login('newhire', 'Office-pass88')
        self.assertIn('waiting', str(e.exception.msg).lower())
        pending = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'newhire'][0]
        self.ac.post('/api/users/review', {'id': pending['id'], 'decision': 'approve', 'role': 'Viewer', 'perms': ['overview.view']})
        self.S.client().login('newhire', 'Office-pass88')

    def test_YT03_reset_code_flow(self):
        self.ac.post('/api/users/save', {'username': 'resetme', 'full_name': 'Reset Me', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
        uid = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'resetme'][0]['id']
        code = self.ac.post('/api/users/reset-code', {'id': uid})
        self.S.client().post('/api/auth/reset', {'username': 'resetme', 'code': code['code'], 'password': 'Fresh-pass42'})
        self.S.client().login('resetme', 'Fresh-pass42')

    def test_YT04_licence_activation_ui_flag(self):
        lic = self.ac.get('/api/licence')
        self.assertTrue(lic.get('activation_ui'))

    def test_YT05_board_limits_cards(self):
        src = open(os.path.join(ROOT, 'js', 'views', 'board.js'), encoding='utf-8').read()
        self.assertIn('BOARD_LIMIT', src)

    def test_YT06_state_unchanged_when_version_matches(self):
        v = self.ac.get('/api/state')['version']
        slim = self.ac.get('/api/state?version=' + str(v))
        self.assertTrue(slim.get('unchanged'))
        self.assertNotIn('trips', slim)

    def test_YT07_server_request_queue_size(self):
        src = open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read()
        self.assertIn('request_queue_size = 128', src)

    def test_YT08_no_times_i18n_keys(self):
        for lang in ('en', 'ar'):
            data = open(os.path.join(ROOT, 'js', 'i18n', lang + '.js'), encoding='utf-8').read()
            self.assertIn('why.NO_TIMES', data)
            self.assertIn('why.NO_KM', data)

    def test_YT09_implausible_trip_refused(self):
        tid = self.ac.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'destination': 'Far'})['id']
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/close', {'id': tid, 'startKm': 100, 'endKm': 5100, 'startAt': '2026-10-12T08:00', 'endAt': '2026-10-12T09:00'})

    def test_YT10_slide_dismiss_hint(self):
        data = open(os.path.join(ROOT, 'js', 'i18n', 'en.js'), encoding='utf-8').read()
        self.assertIn('slide.dismiss', data)

    def test_YT11_port_busy_does_not_open_browser(self):
        src = open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read()
        self.assertNotIn('webbrowser.open', src[src.index('Port {port} is already in use'):src.index('Port {port} is already in use') + 400])

    def test_YT12_unknown_hash_not_silent_overview(self):
        src = open(os.path.join(ROOT, 'js', 'shell.js'), encoding='utf-8').read()
        self.assertIn('err.notFound', src)

    def test_YT13_new_trip_form_submits_on_enter(self):
        src = open(os.path.join(ROOT, 'js', 'views', 'trips.js'), encoding='utf-8').read()
        self.assertIn("form.addEventListener('submit'", src)

    def test_YT14_passenger_cap_error(self):
        cat = 'cat1'
        pax = [{'freeText': 'P' + str(i)} for i in range(20)]
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/trips/new', {'categoryId': cat, 'vehicleId': 'v1', 'destination': 'Many', 'passengers': pax})
        self.assertIn('12', str(e.exception.msg))

    def test_YT15_consent_documented(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, 'docs', 'RELEASE_NOTES.md')))

    def test_YT16_licence_page_in_unguided_catalogue(self):
        cat = open(os.path.join(ROOT, 'tests', 'guide_catalogue.js'), encoding='utf-8').read()
        self.assertIn("'licence'", cat)

    def test_YT17_harness_closes_server(self):
        s = Server('yt17').start()
        try:
            s.client().get('/api/auth/status')
        finally:
            s.cleanup()
        self.assertIsNone(s.proc)

    def test_YT18_audit_retention_doc(self):
        path = os.path.join(ROOT, 'docs', 'AUDIT_RETENTION.md')
        self.assertTrue(os.path.isfile(path))


class YT01Lockout(unittest.TestCase):
    def test_YT01_parallel_wrong_logins_lock_account(self):
        s = Server('yt01').start()
        ac = make_authority(s)
        try:
            ac.post('/api/users/save', {'username': 'victim', 'full_name': 'Victim User', 'password': 'Secure-pass9', 'must_change': False,
                                          'perms': ['overview.view'], 'scopes': None})

            def wrong():
                c = s.client()
                try:
                    c.login('victim', 'wrong-' + str(threading.get_ident()))
                except ApiError:
                    pass

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                list(ex.map(lambda _: wrong(), range(10)))
            users = {u['username']: u for u in ac.get('/api/users')['users']}
            u = users['victim']
            self.assertTrue(u['locked'] or u['failed'] >= 5)
            with self.assertRaises(ApiError):
                s.client().login('victim', 'Secure-pass9')
        finally:
            s.cleanup()


class YT02SoleAdmin(unittest.TestCase):
    def test_YT02_sole_admin_not_hard_locked(self):
        s = Server('yt02').start()
        ac = make_authority(s)
        try:
            for _ in range(8):
                try:
                    s.client().login('boss', 'wrong-only')
                except ApiError:
                    pass
            users = {u['username']: u for u in ac.get('/api/users')['users']}
            self.assertFalse(users['boss']['locked'])
            ac.login('boss', ADMIN[1])
        finally:
            s.cleanup()


class YT07ListenBacklog(unittest.TestCase):
    def test_listen_backlog_at_least_64(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('to_app', os.path.join(ROOT, 'server', 'app.py'))
        app_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_mod)
        self.assertGreaterEqual(getattr(app_mod.Server, 'request_queue_size', 0), 64)
