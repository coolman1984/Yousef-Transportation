"""Signed hub calendar payloads."""
import base64
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))

import hub_time  # noqa: E402


class HubTimeTest(unittest.TestCase):
    def test_verify_round_trip(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
        except ImportError:
            self.skipTest('cryptography not installed')
        private = Ed25519PrivateKey.generate()
        raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        pub = base64.urlsafe_b64encode(raw).decode().rstrip('=')
        day = '2026-10-14'
        sig = base64.urlsafe_b64encode(private.sign(hub_time.hub_time_message(day, 'trial-hub'))).decode().rstrip('=')
        payload = {'calendar_day': day, 'kid': 'trial-hub', 'sig': sig}
        self.assertEqual(hub_time.verify_hub_calendar(payload, {'trial-hub': pub}), day)
        self.assertIsNone(hub_time.verify_hub_calendar({'calendar_day': day}, {'trial-hub': pub}))


if __name__ == '__main__':
    unittest.main()
