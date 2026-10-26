"""The pomodoro cycle: focus -> break -> focus -> ...

This module is plain Python with no Qt, so it is easy to read and to test.
The UI calls `tick()` about once a second; the timer measures real elapsed
time with a monotonic clock, so it never drifts even if ticks are late.

Each phase is in one of three states:
  * ready   - phase chosen, not started yet (waiting for Start)
  * running - counting down
  * paused  - started, then paused
"""

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable


class Phase(Enum):
    IDLE = "idle"              # nothing started yet; Start begins a focus block
    FOCUS = "focus"
    BREAK = "break"
    LONG_BREAK = "long_break"

    @property
    def label(self) -> str:
        return {
            Phase.IDLE: "Ready",
            Phase.FOCUS: "Focus",
            Phase.BREAK: "Break",
            Phase.LONG_BREAK: "Long break",
        }[self]


@dataclass
class TimerSettings:
    focus_minutes: float = 25
    break_minutes: float = 5
    long_break_minutes: float = 15
    long_break_enabled: bool = False
    pomodoros_before_long_break: int = 4
    auto_start_break: bool = True
    auto_start_focus: bool = False

    @classmethod
    def from_db(cls, db) -> "TimerSettings":
        return cls(
            focus_minutes=db.get_int("focus_minutes"),
            break_minutes=db.get_int("break_minutes"),
            long_break_minutes=db.get_int("long_break_minutes"),
            long_break_enabled=db.get_bool("long_break_enabled"),
            pomodoros_before_long_break=db.get_int("pomodoros_before_long_break"),
            auto_start_break=db.get_bool("auto_start_break"),
            auto_start_focus=db.get_bool("auto_start_focus"),
        )


@dataclass
class PhaseRecord:
    """What happened in one finished (or abandoned) phase - saved as a session."""
    phase: Phase
    start: datetime
    end: datetime
    elapsed_seconds: float     # time actually spent counting down (pauses excluded)
    completed: bool            # True only if the phase ran its full length


class PomodoroTimer:
    def __init__(self, settings: TimerSettings,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = datetime.now):
        self.settings = settings
        self._clock = clock
        self._now = now

        # Callbacks the UI can set.
        self.on_phase_changed: Callable[[Phase, bool], None] = lambda phase, running: None
        self.on_phase_finished: Callable[[PhaseRecord], None] = lambda record: None

        self.phase = Phase.IDLE
        self.running = False
        self.pomodoros_in_cycle = 0       # completed focus blocks since the last long break
        self._reset_phase_clock()

    # ---------- queries ----------

    def duration_seconds(self, phase: Phase | None = None) -> float:
        """Length of a phase. A phase that has started keeps the length it started with,
        so changing settings mid-block only affects the next block."""
        if phase is None and self._locked_duration is not None:
            return self._locked_duration
        phase = phase or self.phase
        minutes = {
            Phase.IDLE: self.settings.focus_minutes,
            Phase.FOCUS: self.settings.focus_minutes,
            Phase.BREAK: self.settings.break_minutes,
            Phase.LONG_BREAK: self.settings.long_break_minutes,
        }[phase]
        return minutes * 60

    def elapsed_seconds(self) -> float:
        elapsed = self._accumulated
        if self.running:
            elapsed += self._clock() - self._resumed_at
        return elapsed

    def remaining_seconds(self) -> float:
        return max(0.0, self.duration_seconds() - self.elapsed_seconds())

    @property
    def started(self) -> bool:
        """True once the current phase has begun counting (running or paused)."""
        return self._phase_start is not None

    # ---------- controls ----------

    def start(self):
        """Start the current phase, or resume it if paused."""
        if self.running:
            return
        if self.phase == Phase.IDLE:
            self.phase = Phase.FOCUS
        if self._phase_start is None:
            self._locked_duration = self.duration_seconds(self.phase)
            self._phase_start = self._now()
        self._resumed_at = self._clock()
        self.running = True
        self.on_phase_changed(self.phase, True)

    def pause(self):
        if not self.running:
            return
        self._accumulated += self._clock() - self._resumed_at
        self.running = False
        self.on_phase_changed(self.phase, False)

    def toggle(self):
        self.pause() if self.running else self.start()

    def skip(self):
        """End the current phase early and move on to the next one."""
        if self.phase == Phase.IDLE:
            return
        self._finish(completed=False)

    def stop(self):
        """Abandon the current phase and go back to Ready."""
        if self.started:
            self._emit_record(completed=False)
        self.phase = Phase.IDLE
        self.running = False
        self._reset_phase_clock()
        self.on_phase_changed(self.phase, False)

    def tick(self):
        """Call regularly (e.g. every second). Finishes the phase when time is up."""
        if self.running and self.remaining_seconds() <= 0:
            self._finish(completed=True)

    # ---------- internals ----------

    def _reset_phase_clock(self):
        self._accumulated = 0.0
        self._resumed_at = 0.0
        self._phase_start: datetime | None = None
        self._locked_duration: float | None = None

    def _emit_record(self, completed: bool):
        elapsed = self.duration_seconds() if completed else self.elapsed_seconds()
        self.on_phase_finished(PhaseRecord(
            phase=self.phase,
            start=self._phase_start,
            end=self._now(),
            elapsed_seconds=elapsed,
            completed=completed,
        ))

    def _finish(self, completed: bool):
        finished = self.phase
        if self.started:
            self._emit_record(completed)
        if finished == Phase.FOCUS and completed:
            self.pomodoros_in_cycle += 1

        if finished == Phase.FOCUS:
            n = self.settings.pomodoros_before_long_break
            take_long = (self.settings.long_break_enabled and completed
                         and n > 0 and self.pomodoros_in_cycle % n == 0)
            next_phase = Phase.LONG_BREAK if take_long else Phase.BREAK
            auto = self.settings.auto_start_break
        else:
            if finished == Phase.LONG_BREAK:
                self.pomodoros_in_cycle = 0
            next_phase = Phase.FOCUS
            auto = self.settings.auto_start_focus

        self.phase = next_phase
        self.running = False
        self._reset_phase_clock()
        if auto:
            self.start()            # also fires on_phase_changed
        else:
            self.on_phase_changed(self.phase, False)
