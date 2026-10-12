"""Customer installer must embed a valid licence trust anchor and fail closed.

All keys are throwaway test data; no actual vendor signing key is here.
"""
import base64
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release_policy import create_release_policy, parse_public_keys


def key_blob(seed=b"a"):
    raw = (seed * 32)[:32]
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class CommercialPolicyTest(unittest.TestCase):
    def test_customer_build_refuses_missing_invalid_and_duplicate_keys(self):
        good = key_blob()
        for bad in ("", " ", "invalid", good + ",", good + "," + good,
                    key_blob(b"\x00"), good + "=", "xxx:" + good):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    parse_public_keys(bad)
        self.assertEqual(parse_public_keys(good + "," + key_blob(b"b")),
                         (good, key_blob(b"b")))

    def test_generated_trust_anchor_is_public_only_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "_release_policy.py"
            self.assertEqual(create_release_policy(str(path), key_blob()), 1)
            text = path.read_text("ascii")
            self.assertIn("COMMERCIAL_BUILD = True", text)
            self.assertIn(key_blob(), text)
            self.assertNotIn("PRIVATE KEY", text)
            with self.assertRaises(ValueError):
                create_release_policy(str(path), key_blob(b"b"))

    def test_compiled_policy_ignores_mutable_configuration_and_does_not_unlock_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            generated = pathlib.Path(d) / "_release_policy.py"
            good, rogue = key_blob(), key_blob(b"b")
            create_release_policy(str(generated), good)
            # A separate process imports the generated policy as an installed
            # program would. User-set config/environment cannot replace it.
            code = """
import os, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import _release_policy, licence
class Data:
    def __init__(self): self.values = {'install_id': 'demo'}
    def kv(self, key, value=None):
        if value is not None: self.values[key] = value
        return self.values.get(key)
l = licence.Licence(Data(), sys.argv[1], sys.argv[1], {'licence_keys': [sys.argv[4]]})
assert l.trusted_keys() == [sys.argv[3]]
assert l.enforced
assert not l.status()['full']
_release_policy.TRUSTED_KEYS = ()
licence._RELEASE_KEYS = ()
st = l.status()
assert st['enforced'] and not st['full'] and st['state'] == 'none'
"""
            env = dict(os.environ, TO_LICENCE_KEYS=rogue, TO_DEVICE_ID="forged")
            p = subprocess.run(
                [sys.executable, "-c", code, d, str(ROOT / "server"), good, rogue],
                env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)


    def test_commercial_policy_rejects_unbound_signed_trial_and_monthly_codes(self):
        from datetime import date
        from unittest.mock import patch
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        sys.path.insert(0, str(ROOT / "server"))
        import afcodes, licence
        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public = base64.urlsafe_b64encode(private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip("=")
        device = "ABCDE-FGHJK"
        with patch.object(licence, "_COMMERCIAL_BUILD", True):
            for edition in ("trial", "standard", "pro"):
                with self.subTest(edition=edition):
                    unbound = afcodes.issue_code(pem, "trip-orders", edition, date.today(), 30)["code"]
                    verdict = licence.Licence._check(unbound, device, date.today(), [public])
                    self.assertEqual((verdict["state"], verdict["full"], verdict["reason"]),
                                     ("invalid", False, "device_required"))
                    bound = afcodes.issue_code(pem, "trip-orders", edition, date.today(), 30, device=device)["code"]
                    self.assertTrue(licence.Licence._check(bound, device, date.today(), [public])["full"])

    def test_ci_build_is_conspicuously_not_for_customers(self):
        build = (ROOT / "tools" / "build_windows.py").read_text("utf-8")
        installer = (ROOT / "installer" / "trip-orders.iss").read_text("utf-8")
        licence_js = (ROOT / "js" / "views" / "licence.js").read_text("utf-8")
        self.assertIn("/DAppChannel={channel}", build)
        self.assertIn("CI-TEST-NOT-FOR-CUSTOMERS", installer)
        self.assertIn("lic.ciTest", licence_js)


if __name__ == "__main__":
    unittest.main()
