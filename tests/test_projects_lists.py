import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta

from pomodoro import lists
from pomodoro.database import Database
from pomodoro.models import CATEGORY_PALETTE

TODAY = date(2026, 10, 28)   # a Wednesday


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_create_rename_and_colours(self):
        work = self.db.create_project("Work")
        study = self.db.create_project("  Study ")
        projects = self.db.list_projects()
        self.assertEqual([p["name"] for p in projects], ["Work", "Study"])
        self.assertEqual([p["color"] for p in projects], CATEGORY_PALETTE[:2])
        self.db.rename_project(study, "Learning")
        self.assertEqual(self.db.get_project(study)["name"], "Learning")
        self.db.rename_project(work, "work")              # same project, new case: fine
        self.assertEqual(self.db.get_or_create_project("WORK"), work)

    def test_names_must_be_unique_and_non_blank(self):
        self.db.create_project("Work")
        with self.assertRaises(ValueError):
            self.db.create_project("work")
        with self.assertRaises(ValueError):
            self.db.create_project("   ")
        other = self.db.create_project("Study")
        with self.assertRaises(ValueError):
            self.db.rename_project(other, "Work")
        self.assertIsNone(self.db.get_or_create_project(""))

    def test_tasks_in_projects_and_delete_keeps_tasks(self):
        work = self.db.create_project("Work")
        task = self.db.create_task("Report", project_id=work)
        self.db.create_task("Loose")
        self.assertEqual(self.db.get_task(task)["project"], "Work")
        self.assertEqual([t["title"] for t in self.db.list_tasks(project_id=work)], ["Report"])
        self.db.delete_project(work)
        self.assertIsNone(self.db.get_task(task)["project_id"])
        self.assertEqual(self.db.list_projects(), [])

    def test_old_database_gets_project_column(self):
        path = os.path.join(tempfile.mkdtemp(), "v1.db")
        conn = sqlite3.connect(path)            # a v1 tasks table without project_id
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT "
                     "NULL, category_id INTEGER, type TEXT NOT NULL DEFAULT 'coding', priority "
                     "INTEGER NOT NULL DEFAULT 3, due_date TEXT, estimate_pomodoros INTEGER, "
                     "status TEXT NOT NULL DEFAULT 'todo', notes TEXT, created_at TEXT NOT NULL, "
                     "completed_at TEXT)")
        conn.execute("INSERT INTO tasks (title, created_at) VALUES ('Old task', '2026-01-01')")
        conn.commit()
        conn.close()
        db = Database(path)
        task = db.list_tasks()[0]
        self.assertEqual(task["title"], "Old task")
        self.assertIsNone(task["project_id"])
        db.close()


class ListTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        db = self.db
        self.work = db.create_project("Work")
        self.study = db.create_project("Study")
        self.ids = {}
        for title, due, project, estimate in [
            ("Late", d(-2), self.work, 4),
            ("Today", d(0), self.work, 2),
            ("Tomorrow", d(1), self.study, 3),
            ("Sunday", d(4), None, 1),
            ("Next week", d(7), self.study, None),
            ("No date", None, self.work, 5),
        ]:
            self.ids[title] = db.create_task(title, due_date=due, project_id=project,
                                             estimate_pomodoros=estimate)
        # Finished today, and one finished yesterday
        self.ids["Done today"] = db.create_task("Done today", due_date=d(0), project_id=self.work)
        db.set_task_status(self.ids["Done today"], "done")
        db.conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?",
                        (f"{TODAY}T10:00:00", self.ids["Done today"]))
        old = db.create_task("Done before", due_date=d(-1))
        db.set_task_status(old, "done")
        db.conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?",
                        (f"{d(-1)}T10:00:00", old))
        # Focus time today on "Today" (25 + 10) and on "Done today" (25)
        start = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=9)
        db.add_session("focus", start, start + timedelta(minutes=25), 25, True,
                       task_id=self.ids["Today"])
        db.add_session("focus", start, start + timedelta(minutes=10), 10, False,
                       task_id=self.ids["Today"])
        db.add_session("focus", start, start + timedelta(minutes=25), 25, True,
                       task_id=self.ids["Done today"])

    def tearDown(self):
        self.db.close()

    def titles(self, view):
        content = lists.list_content(self.db, view, TODAY)
        return ({t["title"] for t in content.open_tasks}, {t["title"] for t in content.done_tasks})

    def test_smart_lists(self):
        self.assertEqual(self.titles("today"), ({"Late", "Today"}, {"Done today"}))
        self.assertEqual(self.titles("tomorrow")[0], {"Tomorrow"})
        self.assertEqual(self.titles("week")[0], {"Late", "Today", "Tomorrow", "Sunday"})
        self.assertEqual(self.titles("planned")[0],
                         {"Late", "Today", "Tomorrow", "Sunday", "Next week"})
        self.assertEqual(len(self.titles("all")[0]), 6)
        self.assertEqual(self.titles("completed"), (set(), {"Done today", "Done before"}))

    def test_project_list(self):
        self.assertEqual(self.titles(f"project:{self.work}"),
                         ({"Late", "Today", "No date"}, {"Done today"}))

    def test_stats(self):
        content = lists.list_content(self.db, "today", TODAY)
        stats = lists.list_stats(self.db, content, 25, TODAY)
        # Late: 4 left, Today: 2 estimated - 1 done = 1 left -> 5 x 25 min
        self.assertEqual(stats.estimated_minutes, 125)
        self.assertEqual(stats.to_complete, 2)
        self.assertEqual(stats.elapsed_minutes, 60)
        self.assertEqual(stats.completed, 1)

    def test_sidebar_counts(self):
        counts = lists.sidebar_counts(self.db, 25, TODAY)
        self.assertEqual(counts["today"], (2, 125))
        self.assertEqual(counts["completed"], (1, 0))
        self.assertEqual(counts[f"project:{self.study}"], (2, 75))

    def test_sorting_and_grouping(self):
        tasks = lists.list_content(self.db, "all", TODAY).open_tasks
        by_due = [t["title"] for t in lists.sort_tasks(tasks, "due", {})]
        self.assertEqual(by_due, ["Late", "Today", "Tomorrow", "Sunday", "Next week", "No date"])
        by_name = [t["title"] for t in lists.sort_tasks(tasks, "title", {})]
        self.assertEqual(by_name[0], "Late")
        order = {self.ids["No date"]: 0, self.ids["Sunday"]: 1}
        by_score = [t["title"] for t in lists.sort_tasks(tasks, "score", order)]
        self.assertEqual(by_score[:2], ["No date", "Sunday"])

        groups = lists.group_by_project(tasks, self.db.list_projects())
        self.assertEqual([(name, len(members)) for name, _, members in groups],
                         [("Work", 3), ("Study", 2), ("No project", 1)])

    def test_effort_by_project_report(self):
        from pomodoro import reports
        rows = reports.effort_by(self.db, TODAY, TODAY, "project")
        self.assertEqual([(r.label, r.minutes) for r in rows], [("Work", 60.0)])
        self.assertEqual(rows[0].color, CATEGORY_PALETTE[0])

    def test_format_minutes(self):
        self.assertEqual(lists.format_minutes(0), "0m")
        self.assertEqual(lists.format_minutes(45), "45m")
        self.assertEqual(lists.format_minutes(100), "1h 40m")


if __name__ == "__main__":
    unittest.main()
