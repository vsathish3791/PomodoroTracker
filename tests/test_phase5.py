import unittest

from pomodoro.database import Database
from pomodoro.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_shortcut
from pomodoro.priority import DEFAULT_WEIGHTS, ScoreWeights, rank_tasks
from pomodoro.timer import Phase, PomodoroTimer, TimerSettings


class ShortcutParsingTests(unittest.TestCase):
    def test_supported_shortcuts(self):
        self.assertEqual(parse_shortcut("Ctrl+Alt+P"), (MOD_CONTROL | MOD_ALT, ord("P")))
        self.assertEqual(parse_shortcut("ctrl+shift+5"), (MOD_CONTROL | MOD_SHIFT, ord("5")))
        self.assertEqual(parse_shortcut("Alt+F9"), (MOD_ALT, 0x78))
        self.assertEqual(parse_shortcut("Meta+Space"), (MOD_WIN, 0x20))

    def test_unsupported_shortcuts(self):
        self.assertIsNone(parse_shortcut("P"))              # no modifier
        self.assertIsNone(parse_shortcut("Shift+P"))        # Shift alone would block typing
        self.assertIsNone(parse_shortcut("Ctrl+Alt+Home"))  # key not supported
        self.assertIsNone(parse_shortcut("Hyper+P"))
        self.assertIsNone(parse_shortcut(""))


class TimerSettingsChangeTests(unittest.TestCase):
    def test_running_block_keeps_its_length_when_settings_change(self):
        clock = [0.0]
        timer = PomodoroTimer(TimerSettings(), clock=lambda: clock[0])
        timer.start()
        clock[0] += 10 * 60
        timer.settings = TimerSettings(focus_minutes=50, break_minutes=10)
        self.assertEqual(timer.remaining_seconds(), 15 * 60)    # still a 25-minute block

        clock[0] += 15 * 60
        timer.tick()
        self.assertEqual(timer.phase, Phase.BREAK)
        self.assertEqual(timer.remaining_seconds(), 10 * 60)    # new break length

    def test_idle_timer_shows_new_length_straight_away(self):
        timer = PomodoroTimer(TimerSettings())
        timer.settings = TimerSettings(focus_minutes=45)
        self.assertEqual(timer.remaining_seconds(), 45 * 60)


class ScoreWeightTests(unittest.TestCase):
    def test_round_trip_and_unknown_keys(self):
        weights = ScoreWeights.from_dict({"p1": 60, "at_risk": "5", "colour": 3})
        self.assertEqual((weights.p1, weights.at_risk, weights.p2), (60, 5, 25))
        self.assertEqual(ScoreWeights.from_dict(weights.to_dict()), weights)
        self.assertEqual(ScoreWeights.from_dict({}), DEFAULT_WEIGHTS)

    def test_custom_weights_change_the_ranking(self):
        tasks = [
            {"id": 1, "title": "P1 no date", "priority": 1, "due_date": None,
             "estimate_pomodoros": None, "pomodoros": 0, "status": "todo"},
            {"id": 2, "title": "P4 overdue", "priority": 4, "due_date": "2020-01-01",
             "estimate_pomodoros": None, "pomodoros": 0, "status": "todo"},
        ]
        default_top = rank_tasks(tasks)[0].title                     # 50 > 40
        priority_first = ScoreWeights(p1=100)
        self.assertEqual(default_top, "P4 overdue")
        self.assertEqual(rank_tasks(tasks, weights=priority_first)[0].title, "P1 no date")

    def test_weights_saved_in_settings(self):
        db = Database(":memory:")
        self.assertEqual(db.get_json("score_weights"), {})
        db.set_setting("score_weights", '{"p1": 70}')
        self.assertEqual(ScoreWeights.from_dict(db.get_json("score_weights")).p1, 70)
        db.set_setting("score_weights", "not json")
        self.assertEqual(db.get_json("score_weights"), {})
        self.assertEqual(db.get_setting("hotkey"), "Ctrl+Alt+P")


if __name__ == "__main__":
    unittest.main()
