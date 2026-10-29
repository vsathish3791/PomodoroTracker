"""Energy signal rules (energy.py)."""

import unittest

from pomodoro.energy import DayFacts, EnergyThresholds, infer_energy


class EnergyTests(unittest.TestCase):
    def test_rules_in_order(self):
        cases = [
            (DayFacts(0, 8, used=False), "none"),
            (DayFacts(1, 8, working_day=False), "rest"),
            (DayFacts(8, 8, distractions=1), "high"),
            (DayFacts(8, 8, distractions=2), "steady"),          # full goal but friction 2
            (DayFacts(3, 8), "low"),                              # 37% < 40%
            (DayFacts(5, 8, stopped=1, distractions=1, panic=1), "low"),     # friction 4
            (DayFacts(6, 8, stopped=2, minutes_lost=30), "low"),
            (DayFacts(5, 8, stopped=1, minutes_lost=10), "steady"),
            (DayFacts(4, 8, working_day=False), "steady"),        # worked on a day off
        ]
        for facts, expected in cases:
            self.assertEqual(infer_energy(facts)[0], expected, facts)

    def test_reason_is_plain_words(self):
        key, reason = infer_energy(DayFacts(2, 8, stopped=3, minutes_lost=40, distractions=1))
        self.assertEqual((key, reason),
                         ("low", "2/8 🍅 · 3 stopped early (40 min lost) · 1 distraction(s)"))

    def test_thresholds_can_change(self):
        relaxed = EnergyThresholds(high_percent=60, low_percent=20)
        self.assertEqual(infer_energy(DayFacts(5, 8), relaxed)[0], "high")
        self.assertEqual(infer_energy(DayFacts(3, 8), relaxed)[0], "steady")
        self.assertEqual(EnergyThresholds.from_dict({"low_percent": "30", "x": 1}).low_percent, 30)


if __name__ == "__main__":
    unittest.main()
