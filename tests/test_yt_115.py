"""Regression tests for Yousef QA report v1.1.4 (YT-01..YT-18) and auth flows (v1.1.5)."""
import concurrent.futures
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import warnings
from unittest import mock

from harness import ADMIN, ApiError, Server, make_authority, wait_until

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


def _fold_fresh_auth(data_dir):
    """Rebuild users from journal.db into a new auth.db (multi-PC fold)."""
    import auth
    from journal import Journal
    from node import Node
    from store import REPLICATED

    auth_path = os.path.join(data_dir, 'auth.db')
    for path in (auth_path, auth_path + '-wal', auth_path + '-shm'):
        if os.path.isfile(path):
            os.remove(path)
    node = Node(data_dir)
    journal = Journal(data_dir, node, REPLICATED, log=lambda *_a, **_k: None)
    a = auth.Auth(data_dir)
    a.attach(journal, node)
    a.fold_pending()
    return a


def _journal_clear_reset_bindings(data_dir):
    import sqlite3
    db = os.path.join(data_dir, 'journal.db')
    bindings = []
    con = sqlite3.connect(db)
    try:
        for (body,) in con.execute('SELECT body FROM changes'):
            try:
                env = json.loads(body or '')
            except (TypeError, ValueError):
                continue
            for op in env.get('ops') or []:
                s = op.get('s') or {}
                if s.get('cmd') == 'clear-reset-code':
                    bindings.append(s.get('reset_hash'))
    finally:
        con.close()
    return bindings


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
            self.S.client().login('newhire', 'wrong-password')
        self.assertNotIn('waiting', str(e.exception.msg).lower())
        with self.assertRaises(ApiError) as e2:
            self.S.client().login('newhire', 'Office-pass88')
        self.assertIn('waiting', str(e2.exception.msg).lower())
        pending = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'newhire'][0]
        self.ac.post('/api/users/review', {'id': pending['id'], 'decision': 'approve', 'role': 'Viewer', 'perms': ['overview.view']})
        self.S.client().login('newhire', 'Office-pass88')

    def test_YT03_reset_code_flow(self):
        self.ac.post('/api/users/save', {'username': 'resetme', 'full_name': 'Reset Me', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
        uid = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'resetme'][0]['id']
        code = self.ac.post('/api/users/reset-code', {'id': uid})
        spaced = code['code'][:4] + '-' + code['code'][4:]
        self.S.client().post('/api/auth/reset', {'username': 'resetme', 'code': spaced, 'password': 'Fresh-pass42'})
        self.S.client().login('resetme', 'Fresh-pass42')

    def test_YT03_reset_code_lockout_clears_on_success(self):
        self.ac.post('/api/users/save', {'username': 'resetlock', 'full_name': 'Reset Lock', 'password': 'Office-pass12', 'must_change': False,
                                          'perms': ['overview.view'], 'scopes': None})
        uid = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'resetlock'][0]['id']
        for _ in range(6):
            try:
                self.S.client().login('resetlock', 'wrong-password')
            except ApiError:
                pass
        users = {u['username']: u for u in self.ac.get('/api/users')['users']}
        self.assertTrue(users['resetlock']['locked'])
        code = self.ac.post('/api/users/reset-code', {'id': uid})['code']
        self.S.client().post('/api/auth/reset', {'username': 'resetlock', 'code': code, 'password': 'Fresh-pass99'})
        self.S.client().login('resetlock', 'Fresh-pass99')

    def test_YT115_lock_survives_profile_save_after_reset(self):
        """Local lockout must not be cleared when a later replicated user save materializes stale fields (Grok r3 P2-1)."""
        S = Server('yt115lock').start()
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'locksave', 'full_name': 'Lock Save', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'locksave'][0]['id']
            code = ac.post('/api/users/reset-code', {'id': uid})['code']
            cl.post('/api/auth/reset', {'username': 'locksave', 'code': code, 'password': 'Fresh-pass42'})
            for _ in range(6):
                try:
                    cl.login('locksave', 'wrong-password')
                except ApiError:
                    pass
            self.assertTrue({u['username']: u for u in ac.get('/api/users')['users']}['locksave']['locked'])
            cur = [u for u in ac.get('/api/users')['users'] if u['id'] == uid][0]
            ac.post('/api/users/save', {'id': uid, 'ver': cur['ver'], 'username': 'locksave', 'full_name': 'Lock Save Renamed', 'password': 'Fresh-pass42',
                                         'must_change': False, 'perms': ['overview.view'], 'scopes': None})
            self.assertTrue({u['username']: u for u in ac.get('/api/users')['users']}['locksave']['locked'])
        finally:
            S.cleanup()

    def test_YT115_clear_reset_code_replicated_on_success(self):
        S = Server('yt115clr-ok').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'clr_ok', 'full_name': 'Clr Ok', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'clr_ok'][0]['id']
            code = ac.post('/api/users/reset-code', {'id': uid})['code']
            cl.post('/api/auth/reset', {'username': 'clr_ok', 'code': code, 'password': 'Fresh-pass42'})
            bindings = _journal_clear_reset_bindings(data_dir)
            self.assertTrue(bindings)
            self.assertTrue(all(bindings))
        finally:
            S.kill()
        import auth as auth_mod
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('clr_ok',)).fetchone()
            self.assertIsNotNone(row)
            self.assertFalse(row['reset_hash'])
            with self.assertRaises(auth_mod.AuthError):
                a.reset_with_code('clr_ok', code, 'Another-pass99', '127.0.0.1')
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_clear_reset_code_replicated_after_three_wrong_guesses(self):
        S = Server('yt115clr-bad').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'clr_bad', 'full_name': 'Clr Bad', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'clr_bad'][0]['id']
            burned_code = ac.post('/api/users/reset-code', {'id': uid})['code']
            for _ in range(3):
                try:
                    cl.post('/api/auth/reset', {'username': 'clr_bad', 'code': 'BADCODE1', 'password': 'Fresh-pass42'})
                except ApiError:
                    pass
            bindings = _journal_clear_reset_bindings(data_dir)
            self.assertEqual(len(bindings), 1)
            self.assertTrue(bindings[0])
        finally:
            S.kill()
        import auth as auth_mod
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('clr_bad',)).fetchone()
            self.assertIsNotNone(row)
            self.assertFalse(row['reset_hash'])
            with self.assertRaises(auth_mod.AuthError):
                a.reset_with_code('clr_bad', burned_code, 'Fresh-pass42', '127.0.0.1')
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_reissued_reset_code_survives_wrong_guess(self):
        S = Server('yt115reissue').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'reissue', 'full_name': 'Reissue', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'reissue'][0]['id']
            ac.post('/api/users/reset-code', {'id': uid})
            import sqlite3
            auth_db = os.path.join(data_dir, 'auth.db')
            con = sqlite3.connect(auth_db)
            con.row_factory = sqlite3.Row
            try:
                stale_hash = con.execute('SELECT reset_hash FROM users WHERE id=?', (uid,)).fetchone()['reset_hash']
            finally:
                con.close()
            for _ in range(3):
                try:
                    cl.post('/api/auth/reset', {'username': 'reissue', 'code': 'BADCODE1', 'password': 'Fresh-pass42'})
                except ApiError:
                    pass
            code2 = ac.post('/api/users/reset-code', {'id': uid})['code']
        finally:
            S.kill()
        import auth as auth_mod
        import uuid
        from journal import Journal
        from node import Node
        from store import REPLICATED
        node = Node(data_dir)
        journal = Journal(data_dir, node, REPLICATED, log=lambda *_a, **_k: None)
        writer = auth_mod.Auth(data_dir)
        writer.attach(journal, node)
        writer._write('test', '127.0.0.1', 'stale clear-reset-code', [
            {'e': 'userCommands', 'id': uuid.uuid4().hex, 'op': 'insert', 'noaudit': True,
             's': {'cmd': 'clear-reset-code', 'user': uid, 'reset_hash': stale_hash}}])
        writer.conn.close()
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('reissue',)).fetchone()
            self.assertTrue(row['reset_hash'])
            a.reset_with_code('reissue', code2, 'Fresh-pass55', '127.0.0.1')
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('reissue',)).fetchone()
            self.assertFalse(row['reset_hash'])
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_used_reset_code_not_revived_by_profile_save(self):
        S = Server('yt115code').start()
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'coderevive', 'full_name': 'Code Revive', 'password': 'Office-pass12', 'must_change': False,
                                          'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'coderevive'][0]['id']
            code = ac.post('/api/users/reset-code', {'id': uid})['code']
            for _ in range(3):
                try:
                    cl.post('/api/auth/reset', {'username': 'coderevive', 'code': 'BADCODE1', 'password': 'Fresh-pass42'})
                except ApiError:
                    pass
            cur = [u for u in ac.get('/api/users')['users'] if u['id'] == uid][0]
            ac.post('/api/users/save', {'id': uid, 'ver': cur['ver'], 'username': 'coderevive', 'full_name': 'Code Revive', 'password': 'Office-pass12',
                                         'must_change': False, 'perms': ['overview.view'], 'scopes': None})
            with self.assertRaises(ApiError):
                cl.post('/api/auth/reset', {'username': 'coderevive', 'code': code, 'password': 'Fresh-pass42'})
        finally:
            S.cleanup()

    def test_YT03_suspended_username_cannot_reregister(self):
        S = Server('yt115suspend').start()
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'wasactive', 'full_name': 'Was Active', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'wasactive'][0]['id']
            ac.post('/api/users/review', {'id': uid, 'decision': 'suspend', 'reason': 'Policy test'})
            with self.assertRaises(ApiError) as e:
                cl.post('/api/auth/register', {'username': 'wasactive', 'full_name': 'New Try', 'password': 'Office-pass88'})
            self.assertIn('taken', str(e.exception.msg).lower())
        finally:
            S.cleanup()

    def test_YT03_refused_signup_shows_reason(self):
        self.S.client().post('/api/auth/register', {'username': 'refused1', 'full_name': 'Refused One', 'password': 'Office-pass88'})
        pending = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'refused1'][0]
        self.ac.post('/api/users/review', {'id': pending['id'], 'decision': 'reject', 'reason': 'Not on the staff list'})
        with self.assertRaises(ApiError) as e:
            self.S.client().login('refused1', 'Office-pass88')
        self.assertEqual(e.exception.data.get('key'), 'autherr.signupRejectedReason')
        self.assertEqual((e.exception.data.get('vars') or {}).get('reason'), 'Not on the staff list')

    def test_YT03_cannot_suspend_sole_admin(self):
        boss = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'boss'][0]
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/users/review', {'id': boss['id'], 'decision': 'suspend', 'reason': 'Test'})
        self.assertEqual(e.exception.data.get('key'), 'autherr.lastAdmin')

    def test_YT115_reject_journals_clear_reset_code(self):
        S = Server('yt115rejclr').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            ac.post('/api/users/save', {'username': 'rejclr', 'full_name': 'Rej Clr', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'rejclr'][0]['id']
            burned = ac.post('/api/users/reset-code', {'id': uid})['code']
            auth_db = os.path.join(data_dir, 'auth.db')
            con = sqlite3.connect(auth_db)
            try:
                con.execute('UPDATE users SET status=? WHERE id=?', ('pending', uid))
                con.commit()
            finally:
                con.close()
            ac.post('/api/users/review', {'id': uid, 'decision': 'reject', 'reason': 'Not on the staff list'})
            bindings = _journal_clear_reset_bindings(data_dir)
            self.assertTrue(bindings)
        finally:
            S.kill()
        import auth as auth_mod
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('rejclr',)).fetchone()
            self.assertFalse(row['reset_hash'])
            with self.assertRaises(auth_mod.AuthError):
                a.reset_with_code('rejclr', burned, 'Fresh-pass42', '127.0.0.1')
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_rejected_reregister_journals_clear_reset_code(self):
        S = Server('yt115rejreg').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            cl = S.client()
            cl.post('/api/auth/register', {'username': 'rejagain', 'full_name': 'Rej Again', 'password': 'Office-pass88'})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'rejagain'][0]['id']
            ac.post('/api/users/review', {'id': uid, 'decision': 'reject', 'reason': 'Not on the staff list'})
            from auth import hash_password
            auth_db = os.path.join(data_dir, 'auth.db')
            stale = hash_password('STALE-CODE1')
            con = sqlite3.connect(auth_db)
            try:
                con.execute('UPDATE users SET reset_hash=?, reset_expires=? WHERE id=?',
                            (stale, '2099-01-01T00:00:00', uid))
                con.commit()
            finally:
                con.close()
            cl.post('/api/auth/register', {'username': 'rejagain', 'full_name': 'Rej Again', 'password': 'Office-pass99'})
            bindings = _journal_clear_reset_bindings(data_dir)
            self.assertIn(stale, bindings)
        finally:
            S.kill()
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('rejagain',)).fetchone()
            self.assertFalse(row['reset_hash'])
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_failed_commit_still_clears_reset_hash_after_wrong_guesses(self):
        S = Server('yt115commit').start()
        data_dir = S.data_dir
        burned = None
        try:
            ac = make_authority(S)
            cl = S.client()
            ac.post('/api/users/save', {'username': 'commitburn', 'full_name': 'Commit Burn', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'commitburn'][0]['id']
            burned = ac.post('/api/users/reset-code', {'id': uid})['code']
            for _ in range(2):
                try:
                    cl.post('/api/auth/reset', {'username': 'commitburn', 'code': 'BADCODE1', 'password': 'Fresh-pass42'})
                except ApiError:
                    pass
        finally:
            S.kill()
        import auth as auth_mod
        from journal import Journal
        from node import Node
        from store import REPLICATED
        node = Node(data_dir)
        journal = Journal(data_dir, node, REPLICATED, log=lambda *_a, **_k: None)
        a = auth_mod.Auth(data_dir)
        a.attach(journal, node)
        inner = a.conn

        class _FlakyConn:
            def execute(self, sql, *args):
                if str(sql).strip().upper() == 'COMMIT':
                    raise sqlite3.OperationalError('simulated commit failure')
                return inner.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(inner, name)

        a.conn = _FlakyConn()
        try:
            try:
                a.reset_with_code('commitburn', 'BADCODE1', 'Fresh-pass42', '127.0.0.1')
            except (auth_mod.AuthError, sqlite3.OperationalError):
                pass
        finally:
            inner.close()
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('commitburn',)).fetchone()
            self.assertFalse(row['reset_hash'])
            with self.assertRaises(auth_mod.AuthError):
                a.reset_with_code('commitburn', burned, 'Fresh-pass42', '127.0.0.1')
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT115_suspend_journals_clear_reset_code(self):
        S = Server('yt115susclr').start()
        data_dir = S.data_dir
        try:
            ac = make_authority(S)
            ac.post('/api/users/save', {'username': 'susclr', 'full_name': 'Sus Clr', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
            uid = [u for u in ac.get('/api/users')['users'] if u['username'] == 'susclr'][0]['id']
            burned = ac.post('/api/users/reset-code', {'id': uid})['code']
            ac.post('/api/users/review', {'id': uid, 'decision': 'suspend', 'reason': 'Policy test'})
            bindings = _journal_clear_reset_bindings(data_dir)
            self.assertTrue(bindings)
        finally:
            S.kill()
        import auth as auth_mod
        try:
            a = _fold_fresh_auth(data_dir)
            row = a.conn.execute('SELECT reset_hash FROM users WHERE username=?', ('susclr',)).fetchone()
            self.assertFalse(row['reset_hash'])
            with self.assertRaises(auth_mod.AuthError):
                a.reset_with_code('susclr', burned, 'Fresh-pass42', '127.0.0.1')
            a.conn.close()
        finally:
            S.cleanup()

    def test_YT03_suspend_approved_user(self):
        self.ac.post('/api/users/save', {'username': 'suspendme', 'full_name': 'Suspend Me', 'password': 'Office-pass12', 'must_change': False,
                                         'perms': ['overview.view'], 'scopes': None})
        uid = [u for u in self.ac.get('/api/users')['users'] if u['username'] == 'suspendme'][0]['id']
        self.ac.post('/api/users/review', {'id': uid, 'decision': 'suspend', 'reason': 'Policy test'})
        with self.assertRaises(ApiError) as e:
            self.S.client().login('suspendme', 'Office-pass12')
        self.assertIn('suspended', str(e.exception.msg).lower())

    def test_YT04_licence_activation_ui_flag(self):
        lic = self.ac.get('/api/licence')
        self.assertTrue(lic.get('activation_ui'))

    def test_YT05_board_limits_cards(self):
        src = open(os.path.join(ROOT, 'js', 'views', 'board.js'), encoding='utf-8').read()
        m = re.search(r'BOARD_LIMIT\s*=\s*(\d+)', src)
        self.assertTrue(m and int(m.group(1)) == 80)

    def test_YT06_state_unchanged_when_version_matches(self):
        v = self.ac.get('/api/state')['version']
        slim = self.ac.get('/api/state?version=' + str(v))
        self.assertTrue(slim.get('unchanged'))
        self.assertNotIn('trips', slim)
        self.assertEqual(slim['version'], v)
        ins = self.ac.get('/api/insights?version=' + str(v))
        self.assertTrue(ins.get('unchanged'))
        self.assertEqual(ins['version'], v)

    def test_YT115_insights_unchanged_does_not_replace_client_cache(self):
        """Mirror js/data.js applyInsights: slim insights must not wipe trust colours (Grok r3 P2-2)."""

        def apply_insights(cur, ins, want):
            if not want or not ins or ins.get('unchanged'):
                return cur
            return ins

        cached = {'trip1': {'trust': 'green', 'reasons': []}}
        slim = {'version': 3, 'unchanged': True}
        self.assertEqual(apply_insights(cached, slim, True), cached)
        full = {'trip1': {'trust': 'amber', 'reasons': ['NO_KM']}}
        self.assertEqual(apply_insights(cached, full, True), full)
        src = open(os.path.join(ROOT, 'js', 'data.js'), encoding='utf-8').read()
        self.assertIn('loadSeq', src)
        self.assertIn('applyInsights', src)
        self.assertIn("TO.get('/api/insights')", src)
        self.assertIn('ins.unchanged', src)

    def test_YT06_state_unchanged_still_carries_gateway(self):
        """gateway.json is outside the store version; the slim response must refresh the flag."""
        S = Server('yt06gw').start()
        try:
            ac = make_authority(S)
            v = ac.get('/api/state')['version']
            self.assertFalse(ac.get('/api/state?version=' + str(v))['gateway'])
            ac.post('/api/gateway/save', {'url': '', 'pollSeconds': 60})
            ac.post('/api/gateway/generate', {})
            ac.post('/api/gateway/save', {'url': 'https://mailbox.example.workers.dev', 'pollSeconds': 60})
            slim = ac.get('/api/state?version=' + str(v))
            self.assertTrue(slim['unchanged'])
            self.assertTrue(slim['gateway'])
            self.assertNotIn('trips', slim)
        finally:
            S.cleanup()

    def test_YT07_server_request_queue_size(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('to_app', os.path.join(ROOT, 'server', 'app.py'))
        app_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_mod)
        self.assertEqual(getattr(app_mod.Server, 'request_queue_size', 0), 128)

    def test_YT08_no_times_i18n_keys(self):
        for lang in ('en', 'ar'):
            data = open(os.path.join(ROOT, 'js', 'i18n', lang + '.js'), encoding='utf-8').read()
            self.assertIn('why.NO_TIMES', data)
            self.assertIn('why.NO_KM', data)

    def test_YT09_implausible_trip_refused(self):
        tid = self.ac.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'destination': 'Far'})['id']
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/close', {'id': tid, 'startKm': 100, 'endKm': 5100, 'startAt': '2026-10-12T08:00', 'endAt': '2026-10-12T09:00'})
        tid2 = self.ac.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'destination': 'Far2'})['id']
        self.ac.post('/api/trips/close', {'id': tid2, 'startKm': 100, 'endKm': 200, 'startAt': '2026-10-12T08:00', 'endAt': '2026-10-12T09:00'})
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/amend', {'id': tid2, 'field': 'endKm', 'value': 5100, 'reason': 'Typo fix test'})

    def test_YT10_slide_dismiss_hint(self):
        for lang in ('en', 'ar'):
            data = open(os.path.join(ROOT, 'js', 'i18n', lang + '.js'), encoding='utf-8').read()
            self.assertIn('slide.dismiss', data)
        shell = open(os.path.join(ROOT, 'js', 'shell.js'), encoding='utf-8').read()
        self.assertIn('slide.dismiss', shell)

    def test_YT11_port_busy_does_not_open_browser(self):
        src = open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read()
        self.assertNotIn('webbrowser.open', src[src.index('Port {port} is already in use'):src.index('Port {port} is already in use') + 400])

    def test_YT12_unknown_hash_not_silent_overview(self):
        with open(os.path.join(ROOT, 'js', 'shell.js'), encoding='utf-8') as f:
            shell = f.read()
        anchor = shell.index('!PAGES.some')
        self.assertLess(shell.index('err.pageNotFound', anchor), shell.index("TO.go('overview')", anchor))

    def test_YT13_new_trip_form_submits_on_enter(self):
        trips = open(os.path.join(ROOT, 'js', 'views', 'trips.js'), encoding='utf-8').read()
        self.assertIn("form.addEventListener('submit'", trips)
        self.assertIn('type="submit"', trips)
        self.assertIn('data-save', trips)
        self.assertIn('var saving = false', trips)
        self.assertIn('if (saving) return', trips)

    def test_YT14_passenger_cap_error(self):
        cat = 'cat1'
        pax = [{'freeText': 'P' + str(i)} for i in range(20)]
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/trips/new', {'categoryId': cat, 'vehicleId': 'v1', 'destination': 'Many', 'passengers': pax})
        self.assertIn('12', str(e.exception.msg))

    def test_YT15_consent_documented(self):
        notes = open(os.path.join(ROOT, 'docs', 'RELEASE_NOTES.md'), encoding='utf-8').read()
        self.assertIn('1.1.5', notes)
        self.assertRegex(notes, r'consent|remote help|الموافقة', re.I)

    def test_YT16_licence_page_in_unguided_catalogue(self):
        cat = json.load(open(os.path.join(ROOT, 'guide', 'catalogue.json'), encoding='utf-8'))
        self.assertIn('licence', cat.get('unguided', []))
        self.assertIn('licence', cat.get('pages', []))
        lic_problem = next(p for p in cat['problems'] if p['id'] == 'licence-locked')
        self.assertEqual(lic_problem['page'], 'licence')
        for g in cat.get('guides', []):
            for step in g.get('steps', []):
                self.assertNotEqual(step.get('page'), 'licence')
        for lang in ('en', 'ar'):
            data = open(os.path.join(ROOT, 'js', 'i18n', lang + '.js'), encoding='utf-8').read()
            self.assertEqual(len(re.findall(r"'err\.notFound':", data)), 1)

    def test_YT17_harness_closes_server(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            s = Server('yt17').start()
            try:
                s.client().get('/api/auth/status')
            finally:
                s.cleanup()
            self.assertIsNone(s.proc)
            self.assertFalse([w for w in caught if issubclass(w.category, ResourceWarning)])

    def test_YT18_audit_retention_doc(self):
        path = os.path.join(ROOT, 'docs', 'AUDIT_RETENTION.md')
        self.assertTrue(os.path.isfile(path))


class YT115LicenceBackground(unittest.TestCase):
    """Hub approval is picked up by the server licence thread without the licence screen open."""

    @classmethod
    def setUpClass(cls):
        from test_assist import FakeHub
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            Ed25519PrivateKey = None
        cls._lic_poll = os.environ.get('TO_LICENCE_POLL_SEC')
        os.environ['TO_LICENCE_POLL_SEC'] = '3'
        cls._profile_dir = tempfile.mkdtemp(prefix='triporders-yt115lic-')
        cls._prev_device = os.environ.get('TO_DEVICE_ID')
        cls._prev_dpapi = os.environ.get('TRIPORDERS_DPAPI_DIR')
        cls._prev_xdg = os.environ.get('XDG_CONFIG_HOME')
        os.environ['TO_DEVICE_ID'] = 'test-pc-yt115lic'
        os.environ['TRIPORDERS_DPAPI_DIR'] = cls._profile_dir
        os.environ['XDG_CONFIG_HOME'] = cls._profile_dir
        import atrest
        atrest._MASTER = None
        cls.hub = FakeHub(Ed25519PrivateKey.generate() if Ed25519PrivateKey else None)
        pub = cls.hub.public()
        cls.S = Server('yt115lic', extra_cfg={'licence_hub_url': cls.hub.url, 'licence_keys': [pub, f'paid:{pub}']}).start()
        cls.ac = make_authority(cls.S, consent=None)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()
        cls.hub.stop()
        if cls._lic_poll is None:
            os.environ.pop('TO_LICENCE_POLL_SEC', None)
        else:
            os.environ['TO_LICENCE_POLL_SEC'] = cls._lic_poll
        shutil.rmtree(cls._profile_dir, ignore_errors=True)
        for key, val in (('TO_DEVICE_ID', cls._prev_device), ('TRIPORDERS_DPAPI_DIR', cls._prev_dpapi), ('XDG_CONFIG_HOME', cls._prev_xdg)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        import atrest
        atrest._MASTER = None

    def test_background_poll_activates_after_owner_issues(self):
        self.ac.post('/api/licence/request/clear', {})
        self.hub.mode = 'wait'
        self.ac.post('/api/licence/request', {'kind': 'trial'})
        self.assertEqual(self.ac.get('/api/licence/request')['status'], 'waiting')
        self.hub.mode = 'issue'
        def activated():
            lic = self.ac.get('/api/licence')
            return lic.get('full') and (lic.get('request') or {}).get('status') == 'activated'
        self.assertTrue(wait_until(activated, timeout=30, step=0.5, what='licence background activation'))


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
    def test_YT02_sole_admin_reset_guesses_not_hard_locked(self):
        s = Server('yt02r').start()
        ac = make_authority(s)
        try:
            boss = [u for u in ac.get('/api/users')['users'] if u['username'] == 'boss'][0]
            ac.post('/api/users/reset-code', {'id': boss['id']})
            for _ in range(8):
                try:
                    s.client().post('/api/auth/reset', {'username': 'boss', 'code': 'BADCODE1', 'password': 'Fresh-pass42'})
                except ApiError:
                    pass
            users = {u['username']: u for u in ac.get('/api/users')['users']}
            self.assertFalse(users['boss']['locked'])
        finally:
            s.cleanup()

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
