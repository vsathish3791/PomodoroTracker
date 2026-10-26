import unittest
from datetime import date, datetime, timedelta

from pomodoro.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_default_settings(self):
        self.assertEqual(self.db.get_int("focus_minutes"), 25)
        self.assertEqual(self.db.get_int("break_minutes"), 5)
        self.assertFalse(self.db.get_bool("long_break_enabled"))

    def test_set_setting(self):
        self.db.set_setting("daily_goal", 10)
        self.db.set_setting("long_break_enabled", True)
        self.assertEqual(self.db.get_int("daily_goal"), 10)
        self.assertTrue(self.db.get_bool("long_break_enabled"))

    def test_day_stats_counts_only_completed_focus_blocks(self):
        day = date(2026, 10, 26)
        t = datetime(2026, 10, 26, 9, 0)
        self.db.add_session("focus", t, t + timedelta(minutes=25), 25, completed=True)
        self.db.add_session("break", t, t + timedelta(minutes=5), 5, completed=True)
        self.db.add_session("focus", t, t + timedelta(minutes=10), 10, completed=False)
        # A different day must not be counted.
        other = t - timedelta(days=1)
        self.db.add_session("focus", other, other + timedelta(minutes=25), 25, completed=True)

        stats = self.db.day_stats(day)
        self.assertEqual(stats["pomodoros"], 1)
        self.assertEqual(stats["focus_minutes"], 35)   # 25 full + 10 partial

    def test_get_or_create_task_reuses_open_task(self):
        first = self.db.get_or_create_task("Fix login bug")
        again = self.db.get_or_create_task("  fix   LOGIN bug ")   # same task, messy typing
        other = self.db.get_or_create_task("Write report")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        status = self.db.conn.execute("SELECT status FROM tasks WHERE id = ?", (first,)).fetchone()
        self.assertEqual(status["status"], "in_progress")

    def test_done_task_is_not_reused(self):
        first = self.db.get_or_create_task("Fix login bug")
        self.db.conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (first,))
        self.assertNotEqual(self.db.get_or_create_task("Fix login bug"), first)

    def test_empty_task_title_is_rejected(self):
        with self.assertRaises(ValueError):
            self.db.get_or_create_task("   ")

    def test_task_stats_and_recent_tasks(self):
        a = self.db.get_or_create_task("Task A")
        b = self.db.get_or_create_task("Task B")
        t = datetime(2026, 10, 26, 9, 0)
        self.db.add_session("focus", t, t + timedelta(minutes=25), 25, True, task_id=a)
        self.db.add_session("focus", t, t + timedelta(minutes=8), 8, False, task_id=a)
        later = datetime(2026, 10, 26, 11, 0)
        self.db.add_session("focus", later, later + timedelta(minutes=25), 25, True, task_id=b)

        self.assertEqual(self.db.task_stats(a), {"pomodoros": 1, "focus_minutes": 33})
        self.assertEqual(self.db.recent_open_tasks(), ["Task B", "Task A"])

    def test_tables_for_later_phases_exist(self):
        names = {row["name"] for row in self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"categories", "tasks", "sessions", "overrides", "settings"} <= names)


if __name__ == "__main__":
    unittest.main()
