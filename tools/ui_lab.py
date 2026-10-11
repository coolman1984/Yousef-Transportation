"""Release-candidate check of the pages: speed on a slow CPU, smoothness, overflow and accessibility (axe) in Arabic, against the factory
budgets (Apps-Factory RULES.md, PERF-01, A11Y-01, UX-08, UX-09). Starts a throw-away copy of the program with realistic data, runs the
factory probe and writes docs/ui-lab/REPORT.md with screenshots.

    python tools/ui_lab.py [--lang ar|en] [--out docs/ui-lab]      needs: Node 22, Chromium (set CHROMIUM=...), and an Apps-Factory checkout next to this repository (APPS_FACTORY=...) and network for the first `npm ci`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from harness import ADMIN, Server  # noqa: E402

LAB_USER = 'labadmin'


def seed(client):
    ops = [{'e': 'tripCategories', 'id': f'c{i}', 'op': 'put', 'row': {'name': n, 'exportSheet': n, 'ratePerKm': 10 + i, 'vendor': 'Vendor'}} for i, n in enumerate(['Manager car', 'SUV rent', 'Bus'])]
    ops += [{'e': 'vehicles', 'id': f'v{i}', 'op': 'put', 'row': {'plate': f'ABC {1000 + i}', 'plateKey': f'abc{1000 + i}', 'active': True, 'categoryId': 'c0'}} for i in range(25)]
    ops += [{'e': 'drivers', 'id': f'd{i}', 'op': 'put', 'row': {'name': f'Driver {i}', 'active': True}} for i in range(25)]
    ops += [{'e': 'people', 'id': f'p{i}', 'op': 'put', 'row': {'name': f'Person {i}', 'isRequester': True, 'isPassenger': True, 'active': True}} for i in range(60)]
    client.post('/api/commit', {'label': 'lab lists', 'ops': ops})
    for i in range(120):
        client.post('/api/trips/new', {'categoryId': f'c{i % 3}', 'vehicleId': f'v{i % 25}', 'driverId': f'd{i % 25}', 'requesterId': f'p{i % 60}', 'destination': f'Factory {i % 9}'})


def main(argv):
    out = os.path.join(ROOT, 'docs', 'ui-lab')
    for i, a in enumerate(argv):
        if a == '--out':
            out = os.path.abspath(argv[i + 1])
    factory = os.path.abspath(os.environ.get('APPS_FACTORY', os.path.join(ROOT, '..', 'Apps-Factory')))
    # the factory checkout stays untouched: the probe is copied next to its pinned packages in a work folder and installed there
    lab = os.environ.get('UI_LAB_DIR') or os.path.join(tempfile.gettempdir(), 'to-ui-lab')
    if not os.path.isfile(os.path.join(lab, 'probe.mjs')):
        shutil.copytree(os.path.join(factory, 'tools', 'ui-lab'), lab, ignore=shutil.ignore_patterns('node_modules', 'report*'))
    if not os.path.isdir(os.path.join(lab, 'node_modules')):
        subprocess.check_call(['npm', 'ci'], cwd=lab)
    S = Server('uilab').start()
    try:
        c = S.client()
        c.post('/api/auth/setup', {'username': LAB_USER, 'full_name': 'Lab Admin', 'password': ADMIN[1]})
        p = c.get('/api/consent/prompt?lang=en')
        c.post('/api/consent/decide', {'decision': 'decline', 'text_id': p['text_id'], 'lang': p['lang'], 'scope': 'install'})
        seed(c)
        cfg = json.load(open(os.path.join(ROOT, 'ui-lab.config.json'), encoding='utf-8'))
        cfg['base'] = S.base
        cfg['budgets'] = os.path.join(factory, 'factory', 'ui-budgets.json')
        for step in cfg['login']['steps']:
            if step[1] == '#password':
                step[2] = ADMIN[1]
        if '--lang' in argv and argv[argv.index('--lang') + 1] == 'en':
            cfg['init_storage']['to.prefs'] = json.dumps({'lang': 'en', 'welcomed': True})
        path = os.path.join(tempfile.mkdtemp(prefix='to-uilab-'), 'ui-lab.config.json')
        json.dump(cfg, open(path, 'w'))
        r = subprocess.run(['node', 'probe.mjs', '--config', path, '--out', out], cwd=lab)
        return r.returncode
    finally:
        S.cleanup()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
