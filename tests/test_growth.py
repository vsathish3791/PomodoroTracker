import unittest
from datetime import date, datetime, timedelta

from pomodoro import growth
from pomodoro.database import Database
from pomodoro.priority import rank_tasks

WEEKDAYS = {0, 1, 2, 3, 4}
TODAY = date(2026, 10, 28)


def session(db, task, day, hour, completed=True, minute=0, **practice):
    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
    return db.add_session("focus", start, start + timedelta(minutes=25),
                          25 if completed else 10, completed, task_id=task, **practice)


class BestHoursTests(unittest.TestCase):
    def test_peak_low_and_energy_now(self):
        db = Database(":memory:")
        task = db.create_task("Work")
        for n in range(6):                                  # mornings: strong
            day = TODAY - timedelta(days=n)
            session(db, task, day, 9)
            session(db, task, day, 10)
            session(db, task, day, 15, completed=n % 2 == 0)  # afternoons: half abandoned
        db.log_anomaly("distraction", at=f"{TODAY.isoformat()}T15:10:00")
        hours = growth.best_hours(db, TODAY)
        self.assertEqual(hours.peak, [9, 10])
        self.assertEqual(hours.low, [15])
        self.assertEqual(growth.hour_label(hours.peak), "9–11")
        self.assertTrue(hours.enough_data)
        self.assertEqual(growth.energy_now(db, datetime(2026, 10, 28, 9, 30)), "deep")
        self.assertEqual(growth.energy_now(db, datetime(2026, 10, 28, 15, 30)), "plan")
        self.assertIsNone(growth.energy_now(db, datetime(2026, 10, 28, 12, 0)))

    def test_not_enough_data(self):
        db = Database(":memory:")
        session(db, db.create_task("x"), TODAY, 9)
        self.assertFalse(growth.best_hours(db, TODAY).enough_data)
        self.assertIsNone(growth.energy_now(db, datetime(2026, 10, 28, 9, 30)))


class EnergyRankingTests(unittest.TestCase):
    def test_peak_hours_lift_deep_work_tasks(self):
        db = Database(":memory:")
        deep = db.create_task("Write concept note", energy_slot="deep")
        plain = db.create_task("Other")
        tasks = db.list_tasks("open")
        ranked = rank_tasks(tasks, TODAY, 8, 0, WEEKDAYS, energy_now="deep")
        self.assertEqual(ranked[0].id, deep)
        self.assertIn("fits your peak focus hours", ranked[0].reasons)
        neutral = rank_tasks(tasks, TODAY, 8, 0, WEEKDAYS)
        self.assertEqual(neutral[0].score, neutral[1].score)
        self.assertNotEqual(plain, deep)


class StretchAndPracticeTests(unittest.TestCase):
    def test_stretch_mix_and_advice(self):
        db = Database(":memory:")
        for stretch in ["comfort", "comfort", "comfort", "comfort", None]:
            task = db.create_task(f"T {stretch}")
            db.set_task_status(task, "done")
            db.set_stretch(task, stretch)
        counts, unrated, advice = growth.stretch_mix(db, date.today(), date.today())
        self.assertEqual((counts["comfort"], counts["stretch"], unrated), (4, 0, 1))
        self.assertIn("harder", advice)
        with self.assertRaises(ValueError):
            db.set_stretch(task, "boring")

    def test_practice_summary(self):
        db = Database(":memory:")
        task = db.create_task("Power BI")
        for n, difficulty in enumerate([5, 4, 3, 2]):
            sid = session(db, task, TODAY - timedelta(days=4 - n), 9,
                          practice_skill=" DAX ", practice_target="time intelligence")
            db.set_session_difficulty(sid, difficulty)
        rows = growth.practice_summary(db, TODAY - timedelta(days=10), TODAY)
        self.assertEqual((rows[0].skill, rows[0].sessions, rows[0].minutes), ("DAX", 4, 100))
        self.assertEqual((rows[0].first_difficulty, rows[0].recent_difficulty), (4.5, 2.5))
        self.assertEqual(db.practice_skills(), ["DAX"])
        with self.assertRaises(ValueError):
            db.set_session_difficulty(1, 9)


class ThenVsNowTests(unittest.TestCase):
    def test_comparison(self):
        db = Database(":memory:")
        dev = db.get_or_create_category("Development")
        # Then (31-60 days ago): 3 pomodoros per Development task, some abandoned
        for n in range(3):
            task = db.create_task(f"Old {n}", category_id=dev)
            day = TODAY - timedelta(days=40 + n)
            for _ in range(3):
                session(db, task, day, 9)
            session(db, task, day, 14, completed=False)
            db.set_task_status(task, "done")
            db.conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?",
                            (f"{day.isoformat()}T17:00:00", task))
        # Now: 2 per task, nothing abandoned
        for n in range(3):
            task = db.create_task(f"New {n}", category_id=dev)
            day = TODAY - timedelta(days=5 + n)
            for _ in range(2):
                session(db, task, day, 9)
            db.set_task_status(task, "done")
            db.conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?",
                            (f"{day.isoformat()}T17:00:00", task))
        db.conn.commit()
        rows = {r.name: r for r in growth.then_vs_now(db, TODAY)}
        dev_row = rows["🍅 per Development task (median)"]
        self.assertEqual((dev_row.then, dev_row.now, dev_row.better), ("3", "2", True))
        finished = rows["Pomodoros finished (not abandoned)"]
        self.assertEqual((finished.then, finished.now, finished.better), ("75%", "100%", True))
        db.close()


if __name__ == "__main__":
    unittest.main()
