"""Backups for the SQLite database and the uploaded files.

  * A consistent copy of the database is taken with SQLite's online backup API
    and verified with an integrity check before it is kept.
  * Uploaded photos/documents are never changed or deleted by the app, so they
    are mirrored incrementally (only new files are copied).
  * Every backup is also copied to each "extra_backup_dirs" folder from
    config.json (e.g. a network drive) when that folder is reachable.
  * The user accounts (auth.db) are copied next to each backup as auth_<time>.db.
    A restore never touches them, so it cannot bring back a deleted user or an
    old password.
  * The change journal (journal.db: the history of every PC, the logs) is copied
    next to each backup as journal_<time>.db, for disaster recovery only.
  * Only automatic backups are pruned (oldest first); manual, pre-import,
    pre-restore and pre-upgrade backups are kept forever.
  * A backup is made by one request at a time and never overwrites another (a taken name moves on by a second). Every file is
    written under a temporary name, checked (integrity check, size, SHA-256), and only then renamed; the manifest
    (to_<time>_<kind>.json: sizes, checksums, the history watermark) goes in before the data file, which makes the set visible. A run
    that fails leaves nothing behind and the last good set untouched; the failure is shown to the administrator.
  * What a set contains: business data, user accounts, the change history and the photos. It does NOT contain the secret keys of
    this PC (data/node) or the mailbox secrets (gateway.json) - a plain copy of those on a USB drive would be a key leak.

Restoring never rolls anything back: the differences between the current data and
the backup are saved as one new "restore" change (Store.restore_from). History,
logs and user accounts stay; the other PCs receive the restored data; changes that
another PC made at the same time and this PC had not received yet are kept.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta

from version import VERSION

AUTO_KINDS = ('auto', 'startup')
DRIVE_REMOTE = 4  # Windows GetDriveTypeW: a mapped network drive


def _drive_type(root):
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(root)


def network_folder(path, drive_type=None):
    """True for a network folder: \\\\server\\share or a mapped network drive such as Z:. Backups contain the password
    hashes and the history, so they are only copied to disks of this PC (USB drive, second disk)."""
    p = str(path or '')
    if p.startswith(('\\\\', '//')):
        return True
    if len(p) >= 2 and p[1] == ':' and (drive_type or os.name == 'nt'):
        try:
            return (drive_type or _drive_type)(p[0].upper() + ':\\') == DRIVE_REMOTE
        except (OSError, AttributeError, ValueError):
            return False
    return False
NAME_RE = re.compile(r'^to_\d{8}_\d{6}_[a-z-]+\.db$')


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def _integrity_of(path):
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        return c.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        c.close()


def verify_set(folder, name):
    """{'ok', 'legacy', 'problems'} for the set `name` in `folder` (the 'db' folder of a backup): it is complete and every file is the
    one that was written (sizes and SHA-256 from the manifest). A set from before manifests (legacy) is checked by SQLite's integrity check only."""
    if not NAME_RE.match(name or ''):
        return {'ok': False, 'legacy': False, 'problems': ['unknown backup']}
    mpath = os.path.join(folder, name[:-3] + '.json')
    problems = []
    if not os.path.exists(os.path.join(folder, name)):
        return {'ok': False, 'legacy': False, 'problems': ['data: file not found']}
    manifest = None
    if os.path.exists(mpath):
        try:
            with open(mpath, encoding='utf-8') as f:
                manifest = json.load(f)
            manifest['files']['data']
        except (OSError, ValueError, KeyError, TypeError):
            problems.append('manifest: damaged')
            manifest = None
    if manifest:
        for part, info in manifest['files'].items():
            p = os.path.join(folder, str(info.get('name')))
            if not os.path.exists(p):
                problems.append(f'{part}: file not found')
            elif os.path.getsize(p) != info.get('size'):
                problems.append(f'{part}: size differs from the manifest')
            elif _sha_file(p) != info.get('sha256'):
                problems.append(f'{part}: checksum differs from the manifest')
    try:
        result = _integrity_of(os.path.join(folder, name))
        if result != 'ok':
            problems.append('data: ' + result)
    except sqlite3.DatabaseError as e:
        problems.append('data: ' + str(e))
    return {'ok': not problems, 'legacy': not os.path.exists(mpath), 'problems': problems}


def sets_in(folder):
    """The set names in a backup 'db' folder, newest first."""
    return sorted((n for n in os.listdir(folder) if NAME_RE.match(n)), reverse=True)


class Backups:
    def __init__(self, store, uploads_dir, backup_dir, extra_dirs=(), keep_auto=200, interval_hours=6, log=print, auth=None):
        self.store = store
        self.auth = auth
        self.journal = None
        self.uploads_dir = uploads_dir
        self.dir = backup_dir
        self.extra = [d for d in extra_dirs if d]
        self.keep_auto = keep_auto
        self.interval = max(0.25, float(interval_hours)) * 3600
        self.log = log
        self.last_error = ''
        self.last_ok = ''
        self.last_mark = None   # what the last good set contained: business data version + history watermark
        self.last_time = 0
        self._lock = threading.RLock()
        self.started = time.time()
        os.makedirs(os.path.join(self.dir, 'db'), exist_ok=True)

    # ------------------------------------------------------------ create
    def create(self, kind='manual'):
        """One backup set. Requests wait for each other; a failed run raises, keeps the last good set and sets `last_error`."""
        with self._lock:
            try:
                name = self._create(kind)
            except Exception as e:
                self.last_error = f'The last backup could not be made: {e}. Your data is safe and the previous backup is untouched.'
                self.log('Backup failed: ' + str(e))
                raise
            return name

    def _folder(self):
        return os.path.join(self.dir, 'db')

    def _free_name(self, kind):
        """to_<time>_<kind>.db that no set uses yet: a taken second moves on to the next one."""
        ts = datetime.now()
        while True:
            name = f'to_{ts:%Y%m%d_%H%M%S}_{kind}.db'
            if not any(os.path.exists(os.path.join(self._folder(), n)) for n in (name, 'auth' + name[2:], 'journal' + name[2:], name[:-3] + '.json')):
                return name
            ts += timedelta(seconds=1)

    def _check_space(self):
        need = 0
        for owner in (self.store, self.auth, self.journal):
            path = getattr(owner, 'path', None)
            for suffix in ('', '-wal'):
                try:
                    need += os.path.getsize(str(path) + suffix)
                except (OSError, TypeError):
                    pass
        free = shutil.disk_usage(self.dir).free
        if free < need * 2 + 20 * 1048576:
            raise RuntimeError(f'There is not enough free space on the disk of the backup folder (about {need * 2 // 1048576 + 20} MB are needed, '
                               f'{free // 1048576} MB are free). Free some space or choose another disk.')

    @staticmethod
    def _snapshot(conn, path):
        target = sqlite3.connect(path)
        try:
            conn.backup(target)
            target.execute('PRAGMA journal_mode=DELETE')    # a plain single file: no -wal/-shm files left next to the copy
        finally:
            target.close()

    _integrity = staticmethod(_integrity_of)
    _sha = staticmethod(_sha_file)

    def _create(self, kind):
        os.makedirs(self._folder(), exist_ok=True)
        self._check_space()
        name = self._free_name(kind)
        final = {'data': name, 'auth': 'auth' + name[2:], 'journal': 'journal' + name[2:]}
        mname = name[:-3] + '.json'
        tag = '.tmp-' + uuid.uuid4().hex[:8]
        tmp = {k: os.path.join(self._folder(), v + tag) for k, v in final.items()}
        tmp['manifest'] = os.path.join(self._folder(), mname + tag)
        placed = []
        try:
            version, vv = None, {}
            for _ in range(3):                  # a change during the copy would make data and history differ: copy again (rarely needed)
                before = self.journal.vv() if self.journal else {}
                with self.store.lock:
                    version = self.store.version()
                    self._snapshot(self.store.conn, tmp['data'])
                if self.journal:
                    with self.journal.lock:
                        self._snapshot(self.journal.conn, tmp['journal'])
                        vv = self.journal.vv()
                if not self.journal or vv == before:
                    break
            if self.auth:
                self.auth.backup_to(tmp['auth'])
            parts = [k for k in ('data', 'auth', 'journal') if os.path.exists(tmp[k])]
            files = {}
            for k in parts:                      # every part is checked before the set becomes visible
                result = self._integrity(tmp[k])
                if result != 'ok':
                    raise RuntimeError(f'The copy of the {k} failed the integrity check: {result}')
                files[k] = {'name': final[k], 'size': os.path.getsize(tmp[k]), 'sha256': self._sha(tmp[k])}
            up = self._mirror_uploads(os.path.join(self.dir, 'uploads'))
            manifest = {'format': 1, 'name': name, 'kind': kind, 'createdAt': datetime.now().isoformat(timespec='seconds'), 'app': VERSION,
                        'dataVersion': version, 'journal': {'vv': vv}, 'files': files, 'uploads': up}
            with open(tmp['manifest'], 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=1)
            # the data file is renamed LAST: a set is visible (listed, restorable) only when everything else is already in place
            for k in ('auth', 'journal', 'manifest', 'data'):
                if k not in parts and k != 'manifest':
                    continue
                dest = os.path.join(self._folder(), mname if k == 'manifest' else final[k])
                os.replace(tmp[k], dest)
                placed.append(dest)
        except BaseException:
            for p in list(tmp.values()) + placed:
                try:
                    os.remove(p)
                except OSError:
                    pass
            raise
        self.last_mark, self.last_time = {'dv': version, 'vv': vv}, time.time()
        self.last_ok = datetime.now().isoformat(timespec='seconds')

        errors = []
        if up.get('failed'):
            errors.append(f'{up["failed"]} photo file(s) could not be copied to the backup')
        for extra in self.extra:
            try:
                self._copy_set(name, final, mname, extra)
            except OSError as e:
                errors.append(f'{extra}: {e}')
        self.last_error = '; '.join(errors)
        if errors:
            self.log('Backup copy problem: ' + self.last_error)
        self._prune()
        self.log(f'Backup created: {name}')
        return name

    def _copy_set(self, name, final, mname, extra):
        """The same set in a second folder, file by file under a temporary name, the data file last."""
        folder = os.path.join(extra, 'db')
        os.makedirs(folder, exist_ok=True)
        tag = '.tmp-' + uuid.uuid4().hex[:8]
        order = [n for n in (final['auth'], final['journal'], mname, final['data']) if os.path.exists(os.path.join(self._folder(), n))]
        done = []
        try:
            for n in order:
                shutil.copy2(os.path.join(self._folder(), n), os.path.join(folder, n + tag))
                os.replace(os.path.join(folder, n + tag), os.path.join(folder, n))
                done.append(os.path.join(folder, n))
        except OSError:
            for p in [os.path.join(folder, n + tag) for n in order] + done:
                try:
                    os.remove(p)
                except OSError:
                    pass
            raise
        self._mirror_uploads(os.path.join(extra, 'uploads'))

    def _mirror_uploads(self, target):
        """Photos are never changed by the app, so only missing (or cut-short) files are copied - each one whole, under a temporary name."""
        total = copied = failed = 0
        for root, _, files in os.walk(self.uploads_dir):
            rel = os.path.relpath(root, self.uploads_dir)
            out = os.path.join(target, rel)
            for f in files:
                total += 1
                src, d = os.path.join(root, f), os.path.join(out, f)
                try:
                    if os.path.exists(d) and os.path.getsize(d) == os.path.getsize(src):
                        continue
                    os.makedirs(out, exist_ok=True)
                    part = d + '.part-' + uuid.uuid4().hex[:8]
                    try:
                        shutil.copy2(src, part)
                        os.replace(part, d)
                    except OSError:
                        try:
                            os.remove(part)
                        except OSError:
                            pass
                        raise
                    copied += 1
                except OSError:
                    failed += 1
        return {'files': total, 'copied': copied, 'failed': failed}

    def _prune(self):
        autos = [b for b in self.list() if b['kind'] in AUTO_KINDS]
        for b in autos[self.keep_auto:]:
            for n in (b['name'], 'auth' + b['name'][2:], 'journal' + b['name'][2:], b['name'][:-3] + '.json'):
                try:
                    os.remove(os.path.join(self._folder(), n))
                except OSError:
                    pass
        for n in os.listdir(self._folder()):    # temporary files of a run that was cut short (power failure), after an hour
            p = os.path.join(self._folder(), n)
            if '.tmp-' in n:
                try:
                    if time.time() - os.path.getmtime(p) > 3600:
                        os.remove(p)
                except OSError:
                    pass

    # ------------------------------------------------------------ list / restore
    def list(self):
        out = []
        folder = self._folder()
        for n in os.listdir(folder):
            if NAME_RE.match(n):
                st = os.stat(os.path.join(folder, n))
                out.append({'name': n, 'size': st.st_size, 'kind': n[:-3].split('_', 3)[3], 'legacy': not os.path.exists(os.path.join(folder, n[:-3] + '.json')),
                            'time': datetime.strptime(n[3:18], '%Y%m%d_%H%M%S').isoformat(timespec='seconds')})
        return sorted(out, key=lambda b: b['name'], reverse=True)

    def verify(self, name):
        """See verify_set: this PC's own backup folder."""
        return verify_set(self._folder(), name)

    def restore(self, name, user='', ip='', user_id=''):
        """Brings the data back to the backup by saving the differences as a new change (see module doc).
        Returns (name of the safety backup taken first, result of the restore change)."""
        if not NAME_RE.match(name or ''):
            raise ValueError('Unknown backup')
        src_path = os.path.join(self._folder(), name)
        if not os.path.exists(src_path):
            raise ValueError('Backup file not found')
        if not self.verify(name)['ok']:
            raise ValueError('That backup file is damaged - choose another one')
        safety = self.create('pre-restore')
        when = datetime.strptime(name[3:18], '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M')
        res = self.store.restore_from(src_path, user, ip, f'Restore backup of {when} ({name})', user_id)
        return safety, res

    # ------------------------------------------------------------ what changed since the last good set
    def watermark(self):
        return {'dv': self.store.version(), 'vv': self.journal.vv() if self.journal else {}}

    def changed_since_last(self):
        """True when business data OR an account (both are changes in the history) changed after the last good backup."""
        return self.last_mark is None or self.watermark() != self.last_mark

    def status(self):
        """For the Data tab: the last problem, and `stale` = data changed and no good backup for a day (or three intervals). Counted from the
        program start when there was no backup yet, so a new installation never shows a warning."""
        age = (time.time() - (self.last_time or self.started)) / 3600
        changed = self.changed_since_last()
        return {'lastOk': self.last_ok, 'lastError': self.last_error, 'ageHours': round(age, 1), 'changed': changed,
                'stale': bool(changed and age > max(24, 3 * self.interval / 3600))}

    # ------------------------------------------------------------ scheduler
    def start(self):
        def loop():
            while True:
                time.sleep(600)
                try:
                    if self.changed_since_last() and time.time() - self.last_time >= self.interval:
                        self.create('auto')
                except Exception as e:  # never let the scheduler die
                    self.last_error = str(e)
                    self.log('Automatic backup failed: ' + str(e))
        threading.Thread(target=loop, daemon=True, name='backup').start()
