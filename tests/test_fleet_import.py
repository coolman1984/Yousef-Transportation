"""Vehicles and drivers from one Excel or CSV file: headers, digits, duplicates, errors, and one save.

The preview changes nothing. Confirming writes the accepted rows in one commit. A second confirm, a plate that
appeared after the preview, or a category that was removed saves nothing.
"""
import os
import sys
import unittest

from harness import ApiError, Server, make_authority

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import domain  # noqa: E402
import fleet_import as F  # noqa: E402
import xlsx_write as w  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


def xlsx(headers, rows, name='السيارات'):
    return w.build([w.Sheet(name, [list(headers), *[list(r) for r in rows]])])


class _Sheet:
    def __init__(self, rows, name='S', hidden=False):
        self.name, self.hidden = name, hidden
        self.max_row = len(rows)
        self.max_col = max((len(r) for r in rows), default=1) or 1
        self._rows = rows

    def value(self, r, c):
        if r < 1 or r > len(self._rows):
            return None
        row = self._rows[r - 1]
        return row[c - 1] if c <= len(row) else None


class _Book:
    def __init__(self, *sheets):
        self.sheets = sheets


def codes(item):
    return [m['code'] for m in item['messages']]


class ParseTest(unittest.TestCase):
    def setUp(self):
        F._PREVIEWS.clear()

    def tearDown(self):
        F._PREVIEWS.clear()

    def plan(self, headers, rows, kind='vehicles', state=None, name='cars.xlsx', sheet='السيارات'):
        return F.parse_bytes(xlsx(headers, rows, sheet), name, kind, state or {})

    def test_arabic_and_english_headers_any_order_and_indic_digits(self):
        arabic = self.plan(
            ['ملاحظات', 'النوع', 'اللوحة', 'العداد وقت الإضافة', 'الملكية', 'نشط'],
            [['ملاحظة', 'تويوتا', 'أ ب ج ١٢٣٤', '٤٥٠٠٠', 'إيجار', 'نعم'],
             ['', 'هيونداي', 'هـ ي و ٥٥', '١٢', 'ملك', 'لا']])
        self.assertEqual(arabic['stats']['new'], 2)
        self.assertEqual(arabic['rows'][0]['values']['startKm'], 45000)
        self.assertEqual(arabic['rows'][0]['values']['ownership'], 'rent')
        self.assertIs(arabic['rows'][0]['values']['active'], True)
        self.assertIs(arabic['rows'][1]['values']['active'], False)
        key = domain.norm_plate('أبج 1234')[1]
        self.assertEqual(arabic['rows'][0]['key'], key)

        english = self.plan(
            ['Notes', 'Type', 'Plate Number', 'Baseline Odometer', 'Ownership', 'Active'],
            [['n', 'Bus', 'س ي ن 9', '100', 'rented', 'no']])
        self.assertEqual(english['stats']['new'], 1)
        self.assertEqual(english['rows'][0]['values']['ownership'], 'rent')
        self.assertEqual(english['rows'][0]['values']['startKm'], 100)

        persian = self.plan(['اللوحة', 'النوع'], [['س ي ن ۵۵', 'باص']])
        self.assertEqual(persian['rows'][0]['key'], domain.norm_plate('س ي ن 55')[1])

    def test_title_row_blank_rows_and_duplicate_plates(self):
        book = _Book(_Sheet([
            ['سيارات الشركة'],
            [],
            ['النوع', 'اللوحة'],
            ['تويوتا', 'ط و ي 100'],
            ['', ''],
            ['هيونداي', 'طوي ١٠٠'],
            ['باص', 'ب ص ص 2'],
        ]))
        plan = F.parse_workbook(book, 'vehicles', {})
        self.assertEqual([i['status'] for i in plan['rows']], ['new', 'error', 'new'])
        self.assertEqual(plan['rows'][1]['row'], 6)
        self.assertIn('dup_file', codes(plan['rows'][1]))
        self.assertEqual(plan['rows'][1]['messages'][0]['vars']['row'], 4)
        self.assertEqual(plan['stats']['blank'], 1)
        self.assertEqual(plan['ready'], 2)

    def test_update_matches_the_normalised_plate_and_leaves_blanks_alone(self):
        label, key = domain.norm_plate('ط و ي 6829')
        state = {'vehicles': [{'id': 'v1', 'ver': 3, 'plate': label, 'plateKey': key, 'type': 'Old',
                               'active': True, 'startKm': 1000, 'notes': 'keep', 'ownership': 'own'}]}
        plan = self.plan(['اللوحة', 'النوع', 'ملاحظات'], [['  طوي ٦٨٢٩  ', 'New', '']], state=state)
        self.assertEqual(plan['stats']['update'], 1)
        self.assertEqual(plan['rows'][0]['values'], {'type': 'New'})
        same = self.plan(['اللوحة', 'النوع'], [['طوي 6829', 'Old']], state=state)
        self.assertEqual(same['stats']['same'], 1)
        self.assertEqual(same['ready'], 0)

    def test_bad_rows_are_reported_and_not_ready(self):
        state = {'tripCategories': [{'id': 'c1', 'name': 'Manager car', 'nameAr': 'سيارة مدير'}]}
        plan = self.plan(
            ['اللوحة', 'النوع', 'الفئة', 'الملكية', 'العداد وقت الإضافة', 'نشط'],
            [['', 'تويوتا', '', '', '', ''],
             ['***', 'تويوتا', '', '', '', ''],
             ['س ي ن 1', 'تويوتا', 'مش موجودة', 'تأجير غريب', '١٢٫٥', 'ربما'],
             ['س ي ن 2', 'تويوتا', 'سيارة مدير', 'ملك', '٠', 'نعم'],
             ['س' * 50, 'تويوتا', '', '', '', '']],
            state=state)
        self.assertEqual(codes(plan['rows'][0]), ['plate_required'])
        self.assertIn('plate', codes(plan['rows'][1]))
        self.assertEqual(set(codes(plan['rows'][2])), {'category', 'ownership', 'km', 'active'})
        self.assertEqual(plan['rows'][3]['status'], 'new')
        self.assertEqual(plan['rows'][3]['values']['categoryId'], 'c1')
        self.assertEqual(plan['rows'][3]['values']['startKm'], 0)
        self.assertIn('too_long', codes(plan['rows'][4]))
        self.assertEqual(plan['stats']['error'], 4)
        self.assertEqual(plan['ready'], 1)
        self.assertNotIn('values', plan['errors'][0])

    def test_csv_semicolon_and_utf8(self):
        text = 'النوع;اللوحة\nتويوتا;س ي ن 7\n'
        plan = F.parse_bytes(text.encode('utf-8-sig'), 'cars.csv', 'vehicles', {})
        self.assertEqual(plan['stats']['new'], 1)
        self.assertEqual(plan['rows'][0]['values']['type'], 'تويوتا')

    def test_driver_mobile_date_and_name_match(self):
        name_key = domain.key_text('احمد علي')
        state = {'drivers': [{'id': 'd1', 'ver': 1, 'name': 'أحمد علي', 'nameKey': name_key, 'mobile': '+201000000000', 'active': True}]}
        plan = F.parse_bytes(xlsx(
            ['الاسم', 'الموبايل', 'رقم الرخصة', 'انتهاء الرخصة', 'نشط'],
            [['احمد علي', '٠١٠١٢٣٤٥٦٧٨', '١٢٣', '30/06/2028', 'نعم'],
             ['سامي', '01011111111 / 01022222222', '', '2028-01-02', ''],
             ['منى', '123', '', '2019-01-01', ''],
             ['', '01012345678', '', '', '']],
            'السائقون'), 'drivers.csv', 'drivers', state)
        self.assertEqual(plan['rows'][0]['status'], 'update')
        self.assertEqual(plan['rows'][0]['values']['mobile'], '+201012345678')
        self.assertEqual(plan['rows'][0]['values']['licenseNo'], '123')
        self.assertEqual(plan['rows'][0]['values']['licenseExpiry'], '2028-06-30')
        self.assertEqual(plan['rows'][1]['status'], 'new')
        self.assertIn('+201011111111', plan['rows'][1]['values']['mobile'])
        self.assertIn('+201022222222', plan['rows'][1]['values']['mobile'])
        self.assertIn('mobile', codes(plan['rows'][2]))
        self.assertIn('expiry', codes(plan['rows'][2]))
        self.assertIn('name_required', codes(plan['rows'][3]))

    def test_template_has_arabic_headers_and_one_example(self):
        for kind, header, field in (('vehicles', 'اللوحة', 'plate'), ('drivers', 'الاسم', 'name')):
            raw = F.template(kind)
            plan = F.parse_bytes(raw, kind + '.xlsx', kind, {})
            self.assertEqual(plan['stats']['new'], 1, kind)
            self.assertEqual(plan['sheets'], ['السيارات' if kind == 'vehicles' else 'السائقون'])
            book = __import__('formats').read_workbook(raw, kind + '.xlsx', engine='native')
            headers = [book.sheets[0].value(1, c) for c in range(1, book.sheets[0].max_col + 1)]
            self.assertIn(header, headers)
            self.assertEqual(len(headers), len(F.VEHICLE_HEADERS if kind == 'vehicles' else F.DRIVER_HEADERS))

    def test_no_recognisable_header_and_too_many_rows(self):
        with self.assertRaises(F.FleetError) as big_miss:
            self.plan(['الاسم'], [['سامي']])
        self.assertEqual(big_miss.exception.code, 'err.flt.noColumns')
        rows = [['اللوحة']] + [[f'س ي ن {i}'] for i in range(1, F.MAX_ROWS + 2)]
        with self.assertRaises(F.FleetError) as too_big:
            F.parse_workbook(_Book(_Sheet(rows)), 'vehicles', {})
        self.assertEqual(too_big.exception.code, 'err.flt.big')
        with self.assertRaises(F.FleetError) as kind:
            F.parse_bytes('اللوحة\nس ي ن 1\n'.encode(), 'a.csv', 'people', {})
        self.assertEqual(kind.exception.code, 'err.flt.kind')

    def test_one_thousand_rows(self):
        rows = [[f'س ي ن {i}', 'تويوتا', i * 10] for i in range(1, 999)]
        rows.append(['س ي ن 1', 'مكرر', 1])
        rows.append(['س ي ن 9999', 'غلط', 'لا'])
        rows.insert(10, ['', '', ''])
        plan = self.plan(['اللوحة', 'النوع', 'العداد'], rows)
        self.assertEqual(plan['stats']['rows'], 1000)
        self.assertEqual(plan['stats']['new'], 998)
        self.assertEqual(plan['stats']['error'], 2)
        self.assertEqual(plan['stats']['blank'], 1)
        self.assertEqual(plan['ready'], 998)
        self.assertLessEqual(len(plan['errors']), 1000)

    def test_confirm_refuses_a_changed_list_and_a_second_take(self):
        plan = self.plan(['اللوحة', 'النوع'], [['س ي ن 4', 'باص']])
        label, key = domain.norm_plate(plan['rows'][0]['label'])
        state = {'vehicles': [{'id': 'v9', 'ver': 1, 'plate': label, 'plateKey': key}]}
        with self.assertRaises(F.FleetError) as changed:
            F.build_ops(plan, state)
        self.assertEqual(changed.exception.code, 'err.flt.changed')
        ops, new, updated = F.build_ops(plan, {})
        self.assertEqual((new, updated, len(ops)), (1, 0, 1))
        pid = F.store_preview('u', plan)
        self.assertEqual(F.take_preview(pid, 'u')['kind'], 'vehicles')
        with self.assertRaises(F.FleetError) as expired:
            F.take_preview(pid, 'u')
        self.assertEqual(expired.exception.code, 'err.flt.expired')
        with self.assertRaises(F.FleetError):
            F.take_preview(F.store_preview('u', plan), 'someone-else')

    def test_preview_memory_is_capped_and_the_label_fits_the_log(self):
        ids = [F.store_preview('u', {'kind': 'vehicles'}) for _ in range(40)]
        self.assertLessEqual(len(F._PREVIEWS), F._MAX_PREVIEWS)
        self.assertNotIn(ids[0], F._PREVIEWS)
        label = F.commit_label('vehicles', '../' + 'x' * 300 + '.xlsx', 3, 1)
        self.assertLessEqual(len(label), 200)
        self.assertTrue(label.startswith('Vehicle Excel import '))
        self.assertTrue(label.endswith(' (3 new, 1 updated)'))
        self.assertNotIn('..', label)

    def test_packaged_program_names_the_module(self):
        with open(os.path.join(ROOT, 'tools', 'build_windows.py'), encoding='utf-8') as f:
            build = f.read()
        with open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8') as f:
            app = f.read()
        self.assertIn('--include-module=fleet_import', build)
        self.assertIn('import fleet_import', app)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('fleet').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', nameAr='سيارة مدير', exportSheet='All Car'),
            put('vehicles', 'v1', plate='ط و ي 6829', type='Old', active=True, startKm=1000, notes='keep', ownership='own'),
            put('drivers', 'd1', name='أحمد علي', active=True, mobile='01000000000')]})

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def vehicles(self):
        return self.ac.get('/api/state')['vehicles']

    def drivers(self):
        return self.ac.get('/api/state')['drivers']

    def post_file(self, kind, data, name, client=None):
        return (client or self.ac).call(
            'POST', f'/api/fleet/preview?kind={kind}&name={name}', raw=data,
            headers={'Content-Type': 'application/octet-stream'})

    def test_template_download_is_a_workbook(self):
        raw = self.ac.call('GET', '/api/fleet/template?kind=vehicles')
        self.assertTrue(raw.startswith(b'PK'))
        plan = F.parse_bytes(raw, 'Vehicles_template.xlsx', 'vehicles', {})
        self.assertEqual(plan['stats']['new'], 1)

    def test_preview_then_one_save_updates_and_skips_the_bad_row(self):
        before = len(self.vehicles())
        data = xlsx(
            ['اللوحة', 'النوع', 'الفئة', 'الملكية', 'الشركة', 'ملاحظات'],
            [['طوي ٦٨٢٩', 'New', '', '', '', ''],
             ['طوي 6829', 'Again', '', '', '', ''],
             ['س ب ق 15', 'باص', 'سيارة مدير', 'إيجار', 'النيل', 'ملاحظة'],
             ['', '', '', '', '', ''],
             ['س ب ق 16', 'باص', 'فئة ناقصة', '', '', '']])
        pv = self.post_file('vehicles', data, '../../secret.xlsx')
        self.assertEqual(pv['filename'], 'secret.xlsx')
        self.assertNotIn('rows', pv)
        self.assertEqual(pv['stats']['update'], 1)
        self.assertEqual(pv['stats']['new'], 1)
        self.assertEqual(pv['stats']['error'], 2)
        self.assertEqual(pv['stats']['blank'], 1)
        self.assertTrue(any(m['code'] == 'dup_file' for e in pv['errors'] for m in e['messages']))
        self.assertTrue(any(m['code'] == 'category' for e in pv['errors'] for m in e['messages']))
        saved = self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual((saved['new'], saved['updated']), (1, 1))
        cars = self.vehicles()
        self.assertEqual(len(cars), before + 1)
        old = next(v for v in cars if v['plateKey'] == domain.norm_plate('طوي 6829')[1])
        self.assertEqual(old['type'], 'New')
        self.assertEqual(old['startKm'], 1000)
        self.assertIs(old['active'], True)
        self.assertEqual(old['notes'], 'keep')
        new = next(v for v in cars if v['plateKey'] == domain.norm_plate('س ب ق 15')[1])
        self.assertEqual(new['ownership'], 'rent')
        self.assertEqual(new['vendor'], 'النيل')
        self.assertEqual(new['categoryId'], 'cat1')
        self.assertIs(new['active'], True)
        with self.assertRaises(ApiError) as again:
            self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual(again.exception.data.get('code'), 'err.flt.expired')
        self.assertEqual(len(self.vehicles()), before + 1)
        audit = self.ac.get('/api/audit?q=Vehicle%20Excel%20import')
        self.assertTrue(any('Vehicle Excel import' in (r.get('label') or '') for r in audit['rows']))
        activity = self.ac.get('/api/activity?type=import')
        self.assertTrue(any((r.get('action') or '').startswith('Vehicle Excel import') for r in activity['rows']))

    def test_a_plate_added_after_the_preview_saves_nothing(self):
        data = xlsx(['اللوحة', 'النوع'], [['س ب ق 77', 'جديدة'], ['س ب ق 78', 'جديدة']])
        pv = self.post_file('vehicles', data, 'late.xlsx')
        self.ac.post('/api/commit', {'label': 'manual', 'ops': [put('vehicles', 'v-late', plate='س ب ق 77', active=True)]})
        before = {v['plateKey'] for v in self.vehicles()}
        with self.assertRaises(ApiError) as err:
            self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual(err.exception.data.get('code'), 'err.flt.changed')
        self.assertEqual({v['plateKey'] for v in self.vehicles()}, before)

    def test_removing_the_category_saves_nothing(self):
        self.ac.post('/api/commit', {'label': 'cat', 'ops': [
            put('tripCategories', 'cat-temp', name='Temp cat', nameAr='فئة مؤقتة', exportSheet='All Car')]})
        data = xlsx(['اللوحة', 'الفئة'], [['س ب ق 90', 'فئة مؤقتة']])
        pv = self.post_file('vehicles', data, 'cat.xlsx')
        cat = next(c for c in self.ac.get('/api/state')['tripCategories'] if c['id'] == 'cat-temp')
        self.ac.post('/api/commit', {'label': 'del cat', 'ops': [{'e': 'tripCategories', 'id': 'cat-temp', 'op': 'del', 'ver': cat['ver']}]})
        before = len(self.vehicles())
        with self.assertRaises(ApiError) as err:
            self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual(err.exception.data.get('code'), 'err.flt.changed')
        self.assertEqual(len(self.vehicles()), before)

    def test_drivers_import_normalises_the_mobile(self):
        data = xlsx(
            ['الاسم', 'الموبايل', 'انتهاء الرخصة'],
            [['احمد علي', '01099998888', ''],
             ['سامي محمد', '٠١٠٥٥٥٥٦٦٦٦', '2027-12-01'],
             ['بدون رقم', '999', '']],
            'السائقون')
        pv = self.post_file('drivers', data, 'drivers.xlsx')
        self.assertEqual(pv['stats']['update'], 1)
        self.assertEqual(pv['stats']['new'], 1)
        self.assertEqual(pv['stats']['error'], 1)
        saved = self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual((saved['new'], saved['updated'], saved['skipped']), (1, 1, 1))
        rows = self.drivers()
        old = next(d for d in rows if d['nameKey'] == domain.key_text('أحمد علي'))
        self.assertTrue(old['mobile'].endswith('1099998888'))
        new = next(d for d in rows if d['nameKey'] == domain.key_text('سامي محمد'))
        self.assertTrue(new['mobile'].endswith('1055556666'))
        self.assertEqual(new['licenseExpiry'], '2027-12-01')
        self.assertFalse(any(d['nameKey'] == domain.key_text('بدون رقم') for d in rows))

    def test_nothing_ready_does_not_write(self):
        before = len(self.vehicles())
        pv = self.post_file('vehicles', xlsx(['اللوحة'], [['']]), 'empty.xlsx')
        self.assertEqual(pv['ready'], 0)
        with self.assertRaises(ApiError) as err:
            self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual(err.exception.data.get('code'), 'err.flt.nothing')
        self.assertEqual(len(self.vehicles()), before)

    def test_permission_and_another_server(self):
        viewer = self.S.client()
        self.ac.post('/api/users/save', {'username': 'fleet.view', 'full_name': 'Fleet View', 'password': 'Perm-test-77x',
                                         'must_change': False, 'role': 'Custom', 'perms': ['fleet.view']})
        viewer.login('fleet.view', 'Perm-test-77x')
        with self.assertRaises(ApiError) as denied:
            viewer.call('GET', '/api/fleet/template?kind=vehicles')
        self.assertEqual(denied.exception.code, 403)
        data = xlsx(['اللوحة'], [['س ب ق 3']])
        with self.assertRaises(ApiError) as denied_post:
            self.post_file('vehicles', data, 'x.xlsx', client=viewer)
        self.assertEqual(denied_post.exception.code, 403)
        pv = self.post_file('vehicles', data, 'x.xlsx')
        other = Server('fleet-b').start()
        try:
            boss = make_authority(other)
            with self.assertRaises(ApiError) as foreign:
                boss.post('/api/fleet/commit', {'id': pv['id']})
            self.assertEqual(foreign.exception.data.get('code'), 'err.flt.expired')
        finally:
            other.cleanup()

    def test_one_thousand_rows_are_one_commit(self):
        rows = [[f'أ ل ف {i:04d}', 'تويوتا'] for i in range(1000)]
        rows[500] = ['أ ل ف 0001', 'مكرر']
        pv = self.post_file('vehicles', xlsx(['اللوحة', 'النوع'], rows), 'thousand.xlsx')
        self.assertEqual(pv['stats']['rows'], 1000)
        self.assertEqual(pv['stats']['new'], 999)
        self.assertEqual(pv['stats']['error'], 1)
        before = len(self.vehicles())
        saved = self.ac.post('/api/fleet/commit', {'id': pv['id']})
        self.assertEqual(saved['new'], 999)
        self.assertEqual(len(self.vehicles()), before + 999)

    def test_practice_sheet_is_refused_outside_training(self):
        with self.assertRaises(ApiError) as vehicles:
            self.ac.call('GET', '/api/fleet/practice?kind=vehicles')
        self.assertEqual(vehicles.exception.code, 403)
        self.assertEqual(vehicles.exception.data.get('key'), 'err.flt.practice')
        with self.assertRaises(ApiError) as drivers:
            self.ac.call('GET', '/api/fleet/practice?kind=drivers')
        self.assertEqual(drivers.exception.code, 403)
        self.assertEqual(drivers.exception.data.get('key'), 'err.flt.practice')


class PracticeSheetTest(unittest.TestCase):
    """The bundled exercise. These counts are written out here; they are not copied from the builder."""

    def plan(self, kind, state=None):
        return F.parse_bytes(F.practice_book(kind), F.practice_name(kind), kind, state or {})

    def test_empty_lists_count_the_good_rows_and_the_deliberate_errors(self):
        cars = self.plan('vehicles')
        self.assertTrue(F.practice_book('vehicles').startswith(b'PK'))
        self.assertEqual(F.practice_name('vehicles'), 'Vehicles_practice.xlsx')
        self.assertEqual(cars['sheets'], ['السيارات'])
        self.assertEqual(cars['stats'], {'rows': 7, 'new': 4, 'update': 0, 'same': 0, 'error': 3, 'blank': 1})
        self.assertEqual(cars['ready'], 4)
        self.assertEqual(cars['rows'][1]['values']['startKm'], 12000)
        by = {item['row']: item for item in cars['rows']}
        self.assertEqual(codes(by[5]), ['plate_required'])
        self.assertEqual(codes(by[6]), ['dup_file'])
        self.assertEqual(by[6]['messages'][0]['vars']['row'], 2)
        self.assertEqual(set(codes(by[8])), {'category', 'ownership', 'km', 'active'})
        self.assertEqual([b['row'] for b in cars['blanks']], [7])

        people = self.plan('drivers')
        self.assertEqual(F.practice_name('drivers'), 'Drivers_practice.xlsx')
        self.assertEqual(people['sheets'], ['السائقون'])
        self.assertEqual(people['stats'], {'rows': 6, 'new': 3, 'update': 0, 'same': 0, 'error': 3, 'blank': 1})
        self.assertEqual(people['ready'], 3)
        by = {item['row']: item for item in people['rows']}
        self.assertEqual(codes(by[4]), ['name_required'])
        self.assertEqual(codes(by[5]), ['dup_file'])
        self.assertEqual(by[5]['messages'][0]['vars']['row'], 2)
        self.assertEqual(codes(by[7]), ['mobile', 'date'])
        self.assertEqual(by[8]['status'], 'new')
        self.assertEqual(by[8]['values']['licenseExpiry'], '2028-06-30')
        self.assertEqual([b['row'] for b in people['blanks']], [6])

    def test_the_training_plate_and_name_become_updates(self):
        label, key = domain.norm_plate('أ ب ج 1234')
        cars = self.plan('vehicles', {'vehicles': [{
            'id': 'dv-1', 'plate': label, 'plateKey': key, 'type': 'Sedan', 'ownership': 'rent',
            'active': True, 'startKm': 85210}]})
        self.assertEqual(cars['stats']['new'], 3)
        self.assertEqual(cars['stats']['update'], 1)
        self.assertEqual(cars['stats']['error'], 3)
        self.assertEqual(cars['stats']['blank'], 1)
        self.assertEqual(cars['stats']['same'], 0)
        updated = next(item for item in cars['rows'] if item['row'] == 4)
        self.assertEqual(updated['status'], 'update')
        self.assertEqual(updated['values']['startKm'], 86000)

        name_key = domain.key_text('أحمد سمير')
        people = self.plan('drivers', {'drivers': [{
            'id': 'dd-1', 'name': 'أحمد سمير', 'nameKey': name_key, 'mobile': '01001234567',
            'active': True, 'licenseExpiry': '2027-01-01'}]})
        self.assertEqual(people['stats']['new'], 2)
        self.assertEqual(people['stats']['update'], 1)
        self.assertEqual(people['stats']['error'], 3)
        self.assertEqual(people['stats']['blank'], 1)
        self.assertEqual(next(item for item in people['rows'] if item['row'] == 3)['status'], 'update')


if __name__ == '__main__':
    unittest.main()


OWNER_ROSTER = os.path.join(ROOT, 'tests', 'fixtures', 'fleet_roster_owner_anon.xlsx')


class OwnerRosterTest(unittest.TestCase):
    """The office's real fleet roster (names, plates and numbers replaced): one sheet "Sedan", an Excel table,
    English headers such as «Vehicle no.» and «Name of Driver», phone numbers stored as numbers without the
    leading zero, a =TODAY()-F2 formula column and a used range that runs to column XEA."""

    def setUp(self):
        with open(OWNER_ROSTER, 'rb') as fh:
            self.data = fh.read()

    def test_vehicles_map_every_column_and_keep_the_rest_in_notes(self):
        plan = F.parse_bytes(self.data, 'roster.xlsx', 'vehicles', {})
        self.assertEqual(plan['sheets'], ['Sedan'])
        self.assertEqual(plan['stats'], {'rows': 114, 'new': 113, 'update': 0, 'same': 0, 'error': 1, 'blank': 0})
        first = plan['rows'][0]
        self.assertEqual(first['row'], 2)
        self.assertEqual(first['values']['type'], 'SUV')
        self.assertEqual(first['values']['vendor'], 'Misr Car Travel')
        notes = first['values']['notes']
        for part in ('Model Year: 2022', 'Valid Date of Car License: 2027-11-26', 'Name of Driver: Driver 038',
                     'Leader name: Korean SUV', 'Line: Korean SUV', 'Inspection date: 2026-08-27', 'Statue: Passed'):
            self.assertIn(part, notes)
        self.assertRegex(notes, r'Phone Number: 01\d{9}')
        self.assertNotIn('expiration', notes)       # the =TODAY() column changes daily and is not kept
        self.assertNotIn('No:', notes)              # the running number is not kept
        types = {item['values']['type'] for item in plan['rows']}
        self.assertEqual(types, {'SUV', 'Sedan', 'Microbus'})
        # The same plate on rows 50 and 108 with two different drivers: the second row is reported.
        self.assertEqual([(e['row'], codes(e)) for e in plan['errors']], [(108, ['dup_file'])])

    def test_drivers_fix_the_lost_zero_and_merge_a_driver_on_two_cars(self):
        plan = F.parse_bytes(self.data, 'roster.xlsx', 'drivers', {})
        self.assertEqual(plan['stats'], {'rows': 114, 'new': 95, 'update': 0, 'same': 15, 'error': 4, 'blank': 0})
        first = plan['rows'][0]
        self.assertEqual(first['label'], 'Driver 038')
        self.assertEqual(first['values']['vendor'], 'Misr Car Travel')
        self.assertEqual(len(first['values']['licenseNo']), 14)
        self.assertRegex(first['values']['mobile'], r'^\+201\d{9}$')     # 1053934637 in the cell -> +201053934637
        texted = [i for i in plan['rows'] if i['row'] == 17][0]          # «0 11 1xxxxxxx» typed as text
        self.assertRegex(texted['values']['mobile'], r'^\+2011\d{8}$')
        self.assertEqual([(e['row'], codes(e)) for e in plan['errors']],
                         [(45, ['mobile']), (51, ['mobile']), (57, ['mobile']), (81, ['name_required'])])

    def test_lost_zero_mobile(self):
        self.assertEqual(F._parse_mobile('1090802840'), '+201090802840')
        self.assertEqual(F._parse_mobile('٠١٠٩٠٨٠٢٨٤٠'), '+201090802840')
        with self.assertRaises(ValueError):
            F._parse_mobile('100149222')
