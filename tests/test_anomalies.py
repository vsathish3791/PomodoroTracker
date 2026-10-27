import unittest
from datetime import date, datetime, timedelta

from pomodoro import reports
from pomodoro.database import Database

WEEKDAYS = {0, 1, 2, 3, 4}
MON = date(2026, 10, 26)


class AnomalyTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_log_label_and_unlabelled_list(self):
        task = self.db.create_task("Report")
        a = self.db.log_anomaly("stopped", task_id=task, minutes_lost=15)
        self.db.log_anomaly("distraction", task_id=task)
        self.assertEqual([x["id"] for x in self.db.unlabelled_anomalies()], [a])  # not distraction
        self.db.set_anomaly_reason(a, "meeting", "Boss called")
        self.assertEqual(self.db.unlabelled_anomalies(), [])
        with self.assertRaises(ValueError):
            self.db.log_anomaly("sneezed")
        with self.assertRaises(ValueError):
            self.db.set_anomaly_reason(a, "aliens")

    def test_missed_occurrences_are_logged(self):
        self.db.create_recurrence("Standup", frequency="daily", start_date=MON.isoformat(),
                                  end_date=(MON + timedelta(days=20)).isoformat())
        with self.db.conn:
            self.db.conn.execute("UPDATE recurrences SET created_at = '2026-01-01T00:00'")
        self.db.generate_occurrences(MON, WEEKDAYS)
        self.db.generate_occurrences(MON + timedelta(days=3), WEEKDAYS)   # Mon, Tue, Wed missed
        missed = [a for a in self.db.unlabelled_anomalies() if a["kind"] == "missed"]
        self.assertEqual(len(missed), 3)
        self.assertEqual(sorted(a["happened_at"][:10] for a in missed),
                         ["2026-10-26", "2026-10-27", "2026-10-28"])

    def test_late_finish_is_logged_once(self):
        late = self.db.create_task("Overdue", due_date="2020-01-01")
        on_time = self.db.create_task("Fine", due_date="2099-01-01")
        self.db.set_task_status(late, "done")
        self.db.set_task_status(late, "done")
        self.db.set_task_status(on_time, "done")
        kinds = [(a["kind"], a["task_id"]) for a in self.db.unlabelled_anomalies()]
        self.assertEqual(kinds, [("late", late)])

    def test_pareto(self):
        day = datetime(2026, 10, 26, 10, 0).isoformat()
        for reason, minutes in [("interrupted", 10), ("interrupted", 5), ("meeting", 20),
                                ("interrupted", 8), (None, 3)]:
            self.db.log_anomaly("stopped", reason=reason, minutes_lost=minutes, at=day)
        self.db.log_anomaly("distraction", at=day)
        rows, summary = reports.anomaly_pareto(self.db, MON, MON)
        self.assertEqual([(r.reason, r.count) for r in rows],
                         [("Interrupted", 3), ("Distraction", 1), ("Meeting", 1)])
        self.assertAlmostEqual(rows[0].share, 0.6)
        self.assertAlmostEqual(rows[-1].cumulative, 1.0)
        self.assertEqual(rows[0].minutes_lost, 23)
        self.assertEqual((summary["stopped"], summary["distraction"], summary["unlabelled"],
                          summary["minutes_lost"]), (5, 1, 1, 46))


if __name__ == "__main__":
    unittest.main()
