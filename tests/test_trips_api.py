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
        for field, value in (('startKm', 500), ('endKm', 500), ('status', 'finished')):  # equal readings = 0 km; status only changes through the amend route
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': field, 'value': value, 'reason': 'test reading'})
        ins = self.ac.get('/api/insights')[t['id']]
        self.assertEqual(ins['trust'], 'red')
        self.assertIn('R_END_LE_START', ins['reasons'])
        self.assertNotIn('R_NO_PAPER', ins['reasons'])   # an office-only trip has no driver page to send the paper

    def test_i_bad_values_are_refused_and_nothing_is_saved(self):
        t = self.trip()
        before = self.get_trip(t['id'])
        bad = [('endKm', 'abc'), ('endKm', -5), ('endKm', 12.5), ('startKm', 99999999999), ('status', 'flying'), ('date', 'abc'), ('date', '2026-13-45'),
               ('date', '1999-01-01'), ('date', '2099-01-01'), ('startAt', 'nonsense'), ('destination', 'x' * 201)]
        for field, value in bad:
            with self.assertRaises(ApiError, msg=f'{field}={value!r}') as e:
                self.ac.post('/api/trips/amend', {'id': t['id'], 'field': field, 'value': value, 'reason': 'test the check'})
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(self.get_trip(t['id']), before)
        self.assertEqual([a for a in self.ac.get('/api/state')['tripAmendments'] if a['tripId'] == t['id']], [])
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'startKm', 'value': '1,000', 'reason': 'typed with a comma'})
        self.assertEqual(self.get_trip(t['id'])['startKm'], 1000)
        with self.assertRaises(ApiError):    # end below start
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'endKm', 'value': 900, 'reason': 'lower than start'})

    def test_j_times_order_and_new_trip_checks(self):
        t = self.trip()
        today = date.today().isoformat()
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'startAt', 'value': today + 'T10:00:00', 'reason': 'from the paper'})
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'endAt', 'value': today + 'T09:00:00', 'reason': 'before the start'})
        self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'endAt', 'value': today + 'T12:30:00', 'reason': 'from the paper'})
        for body in ({'date': 'abc'}, {'date': '2026-13-45'}, {'date': '1999-05-05'}, {'date': '2031-05-05'}, {'destination': 'y' * 500}):
            with self.assertRaises(ApiError, msg=str(body)) as e:
                self.trip(**body)
            self.assertEqual(e.exception.code, 400)

    def test_k_cancelled_and_closed_are_final_declined_gets_no_link(self):
        t = self.trip()
        self.ac.post('/api/trips/cancel', {'id': t['id'], 'reason': 'Not needed any more'})
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'status', 'value': 'finished', 'reason': 'bring it back'})
        self.assertEqual(self.get_trip(t['id'])['status'], 'cancelled')
        c = self.trip()
        self.ac.post('/api/trips/amend', {'id': c['id'], 'field': 'status', 'value': 'closed', 'reason': 'Closed by office'})
        with self.assertRaises(ApiError):
            self.ac.post('/api/trips/amend', {'id': c['id'], 'field': 'status', 'value': 'started', 'reason': 'go back'})
        g = self.trip()
        self.ac.post('/api/trips/approve', {'id': g['id'], 'yes': False})
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/trips/link', {'id': g['id']})
        self.assertIn('declined', str(e.exception))

    def test_l_deleting_something_in_use_is_refused(self):
        self.ac.post('/api/commit', {'label': 'x', 'ops': [put('vehicles', 'vdel', plate='س ص ع 1111', plateKey='سصع1111', active=True),
                                                           put('drivers', 'ddel', name='Driver Del', active=True), put('people', 'pdel', name='Req Del', isRequester=True)]})
        self.trip(vehicleId='vdel', driverId='ddel', requesterId='pdel')
        for e, i in (('vehicles', 'vdel'), ('drivers', 'ddel'), ('tripCategories', 'cat1'), ('people', 'pdel')):
            with self.assertRaises(ApiError, msg=e) as ex:
                self.ac.post('/api/commit', {'label': 'del', 'ops': [{'e': e, 'id': i, 'op': 'del'}]})
            self.assertEqual(ex.exception.code, 400)
            self.assertIn('trip(s)', str(ex.exception))
        # an unused one can still be deleted
        self.ac.post('/api/commit', {'label': 'x', 'ops': [put('vehicles', 'vfree', plate='ع ع ع 2222', plateKey='ععع2222', active=True)]})
        ver = next(v['ver'] for v in self.ac.get('/api/state')['vehicles'] if v['id'] == 'vfree')
        self.ac.post('/api/commit', {'label': 'del', 'ops': [{'e': 'vehicles', 'id': 'vfree', 'op': 'del', 'ver': ver}]})

    def test_m_no_copies_and_no_negative_money(self):
        for ops in ([put('tripCategories', 'dupcat', name='manager  CAR')], [put('departments', 'dupdep', name=' hr ')],
                    [put('people', 'dupp', name='Sara Adel')],
                    [put('tripCategories', 'neg', name='Negative', ratePerKm=-5)], [put('tripCategories', 'neg2', name='Negative2', openLimitHours=-3)]):
            with self.assertRaises(ApiError, msg=str(ops)) as ex:
                self.ac.post('/api/commit', {'label': 'x', 'ops': ops})
            self.assertEqual(ex.exception.code, 400)
        # the same name in another department is allowed (two real people can share a name)
        self.ac.post('/api/commit', {'label': 'x', 'ops': [put('people', 'sara2', name='Sara Adel', departmentId='dep1')]})

    def test_n_department_comes_from_the_requester_and_places_merge_in_reports(self):
        self.ac.post('/api/commit', {'label': 'x', 'ops': [put('departments', 'depacc', name='Accounts'), put('people', 'pacc', name='Mona R', departmentId='depacc', isRequester=True),
                                                           put('places', 'pl1', name='Cairo Airport', key='cairoairport', aliases=['مطار القاهرة', 'المطار'], active=True)]})
        t = self.trip(requesterId='pacc', departmentId='')
        self.assertEqual(self.get_trip(t['id'])['departmentId'], 'depacc')
        t2 = self.trip(requesterId='pacc', departmentId='dep1')    # an explicit department wins
        self.assertEqual(self.get_trip(t2['id'])['departmentId'], 'dep1')
        today = date.today().isoformat()[:7]
        for dest in ('Cairo Airport', 'مطار القاهرة', 'المطار', 'Cairo Airport'):
            self.trip(destination=dest)
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
        import reports
        st = self.ac.get('/api/state')
        routes = {r['label']: r['trips'] for r in reports.summaries(st, today)['topRoutes']}
        self.assertEqual(routes.get('Cairo Airport'), 4)
        self.assertNotIn('المطار', routes)
        dep = {d['label']: d['trips'] for d in reports.summaries(st, today)['byDepartment']}
        self.assertIn('Accounts', dep)

    def test_h_office_only_trip_turns_green_after_review(self):
        t = self.trip()
        for field, value in (('startKm', 500), ('endKm', 640), ('status', 'finished')):
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': field, 'value': value, 'reason': 'entered from the paper'})
        ins = self.ac.get('/api/insights')[t['id']]
        self.assertEqual((ins['trust'], ins['reasons']), ('yellow', ['Y_CLOSED_BY_OFFICE', 'Y_AMENDED']))
        self.ac.post('/api/trips/review', {'id': t['id']})
        x = self.get_trip(t['id'])
        self.assertTrue(x['reviewedBy'] and x['reviewedAt'])
        self.assertEqual(self.ac.get('/api/insights')[t['id']]['trust'], 'green')
        with self.assertRaises(ApiError):   # a draft is not reviewable
            self.ac.post('/api/trips/review', {'id': self.trip()['id']})
        with self.assertRaises(ApiError):   # the review stamp cannot be written by hand
            self.ac.post('/api/trips/amend', {'id': t['id'], 'field': 'reviewedAt', 'value': '2099-01-01T00:00:00', 'reason': 'sneaky try'})


if __name__ == '__main__':
    unittest.main()
