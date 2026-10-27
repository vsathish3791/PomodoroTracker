import unittest
from datetime import date, datetime, timedelta

from pomodoro.database import Database
from pomodoro.priority import rank_tasks
from pomodoro.recurrence import due_reminders, parse_cue_time, streaks

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


def day(n: int) -> date:
    return MON + timedelta(days=n)


class StreakTests(unittest.TestCase):
    def test_streaks(self):
        self.assertEqual(streaks([]), (0, 0))
        self.assertEqual(streaks(["done", "done", "missed", "done"]), (1, 2))
        self.assertEqual(streaks(["done", "done", "done", "todo"]), (3, 3))  # today open
        self.assertEqual(streaks(["done", "missed"]), (0, 1))

    def test_cue_time_parsing(self):
        self.assertEqual(parse_cue_time("8:30"), "08:30")
        self.assertIsNone(parse_cue_time("  "))
        for bad in ("25:00", "8", "ab:cd"):
            with self.assertRaises(ValueError):
                parse_cue_time(bad)


class ReminderTests(unittest.TestCase):
    def test_due_within_window_once(self):
        today = MON.isoformat()
        tasks = [
            {"id": 1, "cue_time": "08:30", "remind": 1, "occurrence_date": today},
            {"id": 2, "cue_time": "08:30", "remind": 0, "occurrence_date": today},  # off
            {"id": 3, "cue_time": "09:00", "remind": 1, "occurrence_date": today},  # later
            {"id": 4, "cue_time": None, "remind": 1, "occurrence_date": today},
            {"id": 5, "cue_time": "08:00", "remind": 1, "occurrence_date": today},  # too old
        ]
        now = datetime(2026, 10, 26, 8, 31)
        self.assertEqual([t["id"] for t in due_reminders(tasks, now, set())], [1])
        self.assertEqual(due_reminders(tasks, now, {1}), [])


class HabitDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.read = self.db.create_recurrence(
            "Read 1 pomodoro", nature="habit", frequency="daily", workdays_only=0,
            start_date=MON.isoformat(), end_date=day(30).isoformat(), cue_time="8:30",
            cue_place="at my desk", two_minute="Open the book and read one page")
        with self.db.conn:
            self.db.conn.execute("UPDATE recurrences SET created_at = '2026-01-01T00:00'")

    def tearDown(self):
        self.db.close()

    def today_task(self):
        return self.db.find_open_task("Read 1 pomodoro")

    def test_habit_fields_reach_the_occurrence(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        task = self.db.get_task(self.today_task())
        self.assertEqual((task["cue_time"], task["cue_place"], task["two_minute"], task["remind"]),
                         ("08:30", "at my desk", "Open the book and read one page", 1))
        self.assertEqual(task["nature"], "habit")

    def test_showed_up_counts_for_the_streak(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.mark_showed_up(self.today_task())
        self.db.generate_occurrences(day(1), WEEKDAYS)
        self.db.set_task_status(self.today_task(), "done")
        self.db.generate_occurrences(day(2), WEEKDAYS)
        rec = self.db.list_recurrences(today=day(2), working_days=WEEKDAYS)[0]
        self.assertEqual((rec["streak"], rec["best_streak"]), (2, 2))
        history = self.db.history(self.read, today=day(2), working_days=WEEKDAYS)
        self.assertEqual([(h["status"], h["showed_up"]) for h in history[:3]],
                         [("done", True), ("done", False), ("open", False)])
        self.assertEqual([h["status"] for h in history[3:]], ["future"] * 3)
        # Reopening clears "showed up"
        first = self.db.conn.execute("SELECT id FROM tasks ORDER BY id LIMIT 1").fetchone()[0]
        self.db.set_task_status(first, "todo")
        self.assertEqual(self.db.get_task(first)["showed_up"], 0)

    def test_never_miss_twice_flag_and_boost(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.generate_occurrences(day(1), WEEKDAYS)        # Monday's becomes missed
        task = self.db.get_task(self.today_task())
        self.assertEqual(task["previous_status"], "missed")
        other = self.db.create_task("Equal priority task")
        ranked = rank_tasks(self.db.list_tasks("open"), day(1), 8, 0, WEEKDAYS)
        self.assertEqual(ranked[0].id, task["id"])            # boosted above the other
        self.assertIn("missed last time – don't miss twice", ranked[0].reasons)
        self.assertNotEqual(ranked[0].id, other)

    def test_no_missed_days_before_the_series_existed(self):
        db = Database(":memory:")
        db.create_recurrence("New habit", frequency="daily", workdays_only=0,
                             start_date="2020-01-01", end_date="2030-01-01")
        db.generate_occurrences()
        statuses = [r[0] for r in db.conn.execute("SELECT status FROM tasks")]
        self.assertEqual(statuses, ["todo"])                  # only today, nothing missed
        db.close()

    def test_stacking_followers_and_done_callback(self):
        plan = self.db.create_recurrence("Plan tomorrow", nature="habit", frequency="daily",
                                         workdays_only=0, start_date=MON.isoformat(),
                                         end_date=day(30).isoformat(),
                                         stack_after_id=self.read)
        self.assertEqual([f["id"] for f in self.db.followers(self.read)], [plan])
        with self.assertRaises(ValueError):
            self.db.update_recurrence(plan, stack_after_id=plan)
        done = []
        self.db.on_task_done.append(done.append)
        self.db.generate_occurrences(MON, WEEKDAYS)
        task = self.today_task()
        self.db.set_task_status(task, "done")
        self.db.set_task_status(task, "done")                 # already done: no second call
        self.assertEqual(done, [task])

    def test_stopped_series_history_ends_at_last_occurrence(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.stop_recurrence(self.read)
        history = self.db.history(self.read, today=day(5), working_days=WEEKDAYS)
        self.assertEqual([h["date"] for h in history], [MON])


if __name__ == "__main__":
    unittest.main()
