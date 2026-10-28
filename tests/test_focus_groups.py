"""Focus Next order: today's focus, daily, scheduled today, due today, overdue."""

import unittest
from datetime import date

from pomodoro.database import Database
from pomodoro.priority import OTHER, day_summary, focus_group, rank_tasks, should_warn

WED = date(2026, 10, 28)


def task(id_, title, priority=3, due=None, planned=None, recurrence=None, frequency=None):
    return {"id": id_, "title": title, "priority": priority, "due_date": due,
            "planned_date": planned, "recurrence_id": recurrence, "frequency": frequency,
            "estimate_pomodoros": None, "pomodoros": 0, "status": "todo"}


TASKS = [
    task(1, "Recruiters (weekly Tue, missed)", due="2026-10-27", recurrence=1,
         frequency="weekly"),
    task(2, "Executive presence (weekly Wed)", due="2026-10-28", recurrence=2,
         frequency="weekly"),
    task(3, "Read books (daily)", due="2026-10-28", recurrence=3, frequency="daily"),
    task(4, "AI Builder with n8n (planned)", due="2026-11-13", planned="2026-10-28"),
    task(5, "Report (one-off, due today)", priority=1, due="2026-10-28"),
    task(6, "Old one-off (overdue)", priority=1, due="2026-10-20"),
    task(7, "Later deadline", priority=1, due="2026-11-02"),
]


class FocusGroupTests(unittest.TestCase):
    def test_groups(self):
        groups = {t["title"]: focus_group(t, WED) for t in TASKS}
        self.assertEqual(list(groups.values()), [OTHER, 3, 2, 1, 4, 5, OTHER])

    def test_order_is_by_group_before_score(self):
        ranked = rank_tasks(TASKS, WED)
        self.assertEqual([s.id for s in ranked if s.in_focus_next], [4, 3, 2, 5, 6])
        self.assertEqual(ranked[0].reasons[0], "in today's focus")

    def test_summary_counts_only_focus_next(self):
        text = day_summary(rank_tasks(TASKS, WED), WED, 8, 0)
        self.assertEqual(text, "1 in today's focus  ·  1 overdue  ·  3 due today")

    def test_warns_when_starting_something_outside_todays_plan(self):
        ranked = rank_tasks(TASKS, WED)
        self.assertEqual(should_warn(7, ranked, WED).id, 4)       # later P1 vs planned
        self.assertIsNone(should_warn(4, ranked, WED))             # the planned one itself


class TaskListFilterTests(unittest.TestCase):
    def test_recent_open_tasks_by_project(self):
        db = Database(":memory:")
        career = db.create_project("Career")
        db.create_task("Update resume", project_id=career)
        db.create_task("Loose task")
        self.assertEqual(sorted(db.recent_open_tasks()), ["Loose task", "Update resume"])
        self.assertEqual(db.recent_open_tasks(project_id=career), ["Update resume"])
        self.assertEqual(db.recent_open_tasks(project_id=None), ["Loose task"])
        db.close()


if __name__ == "__main__":
    unittest.main()
