"""The office side of the mailbox against the REAL gateway code (node, local D1 stand-in): links, cards, driver events and photos
applied to trips, idempotency, second phone, cancel, permissions and friendly errors."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
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
    def __init__(self, secret=SECRET, db=None, master='master-key-for-the-office-tests-0123456789', port=None):
        self.port = port or free_port()
        self.master = master
        env = {**os.environ, 'PORT': str(self.port), 'OFFICE_SECRET': secret, 'MASTER_KEY': master, **({'GATEWAY_DB': db} if db else {})}
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

    def test_i_the_age_of_the_oldest_waiting_driver_message_is_reported(self):
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc).timestamp()
        items = [{'recvAt': '2026-10-10T11:00:00Z'}, {'recvAt': '2026-10-05T12:00:00Z'}, {'recvAt': 'junk'}, {}]
        self.assertEqual(G.oldest_waiting_seconds(items, now), 5 * 86400)
        self.assertEqual(G.oldest_waiting_seconds([], now), 0)
        self.assertEqual(G.oldest_waiting_seconds([{'recvAt': '2026-10-11T00:00:00Z'}], now), 0, 'never negative')

    def test_signature_matches_the_gateway_rule(self):
        h = G.sign_headers('k', 'GET', '/office/status', b'', t=1000, nonce='ab' * 8)
        msg = '\n'.join(['GET', '/office/status', '1000', 'ab' * 8, hashlib.sha256(b'').hexdigest()])
        import hmac
        self.assertEqual(h['X-TO-Sig'], hmac.new(b'k', msg.encode(), hashlib.sha256).hexdigest())
        self.assertNotIn('X-TO-Tenant', h)
        tenant = 'ab' * 16
        ht = G.sign_headers('k', 'GET', '/office/status', b'', t=1000, nonce='ab' * 8, tenant=tenant)
        msg_t = msg + '\n' + tenant
        self.assertEqual(ht['X-TO-Tenant'], tenant)
        self.assertEqual(ht['X-TO-Sig'], hmac.new(b'k', msg_t.encode(), hashlib.sha256).hexdigest())

    def test_an_existing_mailbox_is_not_replaced_and_a_setup_code_carries_the_tenant(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a = G.Secrets(os.path.join(d, 'a.json'))
            a.set_url('https://keep.example.workers.dev')
            a.generate()
            kept = a.data['officeSecret']
            self.assertFalse(a.auto_register('http://127.0.0.1:9'), 'a saved address is not a fresh install')
            self.assertEqual(a.data['officeSecret'], kept)
            a.data['tenantId'] = 'cd' * 16
            a.data['auto'] = True
            a.save()
            b = G.Secrets(os.path.join(d, 'b.json'))
            b.from_code(a.setup_code())
            self.assertEqual((b.data['tenantId'], b.data['officeSecret'], b.url), ('cd' * 16, kept, a.url))
            c = G.Secrets(os.path.join(d, 'c.json'))
            c.set_url('https://other.example.workers.dev')
            c.generate()
            self.assertFalse(c.apply_remote(a.export_blob()))
            self.assertNotEqual(c.data['officeSecret'], kept)
            fresh = G.Secrets(os.path.join(d, 'd.json'))
            self.assertTrue(fresh.apply_remote(a.export_blob()))
            self.assertEqual(fresh.data['tenantId'], 'cd' * 16)


class SecretsBeforeAddressTest(unittest.TestCase):
    """Regression (2026-10-12): "Create the secrets" said done but nothing showed, because the secrets could only be read once a
    gateway address was saved - and the address only exists after the deploy that needs the office secret."""

    @classmethod
    def setUpClass(cls):
        cls.S = Server('gwsecrets').start()
        cls.ac = make_authority(cls.S)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()

    def test_secrets_shown_without_address_and_replace_needs_consent(self):
        ac = self.ac
        st = ac.get('/api/gateway')
        self.assertFalse(st['hasSecrets'])
        with self.assertRaises(ApiError) as e:
            ac.get('/api/gateway/secrets')
        self.assertEqual(e.exception.code, 400)
        ac.post('/api/gateway/save', {'url': '', 'pollSeconds': 60})
        st = ac.post('/api/gateway/generate', {})
        self.assertTrue(st['hasSecrets'])
        self.assertFalse(st['configured'], 'no address yet: not connected, but the secrets exist')
        first = ac.get('/api/gateway/secrets')
        self.assertGreaterEqual(len(first['officeSecret']), 32)
        self.assertTrue(first['setupCode'])
        # the setup code made before the address still moves the secrets to another PC
        other = Server('gwsecrets2').start()
        try:
            oc = make_authority(other)
            self.assertTrue(oc.post('/api/gateway/code', {'code': first['setupCode']})['hasSecrets'])
            self.assertEqual(oc.get('/api/gateway/secrets')['officeSecret'], first['officeSecret'])
        finally:
            other.cleanup()
        # making them again needs an explicit "replace" (the screen asks first), even without an address
        with self.assertRaises(ApiError) as e:
            ac.post('/api/gateway/generate', {})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(ac.get('/api/gateway/secrets')['officeSecret'], first['officeSecret'], 'a refused replace changes nothing')
        ac.post('/api/gateway/generate', {'replace': True})
        second = ac.get('/api/gateway/secrets')
        self.assertNotEqual(second['officeSecret'], first['officeSecret'])
        # saving the address later keeps the secrets and puts the address into the setup code
        ac.post('/api/gateway/save', {'url': 'https://mailbox.example.workers.dev', 'pollSeconds': 60})
        third = ac.get('/api/gateway/secrets')
        self.assertEqual(third['officeSecret'], second['officeSecret'])
        self.assertNotEqual(third['setupCode'], second['setupCode'])
        # the secrets never reach the server output or the activity log
        log = ''.join(self.S.out) + json.dumps(ac.get('/api/activity'))
        for v in (first, second):
            self.assertNotIn(v['officeSecret'], log)
            self.assertNotIn(v['setupCode'], log)


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

    def test_0_a_wrong_clock_is_not_reported_as_a_wrong_secret(self):
        from unittest import mock
        c = G.Client(self.gw.url, SECRET)
        c.status()                                              # a normal call works
        with mock.patch.object(G.time, 'time', return_value=time.time() + 14 * 60):
            with self.assertRaises(G.GatewayError) as e:
                c.status()
        self.assertIn('clock of this PC is off by 14 minutes', str(e.exception))
        self.assertNotIn('secret', str(e.exception).lower())
        with self.assertRaises(G.GatewayError) as e:
            G.Client(self.gw.url, 'not-the-secret').status()
        self.assertIn('secret does not match', str(e.exception))

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

    def test_g_the_stored_event_keeps_the_phone_time_with_its_offset_and_the_exact_receive_time(self):
        """F11: shown times are Cairo business time, but the original evidence is not thrown away."""
        t = self.new_trip()
        token = self.token_of(self.ac.post('/api/trips/link', {'id': t['id']})['url'])
        self.pull()
        e = {'uuid': str(uuid.uuid4()), 'v': 1, 'type': 'start', 'deviceId': 'device-AAAA-1', 'seq': 1, 'queued': False,
             'phoneAt': '2026-09-28T06:41:12+00:00', 'data': {'startKm': 100}}      # a phone that is set to UTC
        self.assertEqual(self.gw.driver('POST', f'/api/event/{token}', e)[0], 200)
        self.pull()
        ev = next(x for x in self.ac.get('/api/state')['tripEvents'] if x['tripId'] == t['id'])
        self.assertEqual(ev['payload']['phoneAt'], '2026-09-28T06:41:12+00:00', 'the phone text, with its offset')
        self.assertRegex(ev['payload']['recvAt'], r'Z$', 'the exact receive time')
        self.assertEqual(ev['phoneAt'], '2026-09-28T09:41:12', 'shown as Cairo time')
        self.assertEqual(self.trip(t['id'])['startAt'], '2026-09-28T09:41:12')

    def test_h_a_message_that_cannot_be_applied_stays_in_the_mailbox_and_is_counted(self):
        token = 'TkGhostAbcdefghijklmn'[:22]
        G.Client(self.gw.url, SECRET).put_cards([{'tokenHash': G.token_hash(token), 'tripId': 'no-such-trip', 'body': {}, 'cancelled': False, 'expiresAt': int(time.time()) + 3600}])
        self.event(token, 'start', startKm=1)
        res = self.pull()
        self.assertEqual(res['waiting'], 1)
        self.assertGreaterEqual(res['oldestSeconds'], 0)
        self.assertFalse(res['late'])
        self.assertEqual(len(G.Client(self.gw.url, SECRET).inbox()['events']), 1, 'it is kept, not dropped')

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


def _gw_file(server):
    return os.path.join(server.data_dir, 'gateway.json')


def _read_gw(server):
    with open(_gw_file(server), encoding='utf-8') as f:
        return json.load(f)


def _tenant_count(db):
    script = ("import {DatabaseSync} from 'node:sqlite';"
              "const db = new DatabaseSync(process.argv[1]);"
              "console.log(db.prepare('SELECT COUNT(*) n FROM tenants').get().n);")
    last = ''
    for _ in range(20):
        r = subprocess.run(['node', '--input-type=module', '-e', script, db], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip())
        last = (r.stderr or r.stdout)[-300:]
        time.sleep(0.15)
    raise AssertionError('could not read the mailbox database: ' + last)


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class TenantClientTest(unittest.TestCase):
    """The office client sends its tenant. Install A cannot read install B, and the old secret still works."""

    @classmethod
    def setUpClass(cls):
        cls.db = os.path.join(tempfile.mkdtemp(prefix='gw-tenants-'), 'box.sqlite')
        cls.gw = GatewayProcess(db=cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.gw.stop()

    def test_two_registers_cannot_see_each_other_and_the_legacy_path_still_works(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a, b = G.Secrets(os.path.join(d, 'a.json')), G.Secrets(os.path.join(d, 'b.json'))
            self.assertTrue(a.auto_register(self.gw.url))
            self.assertTrue(b.auto_register(self.gw.url))
            self.assertNotEqual(a.data['tenantId'], b.data['tenantId'])
            self.assertNotEqual(a.data['officeSecret'], b.data['officeSecret'])
            self.assertEqual(os.stat(a.path).st_mode & 0o777, 0o600)
            ca = G.Client(self.gw.url, a.data['officeSecret'], tenant=a.data['tenantId'])
            cb = G.Client(self.gw.url, b.data['officeSecret'], tenant=b.data['tenantId'])
            token = 'Tk_officeAofficeAofficeA'
            ca.put_cards([{'tokenHash': G.token_hash(token), 'tripId': 'trip-a', 'body': {'no': 'A'}, 'expiresAt': int(time.time()) + 3600}])
            e = {'uuid': str(uuid.uuid4()), 'v': 1, 'type': 'start', 'deviceId': 'device-AAAA-1', 'seq': 1, 'phoneAt': datetime.now(timezone.utc).isoformat(), 'data': {'startKm': 10}}
            self.assertEqual(self.gw.driver('POST', f'/api/event/{token}', e)[0], 200)
            self.assertEqual(len(ca.inbox()['events']), 1)
            self.assertEqual(cb.inbox()['events'], [])
            self.assertEqual(cb.inbox()['photos'], [])
            self.assertEqual(G.Client(self.gw.url, SECRET).inbox()['events'], [])
            legacy = G.Client(self.gw.url, SECRET)
            legacy.put_cards([{'tokenHash': G.token_hash('Tk_legacylegacylegacy1'), 'tripId': 'trip-old', 'body': {}, 'expiresAt': int(time.time()) + 3600}])
            self.assertEqual(legacy.status()['cards'], 1)
            self.assertEqual(ca.status()['cards'], 1)
            dumped = open(self.db, 'rb').read()
            self.assertNotIn(a.data['officeSecret'].encode(), dumped)
            self.assertNotIn(b.data['officeSecret'].encode(), dumped)


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoConnectTest(unittest.TestCase):
    """A fresh office, the real program: register, keep old settings, skip training, share with the second PC, finish a trip."""

    @classmethod
    def setUpClass(cls):
        cls.db = os.path.join(tempfile.mkdtemp(prefix='gw-auto-'), 'box.sqlite')
        cls.gw = GatewayProcess(db=cls.db)
        cls.S = Server('auto', extra_cfg={'sign_in': False, 'gateway_url': cls.gw.url}).start()
        cls.c = cls.S.client()
        wait_until(lambda: cls.c.get('/api/gateway').get('configured'), 30, what='automatic mailbox')

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()
        cls.gw.stop()

    def test_a_fresh_install_registers_and_the_secret_is_not_in_the_log_or_the_state(self):
        gw = _read_gw(self.S)
        self.assertEqual(len(gw['tenantId']), 32)
        self.assertTrue(gw['auto'])
        self.assertGreaterEqual(len(gw['officeSecret']), 32)
        self.assertEqual(os.stat(_gw_file(self.S)).st_mode & 0o777, 0o600)
        st = self.c.get('/api/gateway')
        self.assertTrue(st['auto'] and st['configured'])
        self.assertNotIn('officeSecret', st)
        state = json.dumps(self.c.get('/api/state'))
        log = ''.join(self.S.out)
        try:
            log += open(os.path.join(self.S.data_dir, 'logs', 'server.log'), encoding='utf-8').read()
        except OSError:
            pass
        for secret in (gw['officeSecret'], gw['linkSecret'], gw['tenantId'], gw['installId']):
            self.assertNotIn(secret, state)
            self.assertNotIn(secret, log)
        self.assertNotIn(gw['officeSecret'], json.dumps(self.c.get('/api/activity')))

    def test_b_driver_start_photo_and_end_finish_the_trip(self):
        c = self.c
        c.post('/api/commit', {'label': 'lists', 'ops': [
            put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car'),
            put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True, type='Sedan'),
            put('drivers', 'd1', name='Driver One', active=True, mobile='01012345678'),
            put('people', 'p1', name='Sara Adel', isRequester=True, isPassenger=True)]})
        t = c.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'destination': 'Factory'})
        link = c.post('/api/trips/link', {'id': t['id'], 'sent': True})
        token = link['url'].rsplit('/t/', 1)[1]
        c.post('/api/gateway/pull')
        self.assertEqual(self.gw.driver('GET', f'/api/card/{token}')[0], 200)

        def event(typ, **data):
            e = {'uuid': str(uuid.uuid4()), 'v': 1, 'type': typ, 'deviceId': 'device-AAAA-1', 'seq': 1,
                 'phoneAt': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'), 'data': data}
            self.assertEqual(self.gw.driver('POST', f'/api/event/{token}', e)[0], 200, typ)
            return e

        e1 = event('start', startKm=45000)
        photo = jpeg()
        pid = str(uuid.uuid4())
        self.assertEqual(self.gw.driver('PUT', f'/api/photo/{token}/{pid}', photo, {'X-Kind': 'start_odo', 'X-Sha256': hashlib.sha256(photo).hexdigest(), 'X-Event': e1['uuid']})[0], 200)
        event('end', endKm=45120, routeText='Factory - Capital - Factory')
        res = c.post('/api/gateway/pull')
        self.assertIsNone(res['lastError'])
        row = next(x for x in c.get('/api/state')['trips'] if x['id'] == t['id'])
        self.assertEqual((row['status'], row['startKm'], row['endKm'], row['locked']), ('finished', 45000, 45120, True))
        self.assertTrue(any(p['kind'] == 'start_odo' and p['tripId'] == t['id'] for p in c.get('/api/state')['tripPhotos']))


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoOfflineThenOnlineTest(unittest.TestCase):
    def test_it_waits_and_then_connects(self):
        port = free_port()
        S = Server('off', extra_cfg={'sign_in': False, 'gateway_url': f'http://127.0.0.1:{port}'}).start()
        gw = None
        try:
            time.sleep(1.2)
            self.assertFalse(S.client().get('/api/gateway')['configured'])
            offline = S.client().get('/api/gateway')
            self.assertIn('internet', (offline.get('lastError') or '').lower())
            self.assertEqual(offline.get('lastErrorKey'), 'err.mailboxLater')
            gw = GatewayProcess(port=port)
            wait_until(lambda: S.client().get('/api/gateway').get('configured'), 30, what='mailbox after the internet returns')
            self.assertTrue(_read_gw(S)['auto'])
        finally:
            S.cleanup()
            if gw:
                gw.stop()


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoLegacyUntouchedTest(unittest.TestCase):
    def test_an_existing_gateway_file_is_not_rewritten(self):
        gw = GatewayProcess()
        S = Server('legacy', extra_cfg={'sign_in': False, 'gateway_url': gw.url})
        os.makedirs(S.data_dir, exist_ok=True)
        original = {'url': 'https://custom.example.workers.dev', 'officeSecret': 'legacy-office-secret-0123456789abcd',
                    'linkSecret': 'legacy-link-secret-0123456789abcdef', 'pollSeconds': 45}
        with open(_gw_file(S), 'w', encoding='utf-8') as f:
            json.dump(original, f)
        try:
            S.start()
            time.sleep(2)
            self.assertEqual(_read_gw(S), original)
            self.assertFalse(S.client().get('/api/gateway')['auto'])
        finally:
            S.cleanup()
            gw.stop()


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoTrainingSkipTest(unittest.TestCase):
    def test_training_does_not_register_or_push(self):
        db = os.path.join(tempfile.mkdtemp(prefix='gw-train-'), 'box.sqlite')
        gw = GatewayProcess(db=db)
        S = Server('train', extra_cfg={'sign_in': False, 'training': True, 'gateway_url': gw.url}).start()
        try:
            self.assertTrue(S.client().get('/api/auth/status')['me']['training'])
            self.assertTrue(S.client().get('/api/state')['trips'], 'sample trips are loaded')
            time.sleep(2)
            self.assertFalse(os.path.exists(_gw_file(S)))
            self.assertFalse(S.client().get('/api/gateway')['configured'])
            self.assertEqual(_tenant_count(db), 0)
            self.assertNotIn('Mailbox connected', ''.join(S.out))
        finally:
            S.cleanup()
            gw.stop()


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoLanShareTest(unittest.TestCase):
    def test_the_paired_pc_receives_the_same_mailbox_and_does_not_register_another(self):
        from harness import pair, ADMIN
        db = os.path.join(tempfile.mkdtemp(prefix='gw-lan-'), 'box.sqlite')
        gw = GatewayProcess(db=db)
        main = Server('mainpc', extra_cfg={'sign_in': True, 'gateway_url': gw.url}).start()
        other = Server('otherpc', extra_cfg={'sign_in': True, 'gateway_url': gw.url}).start()
        try:
            ac = make_authority(main)
            wait_until(lambda: ac.get('/api/gateway').get('configured'), 30, what='main PC mailbox')
            mc = pair(ac, main, other, name='Second PC')
            mc.login(*ADMIN)
            wait_until(lambda: _read_gw(other).get('tenantId') == _read_gw(main)['tenantId'], 30, what='mailbox on the second PC')
            self.assertEqual(_read_gw(other)['officeSecret'], _read_gw(main)['officeSecret'])
            self.assertEqual(_read_gw(other)['linkSecret'], _read_gw(main)['linkSecret'])
            self.assertEqual(_tenant_count(db), 1)
            secret, link = _read_gw(main)['officeSecret'], _read_gw(main)['linkSecret']
            for S in (main, other):
                blob = ''
                for fn in os.listdir(os.path.join(S.data_dir, 'logs')):
                    with open(os.path.join(S.data_dir, 'logs', fn), encoding='utf-8', errors='replace') as f:
                        blob += f.read()
                self.assertNotIn(secret, blob)
                self.assertNotIn(link, blob)
        finally:
            other.cleanup()
            main.cleanup()
            gw.stop()


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoReplayTest(unittest.TestCase):
    """A lost registration answer must not open a second mailbox, and the install id never lands in the database."""

    def test_retry_keeps_the_same_mailbox_and_a_received_pc_does_not_open_another(self):
        db = os.path.join(tempfile.mkdtemp(prefix='gw-replay-'), 'box.sqlite')
        gw = GatewayProcess(db=db)
        try:
            with tempfile.TemporaryDirectory() as d:
                s = G.Secrets(os.path.join(d, 'gw.json'))
                self.assertTrue(s.auto_register(gw.url))
                tid, sec, iid = s.data['tenantId'], s.data['officeSecret'], s.data['installId']
                s.data = {'installId': iid}
                s.save()
                self.assertTrue(s.blank())
                self.assertTrue(s.auto_register(gw.url))
                self.assertEqual(s.data['tenantId'], tid)
                self.assertEqual(s.data['officeSecret'], sec)
                self.assertEqual(_tenant_count(db), 1)
                raw = open(db, 'rb').read()
                self.assertNotIn(sec.encode(), raw)
                self.assertNotIn(iid.encode(), raw)
                self.assertNotIn(gw.master.encode(), raw)
                kept = s.data['officeSecret']
                s.data.pop('installId')
                s.save()
                self.assertFalse(s.reopen_auto(gw.url))
                self.assertEqual(s.data['officeSecret'], kept)
                self.assertNotIn('installId', s.data)
        finally:
            gw.stop()


@unittest.skipUnless(node_ok(), 'node with node:sqlite is needed')
class AutoReopenTest(unittest.TestCase):
    """After the idle cleanup removes the mailbox, the PC that opened it connects again and the driver link still works."""

    def test_a_removed_mailbox_reconnects_without_changing_the_link(self):
        db = os.path.join(tempfile.mkdtemp(prefix='gw-reopen-'), 'box.sqlite')
        gw = GatewayProcess(db=db)
        S = Server('reopen', extra_cfg={'sign_in': False, 'gateway_url': gw.url}).start()
        try:
            c = S.client()
            wait_until(lambda: c.get('/api/gateway').get('configured'), 30, what='mailbox before the cleanup')
            c.post('/api/commit', {'label': 'lists', 'ops': [
                put('tripCategories', 'cat1', name='Manager car', exportSheet='All Car'),
                put('vehicles', 'v1', plate='ط و ي 6829', plateKey='طوي6829', active=True, type='Sedan'),
                put('drivers', 'd1', name='Driver One', active=True, mobile='01012345678'),
                put('people', 'p1', name='Sara Adel', isRequester=True, isPassenger=True)]})
            t = c.post('/api/trips/new', {'categoryId': 'cat1', 'vehicleId': 'v1', 'driverId': 'd1', 'requesterId': 'p1', 'destination': 'Factory'})
            link = c.post('/api/trips/link', {'id': t['id'], 'sent': True})
            token = link['url'].rsplit('/t/', 1)[1]
            c.post('/api/gateway/pull')
            self.assertEqual(gw.driver('GET', f'/api/card/{token}')[0], 200)
            saved = _read_gw(S)
            self._sql(db, 'DELETE FROM tenants')
            res = c.post('/api/gateway/pull')
            self.assertIsNone(res.get('lastError'))
            now = _read_gw(S)
            self.assertEqual(now['linkSecret'], saved['linkSecret'])
            self.assertEqual(now['installId'], saved['installId'])
            self.assertNotEqual(now['tenantId'], saved['tenantId'])
            self.assertNotEqual(now['officeSecret'], saved['officeSecret'])
            self.assertEqual(_tenant_count(db), 1)
            self.assertEqual(gw.driver('GET', f'/api/card/{token}')[0], 200)
            raw = open(db, 'rb').read()
            self.assertNotIn(now['officeSecret'].encode(), raw)
            self.assertNotIn(now['installId'].encode(), raw)
            self.assertNotIn(gw.master.encode(), raw)
        finally:
            S.cleanup()
            gw.stop()

    @staticmethod
    def _sql(db, sql):
        script = ("import {DatabaseSync} from 'node:sqlite';"
                  "const db = new DatabaseSync(process.argv[1]);"
                  "db.exec(process.argv[2]);")
        last = ''
        for _ in range(20):
            r = subprocess.run(['node', '--input-type=module', '-e', script, db, sql], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return
            last = (r.stderr or r.stdout)[-300:]
            time.sleep(0.15)
        raise AssertionError('could not update the mailbox database: ' + last)


if __name__ == '__main__':
    unittest.main()


class BatchCompatibilityTest(unittest.TestCase):
    def test_ack_splits_uuids_for_the_deployed_worker(self):
        from unittest.mock import Mock
        client = G.Client('http://127.0.0.1:1', 'synthetic')
        client.call = Mock(return_value={'ok': True})
        events = [str(uuid.UUID(int=i + 1, version=4)) for i in range(200)]
        photos = [str(uuid.UUID(int=i + 1001, version=4)) for i in range(100)]
        client.ack(events, photos)
        sent_e, sent_p = [], []
        for args in client.call.call_args_list:
            body = args.args[2]
            self.assertLessEqual(len(body['events']), 80)
            self.assertLessEqual(len(body['photos']), 80)
            sent_e.extend(body['events'])
            sent_p.extend(body['photos'])
        self.assertEqual(sent_e, events)
        self.assertEqual(sent_p, photos)

    def test_partial_card_upload_keeps_successful_batches(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        today = G.domain.business_now().date().isoformat()
        trips = [{'id': str(i), 'date': today, 'linkHash': hashlib.sha256(str(i).encode()).hexdigest(),
                  'linkExpiry': '2099-01-01T00:00:00Z'} for i in range(90)]
        store = Mock()
        store.gateway_state.return_value = {'trips': trips, 'version': 1}
        store.version.return_value = 1
        journal = Mock()
        journal.meta.return_value = None
        sync = G.GatewaySync(store, journal, 'test', SimpleNamespace(configured=True, url='http://127.0.0.1:1', data={}), Mock())
        cl = Mock()
        cl.put_cards.side_effect = [None, G.GatewayError('offline')]
        sync.client = lambda: cl
        with self.assertRaises(G.GatewayError):
            sync.push_cards()
        successful = cl.put_cards.call_args_list[0].args[0]
        self.assertLessEqual(len(successful), 40, 'works within old worker D1 query/parameter limits')
        self.assertEqual(set(sync.pushed), {c['tokenHash'] for c in successful})
        cl.put_cards.reset_mock(side_effect=True)
        sync.push_cards()
        resent = [c['tokenHash'] for args in cl.put_cards.call_args_list for c in args.args[0]]
        self.assertFalse(set(resent) & set(sync.pushed.keys() & {c['tokenHash'] for c in successful}))


class CardSnapshotTest(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        from system import System
        self.tmp = tempfile.TemporaryDirectory(prefix='to-card-snapshot-')
        self.addCleanup(self.tmp.cleanup)
        self.system = System(self.tmp.name, {}, os.path.join(self.tmp.name, 'uploads'),
                             os.path.join(self.tmp.name, 'backup'), log=lambda *a: None)
        self.addCleanup(self.system.close)
        self.store = self.system.store
        self.secrets = G.Secrets(os.path.join(self.tmp.name, 'synthetic.json'))
        self.secrets.data = {'url': 'http://127.0.0.1:1', 'officeSecret': 'synthetic', 'linkSecret': 'synthetic'}
        self.sync = G.GatewaySync(self.store, self.system.journal, self.system.node.id, self.secrets, Mock())
        self.client = Mock()
        self.sync.client = lambda: self.client
        self.hash = hashlib.sha256(b'synthetic-card').hexdigest()
        self.store.commit('bench', 'local', 'fixtures', [
            put('vehicles', 'v', plate='BENCH', active=True),
            put('people', 'requester', name='Requester'),
            put('people', 'pax', name='Passenger'),
            put('trips', 'current', no='CURRENT', date=G.domain.business_now().date().isoformat(),
                status='sent', vehicleId='v', requesterId='requester', linkHash=self.hash,
                linkExpiry='2099-01-01T00:00:00Z', stops=['A', 'B'], locked=False),
            put('trips', 'historic', no='HISTORIC', date='2000-01-01', linkHash='a' * 64),
            put('tripPassengers', 'pax1', tripId='current', personId='pax'),
            put('tripPassengers', 'pax2', tripId='current', freeText='Visitor'),
            put('tripPassengers', 'pax3', tripId='historic', freeText='Historic passenger'),
            put('settings', 'synthetic-setting', value={'nested': [1, True, None]})])

    def test_idle_round_does_not_load_rows_and_lookup_edit_updates_card(self):
        from unittest.mock import patch
        with patch.object(self.store, 'gateway_state', wraps=self.store.gateway_state) as read:
            self.sync.push_cards()
            body = self.client.put_cards.call_args.args[0][0]['body']
            self.assertEqual(body['passengers'], ['Requester', 'Passenger', 'Visitor'])
            self.assertEqual(body['stops'], ['A', 'B'])
            self.client.put_cards.reset_mock()
            self.sync.push_cards()
            self.assertEqual(read.call_count, 1)
            self.client.put_cards.assert_not_called()
            vehicle = self.store.state()['vehicles'][0]
            self.store.commit('bench', 'local', 'edit lookup', [
                {'e': 'vehicles', 'id': 'v', 'op': 'put', 'ver': vehicle['ver'], 'row': {**vehicle, 'plate': 'EDITED'}}])
            self.sync.push_cards()
            self.assertEqual(read.call_count, 2)
            self.assertEqual(self.client.put_cards.call_args.args[0][0]['body']['plate'], 'EDITED')

    def test_mailbox_change_and_phone_release_invalidate_card_receipts(self):
        self.sync.push_cards()
        self.client.put_cards.reset_mock()
        self.secrets.data['url'] = 'http://127.0.0.1:2'
        self.sync.push_cards()
        self.client.put_cards.assert_called_once()
        self.client.put_cards.reset_mock()
        self.sync.release.add(self.hash)
        self.sync.push_cards()
        self.assertTrue(self.client.put_cards.call_args.args[0][0]['releaseDevice'])
        self.assertFalse(self.sync.release)
        self.client.put_cards.reset_mock()
        self.sync.pushed.clear()  # existing settings handlers explicitly invalidate this
        self.sync.push_cards()
        self.client.put_cards.assert_called_once()

    def test_public_rows_keep_types_versions_and_scope_filtering(self):
        from store import ENTITIES
        full = self.store.state()
        for entity, (table, _, _) in ENTITIES.items():
            if entity == 'settings':
                continue
            expected = [self.store._row_js(entity, r) for r in self.store.conn.execute(
                f'SELECT * FROM {table} WHERE deleted=0 ORDER BY rowid')]
            self.assertEqual(full[entity], expected)
        self.assertEqual(full['settings']['synthetic-setting'], {'nested': [1, True, None]})
        self.assertGreater(full['settingsVer']['synthetic-setting'], 0)
        self.assertEqual(self.store.state([])['trips'], [])
        cutoff = (G.domain.business_now() - timedelta(days=45)).date().isoformat()
        cards = self.store.gateway_state(cutoff)
        self.assertEqual([t['id'] for t in cards['trips']], ['current'])
        self.assertEqual([p['id'] for p in cards['tripPassengers']], ['pax1', 'pax2'])
        self.assertNotIn('tripEvents', cards)
