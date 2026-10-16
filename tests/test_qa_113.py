"""QA findings fixed for 1.1.3 (report of 15 Oct 2026, B1-B12) and 1.1.4 (16 Oct deep QA N1)."""
import ast
import json
import os
import subprocess
import sys
import unittest

from harness import ApiError, Server, make_authority

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


class N1_LicenceHubDefault(unittest.TestCase):
    def test_default_config_includes_licence_hub_url(self):
        tree = ast.parse(open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read())
        default = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'DEFAULT_CONFIG')
        url = default['licence_hub_url']
        self.assertTrue(url.startswith('https://'))
        self.assertIn('workers.dev', url)

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


if __name__ == '__main__':
    unittest.main()
