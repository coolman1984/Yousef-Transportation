"""Trip Orders - reading the many file types people have: the file is recognised by its CONTENT (not its name), then read into the
same two shapes the rest of the program uses:

    read_workbook(data) -> xlsx_read.Workbook      xlsx xlsm xltx xltm | xls (Excel 97-2003) | ods | csv tsv txt | html/xml "xls" | SpreadsheetML 2003
    read_document(data) -> {'paragraphs','tables'}  docx docm dotx dotm | doc (Word 97-2003) | odt | rtf | html "doc"

Files that cannot be read by any program outside their owner's company (document-security / DRM wrappers, passwords) get a clear
message that says what to do. Nothing here tries to get around such protection.
"""
import codecs
import csv
import datetime as dt
import html
import io
import re
import struct
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import com_office
import docx_read
import xlsx_read
from xlsx_read import Cell, Sheet, Workbook

OFFICE_TMP = None          # folder for the short-lived work files of the Office route (set by the program)
MAX_BYTES = 60 * 1024 * 1024
MAX_CELLS = 400_000


class FormatError(Exception):
    """The file cannot be read; the message says what the person can do."""


MSG = {
    'drm': 'This file is locked by your company\'s document-security system (it starts with "NASCA DRM"). Trip Orders can read it only through Microsoft Excel/Word on a Windows PC where that security program works. '
           'Otherwise open it on such a PC, use Save As to make a new copy as .xlsx (or .docx), or copy the cells into a new blank file; a plain .csv export also works.',
    'encrypted': 'This file is protected with a password. Open it in Excel/Word, remove the password (File, Info, Protect), save a copy, and choose that copy.',
    'pdf': 'This is a PDF. A PDF cannot be read as a table. Use the original Excel or Word file, or export it from the program that made the PDF.',
    'image': 'This is a picture, not a file with data. Choose the Excel or Word file.',
    'xlsb': 'This is an Excel Binary Workbook (.xlsb). Open it in Excel and use Save As, "Excel Workbook (.xlsx)".',
    'old': 'This is a very old Office file (Excel/Word 95 or older). Open it in Excel/Word and Save As .xlsx / .docx.',
    'empty': 'The file is empty.',
    'unknown': 'This file type is not recognised. Choose an Excel (.xlsx .xlsm .xls .ods .csv) or Word (.docx .docm .doc .odt .rtf) file.',
    'big': 'The file is too large to import safely.',
    'damaged': 'The file is damaged and cannot be opened.',
}

WORD_KINDS = {'docx', 'doc', 'odt', 'rtf', 'htmldoc'}
SHEET_KINDS = {'xlsx', 'xls', 'ods', 'csv', 'htmlsheet', 'xml2003'}


# --------------------------------------------------------------------------- recognising a file
OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def sniff(data, name=''):
    """-> one of: drm encrypted pdf image xlsb old empty unknown | xlsx xls ods csv htmlsheet xml2003 | docx doc odt rtf htmldoc"""
    if not data or len(data.strip(b'\x00 \r\n')) < 4:
        return 'empty'
    if len(data) > MAX_BYTES:
        return 'big'
    head = data[:64]
    if b'DRM FILE' in data[:80] or head.startswith(b'<## ') or b'NASCA' in data[:40]:
        return 'drm'
    if head.startswith(b'%PDF'):
        return 'pdf'
    if head[:3] == b'\xff\xd8\xff' or head.startswith((b'\x89PNG', b'GIF8', b'BM')) or (head.startswith(b'RIFF') and b'WEBP' in head[:16]):
        return 'image'
    if head.startswith(b'PK'):
        return _sniff_zip(data)
    if head.startswith(OLE):
        return _sniff_ole(data)
    text = _peek(data)
    low = text.lower()
    if text.startswith('{\\rtf'):
        return 'rtf'
    if '<workbook' in low[:3000] and 'urn:schemas-microsoft-com:office:spreadsheet' in low[:3000]:
        return 'xml2003'
    if '<html' in low[:2000] or '<table' in low[:5000] or '<!doctype html' in low[:200]:
        return 'htmlsheet' if _name_ext(name) in ('xls', 'xlsx', 'xlsm', 'ods', 'csv', '') and not _name_ext(name) in ('doc', 'docx', 'rtf', 'odt') else 'htmldoc'
    if '\x00' in text[:2000] and not data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return 'unknown'
    ext = _name_ext(name)
    if ext in ('doc', 'docx', 'docm', 'dotx', 'dotm', 'odt') and '\n' not in text[:200] and ',' not in text[:200]:
        return 'unknown'
    return 'csv'


def _name_ext(name):
    return name.rsplit('.', 1)[-1].lower() if '.' in (name or '') else ''


def _peek(data, n=6000):
    chunk = data[:n]
    if chunk.startswith(codecs.BOM_UTF16_LE) or chunk.startswith(codecs.BOM_UTF16_BE):
        return chunk.decode('utf-16', 'ignore')
    return chunk.decode('utf-8', 'ignore').lstrip('\ufeff')


def _sniff_zip(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
    except zipfile.BadZipFile:
        return 'damaged'
    if 'xl/workbook.xml' in names:
        return 'xlsx'
    if 'xl/workbook.bin' in names:
        return 'xlsb'
    if 'word/document.xml' in names:
        return 'docx'
    if 'mimetype' in names:
        mt = z.read('mimetype')[:100]
        if b'opendocument.spreadsheet' in mt:
            return 'ods'
        if b'opendocument.text' in mt:
            return 'odt'
    if 'EncryptedPackage' in names:
        return 'encrypted'
    return 'unknown'


def _sniff_ole(data):
    try:
        cfb = CFB(data)
    except FormatError:
        return 'damaged'
    names = set(cfb.names())
    if 'EncryptedPackage' in names or 'EncryptionInfo' in names:
        return 'encrypted'
    if 'Workbook' in names:
        return 'xls'
    if 'Book' in names:
        return 'old'
    if 'WordDocument' in names:
        return 'doc'
    return 'unknown'


def need_sheet(kind):
    if kind in SHEET_KINDS:
        return
    if kind in WORD_KINDS:
        raise FormatError('This is a Word document, not a spreadsheet.')
    raise FormatError(MSG.get(kind) or MSG['unknown'])


def need_document(kind):
    if kind in WORD_KINDS:
        return
    if kind in SHEET_KINDS:
        raise FormatError('This is a spreadsheet, not a Word document.')
    raise FormatError(MSG.get(kind) or MSG['unknown'])


# --------------------------------------------------------------------------- OLE2 compound file (old .xls / .doc)
class CFB:
    def __init__(self, data):
        if len(data) < 512 or not data.startswith(OLE):
            raise FormatError(MSG['damaged'])
        self.d = data
        try:
            self.ssz = 1 << struct.unpack_from('<H', data, 30)[0]
            self.mssz = 1 << struct.unpack_from('<H', data, 32)[0]
            n_fat, dir_start, _, mini_cutoff, minifat_start, n_minifat, difat_start, n_difat = struct.unpack_from('<IIIIIIII', data, 44)
            self.cutoff = mini_cutoff
            difat = list(struct.unpack_from('<109I', data, 76))
            sec = difat_start
            for _ in range(n_difat):
                if sec >= 0xFFFFFFFA:
                    break
                blk = struct.unpack_from('<%dI' % (self.ssz // 4), data, self._off(sec))
                difat += list(blk[:-1])
                sec = blk[-1]
            fat_secs = [s for s in difat if s < 0xFFFFFFFA][:n_fat]
            self.fat = []
            for s in fat_secs:
                self.fat += struct.unpack_from('<%dI' % (self.ssz // 4), data, self._off(s))
            self.dir = self._dir(self._chain_bytes(dir_start))
            root = self.dir[0]
            self.ministream = self._chain_bytes(root['start'])[:root['size']]
            mf = self._chain_bytes(minifat_start) if n_minifat else b''
            self.minifat = list(struct.unpack_from('<%dI' % (len(mf) // 4), mf)) if mf else []
        except (struct.error, IndexError):
            raise FormatError(MSG['damaged'])

    def _off(self, sec):
        return 512 + sec * self.ssz

    def _chain_bytes(self, start, limit=2000000):
        out, sec, n = [], start, 0
        while sec < 0xFFFFFFFA and n < limit:
            out.append(self.d[self._off(sec):self._off(sec) + self.ssz])
            sec = self.fat[sec]
            n += 1
        return b''.join(out)

    def _dir(self, raw):
        ents = []
        for i in range(len(raw) // 128):
            e = raw[i * 128:(i + 1) * 128]
            nl = struct.unpack_from('<H', e, 64)[0]
            name = e[:max(0, nl - 2)].decode('utf-16-le', 'ignore')
            typ = e[66]
            start, size = struct.unpack_from('<IQ', e, 116)[0], struct.unpack_from('<Q', e, 120)[0] & 0xFFFFFFFF
            ents.append({'name': name, 'type': typ, 'start': start, 'size': size})
        return ents

    def names(self):
        return [e['name'] for e in self.dir if e['type'] in (2, 5)]

    def stream(self, name):
        for e in self.dir:
            if e['type'] == 2 and e['name'] == name:
                if e['size'] < self.cutoff:
                    out, sec = [], e['start']
                    while sec < 0xFFFFFFFA and len(out) < 100000:
                        out.append(self.ministream[sec * self.mssz:(sec + 1) * self.mssz])
                        sec = self.minifat[sec]
                    return b''.join(out)[:e['size']]
                return self._chain_bytes(e['start'])[:e['size']]
        return None


# --------------------------------------------------------------------------- old Excel (BIFF8)
def _rk(v):
    if v & 2:
        n = v >> 2
        if n & 0x20000000:
            n -= 0x40000000
        n = float(n)
    else:
        n = struct.unpack('<d', struct.pack('<Q', (v & 0xFFFFFFFC) << 32))[0]
    return n / 100 if v & 1 else n


def _num(n):
    return int(n) if float(n).is_integer() and abs(n) < 1e15 else n


def read_xls(data):
    cfb = CFB(data)
    wb = cfb.stream('Workbook')
    if not wb:
        raise FormatError(MSG['old'])
    # records
    recs, p = [], 0
    while p + 4 <= len(wb):
        rid, ln = struct.unpack_from('<HH', wb, p)
        recs.append((rid, wb[p + 4:p + 4 + ln], p))
        p += 4 + ln
    sst, xf_fmt, formats, sheets, date1904 = [], [], {}, [], False
    i = 0
    while i < len(recs):
        rid, body, pos = recs[i]
        if rid == 0x22:
            date1904 = bool(struct.unpack_from('<H', body)[0])
        elif rid == 0x41E and len(body) >= 3:
            idx = struct.unpack_from('<H', body)[0]
            formats[idx] = _biff_str(body, 2, 16)[0]
        elif rid == 0xE0 and len(body) >= 4:
            xf_fmt.append(struct.unpack_from('<H', body, 2)[0])
        elif rid == 0x85 and len(body) >= 8:
            off, state, typ = struct.unpack_from('<IBB', body)
            if typ == 0:
                nm = _biff_str(body, 6, 8)[0]
                sheets.append((nm, off, state))
        elif rid == 0xFC:
            j, buf = i + 1, bytearray(body)
            conts = []
            while j < len(recs) and recs[j][0] == 0x3C:
                conts.append(recs[j][1]); j += 1
            sst = _parse_sst(body, conts)
            i = j - 1
        elif rid == 0x0A and sheets and sst is not None and pos > sheets[0][1]:
            break
        i += 1

    def is_date(xf):
        fid = xf_fmt[xf] if xf < len(xf_fmt) else 0
        if fid in xlsx_read._DATE_IDS:
            return True
        code = formats.get(fid)
        return bool(code and xlsx_read._is_date_format(code))

    def is_time(xf):
        fid = xf_fmt[xf] if xf < len(xf_fmt) else 0
        code = formats.get(fid)
        return fid in xlsx_read._TIME_ONLY_IDS or bool(code and xlsx_read._is_time_only(code))

    def conv(num, xf):
        if is_date(xf):
            v = xlsx_read.excel_date(num, date1904)
            if is_time(xf) and isinstance(v, dt.datetime):
                return v.time() if num < 1 else v
            return v
        return _num(num)

    out = []
    pos_to_idx = {r[2]: k for k, r in enumerate(recs)}
    for nm, off, state in sheets:
        sh = Sheet(nm, hidden=state != 0)
        k = pos_to_idx.get(off)
        if k is None:
            out.append(sh); continue
        k += 1
        last_formula = None
        n = 0
        while k < len(recs) and recs[k][0] != 0x0A:
            rid, body, _ = recs[k]
            try:
                if rid == 0xFD and len(body) >= 10:
                    r, c, xf, si = struct.unpack_from('<HHHI', body)
                    sh.cells[(r + 1, c + 1)] = Cell(sst[si] if si < len(sst) else '')
                elif rid == 0x204 and len(body) >= 8:
                    r, c, xf, ln = struct.unpack_from('<HHHH', body)
                    sh.cells[(r + 1, c + 1)] = Cell(body[8:8 + ln].decode('cp1252', 'ignore'))
                elif rid == 0x203 and len(body) >= 14:
                    r, c, xf = struct.unpack_from('<HHH', body)
                    sh.cells[(r + 1, c + 1)] = Cell(conv(struct.unpack_from('<d', body, 6)[0], xf))
                elif rid == 0x27E and len(body) >= 10:
                    r, c, xf, v = struct.unpack_from('<HHHI', body)
                    sh.cells[(r + 1, c + 1)] = Cell(conv(_rk(v), xf))
                elif rid == 0xBD and len(body) >= 6:
                    r, c0 = struct.unpack_from('<HH', body)
                    cols = (len(body) - 6) // 6
                    for q in range(cols):
                        xf, v = struct.unpack_from('<HI', body, 4 + q * 6)
                        sh.cells[(r + 1, c0 + q + 1)] = Cell(conv(_rk(v), xf))
                elif rid == 0x06 and len(body) >= 20:
                    r, c, xf = struct.unpack_from('<HHH', body)
                    res = body[6:14]
                    if res[6:8] == b'\xff\xff':
                        last_formula = (r + 1, c + 1) if res[0] == 0 else None
                        if res[0] == 1:
                            sh.cells[(r + 1, c + 1)] = Cell(bool(res[2]))
                    else:
                        sh.cells[(r + 1, c + 1)] = Cell(conv(struct.unpack('<d', res)[0], xf))
                elif rid == 0x207 and last_formula:
                    sh.cells[last_formula] = Cell(_biff_str(body, 0, 16)[0])
                    last_formula = None
                elif rid == 0x205 and len(body) >= 8:
                    r, c, xf, val, is_err = struct.unpack_from('<HHHBB', body)
                    sh.cells[(r + 1, c + 1)] = Cell(None if is_err else bool(val))
            except (struct.error, IndexError):
                pass
            n += 1
            if n > MAX_CELLS * 2:
                raise FormatError(MSG['big'])
            k += 1
        if sh.cells:
            sh.max_row = max(r for r, _ in sh.cells)
            sh.max_col = max(c for _, c in sh.cells)
        out.append(sh)
    if not out:
        raise FormatError(MSG['damaged'])
    return Workbook(out, date1904)


def _biff_str(body, off, lenbits):
    """Unicode string at body[off:] with a 1- or 2-byte length (lenbits 8/16). Returns (text, end offset)."""
    if lenbits == 16:
        n = struct.unpack_from('<H', body, off)[0]; off += 2
    else:
        n = body[off]; off += 1
    flags = body[off]; off += 1
    rich = flags & 8
    ext = flags & 4
    if rich:
        runs = struct.unpack_from('<H', body, off)[0]; off += 2
    if ext:
        extl = struct.unpack_from('<I', body, off)[0]; off += 4
    if flags & 1:
        text = body[off:off + 2 * n].decode('utf-16-le', 'ignore'); off += 2 * n
    else:
        text = body[off:off + n].decode('latin-1'); off += n
    if rich:
        off += 4 * runs
    if ext:
        off += extl
    return text, off


def _parse_sst(first, conts):
    total, uniq = struct.unpack_from('<II', first)
    chunks = [first[8:]] + list(conts)
    out = []
    ci, buf, p = 0, chunks[0], 0

    def next_chunk():
        nonlocal ci, buf, p
        ci += 1
        if ci >= len(chunks):
            raise IndexError
        buf, p = chunks[ci], 0

    try:
        for _ in range(uniq):
            if p + 3 > len(buf):
                next_chunk()
            n = struct.unpack_from('<H', buf, p)[0]; flags = buf[p + 2]; p += 3
            runs = extl = 0
            if flags & 8:
                runs = struct.unpack_from('<H', buf, p)[0]; p += 2
            if flags & 4:
                extl = struct.unpack_from('<I', buf, p)[0]; p += 4
            wide = flags & 1
            text = []
            remaining = n
            while remaining > 0:
                if p >= len(buf):
                    next_chunk()
                    wide = buf[p] & 1; p += 1          # a continued string repeats its flags byte
                avail = (len(buf) - p) // (2 if wide else 1)
                take = min(avail, remaining)
                seg = buf[p:p + take * (2 if wide else 1)]
                text.append(seg.decode('utf-16-le' if wide else 'latin-1', 'ignore'))
                p += take * (2 if wide else 1)
                remaining -= take
            skip = runs * 4 + extl
            while skip > 0:
                if p >= len(buf):
                    next_chunk()
                step = min(skip, len(buf) - p)
                p += step; skip -= step
            out.append(''.join(text))
    except (IndexError, struct.error):
        pass
    return out


# --------------------------------------------------------------------------- old Word (.doc): text only
def read_doc_binary(data):
    cfb = CFB(data)
    wd = cfb.stream('WordDocument')
    if not wd or len(wd) < 0x1A8 or struct.unpack_from('<H', wd, 0)[0] != 0xA5EC:
        raise FormatError(MSG['old'])
    flags = struct.unpack_from('<H', wd, 0x0A)[0]
    if flags & 0x0100:
        raise FormatError(MSG['encrypted'])
    table = cfb.stream('1Table' if flags & 0x0200 else '0Table')
    if table is None:
        raise FormatError(MSG['damaged'])
    ccp_text = struct.unpack_from('<I', wd, 0x4C)[0]
    fc_clx, lcb_clx = struct.unpack_from('<II', wd, 0x1A2)
    clx = table[fc_clx:fc_clx + lcb_clx]
    p = 0
    while p < len(clx) and clx[p] == 1:                     # skip the formatting properties
        p += 3 + struct.unpack_from('<H', clx, p + 1)[0]
    if p >= len(clx) or clx[p] != 2:
        raise FormatError(MSG['damaged'])
    lcb = struct.unpack_from('<I', clx, p + 1)[0]
    plc = clx[p + 5:p + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from('<%dI' % (n + 1), plc)
    text = []
    for i in range(n):
        fc = struct.unpack_from('<I', plc, 4 * (n + 1) + 8 * i + 2)[0]
        count = cps[i + 1] - cps[i]
        if fc & 0x40000000:
            start = (fc & 0x3FFFFFFF) // 2
            text.append(wd[start:start + count].decode('cp1252', 'ignore'))
        else:
            text.append(wd[fc:fc + 2 * count].decode('utf-16-le', 'ignore'))
    full = ''.join(text)[:ccp_text]
    return _split_word_text(full)


def _split_word_text(full):
    """Word text: \\r ends a paragraph, \\x07 ends a table cell (and a row, which looks like an empty cell). The cells go in one
    flat row, which is enough to find "label, value" pairs."""
    paragraphs, cells = [], []
    cur = []
    for ch in full:
        if ch == '\x07':
            cells.append(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', ''.join(cur)).strip()); cur = []
        elif ch == '\r':
            t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', ''.join(cur)).strip()
            if t:
                paragraphs.append(t)
            cur = []
        else:
            cur.append(ch)
    t = ''.join(cur).strip()
    if t:
        paragraphs.append(t)
    return {'paragraphs': paragraphs, 'tables': [[cells]] if cells else []}


# --------------------------------------------------------------------------- OpenDocument
_ODS = {'t': '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}', 'o': '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}',
        'x': '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'}


def _odf_root(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        if sum(i.file_size for i in z.infolist()) > MAX_BYTES:
            raise FormatError(MSG['big'])
        return ET.fromstring(z.read('content.xml'))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise FormatError(MSG['damaged'])


def _odf_text(el):
    parts = []

    def walk(e):
        if e.tag == _ODS['x'] + 's':
            parts.append(' ' * int(e.get(_ODS['x'] + 'c', '1')))
        elif e.tag == _ODS['x'] + 'tab':
            parts.append(' ')
        elif e.tag == _ODS['x'] + 'line-break':
            parts.append('\n')
        if e.text and e.tag not in (_ODS['x'] + 's',):
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)
    walk(el)
    return ''.join(parts).strip()


def _duration(s):
    m = re.fullmatch(r'PT(\d+)H(\d+)M(\d+(?:\.\d+)?)S', s or '')
    if not m:
        return None
    h, mi, se = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return dt.time(h, mi, int(se)) if h < 24 else dt.timedelta(hours=h, minutes=mi, seconds=se)


def read_ods(data):
    root = _odf_root(data)
    T, O = _ODS['t'], _ODS['o']
    out, cells_total = [], 0
    for tb in root.iter(T + 'table'):
        sh = Sheet(tb.get(T + 'name') or 'Sheet', hidden=tb.get(T + 'display') == 'false')
        r = 0
        for row in tb.iter(T + 'table-row'):
            reps = int(row.get(T + 'number-rows-repeated', '1'))
            vals = []
            for cell in row:
                if cell.tag not in (T + 'table-cell', T + 'covered-table-cell'):
                    continue
                crep = int(cell.get(T + 'number-columns-repeated', '1'))
                vt = cell.get(O + 'value-type')
                v = None
                if vt in ('float', 'percentage', 'currency'):
                    v = _num(float(cell.get(O + 'value')))
                elif vt == 'date':
                    s = cell.get(O + 'date-value') or ''
                    try:
                        v = dt.datetime.fromisoformat(s) if 'T' in s else dt.date.fromisoformat(s)
                    except ValueError:
                        v = s
                elif vt == 'time':
                    v = _duration(cell.get(O + 'time-value'))
                elif vt == 'boolean':
                    v = cell.get(O + 'boolean-value') == 'true'
                elif vt == 'string':
                    v = cell.get(O + 'string-value') or _odf_text(cell)
                vals.append((v, min(crep, 64 if v is None else 4)))
            if not any(v not in (None, '') for v, _ in vals):
                r += min(reps, 5)
                continue
            for _ in range(min(reps, 50)):
                r += 1
                c = 0
                for v, rep in vals:
                    for _ in range(rep):
                        c += 1
                        if v is not None:
                            sh.cells[(r, c)] = Cell(v)
                            cells_total += 1
                if cells_total > MAX_CELLS:
                    raise FormatError(MSG['big'])
        if sh.cells:
            sh.max_row = max(a for a, _ in sh.cells)
            sh.max_col = max(b for _, b in sh.cells)
        out.append(sh)
    if not out:
        raise FormatError(MSG['damaged'])
    return Workbook(out, False)


def read_odt(data):
    root = _odf_root(data)
    T, X = _ODS['t'], _ODS['x']
    body = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text')
    paragraphs, tables = [], []
    if body is None:
        raise FormatError(MSG['damaged'])
    for el in body:
        if el.tag in (X + 'p', X + 'h'):
            t = _odf_text(el)
            if t:
                paragraphs.append(t)
        elif el.tag == T + 'table':
            rows = []
            for tr in el.iter(T + 'table-row'):
                rows.append([_odf_text(tc) for tc in tr if tc.tag in (T + 'table-cell', T + 'covered-table-cell')])
            tables.append(rows)
    return {'paragraphs': paragraphs, 'tables': tables}


# --------------------------------------------------------------------------- RTF
def read_rtf(data):
    text = data.decode('latin-1')
    cp = 'cp1252'
    m = re.search(r'\\ansicpg(\d+)', text[:2000])
    if m:
        cp = 'cp' + m.group(1)
    SKIP = {'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'header', 'footer', 'footnote', 'object', 'themedata', 'datastore', 'latentstyles', 'listtable', 'listoverridetable', 'generator', 'xmlnstbl', 'rsidtbl'}
    stack, skip_depth, uc_skip = [], 0, 0
    cur, cell_texts, rows, tables, paragraphs = [], [], [], [], []
    in_table_row = False
    pending = bytearray()

    def flush_pending():
        if pending:
            cur.append(bytes(pending).decode(cp, 'ignore')); pending.clear()

    def end_cell():
        flush_pending()
        cell_texts.append(re.sub(r'\s+', ' ', ''.join(cur)).strip()); cur.clear()

    def end_row():
        nonlocal cell_texts
        rows.append(cell_texts); cell_texts = []

    def end_para():
        flush_pending()
        t = re.sub(r'[ \t]+', ' ', ''.join(cur)).strip()
        cur.clear()
        if t:
            paragraphs.append(t)

    i, n = 0, len(text)
    depth = 0
    while i < n:
        ch = text[i]
        if ch == '{':
            stack.append(skip_depth); depth += 1; i += 1
            if text.startswith('\\*', i):
                skip_depth = skip_depth or depth
            continue
        if ch == '}':
            if skip_depth and depth == skip_depth:
                skip_depth = 0
            depth -= 1
            if stack:
                stack.pop()
            i += 1
            continue
        if ch == '\\':
            m = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?").match(text, i)
            if m:
                w, arg = m.group(1), m.group(2)
                i = m.end()
                if w in SKIP and not skip_depth:
                    skip_depth = depth
                if skip_depth:
                    continue
                if w == 'par' or w == 'line':
                    if rows or cell_texts or in_table_row:
                        cur.append(' ')
                    else:
                        end_para()
                elif w == 'cell' or w == 'nestcell':
                    end_cell(); in_table_row = True
                elif w == 'row' or w == 'nestrow':
                    end_row(); in_table_row = False
                    if not text.startswith('\\trowd', i) and not re.match(r'\s*\\(trowd|intbl|pard\\intbl)', text[i:i + 30]):
                        tables.append(rows); rows = []
                elif w == 'tab':
                    cur.append(' ')
                elif w == 'u' and arg is not None:
                    flush_pending()
                    code = int(arg) & 0xFFFF
                    cur.append(chr(code)); uc_skip = 1
                elif w == 'uc' and arg:
                    pass
                continue
            if text.startswith("\\'", i) and i + 4 <= n:
                if not skip_depth:
                    if uc_skip:
                        uc_skip = 0
                    else:
                        try:
                            pending.append(int(text[i + 2:i + 4], 16))
                        except ValueError:
                            pass
                i += 4
                continue
            if i + 1 < n:
                c2 = text[i + 1]
                if not skip_depth:
                    if c2 in '\\{}':
                        flush_pending(); cur.append(c2)
                    elif c2 == '~':
                        cur.append(' ')
                i += 2
                continue
        if ch in '\r\n':
            i += 1
            continue
        if not skip_depth:
            if uc_skip:
                uc_skip = 0
            else:
                flush_pending(); cur.append(ch)
        i += 1
    end_para()
    if rows or cell_texts:
        if cell_texts:
            end_row()
        tables.append(rows)
    if not paragraphs and not tables:
        raise FormatError(MSG['damaged'])
    return {'paragraphs': paragraphs, 'tables': [t for t in tables if t]}


# --------------------------------------------------------------------------- HTML tables (web pages saved as .xls / .doc)
class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.paras, self.cur, self.in_cell = [], [], [], [], False
        self.cell = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.stack.append([])
        elif tag == 'tr' and self.stack:
            self.stack[-1].append([])
        elif tag in ('td', 'th') and self.stack:
            if not self.stack[-1]:
                self.stack[-1].append([])
            self.in_cell, self.cell = True, []
        elif tag in ('br',) and self.in_cell:
            self.cell.append(' ')

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.stack and self.in_cell:
            self.stack[-1][-1].append(re.sub(r'\s+', ' ', ''.join(self.cell)).strip()); self.in_cell = False
        elif tag == 'table' and self.stack:
            t = self.stack.pop()
            if not self.stack:
                self.tables.append([r for r in t if r])
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'li') and not self.in_cell and not self.stack:
            s = re.sub(r'\s+', ' ', ''.join(self.cur)).strip()
            if s:
                self.paras.append(s)
            self.cur = []

    def handle_data(self, d):
        if self.in_cell:
            self.cell.append(d)
        elif not self.stack:
            self.cur.append(d)


def _decode_text(data):
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode('utf-8', 'replace')
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode('utf-16', 'replace')
    m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', data[:3000])
    for enc in ([m.group(1).decode()] if m else []) + ['utf-8', 'cp1256', 'cp1252']:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode('latin-1')


def read_html(data):
    p = _Tables()
    p.feed(_decode_text(data))
    return {'paragraphs': p.paras, 'tables': p.tables}


def _grid_workbook(tables_or_rows, names):
    out = []
    for nm, rows in zip(names, tables_or_rows):
        sh = Sheet(nm)
        for r, row in enumerate(rows, 1):
            for c, v in enumerate(row, 1):
                if v not in (None, ''):
                    sh.cells[(r, c)] = Cell(v)
        if sh.cells:
            sh.max_row = max(a for a, _ in sh.cells)
            sh.max_col = max(b for _, b in sh.cells)
        out.append(sh)
    if not any(s.cells for s in out):
        raise FormatError('No table with data was found in this file.')
    return Workbook(out, False)


def read_html_sheets(data):
    d = read_html(data)
    return _grid_workbook(d['tables'], [f'Table {i}' for i in range(1, len(d['tables']) + 1)])


# --------------------------------------------------------------------------- CSV / text
def read_csv(data, name=''):
    text = _decode_text(data)
    sample = '\n'.join(text.splitlines()[:30])
    delim = ','
    counts = {d: sample.count(d) for d in (',', ';', '\t', '|')}
    if max(counts.values()) > 0:
        delim = max(counts, key=counts.get)
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    except csv.Error:
        raise FormatError(MSG['damaged'])
    if len(rows) > MAX_CELLS:
        raise FormatError(MSG['big'])
    stem = re.sub(r'\.[^.]+$', '', name.rsplit('/', 1)[-1]) or 'Sheet'
    return _grid_workbook([rows], [stem[:31]])


# --------------------------------------------------------------------------- SpreadsheetML 2003 (XML)
def read_xml2003(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise FormatError(MSG['damaged'])
    S = '{urn:schemas-microsoft-com:office:spreadsheet}'
    out = []
    for ws in root.iter(S + 'Worksheet'):
        sh = Sheet(ws.get(S + 'Name') or 'Sheet')
        r = 0
        for row in ws.iter(S + 'Row'):
            r = int(row.get(S + 'Index')) if row.get(S + 'Index') else r + 1
            c = 0
            for cell in row.findall(S + 'Cell'):
                c = int(cell.get(S + 'Index')) if cell.get(S + 'Index') else c + 1
                d = cell.find(S + 'Data')
                if d is None or d.text is None and len(d) == 0:
                    continue
                typ, txt = d.get(S + 'Type'), ''.join(d.itertext())
                try:
                    v = _num(float(txt)) if typ == 'Number' else (dt.datetime.fromisoformat(txt) if typ == 'DateTime' else txt)
                except ValueError:
                    v = txt
                sh.cells[(r, c)] = Cell(v)
        if sh.cells:
            sh.max_row = max(a for a, _ in sh.cells)
            sh.max_col = max(b for _, b in sh.cells)
        out.append(sh)
    if not out:
        raise FormatError(MSG['damaged'])
    return Workbook(out, False)


# --------------------------------------------------------------------------- the two doors
COM_KINDS = {'drm', 'xlsb', 'old', 'encrypted'}      # files no built-in reader can open; Microsoft Office may, on a PC that is allowed to


def door(data, name='', engine='auto'):
    """'sheet' or 'word': which reader a file goes to."""
    kind = sniff(data, name)
    if kind in WORD_KINDS:
        return 'word'
    if kind in SHEET_KINDS:
        return 'sheet'
    return 'word' if com_office.kind_of_name(name) == 'word' else 'sheet'


def office_state():
    return {'excel': com_office.available('excel'), 'word': com_office.available('word')}


def _use_office(kind, name, engine, want):
    """Should this file be read through Microsoft Office? want: 'sheet' or 'word'."""
    if engine == 'native':
        return False
    pref = com_office.kind_of_name(name)
    if engine == 'office':
        return True
    return kind in COM_KINDS or (kind == 'unknown' and pref == want)


def _via_office(app, data, name, engine='auto'):
    if not com_office.available(app):
        if engine == 'office':
            raise FormatError('Microsoft ' + ('Excel' if app == 'excel' else 'Word') + ' is not available on this PC (it needs Windows with Office installed).')
        raise FormatError(MSG.get(sniff(data, name)) or MSG['unknown'])
    try:
        return (com_office.read_workbook if app == 'excel' else com_office.read_document)(data, name, OFFICE_TMP)
    except com_office.OfficeError as e:
        raise FormatError(str(e))


def read_workbook(data, name='', engine='auto'):
    """engine: 'auto' (built-in readers; Microsoft Office for files they cannot open), 'office' (always Microsoft Excel), 'native' (never Office)."""
    kind = sniff(data, name)
    if kind in WORD_KINDS or (kind not in SHEET_KINDS and com_office.kind_of_name(name) == 'word'):
        raise FormatError('This is a Word document, not a spreadsheet.')
    if _use_office(kind, name, engine, 'sheet'):
        return _via_office('excel', data, name, engine)
    need_sheet(kind)
    try:
        if kind == 'xlsx':
            return xlsx_read.read(data)
        if kind == 'xls':
            return read_xls(data)
        if kind == 'ods':
            return read_ods(data)
        if kind == 'csv':
            return read_csv(data, name)
        if kind == 'htmlsheet':
            return read_html_sheets(data)
        return read_xml2003(data)
    except xlsx_read.XlsxError as e:
        raise FormatError(str(e))


def read_document(data, name='', engine='auto'):
    kind = sniff(data, name)
    if kind in SHEET_KINDS or (kind not in WORD_KINDS and com_office.kind_of_name(name) == 'sheet'):
        raise FormatError('This is a spreadsheet, not a Word document.')
    if _use_office(kind, name, engine, 'word'):
        return _via_office('word', data, name, engine)
    need_document(kind)
    try:
        if kind == 'docx':
            return docx_read.read(data)
        if kind == 'doc':
            return read_doc_binary(data)
        if kind == 'odt':
            return read_odt(data)
        if kind == 'rtf':
            return read_rtf(data)
        return read_html(data)
    except docx_read.DocxError as e:
        raise FormatError(str(e))
