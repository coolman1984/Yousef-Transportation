"""Dependency-free .xlsx writer with what the trip workbook needs: formulas with cached values, dates and times,
number formats, cell styles, Excel Tables (with calculated columns), frozen panes, column widths, merged cells,
hidden gridlines and right-to-left sheets. Strings go through a shared-strings table like Excel does.

    wb = [Sheet('All Car', rows, widths=[...], tables=[Table(...)], freeze=(1, 0))]
    data = build(wb)
"""
import datetime as dt
import io
import re
import zipfile
from xml.sax.saxutils import escape

_BAD_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')
_BAD_SHEET = re.compile(r'[\[\]:*?/\\]')

# style name -> index in cellXfs (see _styles_xml)
STYLE = {'default': 0, 'header': 1, 'date': 2, 'time': 3, 'datetime': 4, 'duration': 5, 'int': 6, 'dec': 7, 'bold': 8,
         'total_int': 9, 'total_dur': 10, 'total_text': 11, 'title': 12, 'wrap': 13, 'pct': 14, 'ok': 15, 'warn': 16, 'bad': 17,
         'note': 18, 'head_left': 19, 'total_dec': 20}


class Formula:
    """A formula (without the leading =) and the value to show before Excel recalculates."""

    def __init__(self, f, cached=None):
        self.f, self.cached = f, cached


class S:
    """A value with an explicit style name."""

    def __init__(self, value, style):
        self.value, self.style = value, style


class Table:
    def __init__(self, name, ref, columns, style='TableStyleMedium2', formulas=None):
        """ref like 'A1:P233' (header + data rows); formulas: {column name: calculated column formula}."""
        self.name, self.ref, self.columns, self.style, self.formulas = name, ref, columns, style, formulas or {}


class Sheet:
    def __init__(self, name, rows, widths=None, tables=None, freeze=(0, 0), grid=True, rtl=False, autofilter=None, merges=None, landscape=False):
        self.name, self.rows, self.widths = name, rows, widths or []
        self.tables, self.freeze, self.grid, self.rtl = tables or [], freeze, grid, rtl
        self.autofilter, self.merges, self.landscape = autofilter, merges or [], landscape


def col_letters(n):
    """1 -> A."""
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def serial_date(d):
    return (dt.date(d.year, d.month, d.day) - dt.date(1899, 12, 30)).days


def serial_datetime(x):
    return serial_date(x) + (x.hour * 3600 + x.minute * 60 + x.second) / 86400


def serial_time(t):
    return (t.hour * 3600 + t.minute * 60 + t.second) / 86400


class _Strings:
    def __init__(self):
        self.index, self.items = {}, []

    def add(self, s):
        s = _BAD_XML.sub('', s)[:32000]
        if s not in self.index:
            self.index[s] = len(self.items)
            self.items.append(s)
        return self.index[s]


def _num(v):
    return repr(v) if isinstance(v, float) else str(v)


def _cell(ref, v, strings):
    style = None
    if isinstance(v, S):
        v, style = v.value, STYLE[v.style]
    f = None
    if isinstance(v, Formula):
        f, v = v.f, v.cached
    if style is None:
        style = {dt.datetime: STYLE['datetime'], dt.date: STYLE['date'], dt.time: STYLE['time'], dt.timedelta: STYLE['duration']}.get(type(v), 0)
    s = f' s="{style}"' if style else ''
    fx = f'<f>{escape(f)}</f>' if f is not None else ''
    if v is None or v == '':
        return f'<c r="{ref}"{s}>{fx}</c>' if (style or fx) else ''
    if isinstance(v, bool):
        return f'<c r="{ref}"{s} t="b">{fx}<v>{int(v)}</v></c>'
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{s}>{fx}<v>{_num(v)}</v></c>'
    if isinstance(v, dt.datetime):
        return f'<c r="{ref}"{s}>{fx}<v>{_num(serial_datetime(v))}</v></c>'
    if isinstance(v, dt.date):
        return f'<c r="{ref}"{s}>{fx}<v>{serial_date(v)}</v></c>'
    if isinstance(v, dt.time):
        return f'<c r="{ref}"{s}>{fx}<v>{_num(serial_time(v))}</v></c>'
    if isinstance(v, dt.timedelta):
        return f'<c r="{ref}"{s}>{fx}<v>{_num(v.total_seconds() / 86400)}</v></c>'
    if f is not None:   # a formula whose result is text
        return f'<c r="{ref}"{s} t="str">{fx}<v>{escape(_BAD_XML.sub("", str(v)))}</v></c>'
    return f'<c r="{ref}"{s} t="s"><v>{strings.add(str(v))}</v></c>'


def _sheet_xml(sh, strings, table_rids):
    out = []
    maxc = 0
    for n, row in enumerate(sh.rows, start=1):
        cells = ''.join(_cell(f'{col_letters(i)}{n}', v, strings) for i, v in enumerate(row, start=1))
        maxc = max(maxc, len(row))
        out.append(f'<row r="{n}">{cells}</row>' if cells else f'<row r="{n}"/>')
    cols = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(sh.widths, start=1))
    fc, fr = sh.freeze
    pane = ''
    if fc or fr:
        tl = f'{col_letters(fc + 1)}{fr + 1}'
        active = 'bottomRight' if fc and fr else 'topRight' if fc else 'bottomLeft'
        pane = (f'<pane{f" xSplit={chr(34)}{fc}{chr(34)}" if fc else ""}{f" ySplit={chr(34)}{fr}{chr(34)}" if fr else ""} '
                f'topLeftCell="{tl}" activePane="{active}" state="frozen"/>')
    view = (f'<sheetViews><sheetView workbookViewId="0"{"" if sh.grid else " showGridLines=" + chr(34) + "0" + chr(34)}'
            f'{" rightToLeft=" + chr(34) + "1" + chr(34) if sh.rtl else ""}>{pane}</sheetView></sheetViews>')
    dim = f'A1:{col_letters(max(1, maxc))}{max(1, len(sh.rows))}'
    x = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
         '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>' if sh.landscape else '', f'<dimension ref="{dim}"/>', view,
         '<sheetFormatPr defaultRowHeight="15"/>', f'<cols>{cols}</cols>' if cols else '', f'<sheetData>{"".join(out)}</sheetData>']
    if sh.autofilter and not sh.tables:
        x.append(f'<autoFilter ref="{sh.autofilter}"/>')
    if sh.merges:
        x.append(f'<mergeCells count="{len(sh.merges)}">' + ''.join(f'<mergeCell ref="{m}"/>' for m in sh.merges) + '</mergeCells>')
    x.append('<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>')
    if sh.landscape:
        x.append('<pageSetup orientation="landscape" fitToHeight="0"/>')
    if table_rids:
        x.append(f'<tableParts count="{len(table_rids)}">' + ''.join(f'<tablePart r:id="{r}"/>' for r in table_rids) + '</tableParts>')
    x.append('</worksheet>')
    return ''.join(x)


def _table_xml(t, tid):
    cols = []
    for i, name in enumerate(t.columns, start=1):
        f = t.formulas.get(name)
        inner = f'<calculatedColumnFormula>{escape(f)}</calculatedColumnFormula>' if f else ''
        cols.append(f'<tableColumn id="{i}" name="{escape(name, {chr(34): "&quot;"})}">{inner}</tableColumn>' if inner else
                    f'<tableColumn id="{i}" name="{escape(name, {chr(34): "&quot;"})}"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="{tid}" name="{t.name}" displayName="{t.name}" ref="{t.ref}" totalsRowShown="0">'
            f'<autoFilter ref="{t.ref}"/><tableColumns count="{len(t.columns)}">{"".join(cols)}</tableColumns>'
            f'<tableStyleInfo name="{t.style}" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>')


def _styles_xml():
    def font(b=False, i=False, sz=11, color=None):
        return f'<font>{"<b/>" if b else ""}{"<i/>" if i else ""}<sz val="{sz}"/>{f"<color rgb={chr(34)}{color}{chr(34)}/>" if color else ""}<name val="Calibri"/></font>'
    fonts = [font(), font(b=True, color='FFFFFFFF'), font(b=True), font(b=True, sz=14), font(i=True, color='FF666666')]

    def fill(rgb):
        return f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/><bgColor indexed="64"/></patternFill></fill>'
    fills = ['<fill><patternFill patternType="none"/></fill>', '<fill><patternFill patternType="gray125"/></fill>', fill('FF13294B'),
             fill('FFC6EFCE'), fill('FFFFEB9C'), fill('FFFFC7CE'), fill('FFF2F2F2')]
    borders = ['<border><left/><right/><top/><bottom/><diagonal/></border>',
               '<border><left style="thin"><color rgb="FFBBBBBB"/></left><right style="thin"><color rgb="FFBBBBBB"/></right><top style="thin"><color rgb="FFBBBBBB"/></top><bottom style="thin"><color rgb="FFBBBBBB"/></bottom><diagonal/></border>',
               '<border><left/><right/><top style="thin"><color auto="1"/></top><bottom/><diagonal/></border>']

    def xf(num=0, font=0, fill=0, border=0, align=None):
        a = f'<alignment {align}/>' if align else ''
        attrs = f'numFmtId="{num}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"'
        flags = (' applyNumberFormat="1"' if num else '') + (' applyFont="1"' if font else '') + (' applyFill="1"' if fill else '') + (' applyBorder="1"' if border else '') + (' applyAlignment="1"' if align else '')
        return f'<xf {attrs}{flags}>{a}</xf>' if a else f'<xf {attrs}{flags}/>'
    xfs = [xf(), xf(0, 1, 2, 1, 'horizontal="center" vertical="center" wrapText="1"'), xf(14), xf(20), xf(22), xf(164), xf(3), xf(4), xf(0, 2),
           xf(3, 2, 0, 2), xf(164, 2, 0, 2), xf(0, 2, 0, 2), xf(0, 3), xf(0, 0, 0, 0, 'wrapText="1" vertical="top"'), xf(9), xf(0, 0, 3), xf(0, 0, 4), xf(0, 0, 5),
           xf(0, 4), xf(0, 2, 6, 1, 'horizontal="center" vertical="center" wrapText="1"'), xf(4, 2, 0, 2)]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="[h]:mm"/></numFmts>'
            f'<fonts count="{len(fonts)}">{"".join(fonts)}</fonts><fills count="{len(fills)}">{"".join(fills)}</fills><borders count="{len(borders)}">{"".join(borders)}</borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def build(sheets):
    """list of Sheet -> .xlsx bytes."""
    names, used = [], set()
    for sh in sheets:
        base = _BAD_SHEET.sub(' ', str(sh.name)).strip()[:31] or 'Sheet'
        n, k = base, 2
        while n.lower() in used:
            n = f'{base[:28]} {k}'
            k += 1
        used.add(n.lower())
        names.append(n)
    strings = _Strings()
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
          '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>']
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        table_id = 0
        for i, sh in enumerate(sheets, start=1):
            rids = []
            if sh.tables:
                rels = []
                for k, t in enumerate(sh.tables, start=1):
                    table_id += 1
                    rids.append(f'rId{k}')
                    rels.append(f'<Relationship Id="rId{k}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table{table_id}.xml"/>')
                    z.writestr(f'xl/tables/table{table_id}.xml', _table_xml(t, table_id))
                    ct.append(f'<Override PartName="/xl/tables/table{table_id}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>')
                z.writestr(f'xl/worksheets/_rels/sheet{i}.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(rels) + '</Relationships>')
            z.writestr(f'xl/worksheets/sheet{i}.xml', _sheet_xml(sh, strings, rids))
            ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        z.writestr('[Content_Types].xml', ''.join(ct) + '</Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, start=1))
                   + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   f'<Relationship Id="rId{len(sheets) + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
        z.writestr('xl/styles.xml', _styles_xml())
        z.writestr('xl/sharedStrings.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings.items)}" uniqueCount="{len(strings.items)}">'
                   + ''.join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings.items) + '</sst>')
    return buf.getvalue()
