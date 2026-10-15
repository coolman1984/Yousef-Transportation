"""QA findings fixed for 1.1.3 (report of 15 Oct 2026, B1-B12)."""
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
        data = self.c.post('/api/xlsx', {'filename': 'تقرير', 'sheets': [{'name': 'S', 'head': ['a'], 'rows': [['1']]}]})
        self.assertTrue(bytes(data).startswith(b'PK'))

    def test_B8_print_missing_trip_is_404(self):
        with self.assertRaises(ApiError) as e:
            self.c.get('/api/word/form?trip=nope')
        self.assertEqual(e.exception.code, 404)

    def test_B11_absurd_licence_expiry(self):
        self.refused([put('drivers', 'qd5', name='Old Licence', licenseExpiry='1900-01-01', active=True)], 'err.badExpiry')


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


if __name__ == '__main__':
    unittest.main()
