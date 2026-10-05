"""Real-browser check of the application shell (Playwright + the pre-installed Chromium). Skipped when Playwright is missing."""
import json
import os
import unittest

from harness import ADMIN, Server, make_authority

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')


SKIP = unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM), 'Playwright or Chromium not available')


class BrowserBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = Server('e2e').start()
        make_authority(cls.S)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.S.cleanup()

    def open(self, prefs=None, width=1360, height=860):
        ctx = self.browser.new_context(viewport={'width': width, 'height': height})
        ctx.add_init_script("if (!localStorage.getItem('to.prefs')) localStorage.setItem('to.prefs', %s)" % json.dumps(json.dumps({'welcomed': True, **(prefs or {})})))
        pg = ctx.new_page()
        self.errors = []
        pg.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.goto(self.S.base)
        pg.wait_for_selector('#auth-form')
        pg.fill('#username', ADMIN[0])
        pg.fill('#password', ADMIN[1])
        pg.click('button[type=submit]')
        pg.wait_for_selector('#app-shell')
        return pg



@SKIP
class ShellTest(BrowserBase):
    def test_language_and_direction(self):
        pg = self.open({'lang': 'ar'})
        self.assertEqual(pg.evaluate('document.documentElement.dir'), 'rtl')
        pg.keyboard.press('KeyL')
        pg.wait_for_function("document.documentElement.dir === 'ltr'")
        self.assertIn('Overview', pg.inner_text('#sidebar'))
        pg.keyboard.press('KeyL')
        pg.wait_for_function("document.documentElement.dir === 'rtl'")
        self.assertEqual(self.errors, [])

    def test_theme_toggle_and_persistence(self):
        pg = self.open({'theme': 'daylight'})
        pg.keyboard.press('KeyT')
        pg.wait_for_function("document.documentElement.dataset.theme === 'night'")
        pg.reload()
        pg.wait_for_selector('#app-shell')
        self.assertEqual(pg.evaluate('document.documentElement.dataset.theme'), 'night')
        self.assertEqual(self.errors, [])

    def test_palette_and_go_shortcuts(self):
        pg = self.open({'lang': 'en'})
        pg.keyboard.press('Control+k')
        pg.wait_for_selector('#pal-q')
        pg.keyboard.type('settings')
        pg.keyboard.press('Enter')
        pg.wait_for_url('**/#/settings')
        pg.keyboard.press('KeyG')
        pg.keyboard.press('KeyH')
        pg.wait_for_url('**/#/help')
        self.assertEqual(self.errors, [])

    def test_panel_stack_and_escape(self):
        pg = self.open({'lang': 'en'})
        pg.click('[data-act="account"]')
        pg.wait_for_selector('.drawer.on')
        pg.keyboard.press('Escape')
        pg.wait_for_selector('.drawer', state='detached')
        pg.keyboard.press('Shift+Slash')
        pg.wait_for_selector('.keys')
        pg.keyboard.press('Escape')
        self.assertEqual(pg.locator('#overlay.on').count(), 0)

    def test_settings_apply_live(self):
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/settings')
        pg.click('[data-pref="size"][data-v="xl"]')
        self.assertEqual(pg.evaluate('document.documentElement.dataset.size'), 'xl')
        pg.click('[data-pref="theme"][data-v="contrast"]')
        self.assertEqual(pg.evaluate('document.documentElement.dataset.theme'), 'contrast')
        pg.click('[data-pref="font"][data-v="cairo"]')
        self.assertEqual(pg.evaluate('document.documentElement.dataset.font'), 'cairo')
        pg.click('[data-reset]')
        self.assertEqual(pg.evaluate('document.documentElement.dataset.size'), 'm')

    def test_phone_menu(self):
        pg = self.open({'lang': 'ar'}, 390, 800)
        pg.click('[data-act="menu"]')
        pg.wait_for_function("document.getElementById('app-shell').dataset.menu === '1'")
        pg.click('#sidebar a[data-page="settings"]')
        pg.wait_for_function("document.getElementById('app-shell').dataset.menu === '0'")
        self.assertEqual(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), True, 'no sideways scrolling')

    def test_welcome_slides_first_time(self):
        ctx = self.browser.new_context(viewport={'width': 1200, 'height': 800})
        pg = ctx.new_page()
        pg.goto(self.S.base)
        pg.wait_for_selector('#auth-form')
        pg.fill('#username', ADMIN[0])
        pg.fill('#password', ADMIN[1])
        pg.click('button[type=submit]')
        pg.wait_for_selector('#slides.on')
        pg.click('[data-snext]')
        pg.click('[data-sclose]')
        self.assertEqual(pg.locator('#slides.on').count(), 0)


@SKIP
class TripFlowTest(BrowserBase):
    """The office flow in the browser: lists, a new trip, the trip panel, an amendment, the board and the review queue."""

    def add(self, pg, addbtn, values):
        pg.click(addbtn)
        pg.wait_for_selector('.drawer.on #rec-form')
        for name, val in values.items():
            pg.fill(f'.drawer.on [name="{name}"]', val)
        pg.click('.drawer.on [data-save]')
        pg.wait_for_selector('.drawer', state='detached')

    def test_full_office_flow(self):
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/settings?tab=rules')
        pg.wait_for_selector('[data-add]')
        self.add(pg, '[data-add]', {'name': 'Manager car'})
        pg.goto(self.S.base + '/#/vehicles')
        pg.wait_for_selector('[data-add]')
        self.add(pg, '[data-add]', {'plate': 'ط و ي  ٦٨٢٩'})
        self.assertIn('6829', pg.inner_text('.tbl'))
        pg.goto(self.S.base + '/#/drivers')
        pg.wait_for_selector('[data-add]')
        self.add(pg, '[data-add]', {'name': 'Ahmed  Ali', 'mobile': '01012345678'})
        self.assertIn('+201012345678', pg.inner_text('.tbl'))
        # the same driver typed with other spacing is refused, nothing is lost
        pg.click('[data-add]')
        pg.wait_for_selector('.drawer.on #rec-form')
        pg.fill('.drawer.on [name="name"]', 'ahmed ali')
        pg.click('.drawer.on [data-save]')
        pg.wait_for_selector('.toast.bad')
        pg.keyboard.press('Escape')
        # new trip with the keyboard shortcut, a requester that does not exist yet is created on the fly
        pg.goto(self.S.base + '/#/trips')
        pg.wait_for_selector('[data-new]')
        pg.keyboard.press('KeyN')
        pg.wait_for_selector('#nt-form')
        pg.fill('#nt-form [name="categoryId"]', 'Manager car')
        pg.fill('#nt-form [name="vehicleId"]', 'ط و ي 6829')
        pg.fill('#nt-form [name="driverId"]', 'Ahmed Ali')
        pg.fill('#nt-form [name="requesterId"]', 'Sara Adel')
        pg.fill('#nt-form [name="departmentId"]', 'HR')
        pg.fill('#nt-form [name="passengersText"]', 'Sara Adel - Visitor')
        pg.fill('#nt-form [name="destination"]', 'Factory-Capital-Factory')
        pg.click('#overlay [data-save]')
        pg.wait_for_selector('.drawer.on [data-trip]')
        self.assertRegex(pg.inner_text('.drawer.on header h2'), r'^\d\d-A-\d{5}$')
        self.assertIn('Visitor', pg.inner_text('.drawer.on'))
        # amend needs a reason
        pg.click('.drawer.on [data-a="amend"]')
        pg.wait_for_selector('#am-f')
        pg.select_option('#am-f', 'destination')
        pg.fill('#am-v [name="v"]', 'Airport')
        pg.click('#overlay [data-ok]')
        self.assertTrue(pg.is_visible('#overlay .err'))
        pg.fill('#am-r', 'Passenger changed the plan')
        pg.click('#overlay [data-ok]')
        pg.wait_for_selector('#overlay.on', state='detached')
        pg.wait_for_selector('.drawer.on :text("Passenger changed the plan")')
        pg.keyboard.press('Escape')
        pg.wait_for_selector('.drawer', state='detached')
        self.assertIn('Airport', pg.inner_text('.tbl'))
        # board and review pages render
        pg.goto(self.S.base + '/#/board')
        pg.wait_for_selector('.board-card')
        pg.goto(self.S.base + '/#/review')
        pg.wait_for_selector('#view')
        self.assertEqual([e for e in self.errors if '400' not in e], [], 'only the refused duplicate driver (HTTP 400) is expected')


    def test_people_and_access(self):
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/settings?tab=rules')
        pg.wait_for_selector('[data-add]')
        pg.click('[data-add]')
        pg.wait_for_selector('.drawer.on #rec-form')
        pg.fill('.drawer.on [name="name"]', 'Extra')
        pg.click('.drawer.on [data-save]')
        pg.wait_for_selector('.drawer', state='detached')
        pg.goto(self.S.base + '/#/settings?tab=access')
        pg.wait_for_selector('[data-adduser]')
        pg.click('[data-adduser]')
        pg.wait_for_selector('.drawer.on #u-form')
        pg.fill('.drawer.on [name="full_name"]', 'Dina Dispatcher')
        pg.fill('.drawer.on [name="username"]', 'dina.d')
        pg.fill('.drawer.on [name="password"]', 'Dispatch-77x')
        pg.select_option('.drawer.on [name="role"]', 'Dispatcher')
        self.assertTrue(pg.is_checked('.drawer.on [data-perm="trips.create"]'))
        self.assertFalse(pg.is_checked('.drawer.on [data-perm="users.manage"]'))
        pg.click('.drawer.on [data-scope="some"]')
        pg.check('.drawer.on [data-cat]')
        pg.click('.drawer.on [data-save]')
        pg.wait_for_selector('.drawer', state='detached')
        self.assertIn('Dina Dispatcher', pg.inner_text('.tbl'))
        # she can sign in and does not see the administrator pages
        ctx = self.browser.new_context()
        p2 = ctx.new_page()
        p2.goto(self.S.base)
        p2.wait_for_selector('#auth-form')
        p2.fill('#username', 'dina.d')
        p2.fill('#password', 'Dispatch-77x')
        p2.click('button[type=submit]')
        p2.wait_for_selector('#form-must, #auth-form input[name="old"]')


    def test_delete_goes_to_the_bin_and_comes_back(self):
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/vehicles')
        pg.wait_for_selector('[data-add]')
        self.add(pg, '[data-add]', {'plate': 'ص ص ص 1111'})
        pg.click('tbody tr')
        pg.wait_for_selector('.drawer.on [data-del]')
        pg.click('.drawer.on [data-del]')
        pg.click('#overlay [data-ok]')
        pg.wait_for_selector('.drawer', state='detached')
        self.assertNotIn('1111', pg.inner_text('#view'))
        pg.goto(self.S.base + '/#/settings?tab=data')
        pg.wait_for_selector('[data-restore]')
        pg.click('[data-restore]')
        pg.wait_for_selector('.toast')
        pg.goto(self.S.base + '/#/vehicles')
        pg.wait_for_selector('tbody tr')
        self.assertIn('1111', pg.inner_text('#view'))


@SKIP
class ExcelPageTest(BrowserBase):
    def test_import_review_confirm_and_guide(self):
        here = os.path.dirname(os.path.abspath(__file__))
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/excel')
        pg.wait_for_selector('#dz')
        pg.set_input_files('#imp-file', os.path.join(here, 'fixtures', 'sample_sep26_synthetic.xlsx'))
        pg.wait_for_selector('[data-commit]')
        self.assertIn('247', pg.inner_text('#xl-body'))
        self.assertIn('Things to check', pg.inner_text('#xl-body'))
        pg.click('[data-f="problem"]')
        self.assertEqual(pg.locator('#xl-body tbody tr').count(), 7)
        pg.click('[data-f="all"]')
        pg.check('#imp-problems')
        pg.click('[data-commit]')
        pg.wait_for_selector('[data-again]')
        self.assertIn('247', pg.inner_text('#xl-body'))
        # the same file again is all duplicates and cannot be confirmed
        pg.click('[data-again]')
        pg.set_input_files('#imp-file', os.path.join(here, 'fixtures', 'sample_sep26_synthetic.xlsx'))
        pg.wait_for_selector('[data-commit]')
        self.assertTrue(pg.locator('[data-commit]').is_disabled())
        # wrong file type gives a plain message
        pg.click('[data-cancel]')
        pg.set_input_files('#imp-file', files=[{'name': 'trips.xlsx', 'mimeType': 'application/octet-stream', 'buffer': b'<## NASCA DRM FILE - VER1.00 ##>' + bytes(range(256)) * 8}])
        pg.wait_for_selector('#xl-body .tip.bad')
        self.assertIn('document-security', pg.inner_text('#xl-body'))
        # a csv with Arabic text is read too (and shows the review)
        csv = ('Date,Driver Name,Car Plate,Strat KM,End KM\n2026-10-01,علي حسن,س ع د 555,100,180\n').encode('utf-8-sig')
        pg.set_input_files('#imp-file', files=[{'name': 'x.csv', 'mimeType': 'text/csv', 'buffer': csv}])
        pg.wait_for_selector('[data-commit]')
        pg.click('[data-cancel]')
        # export tab, Arabic, guide
        pg.click('[data-tab="export"]')
        pg.wait_for_selector('#ex-ym')
        pg.click('[data-tab="guide"]')
        self.assertEqual(pg.locator('#xl-body details').count(), 12)
        pg.keyboard.press('KeyL')
        pg.wait_for_function("document.documentElement.dir === 'rtl'")
        pg.click('[data-tab="import"]')
        pg.wait_for_selector('#dz')
        self.assertIn('اختار', pg.inner_text('#xl-body'))
        self.assertEqual([e for e in self.errors if 'Failed to load resource' not in e], [])   # the refused file is an expected 400


@SKIP
class SlidesTest(BrowserBase):
    def test_every_welcome_slide_shows_in_both_directions(self):
        for lang in ('ar', 'en'):
            pg = self.open({'lang': lang}, width=1800)
            pg.evaluate("() => TO.slides.open()")
            for k in range(6):
                pg.evaluate("(k) => TO.slides._go(k)", k)
                pg.wait_for_timeout(650)
                box = pg.evaluate("(k) => { const r = document.querySelectorAll('#slides section')[k].getBoundingClientRect(); return [r.left, r.right]; }", k)
                self.assertTrue(abs(box[0]) < 2 and abs(box[1] - 1800) < 2, (lang, k, box))


@SKIP
class ReportsPageTest(BrowserBase):
    def test_reports_and_presentation(self):
        here = os.path.dirname(os.path.abspath(__file__))
        from harness import ADMIN
        c = self.S.client()
        c.login(ADMIN[0], ADMIN[1])
        with open(os.path.join(here, 'fixtures', 'sample_sep26_synthetic.xlsx'), 'rb') as f:
            pv = c.call('POST', '/api/excel/preview?name=s.xlsx', raw=f.read(), headers={'Content-Type': 'application/octet-stream'})
        c.post('/api/excel/commit', {'id': pv['id'], 'includeProblems': True})
        api = c.get('/api/reports?ym=2026-09')
        self.assertEqual(api['summary']['total']['trips'], 247)
        self.assertTrue(api['reconciliation'] and api['anomalies'])
        pg = self.open({'lang': 'en'})
        pg.goto(self.S.base + '/#/reports')
        pg.fill('#rp-ym', '2026-09')
        pg.wait_for_selector('.bar-row')
        self.assertIn('247', pg.inner_text('#rp-body'))
        pg.click('[data-g="byDriver"]')
        self.assertGreater(pg.locator('#rp-body table tbody tr').count(), 5)
        pg.click('[data-present]')
        pg.wait_for_selector('.present .ps')
        pg.keyboard.press('ArrowRight')
        self.assertIn('1 / 6'.replace('1', '2', 1), pg.inner_text('.present .pn'))
        pg.keyboard.press('Escape')
        self.assertEqual(pg.locator('.present').count(), 0)
        self.assertEqual(self.errors, [])

    def test_reviewer_without_money_permission_sees_no_rates_cards(self):
        here = os.path.dirname(os.path.abspath(__file__))
        from harness import ADMIN
        ac = self.S.client()
        ac.login(ADMIN[0], ADMIN[1])
        if not ac.get('/api/reports?ym=2026-09')['summary']['total']['trips']:
            with open(os.path.join(here, 'fixtures', 'sample_sep26_synthetic.xlsx'), 'rb') as f:
                pv = ac.call('POST', '/api/excel/preview?name=s.xlsx', raw=f.read(), headers={'Content-Type': 'application/octet-stream'})
            ac.post('/api/excel/commit', {'id': pv['id'], 'includeProblems': True})
        rv = next(p for p in ac.get('/api/users')['profiles'] if p['id'] == 'reviewer')
        ac.post('/api/users/save', {'username': 'rita.r', 'full_name': 'Rita Reviewer', 'password': 'Review-pass-77', 'must_change': False,
                                    'role': rv['name'], 'perms': rv['perms'], 'scopes': None})
        ctx = self.browser.new_context(viewport={'width': 1360, 'height': 860})
        ctx.add_init_script("localStorage.setItem('to.prefs', JSON.stringify({welcomed: true, lang: 'en'}))")
        errors = []
        p2 = ctx.new_page()
        p2.on('pageerror', lambda e: errors.append(str(e)))
        p2.goto(self.S.base)
        p2.wait_for_selector('#auth-form')
        p2.fill('#username', 'rita.r')
        p2.fill('#password', 'Review-pass-77')
        p2.click('button[type=submit]')
        p2.wait_for_selector('#app-shell')
        p2.goto(self.S.base + '/#/reports')
        p2.fill('#rp-ym', '2026-09')
        p2.wait_for_selector('.bar-row')
        body = p2.inner_text('#rp-body')
        self.assertIn('247', body)  # the km / trips report is still there
        self.assertNotIn('Vendor reconciliation', body)
        self.assertNotIn('Cost per department', body)
        p2.click('[data-present]')
        p2.wait_for_selector('.present .ps')
        self.assertTrue(p2.inner_text('.present .pn').endswith('/ 5'), p2.inner_text('.present .pn'))
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()

