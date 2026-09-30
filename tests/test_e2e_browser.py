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


@unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM), 'Playwright or Chromium not available')
class ShellTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
