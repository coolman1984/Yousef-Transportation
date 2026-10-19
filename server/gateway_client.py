"""Trip Orders - the office side of the internet mailbox (the gateway).

The office PC never listens on the internet: it only calls out to the gateway. It pushes one small "card" per trip
(what the driver's page shows), pulls what drivers submitted (events and photos), applies them to the trips as one
normal change, and only then acknowledges them. Everything is idempotent: a pull that is repeated, or done by two
office PCs at once, never creates a second copy (event ids are `ev-<uuid>`, photo ids `ph-<uuid>`).

Secrets (the office secret shared with the gateway and the link secret that makes the driver links) live in
gateway.json in the data folder of each PC - never in the shared database, never in logs.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets as pysecrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

import domain
import errkeys
from store import Conflict

log = logging.getLogger('to.gateway')
RANK = {s: i for i, s in enumerate(['draft', 'sent', 'started', 'finished', 'closed', 'cancelled'])}


class GatewayError(Exception):
    """A problem with a message for the person at the office. `reason` is a short code, never a secret."""

    def __init__(self, message, reason=''):
        super().__init__(message)
        self.reason = reason


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def link_token(link_secret, trip_id, nonce):
    """22 characters, made from the link secret, so any office PC can make the same link again ("send again")."""
    return b64url(hmac.new(link_secret.encode(), f'TO-LINK1|{trip_id}|{nonce}'.encode(), hashlib.sha256).digest()[:16])


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def sign_headers(secret, method, path, body=b'', t=None, nonce=None, tenant=None):
    """The tenant id, when this PC has its own mailbox, is part of the signed message and of the headers."""
    t = str(int(t if t is not None else time.time()))
    nonce = nonce or pysecrets.token_hex(16)
    parts = [method, path, t, nonce, hashlib.sha256(body).hexdigest()]
    tenant = str(tenant or '').strip().lower()
    if tenant:
        parts.append(tenant)
    headers = {'X-TO-Time': t, 'X-TO-Nonce': nonce, 'X-TO-Sig': hmac.new(secret.encode(), '\n'.join(parts).encode(), hashlib.sha256).hexdigest()}
    if tenant:
        headers['X-TO-Tenant'] = tenant
    return headers


_URL_RE = (r'https://[A-Za-z0-9.-]+(:\d+)?', r'http://(127\.0\.0\.1|localhost)(:\d+)?')
_TENANT_RE = re.compile(r'^[0-9a-f]{32}$')


# --------------------------------------------------------------------------- secrets of this PC
class Secrets:
    """gateway.json: {url, officeSecret, linkSecret, tenantId, pollSeconds}. The setup code moves them to the other office PCs.
    An automatic mailbox also keeps tenantId. The file is mode 0600 and is never put in the shared database."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        self._lock = threading.RLock()   # save() may run while auto_register already holds the lock
        self.load()

    def load(self):
        with self._lock:
            try:
                with open(self.path, encoding='utf-8') as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def save(self):
        with self._lock:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)

    @property
    def url(self):
        return (self.data.get('url') or '').rstrip('/')

    @property
    def configured(self):
        return bool(self.url and self.has_secrets)

    @property
    def has_secrets(self):
        """The secrets exist on this PC, even before the gateway address is saved (the address comes after the deploy)."""
        return bool(self.data.get('officeSecret') and self.data.get('linkSecret'))

    def blank(self):
        """Nothing was saved yet. A file that already has an address or a secret is never treated as blank."""
        d = self.data
        return not any(str(d.get(k) or '').strip() for k in ('url', 'officeSecret', 'linkSecret', 'tenantId'))

    def set_url(self, url):
        url = self._check_url(url)
        with self._lock:
            self.data['url'] = url
            self.save()

    @staticmethod
    def _check_url(url):
        url = str(url or '').strip().rstrip('/')
        if url and not any(re.fullmatch(p, url) for p in _URL_RE):
            raise GatewayError('The address must start with https:// (for example https://trip-orders.yourname.workers.dev).')
        return url

    def generate(self):
        """A hand-made secret for a gateway the office runs itself. This leaves the automatic mailbox."""
        with self._lock:
            self.data.pop('tenantId', None)
            self.data.pop('auto', None)
            self.data.pop('installId', None)
            self.data['officeSecret'] = pysecrets.token_urlsafe(32)
            self.data['linkSecret'] = pysecrets.token_urlsafe(32)
            self.save()

    def _payload(self):
        body = {'v': 2 if self.data.get('tenantId') else 1, 'u': self.url, 'o': self.data['officeSecret'], 'l': self.data['linkSecret']}
        if self.data.get('tenantId'):
            body['t'] = self.data['tenantId']
        return body

    def setup_code(self):
        if not self.has_secrets:
            raise GatewayError('The mailbox is not set up yet.')
        return b64url(json.dumps(self._payload()).encode())

    def export_blob(self):
        """What an already-paired office PC may receive over the local network. None when this PC has no mailbox."""
        if not self.has_secrets:
            return None
        return self._payload()

    def _checked(self, d):
        try:
            assert isinstance(d, dict) and d.get('v') in (1, 2) and d.get('o') and d.get('l')
            if d['v'] == 2:
                assert _TENANT_RE.fullmatch(str(d.get('t') or ''))
        except Exception:
            raise GatewayError('This setup code is not valid. Copy it again from the first office PC.')
        return d

    def _decode(self, code):
        try:
            raw = re.sub(r'\s+', '', str(code))
            d = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        except Exception:
            raise GatewayError('This setup code is not valid. Copy it again from the first office PC.')
        return self._checked(d)

    def _apply(self, d):
        """One write. The address is checked before anything is changed."""
        url = self._check_url(d.get('u') or '')
        self.data['url'] = url
        self.data['officeSecret'], self.data['linkSecret'] = d['o'], d['l']
        if d.get('v') == 2:
            self.data['tenantId'] = d['t']
            self.data['auto'] = True
        else:
            self.data.pop('tenantId', None)
            self.data.pop('auto', None)
        # A mailbox that arrived from another PC must not retry this PC's own registration later.
        self.data.pop('installId', None)
        self.save()

    def from_code(self, code):
        """An administrator pasted a setup code. This is the explicit fallback, so it may replace what is here."""
        d = self._decode(code)
        with self._lock:
            self._apply(d)

    def apply_remote(self, blob):
        """A mailbox received from another PC of this office. Never replaces an address or a secret already saved here."""
        if not isinstance(blob, dict):
            return False
        with self._lock:
            self.load()
            if not self.blank():
                return False
            self._apply(self._checked(blob))
            return True

    def _ensure_install_id(self):
        """Saved before the request, so a lost answer is retried as the same mailbox. Never logged."""
        cur = str(self.data.get('installId') or '').strip().lower()
        if _TENANT_RE.fullmatch(cur):
            return cur
        cur = pysecrets.token_hex(16)
        self.data['installId'] = cur
        self.save()
        return cur

    def _claim(self, url, install_id):
        """Ask for this PC's mailbox. The answer is not logged: it contains the office secret."""
        body = json.dumps({'installId': install_id}).encode()
        req = urllib.request.Request(url + '/office/register', data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'TripOrders-Office'})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read(8192)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise GatewayError('The mailbox is busy. This PC will try again shortly.', 'busy')
            if e.code == 503:
                raise GatewayError('The mailbox is not ready for a new office yet.', 'notready')
            raise GatewayError('The mailbox did not accept this PC. It will be tried again.', 'rejected')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GatewayError('Cannot reach the mailbox. This PC will try again when the internet is back.', 'offline') from e
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            raise GatewayError('The mailbox did not accept this PC. It will be tried again.', 'rejected')
        if not isinstance(data, dict):
            raise GatewayError('The mailbox did not accept this PC. It will be tried again.', 'rejected')
        tid, sec = str(data.get('tenantId') or ''), str(data.get('officeSecret') or '')
        if not _TENANT_RE.fullmatch(tid) or len(sec) < 32:
            raise GatewayError('The mailbox did not accept this PC. It will be tried again.', 'rejected')
        return tid, sec

    def auto_register(self, url):
        """Claim a private mailbox. Does nothing when this PC already has an address or a secret. Returns True when it saved one."""
        url = self._check_url(url)
        if not url:
            return False
        with self._lock:
            self.load()
            if not self.blank():
                return False
            install_id = self._ensure_install_id()
            link = pysecrets.token_urlsafe(32)
            tid, sec = self._claim(url, install_id)
            self.load()
            if not self.blank():
                return False   # another attempt saved one while we were waiting; the spare mailbox is unused and expires
            self.data['url'] = url
            self.data['tenantId'] = tid
            self.data['officeSecret'] = sec
            self.data['linkSecret'] = link
            self.data['installId'] = install_id
            self.data['auto'] = True
            self.save()
            return True

    def reopen_auto(self, url):
        """The mailbox row was deleted after a long silence. Same install id and same driver-link secret, new office secret.
        A PC that received the mailbox from another PC has no install id and is left unchanged."""
        url = self._check_url(url or self.url)
        if not url:
            return False
        with self._lock:
            self.load()
            install_id = str(self.data.get('installId') or '').strip().lower()
            if not _TENANT_RE.fullmatch(install_id):
                return False
            link = self.data.get('linkSecret') or pysecrets.token_urlsafe(32)
            tid, sec = self._claim(url, install_id)
            self.load()
            if str(self.data.get('installId') or '').strip().lower() != install_id:
                return False
            self.data['url'] = url
            self.data['tenantId'] = tid
            self.data['officeSecret'] = sec
            self.data['linkSecret'] = link
            self.data['installId'] = install_id
            self.data['auto'] = True
            self.save()
            return True


# --------------------------------------------------------------------------- talking to the gateway
class Client:
    def __init__(self, url, secret, timeout=25, tenant=None):
        self.url, self.secret, self.timeout = url.rstrip('/'), secret, timeout
        self.tenant = str(tenant or '').strip().lower() or None

    def call(self, method, path, obj=None, raw=False):
        body = b'' if obj is None else json.dumps(obj).encode()
        req = urllib.request.Request(self.url + path, data=body if method != 'GET' else None, method=method,
                                     headers={**sign_headers(self.secret, method, path, body if method != 'GET' else b'', tenant=self.tenant), 'Content-Type': 'application/json',
                                              'User-Agent': 'TripOrders-Office'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = r.read()
                return data if raw else json.loads(data or b'{}')
        except urllib.error.HTTPError as e:
            if e.code == 401:
                try:
                    info = json.loads(e.read() or b'{}')
                except (ValueError, OSError):
                    info = {}
                if info.get('reason') == 'clock':   # the gateway says it is the clock, not the secret
                    mins = max(1, round(abs(float(info.get('skewSeconds') or 0)) / 60))
                    raise GatewayError(f'The clock of this PC is off by {mins} minutes compared with the mailbox. Correct the date and time of this PC, then try again.', 'clock')
                if info.get('reason') == 'replay':
                    raise GatewayError('The mailbox saw this request twice. Try again.', 'replay')
                if info.get('reason') == 'expired':
                    raise GatewayError('This mailbox was removed after a long time with no use. The first PC connects again by itself. Another PC needs the new setup code from the first one.', 'expired')
                raise GatewayError('The mailbox refused this PC. The secret does not match the one set on the gateway.', 'secret')
            if e.code == 503:
                raise GatewayError('The mailbox is running but has no secret yet. Set OFFICE_SECRET on it (see the setup guide).', 'notready')
            raise GatewayError(f'The mailbox answered with an error ({e.code}).', 'status')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GatewayError('Cannot reach the mailbox. Check the internet on this PC and the address.', 'offline') from e

    def status(self):
        return self.call('GET', '/office/status')

    def put_cards(self, cards, remove=()):
        return self.call('PUT', '/office/cards', {'cards': cards, 'remove': list(remove)})

    def inbox(self, limit=100):
        return self.call('GET', f'/office/inbox?limit={int(limit)}')

    def photo(self, uid):
        return self.call('GET', f'/office/photo/{uid}', raw=True)

    def ack(self, events, photos):
        return self.call('POST', '/office/ack', {'events': list(events), 'photos': list(photos)})


# --------------------------------------------------------------------------- cards and events
def _epoch(iso):
    """Unix seconds of an expiry. A time with a zone is exact; one without (written by an older version) was Cairo office time."""
    d = domain.instant(iso)
    return int(d.timestamp()) if d else None


LATE_AFTER_DAYS = 3        # driver messages that sit in the mailbox longer than this are reported to the office (the mailbox drops them after 30)


def oldest_waiting_seconds(items, now=None):
    """How long the oldest item still in the mailbox has been waiting (0 when none). `items`: inbox events/photos with their `recvAt` (UTC)."""
    now = now or time.time()
    ages = []
    for it in items:
        d = domain.instant(it.get('recvAt'))
        if d:
            ages.append(now - d.timestamp())
    return max(0, int(max(ages))) if ages else 0


def card_for(state, trip):
    """What the driver's page shows - nothing else leaves the office."""
    by = lambda ent: {r['id']: r for r in state.get(ent, [])}  # noqa: E731
    veh, drv, ppl, cat = by('vehicles'), by('drivers'), by('people'), by('tripCategories')
    pax = []
    for p in state.get('tripPassengers', []):
        if p.get('tripId') == trip['id']:
            nm = (ppl.get(p.get('personId')) or {}).get('name') or p.get('freeText')
            if nm:
                pax.append(nm)
    req = (ppl.get(trip.get('requesterId')) or {}).get('name')
    if req and req not in pax:
        pax.insert(0, req)
    v = veh.get(trip.get('vehicleId')) or {}
    return {'tripId': trip['id'], 'no': trip.get('no', ''), 'date': trip.get('date', ''), 'driverName': (drv.get(trip.get('driverId')) or {}).get('name', ''),
            'plate': v.get('plate', ''), 'vehicleType': v.get('type', ''), 'destination': trip.get('destination') or '',
            'stops': [s for s in (trip.get('stops') or []) if isinstance(s, str)][:12], 'passengers': pax[:12],
            'category': (cat.get(trip.get('categoryId')) or {}).get('name', ''), 'status': trip.get('status') or 'draft',
            'startAt': trip.get('startAt') or '', 'startKm': trip.get('startKm')}


def local_pair(phone_at, recv_at):
    """(phone time, receive time) as Cairo business-time strings. The phone may be set to any zone (even a wrong one): both times are exact
    moments, so the difference is the real drift and the shown times are the same on every PC. A phone time without a zone is Cairo time.
    Only a time in the hour the clocks go back keeps its offset (domain.business_text). The phone's original text stays in the stored event."""
    p = domain.business_text(phone_at)
    if not p:
        return '', ''
    return p, domain.business_text(recv_at)


def apply_event(trip, ev, bound_device=''):
    """Change the trip row for one driver event (the trip row is a dict; returns True when it changed).

    The result does not depend on the order the messages reach the office: the first start and the first end are kept,
    an end that arrives before its start still lets the start fill the missing facts later, and a closed or cancelled trip
    is never touched by a late message (every raw event is stored separately for the office to read). A malformed event
    changes nothing instead of raising, so one bad message can never block the others."""
    if not isinstance(ev, dict):
        return False
    body = ev.get('body') if isinstance(ev.get('body'), dict) else {}
    data = body.get('data') if isinstance(body.get('data'), dict) else {}
    p_at, r_at = local_pair(ev.get('phoneAt'), ev.get('recvAt'))
    before = json.dumps(trip, sort_keys=True, default=str)
    status = trip.get('status') or 'draft'
    if bound_device and not trip.get('boundDevice'):
        trip['boundDevice'] = bound_device
    rank = RANK.get(status)
    kind = ev.get('type')
    if rank is None or rank >= RANK['closed']:
        pass                                                    # unknown or closed/cancelled: the office decides, not a late message
    elif kind == 'start':
        if rank < RANK['started']:
            trip.update(status='started', startKm=_int(data.get('startKm')), startAt=p_at, startAtRecv=r_at)
        else:                                                   # an end came first: fill only what is still empty
            if not trip.get('startAt'):
                trip.update(startAt=p_at, startAtRecv=r_at)
            if trip.get('startKm') in (None, ''):
                trip['startKm'] = _int(data.get('startKm'))
    elif kind == 'end' and rank < RANK['finished']:
        trip.update(status='finished', endKm=_int(data.get('endKm')), endAt=p_at, endAtRecv=r_at, locked=True)
        route = domain.norm_text(data.get('routeText')) if isinstance(data.get('routeText'), str) else ''
        if route:
            trip['routeText'] = route
    return json.dumps(trip, sort_keys=True, default=str) != before


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- the background service
class GatewaySync:
    def __init__(self, store, journal, node_id, secrets, save_file, log_fn=None, cfg=None, node=None, joining=None):
        self.store, self.journal, self.node_id, self.secrets, self.save_file = store, journal, node_id, secrets, save_file
        self.cfg = cfg or {}
        self.node = node
        self.joining = joining or (lambda: False)
        self.say = log_fn or (lambda *a: None)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.pushed = {}            # token hash -> signature of the card the gateway has
        self.release = set()        # token hashes whose bound phone the office released
        self.removed = set()        # replaced link hashes the gateway has already been told to remove (the trips keep the list, so a restart repeats it harmlessly)
        self.stat = {'lastOk': None, 'lastError': None, 'lastErrorKey': '', 'lastErrorVars': {}, 'lastTry': None, 'waiting': 0, 'oldestSeconds': 0, 'late': False, 'applied': 0}
        self._stop = False
        self._thread = None

    # -- control
    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name='gateway', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        self.wake.set()

    def kick(self):
        self.wake.set()

    def client(self):
        if not self.secrets.configured:
            raise GatewayError('The mailbox is not set up yet.')
        return Client(self.secrets.url, self.secrets.data['officeSecret'], tenant=self.secrets.data.get('tenantId') or None)

    def _training(self):
        return bool(self.cfg.get('training'))

    def _may_register(self):
        """Only a real office that has no mailbox yet, and only the main PC. A joined PC waits for the mailbox over the local network.
        Training never registers, and a file that already has an address or a secret is left exactly as it is."""
        if self._training() or not self.secrets.blank():
            return False
        if not str(self.cfg.get('gateway_url') or '').strip():
            return False
        if self.joining():
            return False
        role = getattr(self.node, 'role', None) if self.node is not None else None
        return role == 'authority'

    def _loop(self):
        delay = 0
        reg_delay = 2
        while not self._stop:
            if delay:
                self.wake.wait(delay)
            self.wake.clear()
            if self._stop:
                break
            if self._training():
                delay = 60          # practice data is never registered and never pushed
                continue
            if not self.secrets.configured:
                if self._may_register():
                    try:
                        if self.secrets.auto_register(self.cfg.get('gateway_url')):
                            self.say('Mailbox connected automatically')
                            reg_delay = 2
                            delay = 0
                            continue
                    except GatewayError as e:
                        self._note(e)
                        reg_delay = min(max(reg_delay * 2, 2), 600)
                    except Exception:
                        log.exception('mailbox register failed')
                        self._note(GatewayError('Cannot reach the mailbox. This PC will try again when the internet is back.', 'offline'))
                        reg_delay = min(max(reg_delay * 2, 2), 600)
                    delay = reg_delay
                else:
                    delay = 5
                continue
            try:
                self.cycle()
                delay = int(self.secrets.data.get('pollSeconds') or 60)
            except GatewayError as e:
                self._note(e)
                delay = min(max(delay * 2, 10), 600)
            except Exception as e:      # never let the thread die; the next round tries again
                log.exception('gateway cycle failed')
                self.stat['lastError'] = 'Unexpected problem: ' + str(e)[:120]
                self.stat['lastErrorKey'] = ''
                self.stat['lastErrorVars'] = {}
                delay = min(max(delay * 2, 10), 600)

    def _note(self, exc):
        """Remember a mailbox problem in the screen's language. The text is the English source; the key is what the screen shows."""
        self.stat['lastError'] = str(exc)
        key, vars_ = errkeys.key_for(str(exc))
        self.stat['lastErrorKey'] = key
        self.stat['lastErrorVars'] = vars_

    def _reopen(self):
        if self._training():
            return False
        url = self.secrets.url or str(self.cfg.get('gateway_url') or '')
        if not self.secrets.reopen_auto(url):
            return False
        self.pushed.clear()
        self.removed.clear()
        self.release.clear()
        self.say('Mailbox connected again')
        return True

    def status(self):
        return {'configured': self.secrets.configured, 'hasSecrets': self.secrets.has_secrets, 'url': self.secrets.url,
                'auto': bool(self.secrets.data.get('tenantId')), 'pollSeconds': int(self.secrets.data.get('pollSeconds') or 60), **self.stat}

    # -- one round
    def cycle(self):
        with self.lock:
            self.stat['lastTry'] = _now()
            try:
                self.push_cards()
                self.pull()
            except GatewayError as e:
                # The row was removed after 90 idle days. The PC that opened the mailbox connects again;
                # a second PC has no install id, so it is left as it is and the message asks for the new code.
                if e.reason != 'expired' or not self._reopen():
                    raise
                self.push_cards()
                self.pull()
            self.stat['lastOk'] = _now()
            self.stat['lastError'] = None
            self.stat['lastErrorKey'] = ''
            self.stat['lastErrorVars'] = {}

    def push_cards(self):
        st = self.store.state()
        cards, sigs = [], {}
        cutoff = (domain.business_now() - timedelta(days=45)).date().isoformat()
        for t in st.get('trips', []):
            h = t.get('linkHash')
            if not h or str(t.get('date', '')) < cutoff:
                continue
            body = card_for(st, t)
            cancelled = t.get('status') == 'cancelled'
            exp = _epoch(t.get('linkExpiry')) or int(time.time()) + 7 * 86400
            rel = h in self.release
            sig = hashlib.sha1(json.dumps([body, cancelled, exp, rel], sort_keys=True, default=str).encode()).hexdigest()
            if self.pushed.get(h) == sig:
                continue
            sigs[h] = sig
            c = {'tokenHash': h, 'tripId': t['id'], 'body': body, 'cancelled': cancelled, 'expiresAt': exp}
            if rel:
                c['releaseDevice'] = True
            cards.append(c)
        gone = []
        for t in st.get('trips', []):
            if str(t.get('date', '')) >= cutoff:
                gone += [h for h in (t.get('oldLinks') or []) if isinstance(h, str) and h not in self.removed and h != t.get('linkHash')]
        gone = list(dict.fromkeys(gone))
        if gone:                        # replaced links die first: the new card is published only after the old one is gone
            cl = self.client()
            for i in range(0, len(gone), 20):
                cl.put_cards([], remove=gone[i:i + 20])
                self.removed.update(gone[i:i + 20])
        if cards:
            cl = self.client()
            for i in range(0, len(cards), 100):
                cl.put_cards(cards[i:i + 100])
            self.pushed.update(sigs)
            self.release -= {c['tokenHash'] for c in cards if c.get('releaseDevice')}

    def pull(self):
        cl = self.client()
        box = cl.inbox(100)
        events, photos = sorted(box.get('events', []), key=lambda e: e['id']), box.get('photos', [])
        self.stat['waiting'] = len(events) + len(photos)
        if not events and not photos:
            self.stat['oldestSeconds'], self.stat['late'] = 0, False
            return
        ack_e, ack_p = [], []
        by_trip = {}
        for e in events:
            by_trip.setdefault(e['tripId'], []).append(e)
        problem = None                  # one trip or photo that cannot be applied must not hold back the others
        for tid, evs in by_trip.items():
            try:
                ack_e += self._apply_events(tid, evs)
            except Exception as e:
                log.exception('gateway: events of trip %s could not be applied', tid)
                problem = problem or e
        for ph in photos:
            try:
                if self._apply_photo(cl, ph):
                    ack_p.append(ph['uuid'])
            except Exception as e:
                log.exception('gateway: photo %s could not be applied', ph.get('uuid'))
                problem = problem or e
        if ack_e or ack_p:
            cl.ack(ack_e, ack_p)
            self.stat['applied'] += len(ack_e) + len(ack_p)
            self.stat['waiting'] = max(0, self.stat['waiting'] - len(ack_e) - len(ack_p))
        left = [e for e in events if e['uuid'] not in ack_e] + [p for p in photos if p['uuid'] not in ack_p]
        self.stat['oldestSeconds'] = oldest_waiting_seconds(left)
        self.stat['late'] = self.stat['oldestSeconds'] > LATE_AFTER_DAYS * 86400
        if problem:                     # what was applied is acknowledged; the rest stays in the mailbox and the office sees why
            raise problem if isinstance(problem, GatewayError) else GatewayError('A driver message could not be applied and stays in the mailbox: ' + str(problem)[:120])

    # -- applying
    def _trip(self, tid):
        import tripsvc
        return tripsvc._row(self.store, 'trips', tid)

    def _existing(self, table, ids):
        if not ids:
            return set()
        with self.store.lock:
            q = ','.join('?' * len(ids))
            return {r[0] for r in self.store.conn.execute(f'SELECT id FROM {table} WHERE id IN ({q})', list(ids))}

    def _apply_events(self, tid, evs):
        """Returns the uuids that are safe to acknowledge."""
        for attempt in range(3):
            trip = self._trip(tid)
            if not trip:
                log.warning('gateway: events for an unknown trip %s are kept in the mailbox', tid)
                return []
            ver = trip.pop('ver')
            have = self._existing('trip_events', ['ev-' + e['uuid'] for e in evs])
            ops, changed = [], False
            for e in evs:
                if 'ev-' + e['uuid'] in have:
                    continue
                p_at, r_at = local_pair(e.get('phoneAt'), e.get('recvAt'))
                body = dict(e.get('body') or {})
                body['second'] = bool(e.get('second'))
                body['recvAt'] = e.get('recvAt') or ''      # the exact receive time (UTC) next to the phone's own text with its offset
                ops.append({'e': 'tripEvents', 'id': 'ev-' + e['uuid'], 'op': 'put', 'row': {'tripId': tid, 'uuid': e['uuid'], 'type': e.get('type', ''), 'payload': body,
                                                                                               'phoneAt': p_at, 'recvAt': r_at, 'deviceId': e.get('deviceId', '')}})
                changed |= apply_event(trip, e, e.get('boundDevice') or '')
            if not ops:
                return [e['uuid'] for e in evs]
            if changed:
                ops.append({'e': 'trips', 'id': tid, 'op': 'put', 'ver': ver, 'row': trip})
            try:
                driver = 'driver link'
                self.store.commit(f'Driver link ({trip.get("no")})', 'gateway', f'Driver link {trip.get("no")}: ' + ', '.join(str(e.get('type')) for e in evs), ops)
                return [e['uuid'] for e in evs]
            except Conflict:
                time.sleep(0.2)             # somebody edited the trip at the same moment: read it again and repeat
        raise GatewayError('A trip was busy; the driver messages stay in the mailbox and are tried again.')

    def _apply_photo(self, cl, ph):
        trip = self._trip(ph['tripId'])
        if not trip:
            log.warning('gateway: photo for an unknown trip %s is kept in the mailbox', ph['tripId'])
            return False
        if self._existing('trip_photos', ['ph-' + ph['uuid']]):
            return True
        data = cl.photo(ph['uuid'])
        if hashlib.sha256(data).hexdigest() != ph['sha256']:
            raise GatewayError('A photo arrived damaged; it is tried again.')
        src, sha = self.save_file(data, '.jpg')
        _, r_at = local_pair(ph.get('recvAt'), ph.get('recvAt'))
        self.store.commit(f'Driver link ({trip.get("no")})', 'gateway', f'Driver photo {ph["kind"]} for {trip.get("no")}', [
            {'e': 'tripPhotos', 'id': 'ph-' + ph['uuid'], 'op': 'put', 'row': {'tripId': ph['tripId'], 'kind': ph['kind'], 'src': src, 'sha256': sha,
                                                                              'takenAt': r_at, 'fallback': bool(ph.get('fallback')), 'eventId': ('ev-' + ph['eventUuid']) if ph.get('eventUuid') else ''}}])
        return True

    # -- links
    def make_link(self, trip_id, nonce):
        if not self.secrets.configured:
            raise GatewayError('The mailbox is not set up yet. An administrator sets it up in Settings, Mailbox.')
        tok = link_token(self.secrets.data['linkSecret'], trip_id, nonce)
        return tok, f'{self.secrets.url}/t/{tok}'


def _now():
    return domain.business_now().isoformat(timespec='seconds')


def new_nonce():
    return uuid.uuid4().hex[:12]
