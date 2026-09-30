"""Dependency-free .docx reader: the text of the paragraphs and of the tables (row by row, cell by cell)."""
import io
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MAX_UNCOMPRESSED = 40 * 1024 * 1024


class DocxError(Exception):
    """The file is not a readable Word document; the message is meant for the person who chose it."""


def _text(el):
    out = []
    for node in el.iter():
        if node.tag == W + 't':
            out.append(node.text or '')
        elif node.tag in (W + 'tab',):
            out.append(' ')
        elif node.tag in (W + 'br', W + 'cr'):
            out.append('\n')
        elif node.tag == W + 'sym':
            out.append('☑' if node.get(W + 'char', '').upper() in ('F0FE', 'F052') else '')
    return ''.join(out)


def _para_text(p):
    return _text(p).strip()


def read(data):
    """bytes -> {'paragraphs': [str], 'tables': [[[cell text]]]} (tables in document order, rows of cells)."""
    if not data or len(data) < 100:
        raise DocxError('The file is empty.')
    if data[:2] != b'PK':
        raise DocxError('This is not a Word (.docx) file. Old .doc files must be saved again as .docx.')
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocxError('The file is damaged and cannot be opened.')
    if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
        raise DocxError('The document is too large to import safely.')
    if 'word/document.xml' not in z.namelist():
        raise DocxError('This does not look like a Word document.')
    try:
        root = ET.fromstring(z.read('word/document.xml'))
    except ET.ParseError:
        raise DocxError('The document is damaged (its text cannot be read).')
    body = root.find(W + 'body')
    paragraphs, tables = [], []
    for el in body:
        if el.tag == W + 'p':
            t = _para_text(el)
            if t:
                paragraphs.append(t)
        elif el.tag == W + 'tbl':
            tables.append(_table(el))
    return {'paragraphs': paragraphs, 'tables': tables}


def _table(tbl):
    rows = []
    for tr in tbl.findall(W + 'tr'):
        cells = []
        for tc in tr.findall(W + 'tc'):
            cells.append(re.sub(r'[ \t]+', ' ', '\n'.join(_para_text(p) for p in tc.findall(W + 'p'))).strip())
        rows.append(cells)
    return rows
