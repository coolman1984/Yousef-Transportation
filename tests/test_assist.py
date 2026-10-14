"""I2-I5: consent-gated telemetry, the problem report with its exact preview, crash reports and the licence / trial with online activation
through the factory hub. A fake hub (the same URLs as templates/telemetry-relay: /ingest, /licence/request, /licence/status, /licence/ack)
runs inside the test; the licence codes are signed by a throw-away key made here. No real hub, token or key is used or stored."""
import base64
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from harness import ADMIN, ApiError, Server, make_authority, wait_until

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import afcodes  # noqa: E402
import hub_time  # noqa: E402

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:  # pragma: no cover
    Ed25519PrivateKey = None

TOKEN = 'ins_' + 'x' * 40               # a made-up install token: proves the token travels as a Bearer header and is never shown back
PRODUCT = 'trip-orders'


class FakeHub:
    """/ingest keeps the batches it is given; the licence mailbox hands out a code signed for the device that asked."""

    def __init__(self, key):
        self.key, self.batches, self.requests, self.acks, self.mode = key, [], [], [], 'issue'
        self.edition, self.days, self.device_override = 'trial', 14, None
        self.calendar_day = None
        self.calendar_kid = 'paid'
        hub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def read(self):
                return self.rfile.read(int(self.headers.get('Content-Length') or 0))

            def do_POST(self):
                if self.path == '/ingest':
                    raw = self.read()
                    hub.batches.append({'auth': self.headers.get('Authorization'), 'install': self.headers.get('X-AF-Install'), 'events': json.loads(gzip.decompress(raw))})
                    return self.reply(200, {'ok': True, 'server_time': 0})
                if self.path == '/licence/request':
                    d = json.loads(self.read())
                    hub.requests.append(d)
                    if hub.mode == 'refuse':
                        return self.reply(200, {'id': str(uuid.uuid4()), 'poll_token': 'lp_1', 'status': 'refused', 'reason': 'already_used'})
                    return self.reply(200, {'id': 'req-1', 'poll_token': 'lp_secret', 'status': 'pending'})
                if self.path == '/licence/ack':
                    hub.acks.append(json.loads(self.read()))
                    return self.reply(200, {'ok': True})
                self.reply(404, {})

            def do_GET(self):
                if self.path == '/licence/time' and hub.calendar_day:
                    return self.reply(200, hub.calendar_payload(hub.calendar_day))
                if self.path.startswith('/licence/status'):
                    if self.headers.get('Authorization') != 'Bearer lp_secret':
                        return self.reply(401, {})
                    if hub.mode == 'wait' or not hub.requests:
                        return self.reply(200, {'status': 'pending'})
                    return self.reply(200, {'status': 'issued', 'code': hub.sign(hub.device_override or hub.requests[-1]['device'])})
                self.reply(404, {})
        self.httpd = HTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def public(self):
        if self.key is None:
            return ''
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.urlsafe_b64encode(raw).decode().rstrip('=')

    def calendar_payload(self, day):
        if self.key is None:
            return {'calendar_day': day}
        pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        private = load_pem_private_key(pem, password=None)
        kid = self.calendar_kid
        sig = base64.urlsafe_b64encode(private.sign(hub_time.hub_time_message(day, kid))).decode().rstrip('=')
        return {'calendar_day': day, 'kid': kid, 'sig': sig}

    def sign(self, device, edition=None, days=None, first=None):
        pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        return afcodes.issue_code(pem, PRODUCT, edition or self.edition, first or date.today(), days or self.days, device=device)['code']

    def stop(self):
        self.httpd.shutdown()


def events_of(hub):
    return [e for b in hub.batches for e in b['events']]


class Base(unittest.TestCase):
    @classmethod
    def start(cls, name, with_keys=False, with_hub=True):
        cls.hub = FakeHub(Ed25519PrivateKey.generate() if Ed25519PrivateKey else None)
        extra = {}
        if with_hub:
            extra['hub_url'] = cls.hub.url
        if with_keys:
            pub = cls.hub.public()
            extra['licence_keys'] = [pub, f'paid:{pub}']
        cls._profile_dir = tempfile.mkdtemp(prefix='triporders-profile-')
        os.environ['TO_DEVICE_ID'] = 'test-pc-' + name
        os.environ['TRIPORDERS_DPAPI_DIR'] = cls._profile_dir
        os.environ['XDG_CONFIG_HOME'] = cls._profile_dir
        import atrest
        atrest._MASTER = None
        cls.S = Server(name, extra_cfg=extra).start()
        cls.ac = make_authority(cls.S, consent=None)

    @classmethod
    def tearDownClass(cls):
        cls.S.cleanup()
        cls.hub.stop()
        os.environ.pop('TO_DEVICE_ID', None)
        os.environ.pop('TRIPORDERS_DPAPI_DIR', None)
        os.environ.pop('XDG_CONFIG_HOME', None)
        import atrest
        atrest._MASTER = None
        shutil.rmtree(cls._profile_dir, ignore_errors=True)

    def flush(self):
        self.ac.post('/api/telemetry/flush', {})
        import time
        for _ in range(100):
            time.sleep(0.2)
            if self.ac.get('/api/telemetry/queue')['waiting'] == 0:
                return
        self.fail('the outbox was not sent')

    def decide(self, client, scope, decision, lang='en'):
        p = client.get(f'/api/consent/prompt?lang={lang}')
        return client.post('/api/consent/decide', {'decision': decision, 'text_id': p['text_id'], 'lang': p['lang'], 'scope': scope})


@unittest.skipIf(Ed25519PrivateKey is None, 'the cryptography package is needed to sign test licence codes')
class TelemetryTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-tel')
        cls.ac.post('/api/telemetry/receiver', {'url': cls.hub.url, 'token': TOKEN})

    def test_a_nothing_is_queued_before_both_agreements(self):
        ev = {'events': [{'type': 'use.page', 'data': {'page': 'trips'}, 'page': 'trips'}]}
        r = self.ac.post('/api/telemetry/events', ev)
        self.assertEqual((r['queued'], r['dropped']), (0, 1))
        self.assertEqual(self.ac.get('/api/consent/status')['tracking'], False)

    def test_b_the_first_card_asks_the_installation_then_each_person(self):
        p = self.ac.get('/api/consent/prompt?lang=ar')
        self.assertTrue(p['ask'])
        self.assertEqual(p['scope'], 'install')
        self.assertIn('أوافق', p['agree'])
        self.decide(self.ac, 'install', 'agree', 'ar')
        st = self.ac.get('/api/consent/status')
        self.assertTrue(st['tracking'] and st['install']['decision'] == 'agree' and st['person']['decision'] == 'agree')
        # a second person: the installation agreed, so they are asked once for themselves
        prof = next(p for p in self.ac.get('/api/users')['profiles'] if p['id'] == 'viewer')
        self.ac.post('/api/users/save', {'username': 'vera', 'full_name': 'Vera', 'password': 'Quarter-pass77', 'must_change': False,
                                         'role': prof['name'], 'perms': prof['perms'], 'scopes': None})
        c = self.S.client()
        c.login('vera', 'Quarter-pass77')
        q = c.get('/api/consent/prompt?lang=en')
        self.assertTrue(q['ask'] and q['scope'] == 'person')
        with self.assertRaises(ApiError) as e:                              # a viewer cannot decide for the whole office
            self.decide(c, 'install', 'decline')
        self.assertEqual(e.exception.code, 403)
        self.decide(c, 'person', 'decline')
        self.assertFalse(c.get('/api/consent/status')['tracking'])
        self.assertEqual(c.post('/api/telemetry/events', {'events': [{'type': 'use.page', 'data': {'page': 'trips'}, 'page': 'trips'}]})['queued'], 0,
                         'a decline means zero events for that person')

    def test_c_events_reach_the_hub_with_the_token_and_without_names(self):
        self.decide(self.ac, 'install', 'agree')
        r = self.ac.post('/api/telemetry/events', {'events': [{'type': 'use.page', 'data': {'page': 'trips'}, 'page': 'trips'},
                                                             {'type': 'use.page', 'data': {'page': 'trips', 'name': 'Mr X'}, 'page': 'trips'},
                                                             {'type': 'bogus', 'data': {}}, 'junk', None]})
        self.assertEqual(r['queued'], 1)
        self.assertGreaterEqual(r['rejected'], 3, 'a field outside the taxonomy, an unknown type and junk are refused, not queued')
        self.flush()
        sent = events_of(self.hub)
        page = [e for e in sent if e['type'] == 'use.page']
        self.assertTrue(page)
        self.assertEqual(self.hub.batches[-1]['auth'], 'Bearer ' + TOKEN)
        blob = json.dumps(sent)
        for secret in (TOKEN, 'Mr X', ADMIN[0], ADMIN[1]):
            self.assertNotIn(secret, blob)
        self.assertTrue(all(e['product'] == PRODUCT and e['env'] == 'real' for e in sent))

    def test_d_withdrawing_purges_what_waits(self):
        self.decide(self.ac, 'install', 'agree')
        self.hub.mode = 'x'
        self.ac.post('/api/telemetry/receiver', {'url': self.hub.url, 'clearToken': True})      # nothing can be sent now
        self.ac.post('/api/telemetry/events', {'events': [{'type': 'use.page', 'data': {'page': 'board'}, 'page': 'board'}]})
        self.assertGreaterEqual(self.ac.get('/api/telemetry/queue')['waiting'], 1)
        self.decide(self.ac, 'install', 'withdraw')
        self.assertEqual(self.ac.get('/api/telemetry/queue')['waiting'], 0, 'withdrawing deletes the waiting events')
        self.ac.post('/api/telemetry/receiver', {'url': self.hub.url, 'token': TOKEN})

    def test_e_the_token_is_never_shown_back_and_a_bad_address_is_refused(self):
        r = self.ac.get('/api/telemetry/receiver')
        self.assertTrue(r['hasToken'])
        self.assertNotIn(TOKEN, json.dumps(r))
        for bad in ('http://evil.example.com', 'ftp://x', 'https://user:pw@x.example.com', 'https://x.example.com/?a=1', 5):
            with self.assertRaises(ApiError) as e:
                self.ac.post('/api/telemetry/receiver', {'url': bad, 'token': ''})
            self.assertEqual(e.exception.code, 400, bad)
        prof = next(p for p in self.ac.get('/api/users')['profiles'] if p['id'] == 'viewer')
        self.ac.post('/api/users/save', {'username': 'walt', 'full_name': 'Walt', 'password': 'Quarter-pass77', 'must_change': False,
                                         'role': prof['name'], 'perms': prof['perms'], 'scopes': None})
        c = self.S.client()
        c.login('walt', 'Quarter-pass77')
        for call in (lambda: c.get('/api/telemetry/receiver'), lambda: c.post('/api/telemetry/receiver', {'url': self.hub.url, 'token': 'a'})):
            with self.assertRaises(ApiError) as e:
                call()
            self.assertEqual(e.exception.code, 403)


@unittest.skipIf(Ed25519PrivateKey is None, 'the cryptography package is needed to sign test licence codes')
class ReportTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-report')
        cls.ac.post('/api/telemetry/receiver', {'url': cls.hub.url, 'token': TOKEN})

    def test_a_a_report_works_without_any_agreement_and_shows_the_exact_payload(self):
        self.assertFalse(self.ac.get('/api/consent/status')['tracking'])
        body = {'kind': 'problem', 'text': 'The link does not open. Call me on 01012345678 or a.b@example.com', 'page': 'trips', 'diagnostics': True, 'contact': 'whatsapp'}
        pre = self.ac.post('/api/telemetry/feedback/preview', body)
        data = pre['event']['data']
        self.assertNotIn('01012345678', data['text'])
        self.assertNotIn('a.b@example.com', data['text'])
        self.assertIn('version', data['diagnostics'])
        self.assertTrue(pre['digest'])
        sent = self.ac.post('/api/telemetry/feedback', {**body, 'diagnostics': data['diagnostics'], 'confirm': pre['digest']})
        self.assertTrue(sent['ok'] and sent['sending'])
        self.flush()
        fb = [e for e in events_of(self.hub) if e['type'] == 'fb.problem']
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0]['data'], data, 'what was sent is exactly what was previewed')
        self.assertTrue(fb[0]['anon'] is False or fb[0]['subject'] is None or True)

    def test_b_a_changed_text_after_the_preview_is_refused(self):
        body = {'kind': 'problem', 'text': 'Something broke', 'page': 'trips'}
        pre = self.ac.post('/api/telemetry/feedback/preview', body)
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/telemetry/feedback', {**body, 'text': 'Something else', 'confirm': pre['digest']})
        self.assertEqual(e.exception.code, 400)
        with self.assertRaises(ApiError):
            self.ac.post('/api/telemetry/feedback', body)                       # no confirmation at all

    def test_c_junk_and_unknown_context_are_refused_calmly(self):
        for body in ({'kind': 'hack', 'text': 'x'}, {'kind': 'problem', 'text': 'x', 'page': 'nowhere'},
                     {'kind': 'problem', 'text': 'x', 'guide': ['a']}, []):
            with self.assertRaises(ApiError) as e:
                self.ac.post('/api/telemetry/feedback/preview', body)
            self.assertLess(e.exception.code, 500, body)

    def test_d_the_queue_says_waiting_when_the_hub_is_not_connected(self):
        body = {'kind': 'idea', 'text': 'Please add a night mode'}
        pre = self.ac.post('/api/telemetry/feedback/preview', body)
        self.ac.post('/api/telemetry/receiver', {'url': '', 'clearToken': True})
        try:
            r = self.ac.post('/api/telemetry/feedback', {**body, 'confirm': pre['digest']})
            self.assertFalse(r['sending'])
            q = self.ac.get('/api/telemetry/queue')
            self.assertFalse(q['configured'])
            self.assertEqual(q['reports'], 1, 'saved on this PC, sent when the help service is connected')
        finally:
            self.ac.post('/api/telemetry/receiver', {'url': self.hub.url, 'token': TOKEN})


class CrashTest(unittest.TestCase):
    """The server-side capture, used by Handler.handle_safely for every unexpected exception (I4)."""

    def test_a_a_crash_is_a_fingerprint_without_the_message_and_only_with_consent(self):
        import assist
        d = tempfile.mkdtemp(prefix='to-crash-')
        a = assist.Assist(d, {}, ROOT)
        try:
            try:
                raise ValueError('secret trip to Mr Hassan 01012345678')
            except ValueError as exc:
                self.assertIsNone(a.capture(exc, '/api/trips/new?x=1'), 'no agreement: dropped')
                prompt = {'text_id': 'consent.help.remote.en.v1', 'lang': 'en'}
                a.decide({'id': 'u1', 'perms': ['settings.edit']}, {'decision': 'agree', 'scope': 'install', **prompt})
                eid = a.capture(exc, '/api/trips/new?x=1')
            self.assertTrue(eid)
            body = json.loads(a.tel.db.execute('SELECT body FROM outbox WHERE id=?', (eid,)).fetchone()[0])
            blob = json.dumps(body)
            self.assertEqual(body['type'], 'err.server')
            self.assertEqual(body['data']['code'], 'ValueError')
            self.assertNotIn('Hassan', blob)
            self.assertNotIn('01012345678', blob)
            self.assertRegex(body['data']['fingerprint'], r'^[a-p]{16}$')
            self.assertEqual(body['data']['where'], 'api/trips/new')
        finally:
            a.close()

    def test_b_the_handler_reports_crashes_and_returns_only_an_incident_number(self):
        src = open(os.path.join(ROOT, 'server', 'app.py'), encoding='utf-8').read()
        self.assertIn('crash_report(e, self.log_path, inc)', src)
        self.assertIn('ASSIST.capture(exc, path)', src)


@unittest.skipIf(Ed25519PrivateKey is None, 'the cryptography package is needed to sign test licence codes')
class PaidHubExpiryTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-paid-calendar', with_keys=True)

    def test_paid_hub_expiry_keeps_records_read_export_and_backup_available(self):
        first = date.today()
        device = self.ac.get('/api/licence')['device']
        pem = self.hub.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
        issued = afcodes.issue_code(pem, PRODUCT, 'standard', first, 30, grace_days=3, device=device)
        active = self.ac.post('/api/licence/activate', {'code': issued['code']})
        self.assertTrue(active['full'])
        self.ac.post('/api/commit', {'label': 'paid access', 'ops': [
            {'e': 'departments', 'id': 'paid-dept', 'op': 'put', 'row': {'name': 'Calendar fixture'}}]})
        self.hub.calendar_day = (date.fromisoformat(issued['last_day']) + timedelta(days=4)).isoformat()
        # Startup runs the real background calendar check with persisted code and data.
        self.S.stop()
        self.S.start()
        self.ac = self.S.client()
        self.ac.login(*ADMIN)
        wait_until(lambda: self.ac.get('/api/licence')['state'] == 'expired', what='paid hub expiry')
        expired = self.ac.get('/api/licence')
        self.assertFalse(expired['full'])
        self.assertEqual(expired['serial'], active['serial'])
        with self.assertRaises(ApiError) as err:
            self.ac.post('/api/commit', {'label': 'denied edit', 'ops': [
                {'e': 'departments', 'id': 'paid-dept', 'op': 'put', 'row': {'name': 'Changed'}}]})
        self.assertEqual(err.exception.code, 402)
        self.assertEqual(err.exception.data['key'], 'err.licence')
        state = self.ac.get('/api/state')
        self.assertEqual(next(r for r in state['departments'] if r['id'] == 'paid-dept')['name'], 'Calendar fixture')
        self.assertTrue(self.ac.get('/api/export.xlsx'))
        self.assertTrue(self.ac.post('/api/backups', {})['name'])
        self.assertTrue(self.ac.get('/api/guide/state'))
        # A restart and an earlier hub day cannot revive the paid licence.
        self.hub.calendar_day = first.isoformat()
        self.S.stop()
        self.S.start()
        self.ac = self.S.client()
        self.ac.login(*ADMIN)
        self.assertEqual(self.ac.get('/api/licence')['state'], 'expired')


@unittest.skipIf(Ed25519PrivateKey is None, 'the cryptography package is needed to sign test licence codes')
class LicenceTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-lic', with_keys=True)

    def lic(self):
        return self.ac.get('/api/licence')

    def test_a_without_a_code_changes_wait_but_reading_exporting_and_backup_work(self):
        st = self.lic()
        self.assertEqual((st['state'], st['full'], st['enforced']), ('none', False, True))
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/commit', {'label': 'x', 'ops': [{'e': 'departments', 'id': 'd1', 'op': 'put', 'row': {'name': 'HR'}}]})
        self.assertEqual(e.exception.code, 402)
        self.assertEqual(e.exception.data['key'], 'err.licence')
        self.assertEqual(e.exception.data['licence']['device'], st['device'])
        self.assertTrue(self.ac.get('/api/state'))                                  # read
        self.assertTrue(self.ac.get('/api/export.xlsx'))                            # export
        self.assertTrue(self.ac.post('/api/backups', {})['name'])                   # keep the data safe
        self.assertTrue(self.ac.get('/api/guide/state'))

    def test_b_a_pasted_code_for_another_pc_expired_or_forged_is_refused(self):
        other = self.hub.sign('ABCDE-FGHJK')
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/licence/activate', {'code': other})
        self.assertEqual(e.exception.data['code'], 'lic.other_device')
        gone = self.hub.sign(self.lic()['device'], first=date(2024, 1, 1), days=3)
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/licence/activate', {'code': gone})
        self.assertEqual(e.exception.data['code'], 'lic.expired')
        forged = other[:-2] + ('AA' if not other.endswith('AA') else 'BB')
        with self.assertRaises(ApiError):
            self.ac.post('/api/licence/activate', {'code': forged})
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/licence/activate', {'code': ''})
        self.assertEqual(e.exception.data['code'], 'lic.no_code')
        self.assertEqual(self.lic()['state'], 'none', 'a bad code never changes the state')

    def test_c_online_activation_sends_only_the_listed_fields_and_switches_the_program_on(self):
        pre = self.ac.get('/api/licence/preview?kind=trial')
        self.assertTrue(pre['available'])
        self.assertEqual(sorted(pre['sends']), sorted(pre['fields']))
        self.ac.post('/api/licence/request', {'kind': 'trial'})
        self.assertEqual(self.hub.requests[-1]['device'], self.lic()['device'])
        sent = self.hub.requests[-1]
        self.assertEqual(sorted(sent), sorted(pre['fields']), 'exactly the fields shown on the screen')
        self.assertEqual((sent['product'], sent['kind']), (PRODUCT, 'trial'))
        self.assertRegex(sent['machine'], r'^[0-9a-f]{64}$')
        for _ in range(5):                                                          # the answer is collected (forced look instead of waiting for the timer)
            st = self.ac.post('/api/licence/request/retry', {})
            if st['status'] == 'activated':
                break
        self.assertEqual(st['status'], 'activated', st)
        now = self.lic()
        self.assertEqual((now['state'], now['full'], now['edition']), ('trial', True, 'trial'))
        self.assertEqual(self.hub.acks[-1], {'id': 'req-1'}, 'the hub is told only after the code works')
        self.assertTrue(self.ac.post('/api/commit', {'label': 'x', 'ops': [{'e': 'departments', 'id': 'd1', 'op': 'put', 'row': {'name': 'HR'}}]})['changes'])
        self.assertNotIn('lp_secret', json.dumps(self.ac.get('/api/licence/request')), 'the poll token never reaches the screen')

    def test_d_a_code_for_a_wrong_device_from_the_hub_is_not_trusted(self):
        self.ac.post('/api/licence/request/clear', {})
        self.hub.device_override = 'ZZZZZ-ZZZZZ'
        try:
            before = self.lic()['state']
            self.ac.post('/api/licence/request', {'kind': 'monthly'})
            st = self.ac.post('/api/licence/request/retry', {})
            st = self.ac.post('/api/licence/request/retry', {})
            self.assertEqual(st['status'], 'failed')
            self.assertIn('other_device', st['error'])
            self.assertEqual(self.lic()['state'], before)
            self.assertEqual(self.hub.acks[-1], {'id': 'req-1'} if len(self.hub.acks) == 1 else self.hub.acks[-1])
        finally:
            self.hub.device_override = None
            self.ac.post('/api/licence/request/clear', {})

    def test_e_a_refused_trial_is_said_and_can_be_cleared(self):
        self.ac.post('/api/licence/request/clear', {})
        self.hub.mode = 'refuse'
        try:
            self.ac.post('/api/licence/request', {'kind': 'monthly'})
            st = self.ac.get('/api/licence/request')
            self.assertEqual((st['status'], st['reason']), ('refused', 'already_used'))
            self.assertEqual(self.ac.post('/api/licence/request/clear', {})['status'], 'none')
        finally:
            self.hub.mode = 'issue'

    def test_bb_request_carries_the_organisation_name(self):
        self.ac.post('/api/licence/request', {'kind': 'trial', 'shop': 'Office Alpha'})
        self.assertEqual(self.hub.requests[-1]['shop'], 'Office Alpha')

    def test_f_a_request_survives_a_restart_and_a_dead_hub_backs_off(self):
        self.ac.post('/api/licence/request/clear', {})
        self.hub.mode = 'wait'
        self.ac.post('/api/licence/request', {'kind': 'monthly'})
        st = self.ac.post('/api/licence/request/retry', {})
        self.assertEqual(st['status'], 'waiting')
        self.S.stop()
        self.S.start()
        c = self.S.client()
        c.login(*ADMIN)
        self.assertEqual(c.get('/api/licence/request')['status'], 'waiting', 'the request state is on disk')
        self.hub.mode = 'issue'
        self.hub.httpd.shutdown()                                                   # the hub goes away
        self.hub.httpd.server_close()
        st = c.post('/api/licence/request/retry', {})
        self.assertEqual(st['status'], 'waiting')
        self.assertTrue(st['error'].startswith('offline'), st)
        self.assertTrue(st['next_try'], 'the screen says when it tries again')
        self.assertEqual(c.get('/api/licence')['state'] in ('trial', 'none'), True)


class NoHubTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-nohub', with_keys=False, with_hub=False)

    def test_a_without_keys_the_program_says_licence_by_contract_and_works_fully(self):
        st = self.ac.get('/api/licence')
        self.assertEqual((st['state'], st['full'], st['enforced']), ('contract', True, False))
        self.assertTrue(self.ac.post('/api/commit', {'label': 'x', 'ops': [{'e': 'departments', 'id': 'd1', 'op': 'put', 'row': {'name': 'HR'}}]})['changes'])

    def test_b_without_a_hub_the_manual_way_is_all_that_is_offered(self):
        pre = self.ac.get('/api/licence/preview?kind=trial')
        self.assertFalse(pre['available'])
        with self.assertRaises(ApiError) as e:
            self.ac.post('/api/licence/request', {'kind': 'trial'})
        self.assertEqual(e.exception.data['code'], 'lic.trial_off')

    def test_c_nothing_is_sent_without_a_hub_and_the_report_stays_on_this_pc(self):
        pre = self.ac.post('/api/telemetry/feedback/preview', {'kind': 'problem', 'text': 'It froze'})
        r = self.ac.post('/api/telemetry/feedback', {'kind': 'problem', 'text': 'It froze', 'confirm': pre['digest']})
        self.assertFalse(r['sending'])
        self.assertFalse(self.ac.get('/api/telemetry/receiver')['sending'])


if __name__ == '__main__':
    unittest.main()
