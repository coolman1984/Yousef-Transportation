"""Trip Orders - the business time zone (Africa/Cairo).

Every office PC and phone may be set to another zone; trips are always read and grouped in Cairo business time. The time zone database
(`zoneinfo`) is used when the PC has it; Windows does not ship one and the installed program must not need an extra package, so the rules
of Egypt are also built in (`EgyptRules`): since 2023 summer time (+03:00) runs from the last Friday of April, 00:00, to the last Thursday of
October, 24:00; otherwise +02:00 (before 2023 the built-in rules say +02:00 - no business data of that time is expected). A test compares
the built-in rules with the database for every half hour from 2023 to 2036.
"""
from datetime import datetime, timedelta, timezone, tzinfo

NAME = 'Africa/Cairo'
STANDARD, SUMMER = timedelta(hours=2), timedelta(hours=3)


def _last(year, month, weekday):
    """Midnight of the last `weekday` (Mon=0) of the month."""
    d = datetime(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


class EgyptRules(tzinfo):
    """Egypt without a tz database. Offsets are decided in UTC, so every conversion is consistent."""

    @staticmethod
    def _offset_at_utc(u):
        if u.year >= 2023:
            start = _last(u.year, 4, 4) - STANDARD                        # Friday 00:00 standard time
            end = _last(u.year, 10, 3) + timedelta(days=1) - SUMMER       # Thursday 24:00 summer time
            if start <= u < end:
                return SUMMER
        return STANDARD

    def utcoffset(self, dt):
        w = dt.replace(tzinfo=None)
        summer = self._offset_at_utc(w - SUMMER) == SUMMER                # could this wall time be summer time?
        standard = self._offset_at_utc(w - STANDARD) == STANDARD          # could it be standard time?
        if summer and standard:                                           # the hour that happens twice: first time summer, second standard
            return STANDARD if dt.fold else SUMMER
        if summer:
            return SUMMER
        if standard:
            return STANDARD
        return SUMMER if dt.fold else STANDARD                            # the hour that does not exist (like zoneinfo)

    def dst(self, dt):
        return self.utcoffset(dt) - STANDARD

    def tzname(self, dt):
        return 'EEST' if self.dst(dt) else 'EET'

    def fromutc(self, dt):
        u = dt.replace(tzinfo=None)
        off = self._offset_at_utc(u)
        w = u + off
        out = w.replace(tzinfo=self)
        if self._offset_at_utc(w - STANDARD) == STANDARD and self._offset_at_utc(w - SUMMER) == SUMMER and off == STANDARD:
            out = out.replace(fold=1)                                     # the second time through the repeated hour
        return out


def _business():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(NAME)
    except Exception:                                                     # noqa: BLE001 - no database (Windows) or no zoneinfo
        return EgyptRules()


BUSINESS = _business()
UTC = timezone.utc


def unclear(naive, zone=None):
    """True when a wall time is ambiguous (the hour that happens twice) or does not exist (the skipped hour) - such a time needs a look."""
    zone = zone or BUSINESS
    w = naive.replace(tzinfo=None)
    return w.replace(tzinfo=zone, fold=0).utcoffset() != w.replace(tzinfo=zone, fold=1).utcoffset()
