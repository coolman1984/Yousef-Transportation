"""Trip Orders - the workbook in and out.

IMPORT   read the workbook -> recognise its sheets by their header -> clean and match every row (drivers, cars, people,
         departments, categories, places) -> a PREVIEW with a status and messages per row and suggested merges of
         spellings -> nothing is written until the user confirms -> ONE change with everything.
EXPORT   "same as today": the three sheets, header spelling, column order, Excel Table, formulas and totals of the
         monthly workbook; "clean": a workbook with proper names and the summaries.

The header spelling of the original (`Depatment`, `Strat KM`, ` KM`, `Misr car KM`, `Column1`) is kept on purpose.
"""
import datetime as dt
import difflib
import hashlib
import re
import time
import uuid

import domain
import xlsx_read
import xlsx_write as w
import formats

# --------------------------------------------------------------------------- layout of the workbook (measured from the real file)
TODAY_HEADERS = ['Date', 'Driver Name', 'Car Plate', 'Requester', 'Employee Name', 'Trip Category', 'Depatment', 'Destination', 'Column1',
                 'Strat KM', 'End KM', ' KM', 'Misr car KM', 'Start', 'End', 'OT Hours']
SHEET_ALL, SHEET_SUV, SHEET_BUS = 'All Car', 'SUV Rent', 'Microbus Rent'
WIDTHS_ALL = [11.9, 28.1, 13.4, 24.6, 26.9, 17.3, 15.6, 66.3, 14.6, 13.1, 12.3, 9, 16, 9.7, 8.9, 13.6]

# header text (normalised) -> field name; the spelling variants people actually use
HEADER_FIELDS = {
    'date': 'date', 'driver name': 'driver', 'driver': 'driver', 'car plate': 'plate', 'plate': 'plate', 'requester': 'requester',
    'employee name': 'employee', 'employee': 'employee', 'passenger': 'employee', 'trip category': 'category', 'category': 'category',
    'depatment': 'department', 'department': 'department', 'destination': 'destination', 'route': 'destination',
    'column1': 'seq', '#': 'rownum', 'strat km': 'startKm', 'start km': 'startKm', 'end km': 'endKm', 'km': 'kmFormula',
    'misr car km': 'billableKm', 'billable km': 'billableKm', 'start': 'startTime', 'end': 'endTime', 'ot hours': 'ot',
}
NEEDED = {'date', 'driver', 'plate'}

_PREVIEWS = {}      # preview id -> {'at', 'user', 'plan'}
_PREVIEW_TTL = 30 * 60


class ImportError_(Exception):
    """An import problem with a message the person can act on."""


def _hkey(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())


# --------------------------------------------------------------------------- reading rows
def find_header(sheet):
    """(row number, {column: field}) of the header row, looking at the first 10 rows. None if the sheet is not a trips sheet."""
    for r in range(1, min(sheet.max_row, 10) + 1):
        cols = {}
        for c in range(1, sheet.max_col + 1):
            v = sheet.value(r, c)
            if isinstance(v, str) and _hkey(v) in HEADER_FIELDS:
                cols.setdefault(c, HEADER_FIELDS[_hkey(v)])
        if NEEDED <= set(cols.values()):
            return r, cols
    return None


def _to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
            try:
                return dt.datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
    return None


def _to_time(v):
    if isinstance(v, dt.datetime):
        return v.time()
    if isinstance(v, dt.time):
        return v if (v.hour or v.minute) else None      # 00:00 in the sheet means "not written"
    if isinstance(v, (int, float)) and 0 < v < 1:
        s = round(v * 86400)
        return dt.time(s // 3600, s % 3600 // 60)
    if isinstance(v, str):
        m = re.fullmatch(r'\s*(\d{1,2}):(\d{2})\s*', v)
        if m and int(m.group(1)) < 24:
            return dt.time(int(m.group(1)), int(m.group(2))) if (int(m.group(1)) or int(m.group(2))) else None
    return None


def _to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    if isinstance(v, str) and re.fullmatch(r'\s*\d[\d,]*(\.\d+)?\s*', v):
        return int(round(float(v.replace(',', ''))))
    return None


def parse_sheet(sheet, hdr):
    """Rows of one sheet -> [{'sheet','row','date','driver',...,'warnings':[(code, text)]}]"""
    hrow, cols = hdr
    rows = []
    for r in range(hrow + 1, sheet.max_row + 1):
        raw = {}
        for c, field in cols.items():
            cell = sheet.cells.get((r, c))
            raw[field] = cell.v if cell else None
        text_fields = ('driver', 'plate', 'requester', 'employee', 'category', 'department', 'destination')
        if not any(raw.get(f) not in (None, '') for f in ('date', 'driver', 'plate', 'destination', 'startKm')):
            continue
        if any(isinstance(raw.get(f), str) and raw[f].strip().upper() == 'TTL' for f in raw) or (raw.get('date') in (None, '') and not raw.get('driver')):
            continue          # totals row / stray numbers
        row = {'sheet': sheet.name, 'row': r, 'warnings': []}
        row['date'] = _to_date(raw.get('date'))
        for f in text_fields:
            row[f] = domain.norm_text(raw.get(f))
        row['seq'] = _to_int(raw.get('seq'))
        row['startKm'], row['endKm'], row['billableKm'] = _to_int(raw.get('startKm')), _to_int(raw.get('endKm')), _to_int(raw.get('billableKm'))
        row['startTime'], row['endTime'] = _to_time(raw.get('startTime')), _to_time(raw.get('endTime'))
        _check_row(row)
        rows.append(row)
    return rows


def _check_row(row):
    wa = row['warnings']
    if row['date'] is None:
        wa.append(('date', 'The date is missing or not a date.'))
    if not row['driver']:
        wa.append(('driver', 'The driver name is missing.'))
    if not row['plate']:
        wa.append(('plate', 'The car plate is missing.'))
    if row['startKm'] is None or row['endKm'] is None:
        wa.append(('km', 'The odometer readings are missing.'))
    elif row['endKm'] <= row['startKm']:
        wa.append(('km_order', f'End km ({row["endKm"]}) is not above start km ({row["startKm"]}).'))
    elif row['endKm'] - row['startKm'] > 1500:
        wa.append(('km_big', f'{row["endKm"] - row["startKm"]} km in one trip looks like a typing mistake.'))
    if row['startTime'] and row['endTime'] and row['endTime'] < row['startTime']:
        wa.append(('night', 'The trip ends after midnight; the end time is taken as the next day.'))


def read_workbook(data, name='', engine='auto'):
    """bytes -> (rows, sheet report). Raises ImportError_ with a person-readable message. Any common spreadsheet type (see formats.py)."""
    try:
        wb = formats.read_workbook(data, name, engine)
    except formats.FormatError as e:
        raise ImportError_(str(e))
    rows, report = [], []
    for sh in wb.sheets:
        if sh.hidden:
            report.append({'sheet': sh.name, 'used': False, 'why': 'hidden'})
            continue
        hdr = find_header(sh)
        if not hdr:
            report.append({'sheet': sh.name, 'used': False, 'why': 'no trip columns'})
            continue
        got = parse_sheet(sh, hdr)
        rows += got
        report.append({'sheet': sh.name, 'used': True, 'rows': len(got)})
    if not any(r['used'] for r in report):
        raise ImportError_('No sheet with trip columns was found. The first rows of a sheet must contain at least: Date, Driver Name and Car Plate.')
    if not rows:
        raise ImportError_('The sheets have the right columns but no trips in them.')
    return rows, report


# --------------------------------------------------------------------------- matching
def _index(state, entity, keyfield):
    out = {}
    for r in state.get(entity, []):
        k = r.get(keyfield) or domain.key_text(r.get('name') or r.get('plate'))
        if k and r.get('active') is not False:
            out.setdefault(k, r)
    return out


def _suggest(key, keys, cutoff=0.86):
    hit = difflib.get_close_matches(key, keys, n=1, cutoff=cutoff)
    return hit[0] if hit else None


def import_key(row):
    parts = [row['sheet'], str(row['date']), domain.key_text(row['driver']), domain.norm_plate(row['plate'])[1], domain.key_text(row['requester']),
             domain.key_text(row['employee']), domain.key_text(row['category']), domain.key_text(row['department']), domain.key_text(row['destination']),
             str(row['startKm']), str(row['endKm'])]
    if row['startKm'] is None or row['endKm'] is None:
        parts.append(f'row{row["row"]}')      # rows without km must not look like duplicates of each other
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def plan(rows, state, filename=''):
    """Match every row against the database. Returns the plan (a dict that is also the preview)."""
    drivers, vehicles = _index(state, 'drivers', 'nameKey'), _index(state, 'vehicles', 'plateKey')
    people, deps = _index(state, 'people', 'nameKey'), _index(state, 'departments', None)
    cats = {domain.key_text(c['name']): c for c in state.get('tripCategories', [])}
    existing = {t.get('importKey') for t in state.get('trips', []) if t.get('importKey')}
    seen, out = set(), []
    new = {'drivers': {}, 'vehicles': {}, 'people': {}, 'departments': {}, 'categories': {}, 'places': {}}
    stats = {'new': 0, 'duplicate': 0, 'problem': 0, 'km': 0, 'ot': 0.0}
    suggestions = []
    place_count = {}
    sheet_of_cat = {}

    for r in rows:
        item = {'sheet': r['sheet'], 'row': r['row'], 'date': r['date'].isoformat() if r['date'] else None, 'driver': r['driver'], 'plate': r['plate'],
                'requester': r['requester'], 'employee': r['employee'], 'category': r['category'], 'department': r['department'], 'destination': r['destination'],
                'seq': r['seq'], 'startKm': r['startKm'], 'endKm': r['endKm'], 'billableKm': r['billableKm'],
                'startTime': r['startTime'].strftime('%H:%M') if r['startTime'] else None, 'endTime': r['endTime'].strftime('%H:%M') if r['endTime'] else None,
                'messages': [{'code': c, 'text': t} for c, t in r['warnings']], 'matches': {}}
        key = import_key(r)
        item['key'] = key
        # category from the row, or from the sheet name when the row has none (rent sheets)
        cname = r['category'] or r['sheet']
        ck = domain.key_text(cname)
        item['category'] = cname
        cat = cats.get(ck)
        if cat:
            item['matches']['category'] = cat['id']
        else:
            new['categories'].setdefault(ck, {'name': cname, 'sheet': r['sheet']})
        sheet_of_cat[ck] = r['sheet']
        # driver
        dk = domain.key_text(r['driver'])
        if dk:
            if dk in drivers:
                item['matches']['driver'] = drivers[dk]['id']
            else:
                near = _suggest(dk, list(drivers))
                if near:
                    item['messages'].append({'code': 'driver_near', 'text': f'Driver "{r["driver"]}" looks like "{drivers[near]["name"]}". Check before importing.'})
                new['drivers'].setdefault(dk, {'name': r['driver'], 'near': drivers[near]['name'] if near else None})
        # vehicle
        if r['plate']:
            disp, pk = domain.norm_plate(r['plate'])
            item['plateNorm'] = disp
            if pk in vehicles:
                item['matches']['vehicle'] = vehicles[pk]['id']
            else:
                new['vehicles'].setdefault(pk, {'plate': disp, 'category': cname, 'rent': r['sheet'] in (SHEET_SUV, SHEET_BUS)})
        # people
        req = r['requester']
        if req:
            rk = domain.key_text(req)
            if rk in people:
                item['matches']['requester'] = people[rk]['id']
            else:
                new['people'].setdefault(rk, {'name': req, 'department': r['department']})
        emp = r['employee']
        if emp and domain.is_non_person(emp):
            item['purpose'] = emp
        elif emp and domain.key_text(emp) != domain.key_text(req):
            known = set(people) | set(new['people'])
            item['passengers'] = domain.split_passengers(emp, known)
        # department
        if r['department']:
            k = domain.key_text(r['department'])
            if k in deps:
                item['matches']['department'] = deps[k]['id']
            else:
                new['departments'].setdefault(k, {'name': r['department']})
        # destination stops (for the place suggestions)
        for stop in [x.strip() for x in re.split(r'\s*-\s*', r['destination']) if x.strip()]:
            place_count.setdefault(domain.key_text(stop), {}).setdefault(stop, 0)
            place_count[domain.key_text(stop)][stop] += 1
        # status
        if key in existing:
            item['status'] = 'duplicate'
            item['messages'].append({'code': 'dup_db', 'text': 'This trip is already in the system.'})
        elif key in seen:
            item['status'] = 'duplicate'
            item['messages'].append({'code': 'dup_file', 'text': 'The same trip appears twice in the file.'})
        elif r['date'] is None or not r['driver'] or not r['plate']:
            item['status'] = 'problem'
        else:
            item['status'] = 'new'
        seen.add(key)
        stats[item['status']] += 1
        if item['status'] == 'new' and r['startKm'] is not None and r['endKm'] is not None and r['endKm'] > r['startKm']:
            stats['km'] += r['endKm'] - r['startKm']
        if r['startTime'] and r['endTime']:
            d = dt.datetime.combine(dt.date.today(), r['endTime']) - dt.datetime.combine(dt.date.today(), r['startTime'])
            if d < dt.timedelta(0):
                d += dt.timedelta(days=1)
            stats['ot'] += domain.hours(domain.overtime(d))
        out.append(item)

    # odometer chain inside the file, per car (a back-step is worth an alert)
    per_car = {}
    for it in out:
        if it.get('plateNorm') and it['startKm'] is not None and it['endKm'] is not None and it['date']:
            per_car.setdefault(domain.norm_plate(it['plate'])[1], []).append({'id': f'{it["sheet"]}#{it["row"]}', 'no': it['date'] + f'{it["row"]:06d}',
                                                                              'date': it['date'], 'startKm': it['startKm'], 'endKm': it['endKm']})
    back = {}
    for trips in per_car.values():
        back.update(domain.odometer_chain(trips))
    by_id = {f'{it["sheet"]}#{it["row"]}': it for it in out}
    backsteps = 0
    for tid, info in back.items():
        if info.get('backstep') and tid in by_id:
            backsteps += 1
            by_id[tid]['messages'].append({'code': 'backstep', 'text': f'The odometer is {info["backstep"]} km lower than the previous trip of this car.'})

    # spellings of places that look the same -> suggested merges
    keys = sorted(place_count, key=lambda k: -sum(place_count[k].values()))
    used, groups = set(), []
    for k in keys:
        if k in used or len(k) < 3:
            continue
        grp = [k]
        for o in keys:
            if o != k and o not in used and difflib.SequenceMatcher(None, k, o).ratio() >= 0.8:
                grp.append(o)
        if len(grp) > 1:
            used.update(grp)
            variants = [{'text': t, 'count': c} for g in grp for t, c in place_count[g].items()]
            variants.sort(key=lambda v: -v['count'])
            groups.append({'canonical': variants[0]['text'], 'variants': [v['text'] for v in variants[1:]], 'counts': [v['count'] for v in variants]})
    existing_places = {domain.key_text(p['name']) for p in state.get('places', [])}
    for k, spellings in place_count.items():
        if k not in existing_places and len(k) >= 2:
            new['places'][k] = max(spellings, key=spellings.get)
    alerts = []
    if backsteps:
        alerts.append({'code': 'backsteps', 'level': 'bad', 'n': backsteps, 'text': f'{backsteps} trips start with a lower odometer than the previous trip of the same car.'})
    no_times = sum(1 for r in rows if not r['startTime'] and not r['endTime'])
    if no_times:
        alerts.append({'code': 'no_times', 'level': 'warn', 'n': no_times, 'text': f'{no_times} rows have no start/end time, so overtime cannot be worked out for them.'})
    no_km = sum(1 for i in out if i['startKm'] is None or i['endKm'] is None)
    if no_km:
        alerts.append({'code': 'no_km', 'level': 'warn', 'n': no_km, 'text': f'{no_km} rows have no odometer readings.'})
    diff = sum(1 for i in out if i['billableKm'] is not None and i['startKm'] is not None and i['endKm'] is not None and i['billableKm'] != i['endKm'] - i['startKm'])
    if diff:
        alerts.append({'code': 'billable', 'level': 'info', 'n': diff, 'text': f'{diff} trips have "Misr car KM" different from the odometer difference.'})
    return {'filename': filename, 'rows': out, 'stats': {**stats, 'ot': round(stats['ot'], 2), 'total': len(out), 'backsteps': backsteps},
            'new': {k: list(v.values()) for k, v in new.items()},
            'merges': groups, 'alerts': alerts, 'sheets': None, 'catsheet': sheet_of_cat}


def make_preview(user, data, state, filename='', engine='auto'):
    rows, report = read_workbook(data, filename, engine)
    p = plan(rows, state, filename)
    p['sheets'] = report
    return store_preview(user, p)


def store_preview(user, p):
    now = time.time()
    for k in [k for k, v in _PREVIEWS.items() if now - v['at'] > _PREVIEW_TTL]:
        _PREVIEWS.pop(k, None)
    pid = uuid.uuid4().hex[:16]
    _PREVIEWS[pid] = {'at': now, 'user': user, 'plan': p}
    return pid, p


def get_preview(pid, user):
    v = _PREVIEWS.get(pid)
    if not v or v['user'] != user or time.time() - v['at'] > _PREVIEW_TTL:
        raise ImportError_('The preview expired. Choose the file again.')
    return v['plan']


def drop_preview(pid):
    _PREVIEWS.pop(pid, None)


# --------------------------------------------------------------------------- commit
def build_ops(p, state, letter, skip_rows=(), merges=(), new_id=None, include_problems=False):
    """The plan -> journal ops (one change). skip_rows: ['sheet#row']; merges: [{'canonical', 'variants': []}] the user accepted."""
    new_id = new_id or (lambda prefix: prefix + uuid.uuid4().hex[:14])
    ops, ids = [], {'drivers': {}, 'vehicles': {}, 'people': {}, 'departments': {}, 'categories': {}}
    skip = set(skip_rows)
    rows = [r for r in p['rows'] if f'{r["sheet"]}#{r["row"]}' not in skip and (r['status'] == 'new' or (include_problems and r['status'] == 'problem'))]
    if not rows:
        raise ImportError_('There is nothing to import: every row is a duplicate, has a problem, or was left out.')
    used_keys = lambda entity: {  # noqa: E731
        'drivers': {domain.key_text(x['name']): x['id'] for x in state.get('drivers', [])},
        'people': {domain.key_text(x['name']): x['id'] for x in state.get('people', [])},
        'departments': {domain.key_text(x['name']): x['id'] for x in state.get('departments', [])},
        'vehicles': {x.get('plateKey') or domain.norm_plate(x.get('plate'))[1]: x['id'] for x in state.get('vehicles', [])},
        'categories': {domain.key_text(x['name']): x['id'] for x in state.get('tripCategories', [])}}[entity]
    have = {e: used_keys(e) for e in ids}

    def ensure(entity, key, make):
        if key in have[entity]:
            return have[entity][key]
        rid = new_id(entity[:2])
        have[entity][key] = rid
        ops.append(make(rid))
        return rid

    order = 0
    used_years = {}
    nos = [t.get('no') for t in state.get('trips', [])]
    for r in rows:
        cat_key = domain.key_text(r['category'])
        cat_id = ensure('categories', cat_key, lambda rid: {'e': 'tripCategories', 'id': rid, 'op': 'put', 'row': {
            'name': r['category'], 'exportSheet': p.get('catsheet', {}).get(cat_key) or r['sheet'], 'openLimitHours': 16, 'hasSequence': r['sheet'] == SHEET_ALL and domain.key_text(r['category']) == 'extra'}})
        veh = ensure('vehicles', domain.norm_plate(r['plate'])[1], lambda rid: {'e': 'vehicles', 'id': rid, 'op': 'put', 'row': {
            'plate': domain.norm_plate(r['plate'])[0], 'plateKey': domain.norm_plate(r['plate'])[1], 'categoryId': cat_id, 'active': True,
            'ownership': 'rent' if r['sheet'] in (SHEET_SUV, SHEET_BUS) else 'own'}}) if r['plate'] else ''
        drv = ensure('drivers', domain.key_text(r['driver']), lambda rid: {'e': 'drivers', 'id': rid, 'op': 'put', 'row': {
            'name': r['driver'], 'nameKey': domain.key_text(r['driver']), 'active': True}}) if r['driver'] else ''
        dep = ensure('departments', domain.key_text(r['department']), lambda rid: {'e': 'departments', 'id': rid, 'op': 'put', 'row': {
            'name': r['department'], 'active': True}}) if r['department'] else ''
        req = ensure('people', domain.key_text(r['requester']), lambda rid: {'e': 'people', 'id': rid, 'op': 'put', 'row': {
            'name': r['requester'], 'nameKey': domain.key_text(r['requester']), 'departmentId': dep, 'isRequester': True, 'isPassenger': True, 'active': True}}) if r['requester'] else ''
        pax = []
        for nm in r.get('passengers') or []:
            pid = ensure('people', domain.key_text(nm), lambda rid: {'e': 'people', 'id': rid, 'op': 'put', 'row': {
                'name': nm, 'nameKey': domain.key_text(nm), 'departmentId': dep, 'isPassenger': True, 'active': True}})
            pax.append({'personId': pid})
        if not pax and r['employee'] and not r.get('purpose') and domain.key_text(r['employee']) != domain.key_text(r['requester']):
            pax.append({'freeText': r['employee']})
        date = dt.date.fromisoformat(r['date'])
        year = date.year
        used_years.setdefault(year, domain.next_counter(nos, year, letter) - 1)
        used_years[year] += 1
        no = domain.trip_no(year, letter, used_years[year])
        start_at = end_at = None
        if r['startTime']:
            start_at = f'{r["date"]}T{r["startTime"]}:00'
        if r['endTime']:
            e = dt.datetime.combine(date, dt.time.fromisoformat(r['endTime']))
            if r['startTime'] and r['endTime'] < r['startTime']:
                e += dt.timedelta(days=1)
            end_at = e.isoformat()
        tid = new_id('tr')
        row = {'no': no, 'date': r['date'], 'categoryId': cat_id, 'vehicleId': veh, 'driverId': drv, 'requesterId': req, 'departmentId': dep,
               'destination': r['destination'], 'purpose': r.get('purpose') or '', 'status': 'closed', 'source': p.get('source', 'excel'), 'locked': True, 'importKey': r['key'],
               'gaApproved': '', 'seq': r['seq'], 'startKm': r['startKm'], 'endKm': r['endKm'], 'billableKm': r['billableKm'], 'startAt': start_at, 'endAt': end_at,
               'importWarn': False}
        row = {k: v for k, v in row.items() if v not in (None, '') and k != 'importWarn'}
        if r['messages'] and any(m['code'] in ('km', 'km_order', 'km_big', 'backstep', 'date', 'plate', 'driver') for m in r['messages']):
            row['notes'] = 'Imported with warnings: ' + '; '.join(m['text'] for m in r['messages'] if m['code'] not in ('night', 'dup_db', 'dup_file'))[:300]
        ops.append({'e': 'trips', 'id': tid, 'op': 'put', 'row': row})
        for x in pax:
            ops.append({'e': 'tripPassengers', 'id': new_id('tp'), 'op': 'put', 'row': {'tripId': tid, **{'personId': x.get('personId', ''), 'freeText': x.get('freeText', '')}}})
        order += 1
    # places: one record per stop, with the accepted spellings as aliases
    canon = {}
    aliases_for = {}
    for m in merges or []:
        aliases_for[domain.key_text(m['canonical'])] = list(m.get('variants') or [])
        for v in m.get('variants') or []:
            canon[domain.key_text(v)] = m['canonical']
    have_places = {domain.key_text(x['name']) for x in state.get('places', [])}
    for name in p['new'].get('places', []):
        k = domain.key_text(name)
        if k in canon or k in have_places:
            continue
        ops.append({'e': 'places', 'id': new_id('pl'), 'op': 'put', 'row': {'name': name, 'key': k, 'aliases': aliases_for.get(k, []), 'active': True}})
    return ops, len(rows)


# --------------------------------------------------------------------------- export
def _people(state):
    return {p['id']: p for p in state.get('people', [])}


def _trip_row_values(t, ctx):
    """The cells of one trip in the "same as today" layout."""
    veh = ctx['veh'].get(t.get('vehicleId')) or {}
    d = dt.date.fromisoformat(t['date'])
    pax = [ctx['ppl'].get(p['personId'], {}).get('name') if p.get('personId') else p.get('freeText') for p in ctx['pax'].get(t['id'], [])]
    pax = [x for x in pax if x]
    requester = (ctx['ppl'].get(t.get('requesterId')) or {}).get('name', '')
    employee = ' - '.join(pax) or t.get('purpose') or requester
    s, e = domain.parse_dt(t.get('startAt')), domain.parse_dt(t.get('endAt'))
    return {'date': d, 'driver': (ctx['drv'].get(t.get('driverId')) or {}).get('name', ''), 'plate': veh.get('plate', ''), 'requester': requester,
            'employee': employee, 'category': (ctx['cat'].get(t.get('categoryId')) or {}).get('name', ''), 'department': (ctx['dep'].get(t.get('departmentId')) or {}).get('name', ''),
            'destination': t.get('destination') or '', 'seq': t.get('seq'), 'startKm': t.get('startKm'), 'endKm': t.get('endKm'), 'billableKm': t.get('billableKm'),
            'start': s.time().replace(second=0) if s else None, 'end': e.time().replace(second=0) if e else None}


def _excel_ot(start, end):
    """Exactly what the workbook's formula gives: IF(End-Start>12:00, End-Start-12:00, 0) on the times of day."""
    if not start or not end:
        return 0.0
    d = (end.hour * 3600 + end.minute * 60 - start.hour * 3600 - start.minute * 60) / 86400
    return d - 0.5 if d > 0.5 else 0.0


def export_today(state, ym):
    """The monthly workbook in the layout people use today: All Car (Table1), SUV Rent, Microbus Rent (Table2)."""
    ctx = {'veh': {v['id']: v for v in state.get('vehicles', [])}, 'drv': {d['id']: d for d in state.get('drivers', [])}, 'ppl': _people(state),
           'cat': {c['id']: c for c in state.get('tripCategories', [])}, 'dep': {d['id']: d for d in state.get('departments', [])}, 'pax': {}}
    for p in state.get('tripPassengers', []):
        ctx['pax'].setdefault(p['tripId'], []).append(p)
    trips = sorted((t for t in state.get('trips', []) if str(t.get('date', ''))[:7] == ym and t.get('status') != 'cancelled'), key=lambda t: (t['date'], t.get('no', '')))
    by_sheet = {SHEET_ALL: [], SHEET_SUV: [], SHEET_BUS: []}
    for t in trips:
        sheet = (ctx['cat'].get(t.get('categoryId')) or {}).get('exportSheet') or SHEET_ALL
        by_sheet.setdefault(sheet if sheet in by_sheet else SHEET_ALL, []).append(t)
    sheets = []
    # ---- All Car
    rows = [list(TODAY_HEADERS)]
    day_seq = {}
    for i, t in enumerate(by_sheet[SHEET_ALL], start=2):
        v = _trip_row_values(t, ctx)
        seq = v['seq']
        if seq is None and (ctx['cat'].get(t.get('categoryId')) or {}).get('hasSequence'):
            day_seq[t['date']] = day_seq.get(t['date'], 0) + 1
            seq = day_seq[t['date']]
        km = v['endKm'] - v['startKm'] if v['startKm'] is not None and v['endKm'] is not None else None
        rows.append([v['date'], v['driver'], v['plate'], v['requester'], v['employee'], v['category'], v['department'], v['destination'], seq,
                     v['startKm'], v['endKm'], w.Formula('+Table1[[#This Row],[End KM]]-Table1[[#This Row],[Strat KM]]', km if km is not None else 0),
                     v['billableKm'], v['start'], v['end'],
                     w.S(w.Formula(f'IF(O{i}-N{i}>TIME(12,0,0),O{i}-N{i}-TIME(12,0,0),0)', _excel_ot(v['start'], v['end'])), 'time')])
    last = max(2, len(rows))
    tbl = w.Table('Table1', f'A1:P{last}', TODAY_HEADERS, formulas={
        ' KM': '+Table1[[#This Row],[End KM]]-Table1[[#This Row],[Strat KM]]', 'OT Hours': 'IF(O2-N2>TIME(12,0,0),O2-N2-TIME(12,0,0),0)'})
    if len(rows) == 1:
        rows.append([None] * 16)
    sheets.append(w.Sheet(SHEET_ALL, rows, widths=WIDTHS_ALL, tables=[tbl], freeze=(1, 0), grid=False))
    # ---- SUV Rent (no table, totals row)
    head15 = [h for h in TODAY_HEADERS if h != 'Column1']
    rows = [list(head15)]
    for i, t in enumerate(by_sheet[SHEET_SUV], start=2):
        v = _trip_row_values(t, ctx)
        km = v['endKm'] - v['startKm'] if v['startKm'] is not None and v['endKm'] is not None else 0
        rows.append([v['date'], v['driver'], v['plate'], v['requester'], v['employee'], v['category'], v['department'], v['destination'], v['startKm'], v['endKm'],
                     w.Formula(f'+J{i}-I{i}', km), v['billableKm'], v['start'], v['end'], w.S(w.Formula(f'IF(N{i}-M{i}>TIME(12,0,0),N{i}-M{i}-TIME(12,0,0),0)', _excel_ot(v['start'], v['end'])), 'time')])
    n = len(rows)
    tot_km = sum((r[10].cached or 0) for r in rows[1:])
    tot_b = sum((r[11] or 0) for r in rows[1:])
    tot_ot = sum(r[14].value.cached for r in rows[1:])
    rows.append([None] * 8 + [w.S('TTL', 'total_text'), None, w.S(w.Formula(f'+SUM(K2:K{n})', tot_km), 'total_int'), w.S(w.Formula(f'+SUM(L2:L{n})', tot_b), 'total_int'), None, None,
                 w.S(w.Formula(f'SUM(O2:O{n})', tot_ot), 'total_dur')])
    sheets.append(w.Sheet(SHEET_SUV, rows, widths=WIDTHS_ALL[:8] + WIDTHS_ALL[9:], freeze=(1, 0), grid=False, autofilter=f'A1:O{max(2, n)}'))
    # ---- Microbus Rent (Table2 with # column, totals row under the table)
    head16 = ['#'] + head15
    rows = [list(head16)]
    for i, t in enumerate(by_sheet[SHEET_BUS], start=2):
        v = _trip_row_values(t, ctx)
        km = v['endKm'] - v['startKm'] if v['startKm'] is not None and v['endKm'] is not None else 0
        rows.append([w.Formula('+ROW()-1', i - 1), v['date'], v['driver'], v['plate'], v['requester'], v['employee'], v['category'], v['department'], v['destination'], v['startKm'], v['endKm'],
                     w.Formula('+Table2[[#This Row],[End KM]]-Table2[[#This Row],[Strat KM]]', km), v['billableKm'], v['start'], v['end'],
                     w.S(w.Formula(f'IF(O{i}-N{i}>TIME(12,0,0),O{i}-N{i}-TIME(12,0,0),0)', _excel_ot(v['start'], v['end'])), 'time')])
    last = max(2, len(rows))
    tot_km = sum((r[11].cached or 0) for r in rows[1:])
    tot_b = sum((r[12] or 0) for r in rows[1:])
    tot_ot = sum(r[15].value.cached for r in rows[1:])
    if len(rows) == 1:
        rows.append([None] * 16)
    rows.append([None] * 9 + [w.S('TTL', 'total_text'), None, w.S(w.Formula('SUBTOTAL(109,Table2[[ KM]])', tot_km), 'total_int'), w.S(w.Formula(f'SUM(M2:M{last})', tot_b), 'total_int'), None, None,
                 w.S(w.Formula(f'SUM(P2:P{last})', tot_ot), 'total_dur')])
    t2 = w.Table('Table2', f'A1:P{last}', head16, formulas={'#': '+ROW()-1', ' KM': '+Table2[[#This Row],[End KM]]-Table2[[#This Row],[Strat KM]]', 'OT Hours': 'IF(O2-N2>TIME(12,0,0),O2-N2-TIME(12,0,0),0)'})
    sheets.append(w.Sheet(SHEET_BUS, rows, widths=[5] + WIDTHS_ALL[:8] + WIDTHS_ALL[9:], tables=[t2], freeze=(2, 0), grid=False))
    return w.build(sheets)


def template():
    """An empty workbook in the same layout (what a person fills to import)."""
    return export_today({}, '0000-00')


# --------------------------------------------------------------------------- clean export (proper names, the summaries)
LBL = {
    'en': {'summary': 'Summary', 'trips': 'Trips', 'by_vehicle': 'By vehicle', 'by_driver': 'By driver', 'by_dept': 'By department', 'by_cat': 'By category', 'overtime': 'Overtime',
           'recon': 'Vendor reconciliation', 'alloc': 'Cost allocation', 'anom': 'Anomalies', 'no': 'Trip no.', 'date': 'Date', 'category': 'Category', 'plate': 'Plate', 'driver': 'Driver',
           'requester': 'Requester', 'department': 'Department', 'passengers': 'Passengers', 'destination': 'Destination', 'start_km': 'Start km', 'end_km': 'End km', 'km': 'km',
           'billable': 'Billable km', 'start': 'Start', 'end': 'End', 'hours': 'Hours', 'ot': 'Overtime h', 'status': 'Status', 'trust': 'Trust', 'reasons': 'Why', 'source': 'Source',
           'trips_n': 'Trips', 'avg': 'Avg km', 'green': 'Green', 'yellow': 'Yellow', 'red': 'Red', 'vendor': 'Vendor', 'actual': 'Actual km', 'billed': 'Billed km', 'diff': 'Difference km',
           'money': 'Difference (money)', 'rate': 'Rate per km', 'km_cost': 'Km cost', 'ot_cost': 'Overtime cost', 'total': 'Total', 'item': 'Item', 'value': 'Value', 'level': 'Level',
           'code': 'Finding', 'total_trips': 'Trips', 'total_km': 'Kilometres', 'total_hours': 'Hours', 'total_ot': 'Overtime hours', 'days': 'Days with trips', 'month': 'Month'},
    'ar': {'summary': 'ملخص', 'trips': 'المشاوير', 'by_vehicle': 'حسب السيارة', 'by_driver': 'حسب السائق', 'by_dept': 'حسب القسم', 'by_cat': 'حسب الفئة', 'overtime': 'الإضافي',
           'recon': 'مطابقة الشركة المؤجرة', 'alloc': 'توزيع التكلفة', 'anom': 'ملاحظات', 'no': 'رقم المشوار', 'date': 'التاريخ', 'category': 'الفئة', 'plate': 'اللوحة', 'driver': 'السائق',
           'requester': 'طالب المشوار', 'department': 'القسم', 'passengers': 'الركاب', 'destination': 'الوجهة', 'start_km': 'عداد البداية', 'end_km': 'عداد النهاية', 'km': 'كم',
           'billable': 'كم المفوتر', 'start': 'البداية', 'end': 'النهاية', 'hours': 'الساعات', 'ot': 'ساعات الإضافي', 'status': 'الحالة', 'trust': 'الثقة', 'reasons': 'السبب', 'source': 'المصدر',
           'trips_n': 'المشاوير', 'avg': 'متوسط كم', 'green': 'أخضر', 'yellow': 'أصفر', 'red': 'أحمر', 'vendor': 'الشركة', 'actual': 'الكم الفعلي', 'billed': 'الكم المفوتر', 'diff': 'الفرق كم',
           'money': 'الفرق (مبلغ)', 'rate': 'سعر الكيلو', 'km_cost': 'تكلفة الكم', 'ot_cost': 'تكلفة الإضافي', 'total': 'الإجمالي', 'item': 'البند', 'value': 'القيمة', 'level': 'المستوى',
           'code': 'الملاحظة', 'total_trips': 'المشاوير', 'total_km': 'الكيلومترات', 'total_hours': 'الساعات', 'total_ot': 'ساعات الإضافي', 'days': 'أيام فيها مشاوير', 'month': 'الشهر'},
}
WHY = {
    'en': {'R_BACKSTEP': 'Odometer went backwards', 'R_END_LE_START': 'End km not above start km', 'R_NO_PAPER': 'Signed paper not photographed', 'R_SECOND_DEVICE': 'Sent from a second phone',
           'R_OPEN_TOO_LONG': 'Open for too long', 'Y_FALLBACK_PHOTO': 'Photo from the gallery', 'Y_NO_START_PHOTO': 'No start odometer photo', 'Y_KM_UNUSUAL': 'Unusual km for the route',
           'Y_DRIFT': 'Phone clock is off', 'Y_CLOSED_BY_OFFICE': 'Closed by the office', 'Y_AMENDED': 'Changed after saving', 'Y_IMPORT_WARN': 'Imported with warnings',
           'Y_BILLABLE_DIFF': 'Billable km differs', 'NO_KM': 'No odometer readings', 'NO_TIMES': 'No start/end times'},
    'ar': {'R_BACKSTEP': 'العداد رجع لورا', 'R_END_LE_START': 'عداد النهاية مش أكبر من البداية', 'R_NO_PAPER': 'الورقة الموقّعة ما اتصورتش', 'R_SECOND_DEVICE': 'اتبعت من موبايل تاني',
           'R_OPEN_TOO_LONG': 'مفتوح من وقت طويل', 'Y_FALLBACK_PHOTO': 'صورة من المعرض', 'Y_NO_START_PHOTO': 'مفيش صورة عداد البداية', 'Y_KM_UNUSUAL': 'كيلومترات غير معتادة',
           'Y_DRIFT': 'ساعة الموبايل مش مظبوطة', 'Y_CLOSED_BY_OFFICE': 'اتقفل من المكتب', 'Y_AMENDED': 'اتعدّل بعد الحفظ', 'Y_IMPORT_WARN': 'مستورد بملاحظات',
           'Y_BILLABLE_DIFF': 'كم المفوتر مختلف', 'NO_KM': 'مفيش قراءات عداد', 'NO_TIMES': 'مفيش أوقات بداية/نهاية'},
}
TRUST = {'en': {'green': 'Verified', 'yellow': 'Worth a look', 'red': 'Needs a decision', 'grey': 'In progress'},
         'ar': {'green': 'موثّق', 'yellow': 'يستاهل نظرة', 'red': 'محتاج قرار', 'grey': 'شغّال'}}


def _sheet(name, head, rows, rtl, kinds=None, widths=None):
    """A report sheet: bold header, frozen first row, filter, widths from the content. kinds: per column 'int' | 'dec' | 'dur' | None."""
    kinds = kinds or [None] * len(head)
    body = [[(w.S(v, kinds[i]) if kinds[i] and v is not None and not isinstance(v, (dt.date, dt.time)) else v) for i, v in enumerate(r)] for r in rows]
    table = [[w.S(h, 'header') for h in head]] + body
    ws = widths or [min(60, max(len(str(head[i])) + 3, *(len(str(r[i])) + 2 for r in rows[:300] if i < len(r) and r[i] is not None), 8)) for i in range(len(head))]
    return w.Sheet(name, table, widths=ws, freeze=(0, 1), rtl=rtl, autofilter=f'A1:{w.col_letters(len(head))}{max(2, len(table))}', landscape=True)


def export_clean(state, ym, lang='en', money=True):
    """money=False leaves out the vendor reconciliation and cost allocation sheets (rates are only for finance.view)."""
    import reports
    L, why, trust, rtl = LBL.get(lang, LBL['en']), WHY.get(lang, WHY['en']), TRUST.get(lang, TRUST['en']), lang == 'ar'
    rows = reports.enrich(state, ym)
    sm = reports.summaries(state, ym)
    ppl = {p['id']: p for p in state.get('people', [])}
    pax = {}
    for p in state.get('tripPassengers', []):
        pax.setdefault(p['tripId'], []).append((ppl.get(p.get('personId')) or {}).get('name') or p.get('freeText') or '')
    sheets = []
    t = sm['total']
    sheets.append(_sheet(L['summary'], [L['item'], L['value']], [[L['month'], ym or '-'], [L['total_trips'], t['trips']], [L['total_km'], t['km']], [L['total_hours'], t['hours']],
                                                              [L['total_ot'], t['ot']], [L['days'], t['days']], [L['green'], t['green']], [L['yellow'], t['yellow']], [L['red'], t['red']]], rtl, widths=[28, 18]))
    trip_rows = []
    for r in sorted(rows, key=lambda x: (x['date'], str(x.get('no')))):
        trip_rows.append([r.get('no'), dt.date.fromisoformat(r['date']), r['categoryName'], r['plate'], r['driverName'], r['requesterName'], r['departmentName'], ' - '.join(x for x in pax.get(r['id'], []) if x),
                          r.get('destination') or '', r.get('startKm'), r.get('endKm'), r['kmDone'] if r['kmKnown'] else None, r.get('billableKm'),
                          domain.parse_dt(r.get('startAt')), domain.parse_dt(r.get('endAt')), r['hours'], r['otHours'] or None, r.get('status'), trust.get(r['trust'], r['trust']),
                          '; '.join(why.get(c, c) for c in r['reasons']), r.get('source')])
    sheets.append(_sheet(L['trips'], [L[k] for k in ('no', 'date', 'category', 'plate', 'driver', 'requester', 'department', 'passengers', 'destination', 'start_km', 'end_km', 'km', 'billable',
                                                     'start', 'end', 'hours', 'ot', 'status', 'trust', 'reasons', 'source')], trip_rows, rtl,
                         kinds=[None, 'date', None, None, None, None, None, None, None, 'int', 'int', 'int', 'int', 'datetime', 'datetime', 'dec', 'dec', None, None, None, None]))
    for key, name in (('byVehicle', 'by_vehicle'), ('byDriver', 'by_driver'), ('byDepartment', 'by_dept'), ('byCategory', 'by_cat')):
        sheets.append(_sheet(L[name], [L['category'] if key == 'byCategory' else L[{'byVehicle': 'plate', 'byDriver': 'driver', 'byDepartment': 'department'}[key]], L['trips_n'], L['km'], L['avg'],
                                       L['hours'], L['ot'], L['green'], L['yellow'], L['red']],
                             [[a['label'], a['trips'], a['km'], a['avgKm'], a['hours'], a['ot'], a['green'], a['yellow'], a['red']] for a in sm[key]], rtl,
                             kinds=[None, 'int', 'int', 'dec', 'dec', 'dec', 'int', 'int', 'int']))
    ot_rows = [[d['driver'], x['date'], x['no'], x['plate'], x['hours']] for d in reports.overtime(state, ym) for x in d['days']]
    sheets.append(_sheet(L['overtime'], [L['driver'], L['date'], L['no'], L['plate'], L['ot']], ot_rows, rtl, kinds=[None, None, None, None, 'dec']))
    if money:
        rec = reports.reconciliation(state, ym)
        sheets.append(_sheet(L['recon'], [L['category'], L['vendor'], L['trips_n'], L['actual'], L['billed'], L['diff'], L['rate'], L['money']],
                             [[a['category'], a['vendor'], a['trips'], a['actualKm'], a['billedKm'], a['diffKm'], a['rate'], a['diffMoney']] for a in rec], rtl, kinds=[None, None, 'int', 'int', 'int', 'int', 'dec', 'dec']))
        sheets.append(_sheet(L['alloc'], [L['department'], L['trips_n'], L['km'], L['ot'], L['km_cost'], L['ot_cost'], L['total']],
                             [[a['department'], a['trips'], a['km'], a['ot'], a['kmCost'], a['otCost'], a['total']] for a in reports.allocation(state, ym)], rtl, kinds=[None, 'int', 'int', 'dec', 'dec', 'dec', 'dec']))
    sheets.append(_sheet(L['anom'], [L['level'], L['code'], L['no'], L['date'], L['plate'], L['driver'], L['destination'], L['km']],
                         [[a['level'], why.get(a['code'], a['code']), a['no'], a['date'], a['plate'], a['driver'], a['destination'], a['km']] for a in reports.anomalies(state, ym)], rtl, kinds=[None, None, None, None, None, None, None, 'int']))
    return w.build(sheets)
