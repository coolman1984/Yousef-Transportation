"""The core journey on a built (or source) program, in a real data folder, before and after an update (factory REL-03, OPS-07, DATA-05).

    python tools/journey_exe.py first <home> "C:\\Program Files\\TripOrders\\TripOrders.exe"
    (run the newer installer over the installed program)
    python tools/journey_exe.py after <home> "C:\\Program Files\\TripOrders\\TripOrders.exe"

`first`: starts the program on an empty folder, sets up the administrator, proves that changes wait for a licence and reading/backup
do not, activates a device-bound test code, adds the lists, creates a trip, takes a backup, and kills the program without warning.
`legacy` (N-1): the same without a licence, on the previous release. `after`: starts it again on the same folder, signs in, checks that the licence, the trip and the backup are still there, that the trip
is not doubled, and that the program can still create a trip. Exit code 0 = good.
The signing key is made here for this run only (needs the `cryptography` package); only its public half reaches the program.
Also works on the source:  python tools/journey_exe.py first <home> python server/app.py

Silent-install CI may read the public hub's /licence/time; an online trial request is sent only after a button press.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
ADMIN, PASSWORD = 'journey-admin', 'Quarter-pass77'


class App:
    def __init__(self, port):
        self.port, self.cookie = port, ''

    def call(self, method, path, body=None, expect=200):
        headers = {'Host': f'127.0.0.1:{self.port}', 'Content-Type': 'application/json'}
        if method == 'POST':
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        if self.cookie:
            headers['Cookie'] = self.cookie
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', json.dumps(body or {}).encode() if method == 'POST' else None, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, raw, set_cookie = r.status, r.read(), r.headers.get('Set-Cookie')
        except urllib.error.HTTPError as e:
            status, raw, set_cookie = e.code, e.read(), None
        if set_cookie:
            self.cookie = set_cookie.split(';', 1)[0]
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {'raw': raw[:80]}
        if status != expect:
            raise SystemExit(f'{method} {path} -> {status} (expected {expect}): {data}')
        return data


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start(cmd, home, env):
    port = free_port()
    with open(os.path.join(home, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump({'port': port, 'sync_port': free_port(), 'open_browser': False, 'host': '127.0.0.1', 'licence_hub_url': ''}, f)
    log = open(os.path.join(home, 'journey-output.txt'), 'a', encoding='utf-8', errors='replace')
    args = list(cmd) + (['--background'] if cmd[0].lower().endswith('.exe') else [])
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, 'TO_HOME': home, **env})
    for _ in range(120):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/auth/status', timeout=5).read()
            return proc, App(port)
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f'the program stopped early with code {proc.returncode}')
            time.sleep(0.5)
    proc.kill()
    raise SystemExit('the program did not answer in 60 seconds')


def put(entity, rid, **row):
    return {'e': entity, 'id': rid, 'op': 'put', 'row': row}


def legacy(home, cmd):
    """The same journey on the PREVIOUS release (N-1), which has no licence: administrator, lists, a trip, a backup. `after` then runs on the new one."""
    os.makedirs(home, exist_ok=True)
    proc, app = start(cmd, home, {})
    try:
        app.call('POST', '/api/auth/setup', {'username': ADMIN, 'full_name': 'Journey', 'password': PASSWORD})
        app.call('POST', '/api/commit', {'label': 'lists', 'ops': [put('tripCategories', 'jc1', name='Manager car', exportSheet='All'), put('vehicles', 'jv1', plate='JRN 123', plateKey='jrn123', active=True),
                                                                   put('drivers', 'jd1', name='Journey Driver', active=True), put('people', 'jp1', name='Journey Rider', isRequester=True, isPassenger=True)]})
        trip = app.call('POST', '/api/trips/new', {'categoryId': 'jc1', 'vehicleId': 'jv1', 'driverId': 'jd1', 'requesterId': 'jp1', 'destination': 'Journey Factory'})
        backup = app.call('POST', '/api/backups', {})['name']
        json.dump({'legacy': True, 'trip': trip['id'], 'no': trip['no'], 'backup': backup}, open(os.path.join(home, 'journey.json'), 'w'))
        print(f"OK legacy: previous release set up, trip {trip['no']}, backup {backup}")
    finally:
        proc.kill()
        proc.wait()


def first(home, cmd):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import afcodes
    key_file = os.environ.get('TO_TEST_SIGNING_KEY_FILE')
    if key_file:
        with open(key_file, 'rb') as source:
            key = serialization.load_pem_private_key(source.read(), password=None)
    else:
        key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip('=')
    os.makedirs(home, exist_ok=True)
    proc, app = start(cmd, home, {'TO_LICENCE_KEYS': public})
    try:
        assert app.call('GET', '/api/auth/status')['hasUsers'] is False, 'a new folder must ask for the first administrator'
        app.call('POST', '/api/auth/setup', {'username': ADMIN, 'full_name': 'Journey', 'password': PASSWORD})
        lists = [put('tripCategories', 'jc1', name='Manager car', exportSheet='All'), put('vehicles', 'jv1', plate='JRN 123', plateKey='jrn123', active=True),
                 put('drivers', 'jd1', name='Journey Driver', active=True), put('people', 'jp1', name='Journey Rider', isRequester=True, isPassenger=True)]
        lic = app.call('GET', '/api/licence')
        assert lic['enforced'] and not lic['full'], lic
        denied = app.call('POST', '/api/commit', {'label': 'lists', 'ops': lists}, expect=402)
        assert denied['key'] == 'err.licence', denied
        assert app.call('GET', '/api/state')['version'] is not None, 'reading must work without a licence'
        code = afcodes.issue_code(pem, 'trip-orders', 'standard', date.today(), 30, lic['device'], 3)['code']
        assert app.call('POST', '/api/licence/activate', {'code': code})['full'] is True
        app.call('POST', '/api/commit', {'label': 'lists', 'ops': lists})
        trip = app.call('POST', '/api/trips/new', {'categoryId': 'jc1', 'vehicleId': 'jv1', 'driverId': 'jd1', 'requesterId': 'jp1', 'destination': 'Journey Factory'})
        backup = app.call('POST', '/api/backups', {})['name']
        json.dump({'public': public, 'trip': trip['id'], 'no': trip['no'], 'backup': backup}, open(os.path.join(home, 'journey.json'), 'w'))
        print(f"OK first: administrator set up, licence waits then works, trip {trip['no']} created, backup {backup}")
    finally:
        proc.kill()                                   # no warning at all: the data must survive a killed program
        proc.wait()


def after(home, cmd):
    state = json.load(open(os.path.join(home, 'journey.json')))
    proc, app = start(cmd, home, {} if state.get('legacy') else {'TO_LICENCE_KEYS': state['public']})
    try:
        assert app.call('GET', '/api/auth/status')['hasUsers'] is True, 'the restart must keep the administrator'
        app.call('POST', '/api/auth/login', {'username': ADMIN, 'password': PASSWORD})
        lic = app.call('GET', '/api/licence')
        if state.get('legacy'):
            if lic['enforced']:
                # Upgrading a historical no-key install must preserve all data,
                # but must NOT silently grandfather an unlicensed customer.
                assert not lic['full'], 'commercial upgrade bypassed the licence: ' + str(lic)
                assert app.call('GET', '/api/state')['version'] is not None
                from cryptography.hazmat.primitives import serialization
                import afcodes
                with open(os.environ['TO_TEST_SIGNING_KEY_FILE'], 'rb') as source:
                    key = source.read()
                signed = afcodes.issue_code(key, 'trip-orders', 'standard', date.today(), 30, lic['device'], 3)['code']
                assert app.call('POST', '/api/licence/activate', {'code': signed})['full']
            else:
                assert lic['full'] and lic['state'] == 'contract', 'source-mode legacy compatibility: ' + str(lic)
        else:
            assert lic['full'] and lic['edition'] == 'standard', 'the licence must survive the restart/update: ' + str(lic)
        trips = [t for t in app.call('GET', '/api/state')['trips'] if t['destination'] == 'Journey Factory']
        assert len(trips) == 1 and trips[0]['id'] == state['trip'], f'the trip before the update must be there exactly once: {trips}'
        assert state['backup'] in [b['name'] for b in app.call('GET', '/api/backups')], 'the backup made before the update is missing'
        newer = app.call('POST', '/api/trips/new', {'categoryId': 'jc1', 'vehicleId': 'jv1', 'driverId': 'jd1', 'requesterId': 'jp1', 'destination': 'After the update'})
        print(f"OK after: trip {state['no']} and backup {state['backup']} kept, licence kept; created {newer['no']} after the update")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] not in ('first', 'after', 'legacy'):
        sys.exit(__doc__)
    {'first': first, 'after': after, 'legacy': legacy}[sys.argv[1]](sys.argv[2], sys.argv[3:])
