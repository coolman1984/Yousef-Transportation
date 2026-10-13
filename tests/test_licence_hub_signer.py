"""Cross-check: a code from licence-hub Node signer verifies in server/afcodes (same bytes as Licence.activate)."""
import json
import os
import subprocess
import sys
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import afcodes  # noqa: E402


class LicenceHubSignerTest(unittest.TestCase):
    def test_node_signed_code_is_valid(self):
        script = os.path.join(ROOT, 'licence-hub', 'test', 'export_code.mjs')
        out = subprocess.check_output(['node', script], cwd=ROOT, text=True)
        data = json.loads(out)
        result = afcodes.read_code(data['code'], [data['public']], 'trip-orders', device=data['device'], today=date.today())
        self.assertTrue(result.valid)
        self.assertEqual(result.state, 'active')
        self.assertEqual(result.terms.get('edition'), 'trial')


if __name__ == '__main__':
    unittest.main()
