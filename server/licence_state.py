"""Tamper-evident licence clock state kept outside assist.db.

The authentication key lives only in the user profile (DPAPI stand-in), not in the
office data directory. Resetting assist.db or install_id cannot forge or erase this
protection without local-administrator access to the profile secret.
"""
import hashlib
import hmac
import json
import os
import secrets
import time

import atrest

STATE_VERSION = 1
STATE_FILE = 'licence-clock.v1'
AUTH_FILE = 'licence-state-auth'


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


def load(bind_tag):
    path = _state_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            return _open(f.read(), bind_tag)
    except OSError:
        return None


def save(record, bind_tag):
    record = dict(record)
    record['v'] = STATE_VERSION
    record['bind'] = bind_tag
    path = _state_path()
    atrest._write_0600(path, _seal(record))


def empty_record():
    return {'max_seen': None, 'hub_calendar_max': None, 'trial_latch': False}
