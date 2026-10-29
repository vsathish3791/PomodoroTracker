"""The day's Energy signal: a hint, inferred from how the day went in the app.

Only a hint for your journal (it sets the tone of the questions and suggests a mood you
confirm). Rules, checked top to bottom:

    No data   - the app wasn't used that day
    Rest day  - not a working day and fewer than 2 pomodoros
    High      - pomodoros >= 90% of the daily goal and friction <= 1
    Low       - pomodoros < 40% of the goal, or friction >= 4,
                or 2+ blocks stopped early with 30+ minutes lost
    Steady    - everything else

friction = stopped early + distractions + 2 x tasks that felt like Panic.
The percentages and the friction limit can be changed in Settings -> Goals.

Plain Python (no Qt, no database) so it is easy to test.
"""

from dataclasses import asdict, dataclass, fields

ENERGY = {"high": "🟢 High", "steady": "🔵 Steady", "low": "🟠 Low",
          "rest": "⚪ Rest day", "none": "— No data"}


@dataclass
class EnergyThresholds:
    high_percent: int = 90        # of the daily goal
    low_percent: int = 40
    low_friction: int = 4
    high_friction: int = 1
    low_stopped: int = 2          # blocks stopped early ...
    low_minutes_lost: int = 30    # ... losing at least this many minutes

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EnergyThresholds":
        known = {f.name for f in fields(cls)}
        return cls(**{k: int(v) for k, v in data.items() if k in known})


@dataclass
class DayFacts:
    pomodoros: int
    goal: int
    stopped: int = 0
    minutes_lost: int = 0
    distractions: int = 0
    panic: int = 0                # finished tasks rated Panic
    working_day: bool = True
    used: bool = True             # any session, finished task or logged event that day


def infer_energy(facts: DayFacts,
                 limits: EnergyThresholds = EnergyThresholds()) -> tuple[str, str]:
    """(ENERGY key, a short reason in plain words)."""
    if not facts.used:
        return "none", "No pomodoros or finished tasks recorded"
    friction = facts.stopped + facts.distractions + 2 * facts.panic
    ratio = facts.pomodoros / facts.goal if facts.goal else 0
    if not facts.working_day and facts.pomodoros < 2:
        key = "rest"
    elif ratio * 100 >= limits.high_percent and friction <= limits.high_friction:
        key = "high"
    elif (ratio * 100 < limits.low_percent or friction >= limits.low_friction
          or (facts.stopped >= limits.low_stopped
              and facts.minutes_lost >= limits.low_minutes_lost)):
        key = "low"
    else:
        key = "steady"

    reason = [f"{facts.pomodoros}/{facts.goal} 🍅"]
    if facts.stopped:
        reason.append(f"{facts.stopped} stopped early"
                      + (f" ({facts.minutes_lost} min lost)" if facts.minutes_lost else ""))
    if facts.distractions:
        reason.append(f"{facts.distractions} distraction(s)")
    if facts.panic:
        reason.append(f"{facts.panic} Panic task(s)")
    if not facts.working_day:
        reason.append("not a working day")
    return key, " · ".join(reason)
