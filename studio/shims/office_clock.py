"""Studio only: run the office program on the STUDIO CLOCK.
The clock file holds {"offset": seconds}; time.time() and datetime.now() are moved by that offset, read again whenever the file changes,
so the studio can jump forward (the drive between start and end) without restarting anything.
    STUDIO_CLOCK=/path/clock.json python office_clock.py ../server/app.py"""
import datetime as _dt
import json
import os
import runpy
import sys
import time as _time

CLOCK = os.environ['STUDIO_CLOCK']
_real = _time.time
_cache = {'m': None, 'off': 0.0}


def offset():
    try:
        m = os.stat(CLOCK).st_mtime_ns
    except OSError:
        return _cache['off']
    if m != _cache['m']:
        try:
            with open(CLOCK) as f:
                _cache['off'] = float(json.load(f)['offset'])
            _cache['m'] = m
        except (OSError, ValueError, KeyError):
            pass
    return _cache['off']


_time.time = lambda: _real() + offset()


class StudioDateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(_time.time(), tz)

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        return cls.fromtimestamp(_time.time(), _dt.timezone.utc).replace(tzinfo=None)


_dt.datetime = StudioDateTime
app = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.dirname(app))
sys.argv = [app] + sys.argv[2:]
runpy.run_path(app, run_name='__main__')
