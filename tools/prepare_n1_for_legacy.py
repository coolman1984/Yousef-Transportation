"""Prepare the N-1 installer for the customer-release legacy journey (CI only).

Always downloads the published TripOrders-Setup-*.exe from PREVIOUS_TAG (gh release download).
Prints ``N1_SETUP_EXE=<path>`` on stdout for the workflow step to assign in-process (not GITHUB_ENV).
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


def main():
    temp = os.environ.get('RUNNER_TEMP')
    tag = os.environ.get('PREVIOUS_TAG', '').strip()
    if not temp:
        raise SystemExit('CI-only script; requires GitHub runner (RUNNER_TEMP)')
    if not tag:
        raise SystemExit('PREVIOUS_TAG is required')

    setup = _download_release(tag, Path(temp) / 'previous-release')
    print(f'Downloaded N-1 installer {setup.name} from {tag}')
    print(f'N1_SETUP_EXE={setup}')


if __name__ == '__main__':
    main()
