"""Business rules of server/domain.py, including the edge cases found in the September workbook."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import domain as d  # noqa: E402


class TextTest(unittest.TestCase):
    def test_plate_variants_are_one_car(self):
        for raw in ('ط و ي 6829', ' ط و ي 6829', 'طوي6829', 'ط  و  ي  ٦٨٢٩', 'ﻁ ﻭ ﻱ 6829', 'ط و ى 6829'):
            with self.subTest(raw=raw):
                self.assertEqual(d.norm_plate(raw), ('ط و ي 6829', 'طوي6829'))

    def test_plate_without_digits_is_kept(self):
        self.assertEqual(d.norm_plate('  Rental van ')[0], 'Rental van')

    def test_names_compare_without_spacing_case_or_spelling(self):
        self.assertEqual(d.key_text('Sayed  Abdallah Reyad '), d.key_text('sayed abdallah reyad'))
        self.assertEqual(d.key_text('أحمد إبراهيم'), d.key_text('احمد ابراهيم'))
        self.assertEqual(d.key_text('Jackie'), d.key_text('jackie'))

    def test_mobile(self):
        for raw in ('01012345678', '+201012345678', '00201012345678', '٠١٠١٢٣٤٥٦٧٨'):
            self.assertEqual(d.norm_mobile_eg(raw), ('+201012345678', True), raw)
        self.assertFalse(d.norm_mobile_eg('123')[1])

    def test_non_person_words_and_passenger_split(self):
        for n in ('Visitor', 'Early leave', 'EHS Audit', 'Cover Katamia- Line'):
            self.assertTrue(d.is_non_person(n), n)
        self.assertFalse(d.is_non_person('Sara Adel'))
        known = {d.key_text('Ali Hassan'), d.key_text('Sara Adel')}
        self.assertEqual(d.split_passengers('Ali Hassan - Sara Adel', known), ['Ali Hassan', 'Sara Adel'])
        self.assertEqual(d.split_passengers('Jungmo Go-Moohyoung Lee', known), ['Jungmo Go-Moohyoung Lee'])


class TripNumberTest(unittest.TestCase):
    def test_format_and_letters(self):
        self.assertEqual(d.trip_no(2026, 'A', 233), '26-A-00233')
        self.assertEqual([d.pc_letter(i) for i in (0, 1, 25, 26, 27)], ['A', 'B', 'Z', 'AA', 'AB'])

    def test_counter_is_per_year_and_pc(self):
        nos = ['26-A-00010', '26-B-00050', '25-A-00099', 'weird']
        self.assertEqual(d.next_counter(nos, 2026, 'A'), 11)
        self.assertEqual(d.next_counter(nos, 2026, 'B'), 51)
        self.assertEqual(d.next_counter(nos, 2027, 'A'), 1)

    def test_two_offline_pcs_never_collide(self):
        a = {d.trip_no(2026, 'A', d.next_counter([], 2026, 'A'))}
        b = {d.trip_no(2026, 'B', d.next_counter([], 2026, 'B'))}
        self.assertFalse(a & b)


class TimeTest(unittest.TestCase):
    def test_overtime_beyond_twelve_hours(self):
        dur = d.duration('2026-09-28T06:30:00', '2026-09-28T22:30:00')
        self.assertEqual(d.hours(d.overtime(dur)), 4.0)
        self.assertEqual(d.hours(d.overtime(d.duration('2026-09-28T07:00:00', '2026-09-28T19:00:00'))), 0.0)

    def test_overtime_across_midnight_is_right(self):
        dur = d.duration('2026-09-28T20:00:00', '2026-09-29T09:00:00')
        self.assertEqual(d.hours(dur), 13.0)
        self.assertEqual(d.hours(d.overtime(dur)), 1.0)

    def test_missing_or_backwards_times(self):
        self.assertIsNone(d.duration(None, '2026-09-28T10:00:00'))
        self.assertIsNone(d.duration('2026-09-28T10:00:00', '2026-09-28T09:00:00'))
        self.assertEqual(d.overtime(None), timedelta(0))

    def test_drift(self):
        self.assertEqual(d.drift_minutes('2026-09-28T09:00:00', '2026-09-28T09:15:00'), 15.0)


class OdometerTest(unittest.TestCase):
    def trips(self, *pairs):
        return [{'id': f't{i}', 'no': f'26-A-{i:05d}', 'date': f'2026-09-{i + 1:02d}', 'startKm': s, 'endKm': e} for i, (s, e) in enumerate(pairs)]

    def test_chain_ok_gap_and_backstep(self):
        ch = d.odometer_chain(self.trips((100, 150), (150, 200), (260, 300), (250, 280)))
        self.assertNotIn('t1', ch)
        self.assertEqual(ch['t2']['gap'], 60)
        self.assertEqual(ch['t3']['backstep'], 50)

    def test_the_31000_km_typo_is_a_backstep(self):
        ch = d.odometer_chain(self.trips((190800, 191220), (160200, 160400)))
        self.assertEqual(ch['t1']['backstep'], 31020)

    def test_trips_without_numbers_are_ignored(self):
        self.assertEqual(d.odometer_chain([{'id': 'x', 'startKm': None, 'endKm': None}]), {})

    def test_unusual_km(self):
        self.assertFalse(d.unusual_km(212, [210, 215, 208]))
        self.assertTrue(d.unusual_km(320, [210, 215, 208]))
        self.assertFalse(d.unusual_km(500, [200, 210]))      # too little history
        self.assertFalse(d.unusual_km(40, [20, 25, 30, 35]))  # small distances tolerate 30 km


class TrustTest(unittest.TestCase):
    def done(self, **kw):
        return {'id': 't', 'status': 'finished', 'startKm': 100, 'endKm': 200, 'source': 'app', **kw}

    PHOTOS = [{'kind': 'start_odo'}, {'kind': 'end_odo'}, {'kind': 'paper'}]

    def test_green(self):
        self.assertEqual(d.trust(self.done(), self.PHOTOS), ('green', []))

    def test_red_rules(self):
        cases = {
            'R_BACKSTEP': dict(chain={'backstep': 5}),
            'R_END_LE_START': dict(trip=self.done(endKm=100)),
            'R_NO_PAPER': dict(photos=[{'kind': 'start_odo'}, {'kind': 'end_odo'}]),
            'R_SECOND_DEVICE': dict(trip=self.done(boundDevice='a'), events=[{'deviceId': 'b'}]),
        }
        for code, kw in cases.items():
            with self.subTest(code=code):
                colour, reasons = d.trust(kw.pop('trip', self.done()), kw.pop('photos', self.PHOTOS), **kw)
                self.assertEqual(colour, 'red')
                self.assertIn(code, reasons)

    def test_open_too_long(self):
        t = {'id': 't', 'status': 'started', 'startAt': '2026-09-28T06:00:00'}
        self.assertEqual(d.trust(t, now=datetime(2026, 9, 28, 20, 0)), ('grey', []))
        self.assertEqual(d.trust(t, now=datetime(2026, 9, 29, 6, 0))[0], 'red')

    def test_yellow_rules(self):
        cases = {
            'Y_FALLBACK_PHOTO': dict(photos=[{'kind': 'start_odo', 'fallback': True}, {'kind': 'paper'}]),
            'Y_NO_START_PHOTO': dict(photos=[{'kind': 'end_odo'}, {'kind': 'paper'}]),
            'Y_KM_UNUSUAL': dict(history_kms=[300, 310, 305]),
            'Y_DRIFT': dict(events=[{'phoneAt': '2026-09-28T09:00:00', 'recvAt': '2026-09-28T09:30:00', 'payload': {}}]),
            'Y_AMENDED': dict(amendments=[{'field': 'endKm', 'new': 210}]),
            'Y_CLOSED_BY_OFFICE': dict(amendments=[{'field': 'status', 'new': 'closed'}]),
            'Y_BILLABLE_DIFF': dict(trip=self.done(billableKm=90)),
        }
        for code, kw in cases.items():
            with self.subTest(code=code):
                colour, reasons = d.trust(kw.pop('trip', self.done()), kw.pop('photos', self.PHOTOS), **kw)
                self.assertEqual(colour, 'yellow')
                self.assertIn(code, reasons)

    def test_queued_events_do_not_count_as_drift(self):
        ev = [{'phoneAt': '2026-09-28T09:00:00', 'recvAt': '2026-09-28T13:00:00', 'payload': {'queued': True}}]
        self.assertEqual(d.trust(self.done(), self.PHOTOS, events=ev), ('green', []))

    def test_paper_trips_from_excel_need_no_photos(self):
        t = self.done(source='excel')
        self.assertEqual(d.trust(t, [])[0], 'green')
        self.assertEqual(d.trust(self.done(source='excel', importWarn=True), [])[0], 'yellow')

    def test_red_beats_yellow_and_cancelled_is_grey(self):
        c, r = d.trust(self.done(billableKm=1), self.PHOTOS, chain={'backstep': 1})
        self.assertEqual(c, 'red')
        self.assertIn('Y_BILLABLE_DIFF', r)
        self.assertEqual(d.trust({'status': 'cancelled'})[0], 'grey')


if __name__ == '__main__':
    unittest.main()
