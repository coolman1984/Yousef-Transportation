"""Office screens for the driver link: Settings -> Mailbox, the trip panel (WhatsApp, copy, new link), printing."""
import base64
import json
import unittest
from urllib.parse import unquote

from test_e2e_browser import BrowserBase, SKIP
from test_gateway_client import GatewayProcess, SECRET, LINK_SECRET, node_ok, put


@SKIP
@unittest.skipUnless(node_ok(), 'node is needed')
class LinkUiTest(BrowserBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gw = GatewayProcess()
        ac = make_client(cls.S)
        cls.ac = ac
        ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car'), put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True, type='Sedan'),
            put('drivers', 'd1', name='Driver One', active=True, mobile='01012345678'), put('people', 'p1', name='Sara Adel', isRequester=True, isPassenger=True)]})
        cls.trip = ac.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'destination': 'Factory-Capital-Factory'})

    @classmethod
    def tearDownClass(cls):
        cls.gw.stop()
        super().tearDownClass()

    def test_a_mailbox_tab_and_trip_panel(self):
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/settings?tab=gateway')
        pg.wait_for_selector('#gw-url')
        self.assertIn('Not set up', pg.inner_text('main'))
        # the trip panel says the mailbox is not set up yet
        pg.goto(self.S.base + '/#/trips')
        pg.wait_for_selector('tbody tr')
        pg.click('tbody tr')
        pg.wait_for_selector('[data-a="print"]')
        self.assertIn('not set up', pg.inner_text('.drawer'))
        pg.keyboard.press('Escape')
        # set it up from the screen
        code = base64.urlsafe_b64encode(json.dumps({'v': 1, 'u': self.gw.url, 'o': SECRET, 'l': LINK_SECRET}).encode()).rstrip(b'=').decode()
        pg.goto(self.S.base + '/#/settings?tab=gateway')
        pg.wait_for_selector('#gw-code')
        pg.fill('#gw-code', code)
        pg.click('[data-gw="code"]')
        pg.wait_for_selector('[data-gw="test"]:not([disabled])')
        pg.click('[data-gw="test"]')
        pg.wait_for_selector('text=The mailbox answered')
        pg.click('[data-gw="pull"]')
        pg.wait_for_selector('.badge.ok >> text=Connected')
        pg.click('[data-gw="show"]')
        pg.wait_for_selector('textarea[data-select]')
        self.assertIn(SECRET, pg.eval_on_selector('input[data-select]', 'e => e.value'))
        # the trip panel now offers WhatsApp
        pg.goto(self.S.base + '/#/trips')
        pg.wait_for_selector('tbody tr')
        pg.click('tbody tr')
        pg.wait_for_selector('[data-a="wa"]')
        pg.context.route('https://wa.me/**', lambda r: r.fulfill(body='ok'))
        with pg.expect_popup() as pop:
            pg.click('[data-a="wa"]')
        url = pop.value.url
        self.assertTrue(url.startswith('https://wa.me/201012345678?text='), url)
        text = unquote(url.split('text=', 1)[1])
        self.assertIn(self.gw.url + '/t/', text)
        self.assertIn(self.trip['no'], text)
        pg.wait_for_selector('[data-a="newlink"]')
        self.assertEqual(next(t for t in self.ac.get('/api/state')['trips'] if t['id'] == self.trip['id'])['status'], 'sent')
        # copy shows the link in a box
        pg.click('[data-a="copylink"]')
        pg.wait_for_selector('#lk')
        self.assertIn('/t/', pg.eval_on_selector('#lk', 'e => e.value'))
        pg.keyboard.press('Escape')
        self.assertEqual(self.errors, [])

    def test_b_print_sheet(self):
        pg = self.open({'lang': 'ar'})
        pg.goto(self.S.base + '/#/trips')
        pg.wait_for_selector('tbody tr')
        pg.click('tbody tr')
        pg.wait_for_selector('[data-a="print"]')
        pg.evaluate("() => { window.__printed = 0; window.print = () => { window.__printed++; }; }")
        pg.click('[data-a="print"]')
        pg.wait_for_selector('#print-sheet', state='attached')
        html = pg.inner_html('#print-sheet')
        self.assertIn(self.trip['no'], html)
        self.assertIn('<svg', html)                                   # the QR code
        for label in ('اسم الراكب', 'توقيع السائق', 'الكيلومتر البادئ للرحلة'):
            self.assertIn(label, html)
        self.assertIn('Sara Adel', html)
        pg.wait_for_timeout(200)
        self.assertEqual(pg.evaluate('window.__printed'), 1)
        self.assertEqual(self.errors, [])


def make_client(srv):
    from harness import make_authority
    return make_authority(srv) if False else _authority(srv)


def _authority(srv):
    from harness import ADMIN
    c = srv.client()
    c.login(ADMIN[0], ADMIN[1])
    return c


if __name__ == '__main__':
    unittest.main()
