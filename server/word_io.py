"""Trip Orders - Word: the printable trip order form (blank or filled), reading filled forms back, and the monthly report.

The form has the same fields as the paper form people already know, in the same order, in Arabic (right-to-left) or English.
Nothing about the company is written here: the title, the legal line and the footer come from the settings (brand.* / form.legal_text).
"""
import datetime as dt
import re

import docx_read
import formats
import docx_write as dw
import domain
import excel_io
import reports

# field -> (Arabic label, English label); the order is the order on the form
LABELS = [
    ('passenger', 'اسم الراكب', 'Passenger name'),
    ('department', 'القسم', 'Department'),
    ('gaOk', 'موافقة قسم الشؤون العامة', 'General Affairs approval'),
    ('gaSign', 'توقيع موظف الشؤون العامة', 'General Affairs signature'),
    ('gaDate', 'تاريخ موافقة الشؤون العامة', 'Approval date'),
    ('driver', 'اسم السائق', 'Driver name'),
    ('plate', 'رقم السيارة', 'Car plate'),
    ('carType', 'نوع السيارة', 'Car type'),
    ('startKm', 'الكيلومتر البادئ للرحلة', 'Start odometer (km)'),
    ('startPoint', 'نقطة بدء الرحلة', 'Start point'),
    ('startTime', 'وقت بدء الرحلة', 'Start time'),
    ('startDate', 'تاريخ بدء الرحلة', 'Start date'),
    ('route', 'خط سير الرحلة بالتفصيل', 'Route in detail'),
    ('endKm', 'الكيلومتر الناهي للرحلة', 'End odometer (km)'),
    ('endPoint', 'نقطة نهاية الرحلة', 'End point'),
    ('endTime', 'وقت إنهاء الرحلة', 'End time'),
    ('endDate', 'تاريخ إنهاء الرحلة', 'End date'),
    ('passSign', 'توقيع الراكب', 'Passenger signature'),
    ('driverSign', 'توقيع السائق', 'Driver signature'),
]
_L = {f: (ar, en) for f, ar, en in LABELS}
# pairs of fields shown side by side (label, value, label, value)
_ROWS = [('passenger', 'department'), ('gaOk', 'gaSign'), ('gaDate', None), ('driver', 'plate'), ('carType', None), ('startKm', 'startPoint'),
         ('startTime', 'startDate'), ('route', None), ('endKm', 'endPoint'), ('endTime', 'endDate'), ('passSign', 'driverSign')]
_WIDE = {'route', 'gaDate', 'carType'}

TITLE = {'ar': 'أمر تشغيل سيارة', 'en': 'Vehicle Trip Order'}
NOLBL = {'ar': 'رقم الأمر', 'en': 'Order No.'}

_FIELD_OF = {}
for _f, _ar, _en in LABELS:
    _FIELD_OF[domain.key_text(_ar)] = _f
    _FIELD_OF[domain.key_text(_en)] = _f
# short spellings people type
for _k, _f in {'اسم الراكب': 'passenger', 'الراكب': 'passenger', 'passenger': 'passenger', 'driver': 'driver', 'plate': 'plate', 'car number': 'plate',
               'route': 'route', 'start km': 'startKm', 'end km': 'endKm'}.items():
    _FIELD_OF.setdefault(domain.key_text(_k), _f)


class WordError(Exception):
    """A problem with a message the person can act on."""


# --------------------------------------------------------------------------- the form
def form(ctx=None, lang='ar', brand=None, legal=''):
    """The trip order form as .docx bytes. ctx: {field: text} to prefill, plus 'no'. brand: {'name','title'}; legal: text under the form."""
    ctx = ctx or {}
    brand = brand or {}
    ar = lang == 'ar'
    i = 0 if ar else 1
    doc = dw.Doc(rtl=ar, font='Arial', footer=brand.get('footer', ''))
    if brand.get('name'):
        doc.para(brand['name'], bold=True, size=12, align='center', after=2)
    doc.para(brand.get('title') or TITLE[lang], bold=True, size=18, align='center', color='13294B', after=4)
    no = ctx.get('no', '')
    doc.para([dw.Run(NOLBL[lang] + ': ', bold=True), dw.Run(no or '________')], align='center', after=10)
    rows, merges, shade = [], {}, {}
    for a, b in _ROWS:
        r = len(rows)
        if b is None or a in _WIDE:
            rows.append([dw.Run(_L[a][i], bold=True), dw.Run(ctx.get(a, '')), '', ''])
            merges[(r, 1)] = 3
        else:
            rows.append([dw.Run(_L[a][i], bold=True), dw.Run(ctx.get(a, '')), dw.Run(_L[b][i], bold=True), dw.Run(ctx.get(b, ''))])
        shade[(r, 0)] = 'F1F4FA'
        if not (b is None or a in _WIDE):
            shade[(r, 2)] = 'F1F4FA'
    # wide rows: label, one merged value cell of 3 columns
    for r, row in enumerate(rows):
        if (r, 1) in merges:
            rows[r] = row[:2]
    doc.table(rows, widths=[4.0, 5.0, 4.0, 4.4], merges=merges, shade=shade, size=11)
    if legal:
        doc.para(legal, size=9, italic=True, after=4, before=6)
    return doc.bytes()


# --------------------------------------------------------------------------- reading a filled form
def _digits(s):
    return str(s).translate(domain._AR_DIGITS)


def parse_time(s):
    """"9:41 صباحاً", "3:30 مساء", "15:20", "٠٩:٤١" -> 'HH:MM' or None."""
    s = _digits(domain.norm_text(s))
    m = re.search(r'(\d{1,2})\s*[:.]\s*(\d{2})', s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    low = s.lower()
    pm = 'مساء' in low or 'pm' in low or bool(re.search(r'(?<!\w)م(?!\w)', low))
    am = 'صباح' in low or 'am' in low or bool(re.search(r'(?<!\w)ص(?!\w)', low))
    if am and pm:
        pm = False
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return f'{h:02d}:{mi:02d}'


def parse_date(s):
    s = _digits(domain.norm_text(s))
    m = re.search(r'(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})', s)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        if a > 31:
            return dt.date(a, b, c)
        if c < 100:
            c += 2000
        return dt.date(c, b, a)
    except ValueError:
        return None


def parse_km(s):
    s = _digits(domain.norm_text(s))
    m = re.search(r'\d[\d,]*', s)
    return int(m.group(0).replace(',', '')) if m else None


def parse_forms(data, name='', engine='auto'):
    """docx bytes -> [{field: text}] one record per form found (a file may hold many forms, one after the other)."""
    try:
        d = formats.read_document(data, name, engine)
    except formats.FormatError as e:
        raise WordError(str(e))
    records, cur = [], {}
    for table in d['tables']:
        for row in table:
            i = 0
            while i < len(row):
                f = _FIELD_OF.get(domain.key_text(row[i].rstrip(':：')))
                if f is None:
                    i += 1
                    continue
                val = ''
                if i + 1 < len(row) and domain.key_text(row[i + 1].rstrip(':：')) not in _FIELD_OF:
                    val = row[i + 1]
                    i += 1
                if f in cur:                       # the same field again = the next form starts here
                    records.append(cur)
                    cur = {}
                cur[f] = val.strip()
                i += 1
    if cur:
        records.append(cur)
    records = [r for r in records if any(v for k, v in r.items() if k not in ('gaOk',))]
    if not records:
        raise WordError('No trip order form was found in this document. The form must be the trip order table (labels such as "اسم السائق" / "Driver name" with their values next to them).')
    return records


def rows_from_forms(records, category):
    """Form records -> rows in the same shape the Excel reader gives, so one review screen and one commit serve both."""
    rows = []
    for n, rec in enumerate(records, 1):
        date = parse_date(rec.get('startDate', '')) or parse_date(rec.get('endDate', ''))
        route = rec.get('route') or ' - '.join(x for x in (rec.get('startPoint'), rec.get('endPoint')) if x)
        row = {'sheet': category, 'row': n, 'warnings': [], 'date': date, 'driver': domain.norm_text(rec.get('driver')), 'plate': domain.norm_text(rec.get('plate')),
               'requester': domain.norm_text(rec.get('passenger')), 'employee': '', 'category': category, 'department': domain.norm_text(rec.get('department')),
               'destination': domain.norm_text(route), 'seq': None, 'startKm': parse_km(rec.get('startKm', '')), 'endKm': parse_km(rec.get('endKm', '')),
               'billableKm': None}
        t1, t2 = parse_time(rec.get('startTime', '')), parse_time(rec.get('endTime', ''))
        row['startTime'] = dt.time.fromisoformat(t1) if t1 else None
        row['endTime'] = dt.time.fromisoformat(t2) if t2 else None
        excel_io._check_row(row)
        rows.append(row)
    return rows


def preview(user, data, state, category, filename='', engine='auto'):
    """Word file -> review screen (same shape as the Excel review). category: the trip category the forms belong to."""
    category = domain.norm_text(category)
    if not category:
        raise WordError('Choose the trip category these forms belong to.')
    rows = rows_from_forms(parse_forms(data, filename, engine), category)
    p = excel_io.plan(rows, state, filename)
    p['source'] = 'word'
    p['sheets'] = [{'sheet': category, 'used': True, 'rows': len(rows)}]
    pid, _ = excel_io.store_preview(user, p)
    return pid, p


# --------------------------------------------------------------------------- the monthly report
_T = {
    'title': ('Monthly trips report', 'تقرير الرحلات الشهري'),
    'month': ('Month', 'الشهر'), 'all': ('All trips', 'كل الرحلات'),
    'trips': ('Trips', 'الرحلات'), 'km': ('Kilometres', 'الكيلومترات'), 'hours': ('Hours', 'الساعات'), 'ot': ('Overtime h', 'إضافي (ساعة)'),
    'green': ('Verified', 'موثوقة'), 'yellow': ('Worth a look', 'تحتاج نظرة'), 'red': ('Needs a decision', 'تحتاج قرارًا'),
    'byVehicle': ('By vehicle', 'حسب السيارة'), 'byDriver': ('By driver', 'حسب السائق'), 'byDepartment': ('By department', 'حسب القسم'),
    'byCategory': ('By trip category', 'حسب نوع الرحلة'), 'name': ('Name', 'الاسم'), 'avg': ('Avg km', 'متوسط كم'),
    'ovt': ('Overtime', 'الوقت الإضافي'), 'driver': ('Driver', 'السائق'), 'total': ('Total', 'الإجمالي'),
    'rec': ('Vendor reconciliation', 'مطابقة المورّد'), 'cat': ('Category', 'النوع'), 'vendor': ('Vendor', 'المورّد'),
    'actual': ('Odometer km', 'كم العداد'), 'billed': ('Billed km', 'كم المفوتر'), 'diff': ('Difference km', 'الفرق كم'), 'money': ('Difference', 'الفرق (مبلغ)'),
    'alloc': ('Cost by department', 'تكلفة الأقسام'), 'kmCost': ('Km cost', 'تكلفة الكم'), 'otCost': ('Overtime cost', 'تكلفة الإضافي'),
    'anom': ('Worth a look', 'يستحق المراجعة'), 'date': ('Date', 'التاريخ'), 'no': ('Trip', 'الرحلة'), 'plate': ('Plate', 'السيارة'), 'why': ('Why', 'السبب'),
    'top': ('Most used routes', 'أكثر المسارات استخدامًا'), 'route': ('Route', 'المسار'), 'none': ('Nothing to report.', 'لا يوجد شيء.'),
    'more': ('… and {n} more (see the Excel report).', '… و{n} أخرى (راجع تقرير الإكسيل).'),
}
_REASON = {
    'en': {**excel_io.WHY['en']} if isinstance(excel_io.WHY.get('en'), dict) else {},
    'ar': {**excel_io.WHY['ar']} if isinstance(excel_io.WHY.get('ar'), dict) else {},
}


def _tr(k, lang, **kw):
    return _T[k][1 if lang == 'ar' else 0].format(**kw)


def _num(x):
    return f'{x:,.0f}' if isinstance(x, (int, float)) and float(x).is_integer() else (f'{x:,.2f}' if isinstance(x, (int, float)) else str(x))


def report(state, ym, lang='en', brand=None):
    """Monthly report as .docx: totals, per vehicle/driver/department/category, overtime, reconciliation, cost, things to look at."""
    brand = brand or {}
    ar = lang == 'ar'
    doc = dw.Doc(rtl=ar, footer=brand.get('footer', ''))
    s = reports.summaries(state, ym)
    t = s['total']
    if brand.get('name'):
        doc.para(brand['name'], bold=True, size=11, align='center', after=2)
    doc.heading(_tr('title', lang))
    doc.para(f'{_tr("month", lang)}: {ym or _tr("all", lang)}', after=8)
    doc.table([[_tr(k, lang) for k in ('trips', 'km', 'hours', 'ot', 'green', 'yellow', 'red')],
               [_num(t['trips']), _num(t['km']), _num(t['hours']), _num(t['ot']), _num(t['green']), _num(t['yellow']), _num(t['red'])]],
              header=True, align='center', size=10)

    def group(title, rows, limit=25):
        doc.heading(_tr(title, lang), 2)
        if not rows:
            doc.para(_tr('none', lang))
            return
        body = [[_tr('name', lang), _tr('trips', lang), _tr('km', lang), _tr('avg', lang), _tr('ot', lang)]]
        for r in rows[:limit]:
            body.append([str(r['label']), _num(r['trips']), _num(r['km']), _num(r['avgKm']), _num(r['ot'])])
        doc.table(body, widths=[6.5, 2.5, 3, 2.5, 2.5], header=True, size=10)
        if len(rows) > limit:
            doc.para(_tr('more', lang, n=len(rows) - limit), size=9, italic=True)

    group('byVehicle', s['byVehicle'])
    group('byDriver', s['byDriver'])
    group('byDepartment', s['byDepartment'])
    group('byCategory', s['byCategory'])
    if s['topRoutes']:
        doc.heading(_tr('top', lang), 2)
        doc.table([[_tr('route', lang), _tr('trips', lang), _tr('km', lang)]] + [[r['label'], _num(r['trips']), _num(r['km'])] for r in s['topRoutes']],
                  widths=[11, 3, 3], header=True, size=10)
    ot = reports.overtime(state, ym)
    doc.heading(_tr('ovt', lang), 2)
    if ot:
        doc.table([[_tr('driver', lang), _tr('ot', lang)]] + [[o['driver'], _num(o['total'])] for o in ot[:25]], widths=[10, 4], header=True, size=10)
    else:
        doc.para(_tr('none', lang))
    rec = reports.reconciliation(state, ym)
    if rec:
        doc.heading(_tr('rec', lang), 2)
        doc.table([[_tr('cat', lang), _tr('vendor', lang), _tr('trips', lang), _tr('actual', lang), _tr('billed', lang), _tr('diff', lang), _tr('money', lang)]] +
                  [[r['category'], r['vendor'], _num(r['trips']), _num(r['actualKm']), _num(r['billedKm']), _num(r['diffKm']), _num(r['diffMoney'])] for r in rec],
                  header=True, size=9)
    al = reports.allocation(state, ym)
    if al and any(a['total'] for a in al):
        doc.heading(_tr('alloc', lang), 2)
        doc.table([[_tr('name', lang), _tr('trips', lang), _tr('km', lang), _tr('kmCost', lang), _tr('otCost', lang), _tr('total', lang)]] +
                  [[a['department'], _num(a['trips']), _num(a['km']), _num(a['kmCost']), _num(a['otCost']), _num(a['total'])] for a in al], header=True, size=9)
    an = reports.anomalies(state, ym)
    doc.heading(_tr('anom', lang), 2)
    if an:
        why = _REASON[lang]
        body = [[_tr('date', lang), _tr('no', lang), _tr('plate', lang), _tr('driver', lang), _tr('why', lang)]]
        for a in an[:40]:
            body.append([a['date'], str(a['no'] or ''), a['plate'], a['driver'], why.get(a['code'], a['code'])])
        doc.table(body, widths=[2.6, 3.2, 3, 4, 4.6], header=True, size=9)
        if len(an) > 40:
            doc.para(_tr('more', lang, n=len(an) - 40), size=9, italic=True)
    else:
        doc.para(_tr('none', lang))
    return doc.bytes()
