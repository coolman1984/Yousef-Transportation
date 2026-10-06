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
from store import Conflict

log = logging.getLogger('to.gateway')
RANK = {s: i for i, s in enumerate(['draft', 'sent', 'started', 'finished', 'closed', 'cancelled'])}


class GatewayError(Exception):
    """A problem with a message for the person at the office."""


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def link_token(link_secret, trip_id, nonce):
    """22 characters, made from the link secret, so any office PC can make the same link again ("send again")."""
    return b64url(hmac.new(link_secret.encode(), f'TO-LINK1|{trip_id}|{nonce}'.encode(), hashlib.sha256).digest()[:16])


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def sign_headers(secret, method, path, body=b'', t=None, nonce=None):
    t = str(int(t if t is not None else time.time()))
    nonce = nonce or pysecrets.token_hex(16)
    msg = '\n'.join([method, path, t, nonce, hashlib.sha256(body).hexdigest()])
    return {'X-TO-Time': t, 'X-TO-Nonce': nonce, 'X-TO-Sig': hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()}


# --------------------------------------------------------------------------- secrets of this PC
class Secrets:
    """gateway.json: {url, officeSecret, linkSecret, pollSeconds}. The setup code moves them to the other office PCs."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def save(self):
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
        return bool(self.url and self.data.get('officeSecret') and self.data.get('linkSecret'))

    def set_url(self, url):
        url = str(url or '').strip().rstrip('/')
        if url and not re.fullmatch(r'https://[A-Za-z0-9.-]+(:\d+)?', url) and not re.fullmatch(r'http://(127\.0\.0\.1|localhost)(:\d+)?', url):
            raise GatewayError('The address must start with https:// (for example https://trip-orders.yourname.workers.dev).')
        self.data['url'] = url
        self.save()

    def generate(self):
        self.data['officeSecret'] = pysecrets.token_urlsafe(32)
        self.data['linkSecret'] = pysecrets.token_urlsafe(32)
        self.save()

    def setup_code(self):
        if not self.configured:
            raise GatewayError('The mailbox is not set up yet.')
        return b64url(json.dumps({'v': 1, 'u': self.url, 'o': self.data['officeSecret'], 'l': self.data['linkSecret']}).encode())

    def from_code(self, code):
        try:
            raw = re.sub(r'\s+', '', str(code))
            d = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
            assert d['v'] == 1 and d['o'] and d['l']
        except Exception:
            raise GatewayError('This setup code is not valid. Copy it again from the first office PC.')
        self.set_url(d['u'])
        self.data['officeSecret'], self.data['linkSecret'] = d['o'], d['l']
        self.save()


# --------------------------------------------------------------------------- talking to the gateway
class Client:
    def __init__(self, url, secret, timeout=25):
        self.url, self.secret, self.timeout = url.rstrip('/'), secret, timeout

    def call(self, method, path, obj=None, raw=False):
        body = b'' if obj is None else json.dumps(obj).encode()
        req = urllib.request.Request(self.url + path, data=body if method != 'GET' else None, method=method,
                                     headers={**sign_headers(self.secret, method, path, body if method != 'GET' else b''), 'Content-Type': 'application/json',
                                              'User-Agent': 'TripOrders-Office'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = r.read()
                return data if raw else json.loads(data or b'{}')
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise GatewayError('The mailbox refused this PC. The secret does not match the one set on the gateway.')
            if e.code == 503:
                raise GatewayError('The mailbox is running but has no secret yet. Set OFFICE_SECRET on it (see the setup guide).')
            raise GatewayError(f'The mailbox answered with an error ({e.code}).')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GatewayError('Cannot reach the mailbox. Check the internet on this PC and the address.') from e

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
    """(phone time, receive time) as naive Cairo business-time strings. The phone may be set to any zone (even a wrong one): both times are
    exact moments, so the difference is the real drift and the shown times are the same on every PC. A phone time without a zone is Cairo time.
    The original text with its offset stays in the stored event (`payload`)."""
    p = domain.parse_dt(phone_at)
    if p is None:
        return '', ''
    r = domain.parse_dt(recv_at)
    return p.isoformat(timespec='seconds'), r.isoformat(timespec='seconds') if r else ''


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
    def __init__(self, store, journal, node_id, secrets, save_file, log_fn=None):
        self.store, self.journal, self.node_id, self.secrets, self.save_file = store, journal, node_id, secrets, save_file
        self.say = log_fn or (lambda *a: None)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.pushed = {}            # token hash -> signature of the card the gateway has
        self.release = set()        # token hashes whose bound phone the office released
        self.removed = set()        # replaced link hashes the gateway has already been told to remove (the trips keep the list, so a restart repeats it harmlessly)
        self.stat = {'lastOk': None, 'lastError': None, 'lastTry': None, 'waiting': 0, 'oldestSeconds': 0, 'late': False, 'applied': 0}
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
        return Client(self.secrets.url, self.secrets.data['officeSecret'])

    def _loop(self):
        delay = 5
        while not self._stop:
            self.wake.wait(delay if delay > 0 else 1)
            self.wake.clear()
            if self._stop:
                break
            if not self.secrets.configured:
                delay = 30
                continue
            try:
                self.cycle()
                delay = int(self.secrets.data.get('pollSeconds') or 60)
            except GatewayError as e:
                self.stat['lastError'] = str(e)
                delay = min(max(delay * 2, 10), 600)
            except Exception as e:      # never let the thread die; the next round tries again
                log.exception('gateway cycle failed')
                self.stat['lastError'] = 'Unexpected problem: ' + str(e)[:120]
                delay = min(max(delay * 2, 10), 600)

    def status(self):
        return {'configured': self.secrets.configured, 'url': self.secrets.url, 'pollSeconds': int(self.secrets.data.get('pollSeconds') or 60), **self.stat}

    # -- one round
    def cycle(self):
        with self.lock:
            self.stat['lastTry'] = _now()
            self.push_cards()
            self.pull()
            self.stat['lastOk'] = _now()
            self.stat['lastError'] = None

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
