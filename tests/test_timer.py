import unittest
from datetime import datetime, timedelta

from pomodoro.timer import Phase, PomodoroTimer, TimerSettings


class FakeClock:
    """Lets tests move time forward instantly."""

    def __init__(self):
        self.seconds = 0.0
        self.start = datetime(2026, 10, 26, 9, 0, 0)

    def monotonic(self):
        return self.seconds

    def now(self):
        return self.start + timedelta(seconds=self.seconds)

    def advance(self, minutes):
        self.seconds += minutes * 60


def make_timer(**settings):
    clock = FakeClock()
    timer = PomodoroTimer(TimerSettings(**settings), clock=clock.monotonic, now=clock.now)
    records = []
    timer.on_phase_finished = records.append
    return timer, clock, records


class PomodoroTimerTests(unittest.TestCase):
    def test_full_focus_block_then_break_starts_automatically(self):
        timer, clock, records = make_timer()
        timer.start()
        self.assertEqual(timer.phase, Phase.FOCUS)

        clock.advance(25)
        timer.tick()

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].completed)
        self.assertEqual(records[0].elapsed_seconds, 25 * 60)
        self.assertEqual(timer.phase, Phase.BREAK)
        self.assertTrue(timer.running)
        self.assertEqual(timer.remaining_seconds(), 5 * 60)

    def test_after_break_focus_waits_for_start(self):
        timer, clock, records = make_timer()
        timer.start()
        clock.advance(25)
        timer.tick()
        clock.advance(5)
        timer.tick()

        self.assertEqual(timer.phase, Phase.FOCUS)
        self.assertFalse(timer.running)
        self.assertFalse(timer.started)
        self.assertEqual([r.phase for r in records], [Phase.FOCUS, Phase.BREAK])

    def test_pause_time_is_not_counted(self):
        timer, clock, _ = make_timer()
        timer.start()
        clock.advance(10)
        timer.pause()
        clock.advance(30)                 # paused for 30 min
        self.assertEqual(timer.remaining_seconds(), 15 * 60)
        timer.start()
        clock.advance(5)
        self.assertEqual(timer.remaining_seconds(), 10 * 60)

    def test_stop_logs_partial_block_and_resets(self):
        timer, clock, records = make_timer()
        timer.start()
        clock.advance(12)
        timer.stop()

        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].completed)
        self.assertEqual(records[0].elapsed_seconds, 12 * 60)
        self.assertEqual(timer.phase, Phase.IDLE)
        self.assertEqual(timer.pomodoros_in_cycle, 0)

    def test_skip_focus_goes_to_break_without_counting_pomodoro(self):
        timer, clock, records = make_timer()
        timer.start()
        clock.advance(3)
        timer.skip()
        self.assertEqual(timer.phase, Phase.BREAK)
        self.assertFalse(records[0].completed)
        self.assertEqual(timer.pomodoros_in_cycle, 0)

    def test_skip_does_nothing_when_idle(self):
        timer, _, records = make_timer()
        timer.skip()
        self.assertEqual(timer.phase, Phase.IDLE)
        self.assertEqual(records, [])

    def test_long_break_after_every_fourth_pomodoro_when_enabled(self):
        timer, clock, _ = make_timer(long_break_enabled=True, auto_start_focus=True)
        breaks = []
        timer.start()
        for _ in range(4):
            clock.advance(25)
            timer.tick()
            breaks.append(timer.phase)
            clock.advance(timer.remaining_seconds() / 60)
            timer.tick()
        self.assertEqual(breaks, [Phase.BREAK] * 3 + [Phase.LONG_BREAK])
        self.assertEqual(timer.pomodoros_in_cycle, 0)

    def test_no_long_break_by_default(self):
        timer, clock, _ = make_timer(auto_start_focus=True)
        timer.start()
        for _ in range(4):
            clock.advance(25)
            timer.tick()
            self.assertEqual(timer.phase, Phase.BREAK)
            clock.advance(5)
            timer.tick()


if __name__ == "__main__":
    unittest.main()
