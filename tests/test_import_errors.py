"""F16: an explicit error contract for imports. Every refusal has a stable CODE (the screens translate the code, not the English words),
the result does not depend on whether the PC has Microsoft Office, a failed import changes no data and never repeats the file's contents."""
import json
import os
import sys
import unittest

from harness import ApiError, Server, make_authority

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import com_office as C  # noqa: E402
import excel_io as X  # noqa: E402
import formats as F  # noqa: E402
import word_io as W  # noqa: E402
import xlsx_write as w  # noqa: E402

DRM = b'<## NASCA DRM FILE - VER1.00 ##>' + bytes(range(256)) * 4
MARK = 'SECRET-MARKER-4711'
CASES = [(DRM, 'f.xlsx', 'drm'), (b'%PDF-1.7 ' + b'x' * 200, 'f.xlsx', 'pdf'), (b'\xff\xd8\xff\xe0' + b'x' * 200, 'f.xlsx', 'image'), (b'', 'f.xlsx', 'empty'),
         (b'PK\x03\x04' + b'x' * 300, 'f.xlsx', 'damaged'), (b'\x00\x01\x02\x03' * 300, 'f.xlsx', 'unknown')]


class NoOffice(unittest.TestCase):
    """The contract is the same on a PC with Office and on one without: Office is switched off for these tests, and tested on its own below."""

    def setUp(self):
        self._avail = C.available
        C.available = lambda app: False

    def tearDown(self):
        C.available = self._avail

    def test_a_every_refusal_has_its_code_at_every_layer(self):
        for data, name, code in CASES:
            for engine in ('auto', 'native'):
                for fn, err in ((F.read_workbook, F.FormatError), (X.read_workbook, X.ImportError_)):
                    with self.assertRaises(err) as e:
                        fn(data, name, engine)
                    self.assertEqual(e.exception.code, code, (code, engine, fn.__module__))
                with self.assertRaises(W.WordError) as e:
                    W.parse_forms(data, name.replace('xlsx', 'docx'), engine)
                self.assertEqual(e.exception.code, code, ('word', code, engine))

    def test_b_the_wrong_door_and_the_content_problems(self):
        with self.assertRaises(X.ImportError_) as e:
            X.read_workbook(W.form({}, 'en'), 'f.docx')
        self.assertEqual(e.exception.code, 'wordGiven')
        with self.assertRaises(W.WordError) as e:
            W.parse_forms(w.build([w.Sheet('A', [['a']])]), 'f.xlsx')
        self.assertEqual(e.exception.code, 'sheetGiven')
        with self.assertRaises(X.ImportError_) as e:
            X.make_preview('u', w.build([w.Sheet('A', [['nothing', 'useful'], [MARK, 1]])]), {}, 'f.xlsx')
        self.assertEqual(e.exception.code, 'noColumns')
        with self.assertRaises(X.ImportError_) as e:
            X.get_preview('nope', 'u')
        self.assertEqual(e.exception.code, 'previewExpired')
        with self.assertRaises(W.WordError) as e:
            W.preview('u', W.form({}, 'en'), {}, '', 'f.docx')
        self.assertEqual(e.exception.code, 'needCategory')

    def test_c_errors_never_repeat_what_is_in_the_file(self):
        bad = [(w.build([w.Sheet('A', [['nothing', 'useful'], [MARK, MARK]])]), 'f.xlsx'),
               (('a;b\n' + MARK + ';' + MARK).encode(), 'f.csv'),
               (b'PK\x03\x04' + MARK.encode() * 40, 'f.xlsx')]
        for data, name in bad:
            try:
                X.make_preview('u', data, {}, name)
            except X.ImportError_ as e:
                self.assertNotIn(MARK, str(e), name)
                self.assertTrue(e.code, name)
            else:
                self.fail('should have been refused: ' + name)
        import docx_write as dw
        d = dw.Doc()
        d.para(MARK)
        try:
            W.parse_forms(d.bytes(), 'f.docx')
        except W.WordError as e:
            self.assertNotIn(MARK, str(e))
            self.assertEqual(e.code, 'noForm')
        else:
            self.fail('a document without a form must be refused')


class OfficeCodes(unittest.TestCase):
    """The optional Office route has its own codes; the answer of a pretend PowerShell is mapped, whatever Office is installed here."""

    def setUp(self):
        self._avail, self._run = C.available, C._subprocess_runner
        C.available = lambda app: True

    def tearDown(self):
        C.available, C._subprocess_runner = self._avail, self._run

    def go(self, answer=None, timeout=False):
        import subprocess

        def fake(cmd, env, timeout_s):
            if timeout:
                raise subprocess.TimeoutExpired(cmd, timeout_s)
            if answer is not None:
                with open(env['TO_OUT'], 'w', encoding='utf-8') as f:
                    json.dump(answer, f)
        C._subprocess_runner = fake
        with self.assertRaises(X.ImportError_) as e:
            X.read_workbook(DRM, 'f.xlsx')
        return e.exception

    def test_d_each_office_outcome_has_a_code(self):
        self.assertEqual(self.go({'error': 'The password is wrong'}).code, 'officePassword')
        self.assertEqual(self.go(timeout=True).code, 'officeTimeout')
        self.assertEqual(self.go(None).code, 'officeFailed')
        self.assertEqual(self.go({'error': 'Retrieving the COM class factory 80040154 Class not registered'}).code, 'officeMissing')
        self.assertEqual(self.go({'error': 'Something odd'}).code, 'officeFailed')
        self.assertEqual(self.go({'error': 'The workbook is too large'}).code, 'big')

    def test_e_office_forced_but_missing(self):
        C.available = lambda app: False
        with self.assertRaises(X.ImportError_) as e:
            X.read_workbook(w.build([w.Sheet('A', [['a']])]), 'f.xlsx', 'office')
        self.assertEqual(e.exception.code, 'officeMissing')


class ApiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('imperr').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_f_the_answer_carries_the_code_and_nothing_is_changed(self):
        before = self.ac.get('/api/version')['version']
        for data, name, code in CASES:
            with self.assertRaises(ApiError) as e:
                self.ac.call('POST', f'/api/import/preview?name={name}&engine=native', raw=data)
            self.assertEqual((e.exception.code, e.exception.data.get('code')), (400, code), name)
            self.assertTrue(e.exception.data.get('error'))
        with self.assertRaises(ApiError) as e:
            self.ac.call('POST', '/api/excel/commit', {'id': 'does-not-exist'})
        self.assertEqual(e.exception.data.get('code'), 'previewExpired')
        self.assertEqual(self.ac.get('/api/version')['version'], before, 'a refused import changes no data')


if __name__ == '__main__':
    unittest.main()
