import unittest
from datetime import date, timedelta

from pomodoro.priority import (capacity_until, day_summary, find_at_risk, rank_tasks,
                               should_warn, urgency_weight)

TODAY = date(2026, 10, 26)            # a Monday
WEEKDAYS = {0, 1, 2, 3, 4}


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


_next_id = iter(range(1, 1000))


def task(title, priority=3, due=None, estimate=None, done=0, status="todo"):
    return {"id": next(_next_id), "title": title, "priority": priority, "due_date": due,
            "estimate_pomodoros": estimate, "pomodoros": done, "status": status}


def rank(tasks, goal=8, done_today=0):
    return rank_tasks(tasks, TODAY, goal, done_today, WEEKDAYS)


class UrgencyTests(unittest.TestCase):
    def test_urgency_weights(self):
        self.assertEqual(urgency_weight(None, TODAY), 0)
        self.assertEqual(urgency_weight(TODAY - timedelta(days=1), TODAY), 50)
        self.assertEqual(urgency_weight(TODAY, TODAY), 40)
        self.assertEqual(urgency_weight(TODAY + timedelta(days=1), TODAY), 30)
        self.assertEqual(urgency_weight(TODAY + timedelta(days=3), TODAY), 20)
        self.assertEqual(urgency_weight(TODAY + timedelta(days=7), TODAY), 10)
        self.assertEqual(urgency_weight(TODAY + timedelta(days=8), TODAY), 0)


class CapacityTests(unittest.TestCase):
    def test_today_counts_what_is_left_of_the_goal(self):
        self.assertEqual(capacity_until(TODAY, TODAY, 8, 3, WEEKDAYS), 5)
        self.assertEqual(capacity_until(TODAY, TODAY, 8, 10, WEEKDAYS), 0)

    def test_weekends_are_skipped(self):
        friday, next_monday = TODAY + timedelta(days=4), TODAY + timedelta(days=7)
        self.assertEqual(capacity_until(friday, TODAY, 8, 0, WEEKDAYS), 40)
        self.assertEqual(capacity_until(next_monday, TODAY, 8, 0, WEEKDAYS), 48)

    def test_past_due_has_no_capacity(self):
        self.assertEqual(capacity_until(TODAY - timedelta(days=1), TODAY, 8, 0, WEEKDAYS), 0)


class AtRiskTests(unittest.TestCase):
    def test_task_that_fits_is_not_at_risk(self):
        t = task("Fits", due=d(1), estimate=10)          # 16 available by tomorrow
        self.assertEqual(find_at_risk([t], TODAY, 8, 0, WEEKDAYS), set())

    def test_task_that_does_not_fit_is_at_risk(self):
        t = task("Too big", due=d(0), estimate=10)        # only 8 today
        self.assertEqual(find_at_risk([t], TODAY, 8, 0, WEEKDAYS), {t["id"]})

    def test_earlier_deadlines_use_up_capacity(self):
        first = task("Due today", due=d(0), estimate=8)
        second = task("Due tomorrow", due=d(1), estimate=9)   # 8 + 9 > 16
        risky = find_at_risk([first, second], TODAY, 8, 0, WEEKDAYS)
        self.assertEqual(risky, {second["id"]})

    def test_overdue_work_uses_up_capacity(self):
        late = task("Late", due=d(-1), estimate=6)
        today = task("Today", due=d(0), estimate=3)            # 6 + 3 > 8
        self.assertEqual(find_at_risk([late, today], TODAY, 8, 0, WEEKDAYS), {today["id"]})

    def test_progress_reduces_remaining_work(self):
        t = task("Half done", due=d(0), estimate=10, done=5)
        self.assertEqual(find_at_risk([t], TODAY, 8, 0, WEEKDAYS), set())

    def test_no_estimate_is_never_at_risk(self):
        t = task("Unknown size", due=d(0))
        self.assertEqual(find_at_risk([t], TODAY, 8, 0, WEEKDAYS), set())


class RankingTests(unittest.TestCase):
    def test_priority_and_due_date_combine(self):
        low_far = task("P4 no date", priority=4)
        high = task("P2 due in 10 days", priority=2, due=d(10))
        medium_today = task("P3 due today", priority=3, due=d(0))
        critical = task("P1 no date", priority=1)
        titles = [s.title for s in rank([low_far, high, medium_today, critical])]
        # P3 due today = 10 + 40 = 50; P1 = 40; P2 far = 25; P4 = 0
        self.assertEqual(titles, ["P3 due today", "P1 no date", "P2 due in 10 days",
                                  "P4 no date"])

    def test_risk_bonus_is_added(self):
        t = task("Too big", priority=3, due=d(0), estimate=20)
        scored = rank([t])[0]
        self.assertTrue(scored.at_risk)
        self.assertEqual(scored.score, 10 + 40 + 20)
        self.assertIn("at risk", scored.reasons)

    def test_ties_broken_by_due_date_then_remaining(self):
        a = task("Later", priority=2, due=d(20), estimate=5)
        b = task("Sooner", priority=2, due=d(15), estimate=5)
        c = task("Smaller", priority=2, due=d(20), estimate=1)
        self.assertEqual([s.title for s in rank([a, b, c])], ["Sooner", "Smaller", "Later"])

    def test_done_and_on_hold_are_left_out(self):
        titles = [s.title for s in rank([task("Open"), task("Done", status="done"),
                                         task("Hold", status="on_hold")])]
        self.assertEqual(titles, ["Open"])

    def test_reasons_text(self):
        s = rank([task("X", priority=1, due=d(0), estimate=4, done=1)])[0]
        self.assertEqual(s.short_reason(), "P1 Critical, due today, 3 🍅 left")


class WarningTests(unittest.TestCase):
    def test_warns_when_starting_low_priority_while_urgent_waits(self):
        urgent = task("API bug", priority=1, due=d(0))
        low = task("Tidy notes", priority=4)
        ranked = rank([urgent, low])
        self.assertEqual(should_warn(low["id"], ranked, TODAY).id, urgent["id"])

    def test_no_warning_when_starting_the_top_task(self):
        urgent = task("API bug", priority=1, due=d(0))
        ranked = rank([urgent, task("Other", priority=4)])
        self.assertIsNone(should_warn(urgent["id"], ranked, TODAY))

    def test_no_warning_when_top_task_is_not_urgent(self):
        top = task("P2 next month", priority=2, due=d(30))
        low = task("P4", priority=4)
        self.assertIsNone(should_warn(low["id"], rank([top, low]), TODAY))

    def test_no_warning_for_equal_scores(self):
        a = task("A", priority=1)
        b = task("B", priority=1)
        self.assertIsNone(should_warn(b["id"], rank([a, b]), TODAY))


class SummaryTests(unittest.TestCase):
    def test_summary(self):
        ranked = rank([task("Late", due=d(-1), estimate=3),
                       task("Today", due=d(0), estimate=4),
                       task("Later", due=d(5))])
        self.assertEqual(day_summary(ranked, TODAY, 8, 2),
                         "1 overdue  ·  1 due today  ·  7 🍅 needed today, 6 left in your goal")

    def test_nothing_urgent(self):
        self.assertEqual(day_summary(rank([task("Someday")]), TODAY, 8, 0),
                         "Nothing urgent today. 👍")


if __name__ == "__main__":
    unittest.main()
