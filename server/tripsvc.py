"""Trip Orders - trip operations that need several records to change together (new trip, amendment, cancel, approval)
and the read-side "insights" (trust colour, km, overtime, odometer chain) for every trip.
Each operation is ONE store commit, so it is saved completely or not at all and appears as one change in the history."""
import uuid
from datetime import datetime, timedelta

import domain
import pricing
from store import BadRequest

CREATE_FIELDS = ('date', 'categoryId', 'vehicleId', 'driverId', 'requesterId', 'departmentId', 'destination', 'stops', 'purpose', 'notes', 'seq',
                 'billableKm')
# fields nobody may change by hand: identity, link secrets and things the driver's page or the server writes
PROTECTED = {'id', 'ver', 'no', 'linkHash', 'linkNonce', 'linkExpiry', 'oldLinks', 'source', 'importKey'}
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
    return datetime.now().isoformat(timespec='seconds')


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
    today = datetime.now()
    row.setdefault('date', today.date().isoformat())
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
    new_row = {**t, field: value}
    if field == 'status' and value in DONE:
        new_row['locked'] = True
    ops = [{'e': 'trips', 'id': trip_id, 'op': 'put', 'ver': ver, 'row': new_row},
           {'e': 'tripAmendments', 'id': new_id('am'), 'op': 'put',
            'row': {'tripId': trip_id, 'field': field, 'old': old, 'new': value, 'reason': reason[:400], 'by': user, 'at': _now()}}]
    store.commit(user, ip, f'Amend trip {t.get("no")}: {field}', ops, guard=guard, user_id=user_id)
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


def make_link(store, gate, user, ip, user_id, trip_id, replace=False, sent=False, guard=None):
    """Give the trip its driver link (or a new one) and, when the dispatcher pressed "send", mark it sent.
    Only the hash of the link is saved; the link itself is made again from the link secret when needed."""
    import gateway_client as gwc
    t = _row(store, 'trips', trip_id)
    if not t:
        raise BadRequest('Trip not found')
    if t.get('status') in ('cancelled', 'closed') or t.get('locked'):
        raise BadRequest('A link cannot be made for a trip that is finished or cancelled')
    nonce = t.get('linkNonce') if t.get('linkNonce') and not replace else gwc.new_nonce()
    try:
        tok, url = gate.make_link(trip_id, nonce)
    except gwc.GatewayError as e:
        raise BadRequest(str(e))
    h = gwc.token_hash(tok)
    exp = max(datetime.now() + timedelta(days=7), (domain.parse_dt(t.get('date')) or datetime.now()) + timedelta(days=3)).isoformat(timespec='seconds')
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
    out = {}
    for t in trips:
        tid = t['id']
        k = domain.key_text(t.get('destination'))
        kms = [km for i, km in hist.get(k, []) if i != tid]
        dur = domain.duration(t.get('startAt'), t.get('endAt'))
        colour, reasons = domain.trust(t, photos.get(tid, []), amends.get(tid, []), events.get(tid, []), chains.get(tid), kms,
                                       open_limit_hours=(cats.get(t.get('categoryId')) or {}).get('openLimitHours') or 16, now=now, drift_limit=drift_limit)
        out[tid] = {'trust': colour, 'reasons': reasons, 'km': domain.km_of(t), 'hours': domain.hours(dur) if dur else None,
                    'otHours': domain.hours(domain.overtime(dur, ot_threshold)) if dur else None, 'chain': chains.get(tid)}
    return out


def normalize_ops(store, ops, trusted=False):
    """Clean names, plates and mobiles on the server (so every client and the Excel import agree) and refuse duplicates
    of things that must be unique: a plate, a driver, a place, a department. People may share a name."""
    if not isinstance(ops, list):
        return ops
    unique = {'vehicles': ('vehicles', 'plate_key', 'plateKey', 'plate'), 'drivers': ('drivers', 'name_key', 'nameKey', 'name'),
              'places': ('places', 'key', 'key', 'name')}
    for op in ops:
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
        if e == 'tripCategories' and not trusted:   # the rate history is kept by the server: an old rate is never rewritten by a save
            row['rateHistory'] = pricing.stamp(_row(store, 'tripCategories', op.get('id')), row, datetime.now().date().isoformat())
        if e in unique and not op.get('resolve'):
            table, col, js, label = unique[e]
            if row.get(js):
                with store.lock:
                    other = store.conn.execute(f'SELECT id FROM {table} WHERE {col}=? AND deleted=0 AND id<>?', (row[js], op.get('id'))).fetchone()
                if other:
                    raise BadRequest(f'Another {e[:-1]} already has this {label}: "{row.get(label) or row[js]}"')
    return ops
