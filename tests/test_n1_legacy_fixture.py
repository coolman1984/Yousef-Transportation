"""N-1 legacy journey helpers (customer-release CI)."""
import importlib.util
import os
import unittest

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

    def test_journey_legacy_handles_enforced_fixture(self):
        src = open(os.path.join(ROOT, 'tools', 'journey_exe.py'), encoding='utf-8').read()
        self.assertIn('_activate_enforced_legacy', src)
        self.assertIn('TO_TEST_SIGNING_KEY_FILE', src)
        self.assertIn('legacy_enforced', src)


if __name__ == '__main__':
    unittest.main()
