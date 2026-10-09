"""The driver's phone page in a real (mobile) browser against the real gateway code: a full trip, offline in the middle, closing and
reopening the page, a second phone, a cancelled trip, the gallery fallback, Arabic and English."""
import hashlib
import os
import sys
import time
import unittest
import zlib
import struct

from test_gateway_client import GatewayProcess, SECRET, node_ok

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import gateway_client as G  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')
SKIP = unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM) or not node_ok(), 'Playwright, Chromium or node is not available')


def png(w=64, h=48):
    raw = b''.join(b'\x00' + bytes([(x * 4) & 255, (y * 5) & 255, 120] * 1) * 1 + b'' for y in range(h) for x in range(1))  # placeholder, replaced below
    rows = b''.join(b'\x00' + b''.join(bytes([(x * 4) & 255, (y * 5) & 255, 120]) for x in range(w)) for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


CARD = {'tripId': 'tr1', 'no': '26-A-00001', 'date': '2026-09-28', 'driverName': 'Driver One', 'plate': 'ط و ي 6829', 'vehicleType': 'Sedan',
        'destination': 'Factory - Capital - Factory', 'stops': ['Capital'], 'passengers': ['Sara Adel'], 'status': 'sent'}


@SKIP
class DriverPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = GatewayProcess()
        cls.office = G.Client(cls.gw.url, SECRET)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM, args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.gw.stop()

    def card(self, **over):
        type(self).n += 1
        token = f'Tk{self.n:02d}abcdefghijklmnopqrs'[:22]
        card = {**CARD, 'tripId': f'tr{self.n}', **over}
        self.office.put_cards([{'tokenHash': G.token_hash(token), 'tripId': card['tripId'], 'body': card, 'cancelled': bool(over.pop('cancelled', False)), 'expiresAt': int(time.time()) + 86400}])
        return token

    def page(self, token, lang='ar', camera=True, ctx=None):
        ctx = ctx or self.browser.new_context(viewport={'width': 393, 'height': 851}, device_scale_factor=2, is_mobile=True, has_touch=True, permissions=['camera'] if camera else [])
        ctx.add_init_script(f"try {{ if (!localStorage.getItem('to.lang')) localStorage.setItem('to.lang', '{lang}') }} catch (e) {{}}")
        pg = ctx.new_page()
        self.errors = []
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(f'{self.gw.url}/t/{token}')
        return pg, ctx

    def until(self, pg, fn, timeout=20):
        """wait_for_function compiles a string, which the page's strict CSP forbids; polling evaluate does not."""
        end = time.time() + timeout
        while time.time() < end:
            if pg.evaluate(fn):
                return
            time.sleep(0.1)
        raise AssertionError('timed out waiting for ' + fn)

    def shoot(self, pg):
        pg.click('[data-a="shoot"]')
        pg.wait_for_selector('.cam [data-s]')
        self.until(pg, "() => document.querySelector('.cam video').videoWidth > 0")
        pg.click('.cam [data-s]')
        pg.wait_for_selector('.photo img')

    def sent(self, pg):
        """Everything is in the mailbox (two ticks). Only the third tick means the office has it."""
        self.until(pg, "() => (document.querySelector('#sync') || { innerText: '' }).innerText.indexOf('✓✓') >= 0")

    def inbox(self, want_events=0, want_photos=0, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            box = self.office.inbox()
            if len(box['events']) >= want_events and len(box['photos']) >= want_photos:
                return box
            time.sleep(0.3)
        return self.office.inbox()

    def ack_all(self):
        box = self.office.inbox(200)
        self.office.ack([e['uuid'] for e in box['events']], [p['uuid'] for p in box['photos']])

    def test_a_full_trip_online(self):
        self.ack_all()
        token = self.card()
        pg, ctx = self.page(token)
        pg.wait_for_selector('[data-a="begin"]')
        self.assertIn('26-A-00001', pg.inner_text('body'))
        self.assertEqual(pg.evaluate('document.documentElement.dir'), 'rtl')
        pg.click('[data-a="begin"]')
        self.shoot(pg)
        pg.fill('#km', '٤٥٠٠٠')                                    # Arabic digits are accepted
        pg.click('[data-a="start"]')
        pg.wait_for_selector('[data-a="finish"]')
        self.assertIn('45000', pg.inner_text('main'))
        pg.click('[data-a="finish"]')
        self.shoot(pg)
        pg.fill('#km', '45120')
        pg.click('[data-a="end"]')
        pg.wait_for_selector('[data-a="skip-paper"]')
        self.shoot(pg)
        pg.click('[data-a="paper"]')
        pg.wait_for_selector('.big-ok')
        pg.wait_for_selector('.sync.wait')                          # ✓✓ in the mailbox - NOT yet "received by the office"
        self.until(pg, "() => document.querySelector('#sync').innerText.indexOf('✓✓✓') < 0 && document.querySelector('#sync').innerText.indexOf('✓✓') >= 0")
        self.assertNotIn('!', pg.inner_text('#sync')[:1])
        box = self.inbox(2, 3)
        photos_kept = "() => D.outbox.items('trip:' + D.token).then(a => a.filter(i => i.kind === 'photo' && i.blob).length)"
        self.assertEqual(pg.evaluate(photos_kept), 3, 'the photos stay on the phone until the office has them')
        self.assertEqual([e['type'] for e in box['events']], ['start', 'end'])
        self.assertEqual([e['body']['data'].get('startKm', e['body']['data'].get('endKm')) for e in box['events']], [45000, 45120])
        self.assertEqual(sorted(p['kind'] for p in box['photos']), ['end_odo', 'paper', 'start_odo'])
        self.assertTrue(all(not p['fallback'] for p in box['photos']), 'live camera photos are not marked as fallback')
        self.assertTrue(all(p['size'] < 300 * 1024 for p in box['photos']))
        photo = self.office.photo(box['photos'][0]['uuid'])
        self.assertEqual(hashlib.sha256(photo).hexdigest(), box['photos'][0]['sha256'])
        self.office.ack([e['uuid'] for e in box['events']], [p['uuid'] for p in box['photos']])   # the office PC collects and stores them
        pg.evaluate('() => D.outbox.reconcile()')
        pg.wait_for_selector('.sync.ok')                            # ✓✓✓ everything is at the office
        self.assertIn('✓✓✓', pg.inner_text('#sync'))
        self.until(pg, "() => D.outbox.items('trip:' + D.token).then(a => a.every(i => i.officeAt && !i.blob))")
        self.assertEqual(pg.evaluate(photos_kept), 0, 'now the phone may forget its copy')
        self.assertEqual(self.errors, [])
        ctx.close()

    def test_h_an_item_the_mailbox_lost_is_sent_again_and_nothing_is_called_received_before_the_office_has_it(self):
        import shutil
        import sqlite3
        import tempfile
        d = tempfile.mkdtemp(prefix='to-gw-')
        gw = None
        try:
            from test_gateway_client import GatewayProcess as GP
            gw = GP(db=os.path.join(d, 'gateway.db'))
            office = G.Client(gw.url, SECRET)
            token = 'TkLostAbcdefghijklmnop'[:22]
            office.put_cards([{'tokenHash': G.token_hash(token), 'tripId': 'trL', 'body': {**CARD, 'tripId': 'trL'}, 'cancelled': False, 'expiresAt': int(time.time()) + 86400}])
            ctx = self.browser.new_context(viewport={'width': 393, 'height': 851}, is_mobile=True, has_touch=True, permissions=['camera'])
            ctx.add_init_script("try { localStorage.setItem('to.lang', 'en') } catch (e) {}")
            pg = ctx.new_page()
            pg.goto(f'{gw.url}/t/{token}')
            pg.wait_for_selector('[data-a="begin"]')
            pg.click('[data-a="begin"]')
            self.shoot(pg)
            pg.fill('#km', '1000')
            pg.click('[data-a="start"]')
            pg.wait_for_selector('[data-a="finish"]')
            self.until(pg, "() => document.querySelector('#sync') && document.querySelector('#sync').innerText.indexOf('✓✓') >= 0")
            end = time.time() + 20
            while time.time() < end and not (office.inbox()['events'] and office.inbox()['photos']):
                time.sleep(0.2)
            first = office.inbox()
            self.assertEqual((len(first['events']), len(first['photos'])), (1, 1))
            # the mailbox loses them (retention, a storage problem): rows gone, no receipt
            db = sqlite3.connect(os.path.join(d, 'gateway.db'), timeout=10)
            db.execute('DELETE FROM events')
            db.execute('DELETE FROM photos')
            db.commit()
            db.close()
            self.assertEqual((len(office.inbox()['events']), len(office.inbox()['photos'])), (0, 0))
            pg.evaluate('() => D.outbox.reconcile()')                  # the phone asks: neither at the office nor in the mailbox -> unknown
            end = time.time() + 20
            while time.time() < end and not (office.inbox()['events'] and office.inbox()['photos']):
                time.sleep(0.2)
            again = office.inbox()
            self.assertEqual([e['uuid'] for e in again['events']], [e['uuid'] for e in first['events']], 'the same event came back, not a new one')
            self.assertEqual([p['uuid'] for p in again['photos']], [p['uuid'] for p in first['photos']])
            self.assertEqual(hashlib.sha256(office.photo(again['photos'][0]['uuid'])).hexdigest(), first['photos'][0]['sha256'], 'the photo is intact')
            ctx.close()
        finally:
            if gw:
                gw.stop()
            shutil.rmtree(d, ignore_errors=True)

    def test_b_offline_in_the_middle_and_reopen(self):
        self.ack_all()
        token = self.card()
        pg, ctx = self.page(token, lang='en')
        pg.wait_for_selector('[data-a="begin"]')
        pg.click('[data-a="begin"]')
        self.shoot(pg)
        pg.fill('#km', '1000')
        pg.click('[data-a="start"]')
        pg.wait_for_selector('[data-a="finish"]')
        self.sent(pg)
        ctx.set_offline(True)
        pg.click('[data-a="finish"]')
        self.shoot(pg)
        pg.fill('#km', '1090')
        pg.click('[data-a="end"]')
        pg.wait_for_selector('[data-a="skip-paper"]')
        pg.wait_for_selector('.sync.wait')
        self.assertIn('waiting', pg.inner_text('#sync').lower())
        # close and reopen the page while offline: the trip is where it was
        pg.reload()
        pg.wait_for_selector('[data-a="skip-paper"]')
        before = len(self.inbox(1, 1, timeout=1)['events'])          # normally only the start; a slow machine may let the end through first
        ctx.set_offline(False)
        pg.evaluate("window.dispatchEvent(new Event('online'))")
        box = self.inbox(2, 2)
        self.assertEqual([e['type'] for e in box['events']], ['start', 'end'])
        if before == 1:
            self.assertTrue(box['events'][1]['body']['queued'], 'an event that waited is marked queued')
        self.sent(pg)
        ctx.close()

    def test_c_second_phone_sees_a_notice(self):
        token = self.card()
        pg, ctx = self.page(token, lang='en')
        pg.wait_for_selector('[data-a="begin"]')
        pg.click('[data-a="begin"]')
        self.shoot(pg)
        pg.fill('#km', '10')
        pg.click('[data-a="start"]')
        pg.wait_for_selector('[data-a="finish"]')
        self.sent(pg)
        pg2, ctx2 = self.page(token, lang='en')
        pg2.wait_for_selector('.note.warn')
        self.assertIn('another phone', pg2.inner_text('main'))
        ctx.close()
        ctx2.close()

    def test_d_cancelled_expired_and_unknown_links(self):
        for token, word in ((self.card(cancelled=True), 'cancelled'), ('Tk_unknownunknownunknown', 'does not work')):
            pg, ctx = self.page(token, lang='en')
            pg.wait_for_selector('.big-ok.bad')
            self.assertIn(word, pg.inner_text('main'))
            ctx.close()

    def test_e_end_lower_than_start_asks_but_never_blocks(self):
        self.ack_all()
        token = self.card()
        pg, ctx = self.page(token, lang='en')
        pg.wait_for_selector('[data-a="begin"]')
        pg.click('[data-a="begin"]')
        pg.fill('#km', '5000')
        pg.click('[data-a="start-nophoto"]')                        # a missing photo never blocks either
        pg.click('[data-a="finish"]')
        pg.fill('#km', '4000')
        pg.click('[data-a="end-nophoto"]')
        pg.wait_for_selector('[data-a="end-force"]')
        self.assertIn('lower', pg.inner_text('main'))
        pg.click('[data-a="end-force"]')
        pg.wait_for_selector('[data-a="skip-paper"]')
        box = self.inbox(2, 0)
        self.assertEqual(len(box['events']), 2)
        ctx.close()

    def test_f_gallery_fallback_is_marked(self):
        self.ack_all()
        token = self.card()
        pg, ctx = self.page(token, lang='en', camera=False)
        pg.evaluate("() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new Error('denied')); }")
        pg.wait_for_selector('[data-a="begin"]')
        pg.click('[data-a="begin"]')
        with pg.expect_file_chooser() as fc:
            pg.click('[data-a="shoot"]')
        fc.value.set_files(files=[{'name': 'odo.png', 'mimeType': 'image/png', 'buffer': png()}])
        pg.wait_for_selector('.photo img')
        pg.fill('#km', '77')
        pg.click('[data-a="start"]')
        pg.wait_for_selector('[data-a="finish"]')
        box = self.inbox(1, 1)
        self.assertTrue(box['photos'][0]['fallback'])
        ctx.close()

    def test_g_language_and_contrast_switch(self):
        token = self.card()
        pg, ctx = self.page(token, lang='ar')
        pg.wait_for_selector('[data-a="begin"]')
        pg.click('[data-a="lang"]')
        self.until(pg, "() => document.documentElement.dir === 'ltr'")
        self.assertIn('Start the trip', pg.inner_text('main'))
        pg.click('[data-a="hc"]')
        self.assertEqual(pg.evaluate("document.documentElement.dataset.hc"), '1')
        # nothing overflows sideways on a phone
        self.assertLessEqual(pg.evaluate('document.documentElement.scrollWidth'), 393)
        ctx.close()


if __name__ == '__main__':
    unittest.main()
