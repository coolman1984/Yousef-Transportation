"""Licence and trial: a signed, device-bound code, checked on this PC with the vendor's PUBLIC key only (Apps-Factory af-license).

What is enforced and what never is
- Only the vendor's public keys are inside the program (licence_keys.txt, TO_LICENCE_KEYS, or `licence_keys` in config.json). They cannot
  make codes. The trusted Licence Studio on the owner's PC signs a code for THIS PC's device code; the relay Worker only carries it.
- Enforcement is on only when the build carries public keys. Without keys the program says "licence by contract" and works fully: that
  is the assisted pilot (LAUNCH_SCOPE.md, manual licensing). Nothing in this file is a kill switch.
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
import platform
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

import afcodes
from version import VERSION

PRODUCT_ID = 'trip-orders'
KINDS = ('trial', 'monthly', 'permanent')
BACKOFF = (60, 300, 900, 3600)
POLL = ((600, 20), (3600, 120), (10 ** 9, 600))
SENT_FIELDS = ('product', 'kind', 'device', 'machine', 'nonce', 'shop', 'ref', 'version')
ACTIVE = ('sending', 'waiting', 'failed')
CLOCK_TOLERANCE_HOURS = 24
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
        override = os.environ.get('TO_DEVICE_ID')                    # tests only: a fixed identity for a fake PC
        return afcodes.device_code(override or _machine_id(), self.a.kv('install_id'), PRODUCT_ID)

    def machine_tag(self):
        """A hash of this PC for the one-trial-per-PC rule; the PC's own identity never leaves it."""
        ident = os.environ.get('TO_DEVICE_ID') or _machine_id()
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

    def status(self):
        """{'state', 'full', 'enforced', 'device', 'edition', 'first_day', 'last_day', 'days_left', 'reason'}."""
        keys = self.trusted_keys()
        code = self.a.kv('licence_code') or ''
        dev = self.device()
        today = date.today()
        if not keys:
            return {'state': 'contract', 'full': True, 'enforced': False, 'device': dev, 'edition': None, 'first_day': None, 'last_day': None,
                    'days_left': None, 'serial': None, 'reason': 'no_keys'}
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
        if clock_back and result['full']:
            result.update(state='clock_back', full=False, reason='clock_back')
        return result

    @staticmethod
    def _check(code, dev, today, keys):
        base = {'device': dev, 'full': False, 'edition': None, 'first_day': None, 'last_day': None, 'days_left': None, 'serial': None, 'reason': ''}
        if not code:
            return {**base, 'state': 'none', 'reason': 'no_code'}
        r = afcodes.read_code(code, keys, PRODUCT_ID, dev, today)
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
