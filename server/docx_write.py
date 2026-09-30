"""Dependency-free .docx writer: headings, paragraphs with runs, tables (also right-to-left), page breaks, header/footer text.
Enough for the trip order form and the monthly report; Word, LibreOffice and Google Docs open the files."""
import io
import re
import zipfile
from xml.sax.saxutils import escape

_BAD_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')
CM = 567   # twips per centimetre


class Run:
    def __init__(self, text, bold=False, size=None, color=None, italic=False):
        self.text, self.bold, self.size, self.color, self.italic = text, bold, size, color, italic


def _t(text):
    return escape(_BAD_XML.sub('', str(text)))


def _run(r, rtl, font):
    if isinstance(r, str):
        r = Run(r)
    props = f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if r.bold:
        props += '<w:b/><w:bCs/>'
    if r.italic:
        props += '<w:i/><w:iCs/>'
    if r.color:
        props += f'<w:color w:val="{r.color}"/>'
    if r.size:
        props += f'<w:sz w:val="{int(r.size * 2)}"/><w:szCs w:val="{int(r.size * 2)}"/>'
    if rtl:
        props += '<w:rtl/>'
    parts = _BAD_XML.sub('', str(r.text)).split('\n')
    body = '<w:br/>'.join(f'<w:t xml:space="preserve">{escape(p)}</w:t>' for p in parts)
    return f'<w:r><w:rPr>{props}</w:rPr>{body}</w:r>'


class Doc:
    def __init__(self, rtl=False, font='Arial', landscape=False, footer=''):
        self.rtl, self.font, self.landscape, self.footer = rtl, font, landscape, footer
        self.body = []

    # ---- paragraphs
    def para(self, content='', bold=False, size=None, align=None, color=None, after=6, before=0, italic=False, keep_next=False):
        runs = content if isinstance(content, list) else [Run(content, bold, size, color, italic)]
        ppr = ''
        if keep_next:
            ppr += '<w:keepNext/>'
        if self.rtl:
            ppr += '<w:bidi/>'
        ppr += f'<w:spacing w:before="{int(before * 20)}" w:after="{int(after * 20)}"/>'
        if align:
            ppr += f'<w:jc w:val="{align}"/>'
        self.body.append(f'<w:p><w:pPr>{ppr}</w:pPr>{"".join(_run(r, self.rtl, self.font) for r in runs)}</w:p>')

    def heading(self, text, level=1):
        size = {1: 20, 2: 15, 3: 12}.get(level, 12)
        self.para(text, bold=True, size=size, color='13294B', after=8, before=10 if level > 1 else 0, keep_next=True)

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ---- tables
    def table(self, rows, widths=None, header=False, borders=True, shade=None, align=None, size=None, merges=None):
        """rows: list of lists of cell contents (str, Run, or list of runs). widths in cm. shade: {(row, col): 'RRGGBB'}. merges: {(row, col): span}."""
        ncols = max(len(r) for r in rows)
        widths = widths or [17.0 / ncols] * ncols
        shade, merges = shade or {}, merges or {}
        b = ('<w:tblBorders>' + ''.join(f'<w:{e} w:val="single" w:sz="6" w:space="0" w:color="999999"/>' for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>') if borders else ''
        x = [f'<w:tbl><w:tblPr><w:tblW w:w="{int(sum(widths) * CM)}" w:type="dxa"/>{"<w:bidiVisual/>" if self.rtl else ""}{b}<w:tblLayout w:type="fixed"/>'
             '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>',
             '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{int(wd * CM)}"/>' for wd in widths) + '</w:tblGrid>']
        for ri, row in enumerate(rows):
            trpr = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if header and ri == 0 else '<w:trPr><w:cantSplit/></w:trPr>'
            cells, ci = [], 0
            for cell in row:
                span = merges.get((ri, ci), 1)
                wd = sum(widths[ci:ci + span])
                tcpr = f'<w:tcW w:w="{int(wd * CM)}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else '')
                fill = 'E4EAF4' if header and ri == 0 and (ri, ci) not in shade else shade.get((ri, ci))
                if fill:
                    tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
                tcpr += '<w:vAlign w:val="center"/>'
                runs = cell if isinstance(cell, list) else [cell if isinstance(cell, Run) else Run('' if cell is None else cell, bold=(header and ri == 0), size=size)]
                if isinstance(cell, Run) is False and not isinstance(cell, list) and header and ri == 0:
                    runs = [Run(cell, bold=True, size=size)]
                ppr = ('<w:bidi/>' if self.rtl else '') + '<w:spacing w:before="0" w:after="0"/>' + (f'<w:jc w:val="{align}"/>' if align else '')
                cells.append(f'<w:tc><w:tcPr>{tcpr}</w:tcPr><w:p><w:pPr>{ppr}</w:pPr>{"".join(_run(r, self.rtl, self.font) for r in runs)}</w:p></w:tc>')
                ci += span
            while ci < ncols:
                cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{int(widths[ci] * CM)}" w:type="dxa"/></w:tcPr><w:p/></w:tc>')
                ci += 1
            x.append(f'<w:tr>{trpr}{"".join(cells)}</w:tr>')
        x.append('</w:tbl>')
        self.body.append(''.join(x))
        self.body.append('<w:p><w:pPr><w:spacing w:after="80"/></w:pPr></w:p>')

    # ---- file
    def bytes(self):
        w, h = (16838, 11906) if self.landscape else (11906, 16838)
        orient = ' w:orient="landscape"' if self.landscape else ''
        footer_ref = '<w:footerReference w:type="default" r:id="rId2"/>' if self.footer else ''
        sect = (f'<w:sectPr>{footer_ref}<w:pgSz w:w="{w}" w:h="{h}"{orient}/><w:pgMar w:top="{int(1.5 * CM)}" w:right="{int(1.6 * CM)}" w:bottom="{int(1.5 * CM)}" '
                f'w:left="{int(1.6 * CM)}" w:header="720" w:footer="600" w:gutter="0"/>{"<w:bidi/>" if self.rtl else ""}</w:sectPr>')
        doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>' + ''.join(self.body) + sect + '</w:body></w:document>')
        styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                  f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{self.font}" w:hAnsi="{self.font}" w:cs="{self.font}"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US" w:bidi="ar-EG"/></w:rPr></w:rPrDefault></w:docDefaults>'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                       '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                       '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                       + ('<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>' if self.footer else '') + '</Types>')
            z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr('word/_rels/document.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                       + ('<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>' if self.footer else '') + '</Relationships>')
            z.writestr('word/document.xml', doc)
            z.writestr('word/styles.xml', styles)
            if self.footer:
                fp = ('<w:bidi/>' if self.rtl else '') + '<w:jc w:val="center"/>'
                z.writestr('word/footer1.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                           f'<w:p><w:pPr>{fp}</w:pPr>{_run(Run(self.footer, size=8, color="666666"), self.rtl, self.font)}</w:p></w:ftr>')
        return buf.getvalue()
