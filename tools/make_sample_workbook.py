"""Writes a SYNTHETIC monthly workbook with the same structure and statistical shape as a real month (fake names and plates):
232 trips on the working days of a month, 11 SUV and 4 microbus trips, empty Start/End in "All Car", odometer back-steps
(one of about 31,000 km), billable km that differ from the odometer, missing plates/km, spelling variants of places and
drivers. Used by the tests and by "Try with the sample" - the owner's real workbook never goes into the repository.

    python tools/make_sample_workbook.py [output.xlsx] [--seed 26]
"""
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import excel_io as X  # noqa: E402
import xlsx_write as w  # noqa: E402

FIRST = ['Omar', 'Khaled', 'Hany', 'Tarek', 'Sameh', 'Adel', 'Wael', 'Ragab', 'Essam', 'Nabil', 'Fathy', 'Gamal', 'Hazem', 'Ibrahim', 'Karim', 'Magdy', 'Nader', 'Reda', 'Saeed', 'Yehia']
LAST = ['Hassan', 'Farouk', 'Mansour', 'Salem', 'Nasr', 'Fahmy', 'Zaki', 'Badawy', 'Helmy', 'Ashour', 'Lotfy', 'Kamel', 'Shaker', 'Tawfik']
DEPTS = ['HR', 'Finance', 'PE', 'MI', 'CS', 'Legal', 'Injection', 'MRO', 'GA', 'LCM', 'ER', 'QA', 'IT', 'SCM', 'EHS', 'PD', 'MX', 'SMT', 'Warehouse', 'Admin']
STOPS = ['SEEG', 'BNS', 'Badr city', 'Nasr city', 'OCT', 'Giza', 'Elbassel', 'Wasta', 'Fayoum', 'Airport', 'Masr Elgdida', 'Maadi', 'Zaid', 'Haram', 'Museum', 'Crown']
LETTERS = 'أبجدرسصطعفقكلمنهوي'


def names(rnd, n):
    out = set()
    while len(out) < n:
        out.add(f'{rnd.choice(FIRST)} {rnd.choice(LAST)}')
    return sorted(out)


def plate(rnd):
    return ' '.join(rnd.sample(LETTERS, 3)) + f' {rnd.randint(1000, 9999)}'


def build(seed=26, year=2026, month=9):
    rnd = random.Random(seed)
    drivers, cars, requesters = names(rnd, 41), sorted({plate(rnd) for _ in range(44)}), names(rnd, 54)
    depts = DEPTS
    days = [dt.date(year, month, d) for d in range(1, 29) if dt.date(year, month, d).weekday() != 4][:25]
    odo = {c: rnd.randint(30_000, 330_000) for c in cars}
    routes = []
    for _ in range(80):
        routes.append('-'.join(rnd.sample(STOPS[1:], rnd.randint(1, 3)) and ['SEEG'] + rnd.sample(STOPS[1:], rnd.randint(1, 3)) + ['SEEG']))
    routes += ['SEEG-BNS-SEEG'] * 12 + ['SEEG-Badr city-SEEG'] * 9 + ['SEEG-Museum-SEEG', 'SEEG-Musiem-SEEG', 'SEEG-museum-SEEG']
    rows, expected_back = [], 0
    n_trips = 232
    per_day = [n_trips // len(days) + (1 if i < n_trips % len(days) else 0) for i in range(len(days))]
    seq = 0
    for day, cnt in zip(days, per_day):
        used_cars = rnd.sample(cars, min(cnt, len(cars)))
        for k in range(cnt):
            car = used_cars[k % len(used_cars)]
            cat = 'Manager car' if rnd.random() < 0.61 else 'Extra'
            drv = rnd.choice(drivers) if rnd.random() > 0.05 else '  ' + rnd.choice(drivers) + ' '
            req = rnd.choice(requesters)
            emp = req if cat == 'Manager car' else rnd.choice(['Visitor', 'Early leave', rnd.choice(requesters), f'{rnd.choice(requesters)} - {rnd.choice(requesters)}'])
            km = rnd.choice([120, 204, 210, 234, 253, 262, 420, 468]) + rnd.randint(-8, 8)
            start = odo[car] + rnd.choice([0, 0, 0, 10, 50])
            odo[car] = start + km
            seq_v = None
            if cat == 'Extra':
                seq = seq % 7 + 1
                seq_v = seq
            rows.append({'date': day, 'driver': drv, 'plate': car, 'requester': req, 'employee': emp, 'category': cat, 'department': rnd.choice(depts),
                         'destination': rnd.choice(routes), 'seq': seq_v, 'start': start, 'end': start + km,
                         'billable': (start + km - start) + (rnd.choice([32, -41, 30, -40, 21, -32]) if rnd.random() < 0.25 else 0)})
    # the faults of the real month
    for i in rnd.sample(range(30, 200), 11):
        rows[i]['start'] -= rnd.randint(2, 300)
        rows[i]['end'] = rows[i]['start'] + (rows[i]['end'] - rows[i]['start'])
    for i, d in ((5, 'SEEG-Museum-SEEG'), (6, 'SEEG-Musiem-SEEG'), (7, 'SEEG-Museum-SEEG'), (8, 'SEEG-Mueiem-SEEG')):   # one place, several spellings
        rows[i]['destination'] = d
    rows[150]['start'] -= 31_000                      # the ~31,000 km typing mistake
    for i in rnd.sample(range(0, 232), 8):
        rows[i]['start'] = rows[i]['end'] = rows[i]['billable'] = None
    for i in rnd.sample(range(0, 232), 7):
        rows[i]['plate'] = None
    rows[12]['plate'] = ' ' + (rows[12]['plate'] or cars[0])       # a plate with a leading space
    all_rows = [list(X.TODAY_HEADERS)]
    for i, r in enumerate(rows, start=2):
        km = (r['end'] - r['start']) if r['start'] is not None and r['end'] is not None else 0
        all_rows.append([r['date'], r['driver'], r['plate'], r['requester'], r['employee'], r['category'], r['department'], r['destination'], r['seq'],
                         r['start'], r['end'], w.Formula('+Table1[[#This Row],[End KM]]-Table1[[#This Row],[Strat KM]]', km), r['billable'], None, None,
                         w.S(w.Formula(f'IF(O{i}-N{i}>TIME(12,0,0),O{i}-N{i}-TIME(12,0,0),0)', 0.0), 'time')])
    t1 = w.Table('Table1', f'A1:P{len(all_rows)}', X.TODAY_HEADERS, formulas={' KM': '+Table1[[#This Row],[End KM]]-Table1[[#This Row],[Strat KM]]', 'OT Hours': 'IF(O2-N2>TIME(12,0,0),O2-N2-TIME(12,0,0),0)'})
    sheets = [w.Sheet(X.SHEET_ALL, all_rows, widths=X.WIDTHS_ALL, tables=[t1], freeze=(1, 0), grid=False)]
    # SUV rent: 11 trips of one car, with times
    head15 = [h for h in X.TODAY_HEADERS if h != 'Column1']
    suv_car, suv_drv, o = plate(rnd), rnd.choice(drivers), 65_000
    suv = [list(head15)]
    for i in range(11):
        km = rnd.choice([100, 150, 275, 300, 315]) ; day = dt.date(year, month, [1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24][i])
        s_t, e_t = (dt.time(6, 30), dt.time(19, 30)) if i % 3 == 0 else (dt.time(7, 0), dt.time(22, 0)) if i % 3 == 1 else (None, None)
        r = i + 2
        ot = ((e_t.hour - s_t.hour) * 60 + e_t.minute - s_t.minute) / 1440 - 0.5 if s_t and (e_t.hour - s_t.hour) * 60 + e_t.minute - s_t.minute > 720 else 0
        suv.append([day, suv_drv, suv_car, 'Jackie' if i < 10 else 'Sherif', rnd.choice(['EHS Audit', 'Visitor', 'Min Kim']), 'SUV Rent', rnd.choice(['EHS', 'Finance', 'Production']),
                    rnd.choice(['Ramsis-SEEG-Maadi-Ramsis', 'Giza-Crown-SEEG-Giza']), o, o + km, w.Formula(f'+J{r}-I{r}', km), km + rnd.randint(-10, 30), s_t, e_t,
                    w.S(w.Formula(f'IF(N{r}-M{r}>TIME(12,0,0),N{r}-M{r}-TIME(12,0,0),0)', ot), 'time')])
        o += km + 50
    suv.append([None] * 8 + [w.S('TTL', 'total_text'), None, w.S(w.Formula('+SUM(K2:K12)', 0), 'total_int')])
    sheets.append(w.Sheet(X.SHEET_SUV, suv, widths=X.WIDTHS_ALL[:8] + X.WIDTHS_ALL[9:], freeze=(1, 0), grid=False, autofilter='A1:O13'))
    bus = [['#'] + head15]
    bus_car, o = plate(rnd), 115_000
    for i, (d, drv) in enumerate([(9, 'A'), (10, 'A'), (10, 'B'), (15, 'A')], start=2):
        km = rnd.choice([75, 200, 95]); 
        bus.append([w.Formula('+ROW()-1', i - 1), dt.date(year, month, d), rnd.choice(drivers), bus_car, 'Jackie', 'EHS Audit', 'Microbus Rent', 'EHS', 'Giza-Crown-Airport-Giza', o, o + km,
                    w.Formula('+Table2[[#This Row],[End KM]]-Table2[[#This Row],[Strat KM]]', km), km + 40, None, None, w.S(w.Formula(f'IF(O{i}-N{i}>TIME(12,0,0),O{i}-N{i}-TIME(12,0,0),0)', 0.0), 'time')])
        o += km + 25
    bus.append([None] * 9 + [w.S('TTL', 'total_text'), None, w.S(w.Formula('SUBTOTAL(109,Table2[[ KM]])', 0), 'total_int')])
    t2 = w.Table('Table2', 'A1:P5', ['#'] + head15, formulas={'#': '+ROW()-1'})
    sheets.append(w.Sheet(X.SHEET_BUS, bus, widths=[5] + X.WIDTHS_ALL[:8] + X.WIDTHS_ALL[9:], tables=[t2], freeze=(2, 0), grid=False))
    return w.build(sheets), {'seed': seed, 'all_car': 232, 'suv': 11, 'microbus': 4}


if __name__ == '__main__':
    out = next((a for a in sys.argv[1:] if not a.startswith('-') and a != '26'), os.path.join('tests', 'fixtures', 'sample_sep26_synthetic.xlsx'))
    seed = int(sys.argv[sys.argv.index('--seed') + 1]) if '--seed' in sys.argv else 26
    data, facts = build(seed)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'wb') as f:
        f.write(data)
    print(json.dumps(facts))
