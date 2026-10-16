"""Prepare the N-1 installer for the customer-release legacy journey (CI only).

Published releases before v1.1.3 run in contract mode; from v1.1.3 onward they are
commercial and enforced, so the legacy journey needs a throwaway studio PUBLIC key in
the installer plus a matching ephemeral private key (see ci_signing_key.py). The
customer build under test still embeds only the real owner PUBLIC keys.

Writes to GITHUB_ENV:
  N1_SETUP_EXE — path to TripOrders-Setup-*.exe to install
  TO_TEST_SIGNING_KEY_FILE — set when an enforced N-1 fixture was built (optional)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse_tag(tag: str) -> tuple:
    m = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)', (tag or '').strip())
    if not m:
        raise SystemExit(f'bad release tag: {tag}')
    return tuple(int(x) for x in m.groups())


def _enforced_previous(tag: str) -> bool:
    return _parse_tag(tag) >= (1, 1, 3)


def _run(cmd, **kwargs):
    print('>', ' '.join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT, **kwargs)


def _generate_ci_signing(temp: Path) -> tuple[str, Path]:
    """Return (studio_public_b64, private_pem_path) without touching GITHUB_ENV."""
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    key_path = temp / 'trip-orders-ci-only-signing-key.pem'
    if key_path.exists():
        raise SystemExit('Refusing to overwrite CI signing material')
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip('=')
    return public, key_path


def _download_release(tag: str, dest: Path) -> Path:
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not repo:
        raise SystemExit('GITHUB_REPOSITORY is required to download a release')
    dest.mkdir(parents=True, exist_ok=True)
    _run(['gh', 'release', 'download', tag, '--repo', repo,
          '--pattern', 'TripOrders-Setup-*.exe', '--dir', str(dest)])
    matches = sorted(dest.glob('TripOrders-Setup-*.exe'))
    if not matches:
        raise SystemExit(f'no installer in release {tag}')
    return matches[0]


def _build_fixture(tag: str, commercial_keys: str, studio_public: str, temp: Path) -> Path:
    work = temp / 'n1-worktree'
    if work.exists():
        raise SystemExit(f'worktree path already exists: {work}')
    _run(['git', 'worktree', 'add', '--detach', str(work), tag])
    try:
        merged = commercial_keys.strip()
        if not merged:
            raise SystemExit('TO_COMMERCIAL_PUBLIC_KEYS is required for an enforced N-1 fixture')
        merged = f'{merged},studio:{studio_public}'
        env = {**os.environ, 'TO_RELEASE_PUBLIC_KEYS': merged, 'TO_BUILD_CHANNEL': 'commercial'}
        _run([sys.executable, 'tools/build_windows.py'], cwd=work, env=env)
        built = sorted((work / 'dist').glob('TripOrders-Setup-*.exe'))
        if not built:
            raise SystemExit(f'fixture build at {tag} produced no installer')
        out = temp / built[0].name
        out.write_bytes(built[0].read_bytes())
        return out
    finally:
        _run(['git', 'worktree', 'remove', '--force', str(work)])


def main():
    env_file = os.environ.get('GITHUB_ENV')
    temp = os.environ.get('RUNNER_TEMP')
    tag = os.environ.get('PREVIOUS_TAG', '').strip()
    commercial = os.environ.get('TO_COMMERCIAL_PUBLIC_KEYS', '').strip()
    if not env_file or not temp:
        raise SystemExit('CI-only script; requires GitHub runner')
    if not tag:
        raise SystemExit('PREVIOUS_TAG is required')

    temp_path = Path(temp)
    signing_file = None
    if _enforced_previous(tag):
        studio_public, signing_file = _generate_ci_signing(temp_path)
        setup = _build_fixture(tag, commercial, studio_public, temp_path)
        print(f'Built enforced N-1 CI fixture for {tag} (ephemeral studio PUBLIC key only in that throwaway installer)')
    else:
        setup = _download_release(tag, temp_path / 'previous-release')
        print(f'Downloaded contract-mode N-1 installer {setup.name}')

    with open(env_file, 'a', encoding='utf-8') as f:
        f.write('N1_SETUP_EXE=' + str(setup) + '\n')
        if signing_file:
            f.write('TO_TEST_SIGNING_KEY_FILE=' + str(signing_file) + '\n')


if __name__ == '__main__':
    main()
