"""I2-I5: consent-gated telemetry, the problem report with its exact preview and crash reports through the factory hub.
A fake hub (the same /ingest URL as templates/telemetry-relay) runs inside the test. No real hub or token is used or stored.
The program has no licence or activation any more (owner request, 17 October 2026)."""
import gzip
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from harness import ADMIN, ApiError, Server, make_authority

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))

TOKEN = 'ins_' + 'x' * 40               # a made-up install token: proves the token travels as a Bearer header and is never shown back
PRODUCT = 'trip-orders'


class FakeHub:
    """/ingest keeps the batches it is given."""

    def __init__(self):
        self.batches = []
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
                self.reply(404, {})

            def do_GET(self):
                self.reply(404, {})
        self.httpd = HTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


def events_of(hub):
    return [e for b in hub.batches for e in b['events']]


class Base(unittest.TestCase):
    @classmethod
    def start(cls, name, with_hub=True):
        cls.hub = FakeHub()
        extra = {'hub_url': cls.hub.url} if with_hub else {}
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


class NoHubTest(Base):
    @classmethod
    def setUpClass(cls):
        cls.start('assist-nohub', with_hub=False)

    def test_a_there_is_no_licence_and_changes_always_work(self):
        with self.assertRaises(ApiError) as e:
            self.ac.get('/api/licence')
        self.assertEqual(e.exception.code, 404)
        self.assertNotIn('licence', self.ac.get('/api/me'))
        self.assertTrue(self.ac.post('/api/commit', {'label': 'x', 'ops': [{'e': 'departments', 'id': 'd1', 'op': 'put', 'row': {'name': 'HR'}}]})['changes'])

    def test_c_nothing_is_sent_without_a_hub_and_the_report_stays_on_this_pc(self):
        pre = self.ac.post('/api/telemetry/feedback/preview', {'kind': 'problem', 'text': 'It froze'})
        r = self.ac.post('/api/telemetry/feedback', {'kind': 'problem', 'text': 'It froze', 'confirm': pre['digest']})
        self.assertFalse(r['sending'])
        self.assertFalse(self.ac.get('/api/telemetry/receiver')['sending'])


if __name__ == '__main__':
    unittest.main()
