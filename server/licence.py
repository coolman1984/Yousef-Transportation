"""Licence and trial: a signed, device-bound code, checked on this PC with the vendor's PUBLIC key only (Apps-Factory af-license).

What is enforced and what never is
- Only the vendor's public keys are inside the program (licence_keys.txt, TO_LICENCE_KEYS, or `licence_keys` in config.json). They cannot
  make codes. The trusted Licence Studio on the owner's PC signs a code for THIS PC's device code; the relay Worker only carries it.
- A COMMERCIAL installer pins its trusted public keys in the compiled binary. A customer's
  config file, environment or filesystem cannot replace them. A commercial build with no keys
  fails at BUILD time, and a corrupt/missing embedded policy fails closed at runtime.
- Source development without a compiled release policy retains the historical contract-mode
  assisted pilot (LAUNCH_SCOPE.md). This must NEVER be distributed as the paid installer.
  Nothing in this file is a remote kill switch.
- Without a working code (none, expired, other PC, clock moved back) the program keeps opening, reading, printing, exporting and backing up:
  only actions that change business data are refused (HTTP 402), with the device code to send to the vendor. Data is never deleted,
  hidden or encrypted (BIZ-03).

Asking the company from the licence screen (online activation through the factory hub, the Cloudflare Worker of templates/telemetry-relay)
- The request carries exactly SENT_FIELDS, shown on the screen before it is sent: product, kind, device code, a hash of this PC, the request id,
  the organisation name, the version. Nothing else: no trips, no people, no amounts.
- The request keeps its own id (`nonce`), so sending it again after a lost answer creates nothing new. One trial per PC (the hash).
- Offline or the hub down: the state says so, retries back off (1, 5, 15, 60 minutes) and survive a restart (the state is in assist.db);
  the manual way (device code out, code in) is always on the same screen.
- The answer is checked here exactly like a pasted code (signature, product, device, dates); a wrong, other-PC or forged code is refused.
The hub address is public configuration: FACTORY_HUB_URL, `hub_url` in config.json, or the Settings box. No secret is needed for a request.
"""
import hashlib
import hmac
import http.client
import json
import os
import pathlib
import platform
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

import afcodes
import atrest  # trips.db is SQLCipher when TRIPORDERS_ENCRYPT=1


def _distributed_runtime():
    """True when this process is a shipped binary, not a plain python source run."""
    if getattr(sys, 'frozen', False):
        return True
    if globals().get('__compiled__'):
        return True
    exe = os.path.basename(sys.executable or '').lower()
    return bool(exe) and not exe.startswith('python')


# In installed customer builds this generated module is compiled into TripOrders.exe.
# Never load commercial trust anchors from writable user configuration.
try:
    from _release_policy import (
        COMMERCIAL_BUILD as _COMMERCIAL_BUILD,
        TRUSTED_KEYS as _RELEASE_KEYS,
        BUILD_CHANNEL as _BUILD_CHANNEL,
        TRUSTED_KEY_ENTRIES as _RELEASE_KEY_ENTRIES,
        TRIAL_ONLY_PUBLIC_KEYS as _RELEASE_TRIAL_ONLY,
        MAX_TRIAL_DAYS as _RELEASE_MAX_TRIAL_DAYS,
    )
except ImportError:
    # Compiled binaries must never silently drop into contract mode if a release
    # policy module is missing due to a damaged build.
    _COMMERCIAL_BUILD = _distributed_runtime()
    _RELEASE_KEYS = ()
    _RELEASE_KEY_ENTRIES = ()
    _RELEASE_TRIAL_ONLY = frozenset()
    _RELEASE_MAX_TRIAL_DAYS = 14
    _BUILD_CHANNEL = 'commercial' if _COMMERCIAL_BUILD else 'source'
import hub_time
import licence_state
from version import VERSION

PRODUCT_ID = 'trip-orders'
KINDS = ('trial', 'monthly', 'permanent')
BACKOFF = (60, 300, 900, 3600)
POLL = ((600, 20), (3600, 120), (10 ** 9, 600))
SENT_FIELDS = ('product', 'kind', 'device', 'machine', 'nonce', 'shop', 'ref', 'version')
ACTIVE = ('sending', 'waiting', 'failed')
CLOCK_TOLERANCE_HOURS_TRIAL = 1
CLOCK_TOLERANCE_HOURS_PAID = 72
TRIAL_EXPIRED_LATCH = 'trial_expired_latch'
HUB_CALENDAR_ESTABLISHED_KEY = 'licence_hub_calendar_established'
HUB_WATCH_KEY = 'licence_hub_watch'
HUB_SEALED_DAY_KEY = 'licence_hub_sealed_calendar_max'
HUB_URL_PIN_KEY = 'licence_hub_url_pinned'
HUB_CALENDAR_POLL_SEC = 6 * 3600
HUB_CALENDAR_RETRY_SEC = 5 * 60
HUB_CALENDAR_MAX_JUMP_DAYS = 7
HUB_CALENDAR_CATCHUP_STEPS_PER_POLL = 8
TRIAL_HUB_KIDS = frozenset({'trial-hub', 'trial_hub', 'hub-trial'})
_hub_poll_mono = None
_hub_retry_at_mono = None
_hub_retry_delay_sec = HUB_CALENDAR_RETRY_SEC
_partial_hub_catchup = False
UPGRADE_GRACE_DAYS = 30
UPGRADE_PRIOR_DATA_MIN_AGE_HOURS = 24
UPGRADE_GRACE_FILE = 'commercial_upgrade_grace.json'
UPGRADE_GRACE_META_KEY = 'commercial_upgrade_grace_at'
UPGRADE_GRACE_CONSUMED_META = 'commercial_upgrade_grace_consumed'
UPGRADE_GRACE_EVER_META = 'commercial_upgrade_grace_ever'
_cache = {}
_lock = threading.RLock()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt=None):
    return (dt or utcnow()).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse(text):
    try:
        return datetime.strptime(str(text), '%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None


def _machine_id():
    """A value that stays the same on this PC and differs between PCs. Never personal data."""
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return winreg.QueryValueEx(k, 'MachineGuid')[0]
        except (OSError, ImportError):
            pass
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            with open(path, encoding='ascii') as f:
                value = f.read().strip()
                if value:
                    return value
        except OSError:
            pass
    if platform.system() == 'Darwin':
        try:
            out = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if 'IOPlatformUUID' in line:
                    return line.split('"')[-2]
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.node() or 'unknown'


class Licence:
    def __init__(self, assist, root, home, cfg, shop_name=lambda: ''):
        self.a = assist
        self.root, self.home, self.cfg = root, home, cfg
        self.shop_name = shop_name
        self.stop = False

    # ---------------------------------------------------------------- keys, device, state
    def _trusted_key_entries(self):
        if _COMMERCIAL_BUILD:
            if _RELEASE_KEY_ENTRIES:
                return list(_RELEASE_KEY_ENTRIES)
            return [('', k) for k in _RELEASE_KEYS]
        entries = []
        for raw in os.environ.get('TO_LICENCE_KEYS', '').split(','):
            raw = raw.strip()
            if not raw:
                continue
            if ':' in raw and len(raw.split(':', 1)[0]) <= 40:
                kid, key = raw.split(':', 1)
                entries.append((kid.strip(), key.strip()))
            else:
                entries.append(('', raw))
        for raw in (self.cfg.get('licence_keys') or []):
            text = str(raw).strip()
            if not text:
                continue
            if ':' in text and len(text.split(':', 1)[0]) <= 40:
                kid, key = text.split(':', 1)
                entries.append((kid.strip(), key.strip()))
            else:
                entries.append(('', text))
        for folder in (self.home, self.root):
            path = os.path.join(folder, 'licence_keys.txt')
            if not os.path.exists(path):
                continue
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.split('#', 1)[0].strip()
                    if not line:
                        continue
                    if ':' in line and len(line.split(':', 1)[0]) <= 40:
                        kid, key = line.split(':', 1)
                        entries.append((kid.strip(), key.strip()))
                    else:
                        entries.append(('', line))
        return entries

    def trusted_keys(self):
        return [key for _, key in self._trusted_key_entries()]

    def trial_only_public_keys(self):
        if _COMMERCIAL_BUILD:
            return _RELEASE_TRIAL_ONLY
        keys = set()
        for kid, key in self._trusted_key_entries():
            if kid and kid.lower() in TRIAL_HUB_KIDS:
                keys.add(key)
        return frozenset(keys)

    def _trusted_key_by_kid(self):
        out = {}
        for kid, key in self._trusted_key_entries():
            if kid:
                out[kid.lower()] = key
        return out

    def _read_sealed_hub_day(self):
        raw = self.a.kv(HUB_SEALED_DAY_KEY)
        if not raw:
            return None
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None

    def _seal_hub_day(self, hub_date):
        if not isinstance(hub_date, date):
            return
        prev = self._read_sealed_hub_day()
        if prev and hub_date <= prev:
            return
        self.a.kv(HUB_SEALED_DAY_KEY, hub_date.isoformat())

    def _accept_network_hub_calendar(self, data, recover_clock=False):
        """Trust hub calendar only when signed by a pinned kid; never roll back sealed day."""
        day = hub_time.verify_hub_calendar(data, self._trusted_key_by_kid())
        if not day:
            return False
        try:
            hub_date = date.fromisoformat(day)
        except ValueError:
            return False
        sealed = self._read_sealed_hub_day()
        if sealed and hub_date < sealed:
            return False
        pinned = (self.a.kv(HUB_URL_PIN_KEY) or '').strip().rstrip('/')
        current = (self.hub() or '').strip().rstrip('/')
        if sealed and pinned and current and pinned != current:
            return False
        noted = self._note_hub_calendar_day(day, recover_clock=recover_clock)
        if noted:
            stored = self._hub_calendar_max_day()
            if stored:
                self._seal_hub_day(stored)
            if current and not pinned:
                self.a.kv(HUB_URL_PIN_KEY, current)
        return noted

    def _state_bind(self):
        return self.machine_tag()

    def _legacy_open_state_value(self, field, sealed):
        if not sealed or not isinstance(sealed, str):
            return None
        if '|' not in sealed:
            return None
        value, mac = sealed.rsplit('|', 1)
        pepper = b'AF-LICENCE-STATE/1|trip-orders'
        key = hmac.new(self.machine_tag().encode('ascii'), pepper, hashlib.sha256).digest()
        expected = hmac.new(key, f'{field}|{value}'.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        return value

    def _profile_clock_established(self):
        """True once this office has used the sealed clock profile (not merely a shared OS profile auth file)."""
        if self.a.kv('licence_clock_profile') == '1':
            return True
        if licence_state.migration_marker_exists():
            return True
        return False

    def _licence_clock_past_initial_use(self):
        """Licence or clock profile was used before (fail-closed when the clock file is gone)."""
        if self._profile_clock_established():
            return True
        if (self.a.kv('licence_code') or '').strip():
            return True
        if licence_state.auth_key_on_disk():
            return True
        return False

    def _stored_licence_code(self):
        return bool((self.a.kv('licence_code') or '').strip())

    def _clock_file_missing_or_corrupt(self):
        status, _ = licence_state.read(self._state_bind())
        return status in ('missing', 'corrupt')

    def _disallow_automatic_clock_create(self):
        """Never recreate a deleted clock from status() reads or hub notes."""
        if not self._clock_file_missing_or_corrupt():
            return False
        if self._stored_licence_code():
            return True
        if licence_state.auth_key_on_disk():
            return True
        return False

    def _licence_auth_usable(self):
        """Auth key for sealing; never mint a new key when a licence code is already stored."""
        if (self.a.kv('licence_code') or '').strip() and not licence_state.auth_key_on_disk():
            return False
        return licence_state.auth_available()

    def _allow_clock_state_create(self):
        if self._disallow_automatic_clock_create():
            return False
        if self._profile_clock_established():
            return False
        return True

    def _seal_clock_state_if_missing_or_corrupt(self, bind):
        status, _ = licence_state.read(bind)
        if status in ('missing', 'corrupt') and self._trial_state_required() and self._licence_auth_usable():
            licence_state.seal_fail_closed(bind, 'state_corrupt')

    def _migrate_clock_state_once(self):
        bind = self._state_bind()
        if self._profile_clock_established():
            status, _ = licence_state.read(bind)
            if status in ('missing', 'corrupt'):
                self._seal_clock_state_if_missing_or_corrupt(bind)
            return
        status, _ = licence_state.read(bind)
        if status == 'ok':
            return
        if status == 'corrupt':
            if self._trial_state_required():
                licence_state.seal_fail_closed(bind, 'state_corrupt')
            return
        legacy_max = self.a.kv('max_seen')
        legacy_latch = self.a.kv(TRIAL_EXPIRED_LATCH)
        if not legacy_max and not legacy_latch:
            return
        opened_max = self._legacy_open_state_value('max_seen', legacy_max)
        opened_latch = self._legacy_open_state_value(TRIAL_EXPIRED_LATCH, legacy_latch)
        if not opened_max and opened_latch is None:
            if self._trial_state_required() and self.a.kv('licence_clock_profile') == '1':
                licence_state.seal_fail_closed(bind, 'state_corrupt')
            licence_state.mark_migration_done()
            return
        record = licence_state.empty_record()
        if opened_max:
            dt = parse(opened_max)
            if dt:
                record['max_seen'] = iso(dt)
        if opened_latch is not None:
            record['trial_latch'] = opened_latch == '1'
        licence_state.save(record, bind)
        licence_state.mark_migration_done()

    def _clock_record(self, create=False):
        self._migrate_clock_state_once()
        bind = self._state_bind()
        status, record = licence_state.read(bind)
        if status == 'ok':
            return record
        if status == 'corrupt':
            if self._trial_state_required():
                licence_state.seal_fail_closed(bind, 'state_corrupt')
            return licence_state.load(bind)
        if status == 'missing' and self._profile_clock_established():
            if self._trial_state_required():
                self._seal_clock_state_if_missing_or_corrupt(bind)
            return licence_state.load(bind) if self._trial_state_required() else None
        if not create:
            return None
        record = licence_state.empty_record()
        licence_state.save(record, bind)
        self.a.kv('licence_clock_profile', '1')
        return record

    def _save_clock_record(self, record):
        bind = self._state_bind()
        if record.get('fail_closed'):
            licence_state.save(record, bind)
            return

        def updater(current):
            current.update({k: record[k] for k in record if k not in ('v', 'bind')})
            return current

        licence_state.mutate(bind, updater, create=True)

    def _note_profile_clock_established(self):
        self.a.kv('licence_clock_profile', '1')

    def _note_hub_calendar_established(self):
        self.a.kv(HUB_CALENDAR_ESTABLISHED_KEY, '1')

    def _paid_hub_calendar_required(self):
        if self._trial_state_required():
            return False
        if not (self.a.kv('licence_code') or ''):
            return False
        return self.a.kv(HUB_CALENDAR_ESTABLISHED_KEY) == '1'

    def _hub_calendar_sync_due(self):
        """Re-fetch when a paid PC once stored a hub day but the profile clock no longer has it."""
        return self._paid_hub_calendar_required() and self._hub_calendar_max_day() is None

    def _trial_state_required(self):
        code = self.a.kv('licence_code') or ''
        if not code:
            return False
        keys = self.trusted_keys()
        if not keys:
            return False
        r = afcodes.read_code(code, keys, PRODUCT_ID, self.device(), date.today(),
                              trial_only_keys=self.trial_only_public_keys())
        return r.terms.get('edition') == 'trial'

    def _clock_state_ok(self):
        if self._paid_hub_calendar_required():
            return self._hub_calendar_max_day() is not None
        bind = self._state_bind()
        status, record = licence_state.read(bind)
        if status == 'ok':
            return not record.get('fail_closed')
        if status == 'corrupt':
            return False
        if status == 'missing':
            if self._stored_licence_code():
                return False
            if self._profile_clock_established():
                return False
            return not self._trial_state_required()
        return False

    def _read_max_seen(self):
        allow_create = (
            not self._trial_state_required()
            and not self._paid_hub_calendar_required()
            and not self._disallow_automatic_clock_create()
        )
        record = self._clock_record(create=allow_create)
        if record is None:
            return None
        return parse(record.get('max_seen') or '')

    def _write_max_seen(self, when):
        bind = self._state_bind()
        if licence_state.is_fail_closed(bind):
            return
        profile = self.a.kv('licence_clock_profile') == '1'

        def updater(record):
            prev = parse(record.get('max_seen') or '')
            if prev and when <= prev:
                return record
            record['max_seen'] = iso(when)
            record['fail_closed'] = False
            record.pop('fail_closed_reason', None)
            return record

        create = self._allow_clock_state_create() if not profile else False
        if licence_state.mutate(bind, updater, create=create) is not None:
            self._note_profile_clock_established()
            return
        if not profile:
            self._seal_clock_state_if_missing_or_corrupt(bind)
            return
        if self._trial_state_required() or not self._paid_hub_calendar_required():
            licence_state.seal_fail_closed(bind, 'state_corrupt')

    def _recover_clock_record(self, updater):
        """Persist clock state when the profile file is missing or unreadable."""
        bind = self._state_bind()
        status, record = licence_state.read(bind)
        if status == 'ok':
            record = dict(record)
        else:
            record = licence_state.empty_record()
        record = updater(record)
        licence_state.save(record, bind)
        return record

    def _hub_calendar_max_day(self):
        record = self._clock_record(create=False)
        if not record or not record.get('hub_calendar_max'):
            return None
        try:
            return date.fromisoformat(str(record['hub_calendar_max'])[:10])
        except ValueError:
            return None

    def _write_hub_calendar_max_day(self, hub_date, recover_clock=False):
        bind = self._state_bind()

        def apply_hub(record):
            current = record.get('hub_calendar_max')
            if current:
                try:
                    current_date = date.fromisoformat(str(current)[:10])
                    if hub_date <= current_date:
                        return record
                except ValueError:
                    pass
            record['hub_calendar_max'] = hub_date.isoformat()
            record['fail_closed'] = False
            record.pop('fail_closed_reason', None)
            return record

        create = True if recover_clock else self._allow_clock_state_create()
        saved = licence_state.mutate(bind, apply_hub, create=create)
        if saved is None and recover_clock:
            saved = self._recover_clock_record(apply_hub)
        if saved is None:
            if self._trial_state_required():
                self._seal_clock_state_if_missing_or_corrupt(bind)
            return False
        self._note_profile_clock_established()
        self._note_hub_calendar_established()
        self._seal_hub_day(hub_date)
        return True

    def _trial_latch_set(self):
        bind = self._state_bind()
        if licence_state.is_fail_closed(bind):
            return

        def updater(record):
            record['trial_latch'] = True
            return record

        if licence_state.mutate(bind, updater, create=self._allow_clock_state_create()) is None:
            self._seal_clock_state_if_missing_or_corrupt(bind)
            return
        self._note_profile_clock_established()

    def _trial_latch_active(self):
        record = self._clock_record(create=False)
        return bool(record and record.get('trial_latch'))

    def _clear_trial_latch(self):
        bind = self._state_bind()

        def updater(record):
            record['trial_latch'] = False
            return record

        licence_state.mutate(bind, updater, create=False)

    @property
    def enforced(self):
        return bool(self.trusted_keys())

    def device(self):
        override = os.environ.get('TO_DEVICE_ID') if not _COMMERCIAL_BUILD else None  # tests only; never in sold binaries
        return afcodes.device_code(override or _machine_id(), self.a.kv('install_id'), PRODUCT_ID)

    def machine_tag(self):
        """A hash of this PC for the one-trial-per-PC rule; the PC's own identity never leaves it."""
        ident = (os.environ.get('TO_DEVICE_ID') if not _COMMERCIAL_BUILD else None) or _machine_id()
        return hashlib.sha256(f'AF-MACHINE/1|{ident}|{PRODUCT_ID}'.encode('utf-8')).hexdigest()

    def _clock_tolerance_hours(self, edition):
        if edition == 'trial':
            return CLOCK_TOLERANCE_HOURS_TRIAL
        return CLOCK_TOLERANCE_HOURS_PAID

    def _seen_now(self, edition=None):
        """The latest time this PC has shown: a clock moved back beyond tolerance locks changes until it is right again."""
        now = utcnow()
        last = self._read_max_seen()
        tol = timedelta(hours=self._clock_tolerance_hours(edition))
        if not last or now > last:
            if not last or now - last > timedelta(minutes=5):
                self._write_max_seen(now)
            return False
        return now < last - tol

    def _effective_calendar_day(self, today=None):
        """Latest calendar day used for licence expiry (local, UTC watermark, or hub business day)."""
        today = today or date.today()
        hub_max = self._hub_calendar_max_day()
        if hub_max and hub_max > today:
            today = hub_max
        sealed = self._read_sealed_hub_day()
        if sealed and sealed > today:
            today = sealed
        last = self._read_max_seen()
        if last and last.date() > today:
            today = last.date()
        return today

    def _note_hub_calendar_day(self, hub_day, recover_clock=False):
        """Record hub business calendar progress without fabricating a UTC instant.

        Returns True when the requested day is stored, False on failure or no-op,
        and 'partial' when the hub day is ahead but only a capped step was stored.
        """
        if not isinstance(hub_day, str) or len(hub_day) != 10:
            return False
        try:
            hub_date = date.fromisoformat(hub_day)
        except ValueError:
            return False
        if hub_date.isoformat() != hub_day:
            return False
        requested = hub_date
        current = self._hub_calendar_max_day()
        if current and hub_date <= current:
            return current == hub_date
        effective = date.today()
        if current and current > effective:
            effective = current
        last = self._read_max_seen()
        if last and last.date() > effective:
            effective = last.date()
        if hub_date > effective + timedelta(days=HUB_CALENDAR_MAX_JUMP_DAYS):
            hub_date = effective + timedelta(days=HUB_CALENDAR_MAX_JUMP_DAYS)
        if not self._write_hub_calendar_max_day(hub_date, recover_clock=recover_clock):
            return False
        stored = self._hub_calendar_max_day()
        if stored != hub_date:
            return False
        if requested > stored:
            return 'partial'
        return True

    def _data_dir(self):
        return getattr(self.a, 'data_dir', None) or self.home

    def _trips_db_path(self):
        return os.path.join(self._data_dir(), 'trips.db')

    def _has_prior_office_data(self):
        path = self._trips_db_path()
        if not os.path.exists(path):
            return False
        try:
            conn = atrest.connect(pathlib.Path(path).resolve().as_uri() + '?mode=ro', uri=True)
            try:
                # A fresh install also gets 'initialized' and sample trips on its first boot, so only an
                # office whose database was initialised well before this commercial build first ran counts.
                if not conn.execute('SELECT 1 FROM trips LIMIT 1').fetchone():
                    return False
                row = conn.execute("SELECT value FROM meta WHERE key='initialized'").fetchone()
                if not row:
                    return False
                try:
                    initialised = datetime.fromisoformat(str(row[0]).rstrip('Z')).replace(tzinfo=None)
                except ValueError:
                    return False
                return initialised < datetime.now() - timedelta(hours=UPGRADE_PRIOR_DATA_MIN_AGE_HOURS)
            finally:
                conn.close()
        except Exception:  # sqlcipher3 raises its own error types
            return None  # unknown (locked/busy/unreadable): decide on a later check, never consume the grace for it

    def _trips_meta(self, key):
        trips = self._trips_db_path()
        if not os.path.exists(trips):
            return None
        try:
            conn = atrest.connect(pathlib.Path(trips).resolve().as_uri() + '?mode=ro', uri=True)
            try:
                row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
                return row[0] if row else None
            finally:
                conn.close()
        except Exception:  # sqlcipher3 raises its own error types
            return None

    def _set_trips_meta(self, key, value):
        trips = self._trips_db_path()
        if not os.path.exists(trips):
            return
        try:
            conn = atrest.connect(trips, isolation_level=None)
            conn.execute(
                'INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING',
                (key, value))
            conn.close()
        except Exception:  # sqlcipher3 raises its own error types
            pass

    def _upgrade_grace_consumed(self):
        if self.a.kv('upgrade_grace_consumed'):
            return True
        return self._trips_meta(UPGRADE_GRACE_CONSUMED_META) == '1'

    def _mark_upgrade_grace_consumed(self):
        self.a.kv('upgrade_grace_consumed', '1')
        self._set_trips_meta(UPGRADE_GRACE_CONSUMED_META, '1')

    def _read_grace_started(self):
        started = parse(self.a.kv('upgrade_grace_started_at'))
        path = os.path.join(self._data_dir(), UPGRADE_GRACE_FILE)
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    file_started = parse((json.load(f) or {}).get('started_at'))
                    if file_started and (not started or file_started < started):
                        started = file_started
            except (OSError, ValueError, TypeError):
                pass
        meta_started = parse(self._trips_meta(UPGRADE_GRACE_META_KEY))
        if meta_started and (not started or meta_started < started):
            started = meta_started
        return started

    def _write_grace_started(self, when):
        if self.a.kv('upgrade_grace_started_at'):
            return parse(self.a.kv('upgrade_grace_started_at')) or when
        payload = {'started_at': iso(when)}
        self.a.kv('upgrade_grace_started_at', payload['started_at'])
        path = os.path.join(self._data_dir(), UPGRADE_GRACE_FILE)
        os.makedirs(self._data_dir(), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        self._set_trips_meta(UPGRADE_GRACE_META_KEY, payload['started_at'])
        self._set_trips_meta(UPGRADE_GRACE_EVER_META, '1')
        return when

    def _commercial_upgrade_grace(self):
        """One-time edit grace after upgrading a contract office to commercial (not CI-test, not fresh installs)."""
        if not _COMMERCIAL_BUILD or _BUILD_CHANNEL == 'ci-test' or not self.trusted_keys():
            return None
        if self.a.kv('licence_code'):
            return None
        if self._seen_now(None):
            # clock behind the last seen time: locked while it lasts, but a corrected clock gets the grace back
            return {'upgrade_grace': True, 'upgrade_grace_days_left': 0, 'reason': 'clock_back'}
        if self._upgrade_grace_consumed():
            return {'upgrade_grace': True, 'upgrade_grace_days_left': 0, 'reason': 'upgrade_grace_expired'}
        started = self._read_grace_started()
        if started is None:
            if self._trips_meta(UPGRADE_GRACE_EVER_META) == '1' or self.a.kv('upgrade_grace_started_at'):
                self._mark_upgrade_grace_consumed()
                return {'upgrade_grace': True, 'upgrade_grace_days_left': 0, 'reason': 'upgrade_grace_expired'}
            prior = self._has_prior_office_data()
            if prior is None:
                return None
            if not prior:
                # decided once, on first sight: a fresh install never becomes eligible later
                self._mark_upgrade_grace_consumed()
                return None
            started = self._write_grace_started(utcnow())
        end = started + timedelta(days=UPGRADE_GRACE_DAYS)
        now = utcnow()
        if now < started:
            return {'upgrade_grace': True, 'upgrade_grace_days_left': 0, 'reason': 'clock_back'}
        if now >= end:
            self._mark_upgrade_grace_consumed()
            return {'upgrade_grace': True, 'upgrade_grace_days_left': 0, 'reason': 'upgrade_grace_expired'}
        days_left = max(0, (end.date() - now.date()).days)
        if end.date() == now.date():
            days_left = 0
        return {'upgrade_grace': True, 'upgrade_grace_days_left': days_left, 'reason': 'upgrade_grace'}

    def status(self):
        """{'state', 'full', 'enforced', 'device', 'edition', 'first_day', 'last_day', 'days_left', 'reason'}."""
        keys = self.trusted_keys()
        code = self.a.kv('licence_code') or ''
        dev = self.device()
        today = self._effective_calendar_day()
        if not keys:
            # A broken commercial key policy must NOT unlock edits.
            return {'state': 'none' if _COMMERCIAL_BUILD else 'contract',
                    'full': not _COMMERCIAL_BUILD, 'enforced': bool(_COMMERCIAL_BUILD),
                    'device': dev, 'edition': None, 'first_day': None, 'last_day': None,
                    'days_left': None, 'serial': None, 'reason': 'no_keys', 'build_channel': _BUILD_CHANNEL,
                    'upgrade_grace': False, 'upgrade_grace_days_left': None}
        grace = self._commercial_upgrade_grace()
        if grace and grace.get('upgrade_grace_days_left', 0) > 0:
            return {'state': 'upgrade_grace', 'full': True, 'enforced': True, 'device': dev,
                    'edition': None, 'first_day': None, 'last_day': None,
                    'days_left': grace['upgrade_grace_days_left'], 'serial': None,
                    'reason': grace['reason'], 'build_channel': _BUILD_CHANNEL,
                    'upgrade_grace': True, 'upgrade_grace_days_left': grace['upgrade_grace_days_left']}
        key = (code, dev, today, tuple(keys))
        with _lock:
            cached = _cache.get('v')
            if cached and cached[0] == key:
                result = dict(cached[1])
            else:
                result = self._check(code, dev, today, keys)
                _cache['v'] = (key, dict(result))
        state_ok = self._clock_state_ok()
        if not state_ok:
            bind = self._state_bind()
            status, _ = licence_state.read(bind)
            if self._trial_state_required():
                if (
                    status in ('missing', 'corrupt')
                    or self.a.kv('licence_clock_profile') == '1'
                    or licence_state.migration_marker_exists()
                ) and self._licence_auth_usable():
                    licence_state.seal_fail_closed(bind, 'state_corrupt')
                result.update(state='invalid', full=False, reason='state_corrupt')
            elif self._stored_licence_code() and status in ('missing', 'corrupt'):
                result.update(full=False, reason='state_corrupt')
                if result.get('state') in ('active', 'grace', 'trial'):
                    result.update(state='warning')
            elif self._profile_clock_established():
                result.update(full=False, reason='state_corrupt')
                if result.get('state') in ('active', 'grace', 'trial'):
                    result.update(state='warning')
            clock_back = False
        elif self._paid_hub_calendar_required() and not state_ok:
            result.update(state='invalid', full=False, reason='state_corrupt')
            clock_back = False
        else:
            clock_back = self._seen_now(result.get('edition'))
        if result.get('reason') == 'state_corrupt':
            result['enforced'] = True
            result['build_channel'] = _BUILD_CHANNEL
            result.setdefault('upgrade_grace', False)
            result.setdefault('upgrade_grace_days_left', None)
            return result
        if self._trial_latch_active() and result.get('edition') == 'trial':
            result.update(state='expired', full=False, reason='expired')
        elif result.get('edition') == 'trial' and result.get('last_day'):
            try:
                last_day = date.fromisoformat(str(result['last_day']))
                if today > last_day:
                    self._trial_latch_set()
                    result.update(state='expired', full=False, reason='expired')
            except ValueError:
                pass
        result['enforced'] = True
        result['build_channel'] = _BUILD_CHANNEL
        if clock_back and result['full']:
            result.update(state='clock_back', full=False, reason='clock_back')
        result.setdefault('upgrade_grace', False)
        result.setdefault('upgrade_grace_days_left', None)
        return result

    def _check(self, code, dev, today, keys):
        base = {'device': dev, 'full': False, 'edition': None, 'first_day': None, 'last_day': None, 'days_left': None, 'serial': None, 'reason': ''}
        if not code:
            return {**base, 'state': 'none', 'reason': 'no_code'}
        r = afcodes.read_code(code, keys, PRODUCT_ID, dev, today, trial_only_keys=self.trial_only_public_keys())
        if _COMMERCIAL_BUILD and r.valid and not r.terms.get('device_bound'):
            # Accidentally signed unbound time licences must not be shareable
            # across PCs in any sold or CI-test build.
            return {**base, 'state': 'invalid', 'reason': 'device_required'}
        out = {**base, 'state': r.state, 'full': r.full_access, 'reason': r.reason}
        out.update({k: r.terms.get(k) for k in ('edition', 'first_day', 'last_day', 'days_left', 'serial') if k in r.terms})
        if r.state == 'active' and r.terms.get('edition') == 'trial':
            out['state'] = 'trial'
        return out

    def activate(self, code, manual=True):
        """Check a code before saving it. Returns the new status; raises ValueError(reason). manual: a person pasted it (that code then wins over
        an older request still open); a code that came back from the hub is not a manual choice."""
        keys = self.trusted_keys()
        if not keys:
            raise ValueError('no_keys')
        code = code if isinstance(code, str) else ''
        result = self._check(code, self.device(), self._effective_calendar_day(), keys)
        if result['state'] == 'none':
            raise ValueError('no_code')                              # an empty box must never wipe the working code
        if result['state'] in ('invalid',):
            raise ValueError(result['reason'] or 'invalid')
        if result['state'] == 'expired':
            raise ValueError('expired')
        bind = self._state_bind()
        had_code = self._stored_licence_code()
        st, _ = licence_state.read(bind)
        if result.get('edition') == 'trial' and self._licence_clock_past_initial_use():
            if st in ('missing', 'corrupt') or licence_state.is_fail_closed(bind):
                if self._licence_auth_usable():
                    licence_state.seal_fail_closed(bind, 'state_corrupt')
                raise ValueError('state_corrupt')
        elif result.get('edition') != 'trial':
            if not had_code and st == 'missing':
                if licence_state.auth_available():
                    licence_state.save(licence_state.empty_record(), bind)
                    self._note_profile_clock_established()
            elif had_code and licence_state.is_fail_closed(bind):
                if self._licence_auth_usable():
                    licence_state.save(licence_state.empty_record(), bind)
        self.a.kv('licence_code', afcodes.group(afcodes.normalize(code)))
        self._clear_trial_latch()
        if result.get('edition') == 'trial':
            if licence_state.is_fail_closed(self._state_bind()):
                raise ValueError('state_corrupt')
            self._clock_record(create=True)
            self._note_profile_clock_established()
        if manual:
            self.a.kv('licence_manual_at', iso())
        with _lock:
            _cache.clear()
        return self.status()

    # ---------------------------------------------------------------- asking the company (online activation)
    def hub(self):
        if self.a.practice:
            return ''
        return self.a.licence_hub_url()

    def _state(self, value=None, clear=False):
        if clear:
            self.a.kv('licence_request', delete=True)
            return None
        if value is not None:
            self.a.kv('licence_request', json.dumps(value))
            return value
        raw = self.a.kv('licence_request')
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def _shop(self, override=None):
        text = str(override if override is not None else self.shop_name() or '').strip()
        return (text or str(self.shop_name() or '').strip())[:60]

    def body(self, kind, ref='', nonce='preview', shop=None):
        return {'product': PRODUCT_ID, 'kind': kind, 'device': self.device(), 'machine': self.machine_tag(), 'nonce': nonce,
                'shop': self._shop(shop), 'ref': str(ref or '')[:60], 'version': VERSION}

    def preview(self, kind, ref=''):
        """Exactly what a request would send, for the person to read before pressing the button."""
        if kind not in KINDS:
            kind = 'trial'
        return {'kind': kind, 'sends': self.body(kind, ref), 'available': bool(self.hub()), 'fields': list(SENT_FIELDS)}

    def _superseded(self, st):
        manual = self.a.kv('licence_manual_at')
        return bool(manual and st.get('created_at') and manual > st['created_at'])

    def public(self):
        """What the screen may see (never the poll token)."""
        st = self._state()
        base = {'available': bool(self.hub()), 'fields': list(SENT_FIELDS)}
        if not st:
            return {**base, 'status': 'none'}
        out = {**base, **{k: st.get(k) for k in ('status', 'kind', 'reason', 'created_at', 'tries', 'next_try', 'error', 'serial', 'stage')}}
        if out['status'] in ACTIVE + ('issued',) and self._superseded(st):
            out.update(status='closed', reason='manual', error='')
        if out['status'] != 'waiting' or out.get('error'):
            out['stage'] = ''
        return out

    @staticmethod
    def _call(method, url, body=None, token=None):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', 'User-Agent': f'TripOrders/{VERSION}',
                                              **({'Authorization': 'Bearer ' + token} if token else {})})
        try:
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    code, data = r.status, json.loads(r.read().decode('utf-8') or '{}')
            except urllib.error.HTTPError as e:
                with e:
                    code = e.code
                    try:
                        data = json.loads(e.read().decode('utf-8') or '{}')
                    except ValueError:
                        data = {}
            if not isinstance(data, dict):
                raise ValueError('response_object')
            return code, data
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise ConnectionError(e.__class__.__name__) from None

    @staticmethod
    def _soon(st, seconds):
        st['next_try'] = iso(utcnow() + timedelta(seconds=seconds))

    def _failed(self, st, error):
        st['tries'] = st.get('tries', 0) + 1
        st.update(status='failed' if st.get('id') is None else 'waiting', error=error)
        self._soon(st, BACKOFF[min(st['tries'] - 1, len(BACKOFF) - 1)])

    def begin(self, kind, ref='', by='', shop=None):
        """The button, first half: record the request (no network). Idempotent: a request still running is returned, not repeated."""
        if kind not in KINDS:
            raise ValueError('bad kind')
        if not self.hub():
            raise LookupError('trial_off')
        with _lock:
            st = self._state()
            if st and st.get('status') in ACTIVE + ('issued',):
                return self.public()
            if kind == 'trial' and self.status()['full'] and self.enforced:
                raise LookupError('have_licence')
            self._state({'status': 'sending', 'kind': kind, 'nonce': str(uuid.uuid4()), 'ref': str(ref or '').strip()[:60],
                         'shop': self._shop(shop), 'id': None,
                         'poll_token': None, 'created_at': iso(), 'by': by, 'tries': 0, 'error': '', 'reason': ''})
        return self.public()

    def clear(self):
        with _lock:
            st = self._state()
            if st and st.get('status') in ('refused', 'failed', 'activated', 'closed'):
                self._state(clear=True)
        return self.public()

    def step(self, now=None, force=False):
        """One look: send the request, or ask for the answer. Never raises; the state says what happened."""
        with _lock:
            st = self._state()
            if not st or st.get('status') not in ACTIVE + ('issued',):
                return self.public()
            if self._superseded(st):
                st.update(status='closed', reason='manual', error='', poll_token=None)
                self._state(st)
                return self.public()
            now = now or utcnow()
            due = parse(st.get('next_try'))
            if not force and due and now < due:
                return self.public()
            url = self.hub()
            if not url:
                st.update(status='failed', error='relay_off')
                self._state(st)
                return self.public()
            st['stage'] = ''
            try:
                if not st.get('id'):
                    code, d = self._call('POST', url + '/licence/request',
                                          self.body(st['kind'], st.get('ref', ''), st['nonce'], shop=st.get('shop')))
                    if code in (429, 503):
                        self._failed(st, 'busy')
                    elif code == 400:
                        st.update(status='failed', error='refused_input:' + str(d.get('field', '')))
                    elif d.get('replay') and not d.get('poll_token'):
                        st['nonce'] = str(uuid.uuid4())              # the first answer was lost: a new request id makes a new request
                        self._soon(st, 5)
                    else:
                        st.update(id=d.get('id'), poll_token=d.get('poll_token'), status='waiting', error='', tries=0, reason=d.get('reason', ''))
                        if d.get('status') == 'refused':
                            st.update(status='refused', reason=d.get('reason', 'refused'))
                        self._soon(st, 5)
                else:
                    code, d = self._call('GET', url + '/licence/status?id=' + str(st['id']), token=st['poll_token'])
                    if code == 401:
                        st.update(status='failed', error='token', id=None, poll_token=None, nonce=str(uuid.uuid4()))
                    elif code != 200:
                        self._failed(st, f'http_{code}')
                    else:
                        self._accept_network_hub_calendar(d)
                        if d.get('status') == 'issued':
                            self._activate(st, url, d.get('code'))
                        elif d.get('status') == 'refused':
                            st.update(status='refused', reason=d.get('reason') or 'refused', error='')
                        elif d.get('status') == 'expired':
                            st.update(status='closed', reason='expired', error='')
                        elif d.get('status') == 'delivered':
                            st.update(status='activated' if self.status()['full'] else 'closed', reason='delivered', error='')
                        else:
                            age = (now - (parse(st['created_at']) or now)).total_seconds()
                            st.update(status='waiting', error='', stage='approved' if d.get('stage') == 'approved' else '')
                            self._soon(st, next(wait for limit, wait in POLL if age < limit))
            except ConnectionError as e:
                self._failed(st, 'offline:' + str(e))
            self._state(st)
            return self.public()

    def _activate(self, st, url, code):
        """The answer arrived: check it exactly like a pasted code. Only a code that works is saved, and only then does the hub forget it."""
        if self._superseded(st):
            st.update(status='closed', reason='manual', error='', poll_token=None)
            return
        poll_token = st.get('poll_token')
        request_id = st.get('id')
        try:
            self.activate(code, manual=False)
        except ValueError as e:
            st.update(status='failed', error='code:' + str(e), reason=str(e))      # shown with the manual way; the hub keeps the code
            self._soon(st, 900)
            return
        activated = self.status()
        if activated.get('edition') == 'trial' and poll_token and request_id:
            self._hub_watch({'id': request_id, 'poll_token': poll_token})
        elif activated.get('edition') != 'trial':
            self._hub_watch(clear=True)
        try:
            self._call('POST', url + '/licence/ack', {'id': st['id']}, token=poll_token)
        except ConnectionError:
            pass                                                    # saved and working; ack clears the code on the hub when it arrives
        st.update(status='activated', serial=activated.get('serial'), error='', poll_token=None)

    def _hub_watch(self, value=None, clear=False):
        if clear:
            self.a.kv(HUB_WATCH_KEY, delete=True)
            return None
        if value is not None:
            self.a.kv(HUB_WATCH_KEY, json.dumps(value))
            return value
        raw = self.a.kv(HUB_WATCH_KEY)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def _poll_hub_calendar(self):
        global _hub_poll_mono, _hub_retry_at_mono, _hub_retry_delay_sec, _partial_hub_catchup
        url = self.hub()
        if not url:
            return
        now_mono = time.monotonic()
        if _hub_retry_at_mono is not None:
            if now_mono < _hub_retry_at_mono:
                return
        elif _hub_poll_mono is not None and now_mono - _hub_poll_mono < HUB_CALENDAR_POLL_SEC:
            if not self._hub_calendar_sync_due():
                return
        synced = False
        noted = False
        catchup_steps = 0
        prev_stored = self._hub_calendar_max_day()
        try:
            while True:
                code, d = self._call('GET', url + '/licence/time')
                if code == 200 and isinstance(d, dict):
                    noted = self._accept_network_hub_calendar(d, recover_clock=True)
                    if noted == 'partial':
                        _partial_hub_catchup = True
                        stored = self._hub_calendar_max_day()
                        if stored == prev_stored:
                            break
                        prev_stored = stored
                        catchup_steps += 1
                        if catchup_steps >= HUB_CALENDAR_CATCHUP_STEPS_PER_POLL:
                            break
                        continue
                    synced = noted is True
                break
            if synced:
                with _lock:
                    _cache.clear()
        except ConnectionError:
            pass
        # These timers only schedule network checks; they never measure use or decide expiry.
        if synced:
            _hub_poll_mono = now_mono
            _hub_retry_at_mono = None
            _hub_retry_delay_sec = HUB_CALENDAR_RETRY_SEC
        elif noted == 'partial':
            _hub_retry_at_mono = now_mono
        else:
            _hub_retry_at_mono = now_mono + _hub_retry_delay_sec
            _hub_retry_delay_sec = min(_hub_retry_delay_sec * 2, HUB_CALENDAR_POLL_SEC)

        watch = self._hub_watch()
        if not watch or not watch.get('id') or not watch.get('poll_token'):
            return
        st = self.status()
        if st.get('edition') != 'trial' or st.get('state') in ('expired', 'invalid', 'none'):
            self._hub_watch(clear=True)
            return
        try:
            code, d = self._call('GET', url + '/licence/status?id=' + str(watch['id']), token=watch['poll_token'])
            if code == 200 and isinstance(d, dict) and self._accept_network_hub_calendar(
                    d, recover_clock=True) is True:
                with _lock:
                    _cache.clear()
            elif code == 401:
                self._hub_watch(clear=True)
        except ConnectionError:
            pass

    def loop(self, every=20):
        """Background: look for the answer while a request is open, even when nobody has the page open."""
        while not self.stop:
            try:
                st = self._state()
                if st and st.get('status') in ACTIVE + ('issued',):
                    self.step()
            except Exception:  # noqa: BLE001 - activation must not prevent calendar checks
                pass
            try:
                self._poll_hub_calendar()
            except Exception:  # noqa: BLE001 - never let this reach the program
                pass
            time.sleep(every)

    def start(self):
        global _hub_poll_mono, _hub_retry_at_mono, _hub_retry_delay_sec, _partial_hub_catchup
        _hub_poll_mono = None
        _hub_retry_at_mono = None
        _hub_retry_delay_sec = HUB_CALENDAR_RETRY_SEC
        _partial_hub_catchup = False
        threading.Thread(target=self.loop, daemon=True, name='licence').start()
