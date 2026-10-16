"""QA findings fixed for 1.1.3 (report of 15 Oct 2026, B1-B12) and 1.1.4 (16 Oct deep QA N1)."""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness import ApiError, Server, make_authority
from assist import Assist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def put(e, rid, **row):
    return {'e': e, 'id': rid, 'op': 'put', 'row': row}


class B1_ArabicOnCp1252Console(unittest.TestCase):
    def test_arabic_admin_setup_and_login_on_cp1252_console(self):
        old = os.environ.get('PYTHONIOENCODING')
        os.environ['PYTHONIOENCODING'] = 'cp1252'
        try:
            s = Server('cp1252').start()
        finally:
            if old is None:
                os.environ.pop('PYTHONIOENCODING', None)
            else:
                os.environ['PYTHONIOENCODING'] = old
        try:
            c = s.client()
            c.post('/api/auth/setup', {'username': 'yousef', 'full_name': 'يوسف المشغل', 'password': 'Strong-pass1'})
            c2 = s.client()
            c2.login('yousef', 'Strong-pass1')
            self.assertTrue(c2.get('/api/auth/status').get('hasUsers'))
        finally:
            s.cleanup()


class QA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('qa113').start()
        cls.c = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def refused(self, ops, key):
        with self.assertRaises(ApiError) as e:
            self.c.post('/api/commit', {'label': 't', 'ops': ops})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual((e.exception.data or {}).get('key'), key, e.exception.data)

    def test_B3_driver_mobile_checked(self):
        self.refused([put('drivers', 'qd1', name='Mobile Test', mobile='abc123', active=True)], 'err.badMobile')
        self.c.post('/api/commit', {'label': 't', 'ops': [put('drivers', 'qd2', name='Good Mobile', mobile='01012345678', active=True)]})

    def test_B4_name_empty_and_too_long(self):
        self.refused([put('drivers', 'qd3', name='', active=True)], 'err.nameEmpty')
        self.refused([put('drivers', 'qd4', name='x' * 5000, active=True)], 'err.tooLong')

    def test_B6_upload_must_be_a_real_picture(self):
        with self.assertRaises(ApiError) as e:
            self.c.call('POST', '/api/upload?name=x.png', raw=b'MZ\x90\x00' + b'\x00' * 100, headers={'Content-Type': 'application/octet-stream'})
        self.assertEqual(e.exception.data.get('key'), 'err.notImage')
        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
        self.assertIn('src', self.c.call('POST', '/api/upload?name=ok.png', raw=png, headers={'Content-Type': 'application/octet-stream'}))

    def test_B7_xlsx_arabic_filename(self):
        import urllib.request
        req = urllib.request.Request(self.S.base + '/api/xlsx', data=json.dumps({'filename': 'تقرير', 'sheets': [{'name': 'S', 'head': ['a'], 'rows': [['1']]}]}).encode(),
                                     method='POST', headers={'Content-Type': 'application/json'})
        with self.c.opener.open(req, timeout=60) as r:
            body, cd = r.read(), r.headers.get('Content-Disposition')
        self.assertTrue(body.startswith(b'PK'))
        self.assertIn("filename*=UTF-8''%D8%AA%D9%82%D8%B1%D9%8A%D8%B1.xlsx", cd)

    def test_B8_print_missing_trip_is_404(self):
        with self.assertRaises(ApiError) as e:
            self.c.get('/api/word/form?trip=nope')
        self.assertEqual(e.exception.code, 404)

    def test_B11_absurd_licence_expiry(self):
        self.refused([put('drivers', 'qd5', name='Old Licence', licenseExpiry='1900-01-01', active=True)], 'err.badExpiry')
        self.refused([put('drivers', 'qd5', name='Old Licence', licenseExpiry='2019-12-31', active=True)], 'err.badExpiry')
        self.refused([put('drivers', 'qd5', name='Old Licence', licenseExpiry='2026-10-12-x', active=True)], 'err.badDate')
        self.c.post('/api/commit', {'label': 't', 'ops': [put('drivers', 'qd6', name='Fine Licence', licenseExpiry='2020-01-01', active=True)]})

    def test_old_rows_stay_editable(self):
        """A row saved before these rules (e.g. by an import) can still be edited in its other fields."""
        old = dict(name='Legacy ' + 'n' * 150, mobile='N/A', licenseExpiry='2019-12-31', active=True)
        self.c.post('/api/commit', {'label': 'import', 'force': True, 'ops': [put('drivers', 'qd9', **old)]})
        drv = next(d for d in self.c.get('/api/state')['drivers'] if d['id'] == 'qd9')
        self.c.post('/api/commit', {'label': 't', 'ops': [{'e': 'drivers', 'id': 'qd9', 'op': 'put', 'ver': drv.get('ver'),
                                                           'row': {**old, 'name': drv['name'], 'vendor': 'Other', 'active': False}}]})

    def test_B3_mobile_pairs_and_arabic_digits(self):
        self.c.post('/api/commit', {'label': 't', 'ops': [put('drivers', 'qd7', name='Two Phones', mobile='01012345678 / 01112345678', active=True),
                                                          put('drivers', 'qd8', name='Arabic Digits', mobile='٠١٠١٢٣٤٥٦٧٨', active=True)]})


class B12_NoSyntaxWarning(unittest.TestCase):
    def test_app_compiles_without_warnings(self):
        r = subprocess.run([sys.executable, '-W', 'error::SyntaxWarning', '-c',
                            "import ast,sys; compile(open(sys.argv[1],encoding='utf-8').read(), 'app.py', 'exec')",
                            os.path.join(ROOT, 'server', 'app.py')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class B5_B9_B10_Strings(unittest.TestCase):
    def test_keys_present(self):
        ar = open(os.path.join(ROOT, 'js', 'i18n', 'ar.js'), encoding='utf-8').read()
        en = open(os.path.join(ROOT, 'js', 'i18n', 'en.js'), encoding='utf-8').read()
        for k in ('err.offline', 'err.fullFolder', 'err.httpsOnly', 'err.badMobile', 'err.nameEmpty', 'err.badExpiry', 'err.notImage'):
            self.assertIn(f"'{k}'", ar)
            self.assertIn(f"'{k}'", en)
        self.assertIn("err.offline", open(os.path.join(ROOT, 'js', 'core.js'), encoding='utf-8').read())
        sys.path.insert(0, os.path.join(ROOT, 'server'))
        import errkeys
        self.assertEqual(errkeys.key_for('This PC already has a working licence.')[0], 'lic.have_licence')
        self.assertEqual(errkeys.key_for('Type the full folder, for example E:\\TO-Backups.')[0], 'err.fullFolder')


class ReviewFixes(unittest.TestCase):
    def test_licence_view_formats_dates_with_ui_dt(self):
        src = open(os.path.join(ROOT, 'js', 'views', 'licence.js'), encoding='utf-8').read()
        self.assertIn('TO.ui.dt(iso)', src)
        self.assertIn("safeWhenMessage('lic.req.offline', q.next_try)", src)
        self.assertIn("return TO.esc(iso)", src)
        self.assertIn("'<bdi dir=\"ltr\">' + whenText(iso)", src)
        self.assertIn("'<bdi dir=\"ltr\">'", src)
        self.assertNotIn("{ when: q.next_try || '' }", src)
        self.assertNotIn('TO.fmt.dt', src)

    def test_activity_maps_real_audit_label_prefixes(self):
        src = open(os.path.join(ROOT, 'js', 'views', 'activity.js'), encoding='utf-8').read()
        for needle in ('GA approved trip', 'GA declined trip', 'Restore backup of', 'Word import', 'act.entity.'):
            self.assertIn(needle, src)
        self.assertIn("act.label.driverLinkReplaced", src)
        self.assertIn("gaApproved: 'f.ga'", src)
        self.assertIn("billableKm: 'f.billableKm'", src)
        self.assertIn("act.label.driverEvents", src)
        self.assertIn("act.label.driverPhoto", src)
        self.assertIn("act.label.releasedPhone", src)
        self.assertIn("label.slice(18)", src)
        self.assertNotIn("label.slice(19)", src)
        ar = open(os.path.join(ROOT, 'js', 'i18n', 'ar.js'), encoding='utf-8').read()
        self.assertIn("'act.label.restoreBackupOf': 'استرجاع نسخة احتياطية من '", ar)

    def test_reviewed_arabic_wording_is_consistent(self):
        ar = open(os.path.join(ROOT, 'js', 'i18n', 'ar.js'), encoding='utf-8').read()
        for needle in ('ساعة الجهاز اترجعت لورا', 'إيه اللي بيتبعت؟', 'مفيش مشاوير ولا أشخاص ولا مبالغ',
                       "'act.label.driverLinkReplaced'", "'act.label.releasedPhone'", 'موافقة الشؤون العامة', 'رفض الشؤون العامة',
                       "'act.label.driverEvents'", "'act.label.driverPhoto'", 'النسخة دي مترخّصة', 'ابعت الرقم ده للشركة',
                       'فترة التجربة خلصت — اضغط تفعيل', 'الترخيص اتفعّل',
                       'المشوار ده ماينفعش يتمسح. الغيه واكتب السبب.'):
            self.assertIn(needle, ar)
        for leftover in ('ات رجعت', 'ما الذي يُرسل؟', 'إدارة عامة', 'هذه النسخة مرخّصة', 'أرسل هذا الرقم',
                         'انتهت الفترة التجريبية', 'تم تفعيل الترخيص', 'لغيه بسبب مكتوب'):
            self.assertNotIn(leftover, ar)


class N1_LicenceHubPrecedence(unittest.TestCase):
    DEFAULT_URL = 'https://trip-orders-licence-hub.mflma2040.workers.dev'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'FACTORY_LICENCE_HUB_URL': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def loaded_config(self, saved=None):
        """Run the real loader without importing app.py (which starts the application)."""
        path = os.path.join(self.tmp.name, 'config.json')
        if saved is not None:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(saved, f)
        with open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'DEFAULT_CONFIG') or
                 (isinstance(n, ast.FunctionDef) and n.name == 'load_config')]
        namespace = {'os': os, 'json': json, 'CONFIG_PATH': path}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), namespace)
        return namespace['load_config']()

    def assist(self, cfg):
        a = Assist(self.tmp.name, cfg, ROOT)
        self.addCleanup(a.close)
        return a

    def test_fresh_install_gets_default_without_persisting_an_override(self):
        cfg = self.loaded_config()
        self.assertEqual(self.assist(cfg).licence_hub_url(), self.DEFAULT_URL)
        with open(os.path.join(self.tmp.name, 'config.json'), encoding='utf-8') as f:
            self.assertNotIn('licence_hub_url', json.load(f))

    def test_saved_database_url_preserved_on_upgrade(self):
        a = self.assist({})
        a.kv('licence_hub_url', 'https://saved-hub.test/')
        a.close()
        a = self.assist(self.loaded_config({}))
        self.assertEqual(a.licence_hub_url(), 'https://saved-hub.test')
        self.assertEqual(a.kv('licence_hub_url'), 'https://saved-hub.test/')

    def test_saved_database_url_preserved_when_config_is_recreated(self):
        a = self.assist({})
        a.kv('licence_hub_url', 'https://saved-hub.test')
        a.close()
        self.assertEqual(self.assist(self.loaded_config()).licence_hub_url(), 'https://saved-hub.test')

    def test_legacy_config_without_saved_url_gets_default(self):
        self.assertEqual(self.assist(self.loaded_config({})).licence_hub_url(), self.DEFAULT_URL)

    def test_explicit_config_overrides_database_and_default(self):
        for url in ('https://configured-hub.test/', '', 'off'):
            with self.subTest(url=url):
                a = self.assist(self.loaded_config({'licence_hub_url': url}))
                a.kv('licence_hub_url', 'https://saved-hub.test')
                self.assertEqual(a.licence_hub_url(), url.rstrip('/') if url.startswith('https://') else '')
                a.close()

    def test_environment_overrides_config_database_and_default(self):
        a = self.assist(self.loaded_config({'licence_hub_url': 'https://configured-hub.test'}))
        a.kv('licence_hub_url', 'https://saved-hub.test')
        for url in ('https://environment-hub.test/', ' OfF '):
            with self.subTest(url=url), patch.dict(os.environ, {'FACTORY_LICENCE_HUB_URL': url}):
                self.assertEqual(a.licence_hub_url(), url.rstrip('/') if url.startswith('https://') else '')

    def test_saved_database_disable_is_preserved(self):
        for url in ('', 'off'):
            with self.subTest(url=url):
                a = self.assist(self.loaded_config({}))
                a.kv('licence_hub_url', url)
                self.assertEqual(a.licence_hub_url(), '')
                a.close()


class N1_LicenceHubDefault(unittest.TestCase):
    def test_empty_licence_hub_url_disables_online_request(self):
        s = Server('lic-off', extra_cfg={'licence_hub_url': ''}).start()
        try:
            ac = make_authority(s)
            self.assertFalse(ac.get('/api/licence')['request']['available'])
        finally:
            s.cleanup()

    def test_explicit_licence_hub_url_enables_request_without_using_telemetry_hub(self):
        s = Server('lic-on', extra_cfg={'licence_hub_url': 'https://hub.test', 'hub_url': 'https://telemetry.test'}).start()
        try:
            ac = make_authority(s)
            self.assertTrue(ac.get('/api/licence')['request']['available'])
        finally:
            s.cleanup()

    def test_off_environment_disables_configured_licence_hub_case_insensitively(self):
        old = os.environ.get('FACTORY_LICENCE_HUB_URL')
        os.environ['FACTORY_LICENCE_HUB_URL'] = ' OfF '
        s = None
        try:
            s = Server('lic-env-off', extra_cfg={'licence_hub_url': 'https://hub.test'}).start()
            self.assertFalse(make_authority(s).get('/api/licence')['request']['available'])
        finally:
            if s:
                s.cleanup()
            if old is None:
                os.environ.pop('FACTORY_LICENCE_HUB_URL', None)
            else:
                os.environ['FACTORY_LICENCE_HUB_URL'] = old


class ActivityAuditColumnsHttpTest(unittest.TestCase):
    """The audit route keeps permissions, search and the full row unless a whitelist column list is asked for."""

    FIELDS = 'id,ts,user,node,label,entity,op,entity_id'
    MARKER = 'XQ-DEST-77'

    @classmethod
    def setUpClass(cls):
        cls.S = Server('audit-cols').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'c1', name='Cars', exportSheet='All Car'),
            put('vehicles', 'v1', plate='ABC 123', active=True)]})
        cls.ac.post('/api/trips/new', {'categoryId': 'c1', 'vehicleId': 'v1', 'destination': cls.MARKER})

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def login_as(self, name, perms, scopes=None):
        self.ac.post('/api/users/save', {'username': name, 'full_name': name, 'password': 'Perm-test-77x', 'must_change': False,
                                         'role': 'Custom', 'perms': perms, 'scopes': scopes})
        client = self.S.client()
        client.login(name, 'Perm-test-77x')
        return client

    def assert_hidden(self, payload):
        if self.MARKER in json.dumps(payload, ensure_ascii=False):
            raise AssertionError('projected audit response included a hidden column')

    def assert_kept(self, payload):
        if self.MARKER not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError('stored-text search missed a hidden column')

    def test_projection_default_search_and_whitelist(self):
        fields = '/api/audit?limit=20&fields=' + self.FIELDS
        projected = self.ac.get(fields)
        full = self.ac.get('/api/audit?limit=20')
        self.assertGreater(full['total'], 1)
        self.assertEqual(projected['total'], full['total'])
        self.assertEqual(len(projected['rows']), len(full['rows']))
        allowed = set(self.FIELDS.split(','))
        self.assertTrue(projected['rows'])
        for row in projected['rows']:
            self.assertEqual(set(row), allowed)
        self.assertIn('changes', full['rows'][0])
        self.assertIn('ip', full['rows'][0])
        self.assertIn('node_name', full['rows'][0])
        self.assertNotIn('node_name', projected['rows'][0])
        self.assert_hidden(projected)
        found = self.ac.get('/api/audit?limit=50&q=' + self.MARKER + '&fields=' + self.FIELDS)
        stored = self.ac.get('/api/audit?limit=50&q=' + self.MARKER)
        self.assertGreaterEqual(stored['total'], 1)
        self.assertEqual(found['total'], stored['total'])
        self.assert_hidden(found)
        self.assert_kept(stored)
        one = self.ac.get('/api/audit?limit=1&fields=' + self.FIELDS)
        self.assertEqual(len(one['rows']), 1)
        self.assertGreater(one['total'], 1)
        self.assertEqual(self.ac.get('/api/audit?limit=1')['total'], one['total'])
        via_columns = self.ac.get('/api/audit?limit=20&columns=' + self.FIELDS)
        self.assertEqual(via_columns['total'], projected['total'])
        self.assert_hidden(via_columns)
        both = self.ac.get('/api/audit?limit=5&fields=id,label&columns=id,label')
        self.assertEqual(set(both['rows'][0]), {'id', 'label'})
        spaced = self.ac.get('/api/audit?limit=5&fields=' + 'id,%20ts,%20user,%20node,%20label,%20entity,%20op,%20entity_id')
        self.assertEqual(set(spaced['rows'][0]), set(self.FIELDS.split(',')))
        activity = self.ac.get('/api/activity?limit=5')
        self.assertIn('rows', activity)
        self.assertIn('total', activity)
        for path in ('/api/audit?fields=before', '/api/audit?fields=id,changes', '/api/audit?fields=',
                     '/api/audit?columns=ip', '/api/audit?fields=id&columns=label', '/api/audit?fields=id%3Bdrop',
                     '/api/activity?fields=id', '/api/activity?columns=detail'):
            try:
                self.ac.get(path)
            except ApiError as caught:
                self.assertEqual(caught.code, 400, path)
                self.assertEqual((caught.data or {}).get('key'), 'err.badRequest', path)
                low = str(caught.msg).lower()
                for leak in ('traceback', 'sqlite', 'operationalerror', 'before', 'changes', 'drop'):
                    self.assertNotIn(leak, low, path)
            else:
                self.fail('column list was accepted: ' + path)

    def test_permissions_still_gate_a_column_list(self):
        blocked = self.login_as('ada.view', ['overview.view'])
        for path in ('/api/audit?limit=5', '/api/audit?limit=5&fields=' + self.FIELDS, '/api/audit?fields=before'):
            with self.assertRaises(ApiError) as caught:
                blocked.get(path)
            self.assertEqual(caught.exception.code, 403, path)
        logs = self.login_as('lee.logs', ['logs.view'])
        admin = self.ac.get('/api/audit?limit=1000&fields=' + self.FIELDS)
        narrowed = logs.get('/api/audit?limit=1000&fields=' + self.FIELDS)
        self.assertGreater(admin['total'], narrowed['total'])
        self.assertGreater(narrowed['total'], 0)
        self.assertTrue(all(row.get('entity') not in ('users', 'nodes', 'userCommands', 'profiles') for row in narrowed['rows']))
        self.assertTrue(any(row.get('entity') == 'users' for row in admin['rows']))
        self.assertEqual(logs.get('/api/audit?limit=1000')['total'], narrowed['total'])
        self.assertTrue(narrowed['rows'])
        self.assertTrue(all(set(row) == set(self.FIELDS.split(',')) for row in narrowed['rows']))
        self.assert_hidden(narrowed)
        scoped = self.login_as('sam.scope', ['logs.view'], scopes=['missing-cat'])
        self.assertEqual(scoped.get('/api/audit?limit=1000&fields=' + self.FIELDS)['total'], 0)
        self.assertEqual(scoped.get('/api/audit?limit=1000')['total'], 0)


if __name__ == '__main__':
    unittest.main()
