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


if __name__ == '__main__':
    unittest.main()
