"""Checks on an INSTALLED customer build (customer-release workflow). PUBLIC keys only, no signing key.

    python tools/customer_release_check.py upgraded <home> <TripOrders.exe> <hub_url>
    python tools/customer_release_check.py fresh <home> <TripOrders.exe>

upgraded: <home> holds data from the previous release (journey_exe.py legacy). Checks the program is a commercial build that
enforces the licence (no editing without a code), the earlier trip and backup survived, a code signed by an unknown key is
refused with 400, and the live hub's calendar day - fetched here and verified with the pinned trial-hub PUBLIC key - is the
day the program sealed (the program only seals a day whose signature verifies with a pinned key).
fresh: a new office on the installed program has its administrator, is commercial, enforced, and not licensed.
Needs TRIPORDERS_DPAPI_DIR (where the program keeps its sealed licence clock).
"""
import glob
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journey_exe  # noqa: E402

PINNED = dict(e.split(':', 1) for e in os.environ.get('TO_RELEASE_PUBLIC_KEYS', '').split(',') if ':' in e)


def commercial_unlicensed(lic):
    print('licence status:', {k: lic.get(k) for k in ('state', 'full', 'enforced', 'build_channel', 'reason', 'upgrade_grace')})
    assert lic['enforced'] is True and lic['build_channel'] == 'commercial', 'not an enforced commercial build: ' + str(lic)
    assert lic['reason'] != 'no_keys', 'no public keys pinned: ' + str(lic)
    assert lic['full'] is False, 'an office without a licence can edit: ' + str(lic)


def forged_refused(app, device):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import afcodes
    rogue = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption())
    forged = afcodes.issue_code(rogue, 'trip-orders', 'standard', date.today(), 30, device, 3)['code']
    app.call('POST', '/api/licence/activate', {'code': forged}, expect=400)
    assert app.call('GET', '/api/licence')['full'] is False, 'forged code unlocked editing'
    print('forged code refused with 400')


def hub_day(hub):
    import hub_time
    req = urllib.request.Request(hub + '/licence/time', headers={'User-Agent': 'TripOrders-release-check'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    day = hub_time.verify_hub_calendar(data, {'trial-hub': PINNED['trial-hub']})
    assert day, 'the live hub calendar does not verify with the pinned trial-hub PUBLIC key: ' + str(data)[:200]
    return day


def sealed_day(dpapi):
    for path in glob.glob(os.path.join(dpapi, '**', 'licence-clock.v1*'), recursive=True):
        m = re.search(rb'"hub_calendar_max":"(\d{4}-\d{2}-\d{2})', open(path, 'rb').read())
        if m:
            return m.group(1).decode()
    return None


def upgraded(home, exe, hub):
    state = json.load(open(os.path.join(home, 'journey.json')))
    dpapi = os.environ['TRIPORDERS_DPAPI_DIR']
    expected = hub_day(hub)
    proc, app = journey_exe.start([exe], home, {'FACTORY_LICENCE_HUB_URL': hub})
    try:
        app.call('POST', '/api/auth/login', {'username': journey_exe.ADMIN, 'password': journey_exe.PASSWORD})
        lic = app.call('GET', '/api/licence')
        commercial_unlicensed(lic)
        trips = [t for t in app.call('GET', '/api/state')['trips'] if t['destination'] == 'Journey Factory']
        assert len(trips) == 1 and trips[0]['id'] == state['trip'], f'the trip from the previous release is not there exactly once: {trips}'
        assert state['backup'] in [b['name'] for b in app.call('GET', '/api/backups')], 'the previous backup is missing'
        forged_refused(app, lic['device'])
        got = None
        for _ in range(240):            # longer than one 5-minute retry of the program's calendar check
            got = sealed_day(dpapi)
            if got:
                break
            time.sleep(2)
        later = hub_day(hub)
        assert got in (expected, later), f'the program did not seal the signed hub day (sealed {got}, hub {expected}/{later})'
        print(f'live hub day {got} verified with the pinned trial-hub key and sealed by the program')
        print('OK customer release check (upgraded)')
    finally:
        proc.terminate()
        proc.wait()


def fresh(home, exe):
    os.makedirs(home, exist_ok=True)
    proc, app = journey_exe.start([exe], home, {})
    try:
        app.call('POST', '/api/auth/setup', {'username': journey_exe.ADMIN, 'full_name': 'Fresh', 'password': journey_exe.PASSWORD})
        app.call('POST', '/api/auth/login', {'username': journey_exe.ADMIN, 'password': journey_exe.PASSWORD})
        lic = app.call('GET', '/api/licence')
        commercial_unlicensed(lic)
        forged_refused(app, lic['device'])
        print('OK customer release check (fresh)')
    finally:
        proc.terminate()
        proc.wait()


if __name__ == '__main__':
    mode = sys.argv[1]
    {'upgraded': lambda: upgraded(*sys.argv[2:5]), 'fresh': lambda: fresh(*sys.argv[2:4])}[mode]()
