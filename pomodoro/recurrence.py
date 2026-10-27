"""Date rules for recurring tasks (plain Python, no database or UI).

A series repeats daily, weekly or monthly from its start date until its end date:
  * daily   - every day, or only on your working days
  * weekly  - on chosen weekdays (0 = Monday ... 6 = Sunday)
  * monthly - on a day of the month; 29-31 fall back to the month's last day
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

FREQUENCIES = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Schedule:
    frequency: str                      # 'daily' | 'weekly' | 'monthly'
    start: date
    end: date
    workdays_only: bool = True          # daily only
    weekdays: list[int] = field(default_factory=list)   # weekly only
    month_day: int | None = None        # monthly only (defaults to the start's day)

    def __post_init__(self):
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"Frequency must be one of {list(FREQUENCIES)}")
        if self.end < self.start:
            raise ValueError("The end date must be on or after the start date")
        if self.frequency == "weekly" and not self.weekdays:
            self.weekdays = [self.start.weekday()]
        if self.frequency == "monthly" and not self.month_day:
            self.month_day = self.start.day

    def matches(self, day: date, working_days: set[int]) -> bool:
        """Is there an occurrence on this day?"""
        if not self.start <= day <= self.end:
            return False
        if self.frequency == "daily":
            return not self.workdays_only or day.weekday() in working_days
        if self.frequency == "weekly":
            return day.weekday() in self.weekdays
        last = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(self.month_day, last)

    def dates(self, first: date, last: date, working_days: set[int]) -> list[date]:
        """All occurrence dates between first and last (inclusive)."""
        first, last = max(first, self.start), min(last, self.end)
        days, day = [], first
        while day <= last:
            if self.matches(day, working_days):
                days.append(day)
            day += timedelta(days=1)
        return days

    def count(self, working_days: set[int]) -> int:
        return len(self.dates(self.start, self.end, working_days))

    def next_date(self, after: date, working_days: set[int]) -> date | None:
        """The first occurrence strictly after `after`, if any."""
        day = max(after + timedelta(days=1), self.start)
        while day <= self.end:
            if self.matches(day, working_days):
                return day
            day += timedelta(days=1)
        return None

    def describe(self) -> str:
        """e.g. 'Every working day until 15 Nov', 'Weekly on Mon, Thu until 31 Dec 2026'."""
        until = f"until {short_date(self.end)}"
        if self.frequency == "daily":
            what = "Every working day" if self.workdays_only else "Every day"
        elif self.frequency == "weekly":
            what = "Weekly on " + ", ".join(DAY_NAMES[d] for d in sorted(self.weekdays))
        else:
            suffix = "last day" if self.month_day >= 31 else ordinal(self.month_day)
            what = f"Monthly on the {suffix}"
        return f"{what} {until}"


def streaks(statuses: list[str]) -> tuple[int, int]:
    """(current, best) runs of done occurrences, oldest first in `statuses`.

    A still-open occurrence at the end (today's) doesn't break the current streak.
    """
    best = run = 0
    for status in statuses:
        if status == "done":
            run += 1
            best = max(best, run)
        elif status == "missed":
            run = 0
    current = 0
    for status in reversed(statuses):
        if status == "done":
            current += 1
        elif status == "missed":
            break
        elif current:          # an open one in the middle can't happen; stop to be safe
            break
    return current, best


def due_reminders(tasks: list[dict], now: datetime, already: set[int],
                  window_minutes: int = 15) -> list[dict]:
    """Today's open occurrences whose cue time has just arrived (within `window_minutes`)."""
    today = now.date().isoformat()
    due = []
    for task in tasks:
        cue = task.get("cue_time")
        if (not cue or not task.get("remind") or task["id"] in already
                or task.get("occurrence_date") != today):
            continue
        hours, minutes = (int(part) for part in cue.split(":"))
        cue_at = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if cue_at <= now <= cue_at + timedelta(minutes=window_minutes):
            due.append(task)
    return due


def parse_cue_time(text: str | None) -> str | None:
    """'8:30' -> '08:30'; blank -> None; anything else raises ValueError."""
    text = (text or "").strip()
    if not text:
        return None
    hours, minutes = text.split(":")
    hours, minutes = int(hours), int(minutes)
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError("Cue time must be like 08:30")
    return f"{hours:02d}:{minutes:02d}"


def short_date(day: date, today: date | None = None) -> str:
    today = today or date.today()
    return day.strftime("%d %b") if day.year == today.year else day.strftime("%d %b %Y")


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def schedule_from_row(row: dict) -> Schedule:
    """Build a Schedule from a `recurrences` database row."""
    weekdays = [int(d) for d in (row.get("weekdays") or "").split(",") if d.strip()]
    return Schedule(row["frequency"], date.fromisoformat(row["start_date"]),
                    date.fromisoformat(row["end_date"]), bool(row.get("workdays_only", 1)),
                    weekdays, row.get("month_day"))
