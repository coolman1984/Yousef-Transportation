"""Trip Orders - business rules that need no database: text and plate normalisation, trip numbers, overtime,
odometer chain, "unusual km", clock drift and the trust colour of a trip. Pure functions, easy to test.

Trust colours never block a trip: the system records first and colours afterwards (docs/EXECUTION_PLAN.md P2.2)."""
import re
import statistics
import unicodedata
from datetime import datetime, timedelta

import tz

_TATWEEL = 'ـ'
_ZERO_WIDTH = dict.fromkeys(map(ord, '​‌‍‎‏‪‫‬⁦⁧⁨⁩﻿'))
_AR_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
_AR_UNIFY = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي', 'ة': 'ه', 'ؤ': 'و', 'ئ': 'ي'})
_DIACRITICS = re.compile('[ً-ٰٟ]')
_AR_LETTER = re.compile('[ء-ي]')

NON_PERSON_WORDS = ('visitor', 'early leave', 'audit', 'cover', 'guest', 'زائر', 'ضيف')


def norm_text(s):
    """Whitespace, tatweel, zero-width characters and width forms cleaned; digits stay as they are."""
    if s is None:
        return ''
    s = unicodedata.normalize('NFKC', str(s)).translate(_ZERO_WIDTH).replace(_TATWEEL, '')
    return re.sub(r'\s+', ' ', s).strip()


def key_text(s):
    """The comparison key of a name or place: case, Arabic spelling variants, digits and punctuation ignored."""
    s = norm_text(s).translate(_AR_DIGITS).translate(_AR_UNIFY)
    s = _DIACRITICS.sub('', s).casefold()
    s = re.sub(r'[^\w\s\-]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_plate(s):
    """(display, key). "ط و ي 6829" and " طوي6829 " are the same car. A text without digits is kept as typed."""
    t = norm_text(s).translate(_AR_DIGITS)
    letters = ''.join(_AR_LETTER.findall(_DIACRITICS.sub('', t).translate(_AR_UNIFY)))
    digits = ''.join(re.findall(r'\d', t))
    if not digits or not letters:
        return t, key_text(t).replace(' ', '')
    return ' '.join(letters) + ' ' + digits, letters + digits


def norm_mobile_eg(s):
    """(+20 number, ok). Egyptian mobiles: 01xxxxxxxxx, 201xxxxxxxxx, +201xxxxxxxxx."""
    d = re.sub(r'\D', '', norm_text(s).translate(_AR_DIGITS))
    if d.startswith('00'):
        d = d[2:]
    if d.startswith('01') and len(d) == 11:
        d = '2' + d
    if d.startswith('201') and len(d) == 12:
        return '+' + d, True
    return norm_text(s), False


def is_non_person(name):
    k = key_text(name)
    return any(w in k for w in NON_PERSON_WORDS)


def split_passengers(text, known_keys=()):
    """"Ali - Sara" -> ['Ali', 'Sara'] only when every part is a known person; otherwise the text is one entry."""
    text = norm_text(text)
    parts = [p.strip() for p in re.split(r'\s+-\s+|\s*[,،]\s*|\s*&\s*', text) if p.strip()]
    if len(parts) > 1 and known_keys and all(key_text(p) in known_keys for p in parts):
        return parts
    return [text] if text else []


# ---------------------------------------------------------------- trip numbers
def pc_letter(index):
    """0 -> A (the administrator PC), 1 -> B ... 25 -> Z, then AA, AB."""
    s = ''
    n = index
    while True:
        s = chr(65 + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


def trip_no(year, letter, counter):
    return f'{year % 100:02d}-{letter}-{counter:05d}'


def parse_trip_no(no):
    m = re.fullmatch(r'(\d{2})-([A-Z]+)-(\d{5,})', str(no or ''))
    return (int(m.group(1)), m.group(2), int(m.group(3))) if m else None


def next_counter(existing_nos, year, letter):
    hi = 0
    for n in existing_nos:
        p = parse_trip_no(n)
        if p and p[0] == year % 100 and p[1] == letter:
            hi = max(hi, p[2])
    return hi + 1


# ---------------------------------------------------------------- time
# One contract: a time WITH a zone is an exact instant; a time WITHOUT a zone (typed at the office, from Excel, from an old version) is
# Cairo wall time. Durations are real elapsed time (so the nights the clocks change are right); days and shown times are Cairo time.
def _parse(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s).strip().replace('Z', '+00:00'))
    except ValueError:
        return None


def instant(s):
    """The exact moment as an aware UTC datetime, None when empty or invalid. A time without a zone is Cairo time."""
    d = _parse(s)
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz.BUSINESS)
    return d.astimezone(tz.UTC)


def parse_dt(s):
    """ISO date or date-time -> naive datetime in Cairo business time (a time with a zone is converted), None when empty or invalid."""
    d = _parse(s)
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(tz.BUSINESS)
    return d.replace(tzinfo=None)


def business_now():
    """Now in Cairo business time (naive), whatever time zone this PC is set to."""
    return datetime.now(tz.UTC).astimezone(tz.BUSINESS).replace(tzinfo=None)


def link_expiry(trip_date, now=None):
    """When a driver link stops working, as an exact UTC time: seven days from now, or three days after the planned date, whichever is later."""
    now = now or datetime.now(tz.UTC)
    day = instant(trip_date)
    later = day + timedelta(days=3) if day else now
    return max(now + timedelta(days=7), later).isoformat(timespec='seconds')


def time_unclear(s):
    """True when a time typed without a zone falls in the hour the clocks change (it may mean either of two moments)."""
    d = _parse(s)
    return d is not None and d.tzinfo is None and tz.unclear(d)


def duration(start_at, end_at):
    a, b = instant(start_at), instant(end_at)
    if not a or not b or b < a:
        return None
    return b - a


def overtime(d, threshold_hours=12):
    """Trip time beyond the threshold, as a timedelta (zero when none)."""
    if d is None:
        return timedelta(0)
    return max(timedelta(0), d - timedelta(hours=threshold_hours))


def hours(td):
    return round(td.total_seconds() / 3600, 2) if td else 0.0


def drift_minutes(phone_at, recv_at):
    a, b = parse_dt(phone_at), parse_dt(recv_at)
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 60, 1)


# ---------------------------------------------------------------- odometer
def km_of(trip):
    s, e = trip.get('startKm'), trip.get('endKm')
    if isinstance(s, (int, float)) and isinstance(e, (int, float)):
        return e - s
    return None


def _order_key(t):
    return (str(t.get('startAt') or t.get('date') or ''), str(t.get('no') or ''), str(t.get('id') or ''))


def odometer_chain(trips):
    """trips of ONE vehicle -> {trip id: {'backstep': km back, 'gap': km without a trip}}.
    A back-step (start below the previous end) is a fault; a gap is only information - the sheet records some trips only."""
    out = {}
    prev = None
    for t in sorted((t for t in trips if isinstance(t.get('startKm'), (int, float)) and isinstance(t.get('endKm'), (int, float))), key=_order_key):
        if prev is not None:
            d = t['startKm'] - prev['endKm']
            if d < 0:
                out[t['id']] = {'backstep': -d, 'after': prev['id']}
            elif d > 0:
                out[t['id']] = {'gap': d, 'after': prev['id']}
        prev = t
    return out


def unusual_km(km, history_kms, min_history=3, tolerance=0.25, floor=30):
    """True when km differs from the median of earlier trips on the same destination by more than 25 % (at least 30 km)."""
    if km is None or len(history_kms) < min_history:
        return False
    med = statistics.median(history_kms)
    return abs(km - med) > max(tolerance * med, floor)


# ---------------------------------------------------------------- trust colour
RED, YELLOW, GREEN, GREY = 'red', 'yellow', 'green', 'grey'
DONE = ('finished', 'closed')


def trust(trip, photos=(), amendments=(), events=(), chain=None, history_kms=(), open_limit_hours=16, now=None, drift_limit=10,
          billable_check=True):
    """(colour, [reason codes]) - deterministic, computed on read. Not-finished trips are grey (or red when left open too long)."""
    now = now or business_now()
    reasons = []
    status = trip.get('status') or 'draft'
    if status == 'cancelled':
        return GREY, []
    kinds = {p.get('kind') for p in photos}
    km = km_of(trip)
    chain = chain or {}
    if chain.get('backstep'):
        reasons.append('R_BACKSTEP')
    if km is not None and km <= 0:
        reasons.append('R_END_LE_START')
    bound = trip.get('boundDevice')
    if bound and any(e.get('deviceId') and e.get('deviceId') != bound for e in events):
        reasons.append('R_SECOND_DEVICE')
    if status in DONE:
        if trip.get('source', 'app') == 'app' and 'paper' not in kinds:
            reasons.append('R_NO_PAPER')
        if trip.get('source', 'app') == 'app' and 'start_odo' not in kinds:
            reasons.append('Y_NO_START_PHOTO')
    elif status == 'started':
        st = parse_dt(trip.get('startAt'))
        if st and now - st > timedelta(hours=open_limit_hours):
            reasons.append('R_OPEN_TOO_LONG')
    if any(p.get('fallback') for p in photos):
        reasons.append('Y_FALLBACK_PHOTO')
    if unusual_km(km, list(history_kms)):
        reasons.append('Y_KM_UNUSUAL')
    if any(abs(drift_minutes(e.get('phoneAt'), e.get('recvAt')) or 0) > drift_limit for e in events if not (e.get('payload') or {}).get('queued')):
        reasons.append('Y_DRIFT')
    if time_unclear(trip.get('startAt')) or time_unclear(trip.get('endAt')):
        reasons.append('Y_TIME_UNCLEAR')
    if any(a.get('field') == 'status' and a.get('new') in DONE for a in amendments):
        reasons.append('Y_CLOSED_BY_OFFICE')
    if amendments:
        reasons.append('Y_AMENDED')
    if trip.get('source') == 'excel' and trip.get('importWarn'):
        reasons.append('Y_IMPORT_WARN')
    if billable_check and km is not None and isinstance(trip.get('billableKm'), (int, float)) and trip['billableKm'] != km:
        reasons.append('Y_BILLABLE_DIFF')
    reasons = list(dict.fromkeys(reasons))
    if any(r.startswith('R_') for r in reasons):
        return RED, reasons
    if any(r.startswith('Y_') for r in reasons):
        return YELLOW, reasons
    return (GREEN if status in DONE else GREY), reasons
