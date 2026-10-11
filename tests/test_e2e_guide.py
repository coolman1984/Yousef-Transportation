"""The guide, the consent card, the problem report and the licence/privacy tabs in a real browser (Playwright + Chromium); skipped without them."""
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


class Base(unittest.TestCase):
    consent = None

    @classmethod
    def setUpClass(cls):
        cls.S = Server('e2eguide').start()
        cls.ac = make_authority(cls.S, consent=cls.consent)
        cls.ac.post('/api/commit', {'label': 'cat', 'ops': [{'e': 'tripCategories', 'id': 'c1', 'op': 'put', 'row': {'name': 'Manager car', 'exportSheet': 'All'}}]})
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.S.cleanup()

    def login(self, lang='en', width=1360):
        ctx = self.browser.new_context(viewport={'width': width, 'height': 860})
        ctx.add_init_script("if (!localStorage.getItem('to.prefs')) localStorage.setItem('to.prefs', %s)" % json.dumps(json.dumps({'welcomed': True, 'lang': lang})))
        pg = ctx.new_page()
        self.errors = []
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(self.S.base)
        pg.wait_for_selector('#auth-form')
        pg.fill('#username', ADMIN[0])
        pg.fill('#password', ADMIN[1])
        pg.click('button[type=submit]')
        pg.wait_for_selector('#app-shell')
        return pg


@SKIP
class ConsentCardTest(Base):
    consent = None

    def test_a_the_first_sign_in_card_has_two_equal_buttons_and_escape_does_not_decide(self):
        pg = self.login('ar')
        pg.wait_for_selector('[data-afc="card"]')
        self.assertEqual(pg.get_attribute('[data-afc="card"] section', 'dir'), 'rtl')
        self.assertIn('أوافق', pg.inner_text('[data-afc="agree"]'))
        self.assertEqual(pg.locator('[data-afc="agree"]').evaluate('b => b.className'), pg.locator('[data-afc="decline"]').evaluate('b => b.className'))
        pg.keyboard.press('Escape')
        self.assertEqual(pg.locator('[data-afc="card"]').count(), 1)
        self.assertIsNone(self.ac.get('/api/consent/status')['install'], 'nothing was recorded by Escape')
        pg.click('[data-afc="decline"]')
        pg.wait_for_selector('[data-afc="card"]', state='detached')
        st = self.ac.get('/api/consent/status')
        self.assertEqual((st['install']['decision'], st['tracking']), ('decline', False))
        pg.reload()
        pg.wait_for_selector('#app-shell')
        pg.wait_for_timeout(800)
        self.assertEqual(pg.locator('[data-afc="card"]').count(), 0, 'asked once')
        self.assertEqual(self.errors, [])


@SKIP
class GuideTest(Base):
    consent = 'decline'

    def test_a_the_panel_shows_the_role_course_in_arabic_with_progress_and_a_separate_guide_language(self):
        pg = self.login('en')
        pg.wait_for_selector('[data-afg="fab"]')
        pg.click('[data-afg="fab"]')
        pg.wait_for_selector('[data-afg="panel"]:not([hidden])')
        course = pg.inner_text('[data-afg="course"]')
        self.assertIn('Administrator path', course)
        pg.click('[data-afg="lang"]')                                                    # the guide's own language switch
        pg.wait_for_function("document.querySelector('[data-afg=\"course\"] h3').textContent.includes('طريق المدير')")
        self.assertEqual(pg.evaluate('document.documentElement.lang'), 'en', 'the program itself stays English')
        self.assertEqual(pg.get_attribute('[data-afg="panel"]', 'dir'), 'rtl')
        self.assertEqual(self.ac.get('/api/guide/state')['progress']['lang'], 'ar', 'saved on the server')
        self.assertEqual(self.errors, [])

    def test_b_a_lesson_advances_by_itself_and_resumes_after_a_reload(self):
        pg = self.login('en')
        pg.wait_for_selector('[data-afg="fab"]')
        pg.evaluate("window.TO.guide.control().start('create-trip')")
        pg.wait_for_selector('[data-afg="coach"]:not([hidden])')
        self.assertIn('1', pg.inner_text('[data-afg="step"]'))
        pg.click('[data-afg="there"]')                                                    # «Take me there»
        pg.wait_for_url('**/#/trips')                                                     # the 'go' step finishes when the page opens
        pg.wait_for_function("() => document.querySelector('[data-afg=say]').textContent.includes('New trip order')")
        pg.click('[data-guide="trips.new"]')
        pg.wait_for_function("() => document.querySelector('[data-afg=step]').textContent.includes('3')")
        pg.reload()
        pg.wait_for_selector('[data-afg="resume"]')                                       # the saved step is offered again
        pg.click('[data-afg="resume"]')
        pg.wait_for_selector('[data-afg="coach"]:not([hidden]) [data-afg="next"]')
        self.assertEqual(self.errors, [])

    def test_c_every_page_has_a_report_button_with_an_exact_preview_before_sending(self):
        pg = self.login('en')
        for page in ('overview', 'trips', 'settings'):
            pg.goto(self.S.base + '/#/' + page)
            pg.wait_for_selector('[data-act="report"]')
        pg.click('[data-act="report"]')
        pg.wait_for_selector('[data-aft="dialog"]')
        self.assertTrue(pg.locator('[data-aft="send"]').is_disabled(), 'nothing can be sent before the preview')
        pg.fill('[data-aft="text"]', 'The link fails. Phone 01012345678')
        pg.click('[data-aft="preview-btn"]')
        pg.wait_for_selector('[data-aft="preview"]:not([hidden])')
        shown = pg.inner_text('[data-aft="preview"]')
        self.assertIn('fb.problem', shown)
        self.assertNotIn('01012345678', shown, 'redacted before it is shown')
        self.assertFalse(pg.locator('[data-aft="send"]').is_disabled())
        pg.fill('[data-aft="text"]', 'Another text')                                      # editing invalidates the preview
        self.assertTrue(pg.locator('[data-aft="send"]').is_disabled())
        pg.click('[data-aft="preview-btn"]')
        pg.wait_for_selector('[data-aft="preview"]:not([hidden])')
        pg.click('[data-aft="send"]')
        pg.wait_for_selector('#toasts .toast')
        self.assertEqual(self.ac.get('/api/telemetry/queue')['reports'], 1)
        self.assertEqual(self.errors, [])

    def test_d_privacy_and_licence_tabs_open_and_the_unbuilt_tabs_are_gone(self):
        pg = self.login('en')
        pg.goto(self.S.base + '/#/settings?tab=privacy')
        pg.wait_for_selector('[data-install-card]')
        self.assertIn('Remote help', pg.inner_text('[data-install-card]'))
        pg.goto(self.S.base + '/#/settings?tab=licence')
        pg.wait_for_selector('[data-lic-state]')
        self.assertIn('contract', pg.inner_text('[data-lic-state]').lower())
        tabs = pg.eval_on_selector_all('[data-tab]', 'els => els.map(e => e.dataset.tab)')
        self.assertNotIn('organisation', tabs)
        self.assertNotIn('money', tabs)
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
