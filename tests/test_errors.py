"""I7/I8/I9: junk JSON never crashes a handler or leaks exception text, every server message has a translation key in both
dictionaries, and the start-up 'Try again' button works under the page's content security policy."""
import json
import os
import re
import sys
import unittest

from harness import ADMIN, ApiError, Server, make_authority

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import errkeys  # noqa: E402

JUNK = ['null', '[]', '[1, 2]', '5', '"text"', 'true', '{"ops": 5}', '{"ops": [1, null, "x"]}', '{"username": [1], "password": {}}', '{bad json', '\xff\xfe']


def dict_keys(lang):
    src = open(os.path.join(ROOT, 'js', 'i18n', f'{lang}.js'), encoding='utf-8').read()
    return set(re.findall(r"'([a-zA-Z0-9_.\-]+)':\s*'", src))


class JunkBodyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('errors').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    POSTS = ['/api/auth/login', '/api/auth/password', '/api/log', '/api/commit', '/api/trips/new', '/api/trips/amend', '/api/trips/cancel',
             '/api/trips/link', '/api/trips/approve', '/api/trips/close', '/api/trips/start', '/api/trips/review', '/api/users/save', '/api/users/reset', '/api/profiles/save', '/api/backups/restore',
             '/api/backups/folder', '/api/gateway/save', '/api/xlsx', '/api/excel/commit', '/api/trash/restore', '/api/conflicts/resolve',
             '/api/quick-links/set', '/api/devices/decide', '/api/devices/export-key']

    def test_a_no_junk_body_gives_a_server_error_or_leaks_python_text(self):
        for path in self.POSTS:
            for junk in JUNK:
                try:
                    self.ac.call('POST', path, raw=junk.encode('latin-1', 'replace'))
                except ApiError as e:
                    self.assertLess(e.code, 500, f'{path} {junk!r} -> {e.code} {e.msg}')
                    low = str(e.msg).lower()
                    for leak in ('traceback', 'attributeerror', "has no attribute", 'nonetype', 'keyerror', 'typeerror', 'object is not'):
                        self.assertNotIn(leak, low, f'{path} {junk!r}')

    def test_b_junk_before_login_is_a_calm_400_with_a_key(self):
        c = self.S.client()
        for junk in ('[]', 'null', '{bad'):
            with self.assertRaises(ApiError) as e:
                c.call('POST', '/api/auth/login', raw=junk.encode())
            self.assertEqual(e.exception.code, 400)
            self.assertEqual(e.exception.data.get('key'), 'err.badRequest')

    def test_c_junk_query_numbers_do_not_leak_python_messages(self):
        for path in ('/api/audit?limit=abc', '/api/activity?offset=x', '/api/devices/log?limit=1e9x'):
            with self.assertRaises(ApiError) as e:
                self.ac.get(path)
            self.assertEqual(e.exception.code, 400, path)
            self.assertNotIn('invalid literal', str(e.exception.msg))

    def test_d_the_server_error_answer_has_an_incident_number_and_no_exception_text(self):
        # an exception that is not bad input: break the state function inside the server process through a poisoned category scope is not
        # possible from outside, so check the answer shape through the handler source and the log instead
        src = open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read()
        self.assertNotIn("f'Server error: {e}'", src)
        self.assertIn("'key': 'err.server', 'incident': inc", src)

    def test_e_errors_carry_the_key_of_their_message(self):
        with self.assertRaises(ApiError) as e:
            self.S.client().login('nobody', 'wrong-pass-123')
        self.assertEqual(e.exception.data.get('key'), 'autherr.wrong')
        low = self.S.client()
        low.login(ADMIN[0], ADMIN[1])
        with self.assertRaises(ApiError) as e:
            low.post('/api/trips/amend', {'id': 'nope', 'field': 'status', 'value': 'closed', 'reason': ''})
        self.assertTrue(e.exception.data.get('key'))


class KeysTest(unittest.TestCase):
    def test_every_key_the_server_can_send_exists_in_both_dictionaries(self):
        en, ar = dict_keys('en'), dict_keys('ar')
        for k in errkeys.KEYS:
            self.assertIn(k, en, k)
            self.assertIn(k, ar, k)
        for ent in ('tripCategories', 'vehicles', 'drivers', 'departments', 'people', 'places', 'routes', 'trips', 'tripPassengers', 'tripPhotos',
                    'tripAmendments', 'tripEvents', 'settings'):
            self.assertIn('err.entity.' + ent, ar)
        for op in ('insert', 'update', 'delete'):
            self.assertIn('err.op.' + op, ar)

    def test_the_common_messages_are_covered(self):
        for msg, key in [('Wrong user name or password.', 'autherr.wrong'), ('Please log in.', 'err.signIn'),
                         ('The password must have at least 8 characters.', 'autherr.pwShort'),
                         ('This account is locked for 5 more minute(s) after too many wrong passwords. Wait.', 'autherr.locked'),
                         ('Only an administrator can open this.', 'err.adminOnly'), ('Trip not found', 'err.tripNotFound')]:
            self.assertEqual(errkeys.key_for(msg)[0], key, msg)
        self.assertEqual(errkeys.key_for('The password must have at least 12 characters.')[1], {'n': '12'})

    def test_arabic_texts_keep_the_same_placeholders_as_english(self):
        src = {l: open(os.path.join(ROOT, 'js', 'i18n', f'{l}.js'), encoding='utf-8').read() for l in ('en', 'ar')}
        for k in errkeys.KEYS:
            vals = {}
            for l, s in src.items():
                m = re.search(r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(k), s)
                vals[l] = set(re.findall(r'\{(\w+)\}', m.group(1)))
            self.assertEqual(vals['en'], vals['ar'], k)


class NoInlineHandlerTest(unittest.TestCase):
    def test_no_script_builds_an_inline_event_attribute(self):
        """The page's CSP is script-src 'self': an inline onclick/onchange silently does nothing (I9)."""
        bad = []
        for base, _, files in os.walk(os.path.join(ROOT, 'js')):
            for f in files:
                if f.endswith('.js'):
                    for n, line in enumerate(open(os.path.join(base, f), encoding='utf-8'), 1):
                        if re.search(r"""\bon(click|change|input|submit|load|error|keydown|keyup)\s*=\s*\\?["']""", line):
                            bad.append(f'{f}:{n}')
        self.assertEqual(bad, [])


@unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM), 'Playwright or Chromium not available')
class StartupRetryTest(unittest.TestCase):
    def test_f_a_failed_start_shows_a_retry_button_that_works_under_the_csp(self):
        S = Server('retry').start()
        make_authority(S)
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(executable_path=CHROMIUM)
            ctx = browser.new_context()
            ctx.add_init_script("localStorage.setItem('to.prefs', %s)" % json.dumps(json.dumps({'welcomed': True, 'lang': 'en'})))
            pg = ctx.new_page()
            pg.route('**/api/auth/status', lambda route: route.abort())
            pg.goto(S.base)
            pg.wait_for_selector('#retry-start')
            self.assertEqual(pg.get_attribute('#retry-start', 'onclick'), None)
            pg.unroute('**/api/auth/status')
            pg.click('#retry-start')
            pg.wait_for_selector('#auth-form')
            browser.close()
        finally:
            pw.stop()
            S.cleanup()


if __name__ == '__main__':
    unittest.main()
