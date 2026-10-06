"""F13: a backup set (data + accounts + history + photos) is created one at a time, never overwrites another, is complete and
verifiable (manifest with sizes, checksums and the history watermark), a failed run leaves the last good set untouched, and a
set can be turned into a working program on a clean PC. Uses the engine directly (no web server): fast and deterministic."""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest

from harness import ADMIN, Server, make_authority

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
CHROMIUM = os.environ.get('TO_CHROMIUM', '/opt/pw-browsers/chromium')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
from system import System  # noqa: E402


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class BackupBase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='to-bk-')
        self.data = os.path.join(self.d, 'data')
        self.uploads = os.path.join(self.d, 'uploads')
        self.bk = os.path.join(self.d, 'bk')
        self.sy = None
        self.open()
        self.sy.auth.setup('boss', 'The Boss', 'Strong-pass1', '127.0.0.1')
        self.sy.store.commit('u', 'ip', 'lists', [put('vehicles', 'v1', plate='ABC 123', plateKey='abc123', active=True)])

    def open(self):
        self.sy = System(self.data, {}, self.uploads, self.bk, log=lambda m: None)
        self.b = self.sy.backups

    def tearDown(self):
        try:
            self.sy.close()
        finally:
            shutil.rmtree(self.d, ignore_errors=True)

    def sets(self):
        return [n for n in os.listdir(os.path.join(self.bk, 'db')) if n.startswith('to_') and n.endswith('.db')]

    def leftovers(self):
        return [n for n in os.listdir(os.path.join(self.bk, 'db')) if '.tmp' in n or n.endswith('.part')]

    def manifest(self, name):
        with open(os.path.join(self.bk, 'db', name[:-3] + '.json'), encoding='utf-8') as f:
            return json.load(f)


class CreateTest(BackupBase):
    def test_a_simultaneous_backups_never_overwrite_one_another(self):
        results, errors = [], []

        def run(i):
            try:
                results.append(self.b.create('manual'))
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
        threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 8, 'every request gets its own set')
        self.assertEqual(len(self.sets()), 8)
        self.assertEqual(self.leftovers(), [])
        for n in results:
            self.assertTrue(self.b.verify(n)['ok'], n)

    def test_b_two_backups_in_the_same_second_are_two_sets(self):
        a, b = self.b.create('manual'), self.b.create('manual')
        self.assertNotEqual(a, b)
        self.assertEqual({x['name'] for x in self.b.list()}, {a, b})

    def test_c_a_set_has_a_manifest_with_checksums_and_the_history_watermark(self):
        n = self.b.create('manual')
        m = self.manifest(n)
        self.assertEqual((m['format'], m['kind'], m['name']), (1, 'manual', n))
        self.assertEqual(sorted(m['files']), ['auth', 'data', 'journal'])
        folder = os.path.join(self.bk, 'db')
        for part, info in m['files'].items():
            p = os.path.join(folder, info['name'])
            self.assertEqual(os.path.getsize(p), info['size'], part)
            with open(p, 'rb') as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), info['sha256'], part)
        self.assertEqual(m['journal']['vv'], self.sy.journal.vv(), 'the watermark names exactly the history this set contains')
        c = sqlite3.connect(os.path.join(folder, m['files']['journal']['name']))
        try:
            self.assertGreater(c.execute('SELECT COUNT(*) FROM changes').fetchone()[0], 0)
        finally:
            c.close()

    def test_d_a_failed_run_leaves_the_last_good_set_and_no_half_set(self):
        good = self.b.create('manual')
        before = sorted(os.listdir(os.path.join(self.bk, 'db')))
        real = self.sy.auth.backup_to

        def boom(path):
            real(path)
            raise OSError('disk disappeared')
        self.sy.auth.backup_to = boom
        with self.assertRaises(OSError):
            self.b.create('manual')
        self.sy.auth.backup_to = real
        self.assertEqual(sorted(os.listdir(os.path.join(self.bk, 'db'))), before, 'nothing of the failed run is left, the good set is untouched')
        self.assertTrue(self.b.verify(good)['ok'])
        self.assertIn('disk disappeared', self.b.last_error, 'the failure is visible')
        self.b.create('manual')
        self.assertEqual(self.b.last_error, '', 'and the message clears after the next good backup')

    def test_e_no_disk_space_is_said_in_plain_words_and_changes_nothing(self):
        import collections
        real = shutil.disk_usage
        shutil.disk_usage = lambda p: collections.namedtuple('usage', 'total used free')(1000, 999, 1)
        try:
            with self.assertRaises(RuntimeError) as e:
                self.b.create('manual')
        finally:
            shutil.disk_usage = real
        self.assertIn('space', str(e.exception).lower())
        self.assertEqual(self.sets(), [])
        self.assertEqual(self.leftovers(), [])

    def test_f_photos_are_copied_whole_or_not_at_all(self):
        os.makedirs(os.path.join(self.uploads, 'cas'), exist_ok=True)
        with open(os.path.join(self.uploads, 'cas', 'a.jpg'), 'wb') as f:
            f.write(b'\xff\xd8' + b'x' * 5000)
        os.makedirs(os.path.join(self.bk, 'uploads', 'cas'), exist_ok=True)
        with open(os.path.join(self.bk, 'uploads', 'cas', 'a.jpg'), 'wb') as f:
            f.write(b'\xff\xd8')                      # a copy that was cut short by a power failure
        self.b.create('manual')
        with open(os.path.join(self.bk, 'uploads', 'cas', 'a.jpg'), 'rb') as f:
            self.assertEqual(len(f.read()), 5002, 'a damaged copy is replaced, not trusted because the name exists')
        self.assertEqual(self.leftovers(), [])

    def test_k_the_second_folder_gets_the_whole_set_and_a_broken_one_is_reported(self):
        usb = os.path.join(self.d, 'usb')
        blocker = os.path.join(self.d, 'blocker')
        with open(blocker, 'w') as f:
            f.write('a file, so nothing can be created below it')
        self.b.extra = [usb, os.path.join(blocker, 'sub')]
        n = self.b.create('manual')
        folder = os.path.join(usb, 'db')
        self.assertEqual(sorted(x for x in os.listdir(folder)), sorted([n, 'auth' + n[2:], 'journal' + n[2:], n[:-3] + '.json']))
        self.assertIn('blocker', self.b.last_error, 'the broken folder is named')
        self.assertTrue(self.b.verify(n)['ok'], 'the main set is fine')
        self.b.extra = [usb]
        self.b.create('manual')
        self.assertEqual(self.b.last_error, '')

    def test_l_status_says_when_a_backup_is_overdue(self):
        self.assertEqual((self.b.status()['changed'], self.b.status()['stale']), (True, False), 'a new installation does not warn')
        self.b.created = None
        self.b.started -= 3 * 86400                     # the program has run for three days without a backup
        self.assertTrue(self.b.status()['stale'])
        self.b.create('manual')
        st = self.b.status()
        self.assertEqual((st['changed'], st['stale'], st['lastError']), (False, False, ''))
        self.assertTrue(st['lastOk'])
        self.sy.store.commit('u', 'ip', 'x', [put('vehicles', 'v2', plate='XYZ 9', plateKey='xyz9', active=True)])
        self.b.last_time -= 3 * 86400                   # the last good backup is three days old and the data changed since
        self.assertTrue(self.b.status()['stale'])


class WatermarkTest(BackupBase):
    def test_g_a_changed_account_alone_makes_the_next_automatic_backup_due(self):
        self.b.create('manual')
        self.assertFalse(self.b.changed_since_last())
        self.sy.store.commit('u', 'ip', 'x', [put('vehicles', 'v2', plate='XYZ 9', plateKey='xyz9', active=True)])
        self.assertTrue(self.b.changed_since_last(), 'a business change')
        self.b.create('auto')
        self.assertFalse(self.b.changed_since_last())
        token, u = self.sy.auth.login('boss', 'Strong-pass1', '127.0.0.1', 'test')
        self.sy.auth.change_password(u, 'Strong-pass1', 'Quarter-pass77', '127.0.0.1', token)
        self.assertTrue(self.b.changed_since_last(), 'an account-only change (new password) is a change too')


class RestoreTest(BackupBase):
    def test_h_a_tampered_set_is_found_and_refused(self):
        n = self.b.create('manual')
        p = os.path.join(self.bk, 'db', n)
        with open(p, 'r+b') as f:
            f.seek(os.path.getsize(p) // 2)
            f.write(b'\x00\x01\x02\x03')
        v = self.b.verify(n)
        self.assertFalse(v['ok'])
        self.assertTrue(any('data' in x for x in v['problems']), v)
        with self.assertRaises(ValueError) as e:
            self.b.restore(n)
        self.assertIn('damaged', str(e.exception))

    def test_i_a_set_without_a_manifest_still_works(self):
        n = self.b.create('manual')
        os.remove(os.path.join(self.bk, 'db', n[:-3] + '.json'))
        self.assertTrue(self.b.verify(n)['ok'])
        self.assertTrue(self.b.verify(n)['legacy'])
        self.assertIn(n, [x['name'] for x in self.b.list()])
        self.sy.store.commit('u', 'ip', 'later', [put('vehicles', 'v3', plate='LATER 1', plateKey='later1', active=True)])
        safety, res = self.b.restore(n, 'boss', '127.0.0.1')
        self.assertTrue(safety)

    def test_j_a_clean_pc_comes_back_from_a_set_at_data_level(self):
        """The drill: only the set's files, in an empty data folder. Business data, accounts and photos come back and work.
        The PC's secret keys are not in a set (a plain copy on a USB drive would be a key leak), so the program starts as a new
        device: the old history is kept aside as journal.incomplete-*.db and a new history starts from the restored data."""
        os.makedirs(os.path.join(self.uploads, 'cas'), exist_ok=True)
        with open(os.path.join(self.uploads, 'cas', 'p.jpg'), 'wb') as f:
            f.write(b'\xff\xd8photo')
        n = self.b.create('manual')
        m = self.manifest(n)
        history = self.sy.journal.conn.execute('SELECT COUNT(*) FROM changes').fetchone()[0]
        self.sy.close()
        clean = os.path.join(self.d, 'clean')
        os.makedirs(os.path.join(clean, 'data'))
        folder = os.path.join(self.bk, 'db')
        for part, target in (('data', 'trips.db'), ('auth', 'auth.db'), ('journal', 'journal.db')):
            shutil.copy(os.path.join(folder, m['files'][part]['name']), os.path.join(clean, 'data', target))
        shutil.copytree(os.path.join(self.bk, 'uploads'), os.path.join(clean, 'uploads'))
        sy2 = System(os.path.join(clean, 'data'), {}, os.path.join(clean, 'uploads'), os.path.join(clean, 'bk'), log=lambda m: None)
        try:
            self.assertEqual(sy2.store.counts().get('Vehicles'), 1, 'business data')
            self.assertTrue(sy2.auth.has_users())
            token, u = sy2.auth.login('boss', 'Strong-pass1', '127.0.0.1', 'test')
            self.assertEqual(u['username'], 'boss', 'accounts and passwords')
            self.assertTrue(os.path.exists(os.path.join(clean, 'uploads', 'cas', 'p.jpg')), 'photos')
            self.assertTrue(sy2.journal.verify(True)['ok'], 'the new history is sound')
            kept = [x for x in os.listdir(os.path.join(clean, 'data')) if x.startswith('journal.incomplete-') and x.endswith('.db')]
            self.assertEqual(len(kept), 1, 'the old history is kept, not deleted')
            c = sqlite3.connect(os.path.join(clean, 'data', kept[0]))
            try:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM changes').fetchone()[0], history)
            finally:
                c.close()
            sy2.store.commit('u', 'ip', 'work continues', [put('vehicles', 'v9', plate='NEW 1', plateKey='new1', active=True)])
        finally:
            sy2.close()
        self.open()                                  # tearDown closes the original folder's System


@unittest.skipIf(sync_playwright is None or not os.path.exists(CHROMIUM), 'Playwright or Chromium not available')
class ScreenTest(unittest.TestCase):
    """Settings -> Data: a backup problem is shown to the administrator in plain words, in both languages."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('bkui').start()
        cls.ac = make_authority(cls.S)
        cls.usb = os.path.join(cls.S.root, 'usb')
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.S.cleanup()

    def page(self, lang):
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
        pg.goto(self.S.base + '/#/settings?tab=data')
        pg.wait_for_selector('[data-backup]')
        return pg

    def test_a_a_problem_with_the_second_folder_is_shown_and_clears_after_a_good_backup(self):
        pg = self.page('en')
        self.assertEqual(pg.locator('[data-bk-warn]').count(), 0, 'nothing to warn about at first')
        os.makedirs(self.usb)
        self.ac.post('/api/backups/folder', {'path': self.usb})                             # accepted: it can be written
        shutil.rmtree(self.usb)
        with open(self.usb, 'w') as f:                                                      # the USB drive is gone; something else is at that path
            f.write('x')
        self.ac.post('/api/backups')                                                        # the main backup works, the second copy does not
        pg = self.page('en')
        self.assertIn('did not work', pg.inner_text('[data-bk-warn]'))
        self.assertIn('usb', pg.inner_text('[data-bk-warn]'))
        pg_ar = self.page('ar')
        self.assertIn('آخر نسخة احتياطية', pg_ar.inner_text('[data-bk-warn]'))
        self.assertEqual(pg_ar.evaluate('document.documentElement.dir'), 'rtl')
        os.remove(self.usb)
        os.makedirs(self.usb)                                                               # the drive is back
        self.ac.post('/api/backups')
        pg = self.page('en')
        self.assertEqual(pg.locator('[data-bk-warn]').count(), 0)
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
