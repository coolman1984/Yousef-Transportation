"""The core journey on a built (or source) program, in a real data folder, before and after an update (factory REL-03, OPS-07, DATA-05).

    python tools/journey_exe.py first <home> "C:\\Program Files\\TripOrders\\TripOrders.exe"
    (run the newer installer over the installed program)
    python tools/journey_exe.py after <home> "C:\\Program Files\\TripOrders\\TripOrders.exe"

`first`: starts the program on an empty folder (demo mode: no sign-in, the sample data is loaded), adds the lists, creates a trip,
takes a backup, and kills the program without warning. `after`: starts it again on the same folder, checks that the trip and the
backup are still there, that the trip is not doubled, and that the program can still create a trip. Exit code 0 = good.
Also works on the source:  python tools/journey_exe.py first <home> python server/app.py
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))


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
        json.dump({'port': port, 'sync_port': free_port(), 'open_browser': False, 'host': '127.0.0.1'}, f)
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


LISTS = [put('tripCategories', 'jc1', name='Journey car', exportSheet='All'), put('vehicles', 'jv1', plate='JRN 123', plateKey='jrn123', active=True),
         put('drivers', 'jd1', name='Journey Driver', active=True), put('people', 'jp1', name='Journey Rider', isRequester=True, isPassenger=True)]
TRIP = {'categoryId': 'jc1', 'vehicleId': 'jv1', 'driverId': 'jd1', 'requesterId': 'jp1'}


def first(home, cmd):
    os.makedirs(home, exist_ok=True)
    proc, app = start(cmd, home, {})
    try:
        status = app.call('GET', '/api/auth/status')
        assert status['me'] and status['me']['demo'], 'demo mode must open the program without signing in: ' + str(status)
        assert app.call('GET', '/api/state')['trips'], 'a new folder must start with the sample trips'
        app.call('POST', '/api/commit', {'label': 'lists', 'ops': LISTS})
        trip = app.call('POST', '/api/trips/new', {**TRIP, 'destination': 'Journey Factory'})
        backup = app.call('POST', '/api/backups', {})['name']
        json.dump({'trip': trip['id'], 'no': trip['no'], 'backup': backup}, open(os.path.join(home, 'journey.json'), 'w'))
        print(f"OK first: demo mode opened with sample data, trip {trip['no']} created, backup {backup}")
    finally:
        proc.kill()                                   # no warning at all: the data must survive a killed program
        proc.wait()


def after(home, cmd):
    state = json.load(open(os.path.join(home, 'journey.json')))
    proc, app = start(cmd, home, {})
    try:
        assert app.call('GET', '/api/auth/status')['me'], 'the restart must open the program without signing in'
        trips = [t for t in app.call('GET', '/api/state')['trips'] if t['destination'] == 'Journey Factory']
        assert len(trips) == 1 and trips[0]['id'] == state['trip'], f'the trip before the update must be there exactly once: {trips}'
        assert state['backup'] in [b['name'] for b in app.call('GET', '/api/backups')], 'the backup made before the update is missing'
        newer = app.call('POST', '/api/trips/new', {**TRIP, 'destination': 'After the update'})
        print(f"OK after: trip {state['no']} and backup {state['backup']} kept; created {newer['no']} after the update")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] not in ('first', 'after'):
        sys.exit(__doc__)
    {'first': first, 'after': after}[sys.argv[1]](sys.argv[2], sys.argv[3:])
