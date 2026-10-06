"""F07: a trip is priced with the rate that was valid on its date. A new rate never changes last month's numbers.
Unit rules (server/pricing.py) and the real server: category save -> history -> Reports, reconciliation and cost allocation."""
import os
import sys
import unittest

from harness import ADMIN, Server, make_authority

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import pricing  # noqa: E402


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class RuleTest(unittest.TestCase):
    def test_a_the_rate_of_the_trip_date_is_used(self):
        cat = {'ratePerKm': 20, 'ratePerOtHour': 60, 'rateHistory': [{'until': '2026-09-15', 'ratePerKm': 10, 'ratePerOtHour': 50}]}
        self.assertEqual(pricing.rates_on(cat, '2026-09-14'), (10, 50))
        self.assertEqual(pricing.rates_on(cat, '2026-09-15'), (20, 60), 'the change day already uses the new rate')
        self.assertEqual(pricing.rates_on(cat, '2026-10-01'), (20, 60))
        self.assertEqual(pricing.rates_on(cat, ''), (20, 60), 'no date: current rate')
        self.assertEqual(pricing.rates_on({}, '2026-01-01'), (0, 0), 'no rate set is 0, not an error')
        self.assertEqual(pricing.rates_on({'ratePerKm': 5, 'rateHistory': 'junk'}, '2026-01-01'), (5, 0), 'a damaged history is ignored')

    def test_b_a_change_keeps_the_old_rate_for_earlier_trips(self):
        before = {'ratePerKm': 10, 'ratePerOtHour': 50, 'rateHistory': []}
        h = pricing.stamp(before, {'ratePerKm': 20, 'ratePerOtHour': 50}, '2026-09-15')
        self.assertEqual(h, [{'until': '2026-09-15', 'ratePerKm': 10, 'ratePerOtHour': 50}])
        h2 = pricing.stamp({**before, 'ratePerKm': 20, 'rateHistory': h}, {'ratePerKm': 30, 'ratePerOtHour': 50}, '2026-10-20')
        self.assertEqual([x['until'] for x in h2], ['2026-09-15', '2026-10-20'])
        cat = {'ratePerKm': 30, 'ratePerOtHour': 50, 'rateHistory': h2}
        self.assertEqual([pricing.rates_on(cat, d)[0] for d in ('2026-09-01', '2026-09-20', '2026-11-01')], [10, 20, 30])

    def test_c_nothing_changes_when_the_rates_do_not(self):
        before = {'ratePerKm': 10, 'ratePerOtHour': 50, 'rateHistory': [{'until': '2026-01-01', 'ratePerKm': 8, 'ratePerOtHour': 40}]}
        self.assertEqual(pricing.stamp(before, {'ratePerKm': 10.0, 'ratePerOtHour': '50'}, '2026-09-15'), before['rateHistory'])

    def test_d_fixing_a_typo_on_the_same_day_does_not_make_history(self):
        h = pricing.stamp({'ratePerKm': 10, 'rateHistory': []}, {'ratePerKm': 20}, '2026-09-15')
        again = pricing.stamp({'ratePerKm': 20, 'rateHistory': h}, {'ratePerKm': 22}, '2026-09-15')
        self.assertEqual(again, h)

    def test_e_a_rate_that_was_never_set_is_not_history(self):
        h = pricing.stamp({'ratePerKm': 10, 'ratePerOtHour': None, 'rateHistory': []}, {'ratePerKm': 10, 'ratePerOtHour': 50}, '2026-09-15')
        self.assertEqual(h, [], 'the first overtime rate applies to every trip, as before')
        h = pricing.stamp({'ratePerKm': 10, 'rateHistory': [{'until': '2026-03-01', 'ratePerKm': 8, 'ratePerOtHour': None}]}, {'ratePerKm': 10, 'ratePerOtHour': 50}, '2026-09-15')
        self.assertEqual(h[0]['ratePerOtHour'], 50, 'earlier entries without an overtime rate get the first one set')
        self.assertEqual(pricing.stamp(None, {'ratePerKm': 5}, '2026-09-15'), [], 'a new category starts without history')

    def test_f_a_removed_rate_is_remembered_too(self):
        h = pricing.stamp({'ratePerKm': 10, 'rateHistory': []}, {'ratePerKm': 0}, '2026-09-15')
        self.assertEqual(pricing.rates_on({'ratePerKm': 0, 'rateHistory': h}, '2026-09-01'), (10, 0))


class ReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('pricing').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car', ratePerKm=10, ratePerOtHour=50, vendor='Misr'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True),
            put('drivers', 'd1', name='Driver One', active=True),
            put('departments', 'dep1', name='HR')]})
        # three finished trips of 100 km on three dates; the vendor bills 110 km for each
        for i, d in enumerate(('2026-08-10', '2026-09-10', '2026-09-20')):
            cls.ac.post('/api/commit', {'label': 'trip', 'ops': [put('trips', f't{i}', no=f'T{i}', date=d, categoryId='cat1', vehicleId='v1', driverId='d1', departmentId='dep1',
                                                                    status='finished', startKm=1000 + i * 200, endKm=1100 + i * 200, billableKm=110, source='app', destination='X')]})

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def cat(self):
        return next(c for c in self.ac.get('/api/state')['tripCategories'] if c['id'] == 'cat1')

    def money(self, ym):
        r = self.ac.get(f'/api/reports?ym={ym}')
        return r['allocation'][0]['kmCost'] if r['allocation'] else 0, (r['reconciliation'][0]['diffMoney'] if r['reconciliation'] else 0)

    def change_rate(self, **rates):
        c = self.cat()
        self.ac.post('/api/commit', {'label': 'rate', 'ops': [{'e': 'tripCategories', 'id': 'cat1', 'op': 'put', 'ver': c['ver'], 'row': {**{k: v for k, v in c.items() if k != 'ver'}, **rates}}]})

    def test_a_a_new_rate_does_not_change_last_months_numbers(self):
        self.assertEqual(self.money('2026-08'), (1000, 100), '100 km x 10; 10 extra billed km x 10')
        self.assertEqual(self.money('2026-09'), (2000, 200))
        self.change_rate(ratePerKm=20)
        c = self.cat()
        self.assertEqual(c['ratePerKm'], 20)
        self.assertEqual(len(c['rateHistory']), 1)
        self.assertEqual((c['rateHistory'][0]['ratePerKm'], c['rateHistory'][0]['ratePerOtHour']), (10, 50))
        # every trip is older than today, so they all keep the old rate
        self.assertEqual(self.money('2026-08'), (1000, 100))
        self.assertEqual(self.money('2026-09'), (2000, 200))

    def test_b_the_client_cannot_write_the_history(self):
        c = self.cat()
        fake = [{'until': '2099-01-01', 'ratePerKm': 1, 'ratePerOtHour': 1}]
        self.ac.post('/api/commit', {'label': 'tamper', 'ops': [{'e': 'tripCategories', 'id': 'cat1', 'op': 'put', 'ver': c['ver'], 'row': {**{k: v for k, v in c.items() if k != 'ver'}, 'rateHistory': fake}}]})
        self.assertEqual(self.cat()['rateHistory'], c['rateHistory'])
        self.assertEqual(self.money('2026-09'), (2000, 200))

    def test_c_a_month_with_two_rates_adds_up_per_trip(self):
        """Edit the history through the engine's own rows (as a restore would) so one month has two rates."""
        c = self.cat()
        h = [{'until': '2026-09-15', 'ratePerKm': 10, 'ratePerOtHour': 50}]
        self.ac.post('/api/commit', {'label': 'restore', 'force': True, 'ops': [{'e': 'tripCategories', 'id': 'cat1', 'op': 'put', 'row': {**{k: v for k, v in c.items() if k != 'ver'}, 'rateHistory': h}}]})
        self.assertEqual(self.cat()['rateHistory'], h, 'the full-restore path keeps a history as given')
        # 10 Sep at 10/km and 20 Sep at 20/km (current): 100x10 + 100x20 = 3000; billed difference 10 km each: 100 + 200
        self.assertEqual(self.money('2026-09'), (3000, 300))
        rec = self.ac.get('/api/reports?ym=2026-09')['reconciliation'][0]
        self.assertEqual((rec['actualKm'], rec['billedKm'], rec['diffKm']), (200, 220, 20))

    def test_d_the_rate_history_is_money_information(self):
        prof = next(p for p in self.ac.get('/api/users')['profiles'] if p['id'] == 'dispatcher')
        self.ac.post('/api/users/save', {'username': 'disp', 'full_name': 'Disp', 'password': 'Quarter-pass77', 'must_change': False, 'role': prof['name'], 'perms': prof['perms'], 'scopes': None})
        c = self.S.client()
        c.login('disp', 'Quarter-pass77')
        cat = next(x for x in c.get('/api/state')['tripCategories'] if x['id'] == 'cat1')
        self.assertNotIn('rateHistory', cat)
        self.assertNotIn('ratePerKm', cat)


@unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM), 'Playwright or Chromium not available')
class ScreenTest(unittest.TestCase):
    """The category editor in a real browser: the rule is explained in both languages, and changing a rate keeps last month's numbers."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('pricingui').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car', ratePerKm=10, ratePerOtHour=50, vendor='Misr'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True),
            put('trips', 't1', no='T1', date='2026-08-10', categoryId='cat1', vehicleId='v1', status='finished', startKm=1000, endKm=1100, source='app', destination='X')]})
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.S.cleanup()

    def open(self, lang):
        import json
        ctx = self.browser.new_context(viewport={'width': 1360, 'height': 860})
        ctx.add_init_script("localStorage.setItem('to.prefs', %s)" % json.dumps(json.dumps({'welcomed': True, 'lang': lang})))
        pg = ctx.new_page()
        self.errors = []
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.goto(self.S.base)
        pg.wait_for_selector('#auth-form')
        pg.fill('#username', ADMIN[0])
        pg.fill('#password', ADMIN[1])
        pg.click('button[type=submit]')
        pg.wait_for_selector('#app-shell')
        pg.goto(self.S.base + '/#/settings?tab=rules')
        pg.wait_for_selector('tr[data-id="cat1"]')
        return pg

    def test_a_the_rule_is_explained_in_both_languages_and_a_rate_change_keeps_history(self):
        pg = self.open('en')
        pg.click('tr[data-id="cat1"]')
        pg.wait_for_selector('.drawer.on #rec-form')
        self.assertIn('Earlier trips keep the rate they had', pg.inner_text('.drawer.on'))
        pg.fill('.drawer.on [name="ratePerKm"]', '25')
        pg.click('.drawer.on [data-save]')
        pg.wait_for_selector('.drawer', state='detached')
        cat = next(c for c in self.ac.get('/api/state')['tripCategories'] if c['id'] == 'cat1')
        self.assertEqual((cat['ratePerKm'], [h['ratePerKm'] for h in cat['rateHistory']]), (25, [10]))
        rep = self.ac.get('/api/reports?ym=2026-08')
        self.assertEqual(rep['allocation'][0]['kmCost'], 1000, 'August is still priced at 10 per km')
        self.assertEqual(self.errors, [])
        pg2 = self.open('ar')
        pg2.click('tr[data-id="cat1"]')
        pg2.wait_for_selector('.drawer.on #rec-form')
        self.assertIn('بتفضل بالسعر القديم', pg2.inner_text('.drawer.on'))
        self.assertEqual(pg2.evaluate('document.documentElement.dir'), 'rtl')


if __name__ == '__main__':
    unittest.main()
