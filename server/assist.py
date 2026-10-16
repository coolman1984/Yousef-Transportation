"""In-app guide, consent, consented telemetry, problem reports and crash reports (product glue for the three factory packages).

afguide, afconsent and aftelemetry are vendored from Apps-Factory (python scripts/vendor_*.py) and are not edited. This module keeps the
product side:
  * one small local database, data/assist.db: the consent log, each person's guide progress, this installation's id and secret, the
    help-service address and token. It is NOT part of the business data: it is not replicated to other PCs, not rolled back by a restore
    (a restore must never bring back an old agreement) and not in the backup set;
  * the outbox of events, data/telemetry.db (bounded, offline-safe);
  * nothing leaves this PC unless the installation agreed (consent) AND a help-service address and token are configured. A problem
    report the person wrote and previewed is the one thing that is allowed without tracking consent (Apps-Factory RULES.md section 2).
The address comes from the environment (FACTORY_HUB_URL) or config.json (`hub_url`); the token is typed in Settings (or TO_HUB_TOKEN) and kept
only in assist.db. Neither is in the repository.
"""
import gzip
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import afconsent
import afguide
import aftelemetry
import atrest
from version import DEVELOPER, VERSION

PRODUCT_ID = 'trip-orders'
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:\-/]{0,79}$')
_LONG = re.compile(r'\d{8,}')
ROLES = ('administrator', 'dispatcher', 'ga-approver', 'reviewer', 'finance', 'viewer')
PAGES = {'overview', 'trips', 'board', 'review', 'vehicles', 'drivers', 'people', 'places', 'reports', 'excel', 'activity', 'settings',
         'help', 'signin', 'setup'}
# confirmed actions worth a count. Ids only: never a trip number, a name or an amount.
ACTIONS = {
    '/api/trips/new': ('trip.new', 'trips'),
    '/api/trips/link': ('trip.link', 'trips'),
    '/api/trips/approve': ('trip.approve', 'trips'),
    '/api/trips/amend': ('trip.amend', 'trips'),
    '/api/trips/cancel': ('trip.cancel', 'trips'),
    '/api/excel/commit': ('excel.import', 'excel'),
    '/api/backups': ('backup.now', 'settings'),
    '/api/users/save': ('user.save', 'settings'),
}
KV_SQL = 'CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)'


def guide_role(perms):
    """The first-day course of a person: the closest of the six courses to what their permissions let them do.
    A hand-made set of permissions follows the same rule, so nobody is left without a course."""
    have = set(perms or ())
    if 'users.manage' in have:
        return 'administrator'
    if 'trips.create' in have or 'trips.send' in have:
        return 'dispatcher'
    if 'trips.approve' in have:
        return 'ga-approver'
    if 'trips.review' in have or 'trips.amend' in have:
        return 'reviewer'
    if have & {'finance.view', 'rates.manage', 'excel.export', 'reports.view'} and 'trips.edit' not in have:
        return 'finance' if have & {'finance.view', 'rates.manage', 'excel.import'} else 'viewer'
    return 'viewer'


def _machine_id(value):
    if isinstance(value, str) and _ID.fullmatch(value) and not _LONG.search(value) and '@' not in value:
        return value
    return None


def _report_fields(data):
    """Kind, text and contact must be text. A junk body (a number, a list) is a bad request, not a crash."""
    data = data if isinstance(data, dict) else {}
    kind, text, contact = data.get('kind'), data.get('text'), data.get('contact')
    return data, (kind if isinstance(kind, str) and kind else 'problem', text if isinstance(text, str) else '',
                  contact if isinstance(contact, str) and contact else 'none')


def valid_hub_url(url):
    """https only (an address on this PC may use http, for tests); no user name, no query."""
    if not isinstance(url, str) or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    try:
        p = urlsplit(url)
        port = p.port
        return bool(p.hostname and p.username is None and p.password is None and not p.fragment and not p.query
                    and (port is None or 1 <= port <= 65535)
                    and (p.scheme == 'https' or (p.scheme == 'http' and p.hostname in ('127.0.0.1', 'localhost'))))
    except ValueError:
        return False


class Assist:
    def __init__(self, data_dir, cfg, root, assets=None, started=None, extra_diagnostics=None, practice=False):
        self.data_dir = data_dir
        self.cfg = cfg
        self.started = started or time.time()
        self.extra = extra_diagnostics or (lambda: {})
        self.practice = practice
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.closed = False
        self.errors = []              # times of recent server errors (for the diagnostics count)
        self.catalogue, self.texts = self._load_guide(root, assets)
        self.db = atrest.connect(os.path.join(data_dir, 'assist.db'), check_same_thread=False, isolation_level=None)
        self.db.execute(KV_SQL)
        self.db.executescript(afconsent.SQL)
        self.db.execute(afguide.SQL)
        self._ensure_identity()
        self.consent = afconsent.Consent(self.db, on_change=self._on_consent)
        # aftelemetry is vendored and opens telemetry.db itself. Patch only for this call so the
        # module's sqlite3.connect is unchanged for the rest of the process when encryption is off,
        # and so the vendored file does not grow a product dependency.
        real_connect = sqlite3.connect
        try:
            if atrest.enabled():
                sqlite3.connect = atrest.connect
            self.tel = aftelemetry.Telemetry(os.path.join(data_dir, 'telemetry.db'), self.kv('install_id'), node='office', product=PRODUCT_ID,
                                             version=VERSION, env='practice' if practice else 'real', secret=self.kv('secret'),
                                             consent=self.consent)
        finally:
            sqlite3.connect = real_connect
        self._prune_pending()
        self.thread = None

    # ---------------------------------------------------------------- guide files
    @staticmethod
    def _load_guide(root, assets):
        """catalogue.json and <lang>.json: from the packed pages of the installed program, else from the guide/ folder."""
        def read(name):
            rel = f'guide/{name}.json'
            if assets is not None and rel in assets:
                return json.loads(assets[rel].decode('utf-8'))
            with open(os.path.join(root, 'guide', f'{name}.json'), encoding='utf-8') as f:
                return json.load(f)
        cat = read('catalogue')
        return cat, {lang: read(lang) for lang in cat.get('languages', [])}

    # ---------------------------------------------------------------- identity, receiver (local only)
    def kv(self, key, value=None, delete=False):
        with self.lock:
            if delete:
                self.db.execute('DELETE FROM kv WHERE k=?', (key,))
                return None
            if value is not None:
                self.db.execute('INSERT INTO kv(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (key, str(value)))
                return value
            row = self.db.execute('SELECT v FROM kv WHERE k=?', (key,)).fetchone()
            return row[0] if row else None

    def _ensure_identity(self):
        if not self.kv('secret') or len(self.kv('secret')) < 32:
            self.kv('secret', secrets.token_hex(32))
        if not self.kv('install_id'):
            self.kv('install_id', aftelemetry.new_identity()[0])

    def hub_url(self):
        url = (os.environ.get('FACTORY_HUB_URL') or self.cfg.get('hub_url') or self.kv('hub_url') or '').strip().rstrip('/')
        return url if valid_hub_url(url) else ''

    def licence_hub_url(self):
        env = (os.environ.get('FACTORY_LICENCE_HUB_URL') or '').strip().rstrip('/')
        if env:
            return env if valid_hub_url(env) else ''
        if 'licence_hub_url' in self.cfg:
            url = (self.cfg.get('licence_hub_url') or '').strip().rstrip('/')
            return url if valid_hub_url(url) else ''
        url = (self.kv('licence_hub_url') or '').strip().rstrip('/')
        return url if valid_hub_url(url) else ''

    def hub_token(self):
        return (os.environ.get('TO_HUB_TOKEN') or self.kv('hub_token') or '').strip()

    def receiver_public(self):
        """What Settings may see: never the token."""
        return {'url': self.hub_url(), 'urlFromEnvironment': bool(os.environ.get('FACTORY_HUB_URL') or self.cfg.get('hub_url')),
                'hasToken': bool(self.hub_token()), 'sending': bool(self._receiver()), 'installId': self.kv('install_id')}

    def save_receiver(self, data):
        """Administrator only (the route checks). The token is stored and never returned or logged."""
        if not isinstance(data, dict):
            raise ValueError('bad receiver settings')
        url, token = data.get('url', ''), data.get('token', '')
        if not isinstance(url, str) or not isinstance(token, str) or not isinstance(data.get('clearToken', False), bool):
            raise ValueError('bad receiver settings')
        url = url.strip().rstrip('/')
        if url and not valid_hub_url(url):
            raise ValueError('The help-service address must start with https://')
        if len(token) > 4096 or any(ord(ch) < 33 or ord(ch) > 126 for ch in token.strip()):
            raise ValueError('The help-service token is not valid')
        self.kv('hub_url', url) if url else self.kv('hub_url', delete=True)
        if token.strip():
            self.kv('hub_token', token.strip())
        if data.get('clearToken'):
            self.kv('hub_token', delete=True)
        return self.receiver_public()

    def _receiver(self):
        url, token = self.hub_url(), self.hub_token()
        if not url or not token or len(token) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            return None
        return url + '/ingest', token

    # ---------------------------------------------------------------- guide
    def live_states(self, user, facts):
        """Names from catalogue.states that are already true. `facts` is computed by the app from the business data."""
        states = ['signed.in']
        for key in ('setup.done', 'trip.first', 'link.sent', 'trip.approved', 'person.second', 'backup.made'):
            if facts.get(key):
                states.append(key)
        with self.lock:
            if self.consent.current('person', user['id']) is not None:
                states.append('consent.answered')
        return states

    def guide_state(self, user, facts):
        perms = set(user.get('perms') or ())
        role = guide_role(perms)

        def can(perm):
            return perm in (None, '*') or perm in perms
        with self.lock:
            record = afguide.load(self.db, user['id'])
            return {**afguide.state(self.catalogue, role, record, self.live_states(user, facts), can), 'role': role}

    def save_progress(self, user, update, facts):
        if not isinstance(update, dict):
            raise ValueError('bad update')
        for key in ('op', 'guide', 'lang'):
            if key in update and not isinstance(update[key], str):
                raise ValueError('bad update')
        with self.lock:
            record = afguide.apply(afguide.load(self.db, user['id']), update, self.catalogue)
            afguide.save(self.db, user['id'], record)
        return self.guide_state(user, facts)

    # ---------------------------------------------------------------- consent
    def _on_consent(self, scope, subject, decision):
        with self.lock:
            self.tel.on_consent_change(scope, subject, decision)

    def prompt_for(self, user, lang):
        if lang not in ('ar', 'en'):
            lang = 'ar'
        body = afconsent.prompt(lang, afconsent.vendor_name({}, DEVELOPER))
        perms = set(user.get('perms') or ())
        with self.lock:
            if self.consent.current('install') is None and 'settings.edit' in perms:
                ask, scope = True, 'install'
            elif self.consent.needs_prompt(user['id']):
                ask, scope = True, 'person'
            else:
                ask, scope = False, 'person'
        body['ask'], body['scope'] = ask, scope
        return body

    def consent_status(self, user):
        with self.lock:
            status = self.consent.status(user['id'])
        status['feedback_always_allowed'] = True
        status['receiver'] = {'configured': bool(self._receiver())}
        return status

    def decide(self, user, data):
        """Returns the new status. Raises ValueError for junk, PermissionError when the person may not decide for the installation."""
        if not isinstance(data, dict):
            raise ValueError('bad decision')
        decision, text_id, lang, scope = data.get('decision'), data.get('text_id'), data.get('lang'), data.get('scope', 'person')
        if not isinstance(scope, str) or scope not in afconsent.SCOPES or not isinstance(decision, str) or decision not in afconsent.DECISIONS:
            raise ValueError('bad scope or decision')
        if not isinstance(text_id, str) or text_id not in afconsent.TEXTS or afconsent.TEXTS[text_id]['lang'] != lang:
            raise ValueError('unknown consent text')
        if scope == 'install' and 'settings.edit' not in set(user.get('perms') or ()):
            raise PermissionError('settings.edit')
        with self.lock:
            if scope == 'install':
                self.consent.record('install', '', decision, text_id, lang, user['id'])
                if decision in ('agree', 'decline') and self.consent.current('person', user['id']) is None:
                    self.consent.record('person', user['id'], decision, text_id, lang, user['id'])
            else:
                self.consent.record('person', user['id'], decision, text_id, lang, user['id'])
        return self.consent_status(user)

    # ---------------------------------------------------------------- telemetry
    def note_action(self, user, action, page):
        role = guide_role(user.get('perms'))
        with self.lock:
            self.tel.emit('use.action', {'action': action, 'page': page}, user=user['id'], role=role, page=page)

    def note_error(self):
        t = time.time()
        with self.lock:
            self.errors = [x for x in self.errors if t - x < 3600] + [t]

    def recent_errors(self):
        t = time.time()
        return len([x for x in self.errors if t - x < 3600])

    def event(self, etype, data=None):
        """An installation-level event (backup, sync, upgrade ...): dropped by the outbox unless the installation agreed."""
        try:
            with self.lock:
                self.tel.emit(etype, data or {})
        except aftelemetry.PrivacyError:
            pass

    def browser_events(self, user, events):
        role = guide_role(user.get('perms'))
        known = {'page': PAGES, 'guide': {g['id'] for g in self.catalogue['guides']},
                 'problem': {p['id'] for p in self.catalogue['problems']}, 'lang': {'ar', 'en'},
                 'kind': {s['k'] for g in self.catalogue['guides'] for s in g['steps']},
                 'action': {a for a, _ in ACTIONS.values()}, 'perm': None,
                 'shortcut': None, 'error': None, 'code': None}
        files = {'promise', 'inline'}
        safe, rejected = [], 0
        for event in (events if isinstance(events, list) else [])[:200]:
            if not isinstance(event, dict) or not isinstance(event.get('type'), str) or not isinstance(event.get('data', {}), dict):
                rejected += 1
                continue
            page, data = event.get('page'), event.get('data', {})
            valid = page is None or (isinstance(page, str) and page in PAGES)
            for key, value in data.items():
                if key in known and known[key] is not None:
                    valid = valid and isinstance(value, str) and value in known[key]
                elif key == 'where':
                    file, sep, line = value.rpartition(':') if isinstance(value, str) else ('', '', '')
                    valid = valid and bool(sep and re.fullmatch(r'[A-Za-z0-9_.\-]{1,60}\.js|promise|inline', file) and re.fullmatch(r'\d{1,7}', line))
                elif key == 'fingerprint':
                    valid = valid and isinstance(value, str) and bool(re.fullmatch(r'[a-p]{8,32}', value))
            if not valid:
                rejected += 1
                continue
            safe.append(event)
        with self.lock:
            result = self.tel.from_browser(safe, user['id'], role=role)
        result['rejected'] += rejected
        return result

    def capture(self, exc, where):
        """A server crash: type, fingerprint and the product's own module:function only - never the message, the path of a person's
        request or any value. Consent still applies inside the outbox (installation level)."""
        raw = (where or '').split('?', 1)[0]
        raw = raw.lstrip('/') if raw in ACTIONS or raw in ('/api/guide/state', '/api/guide/progress', '/api/consent/decide',
                                                           '/api/telemetry/events', '/api/telemetry/feedback') else 'server'
        with self.lock:
            return self.tel.capture(exc, where=raw[:80], root=os.path.dirname(os.path.abspath(__file__)))

    def diagnostics(self):
        """Allowlisted counts and versions only. Never a name, a path that identifies a person, or an amount."""
        try:
            free = int(shutil.disk_usage(self.data_dir).free // (1024 * 1024))
        except OSError:
            free = 0
        try:
            db_mb = int(os.path.getsize(os.path.join(self.data_dir, 'trips.db')) // (1024 * 1024))
        except OSError:
            db_mb = 0
        with self.lock:
            pending = int(self.tel.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0])
        base = {'version': VERSION, 'os': _machine_id(os.name) or 'os', 'db_mb': db_mb, 'disk_free_mb': free, 'pending_sync': pending,
                'error_count': int(self.recent_errors()), 'uptime_h': int((time.time() - self.started) // 3600), 'build': VERSION}
        for k, v in (self.extra() or {}).items():
            if k in ('last_backup_age_h', 'pcs', 'licence_state') and (isinstance(v, int) or _machine_id(v)):
                base[k] = v
        return base

    def _report_preview(self, data, snapshot=False):
        data, (kind, text, contact) = _report_fields(data)
        if kind not in ('problem', 'idea', 'question'):
            raise aftelemetry.PrivacyError('kind is problem, idea or question')
        known = {'page': PAGES, 'guide': {g['id'] for g in self.catalogue['guides']}, 'problem': {p['id'] for p in self.catalogue['problems']}}
        args = {'contact': contact}
        allowed = self.tel.tax['types']['fb.' + kind]['data']
        for key in ('page', 'guide', 'problem'):
            value = data.get(key)
            if value is not None and (not isinstance(value, str) or value not in known[key]):
                raise aftelemetry.PrivacyError('unknown report context')
            if value is not None and key in allowed:
                args[key] = value
        if 'diagnostics' in allowed:
            flag = data.get('diagnostics')
            if flag is True:
                args['diagnostics'] = self.diagnostics()       # never browser-supplied values
            elif snapshot and isinstance(flag, dict):
                args['diagnostics'] = flag                      # checked against the signed preview before anything is queued
        return self.tel.preview(kind, text, **args), kind, text, args

    def _digest(self, event):
        return hmac.new(self.tel.secret.encode(), json.dumps(event, sort_keys=True).encode(), hashlib.sha256).hexdigest()

    def preview(self, data):
        """Exactly what a problem report would send (after redaction) and a digest that binds the confirmation to it."""
        data = dict(data) if isinstance(data, dict) else {}
        snapshot = False
        if data.get('diagnostics') is True:
            data['diagnostics'] = self.diagnostics()
            snapshot = True
        with self.lock:
            result, _, _, _ = self._report_preview(data, snapshot)
            result['digest'] = self._digest(result['event'])
            result['version'] = VERSION
            result['sending'] = bool(self._receiver())
            return result

    def feedback(self, user, data):
        """Queue a problem report exactly as previewed. Allowed without tracking consent (Apps-Factory RULES.md section 2)."""
        data = data if isinstance(data, dict) else {}
        if data.get('diagnostics') is True:
            raise aftelemetry.PrivacyError('send the diagnostic snapshot from the preview')
        if not isinstance(data.get('confirm'), str) or not data['confirm']:
            raise aftelemetry.PrivacyError('preview and confirm the report first')
        with self.lock:
            result, kind, text, args = self._report_preview(data, snapshot=True)
            if not hmac.compare_digest(data['confirm'], self._digest(result['event'])):
                raise aftelemetry.PrivacyError('the report changed after the preview')
            eid = self.tel.feedback(kind, text, user=user['id'], confirm=result['digest'], **args)
        self.kick()
        return {'ok': True, 'id': eid, 'sending': bool(self._receiver()), 'queued': self.queue_state()}

    def queue_state(self):
        """queued / sent / retry states shown after a report: how many wait, when the last one went, the last problem."""
        with self.lock:
            waiting = int(self.tel.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0])
            reports = int(self.tel.db.execute("SELECT COUNT(*) FROM outbox WHERE type LIKE 'fb.%'").fetchone()[0])
            dead = len(self.tel.dead_letters(20))
        return {'waiting': waiting, 'reports': reports, 'dead': dead, 'lastSent': self.kv('last_sent'), 'lastError': self.kv('last_error') or '',
                'configured': bool(self._receiver())}

    def sent_public(self, user):
        with self.lock:
            rows = self.tel.recent_sent(30)
            subject = self.tel.subject(user['id'])
        return [{'type': ev.get('type'), 'ts': ev.get('ts'), 'page': ev.get('page')}
                for ev in rows if isinstance(ev, dict) and (ev.get('subject') == subject or ev.get('subject') is None)]

    def heartbeat(self):
        with self.lock:
            pending = int(self.tel.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0])
        try:
            free = int(shutil.disk_usage(self.data_dir).free // (1024 * 1024))
        except OSError:
            free = 0
        self.event('hb', {'pending_sync': pending, 'error_count': int(self.recent_errors()), 'disk_free_mb': free,
                          'uptime_h': int((time.time() - self.started) // 3600)})

    def _prune_pending(self):
        """Consent can be withdrawn while events are still waiting: anything the current agreements do not allow is deleted."""
        with self.lock:
            install = self.consent.install_allowed()
            for eid, subject, body in self.tel.db.execute('SELECT id, subject, body FROM outbox').fetchall():
                event = json.loads(body)
                if event['type'].startswith('fb.'):
                    continue                                   # the person's own report, sent on purpose
                if not install:
                    self.tel.db.execute('DELETE FROM outbox WHERE id = ?', (eid,))
                elif subject is not None and not any(self.tel.subject(r[0]) == subject and self.consent.allowed(r[0])
                                                     for r in self.db.execute("SELECT DISTINCT subject FROM consent_log WHERE scope='person'")):
                    self.tel.db.execute('DELETE FROM outbox WHERE id = ?', (eid,))

    # ---------------------------------------------------------------- delivery (a background thread, never on a request)
    @staticmethod
    def _post_remote(url, body, headers):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        request = urllib.request.Request(url, data=body, headers=headers, method='POST')
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(request, timeout=20) as response:
                return response.status, aftelemetry._server_time(response.read(65536), response.headers.get('Date'))
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, aftelemetry._server_time(exc.read(65536), exc.headers.get('Date'))

    def flush_remote(self):
        """Send one batch when a help-service address and token are both set. Returns (what, value) of the outbox, or None when nothing was tried."""
        if self.practice or not self.send_lock.acquire(blocking=False):
            return None
        try:
            with self.lock:
                if self.closed:
                    return None
                pair = self._receiver()
                if not pair:
                    return None
                self._prune_pending()

            def post(url, body, headers):
                batch = json.loads(gzip.decompress(body))
                with self.lock:
                    for event in batch:
                        self.tel.db.execute('UPDATE outbox SET merge_key = NULL WHERE id = ?', (event['id'],))
                return self._post_remote(url, body, headers)      # the network call runs without the lock
            try:
                result = self.tel.send_once(pair[0], pair[1], post=post)
            except Exception as e:  # noqa: BLE001 - never let delivery reach the program
                self.kv('last_error', e.__class__.__name__)
                return None
            what, value = result
            if what == 'sent':
                self.kv('last_error', delete=True)
                self.kv('last_sent', aftelemetry.now_iso())
            elif what in ('failed', 'dead'):
                self.kv('last_error', 'offline' if what == 'failed' and not value else f'{what}_{value}')
            return result
        finally:
            self.send_lock.release()

    def kick(self):
        self._kick.set() if hasattr(self, '_kick') else None

    def start(self, every=60):
        """Background delivery + an hourly heartbeat. The program works the same with the network unplugged."""
        self._kick = threading.Event()

        def loop():
            last_hb = 0
            while not self.closed:
                try:
                    if time.time() - last_hb > 3600:
                        last_hb = time.time()
                        self.heartbeat()
                    self.flush_remote()
                except Exception:  # noqa: BLE001
                    pass
                self._kick.wait(every)
                self._kick.clear()
        self.thread = threading.Thread(target=loop, daemon=True, name='assist')
        self.thread.start()

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                if hasattr(self, '_kick'):
                    self._kick.set()
                self.tel.close()
                self.db.close()
