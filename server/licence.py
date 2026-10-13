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
    from _release_policy import COMMERCIAL_BUILD as _COMMERCIAL_BUILD, TRUSTED_KEYS as _RELEASE_KEYS, BUILD_CHANNEL as _BUILD_CHANNEL
except ImportError:
    # Compiled binaries must never silently drop into contract mode if a release
    # policy module is missing due to a damaged build.
    _COMMERCIAL_BUILD = _distributed_runtime()
    _RELEASE_KEYS = ()
    _BUILD_CHANNEL = 'commercial' if _COMMERCIAL_BUILD else 'source'
from version import VERSION

PRODUCT_ID = 'trip-orders'
KINDS = ('trial', 'monthly', 'permanent')
BACKOFF = (60, 300, 900, 3600)
POLL = ((600, 20), (3600, 120), (10 ** 9, 600))
SENT_FIELDS = ('product', 'kind', 'device', 'machine', 'nonce', 'shop', 'ref', 'version')
ACTIVE = ('sending', 'waiting', 'failed')
CLOCK_TOLERANCE_HOURS = 24
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
    def trusted_keys(self):
        if _COMMERCIAL_BUILD:
            return list(_RELEASE_KEYS)  # pinned in the compiled program; customer config/env ignored
        keys = [k.strip() for k in os.environ.get('TO_LICENCE_KEYS', '').split(',') if k.strip()]
        keys += [str(k).split(':', 1)[-1].strip() for k in (self.cfg.get('licence_keys') or []) if str(k).strip()]
        for folder in (self.home, self.root):
            path = os.path.join(folder, 'licence_keys.txt')
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    for line in f:
                        line = line.split('#', 1)[0].strip()
                        if line:
                            keys.append(line.split(':', 1)[-1])      # "kid:key" or "key"
        return keys

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

    def _seen_now(self):
        """The latest time this PC has shown: a clock moved back by more than a day locks changes until it is right again."""
        now = utcnow()
        last = parse(self.a.kv('max_seen'))
        if not last or now > last:
            if not last or now - last > timedelta(minutes=5):
                self.a.kv('max_seen', iso(now))
            return False
        return now < last - timedelta(hours=CLOCK_TOLERANCE_HOURS)

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
        if self._seen_now():
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
        today = date.today()
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
        clock_back = self._seen_now()
        key = (code, dev, today, tuple(keys))
        with _lock:
            cached = _cache.get('v')
            if cached and cached[0] == key:
                result = dict(cached[1])
            else:
                result = self._check(code, dev, today, keys)
                _cache['v'] = (key, dict(result))
        result['enforced'] = True
        result['build_channel'] = _BUILD_CHANNEL
        if clock_back and result['full']:
            result.update(state='clock_back', full=False, reason='clock_back')
        result.setdefault('upgrade_grace', False)
        result.setdefault('upgrade_grace_days_left', None)
        return result

    @staticmethod
    def _check(code, dev, today, keys):
        base = {'device': dev, 'full': False, 'edition': None, 'first_day': None, 'last_day': None, 'days_left': None, 'serial': None, 'reason': ''}
        if not code:
            return {**base, 'state': 'none', 'reason': 'no_code'}
        r = afcodes.read_code(code, keys, PRODUCT_ID, dev, today)
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
        result = self._check(code, self.device(), date.today(), keys)
        if result['state'] == 'none':
            raise ValueError('no_code')                              # an empty box must never wipe the working code
        if result['state'] in ('invalid',):
            raise ValueError(result['reason'] or 'invalid')
        if result['state'] == 'expired':
            raise ValueError('expired')
        self.a.kv('licence_code', afcodes.group(afcodes.normalize(code)))
        if manual:
            self.a.kv('licence_manual_at', iso())
        with _lock:
            _cache.clear()
        return self.status()

    # ---------------------------------------------------------------- asking the company (online activation)
    def hub(self):
        return self.a.hub_url() if not self.a.practice else ''

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

    def body(self, kind, ref='', nonce='preview'):
        return {'product': PRODUCT_ID, 'kind': kind, 'device': self.device(), 'machine': self.machine_tag(), 'nonce': nonce,
                'shop': str(self.shop_name() or '')[:60], 'ref': str(ref or '')[:60], 'version': VERSION}

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
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode('utf-8') or '{}')
            except ValueError:
                return e.code, {}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            raise ConnectionError(e.__class__.__name__) from None

    @staticmethod
    def _soon(st, seconds):
        st['next_try'] = iso(utcnow() + timedelta(seconds=seconds))

    def _failed(self, st, error):
        st['tries'] = st.get('tries', 0) + 1
        st.update(status='failed' if st.get('id') is None else 'waiting', error=error)
        self._soon(st, BACKOFF[min(st['tries'] - 1, len(BACKOFF) - 1)])

    def begin(self, kind, ref='', by=''):
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
            self._state({'status': 'sending', 'kind': kind, 'nonce': str(uuid.uuid4()), 'ref': str(ref or '').strip()[:60], 'id': None,
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
                    code, d = self._call('POST', url + '/licence/request', self.body(st['kind'], st.get('ref', ''), st['nonce']))
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
                    elif d.get('status') == 'issued':
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
        try:
            self.activate(code, manual=False)
        except ValueError as e:
            st.update(status='failed', error='code:' + str(e), reason=str(e))      # shown with the manual way; the hub keeps the code
            self._soon(st, 900)
            return
        try:
            self._call('POST', url + '/licence/ack', {'id': st['id']}, token=st['poll_token'])
        except ConnectionError:
            pass                                                    # saved and working; the hub drops the code by itself after two weeks
        st.update(status='activated', serial=self.status().get('serial'), error='', poll_token=None)

    def loop(self, every=20):
        """Background: look for the answer while a request is open, even when nobody has the page open."""
        while not self.stop:
            try:
                st = self._state()
                if st and st.get('status') in ACTIVE + ('issued',):
                    self.step()
            except Exception:  # noqa: BLE001 - never let this reach the program
                pass
            time.sleep(every)

    def start(self):
        threading.Thread(target=self.loop, daemon=True, name='licence').start()
