import unittest
from datetime import date

from pomodoro.recurrence import Schedule, ordinal

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


class ScheduleTests(unittest.TestCase):
    def test_daily_working_days_skips_weekend(self):
        s = Schedule("daily", MON, date(2026, 11, 8))
        dates = s.dates(MON, date(2026, 11, 8), WEEKDAYS)
        self.assertEqual(len(dates), 10)                   # two working weeks
        self.assertTrue(all(d.weekday() < 5 for d in dates))
        self.assertEqual(s.describe(), "Every working day until 08 Nov")

    def test_daily_every_day(self):
        s = Schedule("daily", MON, date(2026, 11, 1), workdays_only=False)
        self.assertEqual(s.count(WEEKDAYS), 7)

    def test_weekly_defaults_to_start_weekday_and_supports_several_days(self):
        s = Schedule("weekly", MON, date(2026, 11, 23))
        self.assertEqual(s.weekdays, [0])
        self.assertEqual(s.count(WEEKDAYS), 5)              # 26 Oct, 2, 9, 16, 23 Nov
        s2 = Schedule("weekly", MON, date(2026, 11, 1), weekdays=[0, 3])
        self.assertEqual(s2.dates(MON, date(2026, 11, 1), WEEKDAYS),
                         [date(2026, 10, 26), date(2026, 10, 29)])
        self.assertEqual(s2.describe(), "Weekly on Mon, Thu until 01 Nov")

    def test_monthly_day_31_uses_last_day_of_short_months(self):
        s = Schedule("monthly", date(2026, 1, 31), date(2026, 5, 31))
        self.assertEqual(s.dates(s.start, s.end, WEEKDAYS),
                         [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31),
                          date(2026, 4, 30), date(2026, 5, 31)])
        self.assertEqual(s.describe(), "Monthly on the last day until 31 May")

    def test_monthly_leap_year(self):
        s = Schedule("monthly", date(2028, 1, 30), date(2028, 3, 31))
        self.assertIn(date(2028, 2, 29), s.dates(s.start, s.end, WEEKDAYS))

    def test_end_date_is_inclusive_and_required_order(self):
        s = Schedule("daily", MON, MON)
        self.assertEqual(s.count(WEEKDAYS), 1)
        with self.assertRaises(ValueError):
            Schedule("daily", MON, date(2026, 10, 1))
        with self.assertRaises(ValueError):
            Schedule("yearly", MON, MON)

    def test_next_date(self):
        s = Schedule("daily", MON, date(2026, 11, 6))
        self.assertEqual(s.next_date(date(2026, 10, 30), WEEKDAYS), date(2026, 11, 2))  # Fri -> Mon
        self.assertIsNone(s.next_date(date(2026, 11, 6), WEEKDAYS))
        self.assertEqual(s.next_date(date(2026, 10, 1), WEEKDAYS), MON)       # before start

    def test_ordinal(self):
        self.assertEqual([ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23)],
                         ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd",
                          "23rd"])


if __name__ == "__main__":
    unittest.main()
