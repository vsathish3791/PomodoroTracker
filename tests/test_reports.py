import csv
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta

from pomodoro import reports
from pomodoro.database import Database
from pomodoro.models import CATEGORY_PALETTE, EXTRA_CATEGORY_COLOR
from pomodoro.priority import rank_tasks

DAY = date(2026, 10, 26)   # Monday


def at(day_offset: int, hour: int = 9) -> datetime:
    return datetime.combine(DAY + timedelta(days=day_offset), datetime.min.time()) \
        + timedelta(hours=hour)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        db = self.db
        dev = db.get_or_create_category("Development")
        meet = db.get_or_create_category("Meetings")
        self.bug = db.create_task("Fix bug", category_id=dev, type="coding", priority=1,
                                  due_date=DAY.isoformat(), estimate_pomodoros=2)
        self.sync = db.create_task("Team sync", category_id=meet, type="non-coding", priority=3)
        self.loose = db.create_task("No category task", type="non-coding", priority=4)
        self.gone = db.create_task("Deleted later")

        def focus(task_id, offset, minutes=25, completed=True, hour=9):
            start = at(offset, hour)
            db.add_session("focus", start, start + timedelta(minutes=minutes), minutes,
                           completed, task_id=task_id)

        focus(self.bug, 0)
        focus(self.bug, 0, hour=10)
        focus(self.bug, 1, minutes=10, completed=False)
        focus(self.sync, 0, hour=11)
        focus(self.loose, 2)
        focus(self.gone, 2, hour=10)
        focus(self.bug, 10)                               # outside the test range
        db.add_session("break", at(0, 12), at(0, 12) + timedelta(minutes=5), 5, True)
        db.delete_task(self.gone)

        self.start, self.end = DAY, DAY + timedelta(days=6)

    def tearDown(self):
        self.db.close()

    def test_effort_by_category(self):
        rows = reports.effort_by(self.db, self.start, self.end, "category")
        as_tuples = [(r.label, r.pomodoros, r.minutes) for r in rows]
        self.assertEqual(as_tuples, [
            ("Development", 2, 60.0),     # 25 + 25 + 10 partial; biggest first
            ("Meetings", 1, 25.0),
            ("No category", 1, 25.0),
            ("Unassigned", 1, 25.0),      # its task was deleted
        ])
        self.assertEqual(rows[0].color, CATEGORY_PALETTE[0])

    def test_effort_by_type_keeps_natural_order(self):
        rows = reports.effort_by(self.db, self.start, self.end, "type")
        self.assertEqual([(r.label, r.pomodoros) for r in rows],
                         [("Coding", 2), ("Non-coding", 2), ("Unassigned", 1)])

    def test_effort_by_priority(self):
        rows = reports.effort_by(self.db, self.start, self.end, "priority")
        self.assertEqual([(r.label, r.pomodoros) for r in rows],
                         [("P1 Critical", 2), ("P3 Medium", 1), ("P4 Low", 1), ("Unassigned", 1)])

    def test_daily_trend_includes_empty_days(self):
        trend = reports.daily_trend(self.db, self.start, self.end)
        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[0], (DAY, 3, 75.0))
        self.assertEqual(trend[1], (DAY + timedelta(days=1), 0, 10.0))
        self.assertEqual(trend[3][1:], (0, 0.0))

    def test_summary(self):
        self.db.set_task_status(self.bug, "done")
        self.db.conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?",
                             (at(1).isoformat(), self.bug))          # one day late
        self.db.add_override(self.sync, self.bug)
        result = reports.summary(self.db, self.start, DAY + timedelta(days=30))
        self.assertEqual(result["pomodoros"], 6)
        self.assertEqual(result["tasks_done"], 1)
        self.assertEqual((result["on_time"], result["late"]), (0, 1))

    def test_summary_counts_overrides_in_range(self):
        self.db.add_override(self.sync, self.bug)          # happens "now"
        today = date.today()
        self.assertEqual(reports.summary(self.db, today, today)["overrides"], 1)

    def test_csv_exports(self):
        folder = tempfile.mkdtemp()
        sessions_path = os.path.join(folder, "sessions.csv")
        tasks_path = os.path.join(folder, "tasks.csv")
        self.assertEqual(reports.export_sessions_csv(self.db, self.start, self.end,
                                                     sessions_path), 7)   # 6 focus + 1 break
        self.assertEqual(reports.export_tasks_csv(self.db, tasks_path), 3)
        with open(sessions_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["Task"], "Fix bug")
        self.assertEqual(rows[0]["Category"], "Development")
        self.assertEqual(rows[0]["Full pomodoro"], "Yes")
        with open(tasks_path, encoding="utf-8-sig") as f:
            titles = {r["Task"]: r for r in csv.DictReader(f)}
        self.assertEqual(titles["Fix bug"]["Pomodoros"], "3")


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        d = lambda n: (DAY + timedelta(days=n)).isoformat()
        for title, due, est in [("Late", d(-1), 2), ("Today", d(0), 4), ("Thursday", d(3), 3),
                                ("Next month", d(30), 5), ("Whenever", None, 1)]:
            self.db.create_task(title, due_date=due, estimate_pomodoros=est)
        self.ranked = rank_tasks(self.db.list_tasks("open"), DAY, 8, 0, {0, 1, 2, 3, 4})

    def tearDown(self):
        self.db.close()

    def test_deadline_board_groups(self):
        board = reports.deadline_board(self.ranked, DAY)
        self.assertEqual({k: [s.title for s in v] for k, v in board.items()}, {
            "Overdue": ["Late"], "Today": ["Today"], "This week": ["Thursday"],
            "Later": ["Next month"], "No date": ["Whenever"],
        })

    def test_workload(self):
        days = reports.workload(self.ranked, DAY, daily_goal=3, done_today=0,
                                working_days={0, 1, 2, 3, 4})
        self.assertEqual(len(days), 7)
        today = days[0]
        self.assertEqual((today.needed, today.available), (6, 3))   # overdue counts today
        self.assertTrue(today.overloaded)
        thursday = days[3]
        self.assertEqual(thursday.needed, 3)
        self.assertEqual((thursday.cumulative_needed, thursday.cumulative_available), (9, 12))
        self.assertFalse(thursday.overloaded)
        self.assertEqual(days[5].available, 0)                     # Saturday


class CategoryColorTests(unittest.TestCase):
    def test_new_categories_take_next_free_palette_colour(self):
        db = Database(":memory:")             # 7 defaults use the first 7 colours
        colors = {c["name"]: c["color"] for c in db.list_categories()}
        self.assertEqual(colors["Development"], CATEGORY_PALETTE[0])
        db.get_or_create_category("Interviews")
        db.get_or_create_category("Hiring")
        colors = {c["name"]: c["color"] for c in db.list_categories()}
        self.assertEqual(colors["Interviews"], CATEGORY_PALETTE[7])
        self.assertEqual(colors["Hiring"], EXTRA_CATEGORY_COLOR)

    def test_old_default_colours_are_upgraded(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        db = Database(path)
        db.conn.execute("UPDATE categories SET color = '#E5484D' WHERE name = 'Development'")
        db.conn.execute("UPDATE categories SET color = '#123456' WHERE name = 'Meetings'")
        db.conn.commit()
        db.close()
        db = Database(path)                   # reopening runs the upgrade
        colors = {c["name"]: c["color"] for c in db.list_categories()}
        self.assertEqual(colors["Development"], CATEGORY_PALETTE[0])
        self.assertEqual(colors["Meetings"], "#123456")   # user's own colour is kept
        db.close()


if __name__ == "__main__":
    unittest.main()
