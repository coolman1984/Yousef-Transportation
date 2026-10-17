"""Training mode (owner request, 17 October 2026): a separate copy of the program with its own data folder, filled with sample data,
so a person can practise without any worry. The real office never sees it: it runs as a second process on its own port
(`training_port`, by default the office port + 10) with its data under <home>/training. One button opens it; one button inside it
goes back to the real work; "start again" deletes the training folder and brings the samples back.
"""
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request


class TrainingError(Exception):
    pass


class Training:
    def __init__(self, home, cfg, cmd, log=print):
        self.dir = os.path.join(home, 'training')
        self.cfg, self.cmd, self.log = cfg, cmd, log
        self.proc = None
        self.lock = threading.Lock()

    @property
    def port(self):
        return int(self.cfg.get('training_port') or int(self.cfg['port']) + 10)

    def alive(self):
        """True when the training copy answers on its port (ours, or one left running by an earlier start)."""
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/api/auth/status', headers={'Host': f'127.0.0.1:{self.port}'})
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                return bool(((json.loads(r.read()) or {}).get('me') or {}).get('training'))
        except (OSError, ValueError):
            return False

    def _config(self):
        keep = ('host', 'allowed_networks', 'allowed_hosts', 'max_connections', 'idle_timeout_seconds', 'max_upload_mb')
        return {**{k: self.cfg[k] for k in keep if k in self.cfg},
                'port': self.port, 'sync_port': self.port + 1, 'data_dir': os.path.join(self.dir, 'data'),
                'backup_dir': os.path.join(self.dir, 'backups'), 'extra_backup_dirs': [], 'backup_interval_hours': 24, 'keep_auto_backups': 5,
                'open_browser': False, 'peer_addresses': {}, 'sign_in': False, 'training': True, 'real_port': int(self.cfg['port'])}

    def _start(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(self._config(), f, indent=2)
        env = {k: v for k, v in os.environ.items() if k != 'TO_CONFIG'}
        env['TO_HOME'] = self.dir
        out = open(os.path.join(self.dir, 'training-output.txt'), 'a', encoding='utf-8', errors='replace')
        self.proc = subprocess.Popen(self.cmd, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        out.close()
        self.log(f'Training copy starting on port {self.port}')

    def open(self, wait=60):
        """Start the training copy if it is not running yet and wait until it answers. Returns its port."""
        with self.lock:
            if self.alive():
                return self.port
            if not (self.proc and self.proc.poll() is None):
                self._start()
            end = time.time() + wait
            while time.time() < end:
                if self.alive():
                    return self.port
                if self.proc.poll() is not None:
                    break
                time.sleep(0.3)
            raise TrainingError('The training copy did not start. Close the program, open it again and try once more.')

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=15)
        self.proc = None

    def reset(self):
        """Delete everything done in training and start again with fresh sample data. Returns the port."""
        with self.lock:
            self.stop()
            if self.alive():   # left running by an earlier start of the program: it cannot be stopped from here
                raise TrainingError('The training copy is still open from before. Close the program, open it again and try once more.')
            for _ in range(20):
                try:
                    shutil.rmtree(os.path.join(self.dir, 'data'), ignore_errors=False)
                    shutil.rmtree(os.path.join(self.dir, 'backups'), ignore_errors=True)
                    break
                except FileNotFoundError:
                    break
                except OSError:  # Windows frees the database files a moment after the process ends
                    time.sleep(0.5)
            else:
                raise TrainingError('The training data could not be deleted. Close the program, open it again and try once more.')
        return self.open()


def watch_real(real_port, stop, every=20, misses=3):
    """In the training copy: stop it when the real program is gone (closed, killed or updated), so no training copy is left running alone."""
    def answers():
        req = urllib.request.Request(f'http://127.0.0.1:{real_port}/api/auth/status', headers={'Host': f'127.0.0.1:{real_port}'})
        try:
            with urllib.request.urlopen(req, timeout=5):
                return True
        except OSError:
            return False

    def loop():
        missed = 0
        while missed < misses:
            time.sleep(every)
            missed = 0 if answers() else missed + 1
        stop()

    t = threading.Thread(target=loop, name='training-watch', daemon=True)
    t.start()
    return t
