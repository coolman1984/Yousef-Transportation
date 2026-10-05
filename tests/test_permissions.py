"""Permissions through the real server: what each profile may READ (rates, contact numbers, reports, photos) and WRITE
(approval, status, link and lock fields, locked trips, amendments). Direct API calls, not the screens - hiding a button is not protection."""
import io
import unittest
import zipfile

from harness import ApiError, Server, make_authority


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class PermissionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('perms').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car', ratePerKm=10, ratePerOtHour=50, vendor='Misr'),
            put('tripCategories', 'cat2', name='SUV Rent', exportSheet='SUV Rent', ratePerKm=12),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True),
            put('drivers', 'd1', name='Driver One', mobile='01012345678', active=True),
            put('people', 'p1', name='Sara Adel', mobile='01199999999', isRequester=True, isPassenger=True),
            put('departments', 'dep1', name='HR')]})
        cls.profiles = {p['id']: p for p in cls.ac.get('/api/users')['profiles']}
        cls.users = {}

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def login_as(self, name, perms=None, profile=None, scopes=None):
        """A user with the given profile (or a hand-made permission list), logged in on its own browser."""
        if name not in self.users:
            p = self.profiles.get(profile)
            self.ac.post('/api/users/save', {'username': name, 'full_name': name.title(), 'password': 'Perm-test-77x', 'must_change': False,
                                             'role': p['name'] if p else 'Custom', 'perms': perms if perms is not None else p['perms'], 'scopes': scopes})
            self.users[name] = True
        c = self.S.client()
        c.login(name, 'Perm-test-77x')
        return c

    def new_trip(self, cat='cat1'):
        return self.ac.post('/api/trips/new', {'categoryId': cat, 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'destination': 'Factory'})

    def trip(self, tid, c=None):
        return next(t for t in (c or self.ac).get('/api/state')['trips'] if t['id'] == tid)

    def close_trip(self, tid):
        self.ac.post('/api/trips/amend', {'id': tid, 'field': 'status', 'value': 'closed', 'reason': 'Closed by office'})

    def raw_row(self, tid):
        t = self.trip(tid)
        return t['ver'], {k: v for k, v in t.items() if k != 'ver'}

    def commit_trip_change(self, c, tid, **changes):
        ver, row = self.raw_row(tid)
        return c.post('/api/commit', {'label': 'edit', 'ops': [{'e': 'trips', 'id': tid, 'op': 'put', 'ver': ver, 'row': {**row, **changes}}]})

    # ---------------------------------------------------------------- reading
    def test_a_view_only_user_gets_no_rates_and_no_phone_numbers(self):
        c = self.login_as('vera.view', perms=['overview.view', 'trips.view'])
        st = c.get('/api/state')
        self.assertTrue(st['tripCategories'])
        for cat in st['tripCategories']:
            self.assertNotIn('ratePerKm', cat)
            self.assertNotIn('ratePerOtHour', cat)
        self.assertEqual(st['tripCategories'][0]['name'], 'Manager car')  # the names stay: trips still show their category
        self.assertTrue(all('mobile' not in d for d in st['drivers']))
        self.assertTrue(all('mobile' not in p for p in st['people']))
        self.assertTrue(st['drivers'])

    def test_b_pages_that_need_the_numbers_still_get_them(self):
        full = self.ac.get('/api/state')
        self.assertEqual(next(c for c in full['tripCategories'] if c['id'] == 'cat1')['ratePerKm'], 10)
        fin = self.login_as('fiona.fin', profile='finance').get('/api/state')
        self.assertEqual(next(c for c in fin['tripCategories'] if c['id'] == 'cat1')['ratePerKm'], 10)
        disp = self.login_as('dina.disp', profile='dispatcher').get('/api/state')  # sends links on WhatsApp, sees the Drivers page
        self.assertTrue(disp['drivers'][0]['mobile'].endswith('1012345678'))  # stored normalised, e.g. +20...
        self.assertNotIn('ratePerKm', disp['tripCategories'][0])

    def test_c_money_reports_need_finance(self):
        t = self.new_trip()
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'startKm', 'value': 100, 'reason': 'test reading'})
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'endKm', 'value': 160, 'reason': 'test reading'})
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'billableKm', 'value': 90, 'reason': 'vendor bill'})
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'status', 'value': 'finished', 'reason': 'test reading'})
        rep = self.login_as('rita.review', profile='reviewer').get('/api/reports')
        self.assertFalse(rep['money'])
        self.assertEqual((rep['reconciliation'], rep['allocation']), ([], []))
        self.assertIn('summary', rep)
        full = self.ac.get('/api/reports')
        self.assertTrue(full['money'])
        self.assertTrue(full['reconciliation'])

    def test_d_clean_exports_leave_out_money_sheets_without_finance(self):
        ym = self.trip(self.new_trip()['id'])['date'][:7]
        def sheet_names(data):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return z.read('xl/workbook.xml').decode('utf-8')
        no_money = sheet_names(self.login_as('rita.review', profile='reviewer').get(f'/api/excel/export?layout=clean&ym={ym}'))
        with_money = sheet_names(self.ac.get(f'/api/excel/export?layout=clean&ym={ym}'))
        self.assertIn('Vendor reconciliation', with_money)
        self.assertIn('Cost allocation', with_money)
        self.assertNotIn('Vendor reconciliation', no_money)
        self.assertNotIn('Cost allocation', no_money)
        self.assertIn('Anomalies', no_money)  # the rest of the report is still there

    # ---------------------------------------------------------------- writing
    def test_e_plain_save_cannot_approve(self):
        t = self.new_trip()
        c = self.login_as('ed.editor', perms=['overview.view', 'trips.view', 'trips.create', 'trips.edit'])
        with self.assertRaises(ApiError) as e:
            self.commit_trip_change(c, t['id'], gaApproved='yes', gaBy='Somebody Else')
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.trip(t['id'])['gaApproved'], '')
        with self.assertRaises(ApiError) as e:  # the real button is still limited to the approver
            c.post('/api/trips/approve', {'id': t['id'], 'yes': True})
        self.assertEqual(e.exception.code, 403)
        approver = self.login_as('gail.ga', profile='ga-approver')
        approver.post('/api/trips/approve', {'id': t['id'], 'yes': True})
        x = self.trip(t['id'])
        self.assertEqual(x['gaApproved'], 'yes')
        self.assertIn('gail.ga', x['gaBy'])  # the server writes who approved, never the client

    def test_f_plain_save_cannot_change_status_link_or_lock(self):
        t = self.new_trip()
        c = self.login_as('ed.editor', perms=['overview.view', 'trips.view', 'trips.create', 'trips.edit'])
        for field, value in (('status', 'closed'), ('status', 'cancelled'), ('linkHash', 'abc'), ('linkExpiry', '2099-01-01T00:00:00'),
                             ('boundDevice', 'x'), ('locked', True), ('no', '99-Z-99999'), ('source', 'excel')):
            with self.assertRaises(ApiError, msg=field) as e:
                self.commit_trip_change(c, t['id'], **{field: value})
            self.assertEqual(e.exception.code, 403, field)
        self.assertEqual(self.trip(t['id'])['status'], 'draft')
        self.commit_trip_change(c, t['id'], notes='an ordinary edit still works')  # harmless fields are fine
        self.assertEqual(self.trip(t['id'])['notes'], 'an ordinary edit still works')

    def test_g_plain_save_cannot_create_an_approved_or_linked_trip(self):
        c = self.login_as('ed.editor', perms=['overview.view', 'trips.view', 'trips.create', 'trips.edit'])
        with self.assertRaises(ApiError) as e:
            c.post('/api/commit', {'label': 'x', 'ops': [put('trips', 'forged1', no='26-A-00001', categoryId='cat1', gaApproved='yes', gaBy='X')]})
        self.assertEqual(e.exception.code, 403)

    def test_h_locked_trip_needs_the_amend_route(self):
        t = self.new_trip()
        self.close_trip(t['id'])
        reviewer = self.login_as('rita.review', profile='reviewer')  # has trips.amend
        before = [a for a in self.ac.get('/api/state')['tripAmendments'] if a['tripId'] == t['id']]
        with self.assertRaises(ApiError) as e:
            self.commit_trip_change(reviewer, t['id'], notes='silent edit')
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.trip(t['id']).get('notes') or '', '')
        with self.assertRaises(ApiError) as e:  # a hand-written amendment record is refused too
            reviewer.post('/api/commit', {'label': 'x', 'ops': [put('tripAmendments', 'amX', tripId=t['id'], field='notes', old='', new='x', reason='forged', by='Boss')]})
        self.assertEqual(e.exception.code, 403)
        reviewer.post('/api/trips/amend', {'id': t['id'], 'field': 'notes', 'value': 'proper correction', 'reason': 'Typo fixed'})
        after = [a for a in self.ac.get('/api/state')['tripAmendments'] if a['tripId'] == t['id']]
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(self.trip(t['id'])['notes'], 'proper correction')

    def test_i_dispatcher_can_cancel_an_open_trip_but_not_a_closed_one(self):
        d = self.login_as('dina.disp', profile='dispatcher')
        t = self.new_trip()
        d.post('/api/trips/cancel', {'id': t['id'], 'reason': 'Passenger cancelled'})
        self.assertEqual(self.trip(t['id'])['status'], 'cancelled')
        self.assertEqual(len([a for a in self.ac.get('/api/state')['tripAmendments'] if a['tripId'] == t['id']]), 1)
        closed = self.new_trip()
        self.close_trip(closed['id'])
        with self.assertRaises(ApiError) as e:
            d.post('/api/trips/cancel', {'id': closed['id'], 'reason': 'Too late for this'})
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.trip(closed['id'])['status'], 'closed')
        reviewer = self.login_as('cora.canceller', perms=self.profiles['reviewer']['perms'] + ['trips.cancel'])
        reviewer.post('/api/trips/cancel', {'id': closed['id'], 'reason': 'Reviewed and cancelled'})
        self.assertEqual(self.trip(closed['id'])['status'], 'cancelled')

    def test_j_category_limit_still_applies_to_the_dedicated_routes(self):
        d = self.login_as('dina.cat1', profile='dispatcher', scopes=['cat1'])
        other = self.new_trip('cat2')
        with self.assertRaises(ApiError) as e:
            d.post('/api/trips/cancel', {'id': other['id'], 'reason': 'Not my category'})
        self.assertEqual(e.exception.code, 403)

    # ---------------------------------------------------------------- photos
    def test_k_trip_photo_follows_its_trip(self):
        t = self.new_trip('cat1')
        img = bytes(range(256)) * 20
        up = self.ac.call('POST', '/api/upload?name=odo.jpg', raw=img, headers={'Content-Type': 'application/octet-stream'})
        self.ac.post('/api/commit', {'label': 'photo', 'ops': [put('tripPhotos', 'ph1', tripId=t['id'], kind='start', src=up['src'])]})
        same = self.login_as('pia.cat1', profile='viewer', scopes=['cat1'])
        other = self.login_as('pia.cat2', profile='viewer', scopes=['cat2'])
        nofiles = self.login_as('pia.nofiles', perms=['overview.view', 'trips.view'])
        self.assertEqual(same.get(up['src']), img)
        with self.assertRaises(ApiError) as e:  # known path, wrong category: answered like a missing file
            other.get(up['src'])
        self.assertEqual(e.exception.code, 404)
        with self.assertRaises(ApiError) as e:  # an image no longer skips the download permission
            nofiles.get(up['src'])
        self.assertEqual(e.exception.code, 403)
        with same.opener.open(same.base + up['src']) as r:
            cache = r.headers.get('Cache-Control', '')
        self.assertIn('private', cache)
        self.assertNotIn('immutable', cache)
        self.assertEqual(self.ac.get(up['src']), img)


if __name__ == '__main__':
    unittest.main()
