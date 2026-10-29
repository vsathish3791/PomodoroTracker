import unittest
from datetime import date, datetime, timedelta

from pomodoro import lists, planning
from pomodoro.database import Database
from pomodoro.daylog import build_day_log

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


def focus(db, task_id, on, count=1):
    for i in range(count):
        start = datetime.combine(on, datetime.min.time()) + timedelta(hours=9, minutes=30 * i)
        db.add_session("focus", start, start + timedelta(minutes=25), 25, True, task_id=task_id)


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.set_setting("daily_goal", 6)
        rec = self.db.create_recurrence("Standup", nature="routine", estimate_pomodoros=1,
                                        frequency="daily", start_date=MON.isoformat(),
                                        end_date=(MON + timedelta(days=20)).isoformat(),
                                        cue_time="09:00")
        self.habit = self.db.create_recurrence("Read", nature="habit", estimate_pomodoros=1,
                                               frequency="daily", workdays_only=0,
                                               start_date=MON.isoformat(),
                                               end_date=(MON + timedelta(days=20)).isoformat(),
                                               cue_time="07:30")
        with self.db.conn:
            self.db.conn.execute("UPDATE recurrences SET created_at = '2026-01-01T00:00'")
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.rec = rec
        self.report = self.db.create_task("Report", estimate_pomodoros=3, due_date="2026-11-30")
        self.deck = self.db.create_task("Deck", estimate_pomodoros=4)

    def tearDown(self):
        self.db.close()

    def test_plan_does_not_touch_due_date_and_shows_in_today(self):
        self.db.plan_task(self.report, MON)
        task = self.db.get_task(self.report)
        self.assertEqual((task["planned_date"], task["due_date"]), ("2026-10-26", "2026-11-30"))
        titles = {t["title"] for t in lists.list_content(self.db, "today", MON).open_tasks}
        self.assertIn("Report", titles)
        self.db.plan_task(self.report, None)
        self.assertIsNone(self.db.get_task(self.report)["planned_date"])

    def test_day_tasks_and_capacity(self):
        self.db.plan_task(self.report, MON)
        self.db.plan_task(self.deck, MON)
        routine, planned = planning.day_tasks(self.db, MON)
        self.assertEqual([t["title"] for t in routine], ["Read", "Standup"])   # by cue time
        self.assertEqual({t["title"] for t in planned}, {"Report", "Deck"})
        cap = planning.capacity(self.db, MON)
        self.assertEqual((cap.available, cap.routine, cap.planned, cap.over), (6, 2, 7, 3))
        focus(self.db, self.report, MON, 2)
        cap = planning.capacity(self.db, MON)
        self.assertEqual((cap.available, cap.planned), (4, 5))

    def test_day_summary_and_day_log(self):
        self.db.plan_task(self.report, MON)
        self.db.plan_task(self.deck, MON)
        focus(self.db, self.deck, MON, 2)
        self.db.set_task_status(self.deck, "done")
        self.db.conn.execute("UPDATE tasks SET completed_at = '2026-10-26T15:00:00' "
                             "WHERE id = ?", (self.deck,))
        read = self.db.find_open_task("Read")
        self.db.set_task_status(read, "done")
        self.db.conn.execute("UPDATE tasks SET completed_at = '2026-10-26T08:00:00' "
                             "WHERE id = ?", (read,))
        self.db.conn.commit()
        self.db.log_anomaly("stopped", reason="meeting", minutes_lost=12,
                            at="2026-10-26T11:00:00")
        summary = planning.day_summary(self.db, MON)
        self.assertEqual(summary.pomodoros, 2)
        self.assertEqual(summary.habits, (1, 1))
        self.assertEqual(summary.routines, (0, 1))
        self.assertEqual([t["title"] for t in summary.unfinished_planned], ["Report"])
        log = build_day_log(self.db, MON)
        self.assertEqual([(t.title, t.pomodoros, t.minutes) for t in log.completed],
                         [("Read", 0, 0), ("Deck", 2, 50)])
        self.assertEqual(sorted(log.focus), [("Deck", True), ("Report", False)])
        self.assertEqual(log.focus_text, "2 planned · 1 done")
        self.assertEqual(log.interruptions_text(), "1 stopped early (12 min lost) · "
                                                   "top cause: Meeting")
        self.assertEqual((log.energy, log.energy_reason),
                         ("low", "2/6 🍅 · 1 stopped early (12 min lost)"))     # 2 of 6 < 40%
        text = log.markdown()
        for part in ("# Mon 26 Oct 2026 – Day log", "## ✅ Completed",
                     "- Deck – 2 🍅, 50 min", "- ○ not done – Report", "Habits 1/1",
                     "- Cause – Meeting: 1"):
            self.assertIn(part, text)
        planning.move_to(self.db, [self.report], MON + timedelta(days=1))
        self.assertEqual(self.db.get_task(self.report)["planned_date"], "2026-10-27")

    def test_week_report(self):
        self.db.create_goal("Focus", "weekly", "all", None, 20, start_date=MON.isoformat())
        self.db.plan_task(self.report, MON)
        focus(self.db, self.deck, MON, 3)
        self.db.log_anomaly("stopped", reason="interrupted", minutes_lost=10,
                            at="2026-10-26T10:00:00")
        report = planning.week_report(self.db, MON, today=MON + timedelta(days=4))
        md = report.markdown()
        for heading in ("## 1. Planned", "## 2. Done and results", "## 3. Problems",
                        "## Next actions"):
            self.assertIn(heading, md)
        self.assertIn("Goal: Focus (All work) – 20 🍅 a week", md)
        self.assertIn("3 pomodoros", md)
        self.assertIn("Cause: Interrupted", md)
        self.assertIn("Countermeasure for the top cause “Interrupted”", md)
        self.assertIn("1 planned task(s) not finished: Report", md)
        self.assertEqual(planning.last_monday(MON + timedelta(days=3)), MON)


if __name__ == "__main__":
    unittest.main()
