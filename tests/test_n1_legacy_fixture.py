"""N-1 legacy journey helpers (customer-release CI)."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_prepare():
    path = os.path.join(ROOT, 'tools', 'prepare_n1_for_legacy.py')
    spec = importlib.util.spec_from_file_location('prepare_n1_for_legacy', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class N1LegacyFixtureTest(unittest.TestCase):
    def test_enforced_previous_from_tag(self):
        prep = _load_prepare()
        self.assertFalse(prep._enforced_previous('v1.1.2'))
        self.assertTrue(prep._enforced_previous('v1.1.3'))
        self.assertTrue(prep._enforced_previous('v1.1.6'))

    def test_main_downloads_and_prints_setup_path(self):
        prep = _load_prepare()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'TripOrders-Setup-1.1.5.exe'
            fake.write_bytes(b'fake')
            lines = []
            with mock.patch.object(prep, '_download_release', return_value=fake) as dl:
                with mock.patch.dict(os.environ, {'RUNNER_TEMP': tmp, 'PREVIOUS_TAG': 'v1.1.5', 'GITHUB_REPOSITORY': 'org/repo'}, clear=True):
                    with mock.patch('builtins.print', side_effect=lambda *a, **k: lines.append(' '.join(str(x) for x in a))):
                        prep.main()
            dl.assert_called_once_with('v1.1.5', Path(tmp) / 'previous-release')
            n1_lines = [x for x in lines if x.startswith('N1_SETUP_EXE=')]
            self.assertEqual(len(n1_lines), 1)
            self.assertTrue(n1_lines[0].endswith('TripOrders-Setup-1.1.5.exe'))

    def test_prepare_module_has_no_fixture_rebuild(self):
        src = open(os.path.join(ROOT, 'tools', 'prepare_n1_for_legacy.py'), encoding='utf-8').read()
        self.assertNotIn('worktree', src)
        self.assertNotIn("get('GITHUB_ENV')", src)
        self.assertNotIn('TO_TEST_SIGNING_KEY_FILE', src)

    def test_journey_legacy_enforced_stays_unlicensed(self):
        src = open(os.path.join(ROOT, 'tools', 'journey_exe.py'), encoding='utf-8').read()
        legacy = src.split('def legacy(home, cmd):')[1].split('def first(home, cmd):')[0]
        self.assertIn('legacy_enforced', legacy)
        self.assertIn('expect=402', legacy)
        self.assertNotIn('TO_TEST_SIGNING_KEY_FILE', legacy)
        self.assertNotIn('_activate_enforced_legacy', src)

    def test_customer_release_workflow_sets_n1_in_process(self):
        yml = open(os.path.join(ROOT, '.github', 'workflows', 'customer-release.yml'), encoding='utf-8').read()
        self.assertIn('$env:N1_SETUP_EXE = $Matches[1]', yml)
        self.assertNotIn('TO_TEST_SIGNING_KEY_FILE', yml)


if __name__ == '__main__':
    unittest.main()
