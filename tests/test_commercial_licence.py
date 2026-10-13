"""Commercial licence fail-closed runtime, installer channel separation, and contract-upgrade grace."""
import base64
import http.client
import io
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

import licence  # noqa: E402


def hub_response(payload, status=200, missing_bytes=0):
    """Real HTTP parser over an in-memory socket, including short Content-Length bodies."""
    class Socket:
        def makefile(self, *args):
            return io.BytesIO(
                f'HTTP/1.1 {status} Test\r\nContent-Length: {len(payload) + missing_bytes}\r\n\r\n'.encode()
                + payload)

    response = http.client.HTTPResponse(Socket())
    response.begin()
    return response


def key_blob(seed=b"a"):
    raw = (seed * 32)[:32]
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class _Assist:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.values = {'install_id': 'test-install'}
        self.practice = False

    def hub_url(self):
        return self.values.get('hub_url', '')

    def licence_hub_url(self):
        return self.values.get('licence_hub_url') or self.hub_url()

    def kv(self, key, value=None, delete=False):
        if delete:
            self.values.pop(key, None)
            return None
        if value is not None:
            self.values[key] = value
        return self.values.get(key)


class _CommercialLicence:
    """Licence() under patched commercial build flags for the whole test block."""

    def __init__(self, data_dir, build_channel='commercial', release_keys=None, studio_keys=None):
        trial_keys = release_keys if release_keys is not None else (key_blob(),)
        studio = studio_keys or ()
        entries = [('studio', k) for k in studio] + [('trial-hub', k) for k in trial_keys]
        all_keys = tuple(dict.fromkeys(list(studio) + list(trial_keys)))
        self._prof = tempfile.mkdtemp()
        self._patch = patch.multiple(
            licence,
            _COMMERCIAL_BUILD=True,
            _BUILD_CHANNEL=build_channel,
            _RELEASE_KEYS=all_keys,
            _RELEASE_KEY_ENTRIES=tuple(entries),
            _RELEASE_TRIAL_ONLY=frozenset(trial_keys),
            _RELEASE_MAX_TRIAL_DAYS=14,
        )
        self._env = patch.dict(os.environ, {'TRIPORDERS_DPAPI_DIR': self._prof, 'XDG_CONFIG_HOME': self._prof})
        self._patch.start()
        self._env.start()
        import atrest
        atrest._MASTER = None
        licence._hub_poll_mono = None
        licence._hub_retry_at_mono = None
        licence._hub_retry_delay_sec = licence.HUB_CALENDAR_RETRY_SEC
        self.lic = licence.Licence(_Assist(data_dir), str(ROOT), str(data_dir), {})

    def __enter__(self):
        return self.lic

    def __exit__(self, *exc):
        self._env.stop()
        self._patch.stop()
        import atrest
        atrest._MASTER = None

    @property
    def profile_dir(self):
        return self._prof


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
                l._note_hub_calendar_day((first + timedelta(days=10)).isoformat())
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
                seen = l._hub_calendar_max_day()
                self.assertIsNotNone(seen)
                self.assertGreaterEqual(seen, first + timedelta(days=5))

    def test_trial_watch_still_polls_when_public_time_check_fails(self):
        import afcodes
        first = date.today()
        pem, public = self._trial_keypair()
        with tempfile.TemporaryDirectory() as d:
            with _CommercialLicence(d, release_keys=(public,)) as l:
                l.a.kv('licence_hub_url', 'https://hub.test')
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 14,
                                          device=l.device())['code']
                l.activate(code, manual=True)
                l._hub_watch({'id': 'r1', 'poll_token': 'tok'})
                hub_day = first + timedelta(days=1)
                with patch.object(l, '_call', side_effect=[ConnectionError('offline'),
                        (200, {'calendar_day': hub_day.isoformat(), 'status': 'delivered'})]) as call:
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 2)
                self.assertEqual(call.call_args.args, ('GET', 'https://hub.test/licence/status?id=r1'))
                self.assertEqual(call.call_args.kwargs, {'token': 'tok'})
                self.assertEqual(l._hub_calendar_max_day(), hub_day)
                self.assertTrue(l.status()['full'])

    def test_transport_and_shape_failures_keep_trial_watch_fallback(self):
        import afcodes
        first = date.today()
        pem, public = self._trial_keypair()
        failures = [
            lambda: hub_response(b'{}', missing_bytes=10),
            lambda: hub_response(b'[]'),
            lambda: hub_response(b'null'),
            lambda: hub_response(b'"text"'),
            lambda: hub_response(b'{broken'),
            lambda: hub_response(b'\xff'),
            lambda: hub_response(b'{"calendar_day": []}'),
            lambda: hub_response(b'{"calendar_day": "2026-02-30"}'),
            lambda: urllib.error.HTTPError('https://hub.test/licence/time', 503, 'busy', {},
                                          hub_response(b'{}', missing_bytes=10)),
        ]
        for failure in failures:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                with _CommercialLicence(d, release_keys=(public,)) as l:
                    l.a.kv('licence_hub_url', 'https://hub.test')
                    code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 14,
                                              device=l.device())['code']
                    l.activate(code, manual=True)
                    l._hub_watch({'id': 'r1', 'poll_token': 'tok'})
                    last_good = first + timedelta(days=1)
                    l._note_hub_calendar_day(last_good.isoformat())
                    fallback_day = first + timedelta(days=2)
                    fallback = hub_response(json.dumps({'calendar_day': fallback_day.isoformat()}).encode())
                    with patch.object(licence.urllib.request, 'urlopen', side_effect=[failure(), fallback]) as call:
                        l._poll_hub_calendar()
                    self.assertEqual([c.args[0].full_url for c in call.call_args_list], [
                        'https://hub.test/licence/time', 'https://hub.test/licence/status?id=r1'])
                    self.assertEqual(l._hub_calendar_max_day(), fallback_day)
                    self.assertTrue(l.status()['full'])
                    self.assertIsNone(licence._hub_poll_mono)
                    self.assertIsNotNone(licence._hub_retry_at_mono)

    def test_invalid_watch_response_preserves_last_good_date_and_watch(self):
        import afcodes
        first = date.today()
        pem, public = self._trial_keypair()
        with tempfile.TemporaryDirectory() as d, _CommercialLicence(d, release_keys=(public,)) as l:
            l.a.kv('licence_hub_url', 'https://hub.test')
            l.activate(afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 14,
                                         device=l.device())['code'], manual=True)
            watch = {'id': 'r1', 'poll_token': 'tok'}
            l._hub_watch(watch)
            last_good = first + timedelta(days=1)
            l._note_hub_calendar_day(last_good.isoformat())
            before = l.status()
            with patch.object(licence.urllib.request, 'urlopen', side_effect=[
                    hub_response(b'null'), hub_response(b'[]')]):
                l._poll_hub_calendar()
            self.assertEqual(l._hub_calendar_max_day(), last_good)
            self.assertEqual(l._hub_watch(), watch)
            self.assertEqual(l.status(), before)

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
                record = l._clock_record(create=False)
                if record:
                    record['trial_latch'] = False
                    l._save_clock_record(record)
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
            pem_t, public_trial = self._trial_keypair()
            with _CommercialLicence(d, release_keys=(public_trial,), studio_keys=(public,)) as l:
                first = date_cls.today()
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'standard', first, 30, device=l.device())['code']
                l.activate(code, manual=True)
                licence._cache.clear()
                l._write_max_seen(licence.utcnow() + timedelta(hours=48))
                with patch.object(licence, 'utcnow', return_value=licence.utcnow()):
                    st = l.status()
                self.assertTrue(st['full'], st)
                trial_code = afcodes.issue_code(pem_t, licence.PRODUCT_ID, 'trial', first, 14, device=l.device())['code']
                l.activate(trial_code, manual=True)
                licence._cache.clear()
                l._write_max_seen(licence.utcnow() + timedelta(hours=48))
                with patch.object(licence, 'utcnow', return_value=licence.utcnow()):
                    st_trial = l.status()
                self.assertFalse(st_trial['full'])
                self.assertEqual(st_trial['reason'], 'clock_back')


class PaidHubCalendarTest(unittest.TestCase):
    @contextmanager
    def _paid(self):
        import afcodes
        frozen = date(2026, 1, 15)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        pem, public = TrialClockExpiryTest()._trial_keypair()
        with tempfile.TemporaryDirectory() as d:
            with _CommercialLicence(d, release_keys=(), studio_keys=(public,)) as l:
                with patch.object(licence, 'date', FrozenDate), patch.object(
                        licence, 'utcnow', return_value=licence.parse('2026-01-15T12:00:00Z')):
                    l.a.kv('licence_hub_url', 'https://hub.test')
                    issued = afcodes.issue_code(pem, licence.PRODUCT_ID, 'standard', frozen, 30,
                                                grace_days=3, device=l.device())
                    self.assertTrue(l.activate(issued['code'], manual=True)['full'])
                    self.assertIsNone(l._hub_watch())
                    yield l, frozen, date.fromisoformat(issued['last_day']) + timedelta(days=3)

    def test_frozen_local_date_paid_expires_after_hub_day_passes_grace(self):
        with self._paid() as (l, frozen, end):
            original_code = l.a.kv('licence_code')
            self.assertTrue(l.status()['full'])  # Populate the status cache before polling.
            with patch.object(l, '_call', return_value=(200, {
                    'calendar_day': (end + timedelta(days=1)).isoformat()})) as call:
                l._poll_hub_calendar()
            call.assert_called_once_with('GET', 'https://hub.test/licence/time')
            self.assertEqual(licence.date.today(), frozen)
            self.assertEqual(licence._cache, {})
            st = l.status()
            self.assertEqual(st['state'], 'expired')
            self.assertFalse(st['full'])
            self.assertTrue(st['enforced'])
            self.assertEqual(l.a.kv('licence_code'), original_code)

    def test_paid_grace_last_day_remains_full(self):
        with self._paid() as (l, _, end):
            with patch.object(l, '_call', return_value=(200, {'calendar_day': end.isoformat()})):
                l._poll_hub_calendar()
            st = l.status()
            self.assertEqual(st['state'], 'grace')
            self.assertTrue(st['full'])

    def test_hub_day_earlier_than_local_does_not_change_paid_status(self):
        with self._paid() as (l, frozen, _):
            before = l.status()
            with patch.object(l, '_call', return_value=(200, {
                    'calendar_day': (frozen - timedelta(days=2)).isoformat()})):
                l._poll_hub_calendar()
            self.assertEqual(l._effective_calendar_day(), frozen)
            self.assertEqual(l.status(), before)

    def test_offline_startup_recovers_after_five_minutes_and_resets_cadence(self):
        with self._paid() as (l, frozen, end):
            l._note_hub_calendar_day(frozen.isoformat())
            before = l.status()
            with patch.object(l, '_call', side_effect=[ConnectionError('offline'),
                    (200, {'calendar_day': (end + timedelta(days=1)).isoformat()}),
                    ConnectionError('offline again')]) as call:
                with patch.object(licence.time, 'monotonic', return_value=100):
                    l._poll_hub_calendar()
                    l._poll_hub_calendar()
                self.assertIsNone(licence._hub_poll_mono)
                self.assertEqual(l._hub_calendar_max_day(), frozen)
                self.assertEqual(l.status(), before)
                with patch.object(licence.time, 'monotonic', return_value=399):
                    l._poll_hub_calendar()
                call.assert_called_once_with('GET', 'https://hub.test/licence/time')
                with patch.object(licence.time, 'monotonic', return_value=400):
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 2)
                self.assertEqual(l.status()['state'], 'expired')
                self.assertFalse(l.status()['full'])
                with patch.object(licence.time, 'monotonic', return_value=400 + licence.HUB_CALENDAR_POLL_SEC - 1):
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 2)
                with patch.object(licence.time, 'monotonic', return_value=400 + licence.HUB_CALENDAR_POLL_SEC):
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 3)
                self.assertEqual(licence._hub_retry_at_mono, 400 + licence.HUB_CALENDAR_POLL_SEC + 300)

    def test_failed_checks_back_off_to_six_hours_without_changing_access(self):
        with self._paid() as (l, frozen, _):
            l._note_hub_calendar_day(frozen.isoformat())
            before = l.status()
            now = 100
            with patch.object(l, '_call', side_effect=ConnectionError('offline')) as call:
                for attempt, delay in enumerate([300, 600, 1200, 2400, 4800, 9600, 19200, 21600, 21600], 1):
                    with patch.object(licence.time, 'monotonic', return_value=now):
                        l._poll_hub_calendar()
                    self.assertEqual(call.call_count, attempt)
                    self.assertEqual(licence._hub_retry_at_mono, now + delay)
                    with patch.object(licence.time, 'monotonic', return_value=now + delay - 1):
                        l._poll_hub_calendar()
                    self.assertEqual(call.call_count, attempt)
                    now += delay
            self.assertIsNone(licence._hub_poll_mono)
            self.assertEqual(l._hub_calendar_max_day(), frozen)
            self.assertEqual(l.status(), before)

    def test_http_and_invalid_calendar_responses_retry_without_touching_last_good_date(self):
        failures = [(status, {}) for status in (429, 500, 503)] + [
            (200, shape) for shape in (None, [], 'text', {}, {'calendar_day': None},
                {'calendar_day': 20260217}, {'calendar_day': []}, {'calendar_day': '2026-02-30'},
                {'calendar_day': '20260217'}, {'calendar_day': '2026-02-17extra'})]
        for failure in failures:
            with self.subTest(failure=failure), self._paid() as (l, frozen, end):
                l._note_hub_calendar_day(frozen.isoformat())
                before = l.status()
                failed_response = hub_response(json.dumps(failure[1]).encode())
                if failure[0] != 200:
                    failed_response = urllib.error.HTTPError('https://hub.test/licence/time', failure[0],
                                                            'busy', {}, failed_response)
                recovered = hub_response(json.dumps({'calendar_day': (end + timedelta(days=1)).isoformat()}).encode())
                with patch.object(licence.urllib.request, 'urlopen', side_effect=[failed_response, recovered]) as call:
                    with patch.object(licence.time, 'monotonic', return_value=100):
                        l._poll_hub_calendar()
                    self.assertEqual(l._hub_calendar_max_day(), frozen)
                    self.assertEqual(l.status(), before)
                    self.assertIsNone(licence._hub_poll_mono)
                    with patch.object(licence.time, 'monotonic', return_value=400):
                        l._poll_hub_calendar()
                    self.assertEqual(call.call_count, 2)
                    self.assertFalse(l.status()['full'])

    def test_loop_checks_calendar_even_when_real_activation_step_raises(self):
        for failure in (http.client.IncompleteRead(b'{}', 10), (200, []), RuntimeError('activation')):
            with self.subTest(failure=failure), self._paid() as (l, _, end):
                l._state({'status': 'waiting', 'kind': 'monthly', 'id': 'r1', 'poll_token': 'tok',
                          'created_at': licence.iso(), 'nonce': 'test'})
                l.stop = False

                def finish_iteration(_):
                    l.stop = True

                with patch.object(l, '_call', side_effect=[failure,
                        (200, {'calendar_day': (end + timedelta(days=1)).isoformat()})]) as call, \
                        patch.object(licence.time, 'sleep', side_effect=finish_iteration):
                    l.loop()
                self.assertEqual([c.args[1] for c in call.call_args_list], [
                    'https://hub.test/licence/status?id=r1', 'https://hub.test/licence/time'])
                self.assertEqual(l.status()['state'], 'expired')
                self.assertFalse(l.status()['full'])

    def test_paid_poll_is_limited_and_hub_day_never_moves_back(self):
        with self._paid() as (l, frozen, end):
            future = end + timedelta(days=1)
            with patch.object(l, '_call', side_effect=[
                    (200, {'calendar_day': future.isoformat()}),
                    (200, {'calendar_day': frozen.isoformat()})]) as call:
                with patch.object(licence.time, 'monotonic', return_value=100):
                    l._poll_hub_calendar()
                with patch.object(licence.time, 'monotonic', return_value=100 + licence.HUB_CALENDAR_POLL_SEC - 1):
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 1)
                with patch.object(licence.time, 'monotonic', return_value=100 + licence.HUB_CALENDAR_POLL_SEC):
                    l._poll_hub_calendar()
                self.assertEqual(call.call_count, 2)
            self.assertEqual(l._hub_calendar_max_day(), future)
            self.assertEqual(l.status()['state'], 'expired')

    def test_expired_looking_paid_code_still_checks_hub_time(self):
        with self._paid() as (l, _, end):
            l._note_hub_calendar_day((end + timedelta(days=1)).isoformat())
            self.assertEqual(l.status()['state'], 'expired')
            with patch.object(l, '_call', return_value=(200, {
                    'calendar_day': (end + timedelta(days=2)).isoformat()})) as call:
                l._poll_hub_calendar()
            call.assert_called_once_with('GET', 'https://hub.test/licence/time')
            self.assertEqual(l._effective_calendar_day(), end + timedelta(days=2))

    def test_practice_or_missing_hub_does_not_poll(self):
        with self._paid() as (l, _, _):
            with patch.object(l, '_call') as call:
                l.a.practice = True
                l._poll_hub_calendar()
                l.a.practice = False
                l.a.kv('licence_hub_url', delete=True)
                l._poll_hub_calendar()
            call.assert_not_called()

    def test_never_online_paid_without_hub_day_stays_editable(self):
        with self._paid() as (l, _, _):
            self.assertIsNone(l._hub_calendar_max_day())
            self.assertNotEqual(l.a.kv(licence.HUB_CALENDAR_ESTABLISHED_KEY), '1')
            st = l.status()
            self.assertTrue(st['full'])
            self.assertIn(st['state'], ('active', 'grace'))

    def test_deleted_clock_file_after_hub_day_locks_until_poll_recovers(self):
        import licence_state
        with self._paid() as (l, frozen, end):
            expired_day = (end + timedelta(days=1)).isoformat()
            with patch.object(l, '_call', return_value=(200, {'calendar_day': expired_day})):
                with patch.object(licence.time, 'monotonic', return_value=100):
                    l._poll_hub_calendar()
            licence._cache.clear()
            self.assertEqual(l.status()['state'], 'expired')
            self.assertFalse(l.status()['full'])
            path = os.path.join(
                pathlib.Path(os.environ['TRIPORDERS_DPAPI_DIR']), licence_state.STATE_FILE)
            os.remove(path)
            licence._cache.clear()
            st = l.status()
            self.assertFalse(st['full'])
            self.assertEqual(st['reason'], 'state_corrupt')
            with patch.object(l, '_call', return_value=(200, {'calendar_day': expired_day})) as call:
                with patch.object(licence.time, 'monotonic', return_value=101):
                    l._poll_hub_calendar()
            call.assert_called_once_with('GET', 'https://hub.test/licence/time')
            licence._cache.clear()
            self.assertEqual(l._hub_calendar_max_day(), date.fromisoformat(expired_day))
            self.assertEqual(l.status()['state'], 'expired')
            self.assertFalse(l.status()['full'])

    def test_corrupt_clock_file_recovers_hub_day_and_does_not_fake_sync(self):
        import licence_state
        with self._paid() as (l, _, end):
            expired_day = (end + timedelta(days=1)).isoformat()
            with patch.object(l, '_call', return_value=(200, {'calendar_day': expired_day})):
                with patch.object(licence.time, 'monotonic', return_value=100):
                    l._poll_hub_calendar()
            path = os.path.join(
                pathlib.Path(os.environ['TRIPORDERS_DPAPI_DIR']), licence_state.STATE_FILE)
            with open(path, 'r+b') as f:
                data = bytearray(f.read())
                data[10] ^= 0xFF
                f.seek(0)
                f.write(data)
            licence._cache.clear()
            self.assertFalse(l.status()['full'])
            self.assertIsNone(l._hub_calendar_max_day())
            with patch.object(l, '_call', return_value=(200, {'calendar_day': expired_day})) as call:
                with patch.object(licence.time, 'monotonic', return_value=200):
                    l._poll_hub_calendar()
            self.assertEqual(call.call_count, 1)
            self.assertEqual(licence._hub_poll_mono, 200)
            licence._cache.clear()
            self.assertEqual(l._hub_calendar_max_day(), date.fromisoformat(expired_day))
            self.assertEqual(l.status()['state'], 'expired')
            with patch.object(l, '_call', return_value=(200, {'calendar_day': expired_day})) as call2:
                with patch.object(licence.time, 'monotonic',
                                  return_value=200 + licence.HUB_CALENDAR_POLL_SEC):
                    l._poll_hub_calendar()
            call2.assert_called_once()
            licence._cache.clear()
            self.assertEqual(l.status()['state'], 'expired')
            self.assertFalse(l.status()['full'])


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

class LicenceClockStateTest(unittest.TestCase):
    def _env(self, d):
        prof = os.path.join(d, 'profile')
        os.makedirs(prof, exist_ok=True)
        return patch.dict(os.environ, {'TRIPORDERS_DPAPI_DIR': prof, 'XDG_CONFIG_HOME': prof})

    def test_invalid_mac_on_state_denies_trial(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = TrialClockExpiryTest()._trial_keypair()
            holder = _CommercialLicence(d, release_keys=(public,))
            with holder as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', date_cls.today(), 3, device=l.device())['code']
                l.activate(code, manual=True)
                licence._cache.clear()
                path = os.path.join(holder.profile_dir, 'licence-clock.v1')
                with open(path, 'wb') as f:
                    f.write(b'{"v":1,"bind":"x","max_seen":"2020-01-01T00:00:00Z","hub_calendar_max":null,"trial_latch":false}\n' + b'0' * 64)
                licence._cache.clear()
                st = l.status()
                self.assertFalse(st['full'])
                self.assertEqual(st['reason'], 'state_corrupt')
                licence._cache.clear()
                for _ in range(3):
                    again = l.status()
                    self.assertFalse(again['full'])
                    self.assertEqual(again['reason'], 'state_corrupt')

    def test_garbage_legacy_markers_fail_closed_without_reviving_trial(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            import licence_state
            pem, public = TrialClockExpiryTest()._trial_keypair()
            holder = _CommercialLicence(d, release_keys=(public,))
            with holder as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', date_cls.today(), 3, device=l.device())['code']
                l.activate(code, manual=True)
                path = os.path.join(holder.profile_dir, licence_state.STATE_FILE)
                os.remove(path)
                l.a.kv('max_seen', 'not-valid|deadbeef')
                l.a.kv(licence.TRIAL_EXPIRED_LATCH, 'bad|deadbeef')
                licence._cache.clear()
                st = l.status()
                self.assertFalse(st['full'])
                self.assertEqual(st['reason'], 'state_corrupt')
                licence._cache.clear()
                self.assertFalse(l.status()['full'])

    def test_concurrent_state_writes_do_not_erase_expiry_latch(self):
        import threading
        import licence_state
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = TrialClockExpiryTest()._trial_keypair()
            holder = _CommercialLicence(d, release_keys=(public,))
            with holder as l:
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', date_cls.today(), 3, device=l.device())['code']
                l.activate(code, manual=True)
                bind = l.machine_tag()
                ready = threading.Barrier(2)

                def latch():
                    ready.wait(timeout=2)
                    l._trial_latch_set()

                def watermark():
                    ready.wait(timeout=2)
                    l._write_max_seen(licence.utcnow())

                threads = [threading.Thread(target=fn) for fn in (latch, watermark)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5)
                licence._cache.clear()
                st = l.status()
                self.assertEqual(st['state'], 'expired')
                self.assertFalse(st['full'])

    def test_plaintext_assist_max_seen_does_not_revive_expired_trial(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = TrialClockExpiryTest()._trial_keypair()
            with _CommercialLicence(d, release_keys=(public,)) as l:
                first = date_cls.today()
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', first, 3, device=l.device())['code']
                l.activate(code, manual=True)
                l._note_hub_calendar_day((first + timedelta(days=5)).isoformat())
                licence._cache.clear()
                l.status()
                l.a.kv('max_seen', licence.iso(licence.utcnow()))
                l.a.kv(licence.TRIAL_EXPIRED_LATCH, delete=True)
                licence._cache.clear()
                st = l.status()
                self.assertEqual(st['state'], 'expired')

    def test_cairo_midnight_hub_day_does_not_trigger_clock_back(self):
        with tempfile.TemporaryDirectory() as d:
            import afcodes
            pem, public = TrialClockExpiryTest()._trial_keypair()
            utc = licence.parse('2026-10-13T22:15:00Z')
            hub_day = '2026-10-14'
            with _CommercialLicence(d, release_keys=(public,)) as l:
                with patch.object(licence, 'utcnow', return_value=utc):
                    code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', utc.date(), 14, device=l.device())['code']
                    l.activate(code, manual=True)
                    licence._cache.clear()
                    st = l.status()
                self.assertTrue(st['full'])
                l._note_hub_calendar_day(hub_day)
                licence._cache.clear()
                with patch.object(licence, 'utcnow', return_value=utc):
                    st2 = l.status()
                self.assertNotEqual(st2.get('reason'), 'clock_back')
                self.assertTrue(st2['full'])

    def test_frozen_clock_scheduler_polls_each_process_window(self):
        with tempfile.TemporaryDirectory() as d:
            from datetime import date as date_cls
            import afcodes
            pem, public = TrialClockExpiryTest()._trial_keypair()
            frozen = date_cls.today()
            calls = []
            with _CommercialLicence(d, release_keys=(public,)) as l:
                l.a.kv('hub_url', 'https://hub.test')
                code = afcodes.issue_code(pem, licence.PRODUCT_ID, 'trial', frozen, 14, device=l.device())['code']
                with patch.object(l, '_effective_calendar_day', return_value=frozen):
                    l.activate(code, manual=True)
                l._hub_watch({'id': 'r1', 'poll_token': 'tok'})
                future_day = (frozen + timedelta(days=20)).isoformat()

                def fake_call(method, url, body=None, token=None):
                    self.assertEqual(method, 'GET')
                    self.assertEqual(token, 'tok' if '/licence/status?' in url else None)
                    calls.append(url)
                    return 200, {'calendar_day': future_day, 'status': 'pending'}

                with patch.object(l, '_effective_calendar_day', return_value=frozen):
                    with patch.object(l, '_call', side_effect=fake_call):
                        with patch.object(licence, 'utcnow', return_value=licence.parse('2020-01-01T00:00:00Z')):
                            with patch.object(licence.time, 'monotonic', return_value=100):
                                l._poll_hub_calendar()
                            with patch.object(licence.time, 'monotonic', return_value=100 + licence.HUB_CALENDAR_POLL_SEC):
                                l._poll_hub_calendar()
                                l._poll_hub_calendar()
                self.assertEqual(calls, [
                    'https://hub.test/licence/time', 'https://hub.test/licence/status?id=r1',
                    'https://hub.test/licence/time', 'https://hub.test/licence/status?id=r1',
                ])
                licence._cache.clear()
                with patch.object(l, '_effective_calendar_day', return_value=frozen + timedelta(days=20)):
                    st = l.status()
                self.assertEqual(st['state'], 'expired')


if __name__ == "__main__":
    unittest.main()
