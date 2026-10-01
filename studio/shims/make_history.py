"""Studio only: an invented September workbook in the owner's three-sheet layout (Arabic sample names, no real data),
written with the program's own writer. Loaded into the film's world through the program's normal Excel import."""
import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'server'))
import excel_io  # noqa: E402
import xlsx_write as w  # noqa: E402

rnd = random.Random(2026)
DRIVERS = ['كريم فؤاد', 'حسام نبيل', 'وليد شاكر', 'إيهاب رمزي', 'طارق منير']
CARS = ['ن ج ع 4821', 'س ط ر 1937', 'م ل ك 5520', 'ه د ب 7045']
PEOPLE = [('منى سامي', 'المشتريات'), ('أحمد ربيع', 'المالية'), ('ريهام فتحي', 'الموارد البشرية'), ('ياسر عادل', 'الصيانة'), ('دينا حسن', 'المبيعات')]
ROUTES = [('المصنع - المطار - المصنع', 118), ('المصنع - البنك - المصنع', 34), ('المصنع - الميناء - المصنع', 212), ('المصنع - المستودع - المصنع', 46),
          ('المصنع - المكتب الرئيسي - المصنع', 72)]
odo = {c: 47200 + i * 9100 for i, c in enumerate(CARS)}
rows = []
last_end = {}
for day in range(0, 35):                       # 1 September .. 5 October (the studio day is 6 October)
    d = dt.date(2026, 9, 1) + dt.timedelta(days=day)
    if d.weekday() in (4,):          # Friday off
        continue
    day_trips = []
    for _ in range(rnd.randint(2, 4)):
        car = rnd.choice(CARS[:3])
        route, km = rnd.choice(ROUTES)
        km += rnd.randint(-6, 6)
        req, dep = rnd.choice(PEOPLE)
        st = dt.time(rnd.randint(7, 12), rnd.choice([0, 10, 20, 30, 40, 50]))
        day_trips.append((st, car, route, km, req, dep))
    busy = {}
    for st, car, route, km, req, dep in sorted(day_trips):     # odometers follow the order of the day, like a real car
        start = dt.datetime.combine(d, st)
        if busy.get(car) and start < busy[car]:
            start = busy[car] + dt.timedelta(minutes=20)
        en_dt = start + dt.timedelta(minutes=int(km * 1.4) + rnd.randint(20, 90))
        busy[car] = en_dt
        s, e = odo[car], odo[car] + km
        odo[car] = e + rnd.randint(0, 3)
        last_end[car] = e
        rows.append([d, rnd.choice(DRIVERS), car, req, req, 'سيارات الإدارة', dep, route, None, s, e, None, None, start.time(), en_dt.time(), None])
data = [excel_io.TODAY_HEADERS]
for i, r in enumerate(rows, 2):
    r[11] = w.Formula(f'+K{i}-J{i}', r[10] - r[9])
    data.append(r)
out = sys.argv[1]
with open(out, 'wb') as f:
    f.write(w.build([w.Sheet('All Car', data)]))
print(out, len(rows))
for car in CARS:
    print('ODO', car, last_end.get(car, odo[car]))
