"""At-rest encryption for Trip Orders databases and backup archives.

Off unless TRIPORDERS_ENCRYPT=1. With the variable unset, every function that
opens a database is ordinary sqlite3 and nothing is written to disk here.

When it is on:
  * sqlcipher3 is required. If it cannot be imported, or if
    TRIPORDERS_ENCRYPT_BACKEND=file, the program refuses to start. There is no
    whole-file fallback and no plaintext work file.
  * Each live database (trips, auth, journal, assist, telemetry) is SQLCipher 4
    with a raw 32-byte key (PRAGMA key = "x'...'"), AES-256-CBC and HMAC-SHA512
    per page. PBKDF2 is not used.
  * Backup database files are ChaCha20-Poly1305 archives: a random 12-byte nonce
    and a header that is authenticated as additional data. The header carries the
    wrapped data key, never the raw key.
  * The raw key is random per data directory. It is stored only as
    data/atrest.key, sealed with a per-user secret in the profile directory
    (mode 0600). That file is a Linux stand-in for Windows DPAPI user scope, not
    DPAPI itself: any process of this user can read the stand-in secret.

The raw key is never written, logged, or put in source.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
import threading
import time

MAGIC_AEAD = b'TOAEAD1'          # backup archives (ChaCha20-Poly1305, not a live database)
MAGIC_KEY = b'TODPK1'            # wrapped data key (dpapi stand-in)
AAD_KEY = b'triporders-db-key-v1'
KEY_NAME = 'atrest.key'
_O_BINARY = getattr(os, 'O_BINARY', 0)
_LOCK = threading.RLock()
_MASTER = None
_DATA_KEYS = {}
_DRIVER = None
_DRIVER_TRIED = False


def enabled():
    return os.environ.get('TRIPORDERS_ENCRYPT') == '1'


def _sqlcipher():
    global _DRIVER, _DRIVER_TRIED
    if _DRIVER_TRIED:
        return _DRIVER
    _DRIVER_TRIED = True
    try:
        import sqlcipher3
        _DRIVER = sqlcipher3
    except ImportError:
        _DRIVER = None
    return _DRIVER


def backend():
    """'off' or 'sqlcipher'.

    With TRIPORDERS_ENCRYPT=1, a missing sqlcipher3 module or
    TRIPORDERS_ENCRYPT_BACKEND=file raises RuntimeError before any database
    file is created. There is no whole-file fallback and no plaintext work file.
    """
    if not enabled():
        return 'off'
    forced = os.environ.get('TRIPORDERS_ENCRYPT_BACKEND', '').strip().lower()
    if forced == 'file':
        raise RuntimeError(
            'TRIPORDERS_ENCRYPT_BACKEND=file is not supported. '
            'The program will not start and will not write a plaintext work file. '
            'Install sqlcipher3 and leave TRIPORDERS_ENCRYPT_BACKEND unset, or set it to sqlcipher.'
        )
    driver = _sqlcipher()
    if driver is None:
        if forced == 'sqlcipher':
            raise RuntimeError(
                'TRIPORDERS_ENCRYPT_BACKEND=sqlcipher but the sqlcipher3 module is not installed. '
                'TRIPORDERS_ENCRYPT=1 requires sqlcipher3. '
                'The program will not start and will not write a plaintext database. '
                'Install it with: pip install sqlcipher3-binary'
            )
        raise RuntimeError(
            'TRIPORDERS_ENCRYPT=1 requires the sqlcipher3 module, which is not installed. '
            'The program will not start and will not write a plaintext database. '
            'Install it with: pip install sqlcipher3-binary'
        )
    return 'sqlcipher'


def _aead():
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    return ChaCha20Poly1305


def _profile_dir():
    directory = os.environ.get('TRIPORDERS_DPAPI_DIR')
    if not directory:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
        directory = os.path.join(base, 'triporders')
    return directory


def master_secret():
    """32 bytes that stand in for a Windows DPAPI user-scope wrapping key."""
    global _MASTER
    if _MASTER is not None:
        return _MASTER
    with _LOCK:
        if _MASTER is not None:
            return _MASTER
        directory = _profile_dir()
        os.makedirs(directory, mode=0o700, exist_ok=True)
        path = os.path.join(directory, 'dpapi-standin')
        for _ in range(5):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_BINARY, 0o600)
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
            raise RuntimeError('DPAPI stand-in file is damaged: ' + path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _MASTER = data
        return _MASTER


def _write_0600(path, blob):
    tmp = path + '.tmp-' + secrets.token_hex(4)
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_BINARY, 0o600)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _wrap_key(data_key):
    nonce = secrets.token_bytes(12)
    ct = _aead()(master_secret()).encrypt(nonce, data_key, AAD_KEY)
    return MAGIC_KEY + nonce + ct


def unwrap_key_blob(blob):
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < len(MAGIC_KEY) + 12 + 16 or not bytes(blob).startswith(MAGIC_KEY):
        raise sqlite3.DatabaseError('wrapped data key is damaged')
    blob = bytes(blob)
    nonce = blob[len(MAGIC_KEY):len(MAGIC_KEY) + 12]
    ct = blob[len(MAGIC_KEY) + 12:]
    try:
        return _aead()(master_secret()).decrypt(nonce, ct, AAD_KEY)
    except Exception:
        raise sqlite3.DatabaseError('cannot unwrap the data key with the DPAPI stand-in on this user') from None


def _key_path(data_dir):
    return os.path.join(os.path.abspath(data_dir), KEY_NAME)


def data_key(data_dir):
    """Raw 32-byte key for this data directory. Created on first use and cached."""
    data_dir = os.path.abspath(data_dir)
    with _LOCK:
        found = _DATA_KEYS.get(data_dir)
        if found is not None:
            return found
        path = _key_path(data_dir)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                key = unwrap_key_blob(f.read())
        else:
            os.makedirs(data_dir, exist_ok=True)
            key = secrets.token_bytes(32)
            _write_0600(path, _wrap_key(key))
        if len(key) != 32:
            raise sqlite3.DatabaseError('data key must be 32 bytes')
        _DATA_KEYS[data_dir] = key
        return key


def adopt_wrapped(data_dir, blob):
    """Use the directory's key if it already has one, otherwise install this wrapped key."""
    data_dir = os.path.abspath(data_dir)
    path = _key_path(data_dir)
    with _LOCK:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                key = unwrap_key_blob(f.read())
            _DATA_KEYS[data_dir] = key
            return key
        os.makedirs(data_dir, exist_ok=True)
        _write_0600(path, bytes(blob))
        key = unwrap_key_blob(blob)
        _DATA_KEYS[data_dir] = key
        return key


def _uri_fs(uri):
    q = uri.find('?')
    if q >= 0:
        uri = uri[:q]
    body = uri[len('file:'):]
    if body.startswith('//'):
        slash = body.find('/', 2)
        return '' if slash < 0 else body[slash:]
    return body


def _is_memory(path):
    if path in (':memory:', ''):
        return True
    if isinstance(path, str) and path.startswith('file:'):
        return _uri_fs(path) in (':memory:', '')
    return False


def _fs_of(path):
    if isinstance(path, str) and path.startswith('file:'):
        return _uri_fs(path)
    return path


def is_aead(path):
    try:
        with open(path, 'rb') as f:
            return f.read(len(MAGIC_AEAD)) == MAGIC_AEAD
    except OSError:
        return False


def is_plain_sqlite(path):
    try:
        with open(path, 'rb') as f:
            return f.read(16) == b'SQLite format 3\x00'
    except OSError:
        return False


def _split_sealed(blob):
    if len(blob) < len(MAGIC_AEAD) + 12 + 4 or not blob.startswith(MAGIC_AEAD):
        raise sqlite3.DatabaseError('not an encrypted backup')
    nonce = blob[len(MAGIC_AEAD):len(MAGIC_AEAD) + 12]
    start = len(MAGIC_AEAD) + 12
    meta_len = int.from_bytes(blob[start:start + 4], 'big')
    if meta_len > 1_000_000 or start + 4 + meta_len > len(blob):
        raise sqlite3.DatabaseError('encrypted backup header is damaged')
    meta = blob[start + 4:start + 4 + meta_len]
    ct = blob[start + 4 + meta_len:]
    return nonce, meta, ct


def key_from_sealed(path):
    """Raw key recorded in an archive header (wrapped). Does not trust the file body."""
    info = _read_header(path)
    try:
        return unwrap_key_blob(bytes.fromhex(info['wrappedKey']))
    except ValueError:
        raise sqlite3.DatabaseError('encrypted backup header is damaged') from None


def _read_header(path):
    with open(path, 'rb') as f:
        magic = f.read(len(MAGIC_AEAD))
        if magic != MAGIC_AEAD:
            raise sqlite3.DatabaseError('not an encrypted backup')
        nonce = f.read(12)
        raw_len = f.read(4)
        if len(nonce) != 12 or len(raw_len) != 4:
            raise sqlite3.DatabaseError('encrypted backup header is damaged')
        meta_len = int.from_bytes(raw_len, 'big')
        if meta_len > 1_000_000:
            raise sqlite3.DatabaseError('encrypted backup header is damaged')
        meta = f.read(meta_len)
        if len(meta) != meta_len:
            raise sqlite3.DatabaseError('encrypted backup header is damaged')
    try:
        info = json.loads(meta.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError):
        raise sqlite3.DatabaseError('encrypted backup header is damaged') from None
    if not isinstance(info, dict) or not isinstance(info.get('wrappedKey'), str):
        raise sqlite3.DatabaseError('encrypted backup header is damaged')
    info['_meta_bytes'] = meta
    info['_nonce'] = nonce
    return info


def unseal_bytes(path):
    """Plaintext SQLite bytes from an archive. Raises sqlite3.DatabaseError on a bad tag."""
    with open(path, 'rb') as f:
        blob = f.read()
    nonce, meta, ct = _split_sealed(blob)
    try:
        info = json.loads(meta.decode('utf-8'))
        key = unwrap_key_blob(bytes.fromhex(info['wrappedKey']))
    except (UnicodeError, json.JSONDecodeError, ValueError, KeyError):
        raise sqlite3.DatabaseError('encrypted backup header is damaged') from None
    try:
        plain = _aead()(key).decrypt(nonce, ct, meta)
    except Exception:
        raise sqlite3.DatabaseError('authentication failed') from None
    return plain


def _unseal_to_temp(path):
    plain = unseal_bytes(path)
    fd, tmp = tempfile.mkstemp(prefix='to-unseal-', suffix='.db')
    try:
        os.write(fd, plain)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    return tmp


def seal_sqlite_file(path, data_dir, meta):
    """Replace a plaintext SQLite file with an authenticated archive. The raw key is not stored in it."""
    key = data_key(data_dir)
    with open(_key_path(data_dir), 'rb') as f:
        wrapped = f.read()
    header = {
        'v': 1,
        'alg': 'chacha20poly1305',
        'part': str((meta or {}).get('part') or ''),
        'name': str((meta or {}).get('name') or os.path.basename(path)),
        'kind': str((meta or {}).get('kind') or ''),
        'wrappedKey': wrapped.hex(),
    }
    aad = json.dumps(header, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    nonce = secrets.token_bytes(12)
    with open(path, 'rb') as f:
        plain = f.read()
    ct = _aead()(key).encrypt(nonce, plain, aad)
    out = MAGIC_AEAD + nonce + len(aad).to_bytes(4, 'big') + aad + ct
    tmp = path + '.seal'
    try:
        with open(tmp, 'wb') as f:
            f.write(out)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def manifest_mac(manifest, key):
    """HMAC-SHA256 over the manifest. The mac field itself is not covered."""
    data = json.loads(json.dumps(manifest))
    at = data.get('atrest')
    if isinstance(at, dict):
        at = dict(at)
        at.pop('mac', None)
        if at:
            data['atrest'] = at
        else:
            data.pop('atrest', None)
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hmac.new(key, b'triporders-manifest-v1\n' + raw, hashlib.sha256).hexdigest()


def manifest_mac_ok(manifest, key):
    got = ((manifest.get('atrest') or {}).get('mac')) or ''
    if not isinstance(got, str) or len(got) != 64:
        return False
    return hmac.compare_digest(got, manifest_mac(manifest, key))


class CompatRow:
    """Enough of sqlite3.Row for the stores: index, name, keys(), and dict(row)."""

    def __init__(self, cursor, values):
        self._keys = [d[0] for d in cursor.description]
        self._values = tuple(values)
        self._map = dict(zip(self._keys, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        try:
            return self._map[key]
        except KeyError:
            raise IndexError(key) from None

    def keys(self):
        return list(self._keys)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def _row_from_cursor(cursor, values):
    return CompatRow(cursor, values)


def _raise_sqlite(exc):
    if isinstance(exc, sqlite3.Error):
        raise exc
    driver = _sqlcipher()
    if driver is None:
        raise exc
    mapping = (
        (driver.IntegrityError, sqlite3.IntegrityError),
        (driver.OperationalError, sqlite3.OperationalError),
        (driver.ProgrammingError, sqlite3.ProgrammingError),
        (driver.NotSupportedError, sqlite3.NotSupportedError),
        (driver.DataError, sqlite3.DataError),
        (driver.InternalError, sqlite3.InternalError),
        (driver.DatabaseError, sqlite3.DatabaseError),
        (driver.InterfaceError, sqlite3.InterfaceError),
        (driver.Error, sqlite3.Error),
    )
    for src, dst in mapping:
        if isinstance(exc, src):
            raise dst(str(exc)) from None
    raise exc


def unwrap(conn):
    return getattr(conn, '_raw', conn)


def _is_sqlcipher_conn(raw):
    return type(raw).__module__.split('.')[0] == 'sqlcipher3'


class Conn:
    """Thin proxy. SQLCipher errors are re-raised as sqlite3 errors so existing handlers still match."""

    def __init__(self, raw, translate=False):
        object.__setattr__(self, '_raw', raw)
        object.__setattr__(self, '_translate', translate)
        object.__setattr__(self, '_closed', False)
        object.__setattr__(self, '_row_public', None)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
            return
        if name == 'row_factory' and self._translate:
            object.__setattr__(self, '_row_public', value)
            self._raw.row_factory = None if value is None else (_row_from_cursor if value is sqlite3.Row else value)
            return
        setattr(self._raw, name, value)

    def __getattr__(self, name):
        if name == 'row_factory' and self._row_public is not None:
            return self._row_public
        return getattr(self._raw, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _reraise(self, exc):
        if self._translate:
            _raise_sqlite(exc)
        raise exc

    def execute(self, *args, **kwargs):
        try:
            return self._raw.execute(*args, **kwargs)
        except Exception as e:
            self._reraise(e)

    def executemany(self, *args, **kwargs):
        try:
            return self._raw.executemany(*args, **kwargs)
        except Exception as e:
            self._reraise(e)

    def executescript(self, *args, **kwargs):
        try:
            return self._raw.executescript(*args, **kwargs)
        except Exception as e:
            self._reraise(e)

    def cursor(self, *args, **kwargs):
        try:
            return self._raw.cursor(*args, **kwargs)
        except Exception as e:
            self._reraise(e)

    def commit(self):
        try:
            return self._raw.commit()
        except Exception as e:
            self._reraise(e)

    def rollback(self):
        try:
            return self._raw.rollback()
        except Exception as e:
            self._reraise(e)

    def backup(self, target, *args, **kwargs):
        try:
            return self._raw.backup(unwrap(target), *args, **kwargs)
        except Exception as e:
            self._reraise(e)

    def close(self):
        if self._closed:
            return
        object.__setattr__(self, '_closed', True)
        try:
            self._raw.close()
        except Exception as e:
            self._reraise(e)


def _apply_key(raw, key):
    hexkey = key.hex()
    try:
        raw.execute("PRAGMA key = \"x'" + hexkey + "'\"")
        raw.execute('SELECT count(*) FROM sqlite_master').fetchone()
    except Exception as e:
        if hexkey in str(e):
            raise sqlite3.DatabaseError('database key was rejected') from None
        _raise_sqlite(e)


def _raw_sqlcipher(path, key, kwargs=None, uri=False):
    driver = _sqlcipher()
    if driver is None:
        raise RuntimeError('sqlcipher3 is not installed')
    kw = dict(kwargs or {})
    if uri:
        kw['uri'] = True
    raw = driver.connect(path, **kw)
    try:
        _apply_key(raw, key)
    except Exception:
        raw.close()
        raise
    return raw


def _db_file(raw):
    row = raw.execute('PRAGMA database_list').fetchone()
    if row is None or not row[2]:
        raise sqlite3.DatabaseError('database has no file path')
    return row[2]


def _snapshot_sqlcipher(raw, path):
    src = _db_file(raw)
    key = data_key(os.path.dirname(os.path.abspath(src)))
    tmp = path + '.cipher'
    dst = None
    try:
        dst = _raw_sqlcipher(tmp, key)
        raw.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
        if os.path.exists(path):
            os.remove(path)
        dst.execute('ATTACH DATABASE ? AS plainout KEY \'\'', (path,))
        try:
            dst.execute("SELECT sqlcipher_export('plainout')").fetchone()
        finally:
            dst.execute('DETACH DATABASE plainout')
    finally:
        if dst is not None:
            dst.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(tmp + suffix)
            except OSError:
                pass
    c = sqlite3.connect(path)
    try:
        c.execute('PRAGMA journal_mode=DELETE')
    finally:
        c.close()
    for suffix in ('-wal', '-shm'):
        try:
            os.remove(path + suffix)
        except OSError:
            pass


def snapshot_plain(conn, path):
    """Consistent plaintext SQLite file at `path`. Callers seal it when encryption is on."""
    raw = unwrap(conn)
    if enabled() and _is_sqlcipher_conn(raw):
        _snapshot_sqlcipher(raw, path)
        return
    target = sqlite3.connect(path)
    try:
        raw.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')
    finally:
        target.close()


def _materialize_sqlcipher(fs):
    """Turn an AEAD archive that was copied into the data folder into a SQLCipher database."""
    plain = unseal_bytes(fs)
    info = _read_header(fs)
    try:
        wrapped = bytes.fromhex(info['wrappedKey'])
    except ValueError:
        raise sqlite3.DatabaseError('encrypted backup header is damaged') from None
    data_dir = os.path.dirname(os.path.abspath(fs))
    key = adopt_wrapped(data_dir, wrapped)
    fd, plain_path = tempfile.mkstemp(prefix='to-mat-', suffix='.db')
    try:
        os.write(fd, plain)
    finally:
        os.close(fd)
    try:
        os.chmod(plain_path, 0o600)
    except OSError:
        pass
    enc_path = fs + '.encnew'
    raw = None
    try:
        raw = _raw_sqlcipher(enc_path, key)
        raw.execute('ATTACH DATABASE ? AS src KEY \'\'', (plain_path,))
        try:
            raw.execute("SELECT sqlcipher_export('main', 'src')").fetchone()
        finally:
            raw.execute('DETACH DATABASE src')
        raw.execute('PRAGMA journal_mode=DELETE')
        raw.close()
        raw = None
        os.replace(enc_path, fs)
    finally:
        if raw is not None:
            raw.close()
        for base in (plain_path, enc_path):
            for suffix in ('', '-wal', '-shm'):
                try:
                    os.remove(base + suffix)
                except OSError:
                    pass


def _open_sqlcipher(connect_path, fs, kwargs, uri=False):
    data_dir = os.path.dirname(os.path.abspath(fs))
    os.makedirs(data_dir, exist_ok=True)
    key = data_key(data_dir)
    raw = _raw_sqlcipher(connect_path, key, kwargs, uri=uri)
    return Conn(raw, translate=True)


def connect(path, **kwargs):
    """sqlite3.connect when encryption is off. SQLCipher when it is on.

    Refuses, before creating any file, when encryption is on and sqlcipher3 is
    missing or TRIPORDERS_ENCRYPT_BACKEND=file.
    """
    if not enabled() or _is_memory(path):
        return sqlite3.connect(path, **kwargs)
    uri = isinstance(path, str) and path.startswith('file:')
    fs = _fs_of(path)
    if not fs or fs == ':memory:':
        return sqlite3.connect(path, **kwargs)
    backend()
    fs = os.path.abspath(fs)
    if os.path.exists(fs) and is_aead(fs):
        _materialize_sqlcipher(fs)
    if os.path.exists(fs) and is_plain_sqlite(fs):
        raise sqlite3.DatabaseError('This database is not encrypted. TRIPORDERS_ENCRYPT=1 will not open a plaintext database.')
    return _open_sqlcipher(path if uri else fs, fs, kwargs, uri=uri)


def open_reader(path):
    """(connection, cleanup) for a live database or a backup archive. Does not rewrite the file."""
    uri = isinstance(path, str) and path.startswith('file:')
    if not enabled():
        c = sqlite3.connect(path, uri=uri)
        return c, c.close
    fs = _fs_of(path)
    if fs and os.path.exists(fs) and is_aead(fs):
        tmp = _unseal_to_temp(fs)
        c = sqlite3.connect('file:%s?mode=ro' % tmp, uri=True)

        def cleanup(c=c, tmp=tmp):
            try:
                c.close()
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        return c, cleanup
    if not fs or not os.path.exists(fs) or is_plain_sqlite(fs):
        c = sqlite3.connect(path, uri=uri)
        return c, c.close
    backend()
    c = _open_sqlcipher(path if uri else fs, os.path.abspath(fs), {}, uri=uri)
    return c, c.close
