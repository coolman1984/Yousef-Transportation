"""Demo mode: the program opens without signing in and a new data folder starts with sample data on every page,
so a person can learn with examples (owner request, 17 October 2026).

Everything here is made up: fake names, fake plates, fake phone numbers. The sample trips are written through the same
service functions as a real dispatcher's clicks (tripsvc), so they carry history, amendments and trip numbers like real ones.
"""
import contextlib
import datetime
import random
import secrets

import domain
import tripsvc

USERNAME = 'admin'
FULL_NAME = 'مدير المكتب'
IP = '127.0.0.1'


def ensure_user(auth, node):
    """The one built-in administrator every request works as. Created once, on a PC that is not a member of another PC."""
    if auth.has_users() or node.role == 'member':
        return
    # nobody types this password: demo mode never asks for one
    auth.setup(USERNAME, FULL_NAME, 'Demo-' + secrets.token_urlsafe(18) + '-7', IP)


def user(auth):
    """The built-in administrator, or None (another PC's accounts, or it was disabled)."""
    with auth.lock:
        r = auth.conn.execute('SELECT id FROM users WHERE username=? AND deleted=0', (USERNAME,)).fetchone()
    u = auth.get(r[0]) if r else None
    return u if u and u['active'] and (u.get('status') or 'approved') == 'approved' and 'users.manage' in u['perms'] else None


CATEGORIES = [  # id, name, Arabic name, Excel sheet, daily sequence, rate per km, rate per overtime hour, vendor
    ('dc-manager', 'Manager car', 'سيارة مدير', 'All Car', False, 6.5, 45, 'شركة الأمل للتأجير'),
    ('dc-extra', 'Extra', 'رحلة إضافية', 'All Car', True, 6.5, 45, 'شركة الأمل للتأجير'),
    ('dc-suv', 'SUV', 'سيارة دفع رباعي', 'SUV Rent', False, 9, 60, 'شركة النور للنقل'),
    ('dc-bus', 'Microbus', 'ميكروباص', 'Microbus Rent', False, 8, 55, 'شركة النور للنقل'),
]
VEHICLES = [  # id, plate, type, category, ownership, vendor, baseline odometer
    ('dv-1', 'أ ب ج 1234', 'Sedan', 'dc-manager', 'rented', 'شركة الأمل للتأجير', 85210),
    ('dv-2', 'س ص ط 5821', 'Sedan', 'dc-manager', 'rented', 'شركة الأمل للتأجير', 141300),
    ('dv-3', 'ن ه و 3307', 'Sedan', 'dc-extra', 'rented', 'شركة الأمل للتأجير', 63050),
    ('dv-4', 'ر ع ف 7740', 'Sedan', 'dc-extra', 'owned', '', 210400),
    ('dv-5', 'ق ك ل 9012', 'SUV', 'dc-suv', 'rented', 'شركة النور للنقل', 38900),
    ('dv-6', 'م ن ي 4468', 'Microbus', 'dc-bus', 'rented', 'شركة النور للنقل', 176020),
    ('dv-7', 'د ر س 2290', 'Microbus', 'dc-bus', 'owned', '', 99500),
]
DRIVERS = [  # id, name, mobile, vendor, licence number, days until the licence ends (negative = already ended)
    ('dd-1', 'أحمد سمير', '01001234567', 'شركة الأمل للتأجير', 'DL-55120', 400),
    ('dd-2', 'محمود عادل', '01112345678', 'شركة الأمل للتأجير', 'DL-55121', 220),
    ('dd-3', 'حسن فتحي', '01223456789', 'شركة الأمل للتأجير', 'DL-55122', 18),
    ('dd-4', 'مصطفى نبيل', '01534567890', 'شركة النور للنقل', 'DL-55123', 610),
    ('dd-5', 'كريم لطفي', '01045678901', 'شركة النور للنقل', 'DL-55124', -6),
    ('dd-6', 'سيد رجب', '01156789012', '', 'DL-55125', 300),
]
DEPARTMENTS = [('dp-hr', 'الموارد البشرية', 'HR'), ('dp-fin', 'المالية', 'FIN'), ('dp-it', 'تكنولوجيا المعلومات', 'IT'),
               ('dp-qa', 'الجودة', 'QA'), ('dp-wh', 'المخازن', 'WH'), ('dp-ga', 'الشؤون الإدارية', 'GA')]
PEOPLE = [  # id, name, department, requester, passenger
    ('ds-1', 'عمر حسن', 'dp-hr', True, True), ('ds-2', 'نور سالم', 'dp-fin', True, True),
    ('ds-3', 'طارق منصور', 'dp-it', True, True), ('ds-4', 'منى فاروق', 'dp-qa', True, True),
    ('ds-5', 'ياسر كامل', 'dp-wh', True, True), ('ds-6', 'هبة زكي', 'dp-ga', True, True),
    ('ds-7', 'شريف حلمي', 'dp-fin', False, True), ('ds-8', 'دينا عاشور', 'dp-hr', False, True),
    ('ds-9', 'عمرو شاكر', 'dp-it', False, True), ('ds-10', 'رانيا توفيق', 'dp-qa', False, True),
]
PLACES = [  # id, name, Arabic name
    ('dl-1', 'المقر الرئيسي', 'المقر الرئيسي'), ('dl-2', 'المصنع - العاشر من رمضان', 'المصنع - العاشر من رمضان'),
    ('dl-3', 'مطار القاهرة', 'مطار القاهرة'), ('dl-4', 'مدينة نصر', 'مدينة نصر'), ('dl-5', 'القرية الذكية', 'القرية الذكية'),
    ('dl-6', 'مخزن بورسعيد', 'مخزن بورسعيد'), ('dl-7', 'الجيزة', 'الجيزة'), ('dl-8', 'العاصمة الإدارية', 'العاصمة الإدارية'),
]
ROUTES = [  # id, name, stops, standard km, billable km
    ('dr-1', 'المقر - المصنع - المقر', ['dl-1', 'dl-2', 'dl-1'], 120, 120),
    ('dr-2', 'المقر - المطار - المقر', ['dl-1', 'dl-3', 'dl-1'], 64, 70),
    ('dr-3', 'المقر - بورسعيد - المقر', ['dl-1', 'dl-6', 'dl-1'], 410, 420),
]
TRIPS = [  # destination, purpose, km, hours
    ('المصنع - العاشر من رمضان', 'اجتماع الإنتاج', 118, 6),
    ('مطار القاهرة', 'استقبال ضيف', 66, 3),
    ('مدينة نصر', 'أوراق البنك', 34, 2),
    ('القرية الذكية', 'زيارة عميل', 82, 5),
    ('مخزن بورسعيد', 'جرد المخزن', 415, 10),
    ('الجيزة', 'مصلحة حكومية', 41, 3),
    ('العاصمة الإدارية', 'اجتماع في الوزارة', 96, 7),
    ('المصنع - العاشر من رمضان', 'نقل موظفين', 121, 4),
]


def _put(entity, rid, **row):
    return {'e': entity, 'id': rid, 'op': 'put', 'row': row}


def _lists(today):
    ops = [_put('departments', i, name=n, code=c, active=True) for i, n, c in DEPARTMENTS]
    ops += [_put('tripCategories', i, name=n, nameAr=ar, exportSheet=sheet, hasSequence=seq, openLimitHours=16, ratePerKm=km,
                 ratePerOtHour=ot, vendor=v, order=k + 1) for k, (i, n, ar, sheet, seq, km, ot, v) in enumerate(CATEGORIES)]
    ops += [_put('vehicles', i, plate=p, type=t, categoryId=c, ownership=o, vendor=v, active=True, startKm=km)
            for i, p, t, c, o, v, km in VEHICLES]
    ops += [_put('drivers', i, name=n, mobile=m, vendor=v, licenseNo=no, licenseExpiry=(today + datetime.timedelta(days=d)).isoformat(), active=True)
            for i, n, m, v, no, d in DRIVERS]
    ops += [_put('people', i, name=n, departmentId=d, isRequester=r, isPassenger=p, active=True) for i, n, d, r, p in PEOPLE]
    ops += [_put('places', i, name=n, nameAr=ar, aliases=[], active=True) for i, n, ar in PLACES]
    ops += [_put('routes', i, name=n, stops=s, standardKm=km, billableKm=b) for i, n, s, km, b in ROUTES]
    return ops


def _at(day, hour, minute=0):
    return f'{day.isoformat()}T{hour:02d}:{minute:02d}:00'


@contextlib.contextmanager
def _clock(t):
    """The sample history happened on the trip days, not all in the second the folder was made: the trip services stamp
    amendments, approvals and reviews with this time while it is set."""
    old = tripsvc._now
    tripsvc._now = lambda: t.isoformat(timespec='seconds')
    try:
        yield
    finally:
        tripsvc._now = old


def seed(store, journal, node_id, who):
    """Fill a brand-new database with examples: the lists, then about forty trips of the last three weeks in every state
    (closed and reviewed, waiting for review, approved and declined, corrected with a reason, cancelled, on the road now, and orders
    for today and tomorrow). `who` is the built-in administrator."""
    rnd = random.Random(26)
    user, uid = who['display'], who['id']
    now = domain.business_now().replace(tzinfo=None, microsecond=0)
    today = now.date()
    store.commit(user, IP, 'Sample data: lists', tripsvc.normalize_ops(store, _lists(today)), user_id=uid)

    cars = [v for v in VEHICLES if v[0] != 'dv-4']                     # one owned car stays unused, so the list shows an idle car too
    odo = {v[0]: v[6] for v in VEHICLES}
    requesters = [p for p in PEOPLE if p[3]]
    k = 0
    for back in range(20, -2, -1):                                      # 20 days ago ... tomorrow
        day = today - datetime.timedelta(days=back)
        if day.weekday() == 4 and back > 0:                             # Friday off, like the office
            continue
        for _ in range(2 if back > 1 else 3):
            k += 1
            car = rnd.choice(cars)
            driver = DRIVERS[(VEHICLES.index(car) + back) % len(DRIVERS)]
            if driver[5] < 0 and back > 3:                              # the driver whose licence ended only drives in the last days
                driver = DRIVERS[0]
            req = rnd.choice(requesters)
            dest, purpose, km, hours = rnd.choice(TRIPS)
            corrected, long_day = k % 7 == 0, k % 11 == 0
            riders = rnd.sample([p for p in PEOPLE if p[0] != req[0]], rnd.randint(0, 3))
            data = {'date': day.isoformat(), 'categoryId': car[3], 'vehicleId': car[0], 'driverId': driver[0], 'requesterId': req[0],
                    'destination': dest, 'purpose': purpose, 'passengers': [{'personId': p[0]} for p in riders]}
            if car[3] in ('dc-manager', 'dc-extra'):
                data['billableKm'] = km + (5 if corrected else 0)       # the vendor's km; the corrected trip shows why they must match
            tid = tripsvc.create_trip(store, journal, node_id, user, IP, uid, data)['id']
            if back < 0:
                continue                                                # tomorrow: an order that has not left yet
            if back == 0:
                if k % 3 == 0:
                    tripsvc.start_trip(store, user, IP, uid, tid)       # on the road now
                continue
            if k % 13 == 0:
                with _clock(datetime.datetime.combine(day, datetime.time(7, 30))):
                    tripsvc.cancel(store, user, IP, uid, tid, 'الاجتماع اتأجل')
                continue
            start, hour = odo[car[0]] + rnd.choice([0, 0, 0, 8]), rnd.choice([7, 8, 9, 10])
            end_at = datetime.datetime.combine(day, datetime.time(hour)) + datetime.timedelta(
                hours=hours + (6 if long_day else 0), minutes=rnd.choice([0, 15, 30, 45]))   # a long day shows overtime in the reports
            with _clock(min(end_at + datetime.timedelta(minutes=20), now)):
                tripsvc.close_trip(store, user, IP, uid, tid, {'startKm': start, 'endKm': start + km, 'startAt': _at(day, hour),
                                                               'endAt': end_at.isoformat(timespec='seconds')})
            odo[car[0]] = start + km
            if corrected:                                               # a correction keeps the old value and the reason
                with _clock(min(end_at + datetime.timedelta(hours=2), now)):
                    tripsvc.close_trip(store, user, IP, uid, tid, {'endKm': start + km + 5, 'reason': 'السواق قرا العداد تاني'})
                odo[car[0]] += 5
            if back > 3:                                                # older trips were checked; the last days wait in the review queue
                with _clock(datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(10))):
                    if k % 9 != 0:
                        tripsvc.approve(store, user, IP, uid, tid, k % 17 != 0)
                    tripsvc.review(store, user, IP, uid, tid)
    return k
