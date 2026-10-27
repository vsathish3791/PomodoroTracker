import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta

from pomodoro.database import Database, clean_checklist

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


def day(n: int) -> date:
    return MON + timedelta(days=n)


def backdate(db: Database):
    """Tests simulate days before the real today: pretend the series are old."""
    with db.conn:
        db.conn.execute("UPDATE recurrences SET created_at = '2026-01-01T00:00:00'")


class RecurringTaskTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.work = self.db.create_project("Work")
        self.rec = self.db.create_recurrence(
            "Standup notes", project_id=self.work, estimate_pomodoros=1, frequency="daily",
            start_date=MON.isoformat(), end_date=day(11).isoformat(),
            checklist="- Yesterday\n- Today\n\n- Blockers")
        backdate(self.db)

    def tearDown(self):
        self.db.close()

    def occurrences(self):
        return [dict(r) for r in self.db.conn.execute(
            "SELECT occurrence_date, status, title, project_id, due_date, checklist, nature "
            "FROM tasks WHERE recurrence_id = ? ORDER BY occurrence_date", (self.rec,))]

    def test_creates_todays_occurrence_once(self):
        self.assertEqual(self.db.generate_occurrences(MON, WEEKDAYS), 1)
        self.assertEqual(self.db.generate_occurrences(MON, WEEKDAYS), 0)   # no duplicates
        occ = self.occurrences()[0]
        self.assertEqual((occ["occurrence_date"], occ["status"], occ["due_date"]),
                         (MON.isoformat(), "todo", MON.isoformat()))
        self.assertEqual(occ["project_id"], self.work)
        self.assertEqual(occ["checklist"], "Yesterday\nToday\nBlockers")
        self.assertEqual(occ["nature"], "routine")

    def test_unfinished_occurrence_is_missed_when_next_appears(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.generate_occurrences(day(1), WEEKDAYS)
        self.assertEqual([o["status"] for o in self.occurrences()], ["missed", "todo"])

    def test_done_occurrence_stays_done(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        first = self.db.find_open_task("Standup notes")
        self.db.set_task_status(first, "done")
        self.db.generate_occurrences(day(1), WEEKDAYS)
        self.assertEqual([o["status"] for o in self.occurrences()], ["done", "todo"])

    def test_catch_up_after_days_away_records_missed_days(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.generate_occurrences(day(7), WEEKDAYS)      # next Monday; weekend skipped
        occ = self.occurrences()
        self.assertEqual(len(occ), 6)                       # Mon..Fri + next Mon
        self.assertEqual([o["status"] for o in occ], ["missed"] * 5 + ["todo"])
        # Only one open occurrence, so the Timer can find it by name
        self.assertIsNotNone(self.db.find_open_task("Standup notes"))

    def test_weekend_creates_nothing_and_end_date_stops(self):
        self.db.generate_occurrences(day(5), WEEKDAYS)      # Saturday: catches up Mon-Fri
        self.assertEqual(self.occurrences()[-1]["occurrence_date"], day(4).isoformat())
        self.db.generate_occurrences(day(30), WEEKDAYS)     # long after the end date
        self.assertEqual(self.occurrences()[-1]["occurrence_date"], day(11).isoformat())

    def test_missed_and_done_are_not_open(self):
        self.db.generate_occurrences(day(1), WEEKDAYS)
        open_titles = [t["title"] for t in self.db.list_tasks("open")]
        self.assertEqual(open_titles, ["Standup notes"])
        self.assertEqual(len(self.db.list_tasks("all")), 2)

    def test_stats_and_description(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.set_task_status(self.db.find_open_task("Standup notes"), "done")
        self.db.generate_occurrences(day(2), WEEKDAYS)
        rec = self.db.list_recurrences(today=day(2), working_days=WEEKDAYS)[0]
        self.assertEqual((rec["done"], rec["missed"], rec["open"], rec["total"]), (1, 1, 1, 10))
        self.assertEqual(rec["describe"], "Every working day until 06 Nov")
        self.assertEqual(rec["next_date"], day(3))

    def test_upcoming_preview_excludes_created_and_past(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        upcoming = self.db.upcoming_occurrences(MON, day(6), today=MON, working_days=WEEKDAYS)
        self.assertEqual([u["date"] for u in upcoming], [day(1), day(2), day(3), day(4)])
        self.assertEqual(upcoming[0]["project"], "Work")

    def test_edit_series_changes_future_occurrences(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.update_recurrence(self.rec, title="Standup + plan", estimate_pomodoros=2)
        self.db.generate_occurrences(day(1), WEEKDAYS)
        occ = self.occurrences()
        self.assertEqual((occ[0]["title"], occ[1]["title"]), ("Standup notes", "Standup + plan"))

    def test_stop_and_delete(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.stop_recurrence(self.rec)
        self.assertEqual(self.db.generate_occurrences(day(1), WEEKDAYS), 0)
        self.assertEqual(self.occurrences()[0]["status"], "todo")     # current one kept
        # Delete: the untouched open occurrence goes, history stays as normal tasks
        self.db.set_task_status(self.db.find_open_task("Standup notes"), "done")
        self.db.delete_recurrence(self.rec)
        self.assertIsNone(self.db.get_recurrence(self.rec))
        self.assertEqual(len(self.db.list_tasks("done")), 1)

    def test_delete_removes_untouched_open_occurrence(self):
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.delete_recurrence(self.rec)
        self.assertEqual(self.db.list_tasks("all"), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.db.create_recurrence("No end", frequency="daily", start_date="2026-10-26")
        with self.assertRaises(ValueError):
            self.db.create_recurrence("Backwards", frequency="daily",
                                      start_date="2026-10-26", end_date="2026-10-01")
        with self.assertRaises(ValueError):
            self.db.create_recurrence("Bad", frequency="hourly",
                                      start_date="2026-10-26", end_date="2026-11-01")
        with self.assertRaises(ValueError):
            self.db.create_recurrence("Bad kind", frequency="daily", nature="hobby",
                                      start_date="2026-10-26", end_date="2026-11-01")

    def test_weekly_on_chosen_days(self):
        rec = self.db.create_recurrence("Report", frequency="weekly", weekdays=[0, 3],
                                        start_date=MON.isoformat(), end_date=day(13).isoformat())
        backdate(self.db)
        self.db.generate_occurrences(day(10), WEEKDAYS)       # Thursday of week 2
        dates = [r[0] for r in self.db.conn.execute(
            "SELECT occurrence_date FROM tasks WHERE recurrence_id = ? ORDER BY 1", (rec,))]
        self.assertEqual(dates, [MON.isoformat(), day(3).isoformat(), day(7).isoformat(),
                                 day(10).isoformat()])

    def test_checklist_progress_and_cleaning(self):
        self.assertEqual(clean_checklist("  * a \n\n• b\n"), "a\nb")
        self.assertIsNone(clean_checklist("  \n "))
        self.db.generate_occurrences(MON, WEEKDAYS)
        task = self.db.find_open_task("Standup notes")
        self.db.set_checklist_done(task, [2, 0, 0])
        self.assertEqual(self.db.get_task(task)["checklist_done"], "[0, 2]")

    def test_kind_of_work_on_normal_tasks(self):
        task = self.db.create_task("Build dashboard", nature="improvement")
        self.assertEqual(self.db.get_task(task)["nature"], "improvement")
        with self.assertRaises(ValueError):
            self.db.create_task("x", nature="chore")


class RecurringReportTests(unittest.TestCase):
    def test_summary_kind_of_work_and_reserved_time(self):
        from pomodoro import reports
        from pomodoro.priority import rank_tasks
        db = Database(":memory:")
        rec = db.create_recurrence("Standup", estimate_pomodoros=2, frequency="daily",
                                   start_date=MON.isoformat(), end_date=day(11).isoformat())
        backdate(db)
        db.generate_occurrences(MON, WEEKDAYS)
        db.set_task_status(db.find_open_task("Standup"), "done")
        db.generate_occurrences(day(2), WEEKDAYS)               # Tue missed, Wed open
        summary = reports.recurring_summary(db, MON, day(6))
        self.assertEqual((summary[0]["done"], summary[0]["missed"], summary[0]["open"]),
                         (1, 1, 1))
        self.assertAlmostEqual(summary[0]["rate"], 0.5)

        # Kind of work: focus time on a routine occurrence and an improvement task
        start = datetime.combine(MON, datetime.min.time())
        improve = db.create_task("Build dashboard", nature="improvement")
        for task_id in (db.find_open_task("Standup"), improve):
            db.add_session("focus", start, start + timedelta(minutes=25), 25, True,
                           task_id=task_id)
        rows = reports.effort_by(db, MON, MON, "nature")
        self.assertEqual([r.label for r in rows], ["Routine", "Improvement"])

        # Upcoming occurrences reserve time: a big task due Friday becomes at risk
        big = db.create_task("Report", due_date=day(4).isoformat(), estimate_pomodoros=10)
        reserved = [{"id": -1, "due_date": day(3).isoformat(), "estimate_pomodoros": 6,
                     "pomodoros": 0, "status": "todo", "priority": 3, "title": "x"}]
        tasks = db.list_tasks("open")
        no_reserve = {s.id: s for s in rank_tasks(tasks, day(2), 4, 0, WEEKDAYS)}
        with_reserve = {s.id: s for s in rank_tasks(tasks, day(2), 4, 0, WEEKDAYS,
                                                    reserved=reserved)}
        self.assertFalse(no_reserve[big].at_risk)         # 2 + 10 <= 4 + 4 + 4
        self.assertTrue(with_reserve[big].at_risk)        # + 6 reserved > 12
        days = reports.workload(rank_tasks(tasks, day(2), 4, 0, WEEKDAYS), day(2), 4, 0,
                                WEEKDAYS, days=3, reserved=reserved)
        self.assertEqual(days[1].needed, 6)               # Thursday holds the reserved time
        db.close()


class StatusUpgradeTests(unittest.TestCase):
    def test_quoted_table_name_from_earlier_upgrade_gets_missed_status(self):
        """The real v1.2 database stores CREATE TABLE "tasks" with a status CHECK."""
        path = os.path.join(tempfile.mkdtemp(), "v12.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE "tasks" (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                category_id INTEGER, type TEXT NOT NULL DEFAULT 'coding',
                priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
                due_date TEXT, estimate_pomodoros INTEGER,
                status TEXT NOT NULL DEFAULT 'todo'
                       CHECK (status IN ('todo', 'in_progress', 'on_hold', 'done')),
                notes TEXT, created_at TEXT NOT NULL, completed_at TEXT
            , project_id INTEGER, energy_slot TEXT, notion_url TEXT);
            CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id), kind TEXT NOT NULL,
                start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                duration_min REAL NOT NULL, completed INTEGER NOT NULL);
            INSERT INTO tasks (title, created_at, energy_slot) VALUES ('Old', '2026-05-01', 'deep');
            INSERT INTO sessions (task_id, kind, start_time, end_time, duration_min, completed)
                VALUES (1, 'focus', '2026-05-01T09:00', '2026-05-01T09:25', 25, 1);
        """)
        conn.commit()
        conn.close()
        db = Database(path)
        sql = db.conn.execute("SELECT sql FROM sqlite_master WHERE name = 'tasks'").fetchone()[0]
        self.assertNotIn("CHECK (status IN", sql)
        task = db.list_tasks("all")[0]
        self.assertEqual((task["title"], task["energy_slot"], task["pomodoros"]), ("Old", "deep", 1))
        db.set_task_status(task["id"], "missed")                  # allowed now
        self.assertEqual(db.get_task(task["id"])["status"], "missed")
        self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertGreater(db.create_task("New"), task["id"])
        db.close()


if __name__ == "__main__":
    unittest.main()
