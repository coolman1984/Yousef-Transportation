"""Trip Orders - numbers for finance and management, computed from the state of the database.

Everything works on one month (ym = "2026-09") or on all trips (ym = ""): summaries per vehicle, driver, department,
requester and category; overtime per driver and day; vendor reconciliation (kilometres by the odometer against the
kilometres the vendor bills); cost allocation to departments; anomalies. The same functions feed the Reports page,
the presentation mode, the clean Excel export and the Word report, so all of them show the same numbers.
"""
import domain
import pricing
import tripsvc

CANCELLED = 'cancelled'


def month_of(state, ym):
    return [t for t in state.get('trips', []) if (not ym or str(t.get('date', ''))[:7] == ym) and t.get('status') != CANCELLED]


def _names(state):
    return {'veh': {v['id']: v for v in state.get('vehicles', [])}, 'drv': {d['id']: d for d in state.get('drivers', [])},
            'ppl': {p['id']: p for p in state.get('people', [])}, 'dep': {d['id']: d for d in state.get('departments', [])},
            'cat': {c['id']: c for c in state.get('tripCategories', [])}}


def enrich(state, ym='', ot_threshold=12):
    """Every trip of the month with its derived numbers and names."""
    n = _names(state)
    ins = tripsvc.insights(state, ot_threshold=ot_threshold)
    out = []
    for t in month_of(state, ym):
        i = ins.get(t['id'], {})
        km = i.get('km')
        dur = domain.duration(t.get('startAt'), t.get('endAt'))
        cat = n['cat'].get(t.get('categoryId')) or {}
        rate_km, rate_ot = pricing.rates_on(cat, t.get('date'))          # the rates valid on the day of the trip, not today's
        out.append({**t, 'plate': (n['veh'].get(t.get('vehicleId')) or {}).get('plate', ''), 'driverName': (n['drv'].get(t.get('driverId')) or {}).get('name', ''),
                    'requesterName': (n['ppl'].get(t.get('requesterId')) or {}).get('name', ''), 'departmentName': (n['dep'].get(t.get('departmentId')) or {}).get('name', ''),
                    'categoryName': cat.get('name', ''), 'vendor': cat.get('vendor') or (n['veh'].get(t.get('vehicleId')) or {}).get('vendor') or '',
                    'kmDone': km if km is not None and km > 0 else 0, 'kmKnown': km is not None, 'hours': domain.hours(dur) if dur else None,
                    'otHours': i.get('otHours') or 0.0, 'trust': i.get('trust', 'grey'), 'reasons': i.get('reasons', []),
                    'rateKm': rate_km, 'rateOt': rate_ot})
    return out


def _group(rows, keyf, labelf=None):
    g = {}
    for r in rows:
        k = keyf(r)
        a = g.setdefault(k, {'key': k, 'label': (labelf or (lambda x: k))(r), 'trips': 0, 'km': 0, 'hours': 0.0, 'ot': 0.0, 'green': 0, 'yellow': 0, 'red': 0, 'grey': 0})
        a['trips'] += 1
        a['km'] += r['kmDone']
        a['hours'] = round(a['hours'] + (r['hours'] or 0), 2)
        a['ot'] = round(a['ot'] + r['otHours'], 2)
        a[r['trust']] = a.get(r['trust'], 0) + 1
    out = sorted(g.values(), key=lambda a: (-a['km'], str(a['label'])))
    for a in out:
        a['avgKm'] = round(a['km'] / a['trips'], 1) if a['trips'] else 0
    return out


def summaries(state, ym=''):
    rows = enrich(state, ym)
    total = {'trips': len(rows), 'km': sum(r['kmDone'] for r in rows), 'hours': round(sum(r['hours'] or 0 for r in rows), 2), 'ot': round(sum(r['otHours'] for r in rows), 2),
             'green': sum(r['trust'] == 'green' for r in rows), 'yellow': sum(r['trust'] == 'yellow' for r in rows), 'red': sum(r['trust'] == 'red' for r in rows),
             'days': len({r['date'] for r in rows}), 'drivers': len({r['driverId'] for r in rows if r.get('driverId')}), 'vehicles': len({r['vehicleId'] for r in rows if r.get('vehicleId')})}
    return {'ym': ym, 'total': total,
            'byVehicle': _group(rows, lambda r: r.get('vehicleId') or '-', lambda r: r['plate'] or '-'),
            'byDriver': _group(rows, lambda r: r.get('driverId') or '-', lambda r: r['driverName'] or '-'),
            'byDepartment': _group(rows, lambda r: r.get('departmentId') or '-', lambda r: r['departmentName'] or '-'),
            'byRequester': _group(rows, lambda r: r.get('requesterId') or '-', lambda r: r['requesterName'] or '-'),
            'byCategory': _group(rows, lambda r: r.get('categoryId') or '-', lambda r: r['categoryName'] or '-'),
            'byDay': sorted(_group(rows, lambda r: r['date'], lambda r: r['date']), key=lambda a: a['key']),
            'topRoutes': _routes(rows)}


def _routes(rows, n=10):
    g = {}
    for r in rows:
        k = domain.key_text(r.get('destination'))
        if k:
            a = g.setdefault(k, {'label': r['destination'], 'trips': 0, 'km': 0})
            a['trips'] += 1
            a['km'] += r['kmDone']
    return sorted(g.values(), key=lambda a: -a['trips'])[:n]


def overtime(state, ym=''):
    """Overtime per driver and day (only trips with start and end times)."""
    rows = [r for r in enrich(state, ym) if r['otHours']]
    per = {}
    for r in rows:
        d = per.setdefault(r.get('driverId') or '-', {'driver': r['driverName'] or '-', 'total': 0.0, 'days': []})
        d['total'] = round(d['total'] + r['otHours'], 2)
        d['days'].append({'date': r['date'], 'no': r.get('no'), 'hours': r['otHours'], 'plate': r['plate']})
    return sorted(per.values(), key=lambda d: -d['total'])


def reconciliation(state, ym=''):
    """Kilometres by the odometer against the kilometres the vendor bills ("Misr car KM"), per category/vendor, with the money difference."""
    rows = [r for r in enrich(state, ym) if r.get('billableKm') is not None]
    g = {}
    for r in rows:
        key = (r['categoryName'], r['vendor'])
        a = g.setdefault(key, {'category': r['categoryName'], 'vendor': r['vendor'], 'trips': 0, 'actualKm': 0, 'billedKm': 0, 'rate': r['rateKm'], 'diffMoney': 0.0, 'lines': []})
        a['trips'] += 1
        a['rate'] = r['rateKm']             # the latest rate of the month; the money below is added up trip by trip with each trip's own rate
        a['diffMoney'] += (r['billableKm'] - r['kmDone']) * r['rateKm']
        a['actualKm'] += r['kmDone']
        a['billedKm'] += r['billableKm']
        if r['billableKm'] != r['kmDone']:
            a['lines'].append({'date': r['date'], 'no': r.get('no'), 'plate': r['plate'], 'actual': r['kmDone'], 'billed': r['billableKm'], 'diff': r['billableKm'] - r['kmDone']})
    out = []
    for a in g.values():
        a['diffKm'] = a['billedKm'] - a['actualKm']
        a['diffMoney'] = round(a['diffMoney'], 2)
        a['lines'].sort(key=lambda x: -abs(x['diff']))
        out.append(a)
    return sorted(out, key=lambda a: -abs(a['diffKm']))


def allocation(state, ym=''):
    """Cost per department: km x rate + overtime x rate (rates are set per trip category)."""
    g = {}
    for r in enrich(state, ym):
        a = g.setdefault(r.get('departmentId') or '-', {'department': r['departmentName'] or '-', 'trips': 0, 'km': 0, 'ot': 0.0, 'kmCost': 0.0, 'otCost': 0.0})
        a['trips'] += 1
        a['km'] += r['kmDone']
        a['ot'] = round(a['ot'] + r['otHours'], 2)
        a['kmCost'] += r['kmDone'] * r['rateKm']
        a['otCost'] += r['otHours'] * r['rateOt']
    out = []
    for a in g.values():
        a['kmCost'], a['otCost'] = round(a['kmCost'], 2), round(a['otCost'], 2)
        a['total'] = round(a['kmCost'] + a['otCost'], 2)
        out.append(a)
    return sorted(out, key=lambda a: -a['total'])


def anomalies(state, ym=''):
    """Everything worth a look, one line each: [{'code','level','no','date','plate','driver','text_key','detail'}]"""
    out = []
    for r in enrich(state, ym):
        for code in r['reasons']:
            out.append({'code': code, 'level': 'bad' if code.startswith('R_') else 'warn', 'no': r.get('no'), 'date': r['date'], 'plate': r['plate'], 'driver': r['driverName'],
                        'destination': r.get('destination') or '', 'km': r['kmDone']})
        if r['status'] in ('finished', 'closed') and not r['kmKnown']:
            out.append({'code': 'NO_KM', 'level': 'warn', 'no': r.get('no'), 'date': r['date'], 'plate': r['plate'], 'driver': r['driverName'], 'destination': r.get('destination') or '', 'km': 0})
        if r['status'] in ('finished', 'closed') and r['hours'] is None and r.get('source') == 'app':
            out.append({'code': 'NO_TIMES', 'level': 'warn', 'no': r.get('no'), 'date': r['date'], 'plate': r['plate'], 'driver': r['driverName'], 'destination': r.get('destination') or '', 'km': r['kmDone']})
    order = {'bad': 0, 'warn': 1}
    return sorted(out, key=lambda a: (order[a['level']], a['date'], str(a['no'])))
