"""Many file types in: Excel (xlsx xlsm xls ods csv tsv html-xls xml-2003) and Word (docx doc odt rtf html-doc), recognised by content;
protected files (company DRM, password) and non-office files get a plain message."""
import datetime as dt
import io
import os
import struct
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import excel_io as X  # noqa: E402
import formats as F  # noqa: E402
import word_io as W  # noqa: E402
import xlsx_write as w  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HDR = ['Date', 'Driver Name', 'Car Plate', 'Requester', 'Destination', 'Strat KM', 'End KM', 'Start', 'End']
ROWS = [['2026-09-01', 'علي حسن', 'س ع د 555', 'Sara Adel', 'المكتب - Capital', '1000', '1120', '09:00', '15:30'],
        ['2026-09-02', 'Ali Hassan', 'ABC 1234', 'Sara Adel', 'Factory', '1120', '1200', '08:00', '22:00']]


def check(tc, data, name):
    rows, rep = X.read_workbook(data, name)
    tc.assertEqual(len(rows), 2, name)
    tc.assertEqual((rows[0]['date'], rows[0]['driver'], rows[0]['startKm'], rows[0]['endKm']), (dt.date(2026, 9, 1), 'علي حسن', 1000, 1120), name)
    tc.assertEqual((rows[0]['startTime'], rows[0]['endTime']), (dt.time(9, 0), dt.time(15, 30)), name)
    tc.assertEqual(rows[1]['plate'], 'ABC 1234', name)
    return rows


class SpreadsheetTypes(unittest.TestCase):
    def test_csv_variants(self):
        def csv(delim, enc, bom=False):
            t = '\n'.join(delim.join(r) for r in [HDR] + ROWS)
            b = t.encode(enc)
            return (b'\xef\xbb\xbf' + b) if bom else b
        for delim in (',', ';', '\t', '|'):
            check(self, csv(delim, 'utf-8', True), 'trips.csv')
        check(self, csv(',', 'utf-16'), 'trips.csv')
        check(self, csv(';', 'cp1256').replace(b'Capital', b'Capital'), 'trips.txt') if False else None
        # Windows Arabic code page without the Latin-only rows
        t = ','.join(HDR) + '\n' + ','.join(ROWS[0]) + '\n' + ','.join(ROWS[1])
        rows, _ = X.read_workbook(t.encode('cp1256', 'replace'), 'old.csv')
        self.assertEqual(rows[0]['driver'], 'علي حسن')

    def test_xlsx_macro_and_template_types_read_the_same(self):
        data = w.build([w.Sheet('All Car', [HDR] + [[dt.date.fromisoformat(r[0]), r[1], r[2], r[3], r[4], int(r[5]), int(r[6]), dt.time.fromisoformat(r[7]), dt.time.fromisoformat(r[8])] for r in ROWS])])
        for ext in ('xlsx', 'xlsm', 'xltx', 'xltm'):
            check(self, data, 'f.' + ext)             # the name does not matter, the content decides

    def test_html_saved_as_xls(self):
        rows = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in [HDR] + ROWS)
        html = f'<html><head><meta charset="utf-8"></head><body><table>{rows}</table></body></html>'.encode('utf-8')
        self.assertEqual(F.sniff(html, 'report.xls'), 'htmlsheet')
        check(self, html, 'report.xls')

    def test_spreadsheetml_2003(self):
        def cell(v, t='String'):
            return f'<Cell><Data ss:Type="{t}">{v}</Data></Cell>'
        body = ''.join('<Row>' + ''.join(cell(c) for c in r) + '</Row>' for r in [HDR] + ROWS)
        xml = ('<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
               f'<Worksheet ss:Name="S"><Table>{body}</Table></Worksheet></Workbook>').encode()
        self.assertEqual(F.sniff(xml, 'x.xml'), 'xml2003')
        check(self, xml, 'x.xml')

    def test_ods(self):
        def cell(v):
            return f'<table:table-cell office:value-type="string"><text:p>{v}</text:p></table:table-cell>'
        body = ''.join('<table:table-row>' + ''.join(cell(c) for c in r) + '</table:table-row>' for r in [HDR] + ROWS)
        content = ('<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
                   'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>'
                   f'<table:table table:name="S">{body}</table:table></office:spreadsheet></office:body></office:document-content>')
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')
            z.writestr('content.xml', content)
        self.assertEqual(F.sniff(b.getvalue(), 'x.ods'), 'ods')
        check(self, b.getvalue(), 'x.ods')

    def test_old_xls_made_by_another_program(self):
        try:
            import xlwt
        except ImportError:
            self.skipTest('xlwt is only used to make a test file')
        wb = xlwt.Workbook(encoding='utf-8')
        ws = wb.add_sheet('All Car')
        for c, h in enumerate(HDR):
            ws.write(0, c, h)
        df, tf = xlwt.easyxf(num_format_str='DD/MM/YYYY'), xlwt.easyxf(num_format_str='HH:MM')
        for r, row in enumerate(ROWS, 1):
            ws.write(r, 0, dt.date.fromisoformat(row[0]), df)
            for c in (1, 2, 3, 4):
                ws.write(r, c, row[c])
            ws.write(r, 5, int(row[5])); ws.write(r, 6, int(row[6]))
            ws.write(r, 7, dt.time.fromisoformat(row[7]), tf); ws.write(r, 8, dt.time.fromisoformat(row[8]), tf)
        for r in range(3, 500):                                  # enough text to need several SST records
            ws.write(r, 4, 'x' * (r % 90) + 'مكان')
        b = io.BytesIO(); wb.save(b)
        self.assertEqual(F.sniff(b.getvalue(), 'old.xls'), 'xls')
        rows, _ = X.read_workbook(b.getvalue(), 'old.xls')
        self.assertEqual(rows[0]['driver'], 'علي حسن')
        self.assertEqual((rows[0]['date'], rows[0]['startTime']), (dt.date(2026, 9, 1), dt.time(9, 0)))

    def test_refusals_are_plain(self):
        cases = [(b'<## NASCA DRM FILE - VER1.00 ##>' + os.urandom(2000), 'document-security'),
                 (b'%PDF-1.7 ' + b'x' * 200, 'pdf'), (b'\xff\xd8\xff\xe0' + b'x' * 200, 'picture'), (b'', 'empty'),
                 (b'PK\x03\x04' + b'x' * 300, 'damaged'), (b'\x00\x01\x02\x03' * 300, 'not recognised')]
        for data, part in cases:
            with self.assertRaises(X.ImportError_) as e:
                X.read_workbook(data, 'f.xlsx')
            self.assertIn(part, str(e.exception).lower(), data[:12])

    def test_a_word_file_given_to_the_excel_door_says_so(self):
        with self.assertRaises(X.ImportError_) as e:
            X.read_workbook(W.form({}, 'en'), 'f.docx')
        self.assertIn('word document', str(e.exception).lower())

    def test_real_drm_wrapped_files_from_the_owner(self):
        d = os.path.join(HERE, '..', 'samples', 'private')
        for f in ('drm_xlsx.bin', 'drm_docx.bin'):
            p = os.path.join(d, f)
            if os.path.exists(p):
                self.assertEqual(F.sniff(open(p, 'rb').read(), f), 'drm')


# --------------------------------------------------------------------------- Word types
LABELS = {'driver': 'اسم السائق', 'plate': 'رقم السيارة', 'startKm': 'الكيلومتر البادئ للرحلة', 'endKm': 'الكيلومتر الناهي للرحلة', 'startDate': 'تاريخ بدء الرحلة', 'startTime': 'وقت بدء الرحلة'}
VALUES = {'driver': 'علي حسن', 'plate': 'س ع د 555', 'startKm': '١٠٠٠', 'endKm': '1120', 'startDate': '01/09/2026', 'startTime': '9:00 صباحاً'}


def check_form(tc, data, name):
    rec = W.parse_forms(data, name)
    tc.assertEqual(len(rec), 1, name)
    for k, v in VALUES.items():
        tc.assertEqual(rec[0][k], v, (name, k))


class WordTypes(unittest.TestCase):
    def test_docx_variants_by_content(self):
        import docx_write as dw
        d = dw.Doc(rtl=True)
        d.table([[LABELS[k], VALUES[k]] for k in LABELS])
        for ext in ('docx', 'docm', 'dotx', 'dotm'):
            check_form(self, d.bytes(), 'f.' + ext)

    def test_html_saved_as_doc(self):
        rows = ''.join(f'<tr><td>{LABELS[k]}</td><td>{VALUES[k]}</td></tr>' for k in LABELS)
        html = f'<html><head><meta charset="utf-8"></head><body><p>x</p><table>{rows}</table></body></html>'.encode()
        self.assertEqual(F.sniff(html, 'form.doc'), 'htmldoc')
        check_form(self, html, 'form.doc')

    def test_odt(self):
        rows = ''.join(f'<table:table-row><table:table-cell><text:p>{LABELS[k]}</text:p></table:table-cell><table:table-cell><text:p>{VALUES[k]}</text:p></table:table-cell></table:table-row>' for k in LABELS)
        content = ('<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
                   f'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Title</text:p><table:table>{rows}</table:table></office:text></office:body></office:document-content>')
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('mimetype', 'application/vnd.oasis.opendocument.text'); z.writestr('content.xml', content)
        self.assertEqual(F.sniff(b.getvalue(), 'f.odt'), 'odt')
        check_form(self, b.getvalue(), 'f.odt')

    def test_rtf_with_arabic_code_page_and_unicode(self):
        def esc(s):
            out = []
            for ch in s:
                try:
                    out.append(f"\\'{ch.encode('cp1256')[0]:02x}" if ord(ch) > 127 else ch)
                except UnicodeEncodeError:
                    out.append(f'\\u{ord(ch)}?')           # what Word writes for characters outside the code page
            return ''.join(out)
        rows = ''.join('\\trowd\\cellx3000\\cellx6000\\intbl ' + esc(LABELS[k]) + '\\cell ' + esc(VALUES[k]) + '\\cell\\row\n' for k in LABELS)
        rtf = ('{\\rtf1\\ansi\\ansicpg1256\\deff0{\\fonttbl{\\f0 Arial;}}\\pard Title\\par\n' + rows + '}').encode('latin-1')
        self.assertEqual(F.sniff(rtf, 'f.rtf'), 'rtf')
        check_form(self, rtf, 'f.rtf')

    def test_old_doc_binary(self):
        data = make_doc(''.join(f'{LABELS[k]}\x07{VALUES[k]}\x07' for k in LABELS) + '\x07\r')
        self.assertEqual(F.sniff(data, 'f.doc'), 'doc')
        check_form(self, data, 'f.doc')

    def test_refusals(self):
        for data, part in ((b'<## NASCA DRM FILE - VER1.00 ##>' + os.urandom(900), 'document-security'), (b'%PDF-1.4' + b'x' * 300, 'pdf')):
            with self.assertRaises(W.WordError) as e:
                W.parse_forms(data, 'f.docx')
            self.assertIn(part, str(e.exception).lower())
        with self.assertRaises(W.WordError) as e:
            W.parse_forms(w.build([w.Sheet('A', [['a']])]), 'f.xlsx')
        self.assertIn('spreadsheet', str(e.exception).lower())


# --------------------------------------------------------------------------- a minimal Word 97 file maker (OLE2 + FIB + piece table)
def make_doc(text):
    raw = text.encode('utf-16-le')
    n = len(text)
    wd = bytearray(8192)
    struct.pack_into('<H', wd, 0, 0xA5EC)
    struct.pack_into('<H', wd, 0x0A, 0x0200)                 # use 1Table
    struct.pack_into('<I', wd, 0x4C, n)
    text_off = 2048
    wd[text_off:text_off + len(raw)] = raw
    plc = struct.pack('<2I', 0, n) + struct.pack('<HIH', 0, text_off, 0)[:8].ljust(8, b'\x00')
    pcd = struct.pack('<H', 0) + struct.pack('<I', text_off) + struct.pack('<H', 0)
    plc = struct.pack('<2I', 0, n) + pcd
    clx = b'\x02' + struct.pack('<I', len(plc)) + plc
    struct.pack_into('<II', wd, 0x1A2, 0, len(clx))
    table = clx.ljust(4096, b'\x00')
    return ole({'WordDocument': bytes(wd).ljust(8192, b'\x00'), '1Table': table})


def ole(streams):
    """OLE2 with big streams only (>= 4096 bytes), sector size 512."""
    SS = 512
    secs, entries, start = [], [], 0
    layout = {}
    nxt = 0
    for name, data in streams.items():
        data = data.ljust(((len(data) + SS - 1) // SS) * SS, b'\x00')
        layout[name] = (nxt, len(data))
        secs.append(data)
        nxt += len(data) // SS
    dir_sec = nxt
    nxt += 1
    fat_sec = nxt
    total = nxt + 1
    fat = [0xFFFFFFFD if False else 0] * 128
    fat = [0xFFFFFFFF] * 128
    for name, (s, ln) in layout.items():
        cnt = ln // SS
        for i in range(cnt):
            fat[s + i] = s + i + 1 if i < cnt - 1 else 0xFFFFFFFE
    fat[dir_sec] = 0xFFFFFFFE
    fat[fat_sec] = 0xFFFFFFFD
    def ent(name, typ, s, size):
        nm = name.encode('utf-16-le') + b'\x00\x00'
        e = nm.ljust(64, b'\x00') + struct.pack('<HBB', len(nm), typ, 1) + struct.pack('<III', 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF) + b'\x00' * 16 + b'\x00' * 4 + b'\x00' * 16
        e = e.ljust(116, b'\x00') + struct.pack('<IQ', s, size)
        return e.ljust(128, b'\x00')
    d = ent('Root Entry', 5, 0xFFFFFFFE, 0)
    for name, (s, ln) in layout.items():
        d += ent(name, 2, s, ln)
    d = d.ljust(512, b'\x00')
    header = bytearray(512)
    header[:8] = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    struct.pack_into('<HHHHH', header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into('<IIIIIIII', header, 44, 1, dir_sec, 0, 4096, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0)
    difat = [fat_sec] + [0xFFFFFFFF] * 108
    struct.pack_into('<109I', header, 76, *difat)
    return bytes(header) + b''.join(secs) + d + struct.pack('<128I', *fat)


if __name__ == '__main__':
    unittest.main()
