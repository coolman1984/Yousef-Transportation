"""Trip Orders - rates by trip date.

A trip category has a CURRENT rate per km and per overtime hour (`ratePerKm`, `ratePerOtHour`). When a rate that had a value is
changed, the old rate is kept in `rateHistory`, so a trip is always priced with the rate that was valid on ITS date and a report
for last month does not change when this month's rate does:

    rateHistory = [{'until': '2026-09-01', 'ratePerKm': 10, 'ratePerOtHour': 50}, ...]   (oldest first)

An entry's rates apply to trips dated BEFORE `until`; trips from `until` on use the next entry, and finally the current rate.
The rule the user sees: a new rate applies to trips from the day it is saved; earlier trips keep the old one.

Nothing is invented: a rate that was never set is not history (the first value set applies to every trip, as before), and
0 or empty means "not set".
"""
FIELDS = ('ratePerKm', 'ratePerOtHour')


def _num(v):
    try:
        return float(v) if v not in (None, '') else 0.0
    except (TypeError, ValueError):
        return 0.0


def clean_history(raw):
    """The history as a list of well-formed entries (anything else in the field is ignored)."""
    out = []
    for h in raw if isinstance(raw, list) else []:
        if isinstance(h, dict) and isinstance(h.get('until'), str) and len(h['until']) == 10:
            out.append({'until': h['until'], **{f: h.get(f) for f in FIELDS}})
    return sorted(out, key=lambda h: h['until'])


def rates_on(cat, date):
    """(rate per km, rate per overtime hour) valid for a trip of this date; 0 where no rate is set. A trip without a date uses the current rate."""
    cat = cat or {}
    d = str(date or '')[:10]
    if d:
        for h in clean_history(cat.get('rateHistory')):
            if d < h['until']:
                return _num(h.get('ratePerKm')), _num(h.get('ratePerOtHour'))
    return _num(cat.get('ratePerKm')), _num(cat.get('ratePerOtHour'))


def stamp(before, row, today):
    """The `rateHistory` the saved category row must carry. `before` is the saved category (None for a new one), `row` what is being
    saved, `today` the date of the change (YYYY-MM-DD). The client never writes the history itself."""
    if not before:
        return []
    hist = clean_history(before.get('rateHistory'))
    old = {f: _num(before.get(f)) for f in FIELDS}
    new = {f: _num(row.get(f)) for f in FIELDS}
    if old == new:
        return hist
    for f in FIELDS:                                   # a rate that was never set is not history: what is set now applies to the past too
        if not old[f] and new[f]:
            for h in hist:
                if not _num(h.get(f)):
                    h[f] = new[f]
    if hist and hist[-1]['until'] >= today:            # corrected on the same day it was changed: the correction replaces it
        return hist
    if any(old[f] and old[f] != new[f] for f in FIELDS):
        hist.append({'until': today, **{f: (old[f] or new[f]) for f in FIELDS}})
    return hist
