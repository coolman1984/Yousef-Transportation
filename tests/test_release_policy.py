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
        for bad in ("", " ", "invalid", good + "," + good,
                    key_blob(b"\x00"), good + "=", "badkid:not-a-key"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    parse_public_keys(bad)
        self.assertEqual(parse_public_keys(good + "," + key_blob(b"b")),
                         (good, key_blob(b"b")))
        with self.assertRaises(ValueError):
            parse_public_keys(good + "," + good)

    def test_generated_trust_anchor_is_public_only_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "_release_policy.py"
            good = f"trial-hub:{key_blob()}"
            self.assertEqual(create_release_policy(str(path), good), 1)
            text = path.read_text("ascii")
            self.assertIn("COMMERCIAL_BUILD = True", text)
            self.assertIn(key_blob(), text)
            self.assertIn("TRIAL_ONLY_PUBLIC_KEYS", text)
            self.assertNotIn("PRIVATE KEY", text)
            with self.assertRaises(ValueError):
                create_release_policy(str(path), good.replace(key_blob(), key_blob(b"b")))

    def test_commercial_build_requires_trial_hub_kid(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "_release_policy.py"
            with self.assertRaises(ValueError):
                create_release_policy(str(path), key_blob(), channel="commercial")

    def test_compiled_policy_ignores_mutable_configuration_and_does_not_unlock_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            generated = pathlib.Path(d) / "_release_policy.py"
            good, rogue = key_blob(), key_blob(b"b")
            create_release_policy(str(generated), f"trial-hub:{good}", channel="ci-test")
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
        from datetime import date, timedelta
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

        class Data:
            def kv(self, key, value=None, delete=False):
                return None

        lic = licence.Licence(Data(), str(ROOT), str(ROOT), {})
        with patch.object(licence, "_COMMERCIAL_BUILD", True):
            for edition in ("trial", "standard", "pro"):
                with self.subTest(edition=edition):
                    unbound = afcodes.issue_code(pem, "trip-orders", edition, date.today(), 30)["code"]
                    verdict = lic._check(unbound, device, date.today(), [public])
                    self.assertEqual((verdict["state"], verdict["full"], verdict["reason"]),
                                     ("invalid", False, "device_required"))
                    bound = afcodes.issue_code(pem, "trip-orders", edition, date.today(), 30, device=device)["code"]
                    self.assertTrue(lic._check(bound, device, date.today(), [public])["full"])

    def test_commercial_policy_rejects_hub_signed_paid_codes(self):
        from datetime import date, timedelta
        from unittest.mock import patch
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        sys.path.insert(0, str(ROOT / "server"))
        import afcodes, licence
        hub = Ed25519PrivateKey.generate()
        studio = Ed25519PrivateKey.generate()
        hub_pub = base64.urlsafe_b64encode(hub.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip("=")
        studio_pub = base64.urlsafe_b64encode(studio.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip("=")
        hub_pem = hub.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        studio_pem = studio.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        device = "ABCDE-FGHJK"

        class Data:
            def kv(self, key, value=None, delete=False):
                return None

        lic = licence.Licence(Data(), str(ROOT), str(ROOT), {})
        entries = (("trial-hub", hub_pub), ("studio", studio_pub))
        with patch.object(licence, "_COMMERCIAL_BUILD", True), patch.object(licence, "_RELEASE_KEY_ENTRIES", entries), \
                patch.object(licence, "_RELEASE_KEYS", (hub_pub, studio_pub)), \
                patch.object(licence, "_RELEASE_TRIAL_ONLY", frozenset({hub_pub})):
            trial_ok = afcodes.issue_code(hub_pem, "trip-orders", "trial", date.today(), 14, device=device)["code"]
            self.assertTrue(lic._check(trial_ok, device, date.today(), lic.trusted_keys())["full"])
            long_trial = afcodes.issue_code(hub_pem, "trip-orders", "trial", date.today(), 20, device=device)["code"]
            self.assertEqual(lic._check(long_trial, device, date.today(), lic.trusted_keys())["reason"], "trial_key_days")
            graced = afcodes.issue_code(hub_pem, "trip-orders", "trial", date.today(), 14, device=device, grace_days=60)["code"]
            self.assertEqual(lic._check(graced, device, date.today() + timedelta(days=70), lic.trusted_keys())["reason"], "trial_key_grace")
            self.assertEqual(lic._check(graced, device, date.today(), lic.trusted_keys())["reason"], "trial_key_grace")
            with patch.object(afcodes, "_device_tag", lambda code: b"\0" * 6):
                unbound = afcodes.issue_code(hub_pem, "trip-orders", "trial", date.today(), 14, device=device)["code"]
            self.assertFalse(lic._check(unbound, device, date.today(), lic.trusted_keys())["full"])
            self.assertEqual(afcodes.read_code(unbound, [hub_pub], "trip-orders", device=device,
                                               trial_only_keys=frozenset({hub_pub})).reason, "trial_key_unbound")
            monthly = afcodes.issue_code(hub_pem, "trip-orders", "standard", date.today(), 30, device=device)["code"]
            self.assertEqual(lic._check(monthly, device, date.today(), lic.trusted_keys())["reason"], "trial_key_edition")
            paid = afcodes.issue_code(studio_pem, "trip-orders", "standard", date.today(), 30, device=device)["code"]
            self.assertTrue(lic._check(paid, device, date.today(), lic.trusted_keys())["full"])

    def test_trial_only_key_aliases_reject_paid_editions(self):
        from datetime import date
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        sys.path.insert(0, str(ROOT / "server"))
        import afcodes

        hub = None
        hub_pub = hub_pub_padded = hub_pub_std = None
        for _ in range(2000):
            candidate = Ed25519PrivateKey.generate()
            raw = candidate.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            url = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            std = base64.b64encode(raw).decode().rstrip("=")
            if std != url and ('+' in std or '/' in std):
                hub = candidate
                hub_pub, hub_pub_std = url, std
                hub_pub_padded = base64.urlsafe_b64encode(raw).decode()
                break
        self.assertIsNotNone(hub, "need a key whose standard and url-safe spellings differ")

        hub_pem = hub.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        studio = Ed25519PrivateKey.generate()
        studio_raw = studio.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        studio_pub = base64.urlsafe_b64encode(studio_raw).decode().rstrip("=")
        studio_pem = studio.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

        device = "ABCDE-FGHJK"
        trusted = [hub_pub]
        today = date.today()
        mid = len(hub_pub) // 2
        hub_pub_spaced = hub_pub[:mid] + " \n" + hub_pub[mid:]

        paid_codes = {
            "standard": afcodes.issue_code(
                hub_pem, "trip-orders", "standard", today, 30, device=device)["code"],
            "pro": afcodes.issue_code(hub_pem, "trip-orders", "pro", today, 30, device=device)["code"],
            "perpetual": afcodes.issue_code(
                hub_pem, "trip-orders", "perpetual", today, 1, device=device)["code"],
        }
        trial_spellings = (
            hub_pub_padded,
            hub_pub_std,
            f"trial-hub:{hub_pub}",
            hub_pub_spaced,
            frozenset({"not-a-key", hub_pub_padded}),
        )

        for spelling in trial_spellings:
            trial_only = spelling if isinstance(spelling, frozenset) else frozenset({spelling})
            label = next(iter(trial_only))[:20]
            for edition, code in paid_codes.items():
                with self.subTest(trial_only=label, edition=edition):
                    result = afcodes.read_code(
                        code, trusted, "trip-orders", device=device, today=today,
                        trial_only_keys=trial_only)
                    self.assertEqual(result.reason, "trial_key_edition")

        trial_ok = afcodes.issue_code(hub_pem, "trip-orders", "trial", today, 14, device=device)["code"]
        self.assertTrue(
            afcodes.read_code(
                trial_ok, trusted, "trip-orders", device=device, today=today,
                trial_only_keys=frozenset({hub_pub_std, "garbage"})).full_access)

        honest_paid = afcodes.issue_code(
            studio_pem, "trip-orders", "standard", today, 30, device=device)["code"]
        messy_trusted = ["not-a-key", "%%%%", studio_pub]
        paid_result = afcodes.read_code(
            honest_paid, messy_trusted, "trip-orders", device=device, today=today,
            trial_only_keys=frozenset({hub_pub}))
        self.assertTrue(paid_result.full_access)

    def test_ci_build_is_conspicuously_not_for_customers(self):
        build = (ROOT / "tools" / "build_windows.py").read_text("utf-8")
        installer = (ROOT / "installer" / "trip-orders.iss").read_text("utf-8")
        licence_js = (ROOT / "js" / "views" / "licence.js").read_text("utf-8")
        self.assertIn("/DAppChannel={channel}", build)
        self.assertIn("CI-TEST-NOT-FOR-CUSTOMERS", installer)
        self.assertIn("lic.ciTest", licence_js)


if __name__ == "__main__":
    unittest.main()
