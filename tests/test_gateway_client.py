"""The office side of the mailbox against the REAL gateway code (node, local D1 stand-in): links, cards, driver events and photos
applied to trips, idempotency, second phone, cancel, permissions and friendly errors."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unittest
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone

from harness import ApiError, Server, free_port, make_authority, wait_until

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import gateway_client as G  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = 'office-secret-for-the-test-0123456789'
LINK_SECRET = 'link-secret-for-the-test-0123456789'


def node_ok():
    try:
        return subprocess.run(['node', '-e', "require('node:sqlite')"], capture_output=True).returncode == 0
    except OSError:
        return False


class GatewayProcess:
    def __init__(self, secret=SECRET):
        self.port = free_port()
        env = {**os.environ, 'PORT': str(self.port), 'OFFICE_SECRET': secret}
        self.proc = subprocess.Popen(['node', '--no-warnings', os.path.join(ROOT, 'gateway', 'dev', 'server.js')], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line = self.proc.stdout.readline()
        assert line.startswith('READY'), line
        self.url = f'http://127.0.0.1:{self.port}'

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)
        self.proc.stdout.close()

    def driver(self, method, path, body=None, headers=None):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')


def jpeg(n=4000, seed=1):
    b = bytearray((i * seed) & 255 for i in range(n))
    b[0], b[1] = 0xFF, 0xD8
    return bytes(b)


def put(e, i, **row):
    return {'e': e, 'id': i, 'op': 'put', 'row': row}


class UnitTest(unittest.TestCase):
    def test_link_token_is_stable_short_and_url_safe(self):
        a = G.link_token('s', 'tr1', 'n1')
        self.assertEqual(a, G.link_token('s', 'tr1', 'n1'))
        self.assertNotEqual(a, G.link_token('s', 'tr1', 'n2'))
        self.assertNotEqual(a, G.link_token('s2', 'tr1', 'n1'))
        self.assertRegex(a, r'^[A-Za-z0-9_-]{22}$')

    def test_setup_code_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a = G.Secrets(os.path.join(d, 'g.json'))
            a.set_url('https://x.example.workers.dev')
            a.generate()
            b = G.Secrets(os.path.join(d, 'h.json'))
            b.from_code(a.setup_code())
            self.assertEqual((b.url, b.data['officeSecret'], b.data['linkSecret']), (a.url, a.data['officeSecret'], a.data['linkSecret']))
            with self.assertRaises(G.GatewayError):
                b.from_code('garbage')
            with self.assertRaises(G.GatewayError):
                b.set_url('http://evil.example.com')          # plain http only for the local test gateway

    def test_events_change_the_trip_in_order_and_never_go_back(self):
        t = {'status': 'sent'}
        ev = lambda typ, **d: {'type': typ, 'body': {'data': d}, 'phoneAt': '2026-09-28T09:41:12+03:00', 'recvAt': '2026-09-28T06:41:20Z'}  # noqa: E731
        self.assertTrue(G.apply_event(t, ev('start', startKm=1000), 'dev-1'))
        self.assertEqual((t['status'], t['startKm'], t['startAt'], t['boundDevice']), ('started', 1000, '2026-09-28T09:41:12', 'dev-1'))
        self.assertEqual(t['startAtRecv'], '2026-09-28T09:41:20')       # both in the phone's zone: the drift is 8 seconds, not 3 hours
        self.assertFalse(G.apply_event(t, ev('start', startKm=5), ''), 'a second start does not overwrite the first')
        self.assertTrue(G.apply_event(t, ev('end', endKm=1120, routeText='A - B'), ''))
        self.assertEqual((t['status'], t['endKm'], t['routeText'], t['locked']), ('finished', 1120, 'A - B', True))
        self.assertFalse(G.apply_event(t, ev('end', endKm=9999), ''), 'a finished trip is not changed by a late message')
        self.assertEqual(t['endKm'], 1120)
        self.assertFalse(G.apply_event({'status': 'cancelled'}, ev('start', startKm=1), ''))

    def test_f_an_end_that_arrives_before_the_start_keeps_the_start_facts(self):
        """F08: the order the messages reach the office must not decide what the trip knows."""
        import itertools
        ev = lambda typ, at, **d: {'type': typ, 'body': {'data': d}, 'phoneAt': at, 'recvAt': '2026-09-28T09:00:00Z'}  # noqa: E731
        start = ev('start', '2026-09-28T09:00:00+03:00', startKm=1000)
        end = ev('end', '2026-09-28T11:00:00+03:00', endKm=1120, routeText='A - B')
        results = []
        for order in itertools.permutations([start, end, start, end]):          # includes retries and every arrival order
            t = {'status': 'sent'}
            for e in order:
                G.apply_event(t, e, 'dev-1')
            results.append(json.dumps(t, sort_keys=True))
        self.assertEqual(len(set(results)), 1, 'every arrival order gives the same trip')
        t = json.loads(results[0])
        self.assertEqual((t['status'], t['startKm'], t['startAt'], t['endKm'], t['endAt'], t['locked']), ('finished', 1000, '2026-09-28T09:00:00', 1120, '2026-09-28T11:00:00', True))

    def test_g_a_late_message_never_rewrites_a_closed_cancelled_or_filled_trip(self):
        ev = lambda typ, **d: {'type': typ, 'body': {'data': d}, 'phoneAt': '2026-09-28T09:00:00+03:00', 'recvAt': '2026-09-28T06:00:00Z'}  # noqa: E731
        for status in ('closed', 'cancelled'):
            t = {'status': status, 'startKm': None, 'startAt': ''}
            self.assertFalse(G.apply_event(t, ev('start', startKm=5), ''))
            self.assertFalse(G.apply_event(t, ev('end', endKm=9), ''))
            self.assertEqual((t['status'], t['startKm'], t['startAt']), (status, None, ''))
        done = {'status': 'finished', 'startKm': 200, 'startAt': '', 'endKm': 300, 'endAt': '2026-09-28T10:00:00', 'locked': True}
        G.apply_event(done, ev('start', startKm=1), '')               # the office already typed a start odometer: keep it, only fill the empty time
        self.assertEqual((done['startKm'], done['startAt'], done['status']), (200, '2026-09-28T09:00:00', 'finished'))

    def test_h_malformed_events_do_not_break_the_reducer(self):
        good = {'type': 'start', 'phoneAt': '2026-09-28T09:00:00+03:00', 'recvAt': '2026-09-28T06:00:00Z'}
        for bad in ({'type': 'start', 'body': {'data': ['not', 'a', 'dict']}}, {'type': 'start', 'body': 'text'}, {'type': 'start', 'body': None},
                    {'type': 'end', 'body': {'data': {'endKm': 'abc', 'routeText': 5}}}, {'type': 'weird', 'body': {}}, {'body': {}}, {**good, 'phoneAt': None}):
            t = {'status': 'sent'}
            G.apply_event(t, bad, '')                                 # must not raise
        t = {'status': 'mystery'}
        self.assertFalse(G.apply_event(t, {**good, 'body': {'data': {'startKm': 1}}}, ''), 'an unknown status is left alone')

    def test_signature_matches_the_gateway_rule(self):
        h = G.sign_headers('k', 'GET', '/office/status', b'', t=1000, nonce='ab' * 8)
        msg = '\n'.join(['GET', '/office/status', '1000', 'ab' * 8, hashlib.sha256(b'').hexdigest()])
        import hmac
        self.assertEqual(h['X-TO-Sig'], hmac.new(b'k', msg.encode(), hashlib.sha256).hexdigest())


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = GatewayProcess()
        cls.S = Server('gw').start()
        cls.ac = make_authority(cls.S)
        cls.ac.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True, type='Sedan'),
            put('drivers', 'd1', name='Driver One', active=True, mobile='01012345678'),
            put('people', 'p1', name='Sara Adel', isRequester=True, isPassenger=True)]})
        code = base64.urlsafe_b64encode(json.dumps({'v': 1, 'u': cls.gw.url, 'o': SECRET, 'l': LINK_SECRET}).encode()).rstrip(b'=').decode()
        cls.ac.post('/api/gateway/code', {'code': code})

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()
        cls.gw.stop()

    def new_trip(self):
        return self.ac.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'destination': 'Factory-Capital-Factory'})

    def trip(self, tid):
        return next(t for t in self.ac.get('/api/state')['trips'] if t['id'] == tid)

    def token_of(self, url):
        return url.rsplit('/t/', 1)[1]

    def event(self, token, typ, dev='device-AAAA-1', **data):
        e = {'uuid': str(uuid.uuid4()), 'v': 1, 'type': typ, 'deviceId': dev, 'seq': 1, 'phoneAt': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'), 'queued': False, 'data': data}
        st, j = self.gw.driver('POST', f'/api/event/{token}', e)
        self.assertEqual(st, 200, j)
        return e

    def photo(self, token, kind, event=None, fallback=False, seed=1):
        data = jpeg(seed=seed)
        st, j = self.gw.driver('PUT', f'/api/photo/{token}/{uuid.uuid4()}', data, {'X-Kind': kind, 'X-Sha256': hashlib.sha256(data).hexdigest(), 'X-Fallback': '1' if fallback else '0', 'X-Event': event or ''})
        self.assertEqual(st, 200, j)

    def pull(self):
        return self.ac.post('/api/gateway/pull')

    def test_a_full_trip_through_the_mailbox(self):
        t = self.new_trip()
        link = self.ac.post('/api/trips/link', {'id': t['id'], 'sent': True})
        self.assertRegex(link['url'], rf'^{re.escape(self.gw.url)}/t/[A-Za-z0-9_-]{{22}}$')
        self.assertEqual((link['driver'], link['mobile']), ('Driver One', '+201012345678'))
        row = self.trip(t['id'])
        self.assertEqual(row['status'], 'sent')
        token = self.token_of(link['url'])
        self.assertNotIn(token, json.dumps(self.ac.get('/api/state')), 'the link itself is not stored in the database')
        self.assertEqual(row['linkHash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.ac.post('/api/trips/link', {'id': t['id']})['url'], link['url'], 'the same link can be made again')
        self.pull()                                             # pushes the card
        st, card = self.gw.driver('GET', f'/api/card/{token}')
        self.assertEqual(st, 200)
        self.assertEqual((card['card']['no'], card['card']['plate'], card['card']['driverName'], card['card']['passengers']), (t['no'], 'ط و ي 6829', 'Driver One', ['Sara Adel']))
        # the driver: start, end, photos
        e1 = self.event(token, 'start', startKm=45000)
        self.photo(token, 'start_odo', e1['uuid'])
        e2 = self.event(token, 'end', endKm=45120, routeText='Factory - Capital - Factory', stops=['Capital'])
        self.photo(token, 'end_odo', e2['uuid'], seed=3)
        self.photo(token, 'paper', None, seed=5)
        res = self.pull()
        self.assertIsNone(res['lastError'])
        row = self.trip(t['id'])
        self.assertEqual((row['status'], row['startKm'], row['endKm'], row['locked'], row['routeText']), ('finished', 45000, 45120, True, 'Factory - Capital - Factory'))
        self.assertTrue(row['startAt'] and row['endAt'] and row['boundDevice'] == 'device-AAAA-1')
        st = self.ac.get('/api/state')
        self.assertEqual(sorted(p['kind'] for p in st['tripPhotos'] if p['tripId'] == t['id']), ['end_odo', 'paper', 'start_odo'])
        self.assertEqual(len([e for e in st['tripEvents'] if e['tripId'] == t['id']]), 2)
        ins = self.ac.get('/api/insights')[t['id']]
        self.assertEqual((ins['trust'], ins['reasons'], ins['km']), ('green', [], 120))
        # the photo file is really stored and served
        src = next(p['src'] for p in st['tripPhotos'] if p['kind'] == 'paper' and p['tripId'] == t['id'])
        self.assertEqual(self.ac.call('GET', src)[:2], b'\xff\xd8')
        # the mailbox is empty; pulling again changes nothing
        self.assertEqual(self.gw.driver('GET', '/api/card/' + token)[0], 200)
        before = self.ac.get('/api/version')['version']
        self.pull()
        self.assertEqual(self.ac.get('/api/version')['version'], before)

    def test_b_retries_do_not_duplicate_and_a_second_phone_turns_red(self):
        t = self.new_trip()
        token = self.token_of(self.ac.post('/api/trips/link', {'id': t['id']})['url'])
        self.pull()
        e = self.event(token, 'start', startKm=100)
        self.gw.driver('POST', f'/api/event/{token}', e)          # the phone sends the same event again
        self.pull()
        self.assertEqual(len([x for x in self.ac.get('/api/state')['tripEvents'] if x['tripId'] == t['id']]), 1)
        self.event(token, 'end', dev='device-BBBB-2', endKm=180)
        self.photo(token, 'paper')
        self.photo(token, 'start_odo')
        self.pull()
        ins = self.ac.get('/api/insights')[t['id']]
        self.assertIn('R_SECOND_DEVICE', ins['reasons'])
        self.assertEqual(ins['trust'], 'red')
        # the office releases the phone; the trip is not blocked by anything
        self.ac.post('/api/trips/release-device', {'id': t['id']})
        self.assertEqual(self.trip(t['id'])['boundDevice'], '')

    def test_c_cancel_reaches_the_driver(self):
        t = self.new_trip()
        token = self.token_of(self.ac.post('/api/trips/link', {'id': t['id']})['url'])
        self.pull()
        self.assertEqual(self.gw.driver('GET', f'/api/card/{token}')[0], 200)
        self.ac.post('/api/trips/cancel', {'id': t['id'], 'reason': 'Plan changed'})
        self.pull()
        st, j = self.gw.driver('GET', f'/api/card/{token}')
        self.assertEqual((st, j.get('cancelled')), (410, True))

    def test_d_replacing_the_link_kills_the_old_one_and_frees_the_phone(self):
        """F05: the old card is removed from the mailbox, stays removed when a stale PC publishes it again, and what the old phone
        already delivered is kept."""
        t = self.new_trip()
        old = self.ac.post('/api/trips/link', {'id': t['id']})['url']
        old_token = self.token_of(old)
        self.pull()
        self.assertEqual(self.gw.driver('GET', '/api/card/' + old_token)[0], 200)
        self.event(old_token, 'start', startKm=100)                # delivered before the replacement
        new = self.ac.post('/api/trips/link', {'id': t['id'], 'replace': True})['url']
        self.assertNotEqual(old, new)
        old_hash = hashlib.sha256(old_token.encode()).hexdigest()
        row = self.trip(t['id'])
        self.assertEqual((row['linkHash'], row['oldLinks']), (hashlib.sha256(self.token_of(new).encode()).hexdigest(), [old_hash]))
        self.assertNotIn(old_token, json.dumps(self.ac.get('/api/state')))
        self.pull()
        self.assertEqual(self.gw.driver('GET', '/api/card/' + self.token_of(new))[0], 200)
        self.assertEqual(self.gw.driver('GET', '/api/card/' + old_token)[0], 404, 'the replaced link no longer opens')
        e = {'uuid': str(uuid.uuid4()), 'v': 1, 'type': 'end', 'deviceId': 'device-AAAA-1', 'seq': 2, 'phoneAt': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'data': {'endKm': 150}}
        self.assertEqual(self.gw.driver('POST', f'/api/event/{old_token}', e)[0], 404, 'the old phone cannot send as the current link')
        # a PC that was offline still has the old link in its data and publishes it again: it must not come back
        G.Client(self.gw.url, SECRET).put_cards([{'tokenHash': old_hash, 'tripId': t['id'], 'body': {'no': t['no']}, 'cancelled': False, 'expiresAt': int(time.time()) + 3600}])
        self.assertEqual(self.gw.driver('GET', '/api/card/' + old_token)[0], 404)
        # what the old phone had already delivered is applied, and the second replacement keeps the history of hashes
        self.pull()
        self.assertEqual(self.trip(t['id'])['startKm'], 100)
        third = self.ac.post('/api/trips/link', {'id': t['id'], 'replace': True})['url']
        self.assertEqual(self.trip(t['id'])['oldLinks'], [hashlib.sha256(self.token_of(new).encode()).hexdigest(), old_hash])
        self.pull()
        self.assertEqual(self.gw.driver('GET', '/api/card/' + self.token_of(new))[0], 404)
        self.assertEqual(self.gw.driver('GET', '/api/card/' + self.token_of(third))[0], 200)

    def test_f_end_posted_before_start_still_fills_the_start(self):
        """F08 through the real mailbox: the office pulls the end first, the start arrives in a later round."""
        t = self.new_trip()
        token = self.token_of(self.ac.post('/api/trips/link', {'id': t['id']})['url'])
        self.pull()
        self.event(token, 'end', endKm=45120)
        self.assertIsNone(self.pull()['lastError'])
        row = self.trip(t['id'])
        self.assertEqual((row['status'], row['endKm'], row.get('startKm')), ('finished', 45120, None))
        self.event(token, 'start', startKm=45000)
        self.assertIsNone(self.pull()['lastError'])
        row = self.trip(t['id'])
        self.assertEqual((row['status'], row['startKm'], row['endKm']), ('finished', 45000, 45120))
        self.assertTrue(row['startAt'] and row['endAt'])
        self.assertEqual(self.ac.get('/api/insights')[t['id']]['km'], 120)

    def test_e_permissions_and_errors(self):
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/trips/link', {'id': 'nope'})
        self.assertEqual(e.exception.code, 400)
        # a dispatcher can send links but cannot see or change the mailbox settings
        prof = next(p for p in self.ac.get('/api/users')['profiles'] if p['id'] == 'dispatcher')
        self.ac.post('/api/users/save', {'username': 'dispatch', 'full_name': 'Dis Patch', 'password': 'Quarter-pass77', 'must_change': False, 'role': prof['name'], 'perms': prof['perms'], 'scopes': ['cat1']})
        c = self.S.client()
        c.login('dispatch', 'Quarter-pass77')
        with self.assertRaises(ApiError) as e:
            c.get('/api/gateway')
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(ApiError) as e:
            c.get('/api/gateway/secrets')
        self.assertEqual(e.exception.code, 403)
        t = self.new_trip()
        self.assertTrue(c.post('/api/trips/link', {'id': t['id'], 'sent': True})['url'])
        # a wrong secret gives a message the office can act on
        bad = base64.urlsafe_b64encode(json.dumps({'v': 1, 'u': self.gw.url, 'o': 'wrong-secret-wrong-secret-1234', 'l': LINK_SECRET}).encode()).rstrip(b'=').decode()
        self.ac.post('/api/gateway/code', {'code': bad})
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/gateway/test')
        self.assertIn('secret does not match', str(e.exception.msg))
        good = base64.urlsafe_b64encode(json.dumps({'v': 1, 'u': self.gw.url, 'o': SECRET, 'l': LINK_SECRET}).encode()).rstrip(b'=').decode()
        self.ac.post('/api/gateway/code', {'code': good})
        self.assertTrue(self.ac.post('/api/gateway/test')['ok'])
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/gateway/save', {'url': 'http://not-secure.example.com'})
        self.assertIn('https://', str(e.exception.msg))


if __name__ == '__main__':
    unittest.main()
