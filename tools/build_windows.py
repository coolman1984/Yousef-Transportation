"""Builds the Windows installer TripOrders-Setup-<version>.exe (run on Windows; GitHub does it automatically, see
.github/workflows/build.yml and docs/BUILD_AND_RELEASE.md).

Steps: pack the web pages into server/_assets.py, draw the icon, compile the program into TripOrders.exe with Nuitka
(Python translated to C, no readable source files), then wrap it in the Inno Setup installer.

    python tools/build_windows.py            needs: pip install nuitka ordered-set zstandard cryptography, and Inno Setup 6
"""
import glob
import pathlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build')
sys.path.insert(0, os.path.join(ROOT, 'server'))
from version import COPYRIGHT, DEVELOPER, PRODUCT, VERSION  # noqa: E402
from release_policy import create_release_policy  # noqa: E402


def run(cmd):
    print('>', ' '.join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def iscc():
    for p in [shutil.which('iscc'), r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe', r'C:\Program Files\Inno Setup 6\ISCC.exe']:
        if p and os.path.exists(p):
            return p
    sys.exit('Inno Setup 6 (ISCC.exe) was not found.')


def compile_program(v4):
    run([sys.executable, '-m', 'nuitka', '--standalone', '--assume-yes-for-downloads', '--windows-console-mode=attach',
         '--python-flag=no_docstrings', '--lto=auto',
         f'--output-dir={BUILD}', '--output-filename=TripOrders.exe', f'--windows-icon-from-ico={os.path.join(BUILD, "triporders.ico")}',
         f'--company-name={DEVELOPER}', f'--product-name={PRODUCT}', f'--file-description={PRODUCT}', f'--file-version={v4}',
         f'--product-version={v4}', f'--copyright={COPYRIGHT}', '--include-module=nodectl', '--include-module=_assets', '--include-module=_release_policy',
         '--include-data-files=' + os.path.join('server', 'aftelemetry_events.json') + '=aftelemetry_events.json',
         '--include-data-files=' + os.path.join('server', 'afguide_ar_lexicon.json') + '=afguide_ar_lexicon.json',
         '--nofollow-import-to=tkinter,unittest,pydoc,test', os.path.join('server', 'to_main.py')])


def main():
    os.makedirs(BUILD, exist_ok=True)
    assets = os.path.join(ROOT, 'server', '_assets.py')
    policy = os.path.join(ROOT, 'server', '_release_policy.py')
    # Fail before building if the vendor has not supplied a real Ed25519 PUBLIC
    # signing key. Never use a developer/demo key for a customer release.
    channel = os.environ.get('TO_BUILD_CHANNEL', 'commercial')
    key_count = create_release_policy(policy, os.environ.get('TO_RELEASE_PUBLIC_KEYS', ''), channel=channel)
    print(f'{channel} licence enforcement: {key_count} pinned PUBLIC key(s)')
    try:
        run([sys.executable, 'tools/make_assets.py', assets])
        run([sys.executable, 'tools/make_icon.py', os.path.join(BUILD, 'triporders.ico')])
        v4 = '.'.join((VERSION.split('.') + ['0', '0', '0'])[:4])
        compile_program(v4)
    finally:
        # Generated sources contain UI assets and the release trust anchor; they
        # belong in the compiled binary, never in the source checkout.
        for path in (assets, policy):
            if os.path.exists(path):
                os.remove(path)
    dist = os.path.join(BUILD, 'to_main.dist')
    assert os.path.exists(os.path.join(dist, 'TripOrders.exe')), 'TripOrders.exe was not built'
    forbidden = {'.py', '.pyc', '.pyo', '.pdb', '.map', '.c', '.h'}
    leaks = [str(path.relative_to(dist)) for path in pathlib.Path(dist).rglob('*')
             if path.is_file() and path.suffix.lower() in forbidden]
    if leaks:
        raise RuntimeError('Customer package contains readable sources, caches or debugging symbols: ' + repr(leaks))
    # Cloud gateway DEPLOYMENT sources are operator-only materials, not required
    # for the office runtime. They must never be bundled in the customer installer.
    run(['node', os.path.join('gateway', 'build.js')])
    gw = os.path.join(ROOT, 'dist', 'operator-only-gateway')
    os.makedirs(gw, exist_ok=True)
    for src in ('gateway/dist/trip-orders-gateway.js', 'gateway/dist/schema.sql', 'docs/GATEWAY_SETUP.md'):
        shutil.copy(os.path.join(ROOT, src), gw)
    assert not os.path.exists(os.path.join(dist, 'gateway')), 'Gateway deployment files leaked into customer installer'
    run([iscc(), f'/DAppVersion={VERSION}', f'/DAppPublisher={DEVELOPER}', f'/DAppCopyright={COPYRIGHT}', os.path.join('installer', 'trip-orders.iss')])
    if channel == 'ci-test':
        with open(os.path.join(ROOT, 'dist', 'CI-TEST-BUILD-NOT-FOR-CUSTOMERS.txt'), 'w', encoding='utf-8') as f:
            f.write('TEST ONLY. Ephemeral signing keys. Never sell or publish this installer.\\n')
    print('Done:', glob.glob(os.path.join(ROOT, 'dist', f'TripOrders-Setup-{VERSION}.exe')))


if __name__ == '__main__':
    main()
