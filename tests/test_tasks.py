import unittest
from datetime import date, datetime, timedelta

from pomodoro.database import Database
from pomodoro.models import due_label, is_overdue, pomodoro_progress


class TaskDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_default_categories_are_created_once(self):
        names = [c["name"] for c in self.db.list_categories()]
        self.assertIn("Development", names)
        self.db._seed_categories()          # running again must not duplicate
        self.assertEqual(len(self.db.list_categories()), len(names))

    def test_get_or_create_category(self):
        dev = self.db.get_or_create_category("development")
        self.assertEqual(dev, self.db.get_or_create_category("Development"))
        new = self.db.get_or_create_category("Interviews")
        self.assertIn("Interviews", [c["name"] for c in self.db.list_categories()])
        self.assertNotEqual(dev, new)
        self.assertIsNone(self.db.get_or_create_category("  "))

    def test_create_task_with_all_fields(self):
        cat = self.db.get_or_create_category("Development")
        task_id = self.db.create_task("Build login page", category_id=cat, type="coding",
                                      priority=1, due_date="2026-10-30",
                                      estimate_pomodoros=6, notes="OAuth too")
        task = self.db.get_task(task_id)
        self.assertEqual(task["category"], "Development")
        self.assertEqual(task["priority"], 1)
        self.assertEqual(task["due_date"], "2026-10-30")
        self.assertEqual(task["estimate_pomodoros"], 6)
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["pomodoros"], 0)

    def test_new_tasks_default_to_medium_priority_and_no_estimate(self):
        task = self.db.get_task(self.db.create_task("Quick task", estimate_pomodoros=0))
        self.assertEqual(task["priority"], 3)
        self.assertIsNone(task["estimate_pomodoros"])

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.db.create_task("x", priority=7)
        with self.assertRaises(ValueError):
            self.db.create_task("x", status="finished")
        with self.assertRaises(ValueError):
            self.db.create_task("x", type="music")
        with self.assertRaises(ValueError):
            self.db.create_task("x", colour="red")

    def test_mark_done_sets_and_reopen_clears_completed_at(self):
        task_id = self.db.create_task("Write report")
        self.db.set_task_status(task_id, "done")
        task = self.db.get_task(task_id)
        self.assertEqual(task["status"], "done")
        self.assertIsNotNone(task["completed_at"])

        self.db.set_task_status(task_id, "todo")
        self.assertIsNone(self.db.get_task(task_id)["completed_at"])

    def test_list_tasks_sorted_by_priority_then_due_date(self):
        self.db.create_task("Low", priority=4)
        self.db.create_task("High, due later", priority=2, due_date="2026-11-10")
        self.db.create_task("High, due soon", priority=2, due_date="2026-10-28")
        self.db.create_task("High, no date", priority=2)
        self.db.create_task("Critical", priority=1)
        titles = [t["title"] for t in self.db.list_tasks()]
        self.assertEqual(titles, ["Critical", "High, due soon", "High, due later",
                                  "High, no date", "Low"])

    def test_list_tasks_filters(self):
        dev = self.db.get_or_create_category("Development")
        a = self.db.create_task("Fix bug", category_id=dev)
        self.db.create_task("Team meeting notes")
        self.db.set_task_status(a, "done")

        self.assertEqual([t["title"] for t in self.db.list_tasks("open")], ["Team meeting notes"])
        self.assertEqual([t["title"] for t in self.db.list_tasks("done")], ["Fix bug"])
        self.assertEqual(len(self.db.list_tasks("all")), 2)
        self.assertEqual([t["title"] for t in self.db.list_tasks("all", category_id=dev)],
                         ["Fix bug"])
        self.assertEqual([t["title"] for t in self.db.list_tasks("all", search="meeting")],
                         ["Team meeting notes"])

    def test_list_tasks_includes_pomodoro_totals(self):
        task_id = self.db.create_task("Fix bug", estimate_pomodoros=4)
        t = datetime(2026, 10, 26, 9, 0)
        self.db.add_session("focus", t, t + timedelta(minutes=25), 25, True, task_id=task_id)
        self.db.add_session("focus", t, t + timedelta(minutes=25), 25, True, task_id=task_id)
        self.db.add_session("break", t, t + timedelta(minutes=5), 5, True)
        task = self.db.list_tasks()[0]
        self.assertEqual(task["pomodoros"], 2)
        self.assertEqual(task["focus_minutes"], 50)

    def test_delete_task_keeps_time_in_daily_totals(self):
        task_id = self.db.create_task("Typo task")
        t = datetime(2026, 10, 26, 9, 0)
        self.db.add_session("focus", t, t + timedelta(minutes=25), 25, True, task_id=task_id)
        self.db.delete_task(task_id)
        self.assertIsNone(self.db.get_task(task_id))
        self.assertEqual(self.db.day_stats(date(2026, 10, 26))["pomodoros"], 1)

    def test_starting_an_on_hold_task_moves_it_to_in_progress(self):
        task_id = self.db.create_task("Paused work", status="on_hold")
        self.assertEqual(self.db.get_or_create_task("paused work"), task_id)
        self.assertEqual(self.db.get_task(task_id)["status"], "in_progress")


class FormattingTests(unittest.TestCase):
    TODAY = date(2026, 10, 26)   # a Monday

    def test_due_label(self):
        self.assertEqual(due_label(None, self.TODAY), "")
        self.assertEqual(due_label("2026-10-24", self.TODAY), "Overdue (2 d)")
        self.assertEqual(due_label("2026-10-26", self.TODAY), "Today")
        self.assertEqual(due_label("2026-10-27", self.TODAY), "Tomorrow")
        self.assertEqual(due_label("2026-10-30", self.TODAY), "Fri 30 Oct")
        self.assertEqual(due_label("2026-12-15", self.TODAY), "15 Dec")
        self.assertEqual(due_label("2027-01-05", self.TODAY), "05 Jan 2027")

    def test_is_overdue(self):
        self.assertTrue(is_overdue("2026-10-25", self.TODAY))
        self.assertFalse(is_overdue("2026-10-26", self.TODAY))
        self.assertFalse(is_overdue(None, self.TODAY))

    def test_pomodoro_progress(self):
        self.assertEqual(pomodoro_progress(3, 8), "3 / 8")
        self.assertEqual(pomodoro_progress(3, None), "3")


if __name__ == "__main__":
    unittest.main()
