"""Trip operations through the real server: numbering, amendments, cancel, GA approval, locked trips, insights."""
import unittest
from datetime import date

from harness import ApiError, Server, make_authority


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class TripsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('trips').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car'),
            put('tripCategories', 'cat2', name='SUV Rent', exportSheet='SUV Rent'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True),
            put('drivers', 'd1', name='Driver One', active=True),
            put('people', 'p1', name='Sara Adel', isRequester=True, isPassenger=True),
            put('departments', 'dep1', name='HR')]})
        cls.year = date.today().year % 100

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def trip(self, cat='cat1', **kw):
        return self.ac.post('/api/trips/new', {'categoryId': cat, 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'departmentId': 'dep1',
                                               'destination': 'Factory-Capital-Factory', 'passengers': [{'personId': 'p1'}, {'freeText': 'Visitor'}], **kw})

    def get_trip(self, tid, c=None):
        return next(t for t in (c or self.ac).get('/api/state')['trips'] if t['id'] == tid)

    def test_a_numbering_and_defaults(self):
        a, b = self.trip(), self.trip()
        self.assertRegex(a['no'], rf'^{self.year}-A-\d{{5}}$')
        self.assertEqual(int(b['no'][-5:]), int(a['no'][-5:]) + 1)
        t = self.get_trip(a['id'])
        self.assertEqual((t['status'], t['source'], t['locked'], t['date']), ('draft', 'app', False, date.today().isoformat()))
        st = self.ac.get('/api/state')
        self.assertEqual(len([p for p in st['tripPassengers'] if p['tripId'] == a['id']]), 2)

    def test_b_bad_input(self):
        for body in ({}, {'categoryId': 'nope'}, {'categoryId': 'cat1', 'driverId': 'nope'}):
            with self.assertRaises(ApiError) as e:
                self.ac.post('/api/trips/new', body)
            self.assertEqual(e.exception.code, 400, body)

    def test_c_amend_keeps_the_old_value(self):
        t = self.trip()
        with self.assertRaises(ApiError):  # a reason is required
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'destination', 'value': 'X', 'reason': ''})
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'destination', 'value': 'Airport', 'reason': 'Passenger changed the plan'})
        self.assertEqual(self.get_trip(t['id'])['destination'], 'Airport')
        am = [a for a in self.ac.get('/api/state')['tripAmendments'] if a['tripId'] == t['id']]
        self.assertEqual((am[0]['old'], am[0]['new'], am[0]['field']), ('Factory-Capital-Factory', 'Airport', 'destination'))
        for bad in ('no', 'linkHash', 'id', 'source', 'nonsense'):
            with self.assertRaises(ApiError, msg=bad):
                self.ac.post('/api/trips/amend', {'id': t['id'], 'field': bad, 'value': 'x', 'reason': 'test reason'})

    def test_d_closing_locks_and_cancel_wins(self):
        t = self.trip()
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'status', 'value': 'closed', 'reason': 'Closed by office'})
        self.assertTrue(self.get_trip(t['id'])['locked'])
        self.ac.post('/api/trips/cancel', {'id': t['id'], 'reason': 'Wrong car, made again'})
        self.assertEqual(self.get_trip(t['id'])['status'], 'cancelled')
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/cancel', {'id': t['id'], 'reason': 'again'})

    def test_e_approval(self):
        t = self.trip()
        self.ac.post('/api/trips/approve', {'id': t['id'], 'yes': True})
        x = self.get_trip(t['id'])
        self.assertEqual(x['gaApproved'], 'yes')
        self.assertTrue(x['gaBy'])
        self.assertTrue(x['gaAt'])

    def test_f_dispatcher_limits(self):
        ac = self.ac
        prof = next(p for p in ac.get('/api/users')['profiles'] if p['id'] == 'dispatcher')
        ac.post('/api/users/save', {'username': 'dina.d', 'full_name': 'Dina Dispatcher', 'password': 'Dispatch-77x', 'must_change': False,
                                    'role': prof['name'], 'perms': prof['perms'], 'scopes': ['cat1']})
        c = self.S.client()
        c.login('dina.d', 'Dispatch-77x')
        t = c.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1'})
        with self.assertRaises(ApiError) as e:  # other category
            c.post('/api/trips/new', {'categoryId': 'cat2'})
        self.assertEqual(e.exception.code, 403)
        for path, body in (('/api/trips/amend', {'id': t['id'], 'field': 'notes', 'value': 'x', 'reason': 'because'}),
                           ('/api/trips/approve', {'id': t['id'], 'yes': True})):
            with self.assertRaises(ApiError) as e:
                c.post(path, body)
            self.assertEqual(e.exception.code, 403, path)
        # a locked trip cannot be edited through a normal save either
        lt = self.trip()
        self.ac.post('/api/trips/amend', {'id': lt['id'], 'field': 'status', 'value': 'closed', 'reason': 'Closed by office'})
        raw = next(x for x in self.ac.get('/api/state')['trips'] if x['id'] == lt['id'])
        with self.assertRaises(ApiError) as e:
            c.post('/api/commit', {'label': 'x', 'ops': [{'e': 'trips', 'id': lt['id'], 'op': 'put', 'ver': raw['ver'], 'row': {**{k: v for k, v in raw.items() if k != 'ver'}, 'notes': 'sneaky'}}]})
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(sorted(x['id'] for x in c.get('/api/state')['trips'] if x['id'] == lt['id']), [lt['id']])

    def test_g_insights(self):
        t = self.trip(cat='cat1')
        for field, value in (('startKm', 500), ('endKm', 400), ('status', 'finished')):  # status only changes through the amend route
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': field, 'value': value, 'reason': 'test reading'})
        ins = self.ac.get('/api/insights')[t['id']]
        self.assertEqual(ins['trust'], 'red')
        self.assertIn('R_END_LE_START', ins['reasons'])
        self.assertIn('R_NO_PAPER', ins['reasons'])


if __name__ == '__main__':
    unittest.main()
