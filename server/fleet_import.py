"""Bulk import of vehicles and drivers from an Excel or CSV sheet.

The office program already imports trip workbooks. This is the list import: one row per vehicle
(matched by the normalised plate) or one row per driver (matched by the normalised name). The file
is read with the built-in readers (server/formats.py, server/xlsx_read.py) — no Excel install and
no extra package — so the same code runs in the packaged Windows program, offline.

A preview changes nothing. Confirming builds every row and saves them in one commit; a failure
saves none of them. The training copy is a separate program with its own data folder, so an import
there stays in training.
"""
import datetime as dt
import os
import re
import threading
import time
import uuid

import domain
import formats
import xlsx_read
import xlsx_write as w

PERM = {'vehicles': 'vehicles.manage', 'drivers': 'drivers.manage'}
MAX_ROWS = 5000
_PREVIEW_TTL = 30 * 60
_MAX_PREVIEWS = 24
_HEADER_SCAN = 30
_LOCK = threading.Lock()
_PREVIEWS = {}

# Template headers are the words on the screen, in the same order as the form.
VEHICLE_HEADERS = ['اللوحة', 'النوع', 'الفئة', 'الملكية', 'الشركة', 'العداد وقت الإضافة', 'ملاحظات', 'نشط']
DRIVER_HEADERS = ['الاسم', 'الموبايل', 'الشركة', 'رقم الرخصة', 'انتهاء الرخصة', 'نشط']
_FIELDS = {
    'vehicles': ('plate', 'type', 'categoryId', 'ownership', 'vendor', 'active', 'startKm', 'notes'),
    'drivers': ('name', 'mobile', 'vendor', 'licenseNo', 'licenseExpiry', 'active'),
}
_LIMITS = {'plate': 40, 'type': 80, 'vendor': 120, 'notes': 500, 'name': 120, 'licenseNo': 40, 'category': 120}
_YES = ('نعم', 'نشط', 'نشطة', 'yes', 'y', 'true', '1')
_NO = ('لا', 'لأ', 'غير نشط', 'غير نشطة', 'no', 'n', 'false', '0')
_OWN = ('ملك', 'ملكية', 'ملك الشركة', 'خاصة', 'own', 'owned', 'company')
_RENT = ('إيجار', 'ايجار', 'مؤجر', 'مؤجرة', 'تأجير', 'rent', 'rented')


class FleetError(Exception):
    """A file the person can fix. `code` is the translation key (err.flt.*) or a formats.py code (empty, unknown, …)."""

    def __init__(self, msg, code):
        super().__init__(msg)
        self.code = code


def _alias_key(text):
    return domain.key_text(text).replace(' ', '')


def _aliases(pairs):
    """Header text -> field. The same words may be listed twice; two fields may not share a word."""
    out = {}
    for field, names in pairs:
        for name in names:
            key = _alias_key(name)
            if not key:
                continue
            other = out.get(key)
            if other and other != field:
                raise RuntimeError(f'header {name!r} is both {other} and {field}')
            out[key] = field
    return out


_VEHICLE_ALIASES = _aliases([
    ('plate', ['اللوحة', 'رقم اللوحة', 'رقم السيارة', 'رقم العربية', 'لوحة السيارة', 'Car Plate', 'Plate', 'Plate Number', 'plate']),
    ('type', ['النوع', 'نوع السيارة', 'الماركة', 'Type', 'type']),
    ('category', ['الفئة', 'التصنيف', 'Category', 'category']),
    ('ownership', ['الملكية', 'Ownership', 'ownership']),
    ('vendor', ['الشركة', 'الشركة المؤجرة', 'Vendor', 'vendor']),
    ('startKm', ['العداد وقت الإضافة', 'عداد البداية', 'العداد', 'Baseline Odometer', 'Start KM', 'Start km', 'Odometer']),
    ('notes', ['ملاحظات', 'Notes', 'notes']),
    ('active', ['نشط', 'نشطة', 'الحالة', 'Active', 'active']),
])
_DRIVER_ALIASES = _aliases([
    ('name', ['الاسم', 'اسم السائق', 'السائق', 'Driver Name', 'Name', 'name']),
    ('mobile', ['الموبايل', 'رقم الموبايل', 'الهاتف', 'التليفون', 'الجوال', 'Mobile', 'Phone', 'mobile']),
    ('vendor', ['الشركة', 'الشركة المؤجرة', 'Vendor', 'vendor']),
    ('licenseNo', ['رقم الرخصة', 'الرخصة', 'License No', 'License', 'licenseNo']),
    ('licenseExpiry', ['انتهاء الرخصة', 'تاريخ انتهاء الرخصة', 'تاريخ الرخصة', 'License Expiry', 'licenseExpiry']),
    ('active', ['نشط', 'نشطة', 'الحالة', 'Active', 'active']),
])
_ALIAS = {'vehicles': _VEHICLE_ALIASES, 'drivers': _DRIVER_ALIASES}
_REQUIRED = {'vehicles': 'plate', 'drivers': 'name'}
_TEXT_FIELDS = {'type': 'type', 'vendor': 'vendor', 'notes': 'notes', 'licenseNo': 'licenseNo'}


def kind_or_raise(kind):
    if kind not in PERM:
        raise FleetError('Choose vehicles or drivers.', 'err.flt.kind')
    return kind


def clean_name(name):
    name = os.path.basename(str(name or '')).replace('\x00', '')
    name = re.sub(r'[\r\n\t]+', ' ', name).strip()
    return name[:80]


def _western(text):
    return domain.norm_text(text).translate(domain._AR_DIGITS)


def _as_text(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return domain.norm_text(str(value))


def _blank_cell(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not domain.norm_text(value)
    return False


def _choice(text, yes, no):
    key = domain.key_text(text)
    if not key:
        return None
    yes_keys = {domain.key_text(x) for x in yes}
    no_keys = {domain.key_text(x) for x in no}
    if key in yes_keys:
        return True
    if key in no_keys:
        return False
    return 'bad'


def _parse_km(value):
    if isinstance(value, bool) or isinstance(value, (dt.date, dt.datetime)):
        raise ValueError
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not value.is_integer():
            raise ValueError
        number = int(value)
    else:
        text = _western(_as_text(value))
        text = text.replace(',', '').replace(' ', '').replace('\u066c', '').replace('\u00a0', '')
        if text.endswith('.0'):
            text = text[:-2]
        if not re.fullmatch(r'\d+', text or ''):
            raise ValueError
        number = int(text)
    if number < 0 or number > 10_000_000:
        raise ValueError
    return number


def _parse_date(value):
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        found = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not 20000 <= number <= 80000:
            raise ValueError
        found = xlsx_read.excel_date(number).date()
    else:
        text = _western(_as_text(value))
        found = None
        iso = re.fullmatch(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
        dmy = re.fullmatch(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', text)
        ymd = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', text)
        try:
            if iso:
                found = dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            elif dmy:
                found = dt.date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
            elif ymd:
                found = dt.date(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)))
        except ValueError:
            found = None
        if found is None:
            raise ValueError
    if found.year < 2020 or found.year > 2100:
        return None, 'expiry'
    return found.isoformat(), None


def _parse_mobile(text):
    raw = domain.norm_text(text)
    if not raw:
        return None
    parts = [p.strip() for p in re.split(r'\s*[/،,;]\s*', raw) if p.strip()]
    out = []
    for part in parts:
        shown, ok = domain.norm_mobile_eg(part)
        if not ok:
            raise ValueError
        out.append(shown)
    return ' / '.join(out)


def _clip(text, limit):
    return domain.norm_text(text)[:limit]


def _match_category(state, text):
    key = domain.key_text(text)
    if not key:
        return None
    for cat in state.get('tripCategories') or []:
        if domain.key_text(cat.get('name') or '') == key or domain.key_text(cat.get('nameAr') or '') == key:
            return cat.get('id')
    return False


def _index(state, kind):
    out = {}
    if kind == 'vehicles':
        for row in state.get('vehicles') or []:
            key = row.get('plateKey') or domain.norm_plate(row.get('plate') or '')[1]
            if key and key not in out:
                out[key] = row
    else:
        for row in state.get('drivers') or []:
            key = row.get('nameKey') or domain.key_text(row.get('name') or '')
            if key and key not in out:
                out[key] = row
    return out


def _msg(code, **vars):
    clean = {}
    for key, value in vars.items():
        if isinstance(value, str):
            clean[key] = value[:80]
        elif isinstance(value, int):
            clean[key] = value
    return {'code': code, 'vars': clean}


def _parse_row(kind, cells, columns, state):
    """One data row -> (key, label, values, messages). values holds only fields the sheet set."""
    messages, values = [], {}

    def cell(field):
        index = columns.get(field)
        if index is None or index >= len(cells):
            return None
        return cells[index]

    if kind == 'vehicles':
        raw = cell('plate')
        plate_text = _as_text(raw)
        if not domain.norm_text(plate_text):
            messages.append(_msg('plate_required'))
            key, label = '', ''
        elif len(domain.norm_text(plate_text)) > _LIMITS['plate']:
            messages.append(_msg('too_long', field='plate'))
            key, label = '', ''
        else:
            label, key = domain.norm_plate(plate_text)
            if not key:
                messages.append(_msg('plate'))
    else:
        raw = cell('name')
        name = domain.norm_text(_as_text(raw))
        if not name:
            messages.append(_msg('name_required'))
            key, label = '', ''
        elif len(name) > _LIMITS['name']:
            messages.append(_msg('too_long', field='name'))
            key, label = '', ''
        else:
            label, key = name, domain.key_text(name)

    for field, limit_field in _TEXT_FIELDS.items():
        if field not in columns:
            continue
        raw = cell(field)
        if _blank_cell(raw):
            continue
        text = _western(_as_text(raw)) if field == 'licenseNo' else domain.norm_text(_as_text(raw))
        if not text:
            continue
        if len(text) > _LIMITS[limit_field]:
            messages.append(_msg('too_long', field=limit_field))
        else:
            values[field] = text

    if kind == 'vehicles' and 'category' in columns and not _blank_cell(cell('category')):
        raw_cat = _as_text(cell('category'))
        if len(domain.norm_text(raw_cat)) > _LIMITS['category']:
            messages.append(_msg('too_long', field='category'))
        else:
            matched = _match_category(state, raw_cat)
            if matched is False:
                messages.append(_msg('category', name=_clip(raw_cat, 80)))
            elif matched:
                values['categoryId'] = matched

    if kind == 'vehicles' and 'ownership' in columns and not _blank_cell(cell('ownership')):
        own = _choice(_as_text(cell('ownership')), _OWN, _RENT)
        if own == 'bad':
            messages.append(_msg('ownership'))
        elif own is True:
            values['ownership'] = 'own'
        elif own is False:
            values['ownership'] = 'rent'

    if 'startKm' in columns and not _blank_cell(cell('startKm')):
        try:
            values['startKm'] = _parse_km(cell('startKm'))
        except (ValueError, TypeError):
            messages.append(_msg('km'))

    if kind == 'drivers' and 'mobile' in columns and not _blank_cell(cell('mobile')):
        try:
            mobile = _parse_mobile(_as_text(cell('mobile')))
        except ValueError:
            mobile = None
            messages.append(_msg('mobile'))
        if mobile:
            values['mobile'] = mobile

    if kind == 'drivers' and 'licenseExpiry' in columns and not _blank_cell(cell('licenseExpiry')):
        try:
            iso, problem = _parse_date(cell('licenseExpiry'))
        except (ValueError, TypeError):
            iso, problem = None, 'date'
        if problem == 'expiry':
            messages.append(_msg('expiry'))
        elif problem or not iso:
            messages.append(_msg('date'))
        else:
            values['licenseExpiry'] = iso

    if 'active' in columns and not _blank_cell(cell('active')):
        flag = _choice(_as_text(cell('active')), _YES, _NO)
        if flag == 'bad':
            messages.append(_msg('active'))
        elif flag is not None:
            values['active'] = flag

    return key, label, values, messages


def _header_map(kind, cells):
    aliases, columns = _ALIAS[kind], {}
    for index, value in enumerate(cells):
        field = aliases.get(_alias_key(_as_text(value)))
        if field and field not in columns:
            columns[field] = index
    if _REQUIRED[kind] not in columns:
        return None
    return columns


def _sheet_matrix(sheet):
    width = max(sheet.max_col, 1)
    rows = []
    for number in range(1, sheet.max_row + 1):
        cells = [sheet.value(number, col) for col in range(1, width + 1)]
        rows.append((number, cells))
    return rows


def _usable_sheets(book):
    visible = [sheet for sheet in book.sheets if not sheet.hidden]
    return visible or list(book.sheets)


def parse_workbook(book, kind, state):
    """Workbook -> plan. Raises FleetError when the file has no recognisable header or is too large."""
    kind = kind_or_raise(kind)
    found = []
    for sheet in _usable_sheets(book):
        matrix = _sheet_matrix(sheet)
        header_at, columns = None, None
        for number, cells in matrix[:_HEADER_SCAN]:
            if all(_blank_cell(c) for c in cells):
                continue
            columns = _header_map(kind, cells)
            if columns:
                header_at = number
                break
        if header_at:
            found.append((sheet.name, header_at, columns, matrix))
    if not found:
        raise FleetError('This file has no vehicle or driver columns. Download the template and fill it in.', 'err.flt.noColumns')

    existing = _index(state or {}, kind)
    items, blanks = [], []
    seen = {}
    data_count = 0
    for sheet_name, header_at, columns, matrix in found:
        last = header_at
        for number, _cells in matrix:
            if number > header_at and not all(_blank_cell(c) for c in _cells):
                last = number
        for number, cells in matrix:
            if number <= header_at or number > last:
                continue
            if all(_blank_cell(c) for c in cells):
                blanks.append({'row': number, 'sheet': sheet_name})
                continue
            data_count += 1
            if data_count > MAX_ROWS:
                raise FleetError(f'The file has more than {MAX_ROWS} rows. Split it into smaller files.', 'err.flt.big')
            key, label, values, messages = _parse_row(kind, cells, columns, state or {})
            if key:
                if key in seen:
                    messages.append(_msg('dup_file', row=seen[key]))
                elif not messages:
                    seen[key] = number
            if messages:
                status = 'error'
            elif key in existing:
                status = 'same' if _unchanged(existing[key], values) else 'update'
            else:
                status = 'new'
            items.append({'row': number, 'sheet': sheet_name, 'status': status, 'key': key, 'label': label,
                          'values': values, 'messages': messages})
    return _plan(kind, items, blanks, [name for name, _, _, _ in found])


def _unchanged(existing, values):
    for key, value in values.items():
        current = existing.get(key)
        if current in (None, '') and value in (None, ''):
            continue
        if current != value:
            return False
    return True


def _plan(kind, items, blanks, sheets):
    stats = {'rows': len(items), 'new': 0, 'update': 0, 'same': 0, 'error': 0, 'blank': len(blanks)}
    for item in items:
        stats[item['status']] += 1
    samples = [{'row': item['row'], 'sheet': item['sheet'], 'status': item['status'], 'label': item['label']}
               for item in items if item['status'] in ('new', 'update')][:12]
    errors = [{'row': item['row'], 'sheet': item['sheet'], 'label': item['label'], 'messages': item['messages']}
              for item in items if item['status'] == 'error']
    return {'kind': kind, 'sheets': sheets, 'stats': stats, 'samples': samples, 'errors': errors,
            'blanks': blanks[:30], 'rows': items, 'ready': stats['new'] + stats['update']}


def public_plan(plan):
    """What the screen needs. The parsed values stay on the server until confirm."""
    out = {key: plan[key] for key in ('kind', 'sheets', 'stats', 'samples', 'errors', 'blanks', 'ready')}
    out['filename'] = plan.get('filename') or ''
    return out


def parse_bytes(data, filename, kind, state):
    kind = kind_or_raise(kind)
    try:
        book = formats.read_workbook(data, filename or '', engine='native')
    except formats.FormatError as exc:
        raise FleetError(str(exc), exc.code) from exc
    plan = parse_workbook(book, kind, state)
    plan['filename'] = clean_name(filename) or 'file'
    return plan


# The training exercise. Counts below are what parse_bytes returns, and the tests lock them.
# Vehicles: four good plates, one of them the training car «أ ب ج 1234» (an update only when that plate
# already exists), three bad rows (empty plate, a repeated plate, and a row with a bad category,
# ownership, odometer and active flag) and one blank row between them.
# Drivers: three good names, one of them «أحمد سمير» (an update only when that name already exists),
# three bad rows (empty name, a repeated name, a bad mobile and date) and one blank row.
_PRACTICE_ROWS = {
    'vehicles': [
        ['ت ث ج 1001', 'تويوتا', '', 'ملك', '', '45000', '', 'نعم'],
        ['ت ث ج 1002', 'هيونداي', '', 'إيجار', 'شركة النور', '١٢٠٠٠', '', 'نعم'],
        ['أ ب ج ١٢٣٤', 'سيدان محدّثة', '', 'إيجار', '', '86000', '', 'نعم'],
        ['', 'بدون لوحة', '', 'ملك', '', '', '', 'نعم'],
        ['ت ث ج 1001', 'مكرر', '', 'ملك', '', '', '', 'نعم'],
        ['', '', '', '', '', '', '', ''],
        ['ت ث ج 1004', 'كيا', 'فئة ليست هنا', 'عربية', '', 'abc', '', 'ربما'],
        ['ت ث ج 1005', 'نيسان', '', 'ملك', '', '', '', 'نعم'],
    ],
    'drivers': [
        ['سامي فريد', '01099887766', '', '998877', '2028-06-30', 'نعم'],
        ['أحمد سمير', '01001234567', '', '', '2029-01-15', 'نعم'],
        ['', '01011111111', '', '', '', 'نعم'],
        ['سامي فريد', '01099887766', '', '', '', 'نعم'],
        ['', '', '', '', '', ''],
        ['نادر خطأ', '123', '', '', 'غدا', 'لا'],
        ['ليلى حسن', '01123456789', '', '', '30/06/2028', 'نعم'],
    ],
}


def practice_book(kind):
    """The bundled exercise sheet: good rows plus rows that are wrong on purpose. Nothing is saved here."""
    kind = kind_or_raise(kind)
    headers = VEHICLE_HEADERS if kind == 'vehicles' else DRIVER_HEADERS
    sheet = 'السيارات' if kind == 'vehicles' else 'السائقون'
    rows = [list(headers), *[list(row) for row in _PRACTICE_ROWS[kind]]]
    return w.build([w.Sheet(sheet, rows, rtl=True)])


def practice_name(kind):
    kind_or_raise(kind)
    return 'Vehicles_practice.xlsx' if kind == 'vehicles' else 'Drivers_practice.xlsx'


def template(kind):
    """An .xlsx the office fills in: Arabic headers, one example row, and a short instruction sheet."""
    kind = kind_or_raise(kind)
    if kind == 'vehicles':
        headers, example, sheet = VEHICLE_HEADERS, ['أ ب ج ١٢٣٤', 'تويوتا', '', 'ملك', '', '٤٥٠٠٠', 'مثال', 'نعم'], 'السيارات'
        help_lines = [
            'املأ صفحة السيارات: صف لكل سيارة.',
            'اللوحة مطلوبة. باقي الخانات اختيارية.',
            'الملكية: ملك أو إيجار. النشط: نعم أو لا.',
            'الأرقام العربية والإنجليزية مقبولة، وترتيب الأعمدة ليس مهمًا.',
            'إذا كانت اللوحة موجودة، الصف يحدّث السيارة ولا يكررها.',
            'امسح صف المثال قبل الرفع لو مش عايز سيارة المثال.',
        ]
        widths = [22, 16, 18, 14, 18, 24, 22, 12]
    else:
        headers, example, sheet = DRIVER_HEADERS, ['محمود أحمد', '٠١٠١٢٣٤٥٦٧٨', '', '١٢٣٤٥٦', '2028-06-30', 'نعم'], 'السائقون'
        help_lines = [
            'املأ صفحة السائقين: صف لكل سائق.',
            'الاسم مطلوب. الموبايل مصري، مثل 01012345678.',
            'إذا كان الاسم موجودًا، الصف يحدّث السائق ولا يكرره.',
            'تاريخ الرخصة مثل 2028-06-30 أو 30/06/2028.',
            'امسح صف المثال قبل الرفع لو مش عايز سائق المثال.',
        ]
        widths = [24, 20, 18, 16, 20, 12]
    head = [w.S(text, 'header') for text in headers]
    letters = w.col_letters(len(headers))
    data = w.Sheet(sheet, [head, example], widths=widths, freeze=(0, 1), rtl=True, grid=False,
                   autofilter=f'A1:{letters}2')
    notes = w.Sheet('تعليمات', [[line] for line in help_lines], widths=[72], rtl=True, grid=False)
    return w.build([data, notes])


def _new_id(kind):
    return ('ve' if kind == 'vehicles' else 'dr') + uuid.uuid4().hex[:14]


def _merge(kind, existing, values):
    row = {}
    for field in _FIELDS[kind]:
        if existing.get(field) is not None:
            row[field] = existing[field]
    row.update(values)
    return row


def _insert_row(kind, item):
    row = {'active': True}
    if kind == 'vehicles':
        row['plate'] = item['label']
        row['ownership'] = 'own'
    else:
        row['name'] = item['label']
    row.update(item['values'])
    return row


def build_ops(plan, state):
    """The confirmed rows -> journal ops against the current lists. Raises FleetError when nothing can be saved
    or a category used by the file was removed (then the caller saves nothing)."""
    kind = plan['kind']
    categories = {cat.get('id') for cat in (state or {}).get('tripCategories') or []}
    for item in plan['rows']:
        if item['status'] not in ('new', 'update'):
            continue
        category = item['values'].get('categoryId')
        if category and category not in categories:
            raise FleetError('The lists changed while the file was being reviewed. Nothing was saved.', 'err.flt.changed')
    current = _index(state or {}, kind)
    ops, seen = [], set()
    new = updated = 0
    changed = FleetError('The lists changed while the file was being reviewed. Nothing was saved.', 'err.flt.changed')
    for item in plan['rows']:
        if item['status'] not in ('new', 'update') or not item.get('key') or item['key'] in seen:
            continue
        seen.add(item['key'])
        have = current.get(item['key'])
        # The preview is the contract: a "new" plate that appeared since, or an "update" whose row is gone,
        # would save something the person did not confirm. Refuse the whole file.
        if item['status'] == 'new' and have:
            raise changed
        if item['status'] == 'update' and not have:
            raise changed
        if have:
            if _unchanged(have, item['values']):
                continue
            ops.append({'e': kind, 'id': have['id'], 'op': 'put', 'ver': have.get('ver'), 'row': _merge(kind, have, item['values'])})
            updated += 1
        else:
            ops.append({'e': kind, 'id': _new_id(kind), 'op': 'put', 'row': _insert_row(kind, item)})
            new += 1
    if not ops:
        raise FleetError('There is nothing to import.', 'err.flt.nothing')
    return ops, new, updated


def commit_label(kind, filename, new, updated):
    word = 'Vehicle' if kind == 'vehicles' else 'Driver'
    suffix = f' ({new} new, {updated} updated)'
    prefix = f'{word} Excel import '
    room = 200 - len(prefix) - len(suffix)
    return prefix + (clean_name(filename) or 'file')[:max(1, room)] + suffix


def store_preview(user, plan):
    now = time.time()
    with _LOCK:
        for key, value in list(_PREVIEWS.items()):
            if now - value['at'] > _PREVIEW_TTL:
                _PREVIEWS.pop(key, None)
        while len(_PREVIEWS) >= _MAX_PREVIEWS:
            oldest = min(_PREVIEWS, key=lambda k: _PREVIEWS[k]['at'])
            _PREVIEWS.pop(oldest, None)
        pid = uuid.uuid4().hex[:16]
        _PREVIEWS[pid] = {'at': now, 'user': user, 'plan': plan}
    return pid


def get_preview(pid, user):
    with _LOCK:
        value = _PREVIEWS.get(pid)
        if not value or value['user'] != user or time.time() - value['at'] > _PREVIEW_TTL:
            raise FleetError('The preview expired. Choose the file again.', 'err.flt.expired')
        return value['plan']


def take_preview(pid, user):
    """Reads the preview and forgets it. A second confirm of the same id cannot save the rows again."""
    with _LOCK:
        value = _PREVIEWS.pop(pid, None)
        if not value or value['user'] != user or time.time() - value['at'] > _PREVIEW_TTL:
            raise FleetError('The preview expired. Choose the file again.', 'err.flt.expired')
        return value['plan']


def drop_preview(pid):
    with _LOCK:
        _PREVIEWS.pop(pid, None)
