"""Trip Orders - trip operations that need several records to change together (new trip, amendment, cancel, approval)
and the read-side "insights" (trust colour, km, overtime, odometer chain) for every trip.
Each operation is ONE store commit, so it is saved completely or not at all and appears as one change in the history."""
import datetime
import re
import uuid

import domain
import pricing
from store import BadRequest

CREATE_FIELDS = ('date', 'categoryId', 'vehicleId', 'driverId', 'requesterId', 'departmentId', 'destination', 'stops', 'purpose', 'notes', 'seq',
                 'billableKm')
# fields nobody may change by hand: identity, link secrets and things the driver's page or the server writes
PROTECTED = {'id', 'ver', 'no', 'reviewedBy', 'reviewedAt', 'linkHash', 'linkNonce', 'linkExpiry', 'oldLinks', 'source', 'importKey'}
DONE = domain.DONE


def new_id(prefix):
    return prefix + uuid.uuid4().hex[:14]


def my_letter(journal, node_id):
    """A, B, C... by the order in which PCs joined; a PC that is not in the list yet (a single PC) is A."""
    with journal.lock:
        ids = [r[0] for r in journal.conn.execute('SELECT id FROM nodes ORDER BY enrolled_at, id')]
    return domain.pc_letter(ids.index(node_id)) if node_id in ids else 'A'


def _row(store, entity, rid):
    with store.lock:
        table = store_entities()[entity][0]
        r = store.conn.execute(f'SELECT * FROM {table} WHERE id=? AND deleted=0', (rid,)).fetchone()
        return store._row_js(entity, r) if r else None


def store_entities():
    from store import ENTITIES
    return ENTITIES


def _now():
    return domain.business_now().isoformat(timespec='seconds')


STATUSES = ('draft', 'sent', 'started', 'finished', 'closed', 'cancelled')
DATE_WINDOW_DAYS = 60            # a trip date further than this from today is almost always a typing slip (2026-13-45, 1999, 2030)
MAX_KM = 9_999_999
TEXT_MAX = {'destination': 200, 'purpose': 300, 'routeText': 500, 'notes': 10000}


def _whole_number(field, v, top):
    if isinstance(v, bool):
        raise BadRequest(f'{field}: write a whole number')
    try:
        n = float(str(v).strip().replace(',', '')) if not isinstance(v, (int, float)) else float(v)
    except ValueError:
        raise BadRequest(f'{field}: write a whole number')
    if n != n or n in (float('inf'), float('-inf')) or n != int(n) or not 0 <= n <= top:
        raise BadRequest(f'{field}: write a whole number between 0 and {top:,}')
    return int(n)


def check_trip(row, before=None, today=None, trusted=False, window=True):
    """Refuse values that can never be true, for a new trip, a hand amendment and a plain save. Fills in clean numbers in `row`.
    `before` is the saved trip (None for a new one); only fields that CHANGED are judged, so an old record never blocks an unrelated edit.
    `trusted` / `window=False`: real history (Excel import, restore, a plain save of a list row) may be older than the date window; the date must still be a real date."""
    before = before or {}
    changed = lambda f: f in row and row.get(f) != before.get(f)
    if changed('date'):
        d = str(row['date'] or '').strip()
        try:
            day = datetime.date.fromisoformat(d) if len(d) == 10 else None
        except ValueError:
            day = None
        if day is None:
            raise BadRequest('date: write the date like 2026-10-12')
        today = today or domain.business_now().date()
        if window and not trusted and abs((day - today).days) > DATE_WINDOW_DAYS:
            raise BadRequest(f'date: more than {DATE_WINDOW_DAYS} days away from today - check the date')
        row['date'] = d
    for f in ('startKm', 'endKm'):
        if changed(f) and row[f] not in (None, ''):
            row[f] = _whole_number(f, row[f], MAX_KM)
    if changed('billableKm') and row['billableKm'] not in (None, ''):
        row['billableKm'] = _whole_number('billableKm', row['billableKm'], MAX_KM)
    if changed('seq') and row['seq'] not in (None, ''):
        row['seq'] = _whole_number('seq', row['seq'], 100000)
    if (changed('startKm') or changed('endKm')) and isinstance(row.get('startKm'), int) and isinstance(row.get('endKm'), int) and row['endKm'] < row['startKm']:
        raise BadRequest('endKm: the end odometer cannot be lower than the start odometer')
    for f in ('startAt', 'endAt'):
        if changed(f) and row[f] not in (None, ''):
            if domain.parse_dt(row[f]) is None:
                raise BadRequest(f'{f}: write the time like 2026-10-12T08:30')
    if (changed('startAt') or changed('endAt')) and row.get('startAt') and row.get('endAt'):
        a, b = domain.parse_dt(row['startAt']), domain.parse_dt(row['endAt'])
        if a and b and b < a:
            raise BadRequest('endAt: the end time cannot be before the start time')
    for f, top in TEXT_MAX.items():
        if changed(f) and len(str(row.get(f) or '')) > top:
            raise BadRequest(f'{f}: at most {top} characters')
    if changed('status'):
        new, old = row['status'], before.get('status') or 'draft'
        if new not in STATUSES:
            raise BadRequest('status: not a known status')
        if old == 'cancelled':
            raise BadRequest('A cancelled trip cannot be opened again - make a new trip')
        if old == 'closed' and new != 'cancelled':
            raise BadRequest('A closed trip can only be cancelled')
    return row


def create_trip(store, journal, node_id, user, ip, user_id, data, guard=None):
    """data: trip fields (CREATE_FIELDS) + 'passengers': [{'personId': .., 'freeText': ..}]. Returns the saved trip."""
    row = {k: data.get(k) for k in CREATE_FIELDS if data.get(k) not in (None, '')}
    if not row.get('categoryId'):
        raise BadRequest('Choose a trip category')
    if not _row(store, 'tripCategories', row['categoryId']):
        raise BadRequest('This trip category does not exist')
    for f, ent in (('vehicleId', 'vehicles'), ('driverId', 'drivers'), ('requesterId', 'people'), ('departmentId', 'departments')):
        if row.get(f) and not _row(store, ent, row[f]):
            raise BadRequest(f'Unknown {f[:-2]}')
    today = domain.business_now()
    row.setdefault('date', today.date().isoformat())
    check_trip(row, today=today.date())
    if not row.get('departmentId') and row.get('requesterId'):   # the requester's own department, still changeable
        row['departmentId'] = (_row(store, 'people', row['requesterId']) or {}).get('departmentId') or ''
        if not row['departmentId']:
            del row['departmentId']
    with store.lock:  # numbering and saving under one lock, so two clicks at once never get the same number
        nos = [r[0] for r in store.conn.execute('SELECT no FROM trips')]
        letter = my_letter(journal, node_id)
        year = int(str(row['date'])[:4]) if str(row['date'])[:4].isdigit() else today.year
        no = domain.trip_no(year, letter, domain.next_counter(nos, year, letter))
        tid = new_id('tr')
        row.update({'no': no, 'status': 'draft', 'source': 'app', 'locked': False, 'gaApproved': ''})
        ops = [{'e': 'trips', 'id': tid, 'op': 'put', 'row': row}]
        for p in (data.get('passengers') or [])[:12]:
            if not isinstance(p, dict) or not (p.get('personId') or str(p.get('freeText') or '').strip()):
                continue
            ops.append({'e': 'tripPassengers', 'id': new_id('tp'), 'op': 'put',
                        'row': {'tripId': tid, 'personId': p.get('personId') or '', 'freeText': str(p.get('freeText') or '').strip()[:120]}})
        store.commit(user, ip, f'New trip {no}', ops, guard=guard, user_id=user_id)
    return {'id': tid, 'no': no}


def amend(store, user, ip, user_id, trip_id, field, value, reason, guard=None):
    """Change a field of a trip that is locked (or any trip) and keep the old value: trip update + amendment record together."""
    reason = str(reason or '').strip()
    if len(reason) < 3:
        raise BadRequest('Write the reason for the change')
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if field in PROTECTED or field not in {f[0] for f in store_entities()['trips'][2]}:
        raise BadRequest('This field cannot be changed by hand')
    old = t.get(field)
    if old == value:
        raise BadRequest('Nothing changed')
    ver = t.pop('ver')
    new_row = check_trip({**t, field: value}, t)
    if field == 'status' and value in DONE:
        new_row['locked'] = True
    ops = [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': new_row},
           {'e': 'tripAmendments', 'id': new_id('am'), 'op': 'put',
            'row': {'tripId': trip_id, 'field': field, 'old': old, 'new': new_row[field], 'reason': reason[:400], 'by': user, 'at': _now()}}]
    store.commit(user, ip, f'Amend trip {t.get("no")}: {field}', ops, guard=guard, user_id=user_id)
    return {'ok': True}


def start_trip(store, user, ip, user_id, trip_id, guard=None):
    """The trip left: status "started" and the start time now (Cairo time) unless the office already wrote one."""
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') not in ('draft', 'sent'):
        raise BadRequest('Only a trip that has not left yet can be started')
    ver = t.pop('ver')
    row = {**t, 'status': 'started', 'startAt': t.get('startAt') or _now()}
    store.commit(user, ip, f'Started trip {t.get("no")}', [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': row}], guard=guard, user_id=user_id)
    return {'ok': True}


CLOSE_FIELDS = ('startKm', 'endKm', 'startAt', 'endAt')


def close_trip(store, user, ip, user_id, trip_id, data, guard=None):
    """The office writes the whole result of a trip in ONE step: both odometer readings, both times, and the trip is closed.
    Every changed value still gets its own amendment record (old value kept) with the same reason. The reason is only required when the
    trip was already closed before (then it is a correction); the first entry is plain data entry."""
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') == 'cancelled':
        raise BadRequest('A cancelled trip cannot be closed')
    reason = str(data.get('reason') or '').strip()
    if t.get('locked') and len(reason) < 3:
        raise BadRequest('Write the reason for the change')
    reason = reason or 'Entered at the office'
    ver = t.pop('ver')
    row = dict(t)
    for f in CLOSE_FIELDS:
        v = data.get(f)
        if v not in (None, ''):
            row[f] = str(v).strip() + (':00' if f.endswith('At') and len(str(v).strip()) == 16 else '')
    missing = [f for f in CLOSE_FIELDS if row.get(f) in (None, '')]
    if missing:
        raise BadRequest('Write both odometer readings and both times: ' + ', '.join(missing))
    row['status'], row['locked'] = 'closed', True
    check_trip(row, t)
    ops = [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': row}]
    at = _now()
    for f in (*CLOSE_FIELDS, 'status'):
        if row.get(f) != t.get(f):
            ops.append({'e': 'tripAmendments', 'id': new_id('am'), 'op': 'put',
                        'row': {'tripId': trip_id, 'field': f, 'old': t.get(f), 'new': row.get(f), 'reason': reason[:400], 'by': user, 'at': at}})
    if len(ops) == 1:
        raise BadRequest('Nothing changed')
    store.commit(user, ip, f'Closed trip {t.get("no")}', ops, guard=guard, user_id=user_id)
    return {'ok': True}


def cancel(store, user, ip, user_id, trip_id, reason, guard=None):
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') == 'cancelled':
        raise BadRequest('The trip is already cancelled')
    return amend(store, user, ip, user_id, trip_id, 'status', 'cancelled', reason, guard)


def approve(store, user, ip, user_id, trip_id, yes, guard=None):
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    ver = t.pop('ver')
    row = {**t, 'gaApproved': 'yes' if yes else 'no', 'gaBy': user, 'gaAt': _now()}
    store.commit(user, ip, f'GA {"approved" if yes else "declined"} trip {t.get("no")}', [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': row}],
                 guard=guard, user_id=user_id)
    return {'ok': True}


def review(store, user, ip, user_id, trip_id, guard=None):
    """"Reviewed": a person looked at a finished trip and accepts what the office entered. It clears the office-origin yellow marks
    that existed up to now (`domain.trust`); a later correction brings them back."""
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') not in DONE:
        raise BadRequest('Only a finished trip can be marked as reviewed')
    ver = t.pop('ver')
    store.commit(user, ip, f'Reviewed trip {t.get("no")}', [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': {**t, 'reviewedBy': user, 'reviewedAt': _now()}}],
                 guard=guard, user_id=user_id)
    return {'ok': True}


def make_link(store, gate, user, ip, user_id, trip_id, replace=False, sent=False, guard=None):
    """Give the trip its driver link (or a new one) and, when the dispatcher pressed "send", mark it sent.
    Only the hash of the link is saved; the link itself is made again from the link secret when needed."""
    import gateway_client as gwc
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') in ('cancelled', 'closed') or t.get('locked'):
        raise BadRequest('A link cannot be made for a trip that is finished or cancelled')
    if t.get('gaApproved') == 'no':
        raise BadRequest('General Affairs declined this trip - approve it again before sending a link')
    nonce = t.get('linkNonce') if t.get('linkNonce') and not replace else gwc.new_nonce()
    try:
        tok, url = gate.make_link(trip_id, nonce)
    except gwc.GatewayError as e:
        raise BadRequest(str(e))
    h = gwc.token_hash(tok)
    exp = domain.link_expiry(t.get('date'))
    ver = t.pop('ver')
    row = {**t, 'linkHash': h, 'linkNonce': nonce, 'linkExpiry': exp}
    if replace:
        row['boundDevice'] = ''
        old = t.get('linkHash')
        if old and old != h:        # the replaced link is remembered (its hash only) so every office PC can have it removed from the mailbox
            row['oldLinks'] = ([old] + [x for x in (t.get('oldLinks') or []) if x not in (old, h)])[:5]
    if sent and (row.get('status') or 'draft') == 'draft':
        row['status'] = 'sent'
    if row != t:
        store.commit(user, ip, f'Driver link for trip {t.get("no")}' + (' replaced' if replace else ''), [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': row}], guard=guard, user_id=user_id)
    if replace:
        gate.release.add(h)
    gate.kick()
    drv = _row(store, 'drivers', t.get('driverId')) if t.get('driverId') else None
    return {'url': url, 'no': t.get('no'), 'driver': (drv or {}).get('name', ''), 'mobile': (drv or {}).get('mobile', ''), 'status': row.get('status')}


def release_device(store, gate, user, ip, user_id, trip_id, guard=None):
    """The driver changed phone: let the next phone that opens the link become the bound one."""
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    ver = t.pop('ver')
    store.commit(user, ip, f'Released the phone of trip {t.get("no")}', [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': {**t, 'boundDevice': ''}}], guard=guard, user_id=user_id)
    if t.get('linkHash'):
        gate.release.add(t['linkHash'])
        gate.kick()
    return {'ok': True}


def insights(state, now=None, ot_threshold=12, drift_limit=10):
    """state: the dict from Store.state(). Returns {trip id: {...}} with trust colour, reasons, km, overtime and chain facts."""
    trips = state.get('trips', [])
    cats = {c['id']: c for c in state.get('tripCategories', [])}
    photos, amends, events = {}, {}, {}
    for key, bucket in (('tripPhotos', photos), ('tripAmendments', amends), ('tripEvents', events)):
        for r in state.get(key, []):
            bucket.setdefault(r.get('tripId'), []).append(r)
    by_car = {}
    for t in trips:
        if t.get('vehicleId') and t.get('status') != 'cancelled':
            by_car.setdefault(t['vehicleId'], []).append(t)
    chains = {}
    for lst in by_car.values():
        chains.update(domain.odometer_chain(lst))
    hist = {}
    for t in trips:
        k = domain.key_text(t.get('destination'))
        km = domain.km_of(t)
        if k and km and km > 0 and t.get('status') in DONE:
            hist.setdefault(k, []).append((t['id'], km))
    clash = {'vehicleId': {}, 'driverId': {}}                      # who shares a car or a driver at the same time
    for field in clash:
        groups = {}
        for t in trips:
            if t.get(field) and t.get('status') != 'cancelled':
                groups.setdefault(t[field], []).append(t)
        for g in groups.values():
            clash[field].update(domain.overlaps(g))
    day_hours = {}                                                  # hours one driver is on trips in one day
    for t in trips:
        dur = domain.duration(t.get('startAt'), t.get('endAt'))
        st = domain.parse_dt(t.get('startAt'))
        if dur and st and t.get('driverId') and t.get('status') != 'cancelled':
            key = (t['driverId'], st.date().isoformat())
            day_hours[key] = day_hours.get(key, 0) + domain.hours(dur)
    licences = {d['id']: str(d.get('licenseExpiry') or '')[:10] for d in state.get('drivers', [])}
    out = {}
    for t in trips:
        tid = t['id']
        k = domain.key_text(t.get('destination'))
        kms = [km for i, km in hist.get(k, []) if i != tid]
        dur = domain.duration(t.get('startAt'), t.get('endAt'))
        colour, reasons = domain.trust(t, photos.get(tid, []), amends.get(tid, []), events.get(tid, []), chains.get(tid), kms,
                                       open_limit_hours=(cats.get(t.get('categoryId')) or {}).get('openLimitHours') or 16, now=now, drift_limit=drift_limit)
        if t.get('status') != 'cancelled':
            extra = []
            if tid in clash['vehicleId']:
                extra.append('Y_CAR_OVERLAP')
            if tid in clash['driverId']:
                extra.append('Y_DRIVER_OVERLAP')
            st = domain.parse_dt(t.get('startAt'))
            if st and day_hours.get((t.get('driverId'), st.date().isoformat()), 0) > domain.DRIVER_DAY_LIMIT_HOURS:
                extra.append('Y_DRIVER_LONG_DAY')
            exp = licences.get(t.get('driverId'), '')
            if exp and str(t.get('date') or '')[:10] > exp:
                extra.append('Y_LICENCE_EXPIRED')
            reasons = reasons + [x for x in extra if x not in reasons]
            if extra and colour in (domain.GREEN,):
                colour = domain.YELLOW
        out[tid] = {'trust': colour, 'reasons': reasons, 'clashWith': {'vehicle': clash['vehicleId'].get(tid, []), 'driver': clash['driverId'].get(tid, [])}, 'km': domain.km_of(t), 'hours': domain.hours(dur) if dur else None,
                    'otHours': domain.hours(domain.overtime(dur, ot_threshold)) if dur else None, 'chain': chains.get(tid)}
    return out


# what a deleted record would leave orphaned: (trips column, label). Delete the trips first or switch the record off instead.
USED_BY_TRIPS = {'vehicles': ('vehicle_id', 'vehicle'), 'drivers': ('driver_id', 'driver'), 'tripCategories': ('category_id', 'category'),
                 'departments': ('department_id', 'department'), 'people': ('requester_id', 'person')}


def _refuse_delete_trip(store, rid):
    t = _row(store, 'trips', rid)
    if not t:
        return
    if t.get('locked') or t.get('reviewedBy') or (t.get('status') or 'draft') != 'draft':
        raise BadRequest('This trip cannot be deleted. Cancel it with a written reason instead.', 'err.closedNoDelete')


def _refuse_delete_in_use(store, entity, rid):
    if entity not in USED_BY_TRIPS:
        return
    col, label = USED_BY_TRIPS[entity]
    with store.lock:
        n = store.conn.execute(f'SELECT COUNT(*) FROM trips WHERE {col}=? AND deleted=0', (rid,)).fetchone()[0]
        if entity == 'people':
            n += store.conn.execute('SELECT COUNT(*) FROM trip_passengers WHERE person_id=? AND deleted=0', (rid,)).fetchone()[0]
        if entity == 'departments':     # an old trip with no department of its own is reported under its requester's department
            n += store.conn.execute("SELECT COUNT(*) FROM trips t JOIN people p ON p.id=t.requester_id AND p.deleted=0 WHERE t.deleted=0 "
                                    "AND (t.department_id IS NULL OR t.department_id='') AND p.department_id=?", (rid,)).fetchone()[0]
    if n:
        raise BadRequest(f'This {label} is used by {n} trip(s). Switch it off (not active) instead of deleting it, so old trips keep their {label}.')


NAME_MAX = 120
NAMED_LISTS = ('drivers', 'people', 'places', 'departments', 'tripCategories', 'routes')


def _check_list_row(store, entity, row, rid):
    """Master-data sanity: no money or hours below zero, and no second copy of a category, a department or the same person."""
    prev = _row(store, entity, rid) if entity in NAMED_LISTS and rid else None

    def changed(field):   # a row saved earlier keeps its old value when another field is edited (the form posts the whole row)
        return not prev or str(prev.get(field) or '') != str(row.get(field) or '')
    if entity in NAMED_LISTS and 'name' in row and changed('name'):
        name = domain.norm_text(row.get('name') or '')
        if not name:
            raise BadRequest('name: write the name')
        if len(name) > NAME_MAX:
            raise BadRequest(f'name: at most {NAME_MAX} characters')
    if entity in ('drivers', 'people') and row.get('mobile') and changed('mobile'):
        raw = domain.norm_text(str(row['mobile'])).translate(domain._AR_DIGITS)
        digits = ''.join(ch for ch in raw if ch.isdigit())
        if re.search(r'[^0-9+\-\s()./,]', raw) or not 8 <= len(digits) <= 32:
            raise BadRequest('mobile: write a phone number like 01012345678')
    if entity == 'drivers' and row.get('licenseExpiry') and changed('licenseExpiry'):
        v = str(row['licenseExpiry'])
        try:
            d = datetime.date.fromisoformat(v)
        except ValueError:
            raise BadRequest('licenseExpiry: write the date like 2026-10-12')
        if d.year < 2020 or d.year > 2100:
            raise BadRequest('licenseExpiry: this date is not possible - check it')
    if entity == 'tripCategories':
        for f in ('ratePerKm', 'ratePerOtHour', 'openLimitHours'):
            v = row.get(f)
            if v not in (None, ''):
                try:
                    ok = 0 <= float(v) <= 1_000_000
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    raise BadRequest(f'{f}: write a number that is not below zero')
    if entity in ('tripCategories', 'departments') and row.get('name'):
        table = store_entities()[entity][0]
        k = domain.key_text(row['name'])
        with store.lock:
            others = [r[0] for r in store.conn.execute(f'SELECT name FROM {table} WHERE deleted=0 AND id<>?', (rid,))]
        if any(domain.key_text(o) == k for o in others):
            raise BadRequest(f'Another {entity[:-1] if entity == "departments" else "category"} already has this name: "{row["name"]}"')
    if entity == 'people' and row.get('name'):
        k = domain.key_text(row['name'])
        with store.lock:
            others = store.conn.execute('SELECT department_id, mobile FROM people WHERE deleted=0 AND id<>? AND name_key=?', (rid, k)).fetchall()
        if any((o[0] or '') == (row.get('departmentId') or '') and (o[1] or '') == (row.get('mobile') or '') for o in others):
            raise BadRequest(f'This person is already in the list: "{row["name"]}" (same department and mobile)')


def normalize_ops(store, ops, trusted=False):
    """Clean names, plates and mobiles on the server (so every client and the Excel import agree) and refuse duplicates
    of things that must be unique: a plate, a driver, a place, a department. People may share a name."""
    if not isinstance(ops, list):
        return ops
    unique = {'vehicles': ('vehicles', 'plate_key', 'plateKey', 'plate'), 'drivers': ('drivers', 'name_key', 'nameKey', 'name'),
              'places': ('places', 'key', 'key', 'name')}
    for op in ops:
        if isinstance(op, dict) and op.get('op') == 'del' and not trusted and not op.get('resolve'):
            e = op.get('e')
            _refuse_delete_in_use(store, e, op.get('id'))
            if e == 'trips':
                _refuse_delete_trip(store, op.get('id'))
        if not isinstance(op, dict) or op.get('op') != 'put' or not isinstance(op.get('row'), dict):
            continue
        e, row = op.get('e'), op['row']
        if e == 'vehicles' and row.get('plate'):
            row['plate'], row['plateKey'] = domain.norm_plate(row['plate'])
        elif e in ('drivers', 'people') and row.get('name') is not None:
            row['name'] = domain.norm_text(row['name'])
            row['nameKey'] = domain.key_text(row['name'])
            if row.get('mobile'):
                row['mobile'] = domain.norm_mobile_eg(row['mobile'])[0]
        elif e == 'places' and row.get('name') is not None:
            row['name'] = domain.norm_text(row['name'])
            row['key'] = domain.key_text(row['name'])
        elif e in ('departments', 'tripCategories') and row.get('name') is not None:
            row['name'] = domain.norm_text(row['name'])
        elif e == 'trips':
            for f in ('destination', 'purpose', 'routeText'):
                if row.get(f) is not None:
                    row[f] = domain.norm_text(row[f])
            if not trusted:
                check_trip(row, _row(store, 'trips', op.get('id')), window=False)   # the window guards new trips and hand amendments
        if not trusted:
            _check_list_row(store, e, row, op.get('id'))
        if e == 'tripCategories' and not trusted:   # the rate history is kept by the server: an old rate is never rewritten by a save
            row['rateHistory'] = pricing.stamp(_row(store, 'tripCategories', op.get('id')), row, domain.business_now().date().isoformat())
        if e in unique and not op.get('resolve'):
            table, col, js, label = unique[e]
            if row.get(js):
                with store.lock:
                    other = store.conn.execute(f'SELECT id FROM {table} WHERE {col}=? AND deleted=0 AND id<>?', (row[js], op.get('id'))).fetchone()
                if other:
                    raise BadRequest(f'Another {e[:-1]} already has this {label}: "{row.get(label) or row[js]}"')
    return ops


# ---------------------------------------------------------------- the learning path (js/views/guides.js)
# What the person asking (and the office) already did, so the Help page can say "You are here" without anybody ticking
# boxes. Computed from the real rows every time (never stored), so it stays true after an import, a restore or on a second PC.
# Setup facts (categoriesAdded...) are about the office; every daily-work fact (my...) counts only the PERSON's own rows, so a
# new dispatcher still sees "make a trip order" as not done although the office has thousands. Per-person facts use the display name the rows carry ("created_by", "ga_by", amendments' "by", the history's "user").
GUIDE_FACTS = ('passwordChanged', 'categoriesAdded', 'vehiclesAdded', 'driversAdded', 'peopleAdded', 'placesAdded', 'staffAdded',
               'mailboxReady', 'backupFolder', 'myTripCreated', 'myLinkMade', 'myApproval', 'myAmendment', 'myTripClosed', 'myCancel',
               'myWordForm', 'myExcelExport', 'myImport')


def guide_facts(store, journal, user, must_change=False, users=1, backup_folders=0, mailbox=False):
    """{fact id: True/False} for the person asking. `user` is the display name the records carry."""
    def any_row(table, where='', args=()):
        with store.lock:
            return store.conn.execute(f'SELECT 1 FROM {table} WHERE deleted=0' + (' AND ' + where if where else '') + ' LIMIT 1',
                                      args).fetchone() is not None

    def logged(table, where, args):
        with journal.lock:
            return journal.conn.execute(f'SELECT 1 FROM {table} WHERE user=? AND {where} LIMIT 1', (user, *args)).fetchone() is not None

    journal.flush_activity()  # exports are written to the history in batches; the person's last one counts at once
    status_to = "field='status' AND by_user=? AND new_value IN (?, ?)"
    return {
        'passwordChanged': not must_change, 'categoriesAdded': any_row('trip_categories'), 'vehiclesAdded': any_row('vehicles'),
        'driversAdded': any_row('drivers'), 'peopleAdded': any_row('people'), 'placesAdded': any_row('places'), 'staffAdded': users > 1,
        'mailboxReady': bool(mailbox), 'backupFolder': backup_folders > 0,
        'myTripCreated': any_row('trips', "created_by=? AND source='app'", (user,)),
        'myLinkMade': logged('audit', 'label LIKE ?', ('Driver link for trip %',)),
        'myApproval': any_row('trips', 'ga_by=?', (user,)),
        'myAmendment': any_row('trip_amendments', "by_user=? AND field<>'status'", (user,)),
        'myTripClosed': any_row('trip_amendments', status_to, (user, '"closed"', 'closed')),
        'myCancel': any_row('trip_amendments', status_to, (user, '"cancelled"', 'cancelled')),
        'myWordForm': logged('activity', "type='export' AND action='Word export' AND target LIKE 'Trip_order_%'", ()),  # the form, not the month report
        'myExcelExport': logged('activity', "type='export' AND action='Excel export'", ()),
        'myImport': any_row('trips', "created_by=? AND source IN ('excel', 'word')", (user,))}
