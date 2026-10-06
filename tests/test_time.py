"""F11: one time contract. Durations are real elapsed time (aware instants), calendar days and shown times are Cairo business time,
the clock changes of Egypt's daylight saving time are handled, a phone with a wrong time zone is brought to business time, and a
driver link expires at the same instant whatever time zone the office PC is set to."""
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import domain  # noqa: E402
import gateway_client as G  # noqa: E402
import tz  # noqa: E402

H = timedelta(hours=1)


class DurationTest(unittest.TestCase):
    def test_a_the_reproduced_mixed_offset_interval_is_three_hours(self):
        self.assertEqual(domain.duration('2026-10-01T08:00:00+03:00', '2026-10-01T08:00:00Z'), 3 * H)

    def test_b_same_offset_and_naive_times(self):
        self.assertEqual(domain.duration('2026-10-01T08:00:00+03:00', '2026-10-01T11:00:00+03:00'), 3 * H)
        self.assertEqual(domain.duration('2026-10-01T08:00:00', '2026-10-01T11:30:00'), 3.5 * H)
        self.assertEqual(domain.duration('2026-10-01T08:00:00', '2026-10-01T11:00:00+03:00'), 3 * H, 'a naive time is Cairo time')
        self.assertIsNone(domain.duration('2026-10-01T11:00:00', '2026-10-01T08:00:00'), 'an end before the start has no duration')
        self.assertIsNone(domain.duration('', '2026-10-01T08:00:00'))
        self.assertIsNone(domain.duration('junk', '2026-10-01T08:00:00'))

    def test_c_the_nights_the_clocks_change(self):
        # Egypt 2026: summer time starts Fri 24 Apr at 00:00 (-> 01:00) and ends Thu 29 Oct at 24:00 (-> 23:00)
        self.assertEqual(domain.duration('2026-04-23T23:00:00', '2026-04-24T03:00:00'), 3 * H, 'the night is an hour shorter')
        self.assertEqual(domain.duration('2026-10-29T22:00:00', '2026-10-30T03:00:00'), 6 * H, 'the night is an hour longer')
        self.assertEqual(domain.duration('2026-07-01T22:00:00', '2026-07-02T03:00:00'), 5 * H, 'an ordinary night')
        # overtime follows the real time: 12 h threshold
        d = domain.duration('2026-10-29T14:00:00', '2026-10-30T03:30:00')
        self.assertEqual((d, domain.overtime(d)), (14.5 * H, 2.5 * H))

    def test_d_shown_times_are_cairo_business_time(self):
        self.assertEqual(domain.parse_dt('2026-10-01T05:00:00Z'), datetime(2026, 10, 1, 8, 0))     # summer time, +03:00
        self.assertEqual(domain.parse_dt('2026-12-01T05:00:00Z'), datetime(2026, 12, 1, 7, 0))     # winter time, +02:00
        self.assertEqual(domain.parse_dt('2026-12-01T05:00:00+00:00'), datetime(2026, 12, 1, 7, 0))
        self.assertEqual(domain.parse_dt('2026-12-01T09:15:00'), datetime(2026, 12, 1, 9, 15), 'a naive time stays as it is')
        self.assertEqual(domain.parse_dt('2026-12-01'), datetime(2026, 12, 1))
        self.assertIsNone(domain.parse_dt('nonsense'))

    def test_e_business_now_does_not_depend_on_the_pc_time_zone(self):
        old = os.environ.get('TZ')
        try:
            for zone in ('Asia/Tokyo', 'America/New_York', 'UTC'):
                os.environ['TZ'] = zone
                time.tzset()
                got = domain.business_now()
                want = datetime.now(timezone.utc).astimezone(tz.BUSINESS).replace(tzinfo=None)
                self.assertLess(abs((got - want).total_seconds()), 5, zone)
        finally:
            if old is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = old
            time.tzset()


class ZoneRulesTest(unittest.TestCase):
    def test_f_the_built_in_rules_agree_with_the_time_zone_database_for_every_hour_2023_to_2030(self):
        """The program ships without a tz database on Windows, so it carries Egypt's rules itself. Proof against zoneinfo on this machine."""
        try:
            from zoneinfo import ZoneInfo
            ref = ZoneInfo('Africa/Cairo')
        except Exception:                                    # noqa: BLE001
            self.skipTest('no time zone database on this machine')
        mine = tz.EgyptRules()
        t = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end = datetime(2030, 12, 31, tzinfo=timezone.utc)
        bad = []
        while t < end:
            a, b = t.astimezone(ref), t.astimezone(mine)
            if a.replace(tzinfo=None) != b.replace(tzinfo=None) or a.utcoffset() != b.utcoffset():
                bad.append(t)
                if len(bad) > 5:
                    break
            t += timedelta(minutes=30)
        self.assertEqual(bad, [], 'instant -> wall time')
        w = datetime(2023, 1, 1)
        while w < datetime(2030, 12, 31):
            for fold in (0, 1):
                x, y = w.replace(fold=fold), w.replace(fold=fold)
                if x.replace(tzinfo=ref).utcoffset() != y.replace(tzinfo=mine).utcoffset():
                    bad.append((w, fold))
            w += timedelta(minutes=30)
            if len(bad) > 5:
                break
        self.assertEqual(bad, [], 'wall time -> offset, both in the repeated hour and in the skipped hour')

    def test_g_unclear_wall_times_are_recognised(self):
        self.assertTrue(tz.unclear(datetime(2026, 10, 29, 23, 30)), 'the hour that happens twice')
        self.assertTrue(tz.unclear(datetime(2026, 4, 24, 0, 30)), 'the hour that does not exist')
        self.assertFalse(tz.unclear(datetime(2026, 7, 1, 12, 0)))
        for rules in (tz.BUSINESS, tz.EgyptRules()):
            self.assertTrue(tz.unclear(datetime(2026, 10, 29, 23, 30), rules))
            self.assertFalse(tz.unclear(datetime(2026, 12, 1, 0, 30), rules))


class PhoneAndLinkTest(unittest.TestCase):
    def test_h_a_phone_with_the_wrong_time_zone_is_brought_to_business_time(self):
        # the phone thinks it is UTC: 06:41:12 on its clock is 09:41:12 in Cairo in September; receive time is UTC too
        self.assertEqual(G.local_pair('2026-09-28T06:41:12+00:00', '2026-09-28T06:41:20Z'), ('2026-09-28T09:41:12', '2026-09-28T09:41:20'))
        self.assertEqual(G.local_pair('2026-09-28T09:41:12+03:00', '2026-09-28T06:41:20Z'), ('2026-09-28T09:41:12', '2026-09-28T09:41:20'))
        self.assertEqual(G.local_pair('2026-12-28T09:41:12+02:00', '2026-12-28T07:41:20Z'), ('2026-12-28T09:41:12', '2026-12-28T09:41:20'), 'winter')
        self.assertEqual(G.local_pair('2026-09-28T09:41:12', '2026-09-28T06:41:20Z'), ('2026-09-28T09:41:12', '2026-09-28T09:41:20'), 'a phone time without a zone is Cairo time')
        self.assertEqual(G.local_pair('junk', '2026-09-28T06:41:20Z'), ('', ''))
        self.assertEqual(domain.drift_minutes(*G.local_pair('2026-09-28T09:41:12+03:00', '2026-09-28T06:51:12Z')), 10.0)

    def test_i_a_link_expires_at_the_same_instant_on_every_pc(self):
        now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        exp = domain.link_expiry('2026-10-01', now=now)
        self.assertRegex(exp, r'\+00:00$')
        self.assertEqual(exp, '2026-10-08T12:00:00+00:00', 'seven days after the trip order is made')
        self.assertEqual(domain.link_expiry('2026-10-20', now=now), '2026-10-22T21:00:00+00:00', 'three days after the planned date (Cairo midnight, +03:00)')
        old = os.environ.get('TZ')
        try:
            seen = set()
            for zone in ('Africa/Cairo', 'Asia/Tokyo', 'America/New_York', 'UTC'):
                os.environ['TZ'] = zone
                time.tzset()
                seen.add(G._epoch(exp))
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen.pop(), int(datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc).timestamp()))
        finally:
            if old is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = old
            time.tzset()
        # a link made by an older version has no zone: it was written in the office's local time (Cairo)
        self.assertEqual(G._epoch('2026-10-10T12:00:00'), int(datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc).timestamp()))

    def test_j_a_trip_whose_time_is_in_the_hour_the_clocks_change_is_flagged_for_a_look(self):
        base = {'status': 'finished', 'startKm': 1, 'endKm': 50, 'source': 'excel', 'date': '2026-10-29'}
        colour, reasons = domain.trust({**base, 'startAt': '2026-10-29T23:30:00', 'endAt': '2026-10-30T03:00:00'})
        self.assertIn('Y_TIME_UNCLEAR', reasons)
        colour, reasons = domain.trust({**base, 'startAt': '2026-10-29T10:00:00', 'endAt': '2026-10-29T15:00:00'})
        self.assertNotIn('Y_TIME_UNCLEAR', reasons)


if __name__ == '__main__':
    unittest.main()
