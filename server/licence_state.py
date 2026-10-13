"""Tamper-evident licence clock state kept outside assist.db.

The authentication key lives in the user profile, not in the office data directory.
Resetting assist.db or install_id cannot forge clock state without also changing the
profile secret file. That HMAC is tamper evidence against edits confined to assist.db
or trips data — not a boundary against the same Windows user account running arbitrary
code on this PC (the profile key is readable by that user). Windows DPAPI protection
is the intended long-term hardening for sold builds.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

import atrest

STATE_VERSION = 1
STATE_FILE = 'licence-clock.v1'
AUTH_FILE = 'licence-state-auth'
MIGRATION_MARKER = 'licence-clock-migrated.v1'

_io_lock = threading.RLock()


def _profile_dir():
    return atrest._profile_dir()


def _auth_key():
    directory = _profile_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, AUTH_FILE)
    for _ in range(5):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            break
        else:
            try:
                os.write(fd, secrets.token_bytes(32))
            finally:
                os.close(fd)
            break
    data = b''
    for _ in range(5):
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            data = b''
        if len(data) == 32:
            break
        time.sleep(0.05)
    if len(data) != 32:
        raise RuntimeError('licence state authentication file is damaged: ' + path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


def _state_path():
    return os.path.join(_profile_dir(), STATE_FILE)


def _migration_marker_path():
    return os.path.join(_profile_dir(), MIGRATION_MARKER)


def migration_marker_exists():
    return os.path.exists(_migration_marker_path())


def mark_migration_done():
    path = _migration_marker_path()
    atrest._write_0600(path, b'migrated\n')


def _seal(record):
    payload = json.dumps(record, sort_keys=True, separators=(',', ':')).encode('utf-8')
    mac = hmac.new(_auth_key(), payload, hashlib.sha256).hexdigest()
    return payload + b'\n' + mac.encode('ascii')


def _open(blob, bind_tag):
    if not blob:
        return None
    if isinstance(blob, str):
        blob = blob.encode('utf-8')
    if b'\n' not in blob:
        return None
    payload, mac = blob.rsplit(b'\n', 1)
    expected = hmac.new(_auth_key(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac.decode('ascii'), expected):
        return None
    try:
        record = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(record, dict) or record.get('v') != STATE_VERSION:
        return None
    if record.get('bind') != bind_tag:
        return None
    return record


def read(bind_tag):
    """Return ('ok', record), ('missing', None), or ('corrupt', None)."""
    path = _state_path()
    if not os.path.exists(path):
        return 'missing', None
    try:
        with open(path, 'rb') as f:
            record = _open(f.read(), bind_tag)
    except OSError:
        return 'corrupt', None
    if record is None:
        return 'corrupt', None
    return 'ok', record


def load(bind_tag):
    status, record = read(bind_tag)
    if status == 'ok':
        return record
    return None


def is_fail_closed(bind_tag):
    status, record = read(bind_tag)
    return status == 'ok' and bool(record.get('fail_closed'))


def seal_fail_closed(bind_tag, reason='state_corrupt'):
    with _io_lock:
        status, record = read(bind_tag)
        if status == 'ok' and record.get('fail_closed'):
            return record
        record = empty_record()
        record['fail_closed'] = True
        record['fail_closed_reason'] = str(reason or 'state_corrupt')
        record['trial_latch'] = True
        save(record, bind_tag)
        return record


def save(record, bind_tag):
    record = dict(record)
    record['v'] = STATE_VERSION
    record['bind'] = bind_tag
    path = _state_path()
    atrest._write_0600(path, _seal(record))


def mutate(bind_tag, updater, create=False):
    """Load, apply updater(record), save — serialized against concurrent writers."""
    with _io_lock:
        status, record = read(bind_tag)
        if status == 'ok' and record.get('fail_closed'):
            return None
        if status == 'corrupt':
            return None
        if status == 'missing':
            if not create:
                return None
            record = empty_record()
        record = updater(dict(record))
        if record is None:
            return None
        save(record, bind_tag)
        return record


def empty_record():
    return {'max_seen': None, 'hub_calendar_max': None, 'trial_latch': False, 'fail_closed': False}
