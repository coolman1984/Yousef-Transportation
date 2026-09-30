"""Word: the trip order form (blank, filled, Arabic and English), reading filled forms back (Arabic labels and digits, 12-hour times),
importing them through the same review, and the monthly report."""
import os
import sys
import unittest

from harness import ApiError, Server, make_authority

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import docx_read  # noqa: E402
import docx_write as dw  # noqa: E402
import word_io as W  # noqa: E402


class UnitTest(unittest.TestCase):
    def test_times(self):
        for s, want in [('9:41 صباحاً', '09:41'), ('3:30 مساء', '15:30'), ('٠٩:٤١', '09:41'), ('15:20', '15:20'), ('12:10 ص', '00:10'), ('12:30 م', '12:30'), ('11:05 PM', '23:05'), ('abc', None), ('25:00', None)]:
            self.assertEqual(W.parse_time(s), want, s)

    def test_dates_and_km(self):
        import datetime as dt
        self.assertEqual(W.parse_date('١٥/٠٩/٢٠٢٦'), dt.date(2026, 9, 15))
        self.assertEqual(W.parse_date('2026-09-15'), dt.date(2026, 9, 15))
        self.assertIsNone(W.parse_date('31/02/2026'))
        self.assertEqual(W.parse_km('١٢٬٣٤٥'.replace('٬', ',')), 12345)
        self.assertEqual(W.parse_km('45,210 km'), 45210)

    def test_docx_writer_reader_round_trip(self):
        d = dw.Doc(rtl=True)
        d.para('عنوان')
        d.table([['أ', 'ب'], ['1', '2']], header=True)
        got = docx_read.read(d.bytes())
        self.assertEqual(got['paragraphs'][0], 'عنوان')
        self.assertEqual(got['tables'][0], [['أ', 'ب'], ['1', '2']])

    def test_form_round_trip_both_languages(self):
        ctx = {'no': '26-A-00001', 'passenger': 'Sara Adel', 'department': 'Finance', 'driver': 'Ali Hassan', 'plate': 'أ ب ج 1234', 'startKm': '45000',
               'endKm': '45120', 'startDate': '15/09/2026', 'startTime': '9:00 صباحاً', 'endTime': '3:30 مساء', 'route': 'Office - Site A'}
        for lang in ('ar', 'en'):
            data = W.form(ctx, lang, {'name': 'Test Co', 'footer': 'footer text'}, 'legal line')
            rec = W.parse_forms(data)
            self.assertEqual(len(rec), 1)
            for k in ('passenger', 'driver', 'plate', 'startKm', 'route'):
                self.assertEqual(rec[0][k], ctx[k], (lang, k))
            self.assertIn('legal line', ' '.join(docx_read.read(data)['paragraphs']))

    def test_blank_form_has_every_label(self):
        d = docx_read.read(W.form({}, 'ar'))
        flat = ' '.join(c for row in d['tables'][0] for c in row)
        for _, ar, _ in W.LABELS:
            self.assertIn(ar, flat)

    def test_two_forms_in_one_file(self):
        a = W.form({'driver': 'Ali', 'plate': 'س ع د 111', 'startDate': '01/09/2026'}, 'en')
        b = W.form({'driver': 'Omar', 'plate': 'س ع د 222', 'startDate': '02/09/2026'}, 'en')
        # merge the second table into the first document
        import zipfile, io, re
        za = zipfile.ZipFile(io.BytesIO(a)).read('word/document.xml').decode()
        zb = zipfile.ZipFile(io.BytesIO(b)).read('word/document.xml').decode()
        tb = re.search(r'<w:tbl>.*</w:tbl>', zb, re.S).group(0)
        merged = za.replace('<w:sectPr>', tb + '<w:sectPr>', 1)
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(a)) as src, zipfile.ZipFile(out, 'w') as dst:
            for i in src.infolist():
                dst.writestr(i, merged if i.filename == 'word/document.xml' else src.read(i.filename))
        recs = W.parse_forms(out.getvalue())
        self.assertEqual([r['driver'] for r in recs], ['Ali', 'Omar'])

    def test_refusals(self):
        for bad in (b'', b'hello world' * 20, b'PK' + b'x' * 200):
            with self.assertRaises(W.WordError):
                W.parse_forms(bad)
        empty = dw.Doc()
        empty.para('just text')
        with self.assertRaises(W.WordError) as e:
            W.parse_forms(empty.bytes())
        self.assertIn('No trip order form', str(e.exception))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('word').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def raw(self, path, data):
        return self.ac.call('POST', path, raw=data, headers={'Content-Type': 'application/octet-stream'})

    def test_import_form_then_export(self):
        ac = self.ac
        ctx = {'passenger': 'Sara Adel', 'department': 'Finance', 'driver': 'Ali Hassan', 'plate': 'أ ب ج 1234', 'startKm': '45000', 'endKm': '45120',
               'startDate': '١٥/٠٩/٢٠٢٦', 'startTime': '9:00 صباحاً', 'endTime': '3:30 مساء', 'route': 'Office - Site A'}
        data = W.form(ctx, 'ar')
        with self.assertRaises(ApiError) as e:
            self.raw('/api/word/preview?name=f.docx', data)
        self.assertIn('category', str(e.exception.msg).lower())
        pv = self.raw('/api/word/preview?category=Extra&name=f.docx', data)
        self.assertEqual((pv['stats']['total'], pv['stats']['new']), (1, 1))
        res = ac.post('/api/excel/commit', {'id': pv['id']})
        self.assertEqual(res['trips'], 1)
        t = ac.get('/api/state')['trips'][0]
        self.assertEqual((t['source'], t['date'], t['startKm'], t['endKm'], t['startAt'][11:16], t['endAt'][11:16]), ('word', '2026-09-15', 45000, 45120, '09:00', '15:30'))
        with self.assertRaises(ApiError):
            self.raw('/api/word/preview?category=Extra', b'not a document at all' * 10)
        blank = ac.call('GET', '/api/word/form?lang=en')
        self.assertTrue(blank[:2] == b'PK')
        filled = ac.call('GET', f'/api/word/form?lang=ar&trip={t["id"]}')
        self.assertEqual(W.parse_forms(filled)[0]['driver'], 'Ali Hassan')
        rep = ac.call('GET', '/api/word/report?ym=2026-09&lang=ar')
        text = ' '.join(c for tb in docx_read.read(rep)['tables'] for r in tb for c in r)
        self.assertIn('Ali Hassan', text)
        self.assertIn('120', text)
        rep_en = ac.call('GET', '/api/word/report?ym=2026-09&lang=en')
        self.assertIn('Monthly trips report', ' '.join(docx_read.read(rep_en)['paragraphs']))


if __name__ == '__main__':
    unittest.main()
