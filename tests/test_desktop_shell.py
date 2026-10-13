"""Desktop shell: config migration, icon build, single-instance helpers, shutdown hook."""
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))


class ConfigMigrateTest(unittest.TestCase):
    def test_strips_legacy_flags(self):
        from config_migrate import migrate_config

        cfg = {'port': 8090, 'edge_webview': True, 'force_system_browser': 1, 'ui_mode': 'window'}
        self.assertTrue(migrate_config(cfg))
        self.assertNotIn('edge_webview', cfg)
        self.assertNotIn('force_system_browser', cfg)

    def test_invalid_ui_mode_reset(self):
        from config_migrate import migrate_config

        cfg = {'ui_mode': 'edge'}
        self.assertTrue(migrate_config(cfg))
        self.assertEqual(cfg['ui_mode'], 'window')

class IconBuildTest(unittest.TestCase):
    def test_ico_contains_required_sizes(self):
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from make_icon import ICO_SIZES, write_ico

        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, 'triporders.ico')
        write_ico(out)
        self.assertTrue(os.path.getsize(out) > 500)
        with open(out, 'rb') as f:
            f.read(4)
            count = struct.unpack('<H', f.read(2))[0]
        self.assertEqual(count, len(ICO_SIZES))
        found = set()
        with open(out, 'rb') as f:
            f.seek(6)
            for _ in range(count):
                w, h = struct.unpack('<BB', f.read(2))
                found.add((w or 256, h or 256))
                f.read(14)
        self.assertEqual({s for s in ICO_SIZES}, {a for a, b in found})


class DesktopShellLogicTest(unittest.TestCase):
    def test_duplicate_instance_noop_off_windows(self):
        from desktop_shell import exit_if_duplicate_instance

        with mock.patch.object(sys, 'platform', 'linux'):
            self.assertFalse(exit_if_duplicate_instance())

    def test_should_use_desktop_window(self):
        from desktop_shell import should_use_desktop_window

        cfg = {}
        with mock.patch.object(sys, 'platform', 'win32'):
            with mock.patch.object(sys, 'frozen', True, create=True):
                self.assertTrue(should_use_desktop_window(cfg, False, True))
                self.assertFalse(should_use_desktop_window(cfg, True, True))
                self.assertFalse(should_use_desktop_window({'ui_mode': 'browser'}, False, True))
        with mock.patch.dict(os.environ, {'TO_DESKTOP_WINDOW': '1'}, clear=False):
            with mock.patch.object(sys, 'platform', 'linux'):
                self.assertTrue(should_use_desktop_window(cfg, False, True))

    def test_shutdown_callback_invoked(self):
        from desktop_shell import run_window

        called = []
        wv = mock.MagicMock()
        wv.start = mock.Mock(side_effect=lambda fn: fn())

        def on_closed():
            called.append(1)

        with mock.patch.dict(sys.modules, {'webview': wv}):
            run_window('http://127.0.0.1:1/', on_closed)
        self.assertEqual(called, [1])


if __name__ == '__main__':
    unittest.main()
