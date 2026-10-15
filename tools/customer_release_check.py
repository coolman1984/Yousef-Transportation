"""Checks on an INSTALLED customer build (customer-release workflow). PUBLIC keys only, no signing key.

    python tools/customer_release_check.py <home> <TripOrders.exe> <hub_url>

Starts the installed program on <home> (data from the previous release, made by journey_exe.py legacy), then checks:
it is a commercial build that enforces the licence, the previous trip and backup survived the update, a code signed by
an unknown key is refused, and the live hub's signed calendar day (trial-hub kid) is accepted by the pinned real key.
"""
import glob
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journey_exe  # noqa: E402


def main(home, exe, hub):
    state = json.load(open(os.path.join(home, 'journey.json')))
    dpapi = os.environ['TRIPORDERS_DPAPI_DIR']
    proc, app = journey_exe.start([exe], home, {'FACTORY_LICENCE_HUB_URL': hub})
    try:
        app.call('POST', '/api/auth/login', {'username': journey_exe.ADMIN, 'password': journey_exe.PASSWORD})
        lic = app.call('GET', '/api/licence')
        print('licence status:', {k: lic.get(k) for k in ('state', 'full', 'enforced', 'build_channel', 'reason', 'upgrade_grace')})
        assert lic['enforced'] is True and lic['build_channel'] == 'commercial', 'not a commercial build: ' + str(lic)
        assert lic['reason'] != 'no_keys', 'no public keys pinned'
        trips = [t for t in app.call('GET', '/api/state')['trips'] if t['destination'] == 'Journey Factory']
        assert len(trips) == 1 and trips[0]['id'] == state['trip'], f'the trip from 1.1.2 is not there exactly once: {trips}'
        assert state['backup'] in [b['name'] for b in app.call('GET', '/api/backups')], 'the 1.1.2 backup is missing'
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        import afcodes
        rogue = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption())
        forged = afcodes.issue_code(rogue, 'trip-orders', 'standard', date.today(), 30, lic['device'], 3)['code']
        try:
            res = app.call('POST', '/api/licence/activate', {'code': forged})
            assert not res.get('full') or res.get('state') == 'upgrade_grace', 'a code from an unknown key was accepted: ' + str(res)
        except SystemExit as e:
            print('forged code refused:', str(e)[:160])
        # the live hub signs its calendar day with the real trial-hub key; only the pinned real key accepts it
        found = None
        for _ in range(90):
            for path in glob.glob(os.path.join(dpapi, '**', 'licence-clock.v1*'), recursive=True):
                raw = open(path, 'rb').read()
                if b'"hub_calendar_max":"20' in raw:
                    found = path
            if found:
                break
            time.sleep(2)
        assert found, 'the signed calendar day from the live hub was not accepted (real trial-hub key not pinned?)'
        print('live hub signed calendar accepted by the pinned trial-hub key:', found)
        print('OK customer release check')
    finally:
        proc.terminate()
        proc.wait()


if __name__ == '__main__':
    main(*sys.argv[1:4])
