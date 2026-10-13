"""Commercial licence fail-closed runtime, installer channel separation, and contract-upgrade grace."""
import base64
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

import licence  # noqa: E402


def key_blob(seed=b"a"):
    raw = (seed * 32)[:32]
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class _Assist:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.values = {'install_id': 'test-install'}

    def kv(self, key, value=None, delete=False):
        if delete:
            self.values.pop(key, None)
            return None
        if value is not None:
            self.values[key] = value
        return self.values.get(key)


class _CommercialLicence:
    """Licence() under patched commercial build flags for the whole test block."""

    def __init__(self, data_dir, build_channel='commercial', release_keys=None):
        self._patch = patch.multiple(
            licence,
            _COMMERCIAL_BUILD=True,
            _BUILD_CHANNEL=build_channel,
            _RELEASE_KEYS=release_keys if release_keys is not None else (key_blob(),),
        )
        self._patch.start()
        self.lic = licence.Licence(_Assist(data_dir), str(ROOT), str(data_dir), {})

    def __enter__(self):
        return self.lic

    def __exit__(self, *exc):
        self._patch.stop()


def _seed_trips_db(data_dir):
    path = os.path.join(data_dir, 'trips.db')
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('initialized', '2020-01-01T00:00:00Z');
        CREATE TABLE trips (
            id TEXT PRIMARY KEY, deleted INTEGER NOT NULL DEFAULT 0);
        INSERT INTO trips VALUES ('t1', 0);
    """)
    conn.commit()
    conn.close()


class DistributedRuntimeTest(unittest.TestCase):
    def test_missing_policy_is_contract_in_plain_python(self):
        self.assertFalse(licence._distributed_runtime())

    def test_missing_policy_is_commercial_when_frozen(self):
        with patch.object(sys, 'frozen', True, create=True):
            self.assertTrue(licence._distributed_runtime())

    def test_missing_policy_is_commercial_when_executable_not_python(self):
        with patch.object(sys, 'executable', '/opt/TripOrders/TripOrders.exe'):
            self.assertTrue(licence._distributed_runtime())

    def test_missing_release_policy_import_fail_closed_in_subprocess(self):
        code = """
import os, sys
sys.path.insert(0, sys.argv[1])
sys.frozen = True
import importlib
licence = importlib.import_module('licence')
assert licence._COMMERCIAL_BUILD is True
assert licence._RELEASE_KEYS == ()
assert licence._BUILD_CHANNEL == 'commercial'
class Data:
    def __init__(self): self.values = {'install_id': 'x'}
    def kv(self, key, value=None, delete=False):
        if value is not None: self.values[key] = value
        return self.values.get(key)
l = licence.Licence(Data(), sys.argv[1], sys.argv[2], {'licence_keys': ['rogue']})
assert l.trusted_keys() == []
st = l.status()
assert st['enforced'] and not st['full'] and st['state'] == 'none'
"""
        with tempfile.TemporaryDirectory() as d:
            p = __import__("subprocess").run(
                [sys.executable, "-c", code, str(ROOT / "server"), d],
                capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)


class InstallerChannelTest(unittest.TestCase):
    def test_ci_test_and_commercial_installer_identity_differ(self):
        iss = (ROOT / "installer" / "trip-orders.iss").read_text("utf-8")
        ids = re.findall(
            r'\{\{([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})\}"',
            iss,
            flags=re.IGNORECASE,
        )
        self.assertEqual(len(set(ids)), 2, "commercial and ci-test need distinct AppId GUIDs")
        self.assertIn("TripOrders-CITest", iss)
        # the commercial AppId must stay byte-identical so real offices upgrade in place
        self.assertIn('#define MyAppId "{{51A5FF77-EE7F-474F-9A55-53DEEF2A4B7A}"', iss)
        self.assertNotIn("}}\"", iss)
        self.assertRegex(iss, r'DefaultDirName=\{autopf\}\\\{#MyInstallFolder\}')
        self.assertIn('#define MyAppName "Trip Orders CI Test"', iss)
        self.assertIn('#define MyAppName "Trip Orders"', iss)
        build = (ROOT / "tools" / "build_windows.py").read_text("utf-8")
        self.assertIn("f.write('TEST ONLY", build)
        self.assertNotIn("publish this installer.\\\\n')", build)


class UpgradeGraceTest(unittest.TestCase):
    def test_fresh_commercial_install_has_no_grace(self):
        with tempfile.TemporaryDirectory() as d:
            with _CommercialLicence(d) as l:
                st = l.status()
                self.assertFalse(st.get('upgrade_grace'))
                self.assertFalse(st['full'])

    def test_fresh_install_with_sample_trips_never_gets_grace(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            conn = sqlite3.connect(os.path.join(d, 'trips.db'))
            from datetime import datetime as _dt
            conn.execute("UPDATE meta SET value=? WHERE key='initialized'",
                         (_dt.now().isoformat(timespec='seconds'),))
            conn.commit()
            conn.close()
            with _CommercialLicence(d) as l:
                st = l.status()
                self.assertFalse(st.get('upgrade_grace'))
                self.assertFalse(st['full'])
                # even once the data ages, the first-sight decision stands
                conn = sqlite3.connect(os.path.join(d, 'trips.db'))
                conn.execute("UPDATE meta SET value='2020-01-01T00:00:00' WHERE key='initialized'")
                conn.commit()
                conn.close()
                licence._cache.clear()
                self.assertFalse(l.status()['full'])

    def test_prior_contract_data_gets_grace_then_expires(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            with _CommercialLicence(d) as l:
                st = l.status()
                self.assertTrue(st['full'])
                self.assertEqual(st['state'], 'upgrade_grace')
                self.assertGreater(st['upgrade_grace_days_left'], 0)
                future = licence.utcnow() + timedelta(days=licence.UPGRADE_GRACE_DAYS + 1)
                with patch.object(licence, 'utcnow', return_value=future):
                    st2 = l.status()
                self.assertFalse(st2['full'])
                self.assertEqual(st2['state'], 'none')

    def test_grace_not_renewed_after_markers_removed(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            with _CommercialLicence(d) as l:
                l.status()
                os.remove(os.path.join(d, licence.UPGRADE_GRACE_FILE))
                l.a.kv('upgrade_grace_started_at', delete=True)
                future = licence.utcnow() + timedelta(days=licence.UPGRADE_GRACE_DAYS + 1)
                with patch.object(licence, 'utcnow', return_value=future):
                    st = l.status()
                self.assertFalse(st['full'])
                l.a.kv('upgrade_grace_consumed', delete=True)
                st2 = l.status()
                self.assertFalse(st2['full'])

    def test_ci_test_build_never_gets_grace(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            with _CommercialLicence(d, build_channel='ci-test') as l:
                self.assertFalse(l.status()['full'])

    def test_clock_back_ends_grace(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            with _CommercialLicence(d) as l:
                l.status()
                l._write_max_seen(licence.utcnow() + timedelta(hours=100))
                with patch.object(licence, 'utcnow', return_value=licence.utcnow()):
                    st = l.status()
                self.assertFalse(st['full'])



class EncryptedTripsDbGraceTest(unittest.TestCase):
    """With TRIPORDERS_ENCRYPT=1 trips.db is SQLCipher: an upgrading office must still get its grace."""

    def test_prior_contract_office_with_encrypted_db_gets_grace(self):
        try:
            import sqlcipher3  # noqa: F401
        except ImportError:
            self.skipTest('sqlcipher3 not installed')
        import atrest
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as prof:
            env = {'TRIPORDERS_ENCRYPT': '1', 'TRIPORDERS_DPAPI_DIR': prof, 'XDG_CONFIG_HOME': prof}
            with patch.dict(os.environ, env):
                conn = atrest.connect(os.path.join(d, 'trips.db'), isolation_level=None)
                conn.executescript("""
                    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                    INSERT INTO meta VALUES ('initialized', '2020-01-01T00:00:00');
                    CREATE TABLE trips (id TEXT PRIMARY KEY, deleted INTEGER NOT NULL DEFAULT 0);
                    INSERT INTO trips VALUES ('t1', 0);
                """)
                conn.close()
                self.assertFalse(atrest.is_plain_sqlite(os.path.join(d, 'trips.db')))
                licence._cache.clear()
                with _CommercialLicence(d) as l:
                    st = l.status()
                    self.assertTrue(st.get('upgrade_grace'), st)
                    self.assertTrue(st['full'])
                    self.assertEqual(l._trips_meta(licence.UPGRADE_GRACE_EVER_META), '1')


class TrialClockExpiryTest(unittest.TestCase):
    """Trial end uses max(local day, max_seen day) and stays latched after clock rollback."""

    def _trial_keypair(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest('cryptography not installed')
        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        public = base64.urlsafe_b64encode(raw).decode().rstrip('=')
        return pem, public

    def test_trial_latches_expired_after_max_seen_day_passes_last_day(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            first = date_cls.today()
            pem, public = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                device = l.device()
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 3, device=device)['code']
                l.activate(code, manual=True)
                licence._cache.clear()
                l.a.kv('max_seen', licence.iso(licence.utcnow() + timedelta(days=10)))
                st = l.status()
                self.assertEqual(st['state'], 'expired')
                self.assertFalse(st['full'])
                self.assertTrue(l._trial_latch_active())
                with patch.object(l, '_effective_calendar_day', return_value=first):
                    licence._cache.clear()
                    st2 = l.status()
                self.assertEqual(st2['state'], 'expired')

    def test_hub_calendar_day_advances_max_seen_for_stuck_clock(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            first = date_cls.today()
            pem, public = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 14, device=l.device())['code']
                l.activate(code, manual=True)
                future = (first + timedelta(days=5)).isoformat()
                l._note_hub_calendar_day(future)
                seen = l._read_max_seen()
                self.assertIsNotNone(seen)
                self.assertGreaterEqual(seen.date(), first + timedelta(days=5))

    def test_frozen_local_clock_expires_after_hub_calendar_day(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            frozen = date_cls.today() - timedelta(days=10)
            pem, public = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', frozen, 3, device=l.device())['code']
                with patch.object(l, '_effective_calendar_day', return_value=frozen):
                    l.activate(code, manual=True)
                    licence._cache.clear()
                    st = l.status()
                self.assertTrue(st['full'])
                l._note_hub_calendar_day((frozen + timedelta(days=5)).isoformat())
                licence._cache.clear()
                st2 = l.status()
                self.assertEqual(st2['state'], 'expired')
                self.assertFalse(st2['full'])

    def test_trial_latch_survives_deleting_kv_when_max_seen_is_sealed(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            first = date_cls.today()
            pem, public = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 3, device=l.device())['code']
                l.activate(code, manual=True)
                l._note_hub_calendar_day((first + timedelta(days=5)).isoformat())
                licence._cache.clear()
                l.status()
                l.a.kv(licence.TRIAL_EXPIRED_LATCH, delete=True)
                licence._cache.clear()
                st = l.status()
                self.assertEqual(st['state'], 'expired')

    def test_trial_hub_key_rejects_non_trial_editions(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = self._trial_keypair()
            cfg = {'licence_keys': [f'trial-hub:{public}']}
            with patch.object(licence, '_COMMERCIAL_BUILD', False):
                lic = licence.Licence(_Assist(d), str(ROOT), str(d), cfg)
                device = lic.device()
                monthly = afcodes.issue_code(pem, licence.PRODUCT_ID, 'standard', date_cls.today(), 30, device=device)['code']
                verdict = lic._check(monthly, device, date_cls.today(), lic.trusted_keys())
                self.assertEqual(verdict['state'], 'invalid')
                self.assertEqual(verdict['reason'], 'trial_key_edition')

    def test_paid_licence_allows_wider_clock_rollback_than_trial(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                first = date_cls.today()
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'standard', first, 30, device=l.device())['code']
                l.activate(code, manual=True)
                licence._cache.clear()
                l._write_max_seen(licence.utcnow() + timedelta(hours=48))
                with patch.object(licence, 'utcnow', return_value=licence.utcnow()):
                    st = l.status()
                self.assertTrue(st['full'], st)
                trial_code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 14, device=l.device())['code']
                l.activate(trial_code, manual=True)
                licence._cache.clear()
                l._write_max_seen(licence.utcnow() + timedelta(hours=48))
                with patch.object(licence, 'utcnow', return_value=licence.utcnow()):
                    st_trial = l.status()
                self.assertFalse(st_trial['full'])
                self.assertEqual(st_trial['reason'], 'clock_back')


class GraceNotLostByAccidentTest(unittest.TestCase):
    def test_unreadable_db_on_first_check_does_not_consume_grace(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            licence._cache.clear()
            with _CommercialLicence(d) as l:
                with patch.object(licence.Licence, '_has_prior_office_data', return_value=None):
                    self.assertFalse(l.status()['full'])
                self.assertFalse(l._upgrade_grace_consumed())
                licence._cache.clear()
                st = l.status()
                self.assertTrue(st['full'] and st.get('upgrade_grace'), st)

    def test_clock_back_locks_but_corrected_clock_restores_grace(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_trips_db(d)
            licence._cache.clear()
            with _CommercialLicence(d) as l:
                with patch.object(licence.Licence, '_seen_now', return_value=True):
                    self.assertFalse(l.status()['full'])
                self.assertFalse(l._upgrade_grace_consumed())
                licence._cache.clear()
                self.assertTrue(l.status()['full'])

if __name__ == "__main__":
    unittest.main()
