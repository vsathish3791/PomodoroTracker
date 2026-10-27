import unittest
from datetime import date, datetime, timedelta

from pomodoro import goals
from pomodoro.database import Database

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


def day(n: int) -> date:
    return MON + timedelta(days=n)


def focus(db, task_id, on: date, count=1, completed=True):
    for i in range(count):
        start = datetime.combine(on, datetime.min.time()) + timedelta(hours=9, minutes=30 * i)
        db.add_session("focus", start, start + timedelta(minutes=25), 25, completed,
                       task_id=task_id)


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.learning = self.db.create_project("Learning AI")
        self.task = self.db.create_task("Course", project_id=self.learning, nature="habit")
        self.other = self.db.create_task("Report", nature="improvement")

    def tearDown(self):
        self.db.close()

    def test_scope_counting(self):
        focus(self.db, self.task, MON, 3)
        focus(self.db, self.other, MON, 2)
        focus(self.db, self.task, MON, 1, completed=False)          # partial: not counted
        self.assertEqual(goals.pomodoros(self.db, MON, MON), 5)
        self.assertEqual(goals.pomodoros(self.db, MON, MON, ("project", str(self.learning))), 3)
        self.assertEqual(goals.pomodoros(self.db, MON, MON, ("nature", "improvement")), 2)
        self.assertEqual(goals.scope_label(self.db, ("project", str(self.learning))),
                         "Learning AI")

    def test_weekly_goal_pace(self):
        gid = self.db.create_goal("Learn AI weekly", "weekly", "project", self.learning, 10)
        goal = self.db.get_goal(gid)
        focus(self.db, self.task, MON, 2)
        # Wednesday: 3 of 5 working days -> expect 6; 2 done -> critical (33%)
        p = goals.goal_progress(self.db, goal, day(2), WEEKDAYS)
        self.assertEqual((p.done, p.status, p.text), (2, "critical", "2 / 10 🍅 this week"))
        focus(self.db, self.task, day(1), 3)                     # 5 done: 83% -> warning
        self.assertEqual(goals.goal_progress(self.db, goal, day(2), WEEKDAYS).status, "warning")
        focus(self.db, self.task, day(2), 5)                     # 10 -> done
        self.assertEqual(goals.goal_progress(self.db, goal, day(2), WEEKDAYS).status, "done")

    def test_by_date_goal_forecast(self):
        gid = self.db.create_goal("Course: 20 pomodoros", "by_date", "project", self.learning,
                                  20, deadline=day(18).isoformat(), start_date=MON.isoformat())
        goal = self.db.get_goal(gid)
        for n in range(5):                                       # 2 a day, Mon-Fri
            focus(self.db, self.task, day(n), 2)
        p = goals.goal_progress(self.db, goal, day(4), WEEKDAYS)
        # 10 done, 10 left; pace 2/day; 10 working days left -> needs 1/day -> on track
        self.assertEqual((p.done, p.status), (10, "good"))
        self.assertIn("At this pace: reached", p.detail)
        self.assertAlmostEqual(p.fraction, 0.5)

    def test_by_date_goal_missed_deadline_and_validation(self):
        gid = self.db.create_goal("Late", "by_date", "all", None, 50,
                                  deadline=day(2).isoformat(), start_date=MON.isoformat())
        p = goals.goal_progress(self.db, self.db.get_goal(gid), day(5), WEEKDAYS)
        self.assertEqual(p.status, "critical")
        self.assertIn("Deadline passed", p.detail)
        with self.assertRaises(ValueError):
            self.db.create_goal("No deadline", "by_date", "all", None, 5)
        with self.assertRaises(ValueError):
            self.db.create_goal("Zero", "weekly", "all", None, 0)
        with self.assertRaises(ValueError):
            self.db.create_goal("  ", "weekly", "all", None, 5)
        self.db.update_goal(gid, kind="weekly")
        self.assertIsNone(self.db.get_goal(gid)["deadline"])
        self.db.delete_goal(gid)
        self.assertEqual(self.db.list_goals(), [])

    def test_split_and_control_items(self):
        self.db.set_setting("nature_targets", '{"routine": 40, "habit": 20, "improvement": 40}')
        focus(self.db, self.task, MON, 2)                       # habit
        focus(self.db, self.other, MON, 2)                      # improvement
        shares, unset = goals.nature_split(self.db, MON, MON)
        self.assertEqual((shares["habit"], shares["improvement"], unset), (0.5, 0.5, 0))
        self.assertEqual(goals.split_targets(self.db)["improvement"], 40)
        self.assertEqual(goals.split_status(0.5, 40), "good" if abs(50 - 40) <= 5 else "warning")
        items = {i.name: i for i in goals.control_items(self.db, MON, WEEKDAYS)}
        self.assertEqual(items["Focus per working day"].value, "0.8 🍅")   # 4 over 5 working days
        self.assertEqual(items["Improvement share"].value, "50%")
        self.assertEqual(items["Habit consistency"].status, "none")
        self.assertEqual({i.group for i in items.values()}, {"lead", "lag"})


class EstimateTests(unittest.TestCase):
    def test_suggest_from_category_then_type(self):
        db = Database(":memory:")
        dev = db.get_or_create_category("Development")
        self.assertIsNone(goals.suggest_estimate(db, dev, "coding"))
        for n, count in enumerate([1, 2, 2, 4]):
            task = db.create_task(f"Dev {n}", category_id=dev, type="coding")
            focus(db, task, MON, count)
            db.set_task_status(task, "done")
        self.assertEqual(goals.suggest_estimate(db, dev, "coding"), (2, 4, "Development"))
        other = db.get_or_create_category("Meetings")
        self.assertEqual(goals.suggest_estimate(db, other, "coding"), (2, 4, "Coding"))
        db.close()


if __name__ == "__main__":
    unittest.main()
